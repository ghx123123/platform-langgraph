"""
辩论模块 - Multi-Agent Document Debate System
"""
from .session import (
    DebateSession,
    SessionStatus,
    DebateAgent,
    DebateMessage,
    DebateReport,
    AgentRole,
    DebateRole,
    KnowledgePoint,
)
from .manager import DebateSessionManager, get_debate_manager

__all__ = [
    "DebateSession",
    "SessionStatus",
    "DebateAgent",
    "DebateMessage",
    "DebateReport",
    "AgentRole",
    "DebateRole",
    "KnowledgePoint",
    "DebateSessionManager",
    "get_debate_manager",
]