"""
辩论会话数据类
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SessionStatus(str):
    """辩论会话状态"""
    PENDING = "pending"      # 创建，等待开始
    READY = "ready"         # Agent 就绪
    ACTIVE = "active"       # 辩论进行中
    PAUSED = "paused"       # 暂停
    COMPLETED = "completed"  # 完成
    FAILED = "failed"       # 失败


class AgentRole(str):
    """辩论 Agent 角色"""
    PROPONENT = "proponent"   # 正方
    OPPONENT = "opponent"    # 反方
    MODERATOR = "moderator"  # 主持人
    REPORTER = "reporter"    # 汇报员


class DebateRole(str):
    """辩论消息类型"""
    DEBATE = "debate"        # 辩论发言
    CHALLENGE = "challenge"  # 质疑
    REBUTTAL = "rebuttal"   # 反驳
    SUMMARY = "summary"       # 总结
    COMMENT = "comment"      # 点评


class KnowledgePoint(BaseModel):
    """知识点"""
    title: str = ""
    chapter: str = ""
    is_key_point: bool = False
    difficulty_level: str = "中等"
    keywords: List[str] = Field(default_factory=list)


class DebateSession:
    """辩论会话"""

    def __init__(
        self,
        title: str,
        document_id: Optional[str] = None,
        max_rounds: int = 5,
        knowledge_points: Optional[List[KnowledgePoint]] = None,
        raw_text: str = "",
        session_id: Optional[str] = None,
    ):
        self.id = session_id or str(uuid.uuid4())
        self.title = title
        self.document_id = document_id
        self.status = SessionStatus.PENDING
        self.current_round = 0
        self.max_rounds = max_rounds
        self.knowledge_points = knowledge_points or []
        self.raw_text = raw_text
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.agents: List[DebateAgent] = []
        self.messages: List[DebateMessage] = []
        self.report: Optional[DebateReport] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "document_id": self.document_id,
            "status": self.status,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "knowledge_points": [kp.model_dump() for kp in self.knowledge_points],
            "raw_text": self.raw_text[:5000] if self.raw_text else "",  # 限制长度
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateSession":
        session = cls(
            title=data["title"],
            document_id=data.get("document_id"),
            max_rounds=data.get("max_rounds", 5),
            knowledge_points=[KnowledgePoint(**kp) for kp in data.get("knowledge_points", [])],
            raw_text=data.get("raw_text", ""),
            session_id=data["id"],
        )
        session.status = data.get("status", SessionStatus.PENDING)
        session.current_round = data.get("current_round", 0)
        session.created_at = datetime.fromisoformat(data["created_at"])
        session.updated_at = datetime.fromisoformat(data["updated_at"])
        if data.get("completed_at"):
            session.completed_at = datetime.fromisoformat(data["completed_at"])
        return session


class DebateAgent:
    """辩论 Agent"""

    def __init__(
        self,
        session_id: str,
        name: str,
        role: AgentRole,
        stance: str = "",
        system_prompt: str = "",
        avatar: str = "🤖",
        agent_id: Optional[str] = None,
    ):
        self.id = agent_id or str(uuid.uuid4())
        self.session_id = session_id
        self.name = name
        self.role = role
        self.stance = stance
        self.system_prompt = system_prompt
        self.avatar = avatar
        self.status = "idle"
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "role": self.role,
            "stance": self.stance,
            "system_prompt": self.system_prompt,
            "avatar": self.avatar,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateAgent":
        agent = cls(
            session_id=data["session_id"],
            name=data["name"],
            role=data["role"],
            stance=data.get("stance", ""),
            system_prompt=data["system_prompt"],
            avatar=data.get("avatar", "🤖"),
            agent_id=data["id"],
        )
        agent.status = data.get("status", "idle")
        agent.created_at = datetime.fromisoformat(data["created_at"])
        return agent


class DebateMessage:
    """辩论消息"""

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        agent_name: str = "",
        agent_role: str = "",
        round_num: int = 0,
        msg_type: DebateRole = DebateRole.DEBATE,
        content: str = "",
        target_agent_id: Optional[str] = None,
        is_final: bool = False,
        msg_id: Optional[str] = None,
    ):
        self.id = msg_id or str(uuid.uuid4())
        self.session_id = session_id
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.round = round_num
        self.msg_type = msg_type
        self.content = content
        self.target_agent_id = target_agent_id
        self.is_final = is_final
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "round": self.round,
            "msg_type": self.msg_type,
            "content": self.content,
            "target_agent_id": self.target_agent_id,
            "is_final": self.is_final,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateMessage":
        msg = cls(
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            agent_name=data.get("agent_name", ""),
            agent_role=data.get("agent_role", ""),
            round_num=data.get("round", 0),
            msg_type=data.get("msg_type", DebateRole.DEBATE),
            content=data["content"],
            target_agent_id=data.get("target_agent_id"),
            is_final=data.get("is_final", False),
            msg_id=data["id"],
        )
        msg.created_at = datetime.fromisoformat(data["created_at"])
        return msg


class DebateReport:
    """辩论报告"""

    def __init__(
        self,
        session_id: str,
        summary: str = "",
        proponent_points: Optional[List[str]] = None,
        opponent_points: Optional[List[str]] = None,
        key_disagreements: Optional[List[str]] = None,
        conclusion: str = "",
        suggestions: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self.summary = summary
        self.proponent_points = proponent_points or []
        self.opponent_points = opponent_points or []
        self.key_disagreements = key_disagreements or []
        self.conclusion = conclusion
        self.suggestions = suggestions or []
        self.generated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "summary": self.summary,
            "proponent_points": self.proponent_points,
            "opponent_points": self.opponent_points,
            "key_disagreements": self.key_disagreements,
            "conclusion": self.conclusion,
            "suggestions": self.suggestions,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateReport":
        report = cls(
            session_id=data["session_id"],
            summary=data.get("summary", ""),
            proponent_points=data.get("proponent_points", []),
            opponent_points=data.get("opponent_points", []),
            key_disagreements=data.get("key_disagreements", []),
            conclusion=data.get("conclusion", ""),
            suggestions=data.get("suggestions", []),
        )
        if data.get("generated_at"):
            report.generated_at = datetime.fromisoformat(data["generated_at"])
        return report
