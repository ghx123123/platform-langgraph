"""
教学会话数据模型
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TeachingStatus(str, Enum):
    """教学会话状态"""
    PENDING = "pending"       # 创建，等待开始
    DESIGNING = "designing"   # 设计教学流程
    TEACHING = "teaching"     # 教学进行中
    PAUSED = "paused"         # 暂停
    COMPLETED = "completed"    # 完成
    FAILED = "failed"         # 失败


class TeachingPhase(str, Enum):
    """教学阶段"""
    DESIGN = "design"                    # 设计教学流程
    TEACH_KNOWLEDGE = "teach_knowledge"  # 讲授知识点
    STUDENT_QUESTION = "student_question" # 学生提问
    TEACHER_ANSWER = "teacher_answer"    # 教师回答
    SUPERVISOR_COMMENT = "supervisor_comment"  # 督导点评
    ITERATION_COMPLETE = "iteration_complete"  # 迭代完成


class AgentType(str, Enum):
    """Agent类型"""
    TEACHER = "teacher"      # 教师
    STUDENT = "student"      # 学生
    SUPERVISOR = "supervisor"  # 督导


class StudentLevel(str, Enum):
    """学生水平"""
    HIGH = "high"    # 优秀
    MEDIUM = "medium"  # 中等
    LOW = "low"      # 较差


class KnowledgePoint:
    """知识点"""
    def __init__(
        self,
        title: str = "",
        chapter: str = "",
        is_key_point: bool = False,
        difficulty_level: str = "中等",
        keywords: Optional[List[str]] = None,
    ):
        self.title = title
        self.chapter = chapter
        self.is_key_point = is_key_point
        self.difficulty_level = difficulty_level
        self.keywords = keywords or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "chapter": self.chapter,
            "is_key_point": self.is_key_point,
            "difficulty_level": self.difficulty_level,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgePoint":
        return cls(
            title=data.get("title", ""),
            chapter=data.get("chapter", ""),
            is_key_point=data.get("is_key_point", False),
            difficulty_level=data.get("difficulty_level", "中等"),
            keywords=data.get("keywords", []),
        )


class TeachingAgent:
    """教学 Agent"""
    def __init__(
        self,
        session_id: str,
        name: str,
        agent_type: AgentType,
        level: Optional[StudentLevel] = None,
        system_prompt: str = "",
        avatar: str = "🤖",
        agent_id: Optional[str] = None,
    ):
        self.id = agent_id or str(uuid.uuid4())
        self.session_id = session_id
        self.name = name
        self.agent_type = agent_type
        self.level = level
        self.system_prompt = system_prompt
        self.avatar = avatar
        self.status = "idle"
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "agent_type": self.agent_type.value if isinstance(self.agent_type, Enum) else self.agent_type,
            "level": self.level.value if self.level and isinstance(self.level, Enum) else self.level,
            "system_prompt": self.system_prompt,
            "avatar": self.avatar,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeachingAgent":
        agent_type = data.get("agent_type", "teacher")
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type)
        level = data.get("level")
        if level and isinstance(level, str):
            level = StudentLevel(level)
        return cls(
            agent_id=data.get("id"),
            session_id=data["session_id"],
            name=data["name"],
            agent_type=agent_type,
            level=level,
            system_prompt=data.get("system_prompt", ""),
            avatar=data.get("avatar", "🤖"),
        )


class SupervisorSuggestion:
    """督导建议"""
    def __init__(
        self,
        session_id: str,
        agent_id: str,
        agent_name: str,
        iteration: int,
        phase: TeachingPhase,
        suggestion_content: str,
        dimension: str,
        suggestion_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = suggestion_id or str(uuid.uuid4())
        self.session_id = session_id
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.iteration = iteration
        self.phase = phase
        self.suggestion_content = suggestion_content
        self.dimension = dimension
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "iteration": self.iteration,
            "phase": self.phase.value if isinstance(self.phase, Enum) else self.phase,
            "suggestion_content": self.suggestion_content,
            "dimension": self.dimension,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SupervisorSuggestion":
        phase = data.get("phase", "supervisor_comment")
        if isinstance(phase, str):
            phase = TeachingPhase(phase)
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            suggestion_id=data.get("id"),
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            agent_name=data.get("agent_name", ""),
            iteration=data.get("iteration", 1),
            phase=phase,
            suggestion_content=data.get("suggestion_content", ""),
            dimension=data.get("dimension", ""),
            created_at=created_at,
        )


class TeachingMessage:
    """教学消息"""
    def __init__(
        self,
        session_id: str,
        agent_id: str,
        agent_name: str,
        agent_type: AgentType,
        phase: TeachingPhase,
        iteration: int,
        content: str = "",
        msg_id: Optional[str] = None,
        references: Optional[List[Dict[str, Any]]] = None,
    ):
        self.id = msg_id or str(uuid.uuid4())
        self.session_id = session_id
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.phase = phase
        self.iteration = iteration
        self.content = content
        self.references = references or []
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type.value if isinstance(self.agent_type, Enum) else self.agent_type,
            "phase": self.phase.value if isinstance(self.phase, Enum) else self.phase,
            "iteration": self.iteration,
            "content": self.content,
            "references": self.references,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeachingMessage":
        agent_type = data.get("agent_type", "teacher")
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type)
        phase = data.get("phase", "design")
        if isinstance(phase, str):
            phase = TeachingPhase(phase)
        return cls(
            msg_id=data.get("id"),
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            agent_name=data.get("agent_name", ""),
            agent_type=agent_type,
            phase=phase,
            iteration=data.get("iteration", 1),
            content=data.get("content", ""),
            references=data.get("references", []),
        )


class TeachingSession:
    """教学会话"""
    def __init__(
        self,
        title: str,
        document_id: Optional[str] = None,
        max_iterations: int = 3,
        knowledge_points: Optional[List[KnowledgePoint]] = None,
        raw_text: str = "",
        session_id: Optional[str] = None,
    ):
        self.id = session_id or str(uuid.uuid4())
        self.title = title
        self.document_id = document_id
        self.status = TeachingStatus.PENDING
        self.current_iteration = 0
        self.max_iterations = max_iterations
        self.current_phase = TeachingPhase.DESIGN
        self.knowledge_points = knowledge_points or []
        self.raw_text = raw_text
        self.teaching_script = ""  # 讲课稿
        self.teaching_framework: Optional[Dict[str, Any]] = None  # 教学框架
        self.agents: List[TeachingAgent] = []
        self.messages: List[TeachingMessage] = []
        self.supervisor_suggestions: List[SupervisorSuggestion] = []
        # 评估相关字段
        self.interaction_path: List[Dict[str, Any]] = []  # 互动路径
        self.learning_objectives: List[Dict[str, Any]] = []  # 学习目标
        self.objective_assessments: List[Dict[str, Any]] = []  # 目标评估结果
        self.quiz_id: Optional[str] = None  # 关联的测验ID
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "document_id": self.document_id,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "current_phase": self.current_phase.value if isinstance(self.current_phase, Enum) else self.current_phase,
            "knowledge_points": [kp.to_dict() for kp in self.knowledge_points],
            "raw_text": self.raw_text[:5000] if self.raw_text else "",
            "teaching_script": self.teaching_script,
            "teaching_framework": self.teaching_framework,
            "supervisor_suggestions": [s.to_dict() for s in self.supervisor_suggestions],
            # 评估相关字段
            "interaction_path": self.interaction_path,
            "learning_objectives": self.learning_objectives,
            "objective_assessments": self.objective_assessments,
            "quiz_id": self.quiz_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeachingSession":
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = TeachingStatus(status)
        phase = data.get("current_phase", "design")
        if isinstance(phase, str):
            phase = TeachingPhase(phase)
        kps = data.get("knowledge_points", [])
        # 确保 kps 是列表类型（处理旧数据格式）
        if isinstance(kps, str):
            try:
                import json
                kps = json.loads(kps)
            except:
                kps = []
        if not isinstance(kps, list):
            kps = []
        session = cls(
            session_id=data.get("id"),
            title=data["title"],
            document_id=data.get("document_id"),
            max_iterations=data.get("max_iterations", 3),
            knowledge_points=[KnowledgePoint.from_dict(kp) for kp in kps if isinstance(kp, dict)] if kps else [],
            raw_text=data.get("raw_text", ""),
        )
        session.status = status
        session.current_iteration = data.get("current_iteration", 0)
        session.current_phase = phase
        session.teaching_script = data.get("teaching_script", "")
        session.teaching_framework = data.get("teaching_framework", None)

        # 处理 supervisor_suggestions，确保是列表
        suggestions = data.get("supervisor_suggestions", [])
        if isinstance(suggestions, str):
            try:
                import json
                suggestions = json.loads(suggestions)
            except:
                suggestions = []
        if not isinstance(suggestions, list):
            suggestions = []
        session.supervisor_suggestions = [SupervisorSuggestion.from_dict(s) for s in suggestions if isinstance(s, dict)] if suggestions else []

        # 评估相关字段
        interaction_path = data.get("interaction_path", [])
        if isinstance(interaction_path, str):
            try:
                import json
                interaction_path = json.loads(interaction_path)
            except:
                interaction_path = []
        if not isinstance(interaction_path, list):
            interaction_path = []
        session.interaction_path = interaction_path

        learning_objectives = data.get("learning_objectives", [])
        if isinstance(learning_objectives, str):
            try:
                import json
                learning_objectives = json.loads(learning_objectives)
            except:
                learning_objectives = []
        if not isinstance(learning_objectives, list):
            learning_objectives = []
        session.learning_objectives = learning_objectives

        objective_assessments = data.get("objective_assessments", [])
        if isinstance(objective_assessments, str):
            try:
                import json
                objective_assessments = json.loads(objective_assessments)
            except:
                objective_assessments = []
        if not isinstance(objective_assessments, list):
            objective_assessments = []
        session.objective_assessments = objective_assessments

        session.quiz_id = data.get("quiz_id")
        return session
