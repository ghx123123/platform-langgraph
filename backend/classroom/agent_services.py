"""Teacher and Student agent boundaries.

Services own prompt/context construction and structured-action validation;
the runtime remains unaware of classroom domain objects.
"""
from __future__ import annotations
import json
import re
from typing import Any
from .actions import TeacherAction, StudentAction, TeacherActionType, StudentActionType
from .agent_runtime import HarnessAgentRuntime
from .models import ClassroomEvent, LessonSlide, SpeakerNoteBlock, StudentCognitiveState, StudentPersona


class TeacherAgentService:
    def __init__(self, runtime: HarnessAgentRuntime, repository=None):
        self.runtime, self.repository = runtime, repository

    async def act(self, run_id: str, round_number: int, slide: LessonSlide, block: SpeakerNoteBlock | None, recent_events: list[ClassroomEvent], *, prompt_context: dict[str, Any] | None = None) -> TeacherAction:
        context = {"slide": slide.model_dump(mode="json"), "block": block.model_dump(mode="json") if block else None, "recent_events": [e.model_dump(mode="json") for e in recent_events[-6:]], "context": prompt_context or {}}
        system = (
            "You are a teacher executing exactly one classroom action from the current lesson blueprint. "
            "Return one JSON object only. Allowed action_type values are EXPLAIN, ASK_QUESTION, "
            "FOLLOW_UP, FEEDBACK, ANSWER_STUDENT, SUMMARIZE. Allowed keys are action_type, speech, "
            "target_student_id, reply_to_event_id, knowledge_point_ids, feedback_evaluation. "
            "Do not return next_action, next_block_id, block_id, estimated_seconds, workflow control, "
            "markdown, or hidden reasoning. Do not switch slides or end the round."
        )
        required_action = str((prompt_context or {}).get("required_action_type") or "").strip().upper()
        if required_action:
            system += (
                f" The ClassroomOrchestrator has selected this turn as {required_action}; "
                f"action_type must be {required_action}. Generate the concrete classroom wording only."
            )
        if self.repository:
            instance = await self.repository.get_agent_instance(run_id, 'teacher')
            if instance:
                context['role_settings'] = instance.config.get('role_profile', {})
                profile = context['role_settings']
                system += f"\nRole personality and behavior guidance for this course: {json.dumps(profile, ensure_ascii=False)}. Follow it when choosing wording and teaching style; never let it alter the orchestrator contract."
        user = json.dumps(context, ensure_ascii=False)
        for attempt in range(2):
            try:
                raw = await self.runtime.generate(run_id, round_number, "teacher", system, user)
                data = _normalize_teacher_action(_parse_json(raw), block)
                return TeacherAction.model_validate(data)
            except Exception:
                if attempt == 1: raise
                user += (
                    "\nYour previous response did not match TeacherAction. Return only one JSON object "
                    "using the allowed uppercase action_type and allowed keys."
                )
        raise RuntimeError("unreachable")


