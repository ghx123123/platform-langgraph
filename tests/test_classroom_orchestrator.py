from pathlib import Path
import pytest

from backend.classroom.actions import StudentAction, StudentActionType, TeacherAction, TeacherActionType, FeedbackEvaluation
from backend.classroom.models import ClassroomEventType, InteractionAnchor, LessonSlide, LessonVersion, SimulationRound, StudentPersona
from backend.classroom.orchestrator import ClassroomOrchestrator
from backend.classroom.repository import ClassroomRepository


def lesson() -> LessonVersion:
    return LessonVersion(
        id="v1", lesson_id="lesson", run_id="run-a", version_number=1, title="Demo",
        learning_objectives=["goal"], knowledge_points=["kp"], estimated_minutes=1,
        slides=[LessonSlide(slide_id="slide_001", order=1, title="One", estimated_minutes=1, speaker_notes=[
            {"block_id": "slide_001:block_001", "order": 1, "block_type": "explanation", "content": "Explain", "estimated_seconds": 10},
            {"block_id": "slide_001:block_002", "order": 2, "block_type": "summary", "content": "Summary", "estimated_seconds": 10},
        ])],
    )


class FakeTeacher:
    def __init__(self):
        self.actions = [
            TeacherAction(action_type=TeacherActionType.EXPLAIN, speech="Explain"),
            TeacherAction(action_type=TeacherActionType.ASK_QUESTION, speech="What?"),
            TeacherAction(action_type=TeacherActionType.FOLLOW_UP, speech="Why?"),
            TeacherAction(action_type=TeacherActionType.FEEDBACK, speech="Corrected", feedback_evaluation=FeedbackEvaluation(quality="PARTIAL")),
            TeacherAction(action_type=TeacherActionType.SUMMARIZE, speech="Summary"),
        ]
        self.calls = 0

    async def act(self, *args, **kwargs):
        result = self.actions[min(self.calls, len(self.actions) - 1)]
        self.calls += 1
        return result


class RecordingTeacher(FakeTeacher):
    """记录每次调用收到的 prompt_context, 用于验证约束继承。"""

    def __init__(self):
        super().__init__()
        self.contexts: list[dict] = []

    async def act(self, *args, **kwargs):
        self.contexts.append(dict(kwargs.get("prompt_context") or {}))
        return await super().act(*args, **kwargs)


class FakeStudent:
    def __init__(self, action=None):
        self.action = action or StudentAction(action_type=StudentActionType.ANSWER, content="partial", confidence=.3)
        self.calls = 0

    async def act(self, *args, **kwargs):
        self.calls += 1
        return self.action


def persona(run_id="run-a"):
    return StudentPersona(run_id=run_id, student_id="s-low", name="Basic", level="low", ability=.3, engagement=.5, confidence=.4, verbosity=.4, question_propensity=.2, answer_propensity=.8, scenario_seed="seed")


@pytest.mark.asyncio
@pytest.mark.parametrize('asks', [True, False])
async def test_student_listening_decision_continues_same_slide(tmp_path, asks):
    class ListeningStudent(FakeStudent):
        async def listen(self, *args, **kwargs):
            assert args[4] == 'Explain'
            return StudentAction(action_type=StudentActionType.QUESTION if asks else StudentActionType.SILENCE,
                                 content='Why?' if asks else '', confidence=.3)

    class Teacher:
        async def act(self, *args, **kwargs):
            block = args[3]
            if block:
                return TeacherAction(action_type=TeacherActionType.EXPLAIN if block.block_type == 'explanation' else TeacherActionType.SUMMARIZE, speech=block.content)
            return TeacherAction(action_type=TeacherActionType.ANSWER_STUDENT, speech='Because...')

    repo = ClassroomRepository(tmp_path / 'listen.db')
    await repo.initialize()
    item = lesson()
    await repo.create_lesson_version(item)
    orchestrator = ClassroomOrchestrator(repo, Teacher(), ListeningStudent(), personas=[persona()])
    round_item = SimulationRound(id='listen-round', run_id='run-a', round_number=1, lesson_version_id=item.id, scenario_seed='seed')
    await orchestrator.start_round(item, round_item)
    await orchestrator.run_round(round_item.id)
    events = await repo.list_classroom_events('run-a', round_item.id)
    questions = [e for e in events if e.event_type == ClassroomEventType.STUDENT_QUESTION]
    assert len(questions) == int(asks)
    assert not any(e.event_type == ClassroomEventType.STUDENT_SILENCE for e in events)
    assert any(e.content == 'Summary' for e in events)
    if asks:
        answer = next(e for e in events if e.event_type == ClassroomEventType.TEACHER_ANSWER)
        assert answer.reply_to == questions[0].event_id
        assert answer.slide_id == questions[0].slide_id
    state = await repo.get_classroom_state(round_item.id)
    assert state.status == 'completed'
    assert state.student_question_count == int(asks)


