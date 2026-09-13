from pathlib import Path

import pytest

from backend.classroom.lesson_blueprint import BlueprintValidationError, LessonBlueprintService
from backend.classroom.repository import ClassroomRepository


def blueprint_payload(minutes: tuple[int, int] = (23, 22)) -> dict:
    return {
        "title": "Operators",
        "learning_objectives": ["distinguish assignment and comparison"],
        "knowledge_points": ["assignment", "comparison"],
        "slides": [
            {
                "title": "Assignment", "purpose": "define assignment", "estimated_minutes": minutes[0],
                "knowledge_points": ["assignment"],
                "ppt_content": {"title": "=", "bullets": ["stores a value"]},
                "speaker_notes": [{"block_type": "EXPLANATION", "content": "Explain =", "estimated_seconds": 120, "knowledge_point_ids": ["assignment"]}],
                "interaction_anchors": [{"interaction_type": "CHECK_UNDERSTANDING", "objective": "check", "planned_question": "What does = do?", "after_block_id": "block_001", "knowledge_point_ids": ["assignment"]}],
                "expected_misconceptions": [{"knowledge_point_id": "assignment", "description": "confuses = with ==", "observable_signals": ["uses == to assign"], "recommended_correction": "contrast examples"}],
            },
            {
                "title": "Comparison", "purpose": "compare values", "estimated_minutes": minutes[1],
                "knowledge_points": ["comparison"],
                "ppt_content": {"title": "==", "bullets": ["compares values"]},
                "speaker_notes": [{"block_type": "SUMMARY", "content": "Summarize ==", "estimated_seconds": 120, "knowledge_point_ids": ["comparison"]}],
            },
        ],
    }


