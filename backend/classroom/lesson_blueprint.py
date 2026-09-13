"""Structured Lesson Blueprint generation for classroom_v2.

This service only prepares and persists LessonVersion V1.  It does not run a
classroom, create classroom events, or invoke Teacher/Student/Supervisor
sessions.
"""

from __future__ import annotations

import json
import inspect
import re
from copy import deepcopy
from collections.abc import Awaitable, Callable
from typing import Any

from json_repair import repair_json

from .models import (
    ExpectedMisconception,
    InteractionAnchor,
    LessonSlide,
    LessonVersion,
    PptContent,
    SpeakerNoteBlock,
)
from .prompts import build_lesson_blueprint_prompt
from .repository import ClassroomRepository


Generator = Callable[[str, str], Awaitable[Any]]
RetryObserver = Callable[[str], Any]


class BlueprintValidationError(ValueError):
    pass


class LessonBlueprintService:
    def __init__(self, repository: ClassroomRepository, generator: Generator | None = None, on_retry: RetryObserver | None = None) -> None:
        self.repository = repository
        self.generator = generator
        self.on_retry = on_retry

    def build_generation_context(self, source: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
        teaching = source.get("teaching_data") or source
        framework = teaching.get("teaching_framework") or {}
        analysis = teaching.get("content_analysis") or {}
        scope = source.get("scope") or teaching.get("scope") or {}
        points = source.get("knowledge_points") or teaching.get("knowledge_points") or analysis.get("key_points") or []
        point_names = [p.get("title", p.get("id", "")) if isinstance(p, dict) else str(p) for p in points]
        selected_points = [
            str(item).strip()
            for item in scope.get("selected_point_titles") or []
            if str(item).strip()
        ]
        if selected_points:
            point_names = selected_points
        objectives = source.get("learning_objectives") or framework.get("learning_objectives") or teaching.get("learning_objectives") or []
        # Older teaching_v1 runs do not always persist an explicit objective
        # list even though they contain a selected knowledge-point scope.  A
        # classroom Blueprint still requires at least one objective, so derive
        # a transparent, deterministic objective from that scope instead of
        # failing with an opaque 422.  New runs with explicit objectives are
        # unaffected.
        if (not objectives or selected_points) and point_names:
            objectives = [f"理解并能够应用：{name}" for name in point_names[:8]]
        if not objectives:
            title_hint = str(source.get("title") or source.get("objective") or teaching.get("title") or "本课程主题").strip()
            objectives = [f"理解并能够说明{title_hint}的核心概念"]
        # The requested page count is a teaching-design constraint, not just
        # an output-length constraint.  Give the model an explicit, balanced
        # topic allocation so three pages can cover five knowledge points
        # without silently dropping the last two.
        context = {
            "run_id": run_id or source.get("run_id") or source.get("id"),
            "title": source.get("title") or source.get("objective") or teaching.get("title") or "未命名课程",
            "learning_objectives": [str(x) for x in objectives if str(x).strip()],
            "knowledge_points": [str(x) for x in point_names if str(x).strip()],
            "estimated_minutes": int(scope.get("estimated_minutes") or source.get("estimated_minutes") or 45),
            "target_slide_count": int(scope.get("ppt_slide_count") or source.get("ppt_slide_count") or 0) or None,
            "depth": scope.get("depth", "standard"),
            "content_analysis": analysis,
            "teaching_framework": framework,
        }
        context["slide_allocation"] = self._build_slide_allocation(
            context["knowledge_points"], context["target_slide_count"]
        )
        return context

    @staticmethod
    def _build_slide_allocation(knowledge_points: list[str], slide_count: int | None) -> list[dict[str, Any]]:
        """Build a deterministic topic plan for the exact requested page count.

        When there are fewer pages than knowledge points, contiguous balanced
        groups are used.  When there are extra pages, later pages become
        application/synthesis pages instead of inventing new knowledge points.
        """
        points = [str(item).strip() for item in knowledge_points if str(item).strip()]
        count = int(slide_count or 0)
        if count <= 0:
            return []
        if not points:
            return [
                {"slide_number": index + 1, "knowledge_points": [], "focus": "lesson structure"}
                for index in range(count)
            ]

        groups: list[list[str]] = []
        if count <= len(points):
            base, remainder = divmod(len(points), count)
            cursor = 0
            for index in range(count):
                size = base + (1 if index < remainder else 0)
                groups.append(points[cursor:cursor + size])
                cursor += size
        else:
            groups = [[point] for point in points]
            while len(groups) < count:
                # Reserve the final page for synthesis; intermediate spare
                # pages reinforce a relevant point rather than creating a
                # fake topic.
                if len(groups) == count - 1:
                    groups.append(list(points))
                else:
                    groups.append([points[(len(groups) - len(points)) % len(points)]])

        allocation: list[dict[str, Any]] = []
        for index, group in enumerate(groups):
            if index == count - 1 and count > len(points):
                focus = "synthesis and transfer"
            elif len(group) > 1:
                focus = "connected concepts"
            else:
                focus = "concept and example"
            allocation.append({
                "slide_number": index + 1,
                "knowledge_points": group,
                "focus": focus,
            })
        return allocation

    async def generate_blueprint(self, run_id: str, source: dict[str, Any], *, model: str | None = None) -> LessonVersion:
        # V1 is idempotent within a run.  Page refreshes, React development
        # remounts and repeated prepare requests must reuse the persisted draft
        # instead of spending another provider call on the same lesson.
        existing_versions = await self.repository.list_lesson_versions(run_id)
        existing_v1 = next((item for item in existing_versions if item.version_number == 1), None)
        if existing_v1 is not None:
            return existing_v1
        context = self.build_generation_context(source, run_id=run_id)
        if not context["learning_objectives"]:
            raise BlueprintValidationError("learning objectives must not be empty")
        if self.generator is None:
            raise RuntimeError("LessonBlueprintService requires an injected structured generator in Phase 3")
        system, user = build_lesson_blueprint_prompt(context)
        last_error: Exception | None = None
        last_raw: Any = ""
        for attempt in range(2):
            try:
                raw = await self.generator(system, user)
                last_raw = raw
                payload = self._parse_structured(raw)
                payload = self._normalize_generation_payload(payload, context)
                lesson = self._build_lesson(run_id, context, payload)
                self.validate_blueprint(lesson, context["estimated_minutes"], context.get("target_slide_count"))
                await self.repository.ensure_run(run_id)
                created = await self.repository.create_lesson_version_if_absent(lesson)
                if created:
                    return lesson
                # A second worker may have finished the same run while this
                # provider response was in flight.  The database winner is the
                # canonical V1; never expose or persist a duplicate draft.
                concurrent_versions = await self.repository.list_lesson_versions(run_id)
                concurrent_v1 = next((item for item in concurrent_versions if item.version_number == 1), None)
                if concurrent_v1 is not None:
                    return concurrent_v1
                raise BlueprintValidationError("LessonVersion V1 was not persisted")
            except (BlueprintValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 0:
                    if self.on_retry is not None:
                        observed = self.on_retry(str(exc))
                        if inspect.isawaitable(observed):
                            await observed
                    system, user = build_lesson_blueprint_prompt(
                        context,
                        repair=True,
                        invalid_output=str(last_raw),
                        validation_error=str(exc),
                    )
        raise BlueprintValidationError(f"blueprint generation failed after structured retry: {last_error}") from last_error

    @classmethod
    def _normalize_generation_payload(cls, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Repair provider-owned shape without regenerating the whole deck.

        The provider owns teaching content.  The platform owns exact page
        count, stable ordering and the requested time budget.  A model that
        returns 9 complete slides for a 10-slide request therefore needs one
        deterministic supplemental slide, not a second full-deck generation.
        Empty/malformed decks are intentionally left for the structured retry.
        """
        result = dict(payload)
        raw_slides = result.get("slides")
        if not isinstance(raw_slides, list) or not raw_slides:
            return result
        slides = [dict(item) for item in raw_slides if isinstance(item, dict)]
        if not slides:
            return result
        target = int(context.get("target_slide_count") or 0)
        if target:
            if len(slides) > target:
                slides = cls._compact_provider_slides(slides, target)
            while len(slides) < target:
                slides.append(cls._supplemental_slide(context, len(slides), target))
            allocation = context.get("slide_allocation") or cls._build_slide_allocation(
                context.get("knowledge_points") or [], target
            )
            for index, slide in enumerate(slides):
                if index < len(allocation) and allocation[index].get("knowledge_points"):
                    # The platform-owned scope is authoritative.  The model
                    # still writes the actual teaching content, but page/topic
                    # ownership follows the deterministic plan.
                    slide["knowledge_points"] = list(allocation[index]["knowledge_points"])
            cls._normalize_time_budget(slides, int(context["estimated_minutes"]))
        result["slides"] = slides
        return result

    @classmethod
    def _compact_provider_slides(cls, slides: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
        """Merge an overlong provider deck instead of dropping its content."""
        if target <= 0 or len(slides) <= target:
            return slides
        base_size, remainder = divmod(len(slides), target)
        compacted: list[dict[str, Any]] = []
        cursor = 0
        for index in range(target):
            size = base_size + (1 if index < remainder else 0)
            chunk = slides[cursor:cursor + size]
            cursor += size
            merged = deepcopy(chunk[0])
            for extra in chunk[1:]:
                merged["purpose"] = "；".join(
                    value for value in [str(merged.get("purpose") or "").strip(), str(extra.get("purpose") or "").strip()]
                    if value
                )
                for field in ("learning_objectives", "knowledge_points"):
                    merged[field] = cls._unique_texts(
                        list(merged.get(field) or []) + list(extra.get(field) or [])
                    )
                merged["speaker_notes"] = list(merged.get("speaker_notes") or []) + list(extra.get("speaker_notes") or [])
                merged["interaction_anchors"] = list(merged.get("interaction_anchors") or []) + list(extra.get("interaction_anchors") or [])
                merged["expected_misconceptions"] = list(merged.get("expected_misconceptions") or []) + list(extra.get("expected_misconceptions") or [])
                first_ppt = dict(merged.get("ppt_content") or {})
                extra_ppt = dict(extra.get("ppt_content") or {})
                for field in ("bullets", "examples", "code_blocks"):
                    first_ppt[field] = list(first_ppt.get(field) or []) + list(extra_ppt.get(field) or [])
                if not first_ppt.get("subtitle") and extra_ppt.get("subtitle"):
                    first_ppt["subtitle"] = extra_ppt["subtitle"]
                if extra_ppt.get("visual_instruction"):
                    first_ppt["visual_instruction"] = "；".join(
                        value for value in [str(first_ppt.get("visual_instruction") or "").strip(), str(extra_ppt["visual_instruction"]).strip()]
                        if value
                    )
                merged["ppt_content"] = first_ppt
            compacted.append(merged)
        return compacted

    @staticmethod
    def _unique_texts(values: list[Any]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _supplemental_slide(context: dict[str, Any], zero_based_index: int, total: int) -> dict[str, Any]:
        points = [str(item).strip() for item in context.get("knowledge_points") or [] if str(item).strip()]
        objectives = [str(item).strip() for item in context.get("learning_objectives") or [] if str(item).strip()]
        point = points[zero_based_index % len(points)] if points else str(context.get("title") or "本课内容")
        is_last = zero_based_index == total - 1
        title = f"{point}：综合检验" if is_last else f"{point}：应用与巩固"
        purpose = f"通过可观察任务检验学生能否理解并应用{point}"
        return {
            "title": title,
            "purpose": purpose,
            "learning_objectives": objectives,
            "knowledge_points": [point] if points else [],
            "estimated_minutes": max(0.25, float(context.get("estimated_minutes") or total) / total),
            "ppt_content": {
                "title": title,
                "subtitle": "从概念理解走向可观察的课堂应用",
                "bullets": [
                    f"用自己的语言说明{point}的核心含义",
                    f"结合具体任务判断{point}的适用条件",
                    "说明判断依据，并检查常见误区",
                ],
                "examples": [f"选择一个与{point}相关的真实任务，先预测结果，再验证并解释差异。"],
                "code_blocks": [],
                "visual_instruction": "使用步骤卡呈现预测、验证、解释三个环节",
            },
            "speaker_notes": [{
                "block_type": "SUMMARY" if is_last else "EXPLANATION",
                "content": f"引导学生围绕{point}完成一次可观察的理解检查：先说明概念和条件，再应用到具体任务，最后解释判断依据并纠正常见误区。",
                "estimated_seconds": max(15, round(float(context.get("estimated_minutes") or total) * 48 / total)),
                "knowledge_point_ids": [point] if points else [],
            }],
            "interaction_anchors": [{
                "interaction_type": "CHECK_UNDERSTANDING",
                "objective": purpose,
                "planned_question": f"请结合一个具体任务说明{point}在什么条件下成立，并给出判断依据。",
                "target_student_level": "all",
                "after_block_id": "block_001",
                "knowledge_point_ids": [point] if points else [],
                "priority": 1,
            }],
            "expected_misconceptions": [],
        }

    @staticmethod
    def _normalize_time_budget(slides: list[dict[str, Any]], expected_minutes: int) -> None:
        if not slides:
            return
        # Equal allocation is deliberately predictable and keeps the exact
        # total.  Teachers can fine-tune individual pages in the review gate.
        per_slide = expected_minutes / len(slides)
        if per_slide < 0.25:
            raise BlueprintValidationError(
                f"{len(slides)} slides cannot fit into {expected_minutes} minutes; reduce the page count"
            )
        allocated = 0.0
        for index, slide in enumerate(slides):
            minutes = round(expected_minutes - allocated, 3) if index == len(slides) - 1 else round(per_slide, 3)
            allocated += minutes
            slide["estimated_minutes"] = minutes
            notes = slide.get("speaker_notes")
            if not isinstance(notes, list) or not notes:
                continue
            max_seconds = max(len(notes), int(minutes * 60 * 0.92))
            requested = [max(1, int(float(item.get("estimated_seconds") or 30))) for item in notes if isinstance(item, dict)]
            total_requested = sum(requested)
            if total_requested <= max_seconds:
                continue
            scale = max_seconds / total_requested
            note_index = 0
            for item in notes:
                if not isinstance(item, dict):
                    continue
                item["estimated_seconds"] = max(1, round(requested[note_index] * scale))
                note_index += 1

    def validate_blueprint(self, lesson: LessonVersion, expected_minutes: int | None = None, expected_slide_count: int | None = None) -> None:
        if not lesson.slides:
            raise BlueprintValidationError("slides must not be empty")
        if not lesson.learning_objectives:
            raise BlueprintValidationError("learning objectives must not be empty")
        slides = sorted(lesson.slides, key=lambda item: item.order)
        if [s.order for s in slides] != list(range(1, len(slides) + 1)):
            raise BlueprintValidationError("slide order must be contiguous")
        if len({s.slide_id for s in slides}) != len(slides):
            raise BlueprintValidationError("slide_id must be unique")
        if expected_slide_count and len(slides) != expected_slide_count:
            raise BlueprintValidationError(f"expected {expected_slide_count} slides, received {len(slides)}")
        valid_points = set(lesson.knowledge_points)
        total_minutes = sum(s.estimated_minutes for s in slides)
        if expected_minutes and abs(total_minutes - expected_minutes) > expected_minutes * 0.1:
            raise BlueprintValidationError(f"slide time budget {total_minutes}m is outside ±10% of {expected_minutes}m")
        block_ids: set[str] = set()
        for slide in slides:
            local_blocks = {block.block_id for block in slide.speaker_notes}
            if len(local_blocks) != len(slide.speaker_notes):
                raise BlueprintValidationError(f"duplicate block_id on {slide.slide_id}")
            block_ids.update(local_blocks)
            for block in slide.speaker_notes:
                if block.knowledge_point_ids and not set(block.knowledge_point_ids) <= valid_points:
                    raise BlueprintValidationError(f"unknown block knowledge point on {slide.slide_id}")
            for anchor in slide.interaction_anchors:
                if anchor.after_block_id and anchor.after_block_id not in local_blocks:
                    raise BlueprintValidationError(f"anchor {anchor.interaction_id} references missing block")
                if anchor.knowledge_point_ids and not set(anchor.knowledge_point_ids) <= valid_points:
                    raise BlueprintValidationError(f"unknown anchor knowledge point on {slide.slide_id}")
            for misconception in slide.expected_misconceptions:
                if misconception.knowledge_point_id and misconception.knowledge_point_id not in valid_points:
                    raise BlueprintValidationError(f"unknown misconception knowledge point on {slide.slide_id}")
            note_seconds = sum(block.estimated_seconds for block in slide.speaker_notes)
            if note_seconds > slide.estimated_minutes * 60 * 1.25:
                raise BlueprintValidationError(f"speaker notes exceed time budget on {slide.slide_id}")
        if len(block_ids) != sum(len(s.speaker_notes) for s in slides):
            raise BlueprintValidationError("block_id must be globally unique")

    def _build_lesson(self, run_id: str, context: dict[str, Any], payload: dict[str, Any]) -> LessonVersion:
        # The teacher-confirmed scope is authoritative. Provider output may
        # enrich teaching content, but it cannot silently widen the lesson to
        # unselected candidate knowledge points.
        points = [str(x) for x in context["knowledge_points"] if str(x).strip()]
        objectives = [str(x) for x in context["learning_objectives"] if str(x).strip()]
        slides: list[LessonSlide] = []
        for idx, item in enumerate(payload.get("slides") or [], start=1):
            slide_id = f"slide_{idx:03d}"
            notes: list[SpeakerNoteBlock] = []
            block_id_map: dict[str, str] = {}
            for block_idx, block in enumerate(item.get("speaker_notes") or [], start=1):
                block_data = dict(block)
                provider_block_id = str(block_data.get("block_id") or block_data.get("id") or "").strip()
                block_types = {
                    "OPENING": "explanation", "EXPLANATION": "explanation", "EXAMPLE": "example",
                    "DEMONSTRATION": "example", "TRANSITION": "transition", "QUESTION_PREP": "question",
                    "SUMMARY": "summary", "FEEDBACK": "feedback", "QUESTION": "question",
                    "CHECK": "question", "CHECK_UNDERSTANDING": "question", "PRACTICE": "question",
                }
                # Providers occasionally return a semantically reasonable label
                # (for example ``check``) that is outside our closed domain enum.
                # Normalize known aliases and safely retain unknown preparation
                # blocks as ``other`` instead of failing an otherwise valid V1.
                raw_block_type = str(block_data.get("block_type", "explanation")).strip()
                normalized_block_type = block_types.get(raw_block_type.upper(), raw_block_type.lower())
                allowed_block_types = {"explanation", "question", "example", "feedback", "summary", "transition", "other"}
                block_data["block_type"] = normalized_block_type if normalized_block_type in allowed_block_types else "other"
                block_data["block_id"] = f"{slide_id}:block_{block_idx:03d}"
                block_data["order"] = block_idx
                notes.append(SpeakerNoteBlock.model_validate(block_data))
                if provider_block_id:
                    block_id_map[provider_block_id] = block_data["block_id"]
            anchors: list[InteractionAnchor] = []
            for anchor in item.get("interaction_anchors") or []:
                anchor_data = dict(anchor)
                anchor_types = {
                    "CHECK_UNDERSTANDING": "check", "CONCEPT_QUESTION": "question",
                    "APPLICATION_QUESTION": "practice", "PREDICTION": "reflection", "REFLECTION": "reflection",
                }
                anchor_data["type"] = anchor_types.get(str(anchor_data.pop("interaction_type", anchor_data.get("type", "question"))).upper(), str(anchor_data.get("type", "question")).lower())
                level_aliases = {
                    "advanced": "high", "extension": "high", "拓展": "high", "拓展型": "high",
                    "intermediate": "medium", "progressing": "medium", "进阶": "medium", "进阶型": "medium",
                    "basic": "low", "beginner": "low", "foundation": "low", "基础": "low", "基础型": "low",
                    "any": "all", "everyone": "all", "全体": "all",
                }
                raw_level = str(anchor_data.get("target_student_level") or "all").strip().lower()
                anchor_data["target_student_level"] = level_aliases.get(raw_level, raw_level)
                anchor_data["interaction_id"] = anchor_data.get("interaction_id") or f"{slide_id}:interaction_{len(anchors)+1:03d}"
                provider_after = str(anchor_data.get("after_block_id") or "").strip()
                if provider_after:
                    normalized_after = block_id_map.get(provider_after)
                    if normalized_after is None:
                        # Models commonly invent ids such as sn_1_2. Stable ids
                        # are platform-owned, so map the trailing ordinal to the
                        # normalized block created above.
                        ordinal_match = re.search(r"(\d+)$", provider_after)
                        ordinal = int(ordinal_match.group(1)) if ordinal_match else 0
                        if 1 <= ordinal <= len(notes):
                            normalized_after = notes[ordinal - 1].block_id
                        elif len(notes) == 1:
                            normalized_after = notes[0].block_id
                    # Provider-owned ids are advisory.  Never carry an
                    # unverified id into the domain model: validation would
                    # reject an otherwise complete deck and trigger a second
                    # full generation.  If the provider id cannot be mapped,
                    # anchor the interaction after the last valid note (or
                    # leave it unanchored when this slide has no notes).
                    anchor_data["after_block_id"] = (
                        normalized_after
                        or (notes[-1].block_id if notes else None)
                    )
                anchors.append(InteractionAnchor.model_validate(anchor_data))
            misconceptions = []
            for misconception in item.get("expected_misconceptions") or []:
                misconception_data = dict(misconception)
                misconception_data["misconception_id"] = misconception_data.get("misconception_id") or f"{slide_id}:misconception_{len(misconceptions)+1:03d}"
                misconception_data["correction_strategy"] = misconception_data.get("correction_strategy") or misconception_data.get("recommended_correction") or ""
                misconceptions.append(ExpectedMisconception.model_validate(misconception_data))
            ppt_data = dict(item.get("ppt_content") or {})
            ppt_data["bullets"] = self._normalize_text_list(ppt_data.get("bullets"))
            ppt_data["examples"] = self._normalize_text_list(ppt_data.get("examples"))
            ppt_data["code_blocks"] = self._normalize_code_blocks(ppt_data.get("code_blocks"))
            slides.append(LessonSlide(
                    slide_id=slide_id, order=idx, title=str(item.get("title") or f"第 {idx} 页"),
                purpose=str(item.get("purpose") or ""), learning_objectives=item.get("learning_objectives") or objectives,
                knowledge_points=item.get("knowledge_points") or points, estimated_minutes=float(item.get("estimated_minutes") or 1),
                ppt_content=PptContent.model_validate(ppt_data), speaker_notes=notes,
                interaction_anchors=anchors, expected_misconceptions=misconceptions,
            ))
        return LessonVersion(lesson_id=f"lesson:{run_id}", run_id=run_id, version_number=1, title=str(payload.get("title") or context["title"]), learning_objectives=objectives, knowledge_points=points, estimated_minutes=int(context["estimated_minutes"]), slides=slides)

    @staticmethod
    def _normalize_text_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)] if str(value).strip() else []

    @staticmethod
    def _normalize_code_blocks(value: Any) -> list[dict[str, Any]]:
        """Accept provider shorthand while keeping the domain schema strict."""
        if value is None:
            return []
        raw_blocks = value if isinstance(value, list) else [value]
        normalized: list[dict[str, Any]] = []
        for block in raw_blocks:
            if isinstance(block, dict):
                normalized.append(dict(block))
            elif isinstance(block, str) and block.strip():
                normalized.append({"code": block})
            elif block is not None:
                normalized.append({"code": str(block)})
        return normalized

    @staticmethod
    def _parse_structured(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        text = str(raw).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as original_error:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise original_error
            candidate = text[start:end + 1]
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                # Repair syntax only. Pydantic and the domain validation below
                # remain the authoritative content and referential gate.
                parsed = repair_json(candidate, return_objects=True)
        if not isinstance(parsed, dict):
            raise BlueprintValidationError("structured output must be a JSON object")
        return parsed
