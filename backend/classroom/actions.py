"""Structured actions returned by classroom agents."""
from enum import Enum
from typing import Any
from pydantic import Field
from .models import DomainModel


class TeacherActionType(str, Enum):
    EXPLAIN = "EXPLAIN"
    ASK_QUESTION = "ASK_QUESTION"
    FOLLOW_UP = "FOLLOW_UP"
    FEEDBACK = "FEEDBACK"
    ANSWER_STUDENT = "ANSWER_STUDENT"
    SUMMARIZE = "SUMMARIZE"


class StudentActionType(str, Enum):
    ANSWER = "ANSWER"
    QUESTION = "QUESTION"
    CLARIFICATION = "CLARIFICATION"
    SILENCE = "SILENCE"


class FeedbackEvaluation(DomainModel):
    quality: str
    misconception_tags: list[str] = Field(default_factory=list)
    resolved_misconception_tags: list[str] = Field(default_factory=list)


class TeacherAction(DomainModel):
    action_type: TeacherActionType
    speech: str = ""
    target_student_id: str | None = None
    reply_to_event_id: str | None = None
    knowledge_point_ids: list[str] = Field(default_factory=list)
    feedback_evaluation: FeedbackEvaluation | None = None


class StudentAction(DomainModel):
    action_type: StudentActionType
    content: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    misconception_tags: list[str] = Field(default_factory=list)
    reply_to_event_id: str | None = None

