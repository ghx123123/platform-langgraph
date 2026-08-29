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
import uuid
from pathlib import Path

logger = logging.getLogger("multi_agent_platform.dsh_engine")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_SCRIPT = _PROJECT_ROOT / "scripts" / "dsh_agent_bridge.py"
_VENV_PYTHON = Path(os.environ.get("DSH_ENGINE_PYTHON", str(_PROJECT_ROOT / "dev-venv-dshsdk" / "Scripts" / "python.exe")))


class DshEngineError(RuntimeError):
    """dsh 引擎调用失败。"""


class DshAgentEngine:
    """管理一个 stdio 桥子进程, 提供 generate 能力(仅依赖文本输入/输出)。"""

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
        self._next_id = 1
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_lines: list[str] = []
        self._lock = asyncio.Lock()

    @property
    def default_model(self) -> str:
        return self._default_model

    async def ensure_started(self) -> None:
        """懒启动桥子进程。(并发安全)"""
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
                fut = self._pending.pop(int(msg.get("id", -1)), None)
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

    async def _send(self, payload: dict, timeout: float = 300.0) -> dict:
        await self.ensure_started()
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            raise DshEngineError(f"dsh bridge not running (rc={proc.returncode if proc else 'none'})")
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

    async def generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """一次智能体调用: 返回最终响应文本。模型不同时桥会重建 harness(换 provider/model)。"""
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

    async def close(self) -> None:
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