@pytest.mark.asyncio
async def test_service_generates_v1_with_stable_ids_and_persists_nested_content(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    calls: list[tuple[str, str]] = []

    async def generate(system: str, user: str):
        calls.append((system, user))
        return blueprint_payload()

    service = LessonBlueprintService(repo, generate)
    lesson = await service.generate_blueprint("run-a", {"title": "Operators", "learning_objectives": ["distinguish"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45})
    assert lesson.version_number == 1
    assert [slide.slide_id for slide in lesson.slides] == ["slide_001", "slide_002"]
    assert lesson.slides[0].speaker_notes[0].block_id == "slide_001:block_001"
    assert lesson.slides[0].interaction_anchors[0].after_block_id == "slide_001:block_001"
    restored = await repo.get_lesson_version(lesson.id)
    assert restored.slides[0].expected_misconceptions[0].observable_signals == ["uses == to assign"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_invalid_structured_output_is_repaired_once(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    outputs = ["not json", blueprint_payload()]

    async def generate(_system: str, _user: str):
        return outputs.pop(0)

    lesson = await LessonBlueprintService(repo, generate).generate_blueprint("run-a", {"title": "Operators", "learning_objectives": ["goal"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45})
    assert lesson.version_number == 1


@pytest.mark.asyncio
async def test_exact_page_count_is_completed_without_full_deck_retry(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    calls = 0
    payload = blueprint_payload()
    # Simulate the real provider failure: the user requests ten pages but the
    # otherwise valid structured response closes after page nine.
    payload["slides"] = [dict(payload["slides"][index % 2]) for index in range(9)]

    async def generate(_system: str, _user: str):
        nonlocal calls
        calls += 1
        return payload

    lesson = await LessonBlueprintService(repo, generate).generate_blueprint(
        "run-ten",
        {
            "title": "Operators",
            "learning_objectives": ["distinguish operators"],
            "knowledge_points": ["assignment", "comparison"],
            "estimated_minutes": 45,
            "ppt_slide_count": 10,
        },
    )

    assert calls == 1
    assert len(lesson.slides) == 10
    assert [slide.slide_id for slide in lesson.slides] == [f"slide_{index:03d}" for index in range(1, 11)]
    assert sum(slide.estimated_minutes for slide in lesson.slides) == pytest.approx(45)
    assert "综合检验" in lesson.slides[-1].title
    assert len(await repo.list_lesson_versions("run-ten")) == 1


@pytest.mark.asyncio
async def test_unverifiable_anchor_id_is_downgraded_without_regenerating_deck(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    calls = 0
    payload = blueprint_payload()
    payload["slides"] = [dict(payload["slides"][0]) for _ in range(5)]
    for slide in payload["slides"]:
        slide["interaction_anchors"] = [{
            "interaction_type": "CHECK_UNDERSTANDING",
            "objective": "check",
            "planned_question": "What did we learn?",
            "after_block_id": "provider-invented-block-id",
            "knowledge_point_ids": ["assignment"],
        }]

    async def generate(_system: str, _user: str):
        nonlocal calls
        calls += 1
        return payload

    lesson = await LessonBlueprintService(repo, generate).generate_blueprint(
        "run-anchor-repair",
        {
            "title": "Operators",
            "learning_objectives": ["distinguish operators"],
            "knowledge_points": ["assignment", "comparison"],
            "estimated_minutes": 45,
            "ppt_slide_count": 5,
        },
    )

    assert calls == 1
    assert len(lesson.slides) == 5
    for slide in lesson.slides:
        anchor = slide.interaction_anchors[0]
        assert anchor.after_block_id == slide.speaker_notes[-1].block_id
    assert len(await repo.list_lesson_versions("run-anchor-repair")) == 1


@pytest.mark.asyncio
async def test_existing_v1_is_reused_without_provider_call(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()

    async def initial_generate(_system: str, _user: str):
        return blueprint_payload()

    first = await LessonBlueprintService(repo, initial_generate).generate_blueprint(
        "run-idempotent",
        {"title": "Operators", "learning_objectives": ["goal"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45},
    )

    async def must_not_generate(_system: str, _user: str):
        raise AssertionError("provider must not be called for an existing V1")

    second = await LessonBlueprintService(repo, must_not_generate).generate_blueprint(
        "run-idempotent",
        {"title": "Operators", "learning_objectives": ["goal"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45},
    )
    assert second.id == first.id
    assert len(await repo.list_lesson_versions("run-idempotent")) == 1


def test_structured_parser_repairs_minor_json_syntax_without_bypassing_schema() -> None:
    parsed = LessonBlueprintService._parse_structured('{"title":"Demo" "slides":[]}')
    assert parsed == {"title": "Demo", "slides": []}


def test_generation_context_derives_objective_for_legacy_run_without_objectives() -> None:
    context = LessonBlueprintService(None).build_generation_context({
        "title": "Python 基础",
        "teaching_data": {"knowledge_points": [{"title": "变量"}]},
    })
    assert context["learning_objectives"] == ["理解并能够应用：变量"]


def test_generation_context_uses_confirmed_scope_instead_of_all_candidates() -> None:
    context = LessonBlueprintService(None).build_generation_context({
        "title": "Python 基础",
        "teaching_data": {
            "knowledge_points": [{"title": "语言简介"}, {"title": "安装环境"}],
            "scope": {"selected_point_titles": ["语言简介"], "estimated_minutes": 10},
        },
    })
    assert context["knowledge_points"] == ["语言简介"]
    assert context["learning_objectives"] == ["理解并能够应用：语言简介"]


@pytest.mark.asyncio
async def test_provider_cannot_widen_confirmed_knowledge_scope(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    invalid = blueprint_payload()
    repaired = {
        "title": "Assignment only",
        "slides": [{
            "title": "Assignment",
            "purpose": "define assignment",
            "estimated_minutes": 45,
            "knowledge_points": ["assignment"],
            "ppt_content": {"title": "=", "bullets": ["stores a value"]},
            "speaker_notes": [{
                "block_type": "EXPLANATION",
                "content": "Explain assignment",
                "estimated_seconds": 120,
                "knowledge_point_ids": ["assignment"],
            }],
        }],
    }
    outputs = [invalid, repaired]

    async def generate(_system: str, _user: str):
        return outputs.pop(0)

    lesson = await LessonBlueprintService(repo, generate).generate_blueprint(
        "run-a",
        {
            "title": "Operators",
            "teaching_data": {
                "knowledge_points": [{"title": "assignment"}, {"title": "comparison"}],
                "scope": {"selected_point_titles": ["assignment"], "estimated_minutes": 45},
            },
        },
    )
    assert lesson.knowledge_points == ["assignment"]
    assert lesson.slides[0].knowledge_points == ["assignment"]
    assert len(await repo.list_lesson_versions("run-a")) == 1


@pytest.mark.asyncio
async def test_second_failure_does_not_persist_partial_lesson(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()

    async def generate(_system: str, _user: str):
        return {"title": "Broken", "learning_objectives": ["goal"], "knowledge_points": ["kp"], "slides": []}

    with pytest.raises(BlueprintValidationError):
        await LessonBlueprintService(repo, generate).generate_blueprint("run-a", {"title": "Broken", "learning_objectives": ["goal"], "knowledge_points": ["kp"], "estimated_minutes": 45})
    assert await repo.list_lesson_versions("run-a") == []


@pytest.mark.asyncio
async def test_run_isolation_and_time_budget_validation(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()

    async def generate(_system: str, user: str):
        return blueprint_payload((10, 10)) if "run-b" in user else blueprint_payload()

    service = LessonBlueprintService(repo, generate)
    await service.generate_blueprint("run-a", {"title": "A", "learning_objectives": ["goal"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45})
    with pytest.raises(BlueprintValidationError):
        await service.generate_blueprint("run-b", {"title": "B", "learning_objectives": ["goal"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45})
    assert len(await repo.list_lesson_versions("run-a")) == 1
    assert await repo.list_lesson_versions("run-b") == []


def test_requested_page_count_builds_balanced_topic_allocation() -> None:
    context = LessonBlueprintService(None).build_generation_context({
        "title": "Python",
        "knowledge_points": ["A", "B", "C", "D", "E"],
        "learning_objectives": ["understand"],
        "estimated_minutes": 45,
        "ppt_slide_count": 3,
    })

    allocation = context["slide_allocation"]
    assert [item["knowledge_points"] for item in allocation] == [["A", "B"], ["C", "D"], ["E"]]
    assert {point for item in allocation for point in item["knowledge_points"]} == {"A", "B", "C", "D", "E"}


@pytest.mark.asyncio
async def test_string_code_blocks_are_normalized_without_structured_retry(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    calls = 0
    payload = blueprint_payload()
    payload["slides"][0]["ppt_content"]["code_blocks"] = ['# Python\nprint("Hello, Python")']

    async def generate(_system: str, _user: str):
        nonlocal calls
        calls += 1
        return payload

    lesson = await LessonBlueprintService(repo, generate).generate_blueprint(
        "run-code-block",
        {"title": "Operators", "learning_objectives": ["goal"], "knowledge_points": ["assignment", "comparison"], "estimated_minutes": 45},
    )

    assert calls == 1
    assert lesson.slides[0].ppt_content.code_blocks == [{"code": '# Python\nprint("Hello, Python")'}]


@pytest.mark.asyncio
async def test_requested_page_allocation_is_applied_to_slides(tmp_path: Path) -> None:
    repo = ClassroomRepository(tmp_path / "db.sqlite")
    await repo.initialize()
    payload = blueprint_payload()
    payload["slides"] = [dict(payload["slides"][0]) for _ in range(3)]
    for slide in payload["slides"]:
        slide["speaker_notes"] = [dict(payload["slides"][0]["speaker_notes"][0], knowledge_point_ids=[])]
        slide["interaction_anchors"] = []
        slide["expected_misconceptions"] = []

    async def generate(_system: str, _user: str):
        return payload

    lesson = await LessonBlueprintService(repo, generate).generate_blueprint(
        "run-three-pages",
        {
            "title": "Python",
            "learning_objectives": ["understand"],
            "knowledge_points": ["A", "B", "C", "D", "E"],
            "estimated_minutes": 45,
            "ppt_slide_count": 3,
        },
    )

    assert [slide.knowledge_points for slide in lesson.slides] == [["A", "B"], ["C", "D"], ["E"]]


def test_overlong_provider_deck_is_compacted_without_dropping_content() -> None:
    slides = [
        {"title": f"Page {index}", "purpose": "", "ppt_content": {"bullets": [f"topic-{index}"]}}
        for index in range(1, 6)
    ]

    compacted = LessonBlueprintService._compact_provider_slides(slides, 3)

    assert len(compacted) == 3
    merged_bullets = [bullet for slide in compacted for bullet in slide["ppt_content"]["bullets"]]
    assert merged_bullets == ["topic-1", "topic-2", "topic-3", "topic-4", "topic-5"]
