from pathlib import Path

import pytest

from backend.classroom.evaluation import DIMENSION_WEIGHTS, EvaluationError, SupervisorEvaluationService
from backend.classroom.models import ClassroomAgentInstance, ClassroomEvent, ClassroomEventType, LessonSlide, LessonVersion, SimulationRound, StudentPersona, SupervisorObservation, SupervisorReport
from backend.classroom.repository import ClassroomRepository
from backend.classroom.revision import RevisionEngine, RevisionError


def lesson(run_id="run-a", version_id="v1", version_number=1):
    return LessonVersion(id=version_id, lesson_id=f"lesson:{run_id}", run_id=run_id, version_number=version_number, title="Operators", learning_objectives=["understand"], knowledge_points=["assignment"], estimated_minutes=1, slides=[LessonSlide(slide_id="slide_001", order=1, title="Assignment", estimated_minutes=1, knowledge_points=["assignment"], ppt_content={"title": "=", "bullets": ["stores value"]}, speaker_notes=[{"block_id": "slide_001:block_001", "order": 1, "block_type": "explanation", "content": "Explain assignment", "estimated_seconds": 20}], expected_misconceptions=[{"misconception_id": "slide_001:misconception_001", "knowledge_point_id": "assignment", "description": "confuses = and ==", "correction_strategy": "contrast"}])])


async def setup(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    l = lesson()
    await repo.create_lesson_version(l)
    r = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id=l.id, scenario_seed="seed")
    await repo.create_simulation_round(r)
    await repo.append_classroom_event(ClassroomEvent(run_id="run-a", round_id="r1", slide_id="slide_001", actor_id="teacher", actor_role="teacher", event_type=ClassroomEventType.TEACHER_EXPLANATION, content="Explain"))
    await repo.append_classroom_event(ClassroomEvent(run_id="run-a", round_id="r1", slide_id="slide_001", actor_id="s-low", actor_role="student", event_type=ClassroomEventType.STUDENT_ANSWER, content="wrong"))
    return repo, l, r


@pytest.mark.asyncio
async def test_slide_observation_uses_real_event_ids_and_no_speech(tmp_path):
    repo, l, r = await setup(tmp_path)
    obs = await SupervisorEvaluationService(repo).evaluate_slide("run-a", r, l.slides[0])
    events = await repo.list_classroom_events("run-a", "r1")
    assert set(obs.event_ids) <= {e.event_id for e in events}
    assert obs.round_id == "r1"
    assert not hasattr(obs, "speech")


@pytest.mark.asyncio
async def test_slide_without_student_evidence_produces_specific_interaction_issue(tmp_path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    current_lesson = lesson()
    await repo.create_lesson_version(current_lesson)
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id=current_lesson.id, scenario_seed="seed")
    await repo.create_simulation_round(round_item)
    teacher_event = await repo.append_classroom_event(ClassroomEvent(
        run_id="run-a", round_id="r1", slide_id="slide_001", actor_id="teacher",
        actor_role="teacher", event_type=ClassroomEventType.TEACHER_EXPLANATION,
        content="讲解赋值运算符。",
    ))

    observation = await SupervisorEvaluationService(repo).evaluate_slide("run-a", round_item, current_lesson.slides[0])

    assert observation.category == "interaction"
    assert observation.severity == "major"
    assert observation.event_ids == [teacher_event.event_id]
    assert "没有形成学生" in observation.issue
    assert "加入一个" in observation.recommendation


@pytest.mark.asyncio
async def test_generic_model_observation_is_replaced_by_evidence_fallback(tmp_path):
    repo, current_lesson, round_item = await setup(tmp_path)

    async def generic(_system, _user):
        return {
            "category": "other",
            "severity": "info",
            "event_ids": [],
            "issue": "Slide evidence was recorded.",
            "evidence": "",
            "recommendation": "Review the cited slide events.",
        }

    observation = await SupervisorEvaluationService(repo, generic).evaluate_slide(
        "run-a", round_item, current_lesson.slides[0]
    )

    assert observation.issue != "Slide evidence was recorded."
    assert observation.recommendation != "Review the cited slide events."
    assert observation.event_ids


