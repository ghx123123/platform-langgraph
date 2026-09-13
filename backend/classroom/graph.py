"""LangGraph macro-flow adapter for classroom_v2.

The legacy teaching_v1 graph remains untouched.  This graph is intentionally a
thin phase coordinator; classroom turn-taking stays in ClassroomOrchestrator
and domain persistence stays in the classroom services.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph


class ClassroomGraphState(TypedDict, total=False):
    run_id: str
    phase: str
    round_number: int
    max_rounds: int
    lesson_version_id: str
    supervisor_report_id: str | None
    revision_patch_ids: list[str]
    finalized: bool
    error: str | None


PhaseHandler = Callable[[ClassroomGraphState], Awaitable[dict[str, Any]]]


def build_classroom_graph(*, handlers: dict[str, PhaseHandler] | None = None, checkpointer: Any | None = None):
    """Build PREPARATION → SIMULATION → REVIEW → REVISION loop.

    Handlers are injected at the application boundary, keeping this graph free
    of DSH, FastAPI and prompt details.  A handler returns state deltas only.
    """
    handlers = handlers or {}

    async def preparation(state: ClassroomGraphState) -> dict[str, Any]:
        result = await handlers["preparation"](state) if "preparation" in handlers else {}
        return {**result, "phase": "CLASSROOM_SIMULATION"}

    async def classroom_simulation(state: ClassroomGraphState) -> dict[str, Any]:
        result = await handlers["classroom_simulation"](state) if "classroom_simulation" in handlers else {}
        return {**result, "phase": "SUPERVISOR_REVIEW"}

    async def supervisor_review(state: ClassroomGraphState) -> dict[str, Any]:
        result = await handlers["supervisor_review"](state) if "supervisor_review" in handlers else {}
        return {**result, "phase": "LESSON_REVISION"}

    async def lesson_revision(state: ClassroomGraphState) -> dict[str, Any]:
        result = await handlers["lesson_revision"](state) if "lesson_revision" in handlers else {}
        return {**result, "phase": "NEXT_ROUND"}

    async def next_round(state: ClassroomGraphState) -> dict[str, Any]:
        current = int(state.get("round_number", 1))
        maximum = int(state.get("max_rounds", 1))
        if current >= maximum:
            return {"phase": "FINALIZE", "finalized": True}
        result = await handlers["next_round"](state) if "next_round" in handlers else {}
        return {**result, "round_number": current + 1, "phase": "CLASSROOM_SIMULATION"}

    async def finalize(state: ClassroomGraphState) -> dict[str, Any]:
        result = await handlers["finalize"](state) if "finalize" in handlers else {}
        return {**result, "phase": "FINALIZE", "finalized": True}

    def route_after_revision(state: ClassroomGraphState) -> str:
        return "finalize" if int(state.get("round_number", 1)) >= int(state.get("max_rounds", 1)) else "next_round"

    graph = StateGraph(ClassroomGraphState)
    graph.add_node("preparation", preparation)
    graph.add_node("classroom_simulation", classroom_simulation)
    graph.add_node("supervisor_review", supervisor_review)
    graph.add_node("lesson_revision", lesson_revision)
    graph.add_node("next_round", next_round)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "preparation")
    graph.add_edge("preparation", "classroom_simulation")
    graph.add_edge("classroom_simulation", "supervisor_review")
    graph.add_edge("supervisor_review", "lesson_revision")
    graph.add_conditional_edges("lesson_revision", route_after_revision, {"next_round": "next_round", "finalize": "finalize"})
    graph.add_edge("next_round", "classroom_simulation")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer) if checkpointer is not None else graph.compile()

