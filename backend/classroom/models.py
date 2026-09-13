"""Pydantic domain contracts for the classroom_v2 data model.

These models are deliberately free of LangGraph and DSH types.  They describe
business facts which remain valid when an agent runtime or workflow engine is
replaced.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _non_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be empty")
    return value


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ClassroomEventType(str, Enum):
    ROUND_STARTED = "classroom.round.started"
    SLIDE_ENTERED = "classroom.slide.entered"
    TEACHER_EXPLANATION = "classroom.teacher.explanation"
    TEACHER_QUESTION = "classroom.teacher.question"
    TEACHER_FOLLOWUP = "classroom.teacher.followup"
    TEACHER_FEEDBACK = "classroom.teacher.feedback"
    TEACHER_ANSWER = "classroom.teacher.answer"
    TEACHER_SUMMARY = "classroom.teacher.summary"
    STUDENT_ANSWER = "classroom.student.answer"
    STUDENT_QUESTION = "classroom.student.question"
    STUDENT_CLARIFICATION = "classroom.student.clarification"
    STUDENT_SILENCE = "classroom.student.silence"
    USER_INTERVENTION = "classroom.user.intervention"
    SLIDE_COMPLETED = "classroom.slide.completed"
    ROUND_COMPLETED = "classroom.round.completed"
    EVALUATION_COMPLETED = "classroom.evaluation.completed"
    REVISION_COMPLETED = "classroom.revision.completed"
    AGENT_ERROR = "classroom.agent.error"
    ROUND_PAUSED = "classroom.round.paused"
    ROUND_RESUMED = "classroom.round.resumed"
    ROUND_STOPPED = "classroom.round.stopped"

    @classmethod
    def _missing_(cls, value: object):
        aliases = {
            "round.started": cls.ROUND_STARTED,
            "slide.entered": cls.SLIDE_ENTERED,
            "teacher.explanation": cls.TEACHER_EXPLANATION,
            "teacher.question": cls.TEACHER_QUESTION,
            "teacher.followup": cls.TEACHER_FOLLOWUP,
            "teacher.feedback": cls.TEACHER_FEEDBACK,
            "teacher.answer": cls.TEACHER_ANSWER,
            "teacher.summary": cls.TEACHER_SUMMARY,
            "student.answer": cls.STUDENT_ANSWER,
            "student.question": cls.STUDENT_QUESTION,
            "student.clarification": cls.STUDENT_CLARIFICATION,
            "student.silence": cls.STUDENT_SILENCE,
            "user.intervention": cls.USER_INTERVENTION,
            "slide.completed": cls.SLIDE_COMPLETED,
            "round.completed": cls.ROUND_COMPLETED,
            "evaluation.completed": cls.EVALUATION_COMPLETED,
            "revision.completed": cls.REVISION_COMPLETED,
            "agent.error": cls.AGENT_ERROR,
            "round.paused": cls.ROUND_PAUSED,
            "round.resumed": cls.ROUND_RESUMED,
            "round.stopped": cls.ROUND_STOPPED,
        }
        return aliases.get(value)


class PptContent(DomainModel):
    title: str = ""
    subtitle: str = ""
    bullets: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    code_blocks: list[dict[str, Any]] = Field(default_factory=list)
    visual_instruction: str = ""


class SpeakerNoteBlock(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    block_id: str
    order: int = Field(ge=1)
    block_type: Literal["explanation", "question", "example", "feedback", "summary", "transition", "other"] = "explanation"
    content: str
    estimated_seconds: int = Field(default=30, ge=1, le=3600)
    knowledge_point_ids: list[str] = Field(default_factory=list)

    @property
    def block_order(self) -> int:
        return self.order

    @model_validator(mode="before")
    @classmethod
    def accept_block_order_alias(cls, value: Any) -> Any:
        if isinstance(value, dict) and "order" not in value and "block_order" in value:
            value = dict(value)
            value["order"] = value.pop("block_order")
        return value

    _validate_block_id = field_validator("block_id")(_non_empty)


class InteractionAnchor(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    interaction_id: str
    type: Literal["question", "check", "discussion", "practice", "reflection", "other"] = "question"
    objective: str
    planned_question: str
    target_student_level: Literal["high", "medium", "low", "all"] = "all"
    max_questions: int = Field(default=1, ge=0, le=10)
    after_block_id: str | None = None
    knowledge_point_ids: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _validate_interaction_id = field_validator("interaction_id")(_non_empty)

    @property
    def interaction_type(self) -> str:
        return self.type

    @model_validator(mode="before")
    @classmethod
    def accept_interaction_type_alias(cls, value: Any) -> Any:
        if isinstance(value, dict) and "type" not in value and "interaction_type" in value:
            value = dict(value)
            value["type"] = value.pop("interaction_type")
        return value


class ExpectedMisconception(DomainModel):
    misconception_id: str
    description: str
    correction_strategy: str
    knowledge_point_id: str | None = None
    observable_signals: list[str] = Field(default_factory=list)
    recommended_correction: str | None = None

    _validate_misconception_id = field_validator("misconception_id")(_non_empty)


class LessonSlide(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    slide_id: str
    order: int = Field(ge=1)
    title: str
    purpose: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    estimated_minutes: float = Field(default=1, ge=0.25, le=180)
    ppt_content: PptContent = Field(default_factory=PptContent)
    speaker_notes: list[SpeakerNoteBlock] = Field(default_factory=list)
    interaction_anchors: list[InteractionAnchor] = Field(default_factory=list)
    expected_misconceptions: list[ExpectedMisconception] = Field(default_factory=list)

    _validate_slide_id = field_validator("slide_id")(_non_empty)


class LessonVersion(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lesson_id: str
    run_id: str
    version_number: int = Field(ge=1)
    source_version_id: str | None = None
    created_from_round_id: str | None = None
    title: str
    learning_objectives: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(default=45, ge=1, le=600)
    slides: list[LessonSlide] = Field(default_factory=list)
    status: Literal["draft", "ready", "in_simulation", "reviewed", "superseded", "final"] = "draft"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    _validate_lesson_id = field_validator("lesson_id", "run_id")(_non_empty)

    @property
    def version_id(self) -> str:
        """Stable public alias used by the blueprint contract."""
        return self.id

    @model_validator(mode="before")
    @classmethod
    def accept_version_id_alias(cls, value: Any) -> Any:
        if isinstance(value, dict) and "id" not in value and "version_id" in value:
            value = dict(value)
            value["id"] = value.pop("version_id")
        return value


class LessonReviewMessage(DomainModel):
    """Persisted preparation-stage conversation with the Teacher Agent."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    version_id: str
    slide_id: str | None = None
    role: Literal["user", "teacher", "system"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)

    _validate_review_ids = field_validator("run_id", "version_id", "content")(_non_empty)