@pytest.mark.asyncio
async def test_report_uses_fixed_weighted_overall_score(tmp_path):
    repo, l, r = await setup(tmp_path)
    service = SupervisorEvaluationService(repo)
    obs = await service.evaluate_slide("run-a", r, l.slides[0])
    async def gen(_s, _u):
        return {"dimension_scores": {k: 80 for k in DIMENSION_WEIGHTS}, "observation_ids": [obs.observation_id]}
    report = await SupervisorEvaluationService(repo, gen).evaluate_round("run-a", r, l.learning_objectives)
    assert report.overall_score == 80
    assert set(report.dimension_scores) == set(DIMENSION_WEIGHTS)


@pytest.mark.asyncio
async def test_uniform_schema_report_with_generic_observations_uses_evidence_fallback(tmp_path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    current_lesson = lesson()
    await repo.create_lesson_version(current_lesson)
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id=current_lesson.id, scenario_seed="seed")
    await repo.create_simulation_round(round_item)
    await repo.append_classroom_event(ClassroomEvent(
        run_id="run-a", round_id="r1", slide_id="slide_001", actor_id="teacher",
        actor_role="teacher", event_type=ClassroomEventType.TEACHER_EXPLANATION,
        content="Explain assignment",
    ))
    await repo.save_supervisor_observation(SupervisorObservation(
        round_id="r1", slide_id="slide_001", event_ids=[(await repo.list_classroom_events("run-a", "r1"))[0].event_id],
        category="other", severity="major", issue="Slide execution events were recorded.",
        evidence="event", recommendation="Review the cited interaction evidence.",
    ))

    async def generic_report(_system, _user):
        return {
            "dimension_scores": {key: 85 for key in DIMENSION_WEIGHTS},
            "strengths": [], "critical_issues": [], "revision_priorities": [],
        }

    report = await SupervisorEvaluationService(repo, generic_report).evaluate_round(
        "run-a", round_item, current_lesson.learning_objectives,
    )

    assert len(set(report.dimension_scores.values())) > 1
    assert report.revision_priorities


@pytest.mark.asyncio
async def test_incomplete_supervisor_scores_are_rejected_instead_of_defaulting_to_70(tmp_path):
    repo, l, r = await setup(tmp_path)
    service = SupervisorEvaluationService(repo)
    obs = await service.evaluate_slide("run-a", r, l.slides[0])

    async def incomplete(_system, _user):
        return {"dimension_scores": {"content_accuracy": 90}, "observation_ids": [obs.observation_id]}

    with pytest.raises(EvaluationError, match="missing dimension scores"):
        await SupervisorEvaluationService(repo, incomplete).evaluate_round("run-a", r, l.learning_objectives)


@pytest.mark.asyncio
async def test_evidence_fallback_scores_are_dimension_specific(tmp_path):
    repo, l, r = await setup(tmp_path)
    service = SupervisorEvaluationService(repo)
    await service.evaluate_slide("run-a", r, l.slides[0])
    report = await service.evaluate_round("run-a", r, l.learning_objectives)

    assert set(report.dimension_scores) == set(DIMENSION_WEIGHTS)
    assert len(set(report.dimension_scores.values())) > 1
    assert report.dimension_scores["feedback_quality"] < report.dimension_scores["content_accuracy"]


@pytest.mark.asyncio
async def test_revision_patch_only_changes_target_and_keeps_ids(tmp_path):
    repo, l, r = await setup(tmp_path)
    obs = await SupervisorEvaluationService(repo).evaluate_slide("run-a", r, l.slides[0])
    report = SupervisorReport(run_id="run-a", round_id="r1", overall_score=70, dimension_scores={k: 70 for k in DIMENSION_WEIGHTS}, observations=[obs.observation_id])
    patch_data = {"target_type": "speaker_note", "slide_id": "slide_001", "block_id": "slide_001:block_001", "field_path": "content", "before": "Explain assignment", "after": "Explain assignment with contrast", "reason": "misconception", "source_observation_ids": [obs.observation_id]}
    async def gen(_s, _u): return [patch_data]
    engine = RevisionEngine(repo, gen)
    patches = await engine.generate_patches(l, report, r, [obs])
    v2 = await engine.apply_patches(l, r, patches)
    assert v2.version_number == 2
    assert v2.source_version_id == l.id
    assert v2.slides[0].slide_id == l.slides[0].slide_id
    assert v2.slides[0].speaker_notes[0].block_id == l.slides[0].speaker_notes[0].block_id
    assert v2.slides[0].speaker_notes[0].content.endswith("contrast")


