from pathlib import Path

import pytest

from backend.classroom.lesson_blueprint import BlueprintValidationError
from backend.classroom.lesson_review import LessonReviewService
from backend.classroom.models import InteractionAnchor, LessonSlide, LessonVersion, PptContent, SpeakerNoteBlock
from backend.classroom.repository import ClassroomRepository


def draft(run_id: str = "run-review") -> LessonVersion:
    return LessonVersion(
        id="version-review",
        lesson_id=f"lesson:{run_id}",
        run_id=run_id,
        version_number=1,
        title="Python",
        learning_objectives=["理解变量"],
        knowledge_points=["变量"],
        estimated_minutes=1,
        slides=[LessonSlide(
            id=f"row-slide-1-{run_id}", slide_id="slide_001", order=1, title="变量",
            learning_objectives=["理解变量"], knowledge_points=["变量"], estimated_minutes=1,
            ppt_content={"title": "变量", "bullets": ["变量保存值"]},
            speaker_notes=[SpeakerNoteBlock(id=f"row-block-1-{run_id}", block_id="slide_001:block_001", order=1, content="讲解变量", estimated_seconds=50)],
        )],
    )


@pytest.mark.asyncio
async def test_replace_draft_preserves_semantic_ids_and_review_history(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    lesson = draft()
    await repo.create_lesson_version(lesson)
    service = LessonReviewService(repo)
    changed = lesson.slides[0].model_copy(update={"ppt_content": PptContent(title="变量", bullets=["变量保存并引用值"])})
    updated = await service.replace_draft(lesson, [changed])
    assert updated.slides[0].slide_id == "slide_001"
    assert updated.slides[0].speaker_notes[0].block_id == "slide_001:block_001"
    restored = await repo.get_lesson_version(lesson.id)
    assert restored.slides[0].ppt_content.bullets == ["变量保存并引用值"]


@pytest.mark.asyncio
async def test_ready_version_cannot_be_edited(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    lesson = draft()
    await repo.create_lesson_version(lesson)
    await repo.update_lesson_version_status(lesson.id, "ready")
    with pytest.raises(ValueError, match="draft"):
        await LessonReviewService(repo).replace_draft(lesson.model_copy(update={"status": "ready"}), lesson.slides)


class _MockModel:
    is_mock = True
    provider = "mock"


class _Workflow:
    model = _MockModel()


class _SequenceEngine:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def generate_in_session(self, session_id, system, user):
        self.calls.append((session_id, system, user))
        return self.responses.pop(0)


class _RealModel:
    is_mock = False
    provider = "dsh"

    def __init__(self, engine):
        self.engine = engine

    def ensure_dsh_engine(self):
        return self.engine


class _RealWorkflow:
    def __init__(self, responses):
        self.model = _RealModel(_SequenceEngine(responses))


@pytest.mark.asyncio
async def test_teacher_review_updates_only_target_slide_and_persists_chat(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    lesson = draft()
    second = LessonSlide.model_validate({**lesson.slides[0].model_dump(mode="python"),
        "id": "row-slide-2", "slide_id": "slide_002", "order": 2, "title": "常量",
        "ppt_content": {"title": "常量", "bullets": ["常量不重新赋值"]},
        "speaker_notes": [{"id": "row-block-2", "block_id": "slide_002:block_001", "order": 1, "content": "讲解常量", "estimated_seconds": 50}],
    })
    lesson = lesson.model_copy(update={"slides": [lesson.slides[0], second]})
    await repo.create_lesson_version(lesson)
    updated, message = await LessonReviewService(repo).revise_slide(lesson, "slide_001", "补充一个案例", _Workflow())
    assert updated.slides[0].ppt_content.examples
    assert updated.slides[1].model_dump(exclude={"id"}) == lesson.slides[1].model_dump(exclude={"id"})
    assert message.slide_id == "slide_001"
    history = await repo.list_lesson_review_messages(lesson.run_id, lesson.id)
    assert [item.role for item in history][0] == "user"
    assert [item.role for item in history][-1] == "teacher"
    assert any(item.role == "system" and "结构化理解" in item.content for item in history)


@pytest.mark.asyncio
async def test_teacher_review_retries_when_first_response_has_no_visible_diff(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    lesson = draft()
    await repo.create_lesson_version(lesson)
    changed_ppt = lesson.slides[0].ppt_content.model_dump(mode="json")
    changed_ppt["subtitle"] = "用储物柜理解变量"
    workflow = _RealWorkflow([
        {"summary": "已完成修改"},
        {"ppt_content": changed_ppt, "summary": "已补充零基础类比"},
    ])

    updated, message = await LessonReviewService(repo).revise_slide(
        lesson, "slide_001", "换成零基础学生能理解的类比", workflow
    )

    assert updated.slides[0].ppt_content.subtitle == "用储物柜理解变量"
    assert len(workflow.model.engine.calls) == 2
    assert "不要只返回 summary" in workflow.model.engine.calls[1][2]
    assert message.content == "已补充零基础类比"


@pytest.mark.asyncio
async def test_teacher_review_rejects_two_responses_without_visible_diff(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    lesson = draft()
    await repo.create_lesson_version(lesson)
    workflow = _RealWorkflow([
        {"summary": "已完成修改"},
        {"summary": "再次完成修改"},
    ])

    with pytest.raises(BlueprintValidationError, match="未产生可验证"):
        await LessonReviewService(repo).revise_slide(
            lesson, "slide_001", "换成零基础学生能理解的类比", workflow
        )

    restored = await repo.get_lesson_version(lesson.id)
    assert restored.slides[0].ppt_content == lesson.slides[0].ppt_content
    history = await repo.list_lesson_review_messages(lesson.run_id, lesson.id)
    assert [item.role for item in history][0] == "user"
    assert any(item.role == "system" and "没有产生可验证修改" in item.content for item in history)


@pytest.mark.asyncio
async def test_teacher_review_applies_explicit_instruction_when_provider_only_summarizes(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    lesson = draft()
    lesson = lesson.model_copy(update={
        "slides": [lesson.slides[0].model_copy(update={
            "ppt_content": PptContent(title="变量", bullets=["变量保存值", "变量可以重新赋值", "变量名需要有意义", "变量参与表达式"])
        })]
    })
    await repo.create_lesson_version(lesson)
    workflow = _RealWorkflow([{"summary": "已完成修改"}, {"summary": "已完成修改"}])

    updated, message = await LessonReviewService(repo).revise_slide(
        lesson, "slide_001", "精简要点，补充一个可观察的课堂案例", workflow
    )

    assert len(updated.slides[0].ppt_content.bullets) == 3
    assert updated.slides[0].ppt_content.examples
    assert "局部修改" in message.content


def test_teacher_review_can_add_interaction_and_misconception_with_stable_ids():
    lesson = draft()
    slide = lesson.slides[0]
    revised = LessonReviewService._merge_slide(slide, {
        "interaction_anchors": [{
            "interaction_type": "CHECK_UNDERSTANDING",
            "objective": "检查变量理解",
            "planned_question": "变量像生活中的什么？",
            "target_student_level": "basic",
            "after_block_id": "slide_001:block_001",
            "knowledge_point_ids": ["变量", "越界知识点"],
        }],
        "expected_misconceptions": [{
            "knowledge_point_id": "变量",
            "description": "把变量理解成固定值",
            "observable_signals": ["认为不能重新赋值"],
            "recommended_correction": "用可更换标签的储物柜纠正",
        }],
    }, lesson.knowledge_points)

    assert revised.interaction_anchors[0].interaction_id == "slide_001:interaction_001"
    assert revised.interaction_anchors[0].type == "check"
    assert revised.interaction_anchors[0].target_student_level == "low"
    assert revised.interaction_anchors[0].knowledge_point_ids == ["变量"]
    assert revised.expected_misconceptions[0].misconception_id == "slide_001:misconception_001"
    assert revised.expected_misconceptions[0].correction_strategy == "用可更换标签的储物柜纠正"


@pytest.mark.asyncio
async def test_review_data_is_isolated_by_run(tmp_path: Path):
    repo = ClassroomRepository(tmp_path / "review.db")
    await repo.initialize()
    first = draft("run-a")
    second = draft("run-b").model_copy(update={"id": "version-b"})
    await repo.create_lesson_version(first)
    await repo.create_lesson_version(second)
    from backend.classroom.models import LessonReviewMessage
    await repo.append_lesson_review_message(LessonReviewMessage(run_id="run-a", version_id=first.id, role="user", content="A"))
    assert len(await repo.list_lesson_review_messages("run-a", first.id)) == 1
    assert await repo.list_lesson_review_messages("run-b", second.id) == []


def test_review_rejects_anchor_that_loses_its_stable_block():
    lesson = draft()
    slide = lesson.slides[0].model_copy(update={
        "interaction_anchors": [InteractionAnchor(
            interaction_id="anchor-1", objective="检查理解", planned_question="变量是什么？",
            after_block_id="slide_001:block_missing", knowledge_point_ids=["变量"],
        )],
    })
    with pytest.raises(BlueprintValidationError, match="不存在的讲稿 Block"):
        LessonReviewService(None).validate_for_review(lesson.model_copy(update={"slides": [slide]}))


def test_review_accepts_multiple_stable_blocks_and_anchor_reference():
    lesson = draft()
    second = SpeakerNoteBlock(
        id="row-block-2", block_id="slide_001:block_002", order=2,
        block_type="summary", content="总结变量", estimated_seconds=10, knowledge_point_ids=["变量"],
    )
    slide = lesson.slides[0].model_copy(update={
        "speaker_notes": [lesson.slides[0].speaker_notes[0].model_copy(update={"knowledge_point_ids": ["变量"]}), second],
        "interaction_anchors": [InteractionAnchor(
            interaction_id="anchor-1", objective="检查理解", planned_question="变量是什么？",
            after_block_id=second.block_id, knowledge_point_ids=["变量"],
        )],
    })
    LessonReviewService(None).validate_for_review(lesson.model_copy(update={"slides": [slide]}))