@pytest.mark.asyncio
async def test_planned_anchor_creates_real_teacher_student_feedback_chain(tmp_path: Path):
    class AnchorTeacher:
        async def act(self, *args, **kwargs):
            block = args[3]
            mode = (kwargs.get("prompt_context") or {}).get("mode")
            if mode == "planned_interaction":
                return TeacherAction(action_type=TeacherActionType.ASK_QUESTION, speech="请说出这个概念的关键条件。")
            if mode == "respond_to_student":
                return TeacherAction(
                    action_type=TeacherActionType.FEEDBACK,
                    speech="条件已经找对了，再注意适用范围。",
                    feedback_evaluation=FeedbackEvaluation(quality="PARTIAL"),
                )
            return TeacherAction(
                action_type=TeacherActionType.SUMMARIZE if block.block_type == "summary" else TeacherActionType.EXPLAIN,
                speech=block.content,
            )

    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    anchored_lesson = lesson()
    anchored_lesson.slides[0].interaction_anchors = [
        InteractionAnchor(
            interaction_id="slide_001:interaction_001",
            type="check",
            objective="检查关键条件",
            planned_question="这个概念成立的关键条件是什么？",
            target_student_level="low",
            after_block_id="slide_001:block_001",
            knowledge_point_ids=["kp"],
            priority=1,
        )
    ]
    await repo.create_lesson_version(anchored_lesson)
    orchestrator = ClassroomOrchestrator(
        repo,
        AnchorTeacher(),
        FakeStudent(StudentAction(action_type=StudentActionType.ANSWER, content="我觉得要满足这个条件。", confidence=.4)),
        personas=[persona()],
    )
    round_item = SimulationRound(
        id="r-anchor",
        run_id="run-a",
        round_number=1,
        lesson_version_id="v1",
        scenario_seed="seed",
    )
    await orchestrator.start_round(anchored_lesson, round_item)
    await orchestrator.run_round(round_item.id)

    events = await repo.list_classroom_events("run-a", round_item.id)
    teaching_events = [
        event.event_type
        for event in events
        if event.actor_role in {"teacher", "student"}
    ]
    assert teaching_events == [
        ClassroomEventType.TEACHER_EXPLANATION,
        ClassroomEventType.TEACHER_QUESTION,
        ClassroomEventType.STUDENT_ANSWER,
        ClassroomEventType.TEACHER_FEEDBACK,
        ClassroomEventType.TEACHER_SUMMARY,
    ]
    question = next(event for event in events if event.event_type == ClassroomEventType.TEACHER_QUESTION)
    answer = next(event for event in events if event.event_type == ClassroomEventType.STUDENT_ANSWER)
    feedback = next(event for event in events if event.event_type == ClassroomEventType.TEACHER_FEEDBACK)
    assert question.metadata["interaction_id"] == "slide_001:interaction_001"
    assert answer.reply_to == question.event_id
    assert feedback.reply_to == answer.event_id