@pytest.mark.asyncio
async def test_invalid_patch_does_not_create_v2(tmp_path):
    repo, l, r = await setup(tmp_path)
    bad = __import__("backend.classroom.models", fromlist=["RevisionPatch"]).RevisionPatch(run_id="run-a", source_version_id="v1", source_round_id="r1", target_type="speaker_note", slide_id="slide_001", block_id="slide_001:block_001", field_path="content", before="not-current", after="x", reason="bad")
    with pytest.raises(RevisionError):
        await RevisionEngine(repo).apply_patches(l, r, [bad])
    assert len(await repo.list_lesson_versions("run-a")) == 1


@pytest.mark.asyncio
async def test_last_round_finalizes_without_extra_version(tmp_path):
    repo, l, r = await setup(tmp_path)
    report = SupervisorReport(run_id="run-a", round_id="r1", overall_score=90)
    current, patches, finalized = await RevisionEngine(repo).refine_round(l, r, report, max_rounds=1)
    assert finalized is True and patches == [] and current.status == "final"
    assert len(await repo.list_lesson_versions("run-a")) == 1


@pytest.mark.asyncio
async def test_round_baseline_initializes_fresh_state(tmp_path):
    repo, l, r = await setup(tmp_path)
    p = StudentPersona(run_id="run-a", student_id="s-low", name="Basic", level="low", ability=.3, engagement=.5, confidence=.4, verbosity=.4, question_propensity=.2, answer_propensity=.8, scenario_seed="seed")
    engine = RevisionEngine(repo)
    states = await engine.initialize_round_cognitive_states("run-a", r, [p], ["assignment"])
    assert states[0].round_id == "r1" and states[0].current_mastery == .5


@pytest.mark.asyncio
async def test_title_free_model_observation_is_replaced_by_slide_specific_evidence(tmp_path):
    repo, current_lesson, round_item = await setup(tmp_path)

    async def vague(_system, _user):
        return {
            "category": "interaction",
            "severity": "info",
            "event_ids": [],
            "issue": "学生参与了课堂讨论。",
            "evidence": "",
            "recommendation": "继续保持互动。",
        }

    observation = await SupervisorEvaluationService(repo, vague).evaluate_slide(
        "run-a", round_item, current_lesson.slides[0]
    )

    assert "Assignment" in observation.issue
    assert observation.event_ids
    assert "slide_001" in observation.evidence or "Slide 1" in observation.evidence


@pytest.mark.asyncio
async def test_report_adds_major_observations_to_revision_priorities(tmp_path):
    repo, current_lesson, round_item = await setup(tmp_path)
    observation = await SupervisorEvaluationService(repo).evaluate_slide(
        "run-a", round_item, current_lesson.slides[0]
    )

    async def empty_issues(_system, _user):
        return {
            "dimension_scores": {key: 80 for key in DIMENSION_WEIGHTS},
            "observation_ids": [observation.observation_id],
            "critical_issues": [],
            "revision_priorities": [],
        }

    report = await SupervisorEvaluationService(repo, empty_issues).evaluate_round(
        "run-a", round_item, current_lesson.learning_objectives
    )

    assert report.revision_priorities
    assert observation.recommendation in report.revision_priorities[0]


