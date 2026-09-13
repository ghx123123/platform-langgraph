"""dsh 引擎健壮性回归测试。

覆盖两个真实故障:
- A1: 桥把最终结果整行 JSON 打印, 长蓝图超过 asyncio 默认 64KiB 读行上限 → 请求挂死。
      修复: _spawn 传 limit=_STDOUT_LINE_LIMIT。
- A2: stdout reader 崩溃后请求白等 timeout。修复: 标记不健康 + 在途请求立即失败 + 下次请求重建桥。
"""
import asyncio
from typing import Any

import pytest

from backend.workflows.dsh_engine import DshAgentEngine, DshEngineError, _STDOUT_LINE_LIMIT


def _bare_engine() -> DshAgentEngine:
    engine = DshAgentEngine.__new__(DshAgentEngine)
    engine._healthy = True
    engine._reader_error = None
    engine._restarts = []
    engine._pending = {}
    engine._streams = {}
    engine._proc = None
    engine._stdout_task = None
    engine._stderr_task = None
    return engine


def test_stdout_line_limit_is_generous() -> None:
    """A1: 读行上限必须放得下长蓝图(45 页 ≈ 48KB 文本, JSON 转义后更大)。"""
    assert _STDOUT_LINE_LIMIT >= 1024 * 1024


@pytest.mark.asyncio
async def test_mark_unhealthy_fails_pending_requests_immediately() -> None:
    """A2: reader 崩溃后, 在途请求必须立刻失败, 而不是等满 timeout。"""
    engine = _bare_engine()
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict] = loop.create_future()
    engine._pending[42] = fut

    await engine._mark_unhealthy("readline limit exceeded")

    assert engine._healthy is False
    assert engine._reader_error == "readline limit exceeded"
    assert fut.done()
    with pytest.raises(DshEngineError, match="stdout reader exited"):
        fut.result()


@pytest.mark.asyncio
async def test_mark_unhealthy_notifies_stream_consumers() -> None:
    """A2: 流式调用不能因为 reader 崩溃而永远等哨兵。"""
    engine = _bare_engine()
    queue: asyncio.Queue = asyncio.Queue()
    engine._streams[1] = (queue, asyncio.get_running_loop())

    await engine._mark_unhealthy("stdout EOF")
    await asyncio.sleep(0)  # call_soon_threadsafe 投递

    item = queue.get_nowait()
    assert item["event"] == "error"
    assert "stdout reader exited" in item["error"]


@pytest.mark.asyncio
async def test_restart_budget_stops_runaway_restarts() -> None:
    """A2: 60 秒内重启超过 3 次要报错, 而不是无限重建。"""
    engine = _bare_engine()
    engine._reader_error = "boom"
    for _ in range(3):
        engine._check_restart_budget()
    with pytest.raises(DshEngineError, match="反复重启失败"):
        engine._check_restart_budget()


@pytest.mark.asyncio
async def test_ensure_started_rebuilds_when_unhealthy() -> None:
    """A2: 不健康时 ensure_started 必须收尸并重建桥。"""
    engine = _bare_engine()
    engine._healthy = False
    engine._reader_error = "reader died"
    spawned: list[str] = []
    torn_down: list[str] = []

    async def fake_spawn() -> Any:
        spawned.append("spawn")
        return object()

    async def fake_teardown(reason: str) -> None:
        torn_down.append(reason)

    engine._spawn = fake_spawn  # type: ignore[method-assign]
    engine._teardown_locked = fake_teardown  # type: ignore[method-assign]
    engine._lock = asyncio.Lock()

    await engine._ensure_started_internal()

    assert torn_down == ["stdout reader 已退出"]
    assert spawned == ["spawn"]
    assert engine._healthy is True
    assert engine._reader_error is None
    assert len(engine._restarts) == 1


@pytest.mark.asyncio
async def test_ensure_started_reuses_healthy_bridge() -> None:
    """健康桥不该被无谓重建。"""
    engine = _bare_engine()

    class _Proc:
        returncode = None

    engine._proc = _Proc()  # type: ignore[assignment]
    engine._lock = asyncio.Lock()
    spawned: list[str] = []

    async def fake_spawn() -> Any:
        spawned.append("spawn")
        return object()

    engine._spawn = fake_spawn  # type: ignore[method-assign]
    await engine._ensure_started_internal()
    assert spawned == []


def test_request_timeout_is_configurable() -> None:
    """A1 配套: 长蓝图需要更长的单次请求超时, 且不能低于默认 300s。"""
    engine = DshAgentEngine(default_model="m", request_timeout=900.0)
    assert engine._request_timeout == 900.0
    assert DshAgentEngine(default_model="m")._request_timeout == 300.0


def test_model_client_derives_engine_timeout_from_settings() -> None:
    """面板超时设置要传递到桥请求超时, 且至少 300s。"""
    from types import SimpleNamespace

    from backend.workflows.llm import ModelClient

    def client(timeout_seconds: float) -> ModelClient:
        return ModelClient(SimpleNamespace(
            provider="dsh", model="minimax-m3", api_key="", base_url="",
            temperature=0.3, timeout_seconds=timeout_seconds,
        ))

    assert client(600.0)._request_timeout == 600.0
    assert client(90.0)._request_timeout == 300.0
    assert client(0)._request_timeout == 300.0
