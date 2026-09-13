"""Classroom v2 domain models and persistence primitives.

Phase 1 intentionally contains no classroom execution runtime.  The package
is kept independent from LangGraph and the DeepSeek Harness so later phases
can add adapters without coupling domain state to either runtime.
"""

from .models import (
    ClassroomAgentInstance,
    ClassroomEvent,
    ClassroomEventType,
    ClassroomState,
    ExpectedMisconception,
    InteractionAnchor,
    LessonSlide,
    LessonVersion,
    RevisionPatch,
    SimulationRound,
    SpeakerNoteBlock,
    StudentCognitiveState,
    StudentPersona,
    StudentScenarioBaseline,
    SupervisorObservation,
    SupervisorReport,
)
from .agent_runtime import HarnessAgentRuntime, RuntimeSession, SessionKey
from .lesson_blueprint import BlueprintValidationError, LessonBlueprintService
from .actions import FeedbackEvaluation, StudentAction, StudentActionType, TeacherAction, TeacherActionType
from .policies import InteractionPolicy, VirtualTimePolicy
from .agent_services import StudentAgentService, TeacherAgentService
from .orchestrator import ClassroomOrchestrator
from .evaluation import DIMENSION_WEIGHTS, EvaluationError, SupervisorEvaluationService
from .revision import RevisionEngine, RevisionError
from .graph import ClassroomGraphState, build_classroom_graph

__all__ = [
    "ClassroomAgentInstance",
    "ClassroomEvent",
    "ClassroomEventType",
    "ClassroomState",
    "ExpectedMisconception",
    "InteractionAnchor",
    "LessonSlide",
    "LessonVersion",
    "RevisionPatch",
    "SimulationRound",
    "SpeakerNoteBlock",
    "StudentCognitiveState",
    "StudentPersona",
    "StudentScenarioBaseline",
    "SupervisorObservation",
    "SupervisorReport",
    "HarnessAgentRuntime",
    "RuntimeSession",
    "SessionKey",
    "BlueprintValidationError",
    "LessonBlueprintService",
    "FeedbackEvaluation",
    "StudentAction",
    "StudentActionType",
    "TeacherAction",
    "TeacherActionType",
    "InteractionPolicy",
    "VirtualTimePolicy",
    "StudentAgentService",
    "TeacherAgentService",
    "ClassroomOrchestrator",
    "DIMENSION_WEIGHTS",
    "EvaluationError",
    "SupervisorEvaluationService",
    "RevisionEngine",
    "RevisionError",
    "ClassroomGraphState",
    "build_classroom_graph",
]