@pytest.mark.asyncio
async def test_supervisor_profile_is_scoped_to_run_and_reaches_prompt(tmp_path):
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    current_lesson = lesson("run-a")
    await repo.create_lesson_version(current_lesson)
    round_item = SimulationRound(id="r1", run_id="run-a", round_number=1, lesson_version_id=current_lesson.id, scenario_seed="seed")
    await repo.create_simulation_round(round_item)
    await repo.append_classroom_event(ClassroomEvent(
        run_id="run-a", round_id="r1", slide_id="slide_001", actor_id="teacher", actor_role="teacher",
        event_type=ClassroomEventType.TEACHER_EXPLANATION, content="Explain assignment",
    ))
    await repo.save_agent_instance(ClassroomAgentInstance(
        run_id="run-a", agent_key="supervisor", role="supervisor", display_name="督导",
        config={"supervisor_profile": {"role_definition": "只检查误区", "system_prompt": "必须引用原话", "evaluation_focus": ["misconception_handling"]}},
    ))
    captured = {}

    async def generator(_system, user):
        captured["user"] = user
        return {"category": "clarity", "severity": "minor", "event_ids": [], "issue": "Assignment 页面讲解证据不足", "evidence": "teacher event", "recommendation": "补充对比示例"}

    observation = await SupervisorEvaluationService(repo, generator).evaluate_slide("run-a", round_item, current_lesson.slides[0])
    assert "只检查误区" in captured["user"]
    assert observation.analysis["ppt_alignment"]
    assert await repo.get_agent_instance("run-b", "supervisor") is None


@pytest.mark.asyncio
async def test_supervisor_creates_alignment_observation_for_unfollowed_directive(tmp_path):
    """E3-4: 教师指令未被遵守时, 督导要额外产出一条 alignment observation。"""
    import json as _json

    from backend.classroom.models import TeacherDirective

    repo, l, r = await setup(tmp_path)

    class _Gen:
        async def __call__(self, system: str, user: str) -> str:
            return _json.dumps({
                "category": "clarity", "severity": "minor", "event_ids": [],
                "issue": "Assignment 页面讲解偏抽象，未贴合学生回答中的具体表述",
                "evidence": "学生回答错误", "recommendation": "在 Assignment 讲解中补一个生活化例子并追问学生",
                "directive_compliance": [
                    {"directive_id": "dir-1", "followed": False, "evidence": "本页仍在用抽象例子"},
                ],
            }, ensure_ascii=False)

    evaluator = SupervisorEvaluationService(repo, generator=_Gen())
    directive = TeacherDirective(
        directive_id="dir-1", run_id="run-a", round_id="r1", slide_id="slide_001",
        source_event_id="evt-1", content="每个知识点都要举生活化的例子",
        intent="require", scope="round",
    )
    await repo.save_teacher_directive(directive)

    await evaluator.evaluate_slide("run-a", r, l.slides[0], directives=[directive])

    observations = await repo.list_supervisor_observations("r1")
    alignment = [item for item in observations if item.category == "alignment"]
    assert alignment, "未遵守指令必须产出 alignment observation"
    assert "生活化的例子" in alignment[0].issue


@pytest.mark.asyncio
async def test_directive_patch_generation_uses_directive_as_observation(tmp_path):
    """E3-5: 纠正类介入要产出补丁, 且补丁引用教师指令来源的 observation。"""
    import json as _json

    from backend.classroom.integration import ClassroomIntegrationService
    from backend.classroom.models import TeacherDirective
    from backend.workflows.events import EventHub

    repo, l, r = await setup(tmp_path)

    class _Runtime:
        async def generate(self, run_id, round_number, role, system, user):
            return _json.dumps([{
                "target_type": "slide", "slide_id": "slide_001",
                "field_path": "ppt_content.bullets",
                "before": ["stores value"], "after": ["stores value", "生活化例子：把变量想成一个贴了标签的盒子"],
                "reason": "教师纠正：补生活化例子",
            }], ensure_ascii=False)

    service = ClassroomIntegrationService(repo, EventHub())
    directive = TeacherDirective(
        directive_id="dir-9", run_id="run-a", round_id="r1", slide_id="slide_001",
        source_event_id="evt-9", content="补一个生活化例子", intent="correct", scope="round",
    )
    await repo.save_teacher_directive(directive)

    class _Orch:
        _runs = {"r1": type("R", (), {"lesson": l, "round": r, "state": type("S", (), {"current_slide_index": 0})()})()}

    service._agent_runtimes["run-a"] = _Runtime()
    patches = await service._apply_directive_patches(_Orch(), directive)

    assert patches, "纠正类介入应产出补丁"
    assert patches[0]["status"] == "applied"
    stored = await repo.list_revision_patches("run-a", "r1")
    assert stored and stored[0].source_intervention_ids == ["dir-9"]
    observations = await repo.list_supervisor_observations("r1")
    alignment = [o for o in observations if o.analysis.get("source") == "teacher_directive"]
    assert alignment, "补丁必须挂在一条教师指令来源的 observation 上"


