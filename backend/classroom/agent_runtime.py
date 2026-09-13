"""Thin, explicit-session boundary for classroom agents.

This module deliberately contains no teacher/student prompts or classroom
turn-taking.  It only maps a business agent identity to a deterministic DSH
session and delegates generation to :class:`DshAgentEngine`.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import AsyncIterator, Any

from backend.workflows.dsh_engine import DshAgentEngine


_SAFE_SESSION_PART = re.compile(r"[^A-Za-z0-9._:-]+")


@dataclass(frozen=True, slots=True)
class SessionKey:
    run_id: str
    round_number: int
    agent_id: str


@dataclass(slots=True)
class RuntimeSession:
    key: SessionKey
    session_id: str


class HarnessAgentRuntime:
    """Runtime cache and deterministic session-id factory.

    The cache is intentionally process-local.  Business state remains in the
    classroom repository; after a process restart, the same key deterministi-
    cally produces the same DSH session id and callers may reconstruct context.
    Requests are serialized at this boundary because the current stdio bridge
    is safest in serialized mode while request correlation remains explicit in
    ``DshAgentEngine``.
    """

    def __init__(self, engine: DshAgentEngine | None = None) -> None:
        self.engine = engine or DshAgentEngine()
        self._sessions: dict[SessionKey, RuntimeSession] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def build_session_id(run_id: str, round_number: int, agent_id: str) -> str:
        run = _normalise_part(run_id, "run_id")
        agent = _normalise_part(agent_id, "agent_id")
        if round_number < 1:
            raise ValueError("round_number must be >= 1")
        return f"{run}:r{round_number}:{agent}"

    def session_for(self, run_id: str, round_number: int, agent_id: str) -> RuntimeSession:
        key = SessionKey(run_id=run_id, round_number=round_number, agent_id=agent_id)
        current = self._sessions.get(key)
        if current is not None:
            return current
        session = RuntimeSession(key=key, session_id=self.build_session_id(run_id, round_number, agent_id))
        self._sessions[key] = session
        return session

    def clear_registry(self) -> None:
        """Drop runtime references without touching DSH durable sessions."""
        self._sessions.clear()

    def registry_size(self) -> int:
        return len(self._sessions)

    async def open(self, run_id: str, round_number: int, agent_id: str) -> RuntimeSession:
        session = self.session_for(run_id, round_number, agent_id)
        await self.engine.ensure_started()
        return session

    async def generate(
        self,
        run_id: str,
        round_number: int,
        agent_id: str,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        timeout: float = 300.0,
    ) -> str:
        session = await self.open(run_id, round_number, agent_id)
        async with self._lock:
            return await self.engine.generate_in_session(
                session.session_id,
                system_prompt,
                user_prompt,
                model=model,
                timeout=timeout,
            )

    async def generate_stream(
        self,
        run_id: str,
        round_number: int,
        agent_id: str,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        session = await self.open(run_id, round_number, agent_id)
        # Keep the stream request serialized for the lifetime of the iterator.
        await self._lock.acquire()
        try:
            async for item in self.engine.generate_stream_in_session(
                session.session_id,
                system_prompt,
                user_prompt,
                model=model,
            ):
                yield item
        finally:
            self._lock.release()

    async def health(self) -> dict[str, Any]:
        try:
            await self.engine.ensure_started()
            return {"ok": True, "registry_size": self.registry_size()}
        except Exception as exc:  # health endpoint should report, not hide
            return {"ok": False, "registry_size": self.registry_size(), "error": str(exc)}

    async def close(self) -> None:
        self.clear_registry()
        await self.engine.close()


def _normalise_part(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    safe = _SAFE_SESSION_PART.sub("_", text)
    if not safe:
        raise ValueError(f"{field} contains no usable session characters")
    return safe

