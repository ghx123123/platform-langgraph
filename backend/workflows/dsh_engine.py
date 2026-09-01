"""DshAgentEngine — 平台内嵌 dsh 智能体引擎。

用 stdio 桥子进程(venv python 运行 dsh_agent_bridge.py)驱动 dsh 智能体,
每次调用新建一个 session, 桥与 dsh 智能体进程常驻复用。
平台进程(base python)与 dsh SDK 隔离, 不受 site-packages 污染影响。
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("multi_agent_platform.dsh_engine")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_SCRIPT = _PROJECT_ROOT / "scripts" / "dsh_agent_bridge.py"
_VENV_PYTHON = Path(os.environ.get("DSH_ENGINE_PYTHON", str(_PROJECT_ROOT / "dev-venv-dshsdk" / "Scripts" / "python.exe")))


class DshEngineError(RuntimeError):
    """dsh 引擎调用失败。"""


class DshAgentEngine:
    """管理一个 stdio 桥子进程, 提供 generate 能力(仅依赖文本输入/输出)。

    桥子进程及其全部 I/O 跑在一个**常驻的独立 ProactorEventLoop(后台线程)**上,
    与主 app 的 event loop 类型解耦。这样 uvicorn 即便在 Win+reload 下强制 Selector loop
    (不支持 asyncio.create_subprocess_exec) 也能正常 spawn 桥 —— 避免 NotImplementedError
    导致 run 在 content_analysis 节点失败、前端看不到生成过程。
    """

    def __init__(
        self,
        session_root: Path | None = None,
        cwd: Path | None = None,
        default_model: str = "minimax-m3",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._session_root = session_root or (_PROJECT_ROOT / ".runtime" / "dsh-sessions")
        self._cwd = cwd or (_PROJECT_ROOT / ".runtime" / "dsh-workspace")
        self._default_model = default_model
        self._api_key = api_key or ""
        self._base_url = base_url or ""
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._streams: dict[int, asyncio.Queue] = {}
        self._next_id = 1
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_lines: list[str] = []
        self._lock = asyncio.Lock()
        # 常驻独立 Proactor loop 线程: 桥的所有 subprocess + I/O 都在它上面跑, 与主 loop 无关。
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._thread_started = False

    def _ensure_loop_thread(self) -> asyncio.AbstractEventLoop:
        """懒启动后台线程, 在它上面建一个 Proactor loop(Windows)。返回该 loop。"""
        if self._loop is not None and self._loop.is_running():
            return self._loop
        if sys.platform == "win32":
            # 只有 Proactor loop 支持 create_subprocess_exec; 与主 app loop 类型解耦
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="dsh-agent-loop", daemon=True)
        self._thread.start()
        self._thread_started = True
        return self._loop

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _run_on_loop(self, coro: Any, timeout: float) -> Any:
        """把协程投递到独立 loop 线程执行, 在主 loop 上等待, 不跨 loop 传 future(避免 wrong-loop 错误)。"""
        loop = self._ensure_loop_thread()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)

    @property
    def default_model(self) -> str:
        return self._default_model

    async def ensure_started(self) -> None:
        """懒启动桥子进程。(并发安全) 在独立 loop 线程上执行。"""
        await self._run_on_loop(self._ensure_started_internal(), timeout=30)

    async def _ensure_started_internal(self) -> None:
        async with self._lock:
            if self._proc is not None and self._proc.returncode is None:
                return
            self._proc = await self._spawn()
            self._stdout_task = asyncio.create_task(self._read_stdout())
            self._stderr_task = asyncio.create_task(self._read_stderr())

    async def _spawn(self) -> asyncio.subprocess.Process:
        env = os.environ.copy()
        # 面板填的 key/base_url 优先于进程环境变量(如 dev 启动时的 shell env)
        if self._api_key:
            env["MINIMAX_API_KEY"] = self._api_key
            env["DEEPSEEK_API_KEY"] = self._api_key
        if self._base_url:
            env["DSH_BASE_URL"] = self._base_url
        env.update({
            "DSH_CWD": str(self._cwd),
            "DSH_SESSION_ROOT": str(self._session_root),
            "DSH_MODEL": self._default_model,
            "PYTHONUTF8": "1",
        })
        # 桥进程从项目 cwd 启动(它用相对路径解析 cordis / node)
        return await asyncio.create_subprocess_exec(
            str(_VENV_PYTHON),
            "-X", "utf8",
            str(_BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_PROJECT_ROOT),
            env=env,
        )

    async def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("dsh bridge: non-JSON stdout: %.200s", text)
                    continue
                rid = int(msg.get("id", -1))
                # 流式消息(chunk/phase/request) → 经线程安全投递到主 loop 的流队列
                if msg.get("event") in ("chunk", "phase", "request"):
                    for key, (queue, main_loop) in list(self._streams.items()):
                        if isinstance(key, int) and key == rid:
                            try:
                                main_loop.call_soon_threadsafe(queue.put_nowait, msg)
                            except RuntimeError:
                                pass
                    continue
                fut = self._pending.pop(rid, None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("dsh bridge stdout reader crashed")

    async def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                self._stderr_lines.append(text)
                if len(self._stderr_lines) > 200:
                    self._stderr_lines.pop(0)
        except asyncio.CancelledError:
            pass

    async def _send(self, payload: dict, timeout: float = 300.0, rid: int | None = None) -> dict:
        await self.ensure_started()
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            raise DshEngineError(f"dsh bridge not running (rc={proc.returncode if proc else 'none'})")
        if rid is None:
            rid = self._next_id
            self._next_id += 1
        payload["id"] = rid
        fut: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        try:
            proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await proc.stdin.drain()
        except BrokenPipeError:
            self._pending.pop(rid, None)
            raise DshEngineError(f"dsh bridge pipe closed: {self._stderr_tail()}") from None
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise DshEngineError(f"dsh bridge request timed out after {timeout}s") from None
        return msg

    def _stderr_tail(self) -> str:
        return "\n".join(self._stderr_lines[-15:])

    async def generate_stream(self, system_prompt: str, user_prompt: str, model: str | None = None):
        """dsh 流式生成: async generator, 逐 chunk yield {"event":"chunk","text"} / {"event":"phase"}。

        桥端 stream:true 时 on_notification 把 text-delta 实时打 stdio(每行JSON);
        引擎在独立 loop 线程的 _read_stdout 收, 经 run_coroutine_threadsafe 投到主 loop 的队列。
        哨兵 {"event":"done","final_response"} 表示结束。
        """
        queue: asyncio.Queue = asyncio.Queue()
        main_loop = asyncio.get_running_loop()
        user_id = object()
        # 注册"流接受方"(跨 loop): _read_stdout 在独立 loop 线程, 用 run_coroutine_threadsafe 投递
        self._streams[user_id] = (queue, main_loop)

        async def _runner() -> str:
            """独立 loop 上执行真实请求(内部 _send 也是那个 loop 的协程)。"""
            try:
                result = await self._generate_stream_request(system_prompt, user_prompt, model, user_id)
                try:
                    asyncio.run_coroutine_threadsafe(queue.put({
                        "event": "done",
                        "final_response": str(result.get("final_response") or ""),
                        "finish_reason": str(result.get("finish_reason") or ""),
                    }), main_loop)
                except RuntimeError:
                    pass
                return str(result.get("final_response") or "")
            except Exception as exc:
                try:
                    asyncio.run_coroutine_threadsafe(queue.put({"event": "error", "error": str(exc)}), main_loop)
                except RuntimeError:
                    pass
                raise
            finally:
                self._streams.pop(user_id, None)

        task = asyncio.run_coroutine_threadsafe(_runner(), self._ensure_loop_thread())
        # 主 loop 消费队列直到哨兵
        while True:
            item = await queue.get()
            if item.get("event") == "done":
                yield item
                break
            if item.get("event") == "error":
                raise DshEngineError(str(item.get("error") or "dsh stream error"))
            yield item
        # runner 完成或异常: 阻止 task 泄漏
        try:
            await asyncio.wrap_future(task)
        except Exception:
            pass

    async def _generate_stream_request(
        self, system_prompt: str, user_prompt: str, model: str | None, stream_key,
    ) -> dict:
        """在独立 loop 上跑: 预注册数字 rid→(queue,main_loop) 以便 _read_stdout 投递 chunk; _send 发请求."""
        # 先领取 rid(与 _send 内一致的自增逻辑), 预注册 flow
        rid = self._next_id
        self._next_id += 1
        queue, main_loop = self._streams[stream_key]
        self._streams[rid] = (queue, main_loop)
        try:
            msg = await self._send({
                "method": "generate",
                "params": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "session_id": str(uuid.uuid4()),
                    "model": model or self._default_model,
                    "stream": True,
                },
            }, rid=rid)
            return msg
        finally:
            self._streams.pop(rid, None)

    async def generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """一次智能体调用: 返回最终响应文本。模型不同时桥会重建 harness(换 provider/model)。"""
        return await self._run_on_loop(self._generate_internal(system_prompt, user_prompt, model), timeout=300)

    async def _generate_internal(self, system_prompt: str, user_prompt: str, model: str | None) -> str:
        msg = await self._send({
            "method": "generate",
            "params": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "session_id": str(uuid.uuid4()),
                "model": model or self._default_model,
            },
        })
        if not msg.get("ok"):
            raise DshEngineError(str(msg.get("error") or "unknown dsh error") + f"\n{self._stderr_tail()}")
        # 桥已把常见错误翻译为中文说明(额度不足/401等); finish_reason=error 时优先展示翻译文本
        if msg.get("finish_reason") == "error":
            raw = msg.get("error") or self._stderr_tail() or "dsh agent finished with error"
            raise DshEngineError(str(raw).strip())
        return str(msg.get("final_response") or "")

    async def agent_run(
        self,
        system_prompt: str,
        user_prompt: str,
        iterations: int = 2,
        model: str | None = None,
        session_id: str | None = None,
        round_focus: str | None = None,
        timeout: float = 600.0,
    ) -> dict:
        """多轮自主迭代(复用 session 保记忆): 每轮基于上一轮产出修订, 越迭代越收敛。

        - 复用 session_id(不换新) → dsh 多轮记忆, 记住各轮上下文。
        - iterations 控制迭代轮数(桥端 clamp 到 1-5)。
        - return {"final_response", "iterations", "turns"} 或可在调用方重建 prompt 的 raw 迭代。
        """
        return await self._run_on_loop(
            self._agent_run_internal(system_prompt, user_prompt, iterations, model, session_id, round_focus, timeout),
            timeout=timeout,
        )

    async def _agent_run_internal(
        self,
        system_prompt: str,
        user_prompt: str,
        iterations: int,
        model: str | None,
        session_id: str | None,
        round_focus: str | None,
        timeout: float,
    ) -> dict:
        msg = await self._send({
            "method": "agent_run",
            "params": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "session_id": session_id or str(uuid.uuid4()),
                "model": model or self._default_model,
                "iterations": max(1, min(int(iterations), 5)),
                "round_focus": round_focus or "请把上一版成果规范化、补全遗漏、修正疏漏，并给出更完整、更可用的最终版。",
            },
        }, timeout=timeout)
        if not msg.get("ok"):
            raise DshEngineError(str(msg.get("error") or "unknown dsh error") + f"\n{self._stderr_tail()}")
        if msg.get("finish_reason") == "error":
            raw = msg.get("error") or self._stderr_tail() or "dsh agent_run finished with error"
            raise DshEngineError(str(raw).strip())
        return {
            "final_response": str(msg.get("final_response") or ""),
            "iterations": int(msg.get("iterations") or 0),
            "turns": msg.get("turns") or [],
        }

    async def _run_on_loop(self, coro: Any, timeout: float) -> Any:
        """把协程投递到独立 loop 线程执行, 在主 loop 上等待, 不跨 loop 传 future(避免 wrong-loop 错误)。"""
        loop = self._ensure_loop_thread()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)

    async def close(self) -> None:
        await self._run_on_loop(self._close_internal(), timeout=10)

    async def _close_internal(self) -> None:
        proc = self._proc
        if proc is None:
            return
        for task in (self._stdout_task, self._stderr_task):
            if task is not None:
                task.cancel()
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (ProcessLookupError, asyncio.TimeoutError):
            proc.kill()
        self._proc = None
