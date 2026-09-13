"""Draft-only PPT review and Teacher-Agent refinement service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .lesson_blueprint import BlueprintValidationError, LessonBlueprintService
from .models import (
    ExpectedMisconception,
    InteractionAnchor,
    LessonReviewMessage,
    LessonSlide,
    LessonVersion,
    PptContent,
    SpeakerNoteBlock,
)
from .prompts import build_lesson_slide_review_prompt
from .repository import ClassroomRepository


class LessonReviewService:
    def __init__(self, repository: ClassroomRepository) -> None:
        self.repository = repository

    async def replace_draft(self, current: LessonVersion, slides: list[LessonSlide], *, title: str | None = None, estimated_minutes: int | None = None) -> LessonVersion:
        if current.status != "draft":
            raise ValueError("only a draft lesson version can be edited")
        normalized = self._normalize_slides(slides)
        updated = current.model_copy(update={
            "title": (title or current.title).strip(),
            "slides": normalized,
            "estimated_minutes": estimated_minutes or current.estimated_minutes,
            "updated_at": datetime.now(timezone.utc),
        })
        self.validate_for_review(updated)
        return await self.repository.replace_draft_lesson_version(updated)

    async def revise_slide(self, current: LessonVersion, slide_id: str, instruction: str, workflow_service: Any) -> tuple[LessonVersion, LessonReviewMessage]:
        if current.status != "draft":
            raise ValueError("only a draft lesson version can be revised")
        slide = next((item for item in current.slides if item.slide_id == slide_id), None)
        if slide is None:
            raise LookupError("lesson slide not found")
        user_message = LessonReviewMessage(
            run_id=current.run_id, version_id=current.id, slide_id=slide_id,
            role="user", content=instruction.strip(),
        )
        await self.repository.append_lesson_review_message(user_message)
        await self._append_process_message(
            current,
            slide_id,
            "已收到你的修改意见，正在读取当前页 PPT、教师讲稿和互动锚点。",
        )
        await self._append_process_message(
            current,
            slide_id,
            self._understanding_summary(slide, instruction),
        )
        await self._append_process_message(
            current,
            slide_id,
            "正在检查本次修改是否需要同步讲稿、互动锚点或预期误区；其他页面将保持不变。",
        )
        history = await self.repository.list_lesson_review_messages(current.run_id, current.id)
        system, user = build_lesson_slide_review_prompt({
            "lesson": {"title": current.title, "learning_objectives": current.learning_objectives, "knowledge_points": current.knowledge_points},
            "slide": slide.model_dump(mode="json"),
            # Runtime progress messages are for the UI, not model memory.
            "recent_review_messages": [
                item.model_dump(mode="json")
                for item in history
                if item.role in {"user", "teacher"}
            ][-12:],
            "instruction": instruction.strip(),
        })
        try:
            if workflow_service.model.is_mock:
                await self._append_process_message(
                    current,
                    slide_id,
                    "当前使用 Mock Provider，正在生成可验证的结构化修改草案。",
                )
                payload = self._mock_revision(slide, instruction)
                revised = self._merge_slide(slide, payload, current.knowledge_points)
            else:
                session_id = f"{current.run_id}:preparation:teacher"
                await self._append_process_message(
                    current,
                    slide_id,
                    f"正在调用 Teacher Agent 的 DSH Session：{session_id}。",
                )
                payload = {}
                revised = slide
                for attempt in range(2):
                    attempt_user = user
                    if attempt:
                        await self._append_process_message(
                            current,
                            slide_id,
                            "第一次结构化结果没有产生可见页面变化，正在要求 Teacher Agent 补充具体字段修改。",
                        )
                        attempt_user += (
                            "\n上一次响应没有改变当前页的任何可见教学内容。"
                            "这一次必须按用户意见实际修改 title、purpose、ppt_content、"
                            "speaker_notes、interaction_anchors 或 expected_misconceptions 中至少一项；"
                            "不要只返回 summary。仍只输出完整 JSON 对象。"
                        )
                    if workflow_service.model.provider == "dsh":
                        raw = await workflow_service.model.ensure_dsh_engine().generate_in_session(
                            session_id, system, attempt_user
                        )
                    else:
                        raw = await workflow_service.model.generate(system, attempt_user)
                    await self._append_process_message(
                        current,
                        slide_id,
                        "已收到 Teacher Agent 的结构化草案，正在校验 JSON、稳定 ID 和当前页引用。",
                    )
                    payload = LessonBlueprintService._parse_structured(raw)
                    revised = self._merge_slide(slide, payload, current.knowledge_points)
                    if self._revision_signature(revised) != self._revision_signature(slide):
                        break
                else:
                    # A provider may return a plausible summary without changing
                    # the structured slide. For explicit, machine-identifiable
                    # editing requests, apply a minimal local patch so the user's
                    # requested field is still changed and remains reviewable.
                    fallback = self._instruction_fallback(slide, instruction)
                    if fallback is None:
                        await self._append_process_message(
                            current,
                            slide_id,
                            "Teacher Agent 的两次结构化结果都没有产生可验证修改，当前页面保持不变。",
                        )
                        raise BlueprintValidationError(
                            "Teacher Agent 未产生可验证的页面修改，请补充更具体的修改意见后重试"
                        )
                    await self._append_process_message(
                        current,
                        slide_id,
                        "模型结果未形成可验证差异，已根据你的明确动词生成最小可审阅补丁。",
                    )
                    payload = fallback
                    revised = self._merge_slide(slide, fallback, current.knowledge_points)
        except Exception as exc:
            await self._append_process_message(
                current,
                slide_id,
                f"本次修改未写入页面：{type(exc).__name__}。你可以补充意见后重试。",
            )
            raise
        await self._append_process_message(
            current,
            slide_id,
            "结构化修改已通过校验，正在只写入当前页并保留其他页面。",
        )
        slides = [revised if item.slide_id == slide_id else item for item in current.slides]
        updated = await self.replace_draft(current, slides)
        assistant = LessonReviewMessage(
            run_id=current.run_id, version_id=current.id, slide_id=slide_id,
            role="teacher",
            content=str(payload.get("summary") or f"已完成 {slide_id} 的局部修改，其他页面保持不变。"),
        )
        await self.repository.append_lesson_review_message(assistant)
        return updated, assistant

    async def _append_process_message(
        self,
        current: LessonVersion,
        slide_id: str,
        content: str,
    ) -> None:
        """Persist concise operational progress, never hidden chain-of-thought."""
        await self.repository.append_lesson_review_message(
            LessonReviewMessage(
                run_id=current.run_id,
                version_id=current.id,
                slide_id=slide_id,
                role="system",
                content=content,
            )
        )

    @staticmethod
    def _understanding_summary(slide: LessonSlide, instruction: str) -> str:
        text = instruction.strip()
        targets: list[str] = []
        if any(word in text for word in ("精简", "减少", "删减", "要点")):
            targets.append("PPT 要点")
        if any(word in text for word in ("案例", "例子", "场景")):
            targets.append("应用案例")
        if any(word in text for word in ("讲稿", "讲解", "教师")):
            targets.append("教师讲稿")
        if any(word in text for word in ("互动", "提问", "问题")):
            targets.append("互动锚点")
        if any(word in text for word in ("误区", "易错", "纠错")):
            targets.append("预期误区")
        target_text = "、".join(targets) if targets else "当前页可见教学内容"
        return (
            f"结构化理解：目标页面={slide.slide_id}《{slide.title}》；"
            f"修改范围={target_text}；联动规则=必要时同步讲稿与互动设置；"
            "保护规则=不改其他页面、不改变稳定 slide_id/block_id。"
        )

    def validate_for_review(self, lesson: LessonVersion) -> None:
        if not lesson.slides:
            raise BlueprintValidationError("PPT 至少需要一页")
        if not lesson.learning_objectives:
            raise BlueprintValidationError("学习目标不能为空")
        ids = [slide.slide_id for slide in lesson.slides]
        if len(ids) != len(set(ids)):
            raise BlueprintValidationError("slide_id 必须唯一")
        for index, slide in enumerate(lesson.slides, start=1):
            if slide.order != index:
                raise BlueprintValidationError("页面顺序必须连续")
            if not slide.title.strip() or not slide.ppt_content.title.strip():
                raise BlueprintValidationError(f"第 {index} 页标题不能为空")
            if not slide.ppt_content.bullets:
                raise BlueprintValidationError(f"第 {index} 页至少需要一个内容要点")
            if not slide.speaker_notes:
                raise BlueprintValidationError(f"第 {index} 页至少需要一个教师讲稿 Block")
            block_ids = [block.block_id for block in slide.speaker_notes]
            if len(block_ids) != len(set(block_ids)):
                raise BlueprintValidationError(f"第 {index} 页 block_id 必须唯一")
            for block in slide.speaker_notes:
                unknown = set(block.knowledge_point_ids) - set(lesson.knowledge_points)
                if unknown:
                    raise BlueprintValidationError(f"第 {index} 页讲稿引用了无效知识点：{', '.join(sorted(unknown))}")
            for anchor in slide.interaction_anchors:
                if anchor.after_block_id and anchor.after_block_id not in block_ids:
                    raise BlueprintValidationError(
                        f"第 {index} 页互动锚点 {anchor.interaction_id} 引用了不存在的讲稿 Block"
                    )
                unknown = set(anchor.knowledge_point_ids) - set(lesson.knowledge_points)
                if unknown:
                    raise BlueprintValidationError(f"第 {index} 页互动锚点引用了无效知识点：{', '.join(sorted(unknown))}")
            for misconception in slide.expected_misconceptions:
                if misconception.knowledge_point_id and misconception.knowledge_point_id not in lesson.knowledge_points:
                    raise BlueprintValidationError(f"第 {index} 页预期误区引用了无效知识点")

    def validate_for_approval(self, lesson: LessonVersion) -> None:
        self.validate_for_review(lesson)
        note_seconds = sum(block.estimated_seconds for slide in lesson.slides for block in slide.speaker_notes)
        if note_seconds <= 0:
            raise BlueprintValidationError("教师讲稿时间不能为空")

    @staticmethod
    def _normalize_slides(slides: list[LessonSlide]) -> list[LessonSlide]:
        normalized: list[LessonSlide] = []
        seen: set[str] = set()
        next_custom = 1
        for index, slide in enumerate(slides, start=1):
            slide_id = slide.slide_id.strip()
            if not slide_id or slide_id in seen:
                while f"slide_custom_{next_custom:03d}" in seen:
                    next_custom += 1
                slide_id = f"slide_custom_{next_custom:03d}"
                next_custom += 1
            seen.add(slide_id)
            blocks = []
            block_seen: set[str] = set()
            for block_index, block in enumerate(slide.speaker_notes, start=1):
                block_id = block.block_id.strip()
                if not block_id or block_id in block_seen:
                    block_id = f"{slide_id}:block_{block_index:03d}"
                block_seen.add(block_id)
                blocks.append(block.model_copy(update={"block_id": block_id, "order": block_index}))
            normalized.append(slide.model_copy(update={"slide_id": slide_id, "order": index, "speaker_notes": blocks}))
        return normalized

    @staticmethod
    def _merge_slide(slide: LessonSlide, payload: dict[str, Any], valid_points: list[str]) -> LessonSlide:
        ppt = PptContent.model_validate(payload.get("ppt_content") or slide.ppt_content.model_dump(mode="json"))
        notes: list[SpeakerNoteBlock] = []
        for index, raw in enumerate(payload.get("speaker_notes") or [item.model_dump(mode="json") for item in slide.speaker_notes], start=1):
            data = dict(raw)
            previous = slide.speaker_notes[index - 1] if index <= len(slide.speaker_notes) else None
            data.update({
                "block_id": previous.block_id if previous else f"{slide.slide_id}:block_{index:03d}",
                "order": index,
                "knowledge_point_ids": [item for item in data.get("knowledge_point_ids", []) if item in valid_points],
            })
            if previous:
                data["id"] = previous.id
            elif not data.get("id"):
                data.pop("id", None)
            notes.append(SpeakerNoteBlock.model_validate(data))
        block_ids = {item.block_id for item in notes}
        raw_anchors = payload.get("interaction_anchors")
        anchors: list[InteractionAnchor] = []
        if raw_anchors is None:
            anchors = slide.interaction_anchors
        else:
            for index, raw in enumerate(raw_anchors, start=1):
                data = dict(raw)
                previous = slide.interaction_anchors[index - 1] if index <= len(slide.interaction_anchors) else None
                data["interaction_id"] = (
                    previous.interaction_id
                    if previous
                    else f"{slide.slide_id}:interaction_{index:03d}"
                )
                if previous:
                    data["id"] = previous.id
                else:
                    data.pop("id", None)
                interaction_type = data.pop("interaction_type", None)
                data["type"] = LessonReviewService._normalize_interaction_type(
                    data.get("type") or interaction_type
                )
                data["target_student_level"] = LessonReviewService._normalize_student_level(
                    data.get("target_student_level")
                )
                data["knowledge_point_ids"] = [
                    item for item in data.get("knowledge_point_ids", []) if item in valid_points
                ]
                requested_block = data.get("after_block_id")
                if requested_block not in block_ids:
                    data["after_block_id"] = (
                        previous.after_block_id
                        if previous and previous.after_block_id in block_ids
                        else None
                    )
                anchors.append(InteractionAnchor.model_validate(data))

        raw_misconceptions = payload.get("expected_misconceptions")
        misconceptions: list[ExpectedMisconception] = []
        if raw_misconceptions is None:
            misconceptions = slide.expected_misconceptions
        else:
            for index, raw in enumerate(raw_misconceptions, start=1):
                data = dict(raw)
                previous = (
                    slide.expected_misconceptions[index - 1]
                    if index <= len(slide.expected_misconceptions)
                    else None
                )
                data["misconception_id"] = (
                    previous.misconception_id
                    if previous
                    else f"{slide.slide_id}:misconception_{index:03d}"
                )
                point_id = data.get("knowledge_point_id")
                data["knowledge_point_id"] = point_id if point_id in valid_points else None
                correction = data.get("correction_strategy") or data.get("recommended_correction")
                if correction:
                    data["correction_strategy"] = correction
                    data.setdefault("recommended_correction", correction)
                misconceptions.append(ExpectedMisconception.model_validate(data))
        return slide.model_copy(update={
            "title": str(payload.get("title") or slide.title).strip(),
            "purpose": str(payload.get("purpose") or slide.purpose).strip(),
            "ppt_content": ppt,
            "speaker_notes": notes,
            "interaction_anchors": anchors,
            "expected_misconceptions": misconceptions,
        })

    @staticmethod
    def _revision_signature(slide: LessonSlide) -> dict[str, Any]:
        return {
            "title": slide.title,
            "purpose": slide.purpose,
            "ppt_content": slide.ppt_content.model_dump(mode="json"),
            "speaker_notes": [
                {
                    "block_type": item.block_type,
                    "content": item.content,
                    "estimated_seconds": item.estimated_seconds,
                    "knowledge_point_ids": item.knowledge_point_ids,
                }
                for item in slide.speaker_notes
            ],
            "interaction_anchors": [
                {
                    "type": item.type,
                    "objective": item.objective,
                    "planned_question": item.planned_question,
                    "target_student_level": item.target_student_level,
                    "max_questions": item.max_questions,
                    "after_block_id": item.after_block_id,
                    "knowledge_point_ids": item.knowledge_point_ids,
                    "priority": item.priority,
                }
                for item in slide.interaction_anchors
            ],
            "expected_misconceptions": [
                {
                    "description": item.description,
                    "correction_strategy": item.correction_strategy,
                    "knowledge_point_id": item.knowledge_point_id,
                    "observable_signals": item.observable_signals,
                    "recommended_correction": item.recommended_correction,
                }
                for item in slide.expected_misconceptions
            ],
        }

    @staticmethod
    def _instruction_fallback(slide: LessonSlide, instruction: str) -> dict[str, Any] | None:
        """Turn explicit editing verbs into a small, transparent slide patch.

        This is deliberately narrow: vague requests still fail rather than
        silently inventing a lesson change. It protects the review flow when a
        provider emits only a summary or an unchanged JSON object.
        """
        text = instruction.strip()
        if not text:
            return None
        lowered = text.lower()
        action_words = (
            "精简", "减少", "删减", "补充", "增加", "添加", "案例", "例子", "场景",
            "互动", "提问", "讲稿", "讲解", "要点", "误区", "完善", "优化",
        )
        if not any(word in text or word in lowered for word in action_words):
            return None
        ppt = slide.ppt_content.model_dump(mode="json")
        interaction_anchors = [item.model_dump(mode="json") for item in slide.interaction_anchors]
        changed = False
        if any(word in text for word in ("精简", "减少", "删减")):
            bullets = list(ppt.get("bullets") or [])
            compacted = bullets[: max(1, min(3, len(bullets)))]
            if compacted != bullets:
                ppt["bullets"] = compacted
                changed = True
        if any(word in text for word in ("案例", "例子", "场景")):
            examples = list(ppt.get("examples") or [])
            example = f"课堂应用案例：围绕“{slide.title}”设计一个可观察任务，让学生先预测、再操作并说明判断依据。"
            if example not in examples:
                examples.append(example)
                ppt["examples"] = examples
                changed = True
        if any(word in text for word in ("互动", "提问")):
            if not interaction_anchors:
                interaction_anchors.append({
                    "interaction_id": f"{slide.slide_id}:interaction_001",
                    "type": "check",
                    "objective": f"检查学生对{slide.title}的理解",
                    "planned_question": f"请结合一个具体任务说明“{slide.title}”的判断依据。",
                    "target_student_level": "all",
                    "after_block_id": slide.speaker_notes[-1].block_id if slide.speaker_notes else None,
                    "knowledge_point_ids": slide.knowledge_points,
                    "priority": 1,
                })
                changed = True
        if any(word in text for word in ("讲稿", "讲解")) and slide.speaker_notes:
            notes = [item.model_dump(mode="json") for item in slide.speaker_notes]
            notes[0]["content"] = f"{notes[0].get('content', '').rstrip()}\n补充说明：{text}"
            return {
                "title": slide.title,
                "purpose": slide.purpose,
                "ppt_content": ppt,
                "speaker_notes": notes,
                "interaction_anchors": interaction_anchors,
                "expected_misconceptions": [item.model_dump(mode="json") for item in slide.expected_misconceptions],
                "summary": f"已按意见修改 {slide.slide_id} 的讲稿内容，其他页面保持不变。",
            }
        if not changed:
            # “完善/优化要点” is still a concrete request, but must leave a
            # visible, reviewable trace rather than pretending a change occurred.
            if any(word in text for word in ("完善", "优化", "要点")):
                ppt["subtitle"] = f"按教师意见完善：{text[:50]}"
                changed = True
        if not changed:
            return None
        return {
            "title": slide.title,
            "purpose": slide.purpose,
            "ppt_content": ppt,
            "speaker_notes": [item.model_dump(mode="json") for item in slide.speaker_notes],
            "interaction_anchors": interaction_anchors,
            "expected_misconceptions": [item.model_dump(mode="json") for item in slide.expected_misconceptions],
            "summary": f"已按意见完成 {slide.slide_id} 的局部修改，其他页面保持不变。",
        }

    @staticmethod
    def _normalize_interaction_type(value: Any) -> str:
        raw = str(value or "question").lower()
        aliases = {
            "check_understanding": "check",
            "concept_question": "question",
            "application_question": "practice",
            "prediction": "question",
        }
        normalized = aliases.get(raw, raw)
        return normalized if normalized in {"question", "check", "discussion", "practice", "reflection", "other"} else "other"

    @staticmethod
    def _normalize_student_level(value: Any) -> str:
        raw = str(value or "all").lower()
        normalized = {"advanced": "high", "intermediate": "medium", "basic": "low", "beginner": "low"}.get(raw, raw)
        return normalized if normalized in {"high", "medium", "low", "all"} else "all"

    @staticmethod
    def _mock_revision(slide: LessonSlide, instruction: str) -> dict[str, Any]:
        ppt = slide.ppt_content.model_dump(mode="json")
        if "精简" in instruction:
            ppt["bullets"] = ppt.get("bullets", [])[:3]
        elif any(word in instruction for word in ("案例", "例子", "场景")):
            ppt["examples"] = [*ppt.get("examples", []), f"围绕“{slide.title}”补充的课堂应用案例"]
        else:
            ppt["subtitle"] = instruction[:60]
        return {"title": slide.title, "purpose": slide.purpose, "ppt_content": ppt, "speaker_notes": [item.model_dump(mode="json") for item in slide.speaker_notes], "summary": f"已按意见完善 {slide.slide_id}，其他页面保持不变。"}
