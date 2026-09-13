import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.classroom.models import (
    ClassroomAgentInstance,
    ClassroomEvent,
    ClassroomState,
    InteractionAnchor,
    ExpectedMisconception,
    LessonSlide,
    LessonVersion,
    RevisionPatch,
    SimulationRound,
    SpeakerNoteBlock,
    StudentCognitiveState,
    StudentPersona,
    StudentScenarioBaseline,
    SupervisorObservation,
    SupervisorReport,
)
from backend.classroom.repository import ClassroomRepository
from backend.workflows.repository import WorkflowRepository


def make_lesson(run_id: str = "run-1", version: int = 1) -> LessonVersion:
    slide = LessonSlide(
        id=f"slide-row-{run_id}-{version}",
        slide_id="slide-1",
        order=1,
        title="Operators",
        purpose="Build a correct mental model",
        learning_objectives=["recognize operators"],
        knowledge_points=["assignment", "comparison"],
        estimated_minutes=5,
        speaker_notes=[
            SpeakerNoteBlock(id=f"block-row-{run_id}-{version}", block_id="b1", order=1, content="Explain operators", estimated_seconds=40)
        ],
        interaction_anchors=[
            InteractionAnchor(id=f"anchor-row-{run_id}-{version}", interaction_id="i1", objective="check", planned_question="Which operator compares?", target_student_level="low")
        ],
        expected_misconceptions=[
            ExpectedMisconception(misconception_id="m1", description="mixes = and ==", correction_strategy="contrast examples")
        ],
    )
    return LessonVersion(
        id=f"v{version}-{run_id}",
        lesson_id="lesson-1",
        run_id=run_id,
        version_number=version,
        title="Python operators",
        learning_objectives=["recognize operators"],
        estimated_minutes=5,
        slides=[slide],
    )


@pytest.mark.asyncio
async def test_initialize_is_idempotent_and_creates_tables(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "classroom.db")
    await repo.initialize()
    await repo.initialize()

    with sqlite3.connect(repo.database_path) as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"classroom_runs", "lesson_versions", "classroom_events", "revision_patches"} <= names
        assert db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='005_classroom_v2.sql'").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_lesson_version_round_trip_with_nested_blueprint(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    lesson = make_lesson()
    await repo.create_lesson_version(lesson)

    loaded = await repo.get_lesson_version(lesson.id)
    assert loaded is not None
    assert loaded.slides[0].slide_id == "slide-1"
    assert loaded.slides[0].speaker_notes[0].block_id == "b1"
    assert loaded.slides[0].interaction_anchors[0].planned_question.startswith("Which")
    assert loaded.slides[0].expected_misconceptions[0].misconception_id == "m1"


