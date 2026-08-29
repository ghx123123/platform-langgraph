"""
辩论数据模型 - Pydantic models
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    """辩论会话状态"""
    PENDING = "pending"      # 创建，等待开始
    READY = "ready"         # Agent 就绪
    ACTIVE = "active"       # 辩论进行中
    PAUSED = "paused"       # 暂停
    COMPLETED = "completed"  # 完成
    FAILED = "failed"       # 失败


class AgentRole(str, Enum):
    """辩论 Agent 角色"""
    PROPONENT = "proponent"   # 正方
    OPPONENT = "opponent"    # 反方
    MODERATOR = "moderator"  # 主持人
    REPORTER = "reporter"    # 汇报员


class DebateRole(str, Enum):
    """辩论消息类型"""
    DEBATE = "debate"        # 辩论发言
    CHALLENGE = "challenge"  # 质疑
    REBUTTAL = "rebuttal"   # 反驳
    SUMMARY = "summary"       # 总结
    COMMENT = "comment"      # 点评


class KnowledgePoint(BaseModel):
    """知识点"""
    title: str
    chapter: str = ""
    is_key_point: bool = False
    difficulty_level: str = "中等"
    keywords: List[str] = Field(default_factory=list)


class DebateSession(BaseModel):
    """辩论会话"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    document_id: Optional[str] = None
    status: SessionStatus = SessionStatus.PENDING
    current_round: int = 0
    max_rounds: int = 5
    knowledge_points: List[KnowledgePoint] = Field(default_factory=list)
    raw_text: str = ""  # 文档原文摘要
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class DebateAgent(BaseModel):
    """辩论 Agent"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    name: str
    role: AgentRole
    stance: str = ""  # 支持/反对/中立
    system_prompt: str
    avatar: str = "🤖"
    status: str = "idle"  # idle/ready/debating/waiting
    created_at: datetime = Field(default_factory=datetime.now)


class DebateMessage(BaseModel):
    """辩论消息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    agent_id: str
    agent_name: str = ""
    agent_role: str = ""
    round: int = 0
    msg_type: DebateRole = DebateRole.DEBATE
    content: str
    target_agent_id: Optional[str] = None  # 用于直接回复
    is_final: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class DebateReport(BaseModel):
    """辩论报告"""
    session_id: str
    summary: str
    proponent_points: List[str] = Field(default_factory=list)
    opponent_points: List[str] = Field(default_factory=list)
    key_disagreements: List[str] = Field(default_factory=list)
    conclusion: str
    suggestions: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# API Request/Response Models
# =============================================================================

class CreateSessionRequest(BaseModel):
    """创建辩论会话请求"""
    title: str
    document_id: Optional[str] = None
    max_rounds: int = 5
    knowledge_points: List[KnowledgePoint] = Field(default_factory=list)
    raw_text: str = ""


class CreateSessionResponse(BaseModel):
    """创建辩论会话响应"""
    session: DebateSession
    agents: List[DebateAgent] = Field(default_factory=list)


class StartDebateRequest(BaseModel):
    """开始辩论请求"""
    pass


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    content: str
    msg_type: DebateRole = DebateRole.DEBATE
    target_agent_id: Optional[str] = None


import uuid
