"""
教学模拟模块 - Multi-Agent Teaching Simulation System
"""
from .session import (
    TeachingSession,
    TeachingStatus,
    TeachingAgent,
    TeachingMessage,
    TeachingPhase,
    AgentType,
    StudentLevel,
    KnowledgePoint,
    SupervisorSuggestion,
)
from .manager import TeachingSessionManager, get_teaching_manager
from .evaluation_models import (
    InteractionType,
    InteractionNode,
    InteractionPath,
    LearningObjective,
    ObjectiveAssessment,
    QuizType,
    Quiz,
    QuizQuestion,
    QuizAnswer,
    QuizResult,
)

__all__ = [
    "TeachingSession",
    "TeachingStatus",
    "TeachingAgent",
    "TeachingMessage",
    "TeachingPhase",
    "AgentType",
    "StudentLevel",
    "KnowledgePoint",
    "SupervisorSuggestion",
    "TeachingSessionManager",
    "get_teaching_manager",
    # 评估相关模型
    "InteractionType",
    "InteractionNode",
    "InteractionPath",
    "LearningObjective",
    "ObjectiveAssessment",
    "QuizType",
    "Quiz",
    "QuizQuestion",
    "QuizAnswer",
    "QuizResult",
]