@pytest.mark.asyncio
async def test_versions_are_scoped_to_run_and_ordered(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    await repo.create_lesson_version(make_lesson(version=1))
    await repo.create_lesson_version(make_lesson(version=2))
    await repo.create_lesson_version(make_lesson(run_id="run-2", version=1))

    assert [v.version_number for v in await repo.list_lesson_versions("run-1")] == [1, 2]


@pytest.mark.asyncio
async def test_concurrent_v1_writes_have_one_database_winner(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    first = make_lesson(run_id="same-run", version=1)
    second = make_lesson(run_id="same-run", version=1).model_copy(
        update={"id": "competing-v1"}
    )

    results = await asyncio.gather(
        repo.create_lesson_version_if_absent(first),
        repo.create_lesson_version_if_absent(second),
    )

    assert sorted(results) == [False, True]
    versions = await repo.list_lesson_versions("same-run")
    assert len(versions) == 1
    assert versions[0].version_number == 1


@pytest.mark.asyncio
async def test_round_state_and_monotonic_state_version(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    lesson = make_lesson()
    await repo.create_lesson_version(lesson)
    round_item = SimulationRound(run_id="run-1", round_number=1, lesson_version_id=lesson.id, scenario_seed="seed")
    await repo.create_simulation_round(round_item)

    state = ClassroomState(run_id="run-1", round_id=round_item.id, phase="slide_enter", version=2)
    await repo.save_classroom_state(state)
    with pytest.raises(ValueError):
        await repo.save_classroom_state(state.model_copy(update={"version": 1}))
    loaded = await repo.get_classroom_state(round_item.id)
    assert loaded is not None and loaded.version == 2


@pytest.mark.asyncio
async def test_event_sequence_is_global_unique_and_sorted(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    lesson = make_lesson()
    await repo.create_lesson_version(lesson)
    r1 = SimulationRound(run_id="run-1", round_number=1, lesson_version_id=lesson.id, scenario_seed="seed")
    r2 = SimulationRound(run_id="run-1", round_number=2, lesson_version_id=lesson.id, scenario_seed="seed")
    await repo.create_simulation_round(r1)
    await repo.create_simulation_round(r2)

    async def append(round_id: str, text: str) -> ClassroomEvent:
        return await repo.append_classroom_event(ClassroomEvent(run_id="run-1", round_id=round_id, actor_id="teacher", actor_role="teacher", event_type="teacher.explanation", content=text))

    events = await asyncio.gather(append(r1.id, "one"), append(r2.id, "two"), append(r1.id, "three"))
    assert sorted(e.sequence for e in events) == [1, 2, 3]
    listed = await repo.list_classroom_events("run-1")
    assert [e.sequence for e in listed] == [1, 2, 3]
    round_events = await repo.list_classroom_events("run-1", round_id=r1.id)
    assert len(round_events) == 2
    assert {e.sequence for e in round_events} <= {1, 2, 3}
    with pytest.raises(ValueError):
        await repo.append_classroom_event(ClassroomEvent(run_id="run-1", round_id=r1.id, sequence=5, actor_id="teacher", actor_role="teacher", event_type="teacher.explanation"))


@pytest.mark.asyncio
async def test_student_agent_supervisor_and_patch_round_trips(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    lesson = make_lesson()
    await repo.create_lesson_version(lesson)
    round_item = SimulationRound(run_id="run-1", round_number=1, lesson_version_id=lesson.id, scenario_seed="seed")
    await repo.create_simulation_round(round_item)

    persona = StudentPersona(run_id="run-1", student_id="s1", name="Student A", level="low", ability=.4, engagement=.5, confidence=.5, verbosity=.5, question_propensity=.2, answer_propensity=.7, scenario_seed="seed")
    baseline = StudentScenarioBaseline(run_id="run-1", student_id="s1", initial_mastery={"kp": .2}, initial_confidence={"kp": .3}, scenario_seed="seed")
    cognitive = StudentCognitiveState(round_id=round_item.id, student_id="s1", knowledge_point_id="kp", current_mastery=.5, current_confidence=.4)
    agent = ClassroomAgentInstance(run_id="run-1", agent_key="student:low", role="student", display_name="Student A", student_id="s1", persona_id=persona.id)
    await repo.save_student_persona(persona)
    await repo.save_student_scenario_baseline(baseline)
    await repo.save_student_cognitive_state(cognitive)
    await repo.save_agent_instance(agent)
    assert (await repo.get_student_persona("run-1", "s1")).name == "Student A"
    assert (await repo.get_student_scenario_baseline("run-1", "s1")).scenario_seed == "seed"
    assert (await repo.get_student_cognitive_state(round_item.id, "s1", "kp")).round_id == round_item.id
    assert (await repo.get_agent_instance("run-1", "student:low")).role == "student"

    observation = SupervisorObservation(round_id=round_item.id, slide_id="slide-1", event_ids=["evt-1"], category="misconception", issue="confusion", evidence="EVT-1", recommendation="contrast", analysis={"feedback_analysis": "teacher did not identify the wrong part"})
    await repo.save_supervisor_observation(observation)
    saved_observation = (await repo.list_supervisor_observations(round_item.id))[0]
    assert saved_observation.event_ids == ["evt-1"]
    assert saved_observation.analysis["feedback_analysis"].startswith("teacher")
    report = SupervisorReport(run_id="run-1", round_id=round_item.id, overall_score=80, observations=[observation.observation_id])
    await repo.save_supervisor_report(report)
    assert (await repo.get_supervisor_report(round_item.id)).overall_score == 80
    patch = RevisionPatch(run_id="run-1", source_version_id=lesson.id, source_round_id=round_item.id, target_type="speaker_note", slide_id="slide-1", block_id="b1", field_path="content", before="old", after="new", reason="evidence", source_observation_ids=[observation.observation_id])
    await repo.save_revision_patch(patch)
    assert (await repo.list_revision_patches("run-1"))[0].source_observation_ids == [observation.observation_id]


@pytest.mark.asyncio
async def test_existing_workflow_database_remains_readable(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    # Build a database at the last legacy migration (001-004), then apply the
    # classroom migration on top of it.  This mirrors an in-place upgrade.
    migration_dir = Path(__file__).resolve().parents[1] / "backend" / "migrations"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for name in ("001_workflows.sql", "002_teaching_data.sql", "003_human_in_the_loop.sql", "004_teacher_drafts.sql"):
            db.executescript((migration_dir / name).read_text(encoding="utf-8"))
            db.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (name, "2026-01-01T00:00:00+00:00"))
        db.execute("INSERT INTO workflow_runs (id, thread_id, template_id, objective, status, provider, created_at, updated_at) VALUES ('legacy-1', 'thread', 'template', 'objective', 'completed', 'local', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')")
        db.commit()

    workflow_repo = WorkflowRepository(db_path)
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT id FROM workflow_runs WHERE id='legacy-1'").fetchone() is not None

    classroom_repo = ClassroomRepository(db_path)
    await classroom_repo.initialize()
    assert (await workflow_repo.get_run("legacy-1")).id == "legacy-1"
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT workflow_version FROM classroom_runs WHERE run_id='legacy-1'").fetchone() is None


@pytest.mark.asyncio
async def test_teacher_directive_lifecycle(tmp_path: Path) -> None:
    """E3-1: 指令可创建、按 round/status 查询、按 scope 落实。"""
    from backend.classroom.models import TeacherDirective

    repository = ClassroomRepository(tmp_path / "directives.db")
    await repository.initialize()
    directive = TeacherDirective(
        run_id="run-1", round_id="round-1", slide_id="slide_001",
        source_event_id="evt-1", content="这个例子太难，换成生活化的",
        intent="correct", scope="slide",
    )
    await repository.save_teacher_directive(directive)

    loaded = await repository.get_teacher_directive(directive.directive_id)
    assert loaded is not None
    assert loaded.intent == "correct"
    assert loaded.scope == "slide"
    assert loaded.status == "active"

    active = await repository.list_teacher_directives("run-1", round_id="round-1", status="active")
    assert [item.directive_id for item in active] == [directive.directive_id]

    resolved = await repository.resolve_teacher_directives("run-1", round_id="round-1", scope="slide")
    assert resolved == 1
    assert await repository.list_teacher_directives("run-1", status="active") == []
    reloaded = await repository.get_teacher_directive(directive.directive_id)
    assert reloaded.status == "resolved"
    assert reloaded.resolved_at is not None


@pytest.mark.asyncio
async def test_revision_patch_keeps_intervention_provenance(tmp_path: Path) -> None:
    """E3-5: 补丁要能溯源到教师指令。"""
    from backend.classroom.models import RevisionPatch

    repository = ClassroomRepository(tmp_path / "patches.db")
    await repository.initialize()
    lesson = make_lesson(run_id="run-1", version=1)
    await repository.create_lesson_version(lesson)
    patch = RevisionPatch(
        run_id="run-1", source_version_id=lesson.id, source_round_id=None,
        target_type="slide", slide_id="slide_001", field_path="ppt_content.bullets",
        before=["旧例子"], after=["生活化例子"], reason="教师纠正",
        source_intervention_ids=["dir-1"], status="applied",
    )
    await repository.save_revision_patch(patch)

    loaded = (await repository.list_revision_patches("run-1"))[0]
    assert loaded.source_intervention_ids == ["dir-1"]
    assert loaded.status == "applied"
