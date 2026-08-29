"""
教学评估数据模型
包含互动路径、学习目标、测验等评估相关模型
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class InteractionType(str, Enum):
    """互动类型"""
    QUESTION = "question"      # 学生提问
    ANSWER = "answer"          # 教师回答
    COMMENT = "comment"        # 督导点评
    DISCUSSION = "discussion"  # 讨论


class InteractionNode:
    """互动节点 - 记录教学过程中的单次互动"""
    def __init__(
        self,
        session_id: str,
        interaction_type: InteractionType,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        content: str,
        knowledge_point_id: Optional[str] = None,
        knowledge_point_title: Optional[str] = None,
        parent_id: Optional[str] = None,  # 父节点ID，用于构建问答链
        node_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = node_id or str(uuid.uuid4())
        self.session_id = session_id
        self.interaction_type = interaction_type
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.content = content
        self.knowledge_point_id = knowledge_point_id
        self.knowledge_point_title = knowledge_point_title
        self.parent_id = parent_id  # 关联的提问/回答
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "interaction_type": self.interaction_type.value if isinstance(self.interaction_type, Enum) else self.interaction_type,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "content": self.content,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point_title": self.knowledge_point_title,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionNode":
        interaction_type = data.get("interaction_type", "discussion")
        if isinstance(interaction_type, str):
            interaction_type = InteractionType(interaction_type)
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            node_id=data.get("id"),
            session_id=data["session_id"],
            interaction_type=interaction_type,
            agent_id=data["agent_id"],
            agent_name=data.get("agent_name", ""),
            agent_type=data.get("agent_type", ""),
            content=data.get("content", ""),
            knowledge_point_id=data.get("knowledge_point_id"),
            knowledge_point_title=data.get("knowledge_point_title"),
            parent_id=data.get("parent_id"),
            created_at=created_at,
        )


class LearningObjective:
    """学习目标"""
    def __init__(
        self,
        session_id: str,
        objective_id: Optional[str] = None,
        description: str = "",
        objective_type: str = "knowledge",  # knowledge, skill, attitude
        priority: str = "medium",  # high, medium, low
        related_knowledge_points: Optional[List[str]] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = objective_id or str(uuid.uuid4())
        self.session_id = session_id
        self.description = description
        self.objective_type = objective_type
        self.priority = priority
        self.related_knowledge_points = related_knowledge_points or []
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "description": self.description,
            "objective_type": self.objective_type,
            "priority": self.priority,
            "related_knowledge_points": self.related_knowledge_points,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningObjective":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            objective_id=data.get("id"),
            session_id=data["session_id"],
            description=data.get("description", ""),
            objective_type=data.get("objective_type", "knowledge"),
            priority=data.get("priority", "medium"),
            related_knowledge_points=data.get("related_knowledge_points", []),
            created_at=created_at,
        )


class ObjectiveAssessment:
    """学习目标达成评估"""
    def __init__(
        self,
        session_id: str,
        objective_id: str,
        coverage_score: float = 0.0,  # 0-100
        evidence: str = "",  # 支持评估的证据
        gaps: Optional[List[str]] = None,  # 未覆盖的内容
        suggestions: Optional[List[str]] = None,  # 改进建议
        assessment_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = assessment_id or str(uuid.uuid4())
        self.session_id = session_id
        self.objective_id = objective_id
        self.coverage_score = coverage_score
        self.evidence = evidence
        self.gaps = gaps or []
        self.suggestions = suggestions or []
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "objective_id": self.objective_id,
            "coverage_score": self.coverage_score,
            "evidence": self.evidence,
            "gaps": self.gaps,
            "suggestions": self.suggestions,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ObjectiveAssessment":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            assessment_id=data.get("id"),
            session_id=data["session_id"],
            objective_id=data["objective_id"],
            coverage_score=data.get("coverage_score", 0.0),
            evidence=data.get("evidence", ""),
            gaps=data.get("gaps", []),
            suggestions=data.get("suggestions", []),
            created_at=created_at,
        )


class QuizType(str, Enum):
    """测验题型"""
    SINGLE_CHOICE = "single_choice"    # 单选题
    MULTI_CHOICE = "multi_choice"      # 多选题
    FILL_BLANK = "fill_blank"          # 填空题
    SHORT_ANSWER = "short_answer"      # 简答题


class QuizQuestion:
    """测验题目"""
    def __init__(
        self,
        quiz_id: str,
        question_type: QuizType,
        question_text: str,
        options: Optional[List[str]] = None,  # 选择题选项
        correct_answer: str = "",
        explanation: str = "",  # 答案解析
        knowledge_point_id: Optional[str] = None,
        knowledge_point_title: Optional[str] = None,
        difficulty: str = "medium",  # easy, medium, hard
        score: float = 10.0,
        question_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = question_id or str(uuid.uuid4())
        self.quiz_id = quiz_id
        self.question_type = question_type
        self.question_text = question_text
        self.options = options or []
        self.correct_answer = correct_answer
        self.explanation = explanation
        self.knowledge_point_id = knowledge_point_id
        self.knowledge_point_title = knowledge_point_title
        self.difficulty = difficulty
        self.score = score
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "question_type": self.question_type.value if isinstance(self.question_type, Enum) else self.question_type,
            "question_text": self.question_text,
            "options": self.options,
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point_title": self.knowledge_point_title,
            "difficulty": self.difficulty,
            "score": self.score,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuizQuestion":
        question_type = data.get("question_type", "single_choice")
        if isinstance(question_type, str):
            question_type = QuizType(question_type)
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            question_id=data.get("id"),
            quiz_id=data["quiz_id"],
            question_type=question_type,
            question_text=data.get("question_text", ""),
            options=data.get("options", []),
            correct_answer=data.get("correct_answer", ""),
            explanation=data.get("explanation", ""),
            knowledge_point_id=data.get("knowledge_point_id"),
            knowledge_point_title=data.get("knowledge_point_title"),
            difficulty=data.get("difficulty", "medium"),
            score=data.get("score", 10.0),
            created_at=created_at,
        )


class Quiz:
    """测验"""
    def __init__(
        self,
        session_id: str,
        title: str = "",
        description: str = "",
        time_limit: int = 30,  # 分钟
        total_score: float = 100.0,
        passing_score: float = 60.0,
        quiz_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = quiz_id or str(uuid.uuid4())
        self.session_id = session_id
        self.title = title
        self.description = description
        self.time_limit = time_limit
        self.total_score = total_score
        self.passing_score = passing_score
        self.questions: List[QuizQuestion] = []
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "description": self.description,
            "time_limit": self.time_limit,
            "total_score": self.total_score,
            "passing_score": self.passing_score,
            "question_count": len(self.questions),
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Quiz":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        quiz = cls(
            quiz_id=data.get("id"),
            session_id=data["session_id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            time_limit=data.get("time_limit", 30),
            total_score=data.get("total_score", 100.0),
            passing_score=data.get("passing_score", 60.0),
            created_at=created_at,
        )
        return quiz


class QuizAnswer:
    """测验答案"""
    def __init__(
        self,
        quiz_id: str,
        question_id: str,
        answer_text: str = "",
        is_correct: bool = False,
        score: float = 0.0,
        answer_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = answer_id or str(uuid.uuid4())
        self.quiz_id = quiz_id
        self.question_id = question_id
        self.answer_text = answer_text
        self.is_correct = is_correct
        self.score = score
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "question_id": self.question_id,
            "answer_text": self.answer_text,
            "is_correct": self.is_correct,
            "score": self.score,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuizAnswer":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            answer_id=data.get("id"),
            quiz_id=data["quiz_id"],
            question_id=data["question_id"],
            answer_text=data.get("answer_text", ""),
            is_correct=data.get("is_correct", False),
            score=data.get("score", 0.0),
            created_at=created_at,
        )


class QuizResult:
    """测验结果"""
    def __init__(
        self,
        quiz_id: str,
        total_score: float = 0.0,
        max_score: float = 100.0,
        passed: bool = False,
        answers: Optional[List[QuizAnswer]] = None,
        weak_knowledge_points: Optional[List[str]] = None,  # 薄弱知识点
        improvement_suggestions: Optional[List[str]] = None,
        result_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = result_id or str(uuid.uuid4())
        self.quiz_id = quiz_id
        self.total_score = total_score
        self.max_score = max_score
        self.passed = passed
        self.answers = answers or []
        self.weak_knowledge_points = weak_knowledge_points or []
        self.improvement_suggestions = improvement_suggestions or []
        self.created_at = created_at or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "total_score": self.total_score,
            "max_score": self.max_score,
            "passed": self.passed,
            "answers": [a.to_dict() for a in self.answers],
            "weak_knowledge_points": self.weak_knowledge_points,
            "improvement_suggestions": self.improvement_suggestions,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuizResult":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        answers = data.get("answers", [])
        result = cls(
            result_id=data.get("id"),
            quiz_id=data["quiz_id"],
            total_score=data.get("total_score", 0.0),
            max_score=data.get("max_score", 100.0),
            passed=data.get("passed", False),
            answers=[QuizAnswer.from_dict(a) for a in answers] if answers else [],
            weak_knowledge_points=data.get("weak_knowledge_points", []),
            improvement_suggestions=data.get("improvement_suggestions", []),
            created_at=created_at,
        )
        return result


class InteractionPath:
    """互动路径 - 完整的教学互动链条"""
    def __init__(
        self,
        session_id: str,
        nodes: Optional[List[InteractionNode]] = None,
        statistics: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.nodes = nodes or []
        self.statistics = statistics or {}
        
    def add_node(self, node: InteractionNode):
        """添加互动节点"""
        self.nodes.append(node)
        self._update_statistics()
        
    def _update_statistics(self):
        """更新统计数据"""
        question_count = sum(1 for n in self.nodes if n.interaction_type == InteractionType.QUESTION)
        answer_count = sum(1 for n in self.nodes if n.interaction_type == InteractionType.ANSWER)
        comment_count = sum(1 for n in self.nodes if n.interaction_type == InteractionType.COMMENT)
        
        self.statistics = {
            "total_interactions": len(self.nodes),
            "question_count": question_count,
            "answer_count": answer_count,
            "comment_count": comment_count,
            "qa_coverage": answer_count / question_count if question_count > 0 else 0,
        }
        
    def get_qa_chains(self) -> List[List[InteractionNode]]:
        """获取所有问答链"""
        chains = []
        questions = [n for n in self.nodes if n.interaction_type == InteractionType.QUESTION]
        
        for q in questions:
            chain = [q]
            # 查找该问题的所有回答
            answers = [n for n in self.nodes if n.parent_id == q.id]
            chain.extend(answers)
            chains.append(chain)
            
        return chains
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "statistics": self.statistics,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionPath":
        nodes = data.get("nodes", [])
        return cls(
            session_id=data["session_id"],
            nodes=[InteractionNode.from_dict(n) for n in nodes] if nodes else [],
            statistics=data.get("statistics", {}),
        )