@pytest.mark.asyncio
async def test_round_executes_stepwise_and_persists_events(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    teacher, student = FakeTeacher(), FakeStudent()
    orch = ClassroomOrchestrator(repo, teacher, student, personas=[persona()])
    r = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), r)
    state = await orch.run_round("r1")
    assert state.status == "completed"
    events = await repo.list_classroom_events("run-a", "r1")
    stored_personas = await repo.list_student_personas("run-a")
    assert [item.student_id for item in stored_personas] == ["s-low"]
    assert any(e.event_type == ClassroomEventType.TEACHER_QUESTION for e in events)
    assert any(e.event_type == ClassroomEventType.STUDENT_ANSWER for e in events)
    assert events[-1].event_type == ClassroomEventType.ROUND_COMPLETED
    assert events[-1].virtual_timestamp > 0


@pytest.mark.asyncio
async def test_pause_resume_stop_are_cooperative(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    orch = ClassroomOrchestrator(repo, FakeTeacher(), FakeStudent(), personas=[persona()])
    r = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), r); await orch.step("r1")
    paused = await orch.pause("r1"); assert paused.status == "paused"
    count = len(await repo.list_classroom_events("run-a", "r1")); await orch.step("r1"); assert len(await repo.list_classroom_events("run-a", "r1")) == count
    await orch.resume("r1"); assert (await orch.step("r1")).status == "active"
    assert (await orch.stop("r1")).status == "stopped"


@pytest.mark.asyncio
async def test_user_intervention_is_persisted_and_teacher_reply_is_linked(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    orch = ClassroomOrchestrator(repo, FakeTeacher(), FakeStudent(), personas=[persona()])
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), round_item)
    await orch.step("r1")
    await orch.pause("r1")

    user_event, teacher_event, state, directive = await orch.intervene("r1", "请换一个更贴近生活的例子。")

    assert state.status == "paused"
    assert user_event.event_type == ClassroomEventType.USER_INTERVENTION
    assert user_event.actor_role == "user"
    assert user_event.target_agent_id == "teacher"
    assert teacher_event.event_type == ClassroomEventType.TEACHER_ANSWER
    assert teacher_event.reply_to == user_event.event_id
    # question 意图不注册指令(不产生约束)
    assert directive is None
    events = await repo.list_classroom_events("run-a", "r1")
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))

    resumed = await orch.resume("r1")
    assert resumed.status == "active"
    assert resumed.phase == "teacher_act"


@pytest.mark.asyncio
async def test_student_failure_degrades_to_silence_without_losing_events(tmp_path: Path):
    class FailingStudent:
        async def act(self, *args, **kwargs): raise ValueError("invalid JSON")
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    orch = ClassroomOrchestrator(repo, FakeTeacher(), FailingStudent(), personas=[persona()])
    r = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), r)
    for _ in range(4): await orch.step("r1")
    events = await repo.list_classroom_events("run-a", "r1")
    assert any(e.event_type == ClassroomEventType.AGENT_ERROR or e.event_type == ClassroomEventType.STUDENT_SILENCE for e in events)