class StudentPersona(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    student_id: str
    name: str
    level: Literal["high", "medium", "low"]
    ability: float = Field(ge=0, le=1)
    prior_knowledge: dict[str, Any] = Field(default_factory=dict)
    engagement: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    verbosity: float = Field(ge=0, le=1)
    question_propensity: float = Field(ge=0, le=1)
    answer_propensity: float = Field(ge=0, le=1)
    misconception_profile: dict[str, Any] = Field(default_factory=dict)
    scenario_seed: str
    created_at: datetime = Field(default_factory=utc_now)

    _validate_student_ids = field_validator("run_id", "student_id", "name", "scenario_seed")(_non_empty)


class StudentScenarioBaseline(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    student_id: str
    initial_mastery: dict[str, float] = Field(default_factory=dict)
    initial_confidence: dict[str, float] = Field(default_factory=dict)
    initial_misconceptions: dict[str, Any] = Field(default_factory=dict)
    prior_knowledge: dict[str, Any] = Field(default_factory=dict)
    scenario_seed: str
    created_at: datetime = Field(default_factory=utc_now)

    _validate_baseline_ids = field_validator("run_id", "student_id", "scenario_seed")(_non_empty)

    @field_validator("initial_mastery", "initial_confidence")
    @classmethod
    def validate_scores(cls, value: dict[str, float]) -> dict[str, float]:
        if any(score < 0 or score > 1 for score in value.values()):
            raise ValueError("mastery and confidence scores must be between 0 and 1")
        return value


class StudentCognitiveState(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    round_id: str
    student_id: str
    knowledge_point_id: str
    current_mastery: float = Field(ge=0, le=1)
    current_confidence: float = Field(ge=0, le=1)
    misconceptions: list[str] = Field(default_factory=list)
    resolved_misconceptions: list[str] = Field(default_factory=list)
    engagement_runtime: float = Field(default=0.5, ge=0, le=1)
    last_event_id: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    _validate_state_ids = field_validator("round_id", "student_id", "knowledge_point_id")(_non_empty)

    @property
    def mastery(self) -> float:
        return self.current_mastery

    @property
    def confidence(self) -> float:
        return self.current_confidence

    @model_validator(mode="before")
    @classmethod
    def accept_compact_state_names(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = dict(value)
            value.setdefault("current_mastery", value.pop("mastery", None))
            value.setdefault("current_confidence", value.pop("confidence", None))
        return value


class ClassroomAgentInstance(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    agent_key: str
    role: Literal["teacher", "student", "supervisor"]
    display_name: str
    student_id: str | None = None
    persona_id: str | None = None
    status: Literal["configured", "active", "paused", "completed", "failed"] = "configured"
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    _validate_agent_ids = field_validator("run_id", "agent_key", "display_name")(_non_empty)


class SimulationRound(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    round_number: int = Field(ge=1)
    lesson_version_id: str
    scenario_seed: str
    status: Literal["queued", "initializing", "running", "paused", "completed", "failed", "stopped"] = "queued"
    current_slide_id: str | None = None
    current_slide_index: int = Field(default=0, ge=0)
    virtual_elapsed_seconds: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    _validate_round_ids = field_validator("run_id", "lesson_version_id", "scenario_seed")(_non_empty)

    @property
    def round_id(self) -> str:
        return self.id

    @model_validator(mode="before")
    @classmethod
    def accept_round_id_alias(cls, value: Any) -> Any:
        if isinstance(value, dict) and "id" not in value and "round_id" in value:
            value = dict(value)
            value["id"] = value.pop("round_id")
        return value


class TeacherDirective(DomainModel):
    """教师在课堂演练中下达的指令。

    与一次性 USER_INTERVENTION 事件的区别: 指令有生命周期(生效中/已落实/被覆盖),
    会被注入后续 agent 的 prompt(约束继承), 且 intent=correct 时能产出 RevisionPatch。
    """

    directive_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    round_id: str
    slide_id: str | None = None
    source_event_id: str
    content: str
    intent: Literal["question", "correct", "require"] = "question"
    scope: Literal["slide", "round", "lesson"] = "round"
    # cancelled: 教师主动撤销（说错了 / 课堂不再需要这条约束），不会再注入后续 agent。
    status: Literal["active", "resolved", "superseded", "cancelled"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None

    _validate_directive_ids = field_validator("run_id", "round_id", "source_event_id", "content")(_non_empty)


class ClassroomState(DomainModel):
    run_id: str
    round_id: str
    phase: Literal[
        "round_initializing", "slide_enter", "teacher_act", "wait_student",
        "interaction_decision", "teacher_response", "student_initiated_question", "objective_check",
        "slide_complete", "round_complete", "paused", "stopped", "failed",
    ]
    current_slide_id: str | None = None
    current_slide_index: int = Field(default=0, ge=0)
    current_block_id: str | None = None
    active_agent_id: str | None = None
    turn_count: int = Field(default=0, ge=0)
    followup_depth: int = Field(default=0, ge=0)
    slide_interaction_count: int = Field(default=0, ge=0)
    student_question_count: int = Field(default=0, ge=0)
    virtual_elapsed_seconds: int = Field(default=0, ge=0)
    status: Literal["active", "paused", "completed", "stopped", "failed"] = "active"
    version: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utc_now)

    _validate_state_ids = field_validator("run_id", "round_id")(_non_empty)


class ClassroomEvent(DomainModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    round_id: str
    slide_id: str | None = None
    sequence: int = Field(default=0, ge=0, description="0 asks the repository to allocate the next sequence")
    actor_id: str
    actor_role: Literal["teacher", "student", "supervisor", "system", "user"]
    event_type: ClassroomEventType
    content: str = ""
    reply_to: str | None = None
    target_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    virtual_timestamp: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)

    _validate_event_ids = field_validator("run_id", "round_id", "actor_id")(_non_empty)


class SupervisorObservation(DomainModel):
    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    round_id: str
    slide_id: str
    event_ids: list[str] = Field(default_factory=list)
    category: Literal["accuracy", "objective", "clarity", "interaction", "questioning", "feedback", "misconception", "pacing", "alignment", "other"]
    severity: Literal["info", "minor", "major", "critical"] = "info"
    issue: str
    evidence: str
    recommendation: str
    analysis: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    _validate_observation_ids = field_validator("round_id", "slide_id", "issue", "evidence", "recommendation")(_non_empty)


class SupervisorReport(DomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    round_id: str
    overall_score: int = Field(ge=0, le=100)
    dimension_scores: dict[str, int] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    critical_issues: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    revision_priorities: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    _validate_report_ids = field_validator("run_id", "round_id")(_non_empty)

    @model_validator(mode="before")
    @classmethod
    def accept_observation_ids_alias(cls, value: Any) -> Any:
        if isinstance(value, dict) and "observations" not in value and "observation_ids" in value:
            value = dict(value)
            value["observations"] = value.pop("observation_ids")
        return value

    @field_validator("dimension_scores")
    @classmethod
    def validate_dimension_scores(cls, value: dict[str, int]) -> dict[str, int]:
        if any(score < 0 or score > 100 for score in value.values()):
            raise ValueError("dimension scores must be between 0 and 100")
        return value

    @property
    def observation_ids(self) -> list[str]:
        """Explicit name used by the Phase 5 report contract."""
        return self.observations


class RevisionPatch(DomainModel):
    patch_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    source_version_id: str
    target_version_id: str | None = None
    source_round_id: str | None = None
    target_type: Literal["slide", "speaker_note", "interaction_anchor", "misconception", "lesson"]
    slide_id: str
    block_id: str | None = None
    field_path: str
    before: Any
    after: Any
    reason: str
    source_observation_ids: list[str] = Field(default_factory=list)
    # 教师课堂介入产生的补丁: 溯源到 TeacherDirective, 复盘页可回看原话
    source_intervention_ids: list[str] = Field(default_factory=list)
    status: Literal["proposed", "pending", "approved", "rejected", "applied", "failed", "conflict"] = "proposed"
    created_at: datetime = Field(default_factory=utc_now)
    applied_at: datetime | None = None

    _validate_patch_ids = field_validator("run_id", "source_version_id", "slide_id", "field_path", "reason")(_non_empty)

    @model_validator(mode="before")
    @classmethod
    def accept_patch_target_aliases(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = dict(value)
            if "block_id" not in value:
                value["block_id"] = value.get("interaction_id") or value.get("misconception_id")
            aliases = {"speaker_note_block": "speaker_note", "interaction": "interaction_anchor"}
            if value.get("target_type") in aliases:
                value["target_type"] = aliases[value["target_type"]]
        return value