class StudentAgentService:
    def __init__(self, runtime: HarnessAgentRuntime, repository=None):
        self.runtime, self.repository = runtime, repository

    async def listen(self, run_id, round_number, persona, cognitive_state, current_content, recent_events, *, prompt_context=None):
        return await self.act(run_id, round_number, persona, cognitive_state, current_content,
            recent_events, prompt_context={**(prompt_context or {}), 'mode': 'listening',
            'expected_action': 'QUESTION or SILENCE',
            'instruction': 'Decide whether you genuinely have a question about what was just taught. '
            'Use your prior knowledge, misconceptions and current cognitive state. '
            'Do not invent a question to increase interaction. SILENCE means continue listening, not failure. '
            'Ask briefly in your own student voice; do not behave like a teaching expert.'})

    async def act(self, run_id: str, round_number: int, persona: StudentPersona, cognitive_state: list[StudentCognitiveState], current_content: str, recent_events: list[ClassroomEvent], *, prompt_context: dict[str, Any] | None = None) -> StudentAction:
        safe_context = {"persona": persona.model_dump(mode="json"), "cognitive_state": [s.model_dump(mode="json") for s in cognitive_state], "current_content": current_content, "recent_events": [e.model_dump(mode="json") for e in recent_events[-4:]], "context": prompt_context or {}}
        system = (
            "You are one student. Return one JSON StudentAction object only. Allowed action_type values "
            "are ANSWER, QUESTION, CLARIFICATION, SILENCE. Allowed keys are action_type, content, "
            "confidence, knowledge_point_ids, misconception_tags, reply_to_event_id. Never return workflow "
            "control or hidden reasoning, and never reveal hidden answers, future slides, supervisor or "
            "revision information."
        )
        expected_action = str((prompt_context or {}).get("expected_action") or "").strip().upper()
        if expected_action:
            system += (
                f" The ClassroomOrchestrator expects {expected_action} for this turn. "
                "Stay consistent with the persona and use SILENCE when the student cannot respond."
            )
        if self.repository:
            instance = await self.repository.get_agent_instance(run_id, f'student:{persona.level}')
            if instance:
                safe_context['role_settings'] = instance.config.get('role_profile', {})
                profile = safe_context['role_settings']
                system += f"\nRole personality and behavior guidance for this course: {json.dumps(profile, ensure_ascii=False)}. Follow it when deciding whether and what to say, while obeying the orchestrator's allowed action and visibility rules."
        user = json.dumps(safe_context, ensure_ascii=False)
        for attempt in range(2):
            try:
                raw = await self.runtime.generate(run_id, round_number, f"student:{persona.level}", system, user)
                data = _normalize_student_action(_parse_json(raw))
                return StudentAction.model_validate(data)
            except Exception:
                if attempt == 1:
                    return StudentAction(action_type=StudentActionType.SILENCE, content="", confidence=0, reply_to_event_id=recent_events[-1].event_id if recent_events else None)
                user += "\nReturn valid JSON StudentAction; if unsure use SILENCE."
        return StudentAction(action_type=StudentActionType.SILENCE)


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    return json.loads(text)


def _normalize_teacher_action(data: Any, block: SpeakerNoteBlock | None) -> Any:
    """Normalize known provider aliases at the runtime boundary.

    The domain model remains strict. This adapter only accepts a closed set of
    legacy action names and drops runtime-planning fields that agents are not
    allowed to control.
    """
    if not isinstance(data, dict):
        return data
    result = dict(data)
    raw_action = str(result.get("action_type") or result.get("action") or "").strip().upper()
    aliases = {
        "SPEAK": "SUMMARIZE" if block and block.block_type == "summary" else "EXPLAIN",
        "EXPLANATION": "EXPLAIN",
        "QUESTION": "ASK_QUESTION",
        "ASK": "ASK_QUESTION",
        "FOLLOWUP": "FOLLOW_UP",
        "ANSWER": "ANSWER_STUDENT",
        "SUMMARY": "SUMMARIZE",
    }
    result["action_type"] = aliases.get(raw_action, raw_action)
    if "speech" not in result:
        result["speech"] = result.get("content") or result.get("message") or ""
    feedback = result.get("feedback_evaluation")
    if isinstance(feedback, str):
        quality_aliases = {
            "RIGHT": "CORRECT",
            "CORRECT": "CORRECT",
            "PARTIALLY_CORRECT": "PARTIAL",
            "PARTIAL": "PARTIAL",
            "WRONG": "INCORRECT",
            "INCORRECT": "INCORRECT",
            "UNKNOWN": "UNKNOWN",
        }
        result["feedback_evaluation"] = {
            "quality": quality_aliases.get(feedback.strip().upper(), "UNKNOWN"),
        }
    allowed = {
        "action_type", "speech", "target_student_id", "reply_to_event_id",
        "knowledge_point_ids", "feedback_evaluation",
    }
    return {key: value for key, value in result.items() if key in allowed}


def _normalize_student_action(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    result = dict(data)
    raw_action = str(result.get("action_type") or result.get("action") or "").strip().upper()
    aliases = {
        "RESPOND": "ANSWER", "RESPONSE": "ANSWER", "ASK": "QUESTION",
        "CLARIFY": "CLARIFICATION", "NO_ANSWER": "SILENCE", "SILENT": "SILENCE",
    }
    result["action_type"] = aliases.get(raw_action, raw_action)
    if "content" not in result:
        result["content"] = result.get("speech") or result.get("message") or ""
    allowed = {
        "action_type", "content", "confidence", "knowledge_point_ids",
        "misconception_tags", "reply_to_event_id",
    }
    return {key: value for key, value in result.items() if key in allowed}