@pytest.mark.asyncio
async def test_two_runs_are_isolated(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    lesson_a = lesson(); lesson_b = lesson().model_copy(update={"id": "v2", "run_id": "run-b"})
    await repo.create_lesson_version(lesson_a); await repo.create_lesson_version(lesson_b)
    orch = ClassroomOrchestrator(repo, FakeTeacher(), FakeStudent(), personas=[persona("run-a")])
    await orch.start_round(lesson_a, SimulationRound(id="ra", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed-a"))
    await orch.start_round(lesson_b, SimulationRound(id="rb", run_id="run-b", round_number=1, lesson_version_id="v2", scenario_seed="seed-b"), personas=[persona("run-b").model_copy(update={"student_id": "s-b"})])
    await orch.step("ra"); await orch.step("rb")
    assert all(e.run_id == "run-a" for e in await repo.list_classroom_events("run-a"))
    assert all(e.run_id == "run-b" for e in await repo.list_classroom_events("run-b"))


@pytest.mark.asyncio
async def test_require_intervention_registers_directive_and_injects_it(tmp_path: Path) -> None:
    """E3-3: 要求类介入要注册为生效指令, 并注入后续 teacher/student 的 prompt。"""
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    teacher = RecordingTeacher()
    orch = ClassroomOrchestrator(repo, teacher, FakeStudent(), personas=[persona()])
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), round_item)
    await orch.step("r1")
    await orch.pause("r1")

    _, _, _, directive = await orch.intervene(
        "r1", "每个知识点都要举一个生活化的例子", intent="require", scope="round"
    )
    assert directive is not None
    assert directive.intent == "require"
    assert directive.status == "active"
    stored = await repo.list_teacher_directives("run-a", status="active")
    assert [item.directive_id for item in stored] == [directive.directive_id]

    teacher.contexts.clear()
    await orch.resume("r1")
    await orch.step("r1")
    assert teacher.contexts, "teacher 应该被再次调用"
    directives = teacher.contexts[-1].get("teacher_directives")
    assert directives and directives[0]["content"] == "每个知识点都要举一个生活化的例子"


@pytest.mark.asyncio
async def test_slide_scoped_directive_resolves_when_leaving_slide(tmp_path: Path) -> None:
    """E3-3: 本页范围的指令在离开该页后自动落实。"""
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    orch = ClassroomOrchestrator(repo, RecordingTeacher(), FakeStudent(), personas=[persona()])
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), round_item)
    await orch.step("r1")
    await orch.pause("r1")
    _, _, _, directive = await orch.intervene("r1", "这页少讲点", intent="require", scope="slide")
    assert directive is not None

    await orch.resume("r1")
    for _ in range(40):
        state = await orch.step("r1")
        if state.status in {"completed", "stopped", "failed"}:
            break
    stored = await repo.get_teacher_directive(directive.directive_id)
    assert stored.status == "resolved"


@pytest.mark.asyncio
async def test_pause_after_student_question_gate(tmp_path: Path) -> None:
    """E3-8: 开启「学生提问后暂停」时, 学生提问后课堂必须停住等教师。"""
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    question = StudentAction(action_type=StudentActionType.QUESTION, content="老师，这里没听懂", confidence=.3)
    orch = ClassroomOrchestrator(
        repo, RecordingTeacher(), FakeStudent(action=question), personas=[persona()],
        pause_after_student_question=True,
    )
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), round_item)

    paused = False
    for _ in range(40):
        state = await orch.step("r1")
        if state.status == "paused":
            paused = True
            break
    assert paused, "学生提问后应暂停"
    events = await repo.list_classroom_events("run-a", "r1")
    assert any(e.event_type == ClassroomEventType.STUDENT_QUESTION for e in events)
    assert any("等待你的介入" in e.content for e in events)

    # 教师介入后继续
    _, _, _, directive = await orch.intervene("r1", "换个说法再讲一次", intent="require", scope="slide")
    assert directive is not None
    resumed = await orch.resume("r1")
    assert resumed.status == "active"


@pytest.mark.asyncio
async def test_pause_after_student_question_disabled_by_default(tmp_path: Path) -> None:
    """未勾选时行为与现在一致: 学生提问后直接进入教师回应。"""
    repo = ClassroomRepository(tmp_path / "db.sqlite"); await repo.initialize()
    await repo.create_lesson_version(lesson())
    question = StudentAction(action_type=StudentActionType.QUESTION, content="老师，这里没听懂", confidence=.3)
    orch = ClassroomOrchestrator(repo, RecordingTeacher(), FakeStudent(action=question), personas=[persona()])
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id="v1", scenario_seed="seed")
    await orch.start_round(lesson(), round_item)

    for _ in range(40):
        state = await orch.step("r1")
        if state.status in {"completed", "stopped", "failed"}:
            break
        assert state.status != "paused", "未开启设置时不应因学生提问暂停"
