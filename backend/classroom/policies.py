"""Deterministic interaction and virtual-time policies."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from .models import LessonSlide, SpeakerNoteBlock, StudentPersona


@dataclass(frozen=True, slots=True)
class InteractionPolicy:
    max_interactions_per_slide: int = 6
    max_followup_depth: int = 2
    max_turns_per_slide: int = 10
    max_student_questions_per_slide: int = 1

    def allow_followup(self, followup_depth: int, turns: int) -> bool:
        return followup_depth < self.max_followup_depth and turns < self.max_turns_per_slide

    def choose_student(self, scenario_seed: str, slide_id: str, students: list[StudentPersona], *, interaction_index: int = 0, target_level: str | None = None) -> StudentPersona | None:
        candidates = [
            student
            for student in students
            if target_level in (None, "all")
            or student.level == target_level
            or student.student_id == target_level
        ] or students
        if not candidates:
            return None
        digest = hashlib.sha256(f"{scenario_seed}:{slide_id}:{interaction_index}".encode()).digest()
        return sorted(candidates, key=lambda s: s.student_id)[digest[0] % len(candidates)]

    def should_trigger_question(self, scenario_seed: str, slide: LessonSlide, anchor_index: int, *, interaction_count: int, student_question_count: int) -> bool:
        """Decide whether a planned teacher interaction anchor is used.

        A slide with valid anchors always receives at least one observable
        understanding check. Additional anchors remain deterministic for the
        same scenario seed so lesson versions can be compared fairly.
        """
        if interaction_count >= self.max_interactions_per_slide:
            return False
        if anchor_index >= len(slide.interaction_anchors):
            return False
        anchor = slide.interaction_anchors[anchor_index]
        if anchor.priority <= 0:
            return False
        if interaction_count == 0:
            return True
        digest = hashlib.sha256(f"{scenario_seed}:{slide.slide_id}:{anchor_index}:student-question".encode()).digest()
        threshold = min(90, 35 + anchor.priority * 15)
        return digest[0] % 100 < threshold


class VirtualTimePolicy:
    def __init__(self, chars_per_second: float = 8.0, question_seconds: int = 8, answer_seconds: int = 12, feedback_seconds: int = 10):
        self.chars_per_second = chars_per_second
        self.question_seconds = question_seconds
        self.answer_seconds = answer_seconds
        self.feedback_seconds = feedback_seconds

    def for_block(self, block: SpeakerNoteBlock) -> int:
        return block.estimated_seconds

    def for_event(self, event_kind: str, content: str = "") -> int:
        if event_kind.endswith("question"):
            return self.question_seconds
        if event_kind.endswith("answer") or event_kind.endswith("clarification") or event_kind.endswith("silence"):
            return self.answer_seconds
        if event_kind.endswith("feedback") or event_kind.endswith("followup"):
            return self.feedback_seconds
        return max(1, round(len(content) / self.chars_per_second))
