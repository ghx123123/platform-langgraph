from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.graph import END

from backend.classroom.actions import StudentAction, StudentActionType, TeacherAction, TeacherActionType
from backend.classroom.graph import build_classroom_graph
from backend.classroom.integration import ClassroomIntegrationService
from backend.classroom.models import ClassroomEventType, LessonSlide, LessonVersion, SimulationRound, StudentCognitiveState, StudentPersona
from backend.classroom.orchestrator import ClassroomOrchestrator
from backend.classroom.repository import ClassroomRepository
from backend.classroom.router import router as classroom_router
from backend.workflows.events import EventHub


def lesson():
    return LessonVersion(id="v1", lesson_id="lesson:run", run_id="run", version_number=1, title="Demo", learning_objectives=["goal"], knowledge_points=["kp"], estimated_minutes=1, slides=[LessonSlide(slide_id="slide_001", order=1, title="One", estimated_minutes=1, speaker_notes=[{"block_id": "slide_001:block_001", "order": 1, "block_type": "summary", "content": "Summary", "estimated_seconds": 5}])])


class Teacher:
    async def act(self, *args, **kwargs):
        return TeacherAction(action_type=TeacherActionType.SUMMARIZE, speech="Summary")


class Student:
    async def act(self, *args, **kwargs):
        return StudentAction(action_type=StudentActionType.SILENCE)


@pytest.mark.asyncio
async def test_snapshot_and_restore_use_state_plus_event_history(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    l = lesson()
    await repo.create_lesson_version(l)
    r = SimulationRound(id="r1", run_id="run", round_number=1, lesson_version_id=l.id, scenario_seed="seed")
    orch = ClassroomOrchestrator(repo, Teacher(), Student())
    await orch.start_round(l, r)
    persona = StudentPersona(run_id="run", student_id="student:low", name="Basic", level="low", ability=.4, engagement=.5, confidence=.4, verbosity=.4, question_propensity=.3, answer_propensity=.5, scenario_seed="seed")
    await repo.save_student_persona(persona)
    await repo.save_student_cognitive_state(StudentCognitiveState(round_id="r1", student_id="student:low", knowledge_point_id="kp", current_mastery=.45, current_confidence=.4))
    await orch.step("r1")
    integration = ClassroomIntegrationService(repo, EventHub())
    snapshot = await integration.get_snapshot("run", "r1")
    assert snapshot["state"]["round_id"] == "r1"
    assert snapshot["events"]
    assert snapshot["student_personas"][0]["run_id"] == "run"
    assert snapshot["student_cognitive_states"][0]["round_id"] == "r1"
    restored = ClassroomOrchestrator(repo, Teacher(), Student())
    state = await restored.restore_round(l, r)
    assert state.current_slide_index == snapshot["state"]["current_slide_index"]


@pytest.mark.asyncio
async def test_classroom_event_is_fanned_out_through_existing_event_hub(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    hub = EventHub()
    integration = ClassroomIntegrationService(repo, hub)
    queue = await hub.subscribe("run")
    from backend.classroom.models import ClassroomEvent
    event = ClassroomEvent(run_id="run", round_id="r", slide_id="s", actor_id="teacher", actor_role="teacher", event_type=ClassroomEventType.TEACHER_SUMMARY, content="done", sequence=1)
    await integration.publish_event(event)
    envelope = await queue.get()
    assert envelope.run_id == "run" and envelope.event_type == "classroom.event"
    assert envelope.payload["classroom_event"]["event_id"] == event.event_id


@pytest.mark.asyncio
async def test_integration_resume_restarts_the_background_round_runner(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    item = lesson()
    await repo.create_lesson_version(item)
    round_item = SimulationRound(id="r1", run_id="run", round_number=1, lesson_version_id=item.id, scenario_seed="seed")
    orchestrator = ClassroomOrchestrator(repo, Teacher(), Student())
    await orchestrator.start_round(item, round_item)
    integration = ClassroomIntegrationService(repo, EventHub())
    integration.bind_orchestrator("run", orchestrator)

    paused = await integration.control_round("run", "r1", "pause")
    assert paused.status == "paused"
    resumed = await integration.control_round("run", "r1", "resume")
    assert resumed.status == "active"
    assert "run" in integration._tasks
    await integration._tasks["run"]
    assert (await repo.get_classroom_state("r1")).status == "completed"


@pytest.mark.asyncio
async def test_intervention_api_persists_user_message_and_teacher_reply(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    item = lesson()
    await repo.create_lesson_version(item)
    round_item = SimulationRound(id="r1", run_id="run", round_number=1, lesson_version_id=item.id, scenario_seed="seed")
    orchestrator = ClassroomOrchestrator(repo, Teacher(), Student())
    await orchestrator.start_round(item, round_item)
    integration = ClassroomIntegrationService(repo, EventHub())
    integration.bind_orchestrator("run", orchestrator)
    api = FastAPI()
    api.state.classroom_service = integration
    api.include_router(classroom_router)

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post(
            "/api/classroom/runs/run/rounds/r1/interventions",
            json={"content": "请解释当前示例。"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["status"] == "paused"
    assert payload["user_event"]["actor_role"] == "user"
    assert payload["teacher_event"]["event_type"] == ClassroomEventType.TEACHER_ANSWER.value
    assert payload["teacher_event"]["reply_to"] == payload["user_event"]["event_id"]


@pytest.mark.asyncio
async def test_macro_graph_executes_exactly_n_rounds_then_finalize():
    calls = []
    async def simulate(state):
        calls.append(state["round_number"])
        return {}
    graph = build_classroom_graph(handlers={"classroom_simulation": simulate})
    result = await graph.ainvoke({"run_id": "run", "round_number": 1, "max_rounds": 3, "phase": "PREPARATION"})
    assert calls == [1, 2, 3]
    assert result["finalized"] is True and result["phase"] == "FINALIZE"


@pytest.mark.asyncio
async def test_intervention_service_persists_directive(tmp_path):
    """E3: 服务层介入把教师输入落成指令, 后续 prompt 可读取。"""
    from backend.classroom.models import TeacherDirective

    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    l = lesson()
    await repo.create_lesson_version(l)
    round_item = SimulationRound(id="r1", run_id="run", round_number=1, lesson_version_id=l.id, scenario_seed="s")
    await repo.create_simulation_round(round_item)

    directive = TeacherDirective(
        run_id="run", round_id="r1", slide_id="slide_001",
        source_event_id="evt-1", content="多举生活化例子", intent="require", scope="lesson",
    )
    await repo.save_teacher_directive(directive)

    stored = await repo.list_teacher_directives("run", status="active")
    assert [item.content for item in stored] == ["多举生活化例子"]
    assert stored[0].scope == "lesson"

    # 注入给 orchestrator 的上下文
    orch = ClassroomOrchestrator(repo, Teacher(), Student())
    runtime = type("R", (), {"active_directives": stored})()
    context = orch._directive_context(runtime)
    assert context["teacher_directives"][0]["content"] == "多举生活化例子"
    # 学生只接收「要求」类
    assert orch._directive_context(runtime, for_student=True)["teacher_directives"][0]["intent"] == "require"
