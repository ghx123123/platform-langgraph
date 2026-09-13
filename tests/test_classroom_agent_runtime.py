import asyncio
from typing import Any

import pytest

from backend.classroom.agent_runtime import HarnessAgentRuntime
from backend.workflows.dsh_engine import DshAgentEngine


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.started = 0
        self.closed = 0

    async def ensure_started(self) -> None:
        self.started += 1

    async def generate_in_session(self, session_id: str, system_prompt: str, user_prompt: str, **_: Any) -> str:
        self.calls.append((session_id, system_prompt, user_prompt))
        return f"{session_id}:{user_prompt}"

    async def generate_stream_in_session(self, session_id: str, system_prompt: str, user_prompt: str, **_: Any):
        self.calls.append((session_id, system_prompt, user_prompt))
        yield {"event": "done", "final_response": session_id}

    async def close(self) -> None:
        self.closed += 1


def test_session_id_is_deterministic_and_isolated() -> None:
    assert HarnessAgentRuntime.build_session_id("run123", 1, "teacher") == "run123:r1:teacher"
    assert HarnessAgentRuntime.build_session_id("run123", 1, "student:basic") != HarnessAgentRuntime.build_session_id("run123", 2, "student:basic")
    assert HarnessAgentRuntime.build_session_id("run123", 1, "teacher") != HarnessAgentRuntime.build_session_id("run123", 1, "student:basic")


@pytest.mark.asyncio
async def test_runtime_reuses_same_round_session_and_separates_agents() -> None:
    engine = FakeEngine()
    runtime = HarnessAgentRuntime(engine)
    first = await runtime.generate("run123", 1, "teacher", "system", "one")
    second = await runtime.generate("run123", 1, "teacher", "system", "two")
    student = await runtime.generate("run123", 1, "student:basic", "system", "answer")

    assert first.startswith("run123:r1:teacher:")
    assert second.startswith("run123:r1:teacher:")
    assert student.startswith("run123:r1:student:basic:")
    assert [call[0] for call in engine.calls] == ["run123:r1:teacher", "run123:r1:teacher", "run123:r1:student:basic"]
    assert runtime.registry_size() == 2


@pytest.mark.asyncio
async def test_round_two_gets_new_session_and_registry_restart_is_recoverable() -> None:
    engine = FakeEngine()
    runtime = HarnessAgentRuntime(engine)
    await runtime.generate("run123", 1, "student:basic", "system", "r1")
    runtime.clear_registry()
    await runtime.generate("run123", 2, "student:basic", "system", "r2")
    assert [call[0] for call in engine.calls] == ["run123:r1:student:basic", "run123:r2:student:basic"]


@pytest.mark.asyncio
async def test_stream_uses_explicit_session() -> None:
    engine = FakeEngine()
    runtime = HarnessAgentRuntime(engine)
    items = [item async for item in runtime.generate_stream("run", 1, "teacher", "s", "u")]
    assert items[0]["final_response"] == "run:r1:teacher"


@pytest.mark.asyncio
async def test_runtime_serializes_generate_calls() -> None:
    class SlowEngine(FakeEngine):
        async def generate_in_session(self, session_id: str, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
            await asyncio.sleep(0.01)
            return await super().generate_in_session(session_id, system_prompt, user_prompt, **kwargs)

    engine = SlowEngine()
    runtime = HarnessAgentRuntime(engine)
    await asyncio.gather(
        runtime.generate("run", 1, "teacher", "s", "a"),
        runtime.generate("run", 1, "student:basic", "s", "b"),
    )
    assert len(engine.calls) == 2


@pytest.mark.asyncio
async def test_engine_explicit_session_forwards_to_bridge_payload() -> None:
    engine = DshAgentEngine.__new__(DshAgentEngine)
    captured: dict[str, Any] = {}

    async def fake_send(payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        captured.update(payload)
        return {"ok": True, "final_response": "ok"}

    async def fake_run_on_loop(coro: Any, timeout: float) -> Any:
        return await coro

    engine._default_model = "test-model"
    engine._send = fake_send  # type: ignore[method-assign]
    engine._run_on_loop = fake_run_on_loop  # type: ignore[method-assign]
    engine._stderr_tail = lambda: ""  # type: ignore[method-assign]

    result = await engine.generate_in_session("run:r1:teacher", "system", "prompt")
    assert result == "ok"
    assert captured["params"]["session_id"] == "run:r1:teacher"


@pytest.mark.asyncio
async def test_legacy_generate_still_uses_ephemeral_session() -> None:
    engine = DshAgentEngine.__new__(DshAgentEngine)
    captured: dict[str, Any] = {}

    async def fake_send(payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        captured.update(payload)
        return {"ok": True, "final_response": "ok"}

    async def fake_run_on_loop(coro: Any, timeout: float) -> Any:
        return await coro

    engine._default_model = "test-model"
    engine._send = fake_send  # type: ignore[method-assign]
    engine._run_on_loop = fake_run_on_loop  # type: ignore[method-assign]
    engine._stderr_tail = lambda: ""  # type: ignore[method-assign]

    await engine.generate("system", "prompt")
    assert captured["params"]["session_id"]