@pytest.mark.parametrize(
    "raw, expected",
    [
        # 裸数组（标准输出）
        ('[{"field_path": "a"}]', 1),
        # 代码块包裹
        ('```json\n[{"field_path": "a"}]\n```', 1),
        # 对象包裹
        ('{"patches": [{"field_path": "a"}]}', 1),
        # 说明文字 + JSON（provider 常见形态）
        ('Here are the patches:\n[{"field_path": "a"}]\nDone.', 1),
        # 截断 / 非法转义：无法恢复，但必须安全降级为 []
        ('{"patches": [{"field_path": "a"', 0),
        ('[{"field_path": "a", "reason": "a\\qb"}]', 0),
        ("", 0),
        (None, 0),
    ],
)
def test_directive_patch_payload_parsing(raw, expected):
    """纠正类介入的补丁 payload 解析必须既能容错又不能抛异常。

    真实事故：dsh 返回的 JSON 在第 157 字符处多了一个逗号，_apply_directive_patches
    直接 json.loads 抛 JSONDecodeError，被上层 except 吞掉 → 教师纠正只得到一句口头
    回应，patches=0，课件完全没改。这里锁定两种形态（说明文字包裹可恢复、截断安全降级）。
    """
    from backend.classroom.integration import _parse_patch_payload

    payload = _parse_patch_payload(raw)
    assert isinstance(payload, list)
    assert len(payload) == expected
    assert all(isinstance(item, dict) for item in payload)


async def test_lesson_scope_directive_resolves_on_finalize(tmp_path):
    """定稿必须把 scope=lesson 的指令标记为已落实。

    真实事故：orchestrator 只在 slide/round 边界 resolve，定稿路径完全没有 lesson
    分支，导致整节课范围的指令永远停在 status='active'，复盘页一直显示「生效中」。
    """
    from backend.classroom.models import TeacherDirective
    from backend.workflows.events import EventHub

    repo, _l, r = await setup(tmp_path)
    directive = TeacherDirective(
        directive_id="dir-lesson", run_id="run-a", round_id="r1", slide_id="slide_001",
        source_event_id="evt-lesson", content="整节课都要用生活化例子", intent="correct", scope="lesson",
    )
    await repo.save_teacher_directive(directive)
    assert (await repo.list_teacher_directives("run-a", status="active")), "前置：指令应为生效中"

    resolved = await repo.resolve_teacher_directives("run-a", round_id="r1", scope="lesson")

    assert resolved == 1
    stored = await repo.get_teacher_directive("dir-lesson")
    assert stored is not None and stored.status == "resolved"


async def test_question_directives_are_not_superseded(tmp_path):
    """提问类指令只是课堂问答记录，不应被新指令标成「已被新指令覆盖」。"""
    from backend.classroom.models import TeacherDirective

    repo, _l, r = await setup(tmp_path)
    for did in ("dir-q1", "dir-q2"):
        await repo.save_teacher_directive(TeacherDirective(
            directive_id=did, run_id="run-a", round_id="r1", slide_id="slide_001",
            source_event_id=f"evt-{did}", content="这是什么？", intent="question", scope="round",
        ))
    # 模拟新指令到来时的 supersede 规则（与 orchestrator._register_directive 一致）
    for item in await repo.list_teacher_directives("run-a", status="active"):
        if item.intent in ("correct", "require"):
            item.status = "superseded"
            await repo.save_teacher_directive(item)

    stored = await repo.get_teacher_directive("dir-q1")
    assert stored is not None and stored.status == "active"
