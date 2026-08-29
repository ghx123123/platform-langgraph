"""
教学会话管理器 - TeachingSessionManager
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from backend import database
from backend.message_bus.bus import MessageBus, Message

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
from .evaluation_models import (
    InteractionNode, InteractionType, InteractionPath,
    LearningObjective, ObjectiveAssessment,
    Quiz, QuizQuestion, QuizAnswer, QuizResult, QuizType,
)

logger = logging.getLogger(__name__)


# 教学 Agent 系统提示词模板
TEACHING_PROMPTS = {
    AgentType.TEACHER: """你是一名教学设计师，输出结构化的教学方案。在教学过程中必须自然融入思政元素，实现知识传授与价值引领的有机统一。

## 课程主题
{topic}

## 知识点
{points}

## 输出要求（控制在600字以内）

### 1. 【教学目标】
- 知识目标：核心概念与原理
- 能力目标：应用能力与实践技能
- 素养目标：专业思维、科学精神与职业素养

### 2. 【知识框架】
- 知识体系结构
- 重点与难点

### 3. 【详细讲解】（重点，300字左右）
- 按知识点逐一展开
- 概念定义→核心原理→应用场景
- **思政融入**：每个知识点需自然融入1-2个思政元素（家国情怀、科学精神、职业道德、创新意识、社会责任）

### 4. 【案例分析】
- 1个典型案例（可包含中国案例或体现专业伦理的案例）
- 案例与知识点对应分析
- **思政映射**：案例中体现的价值观、职业精神或社会责任

### 5. 【互动设计】
- 预设认知障碍点
- 启发式问题（可涉及伦理思考或社会责任）

### 6. 【总结回顾】
- 核心知识点梳理
- 延伸思考方向（可联系行业发展与社会需求）

## 课程思政元素映射（基于知识点）
| 思政维度 | 融入要点 | 融入方式 |
|---------|---------|---------|
| 家国情怀 | 使命担当、民族自信 | 结合国家成就、行业发展 |
| 科学精神 | 求真务实、批判思维 | 强调方法论、探索过程 |
| 职业道德 | 工匠精神、诚信守法 | 案例示范、规范强调 |
| 创新意识 | 开拓进取、勇于探索 | 前沿技术、创新案例 |
| 社会责任 | 可持续发展、人文关怀 | 社会应用、伦理讨论 |

## 融入原则
- ✅ 自然融入，不生硬说教
- ✅ 与专业知识紧密结合，避免"两张皮"
- ✅ 用专业语言和案例体现价值引领
- ✅ 可使用中国案例增强文化自信

## 语言规范
- ✅ 使用"本节课程旨在..."、"该知识点的核心概念为..."
- ✅ 使用"这一发现体现了科学工作者的..."、"从该案例可以看出..."
- ❌ 严禁"同学们"、"我们来看看"、"那么简单"等口语
- ❌ 避免空洞说教，如"我们要爱国"等直白表述
- 只输出教学内容，不要输出思考过程
- 使用中文撰写""",

    StudentLevel.HIGH: """你是一名优秀学生。认真听讲后，提出一个最有深度的问题。

## 课程主题
{topic}

## 知识点
{points}

## 要求
- 只提1个问题
- 问题要简短（不超过30字）
- 用中文提问
- 只输出问题，不要解释""",

    StudentLevel.MEDIUM: """你是一名中等水平的学生。认真听讲后，提出一个基础性的疑惑。

## 课程主题
{topic}

## 知识点
{points}

## 要求
- 只提1个问题
- 问题要简短（不超过30字）
- 用中文提问
- 只输出问题，不要解释""",

    StudentLevel.LOW: """你是一名学习困难的学生。认真听讲后，提出一个基础问题。

## 课程主题
{topic}

## 知识点
{points}

## 要求
- 只提1个问题
- 问题要简短（不超过30字）
- 用中文提问
- 只输出问题，不要解释""",

    AgentType.SUPERVISOR: """你是一名教学督导专家。对教学过程进行简要点评，特别关注课程思政元素的融入效果，给出具体改进建议。

## 课程主题
{topic}

## 知识点
{points}

## 点评要求

请从以下三个维度进行简要点评：

### 1. 教学设计
- 优点：1-2个亮点
- 建议：1-2条具体改进建议

### 2. 讲授方式  
- 优点：1-2个亮点
- 建议：1-2条具体改进建议

### 3. 思政融入（重点关注）
- **评价要点**：
  - 思政元素与专业知识的融合度（是否自然、不生硬）
  - 思政教育的自然性和感染力（是否引起共鸣）
  - 价值观引导的有效性（是否达到润物无声的效果）
  - 思政案例的恰当性（是否与知识点紧密关联）
- **思政维度覆盖**：家国情怀、科学精神、职业道德、创新意识、社会责任
- 优点：思政融入的亮点
- 建议：如何进一步提升思政教育效果

## 评价标准参考
| 等级 | 融合度 | 自然性 | 感染力 |
|-----|-------|-------|-------|
| 优秀 | 与知识浑然一体 | 如盐入水，润物无声 | 引发深层思考 |
| 良好 | 与知识有机结合 | 过渡自然，不生硬 | 有明显启发 |
| 一般 | 有融合但较浅显 | 略显刻意 | 效果一般 |
| 需改进 | 融合度低或缺失 | 生硬说教 | 难以引起共鸣 |

## 输出格式（控制在400字以内）

**【教学设计】**
优点：...
建议：...

**【讲授方式】**
优点：...
建议：...

**【思政融入】**
评价：...
优点：...
建议：...

**【总结】**
一句话总结核心改进方向（可涉及思政教育优化）。

- 只输出点评内容，不要输出思考过程""",
}


class TeachingSessionManager:
    """
    教学会话管理器

    职责：
    - 创建和管理教学会话
    - 创建教学 Agent（1教师 + 3学生 + 2督导）
    - 控制教学流程（设计 → 讲授 → 提问 → 回答 → 点评）
    - 迭代3次
    """

    def __init__(self, message_bus: Optional[MessageBus] = None):
        self._sessions: Dict[str, TeachingSession] = {}
        self._quizzes: Dict[str, Quiz] = {}
        self._quiz_questions: Dict[str, List[QuizQuestion]] = {}
        self._quiz_results: Dict[str, QuizResult] = {}
        self._message_bus = message_bus
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._load_sessions_from_db()
        self._load_quizzes_from_db()

    def _load_sessions_from_db(self):
        """从数据库加载会话"""
        try:
            sessions_data = database.load_teaching_sessions()
            for data in sessions_data:
                session = TeachingSession.from_dict(data)
                self._sessions[session.id] = session

                # 加载 agents
                agents_data = database.load_teaching_agents(session.id)
                session.agents = [TeachingAgent.from_dict(a) for a in agents_data]

                # 加载消息
                messages_data = database.load_teaching_messages(session.id)
                session.messages = [TeachingMessage.from_dict(m) for m in messages_data]

            logger.info(f"[TeachingManager] Loaded {len(self._sessions)} sessions from database")
        except Exception as e:
            logger.warning(f"[TeachingManager] Failed to load sessions: {e}")

    # =========================================================================
    # Session Management
    # =========================================================================

    def create_session(
        self,
        title: str,
        document_id: Optional[str] = None,
        max_iterations: int = 3,
        knowledge_points: Optional[List[KnowledgePoint]] = None,
        raw_text: str = "",
    ) -> TeachingSession:
        """创建教学会话"""
        session = TeachingSession(
            title=title,
            document_id=document_id,
            max_iterations=max_iterations,
            knowledge_points=knowledge_points,
            raw_text=raw_text,
        )
        self._sessions[session.id] = session

        # 持久化到数据库
        database.save_teaching_session(session.to_dict())

        logger.info(f"[TeachingManager] Created session: {session.id}")
        return session

    def get_session(self, session_id: str) -> Optional[TeachingSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[TeachingSession]:
        """列出所有会话"""
        return list(self._sessions.values())

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            database.delete_teaching_session(session_id)
            logger.info(f"[TeachingManager] Deleted session: {session_id}")
            return True
        return False

    # =========================================================================
    # Agent Management
    # =========================================================================

    def create_agents(
        self,
        session_id: str,
        topic: str = "",
    ) -> List[TeachingAgent]:
        """为会话创建教学 Agent"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # 构建知识点字符串
        points_text = "\n".join([
            f"- {kp.title} ({kp.chapter})"
            for kp in session.knowledge_points
        ]) if session.knowledge_points else "无特定知识点"

        # 如果没有提供 topic，使用文档摘要
        if not topic:
            topic = session.raw_text[:500] if session.raw_text else "课程主题"

        # 创建 Agent
        agents = []

        # 教师
        teacher = TeachingAgent(
            session_id=session_id,
            name="教师",
            agent_type=AgentType.TEACHER,
            system_prompt=TEACHING_PROMPTS[AgentType.TEACHER].format(
                topic=topic,
                points=points_text,
            ),
            avatar="👨‍🏫",
        )
        agents.append(teacher)

        # 优秀学生
        student_high = TeachingAgent(
            session_id=session_id,
            name="优秀学生",
            agent_type=AgentType.STUDENT,
            level=StudentLevel.HIGH,
            system_prompt=TEACHING_PROMPTS[StudentLevel.HIGH].format(
                topic=topic,
                points=points_text,
            ),
            avatar="🎓",
        )
        agents.append(student_high)

        # 中等学生
        student_medium = TeachingAgent(
            session_id=session_id,
            name="中等学生",
            agent_type=AgentType.STUDENT,
            level=StudentLevel.MEDIUM,
            system_prompt=TEACHING_PROMPTS[StudentLevel.MEDIUM].format(
                topic=topic,
                points=points_text,
            ),
            avatar="📚",
        )
        agents.append(student_medium)

        # 困难学生
        student_low = TeachingAgent(
            session_id=session_id,
            name="困难学生",
            agent_type=AgentType.STUDENT,
            level=StudentLevel.LOW,
            system_prompt=TEACHING_PROMPTS[StudentLevel.LOW].format(
                topic=topic,
                points=points_text,
            ),
            avatar="📖",
        )
        agents.append(student_low)

        # 督导1
        supervisor1 = TeachingAgent(
            session_id=session_id,
            name="督导A",
            agent_type=AgentType.SUPERVISOR,
            system_prompt=TEACHING_PROMPTS[AgentType.SUPERVISOR].format(
                topic=topic,
                points=points_text,
            ),
            avatar="🔍",
        )
        agents.append(supervisor1)

        # 督导2
        supervisor2 = TeachingAgent(
            session_id=session_id,
            name="督导B",
            agent_type=AgentType.SUPERVISOR,
            system_prompt=TEACHING_PROMPTS[AgentType.SUPERVISOR].format(
                topic=topic,
                points=points_text,
            ),
            avatar="📋",
        )
        agents.append(supervisor2)

        # 保存到会话和数据库
        session.agents = agents
        for agent in agents:
            database.save_teaching_agent(agent.to_dict())

        logger.info(f"[TeachingManager] Created {len(agents)} agents for session {session_id}")
        return agents

    def get_agent(self, session_id: str, agent_id: str) -> Optional[TeachingAgent]:
        """获取 Agent"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        for agent in session.agents:
            if agent.id == agent_id:
                return agent
        return None

    # =========================================================================
    # Interaction Path Management
    # =========================================================================

    def record_interaction(
        self,
        session_id: str,
        interaction_data: Dict[str, Any],
    ) -> Optional[InteractionNode]:
        """记录单次互动到会话的 interaction_path

        Args:
            session_id: 会话ID
            interaction_data: 互动数据，包含：
                - agent_id: Agent ID
                - agent_name: Agent 名称
                - agent_type: Agent 类型 (teacher/student/supervisor)
                - content: 互动内容
                - interaction_type: 互动类型 (question/answer/comment/discussion)
                - knowledge_point_id: 可选，关联的知识点ID
                - parent_id: 可选，父节点ID（用于构建问答链）

        Returns:
            创建的 InteractionNode 对象，失败返回 None
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return None

        try:
            # 解析互动类型
            interaction_type_str = interaction_data.get("interaction_type", "discussion")
            if isinstance(interaction_type_str, str):
                interaction_type = InteractionType(interaction_type_str)
            else:
                interaction_type = interaction_type_str

            # 创建互动节点
            node = InteractionNode(
                session_id=session_id,
                interaction_type=interaction_type,
                agent_id=interaction_data.get("agent_id", ""),
                agent_name=interaction_data.get("agent_name", ""),
                agent_type=interaction_data.get("agent_type", ""),
                content=interaction_data.get("content", ""),
                knowledge_point_id=interaction_data.get("knowledge_point_id"),
                parent_id=interaction_data.get("parent_id"),
            )

            # 添加到会话的 interaction_path
            session.interaction_path.append(node.to_dict())
            session.updated_at = datetime.now()

            # 持久化到数据库
            database.update_teaching_session(session_id, {
                "interaction_path": session.interaction_path,
                "updated_at": session.updated_at.isoformat(),
            })

            logger.info(f"[TeachingManager] Recorded interaction {node.id} for session {session_id}")
            return node

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to record interaction: {e}")
            return None

    def get_interaction_path(
        self,
        session_id: str,
    ) -> Optional[InteractionPath]:
        """获取会话的完整互动路径

        Args:
            session_id: 会话ID

        Returns:
            InteractionPath 对象，包含所有节点和统计信息
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return None

        try:
            # 从会话数据构建 InteractionPath
            nodes = []
            for node_data in session.interaction_path:
                try:
                    node = InteractionNode.from_dict(node_data)
                    nodes.append(node)
                except Exception as e:
                    logger.warning(f"[TeachingManager] Failed to parse interaction node: {e}")
                    continue

            # 创建 InteractionPath 对象（会自动计算统计数据）
            path = InteractionPath(
                session_id=session_id,
                nodes=nodes,
            )
            # 手动更新统计数据
            path._update_statistics()

            return path

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to get interaction path: {e}")
            return None

    # =========================================================================
    # Teaching Flow Control
    # =========================================================================

    async def start_teaching(self, session_id: str) -> bool:
        """开始教学"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.status == TeachingStatus.TEACHING:
            logger.warning(f"[TeachingManager] Session {session_id} already teaching")
            return False

        # 更新状态
        session.status = TeachingStatus.TEACHING
        session.updated_at = datetime.now()
        database.update_teaching_session(session_id, {"status": TeachingStatus.TEACHING})

        # 启动教学任务
        task = asyncio.create_task(self._run_teaching(session_id))
        self._running_tasks[session_id] = task

        logger.info(f"[TeachingManager] Started teaching for session {session_id}")
        return True

    async def _run_teaching(self, session_id: str):
        """运行教学主循环"""
        logger.info(f"[TeachingManager] _run_teaching started for session {session_id}")

        session = self._sessions.get(session_id)
        if not session:
            logger.error(f"[TeachingManager] Session not found in _run_teaching: {session_id}")
            return

        try:
            # 等待一小段时间让前端连接 WebSocket
            logger.info(f"[TeachingManager] Waiting for WebSocket connection, session {session_id}")
            await asyncio.sleep(1)

            # 第一阶段：设计教学流程
            logger.info(f"[TeachingManager] Starting DESIGN phase for session {session_id}")
            session.current_phase = TeachingPhase.DESIGN
            await self._broadcast_phase_change(session)
            try:
                await self._design_teaching_process(session)
                logger.info(f"[TeachingManager] DESIGN phase completed for session {session_id}")
            except Exception as e:
                logger.error(f"[TeachingManager] Error in DESIGN phase for session {session_id}: {e}")
                # 设计阶段失败不中断流程，使用默认框架
                if not session.teaching_framework:
                    session.teaching_framework = self._create_default_framework(session)

            # 主循环：迭代 max_iterations 次
            for iteration in range(1, session.max_iterations + 1):
                logger.info(f"[TeachingManager] Starting iteration {iteration}/{session.max_iterations} for session {session_id}")

                session.current_iteration = iteration
                session.updated_at = datetime.now()
                try:
                    database.update_teaching_session(session_id, {
                        "current_iteration": session.current_iteration,
                        "current_phase": TeachingPhase.TEACH_KNOWLEDGE.value if isinstance(TeachingPhase.TEACH_KNOWLEDGE, Enum) else TeachingPhase.TEACH_KNOWLEDGE,
                    })
                    logger.info(f"[TeachingManager] Updated session iteration to {iteration}")
                except Exception as e:
                    logger.error(f"[TeachingManager] Failed to update session iteration in database: {e}")

                # 广播迭代开始
                await self._broadcast_iteration_change(session)

                # 1. 教师讲授知识点
                logger.info(f"[TeachingManager] Starting TEACH_KNOWLEDGE phase, iteration {iteration}")
                session.current_phase = TeachingPhase.TEACH_KNOWLEDGE
                await self._broadcast_phase_change(session)
                try:
                    await self._teacher_teaches(session, iteration)
                    logger.info(f"[TeachingManager] TEACH_KNOWLEDGE phase completed, iteration {iteration}")
                except Exception as e:
                    logger.error(f"[TeachingManager] Error in TEACH_KNOWLEDGE phase, iteration {iteration}: {e}")
                    # 继续流程，但记录错误

                # 2. 学生提问
                logger.info(f"[TeachingManager] Starting STUDENT_QUESTION phase, iteration {iteration}")
                session.current_phase = TeachingPhase.STUDENT_QUESTION
                await self._broadcast_phase_change(session)
                try:
                    await self._students_question(session, iteration)
                    logger.info(f"[TeachingManager] STUDENT_QUESTION phase completed, iteration {iteration}")
                except Exception as e:
                    logger.error(f"[TeachingManager] Error in STUDENT_QUESTION phase, iteration {iteration}: {e}")

                # 3. 教师回答
                logger.info(f"[TeachingManager] Starting TEACHER_ANSWER phase, iteration {iteration}")
                session.current_phase = TeachingPhase.TEACHER_ANSWER
                await self._broadcast_phase_change(session)
                try:
                    await self._teacher_answers(session, iteration)
                    logger.info(f"[TeachingManager] TEACHER_ANSWER phase completed, iteration {iteration}")
                except Exception as e:
                    logger.error(f"[TeachingManager] Error in TEACHER_ANSWER phase, iteration {iteration}: {e}")

                # 4. 督导点评
                logger.info(f"[TeachingManager] Starting SUPERVISOR_COMMENT phase, iteration {iteration}")
                session.current_phase = TeachingPhase.SUPERVISOR_COMMENT
                await self._broadcast_phase_change(session)
                try:
                    await self._supervisors_comment(session, iteration)
                    logger.info(f"[TeachingManager] SUPERVISOR_COMMENT phase completed, iteration {iteration}")
                except Exception as e:
                    logger.error(f"[TeachingManager] Error in SUPERVISOR_COMMENT phase, iteration {iteration}: {e}")

                # 本轮迭代完成
                logger.info(f"[TeachingManager] Iteration {iteration} completed for session {session_id}")
                session.current_phase = TeachingPhase.ITERATION_COMPLETE
                await asyncio.sleep(0.5)

            # 教学完成
            logger.info(f"[TeachingManager] All iterations completed for session {session_id}")
            session.status = TeachingStatus.COMPLETED
            session.completed_at = datetime.now()
            try:
                database.update_teaching_session(session.id, {
                    "status": TeachingStatus.COMPLETED.value if isinstance(TeachingStatus.COMPLETED, Enum) else TeachingStatus.COMPLETED,
                    "completed_at": session.completed_at.isoformat(),
                })
                logger.info(f"[TeachingManager] Session {session_id} marked as COMPLETED in database")
            except Exception as e:
                logger.error(f"[TeachingManager] Failed to update session status to COMPLETED: {e}")

            # 广播完成
            await self._broadcast_completion(session)
            logger.info(f"[TeachingManager] Teaching completed broadcasted for session {session_id}")

        except Exception as e:
            logger.error(f"[TeachingManager] Critical teaching error for session {session_id}: {type(e).__name__}: {e}")
            try:
                session.status = TeachingStatus.FAILED
                database.update_teaching_session(session_id, {"status": TeachingStatus.FAILED.value if isinstance(TeachingStatus.FAILED, Enum) else TeachingStatus.FAILED})
                logger.info(f"[TeachingManager] Session {session_id} marked as FAILED")
            except Exception as db_e:
                logger.error(f"[TeachingManager] Failed to update session status to FAILED: {db_e}")

        finally:
            logger.info(f"[TeachingManager] _run_teaching ending for session {session_id}")
            if session_id in self._running_tasks:
                del self._running_tasks[session_id]

    async def _design_teaching_process(self, session: TeachingSession):
        """设计教学流程 - 生成完整的教学内容框架"""
        logger.info(f"[TeachingManager] Starting _design_teaching_process for session {session.id}")

        # 找到教师 Agent
        teacher = self._get_agent_by_type(session, AgentType.TEACHER)
        if not teacher:
            logger.error(f"[TeachingManager] No teacher agent found for session {session.id}, creating default framework")
            # 使用默认框架继续
            framework = self._create_default_framework(session)
            session.teaching_framework = framework
            session.teaching_script = "使用默认教学框架（未找到教师Agent）"
            return

        response = ""
        framework = None

        try:
            # 构建上下文 - 要求生成结构化的教学框架
            context = f"""## 课程主题
{session.title}

## 知识点列表
{self._format_knowledge_points(session.knowledge_points)}

## 任务要求
请设计一份完整的教学内容框架。这个框架将作为后续所有教学轮次的基础，必须包含以下结构化内容：

### 1. 课程主题概述
- 本课程的核心主题和教学目标
- 预期的学习成果

### 2. 知识点列表
对每个知识点，请详细说明：
- 标题：知识点名称
- 重点内容：该知识点必须讲解的核心内容
- 关联例子：与该知识点配套的示例或案例（1-2个）

### 3. 教学重点和难点
- 重点：学生必须掌握的关键内容
- 难点：学生可能难以理解的地方及突破策略

### 4. 建议的教学顺序
- 各知识点的讲解顺序及逻辑关系
- 每个知识点的建议讲解时长分配

## 输出格式要求
请以JSON格式输出，便于后续程序解析：
```json
{{
    "course_overview": {{
        "topic": "课程主题",
        "objectives": ["目标1", "目标2"],
        "outcomes": "预期学习成果"
    }},
    "knowledge_points": [
        {{
            "title": "知识点标题",
            "key_content": "重点内容描述（使用学术化、规范化语言）",
            "examples": ["示例1", "示例2"],
            "ideological_mapping": {{
                "dimension": "思政维度（如：家国情怀、科学精神、职业道德、创新意识、社会责任）",
                "integration_point": "融入要点（具体融入什么价值观）",
                "integration_method": "融入方式（如何自然融入，如案例、方法论、历史背景等）"
            }}
        }}
    ],
    "key_points_and_difficulties": {{
        "key_points": ["重点1", "重点2"],
        "difficulties": ["难点1", "难点2"],
        "strategies": ["突破策略1", "突破策略2"]
    }},
    "teaching_sequence": [
        {{
            "order": 1,
            "knowledge_point": "知识点标题",
            "duration": "建议时长",
            "rationale": "讲解理由"
        }}
    ],
    "ideological_overall_plan": {{
        "primary_dimensions": ["主要思政维度，如：科学精神、职业道德"],
        "integration_strategy": "整体融入策略概述",
        "expected_outcomes": "思政教育预期成效"
    }}
}}
```

## 课程思政规划要求

### 1. 知识点思政映射
每个知识点必须包含 `ideological_mapping` 字段，明确：
- **思政维度**：从家国情怀、科学精神、职业道德、创新意识、社会责任中选择
- **融入要点**：具体融入什么价值观或精神品质
- **融入方式**：如何自然融入，不生硬说教

### 2. 思政融入示例
- **家国情怀**：结合中国在该领域的成就、贡献者事迹
- **科学精神**：强调探索过程、严谨方法、批判思维
- **职业道德**：通过行业规范、职业伦理案例体现
- **创新意识**：介绍前沿进展、突破传统的故事
- **社会责任**：讨论技术应用的社会影响、可持续发展

### 3. 融入原则
- 思政元素必须与知识点有机融合，避免"贴标签"
- 使用专业案例、历史事实、数据支撑，增强说服力
- 注重润物无声，引发学生思考而非生硬说教

## 语言风格要求
- 使用专业教学设计语言，避免口语化
- 知识点描述应准确、规范、学术化
- 严禁使用"同学们""我们来看"等口语表达
- 使用"本节课程旨在""该知识点的核心概念为"等规范表述
- 思政描述要专业、自然，如"该技术的发展体现了科研工作者的求真务实精神"

请确保框架内容完整、结构清晰，涵盖所有给定的知识点及其思政映射。"""

            # 调用 LLM（添加超时保护）
            try:
                logger.info(f"[TeachingManager] Calling LLM for framework design, session {session.id}")
                from backend.main import call_minimax_llm
                # 使用优化的参数：限制输出长度以加快速度
                response = await call_minimax_llm(
                    prompt=context,
                    system_prompt=teacher.system_prompt,
                    conversation_history=[],
                    max_tokens=2000,  # 框架设计不需要太长输出
                    timeout_seconds=30.0,  # 30秒超时
                )
                logger.info(f"[TeachingManager] LLM response received, length: {len(response)}")
            except Exception as e:
                logger.error(f"[TeachingManager] LLM call failed in _design_teaching_process: {e}")
                response = ""

            # 解析 JSON 框架
            try:
                # 尝试从响应中提取 JSON
                json_start = response.find('{')
                json_end = response.rfind('}')
                if json_start != -1 and json_end != -1:
                    json_str = response[json_start:json_end + 1]
                    framework = json.loads(json_str)
                    logger.info(f"[TeachingManager] Successfully parsed framework JSON")
                else:
                    logger.warning(f"[TeachingManager] No JSON found in LLM response, using default framework")
                    framework = self._create_default_framework(session)
            except json.JSONDecodeError as e:
                logger.warning(f"[TeachingManager] JSON parse error in framework: {e}, using default framework")
                framework = self._create_default_framework(session)

        except Exception as e:
            logger.error(f"[TeachingManager] Unexpected error in _design_teaching_process: {e}")
            framework = self._create_default_framework(session)

        # 保存教学框架（确保总有框架）
        if framework is None:
            framework = self._create_default_framework(session)

        session.teaching_framework = framework

        # 保存讲课稿（用于向后兼容）
        session.teaching_script = response if response else "使用默认教学框架"

        # 创建消息 - 显示框架的摘要
        try:
            framework_summary = self._format_framework_summary(framework)
            msg = TeachingMessage(
                session_id=session.id,
                agent_id=teacher.id,
                agent_name=teacher.name,
                agent_type=AgentType.TEACHER,
                phase=TeachingPhase.DESIGN,
                iteration=0,
                content=framework_summary,
            )

            try:
                session.messages.append(msg)
                logger.info(f"[TeachingManager] Message appended to session {session.id}")
            except Exception as e:
                logger.error(f"[TeachingManager] Failed to append message to session: {e}")

            try:
                database.save_teaching_message(msg.to_dict())
                logger.info(f"[TeachingManager] Message saved to database")
            except Exception as e:
                logger.error(f"[TeachingManager] Failed to save message to database: {e}")

            # 广播消息
            try:
                await self._broadcast_message(session.id, msg)
                logger.info(f"[TeachingManager] Message broadcasted")
            except Exception as e:
                logger.error(f"[TeachingManager] Failed to broadcast message: {e}")

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to create or send framework message: {e}")

        logger.info(f"[TeachingManager] Teaching framework designed for session {session.id}")

    def _create_default_framework(self, session: TeachingSession) -> Dict[str, Any]:
        """创建默认的教学框架（包含思政元素规划）"""
        # 为知识点生成思政映射
        ideological_dimensions = ["家国情怀", "科学精神", "职业道德", "创新意识", "社会责任"]

        knowledge_points_with_ideology = []
        if session.knowledge_points:
            for i, kp in enumerate(session.knowledge_points):
                dimension = ideological_dimensions[i % len(ideological_dimensions)]
                knowledge_points_with_ideology.append({
                    "title": kp.title,
                    "key_content": f"详细讲解{kp.title}的核心概念和原理",
                    "examples": [f"{kp.title}的典型应用示例"],
                    "ideological_mapping": {
                        "dimension": dimension,
                        "integration_point": f"通过{kp.title}的学习培养{dimension}",
                        "integration_method": f"结合{kp.title}的专业案例自然融入"
                    }
                })
        else:
            knowledge_points_with_ideology = [
                {
                    "title": session.title,
                    "key_content": "详细讲解课程核心内容",
                    "examples": ["相关实例说明"],
                    "ideological_mapping": {
                        "dimension": "科学精神",
                        "integration_point": "培养求真务实的科学态度",
                        "integration_method": "通过知识探索过程体现"
                    }
                }
            ]

        return {
            "course_overview": {
                "topic": session.title,
                "objectives": ["掌握课程核心知识", "理解关键概念", "培养专业素养与职业精神"],
                "outcomes": "能够运用所学知识解决相关问题，具备良好的职业素养和社会责任感"
            },
            "knowledge_points": knowledge_points_with_ideology,
            "key_points_and_difficulties": {
                "key_points": ["核心概念的理解", "基本原理的掌握", "思政元素的自然融入"],
                "difficulties": ["概念的深入理解", "知识的实际应用", "价值引领与知识传授的统一"],
                "strategies": ["使用类比和比喻", "结合实际案例讲解", "思政案例与专业知识有机融合"]
            },
            "teaching_sequence": [
                {
                    "order": i + 1,
                    "knowledge_point": kp.title,
                    "duration": "均匀分配",
                    "rationale": "按照知识逻辑顺序讲解"
                }
                for i, kp in enumerate(session.knowledge_points)
            ] if session.knowledge_points else [
                {
                    "order": 1,
                    "knowledge_point": session.title,
                    "duration": "整节课",
                    "rationale": "系统讲解主题内容"
                }
            ],
            "ideological_overall_plan": {
                "primary_dimensions": ["科学精神", "职业道德"],
                "integration_strategy": "将思政元素与专业知识有机融合，通过案例分析、方法论讲解自然融入",
                "expected_outcomes": "学生在掌握专业知识的同时，形成正确的价值观和良好的职业素养"
            }
        }

    def _format_framework_summary(self, framework: Dict[str, Any]) -> str:
        """格式化框架摘要用于显示"""
        overview = framework.get("course_overview", {})
        kp_list = framework.get("knowledge_points", [])

        summary_parts = ["## 教学内容框架设计完成\n"]

        # 课程概述
        summary_parts.append(f"**课程主题**: {overview.get('topic', '未指定')}")
        summary_parts.append(f"**教学目标**: {', '.join(overview.get('objectives', []))}\n")

        # 知识点列表
        summary_parts.append("### 知识点规划")
        for i, kp in enumerate(kp_list, 1):
            summary_parts.append(f"{i}. **{kp.get('title', '未命名')}**")
            summary_parts.append(f"   - 重点: {kp.get('key_content', '未指定')[:50]}...")

        # 教学重点
        key_diff = framework.get("key_points_and_difficulties", {})
        summary_parts.append(f"\n### 教学重点")
        for kp in key_diff.get('key_points', []):
            summary_parts.append(f"- {kp}")

        return "\n".join(summary_parts)

    async def _teacher_teaches(self, session: TeachingSession, iteration: int):
        """教师讲授 - 基于教学框架，支持多轮优化"""
        teacher = self._get_agent_by_type(session, AgentType.TEACHER)
        if not teacher:
            return

        # 获取教学框架
        framework = session.teaching_framework
        if not framework:
            # 如果没有框架，先创建一个默认框架
            framework = self._create_default_framework(session)
            session.teaching_framework = framework

        # 获取上一轮（iteration-1）的讲授内容
        previous_teach_content = ""
        for msg in reversed(session.messages):
            if msg.phase == TeachingPhase.TEACH_KNOWLEDGE and msg.iteration == iteration - 1:
                previous_teach_content = msg.content
                break

        # 读取上一轮（iteration-1）的所有督导建议
        previous_supervisor_comments = []
        for msg in session.messages:
            if msg.phase == TeachingPhase.SUPERVISOR_COMMENT and msg.iteration == iteration - 1:
                previous_supervisor_comments.append(f"督导 {msg.agent_name} 的建议：\n{msg.content}")

        supervisor_comments_text = "\n\n".join(previous_supervisor_comments) if previous_supervisor_comments else "暂无督导建议"

        # 格式化教学框架中的知识点信息
        framework_kp_info = self._format_framework_knowledge_points(framework)

        # 构建上下文
        if iteration == 1:
            # 第1轮：基于教学框架生成结构化的教学设计内容
            context = f"""## 教学框架（必须严格遵循）
{self._format_framework_for_teaching(framework)}

## 教学轮次信息
第 1 轮教学（共 {session.max_iterations} 轮）

## 任务要求
基于以上教学框架，生成一份结构化的教学设计方案。要求：

### 内容规范要求
1. **知识范围**：严格遵循教学框架，不扩展新知识点，不删减已有知识点
2. **字数要求**：总字数不少于800字，确保内容充实详尽
3. **专业语言**：使用学术化、规范化的教学语言，严禁口语化表达

### 严禁使用的口语表达（重要）
- ❌ "同学们好"、"大家好"、"各位同学"等称呼语
- ❌ "我们来看看"、"让我们来看一下"等引导语
- ❌ "那么"、"所以呢"、"其实啊"等口头禅
- ❌ "对吧"、"是吧"、"明白了吗"等确认语
- ❌ "很简单"、"很容易"等主观评价

### 必须包含的六个部分（严格按照此结构输出）

#### 1. 【教学目标】
- 知识目标：学习者应掌握的核心概念与原理
- 能力目标：学习者应具备的分析与应用能力
- 素养目标：学习者应形成的专业思维与方法

#### 2. 【知识框架】
- 本节课的知识体系结构
- 各知识点之间的逻辑关联
- 重点与难点明确标注

#### 3. 【详细讲解】（重点部分，不少于400字）
- 按知识点逐一展开
- 每个知识点：概念定义→核心原理→应用场景
- 使用学术化语言，重要公式定理需标注

#### 4. 【案例分析】
- 精选1-2个典型案例
- 案例背景与知识点对应分析
- 从案例中提炼的方法论

#### 5. 【互动设计】
- 预设学生可能的认知障碍点
- 设计针对性的启发式问题
- 提供引导思考的框架

#### 6. 【总结回顾】
- 核心知识点系统梳理
- 知识逻辑脉络总结
- 延伸思考方向

### 输出格式
使用markdown格式，六个部分明确标注，内容专业、规范、学术化。"""
        else:
            # 第2轮及以上：基于督导建议优化教学设计
            context = f"""## 教学框架（知识范围基准）
{self._format_framework_for_teaching(framework)}

## 教学轮次信息
第 {iteration} 轮教学（共 {session.max_iterations} 轮）

## 优化依据
基于第 {iteration - 1} 轮的督导建议，对教学设计进行优化。

## 上一轮督导建议
{supervisor_comments_text}

## 优化要求

### 必须遵守的原则
1. **知识范围严格一致**：只优化表达和结构，严禁增删知识点
2. **保持六个部分结构**：教学目标→知识框架→详细讲解→案例分析→互动设计→总结回顾
3. **强化专业语言**：使用学术化、规范化表达
4. **响应督导建议**：针对指出的问题进行改进

### 语言规范（重要）
- ✅ 使用"本节课程旨在阐述..."、"该知识点的核心概念为..."
- ✅ 使用"从以下三个维度展开..."、"具体而言..."
- ❌ 严禁"同学们"、"我们来看看"、"那么简单"等口语

### 输出要求
严格按照六个部分输出结构化的教学设计方案，内容专业、规范。"""

        # 调用 LLM（使用优化参数）
        try:
            from backend.main import call_minimax_llm
            # 讲授内容限制在合理范围，减少生成时间
            response = await call_minimax_llm(
                prompt=context,
                system_prompt=teacher.system_prompt,
                conversation_history=[],
                max_tokens=1500,  # 限制生成长度，约600-800字
                timeout_seconds=75.0,  # 增加超时时间
            )
        except Exception as e:
            logger.error(f"[TeachingManager] LLM call failed for teaching: {e}")
            # 使用默认讲授内容作为降级策略
            response = self._get_default_teacher_lecture(session, framework, iteration)

        # 构建 references（第2轮及以上引用上一轮的督导建议）
        references = []
        if iteration >= 2:
            # 从 session.supervisor_suggestions 中获取上一轮的所有督导建议
            for suggestion in session.supervisor_suggestions:
                if suggestion.iteration == iteration - 1:
                    references.append({
                        "agent_id": suggestion.agent_id,
                        "agent_name": suggestion.agent_name,
                        "suggestion": suggestion.suggestion_content,
                        "dimension": suggestion.dimension,
                    })

        msg = TeachingMessage(
            session_id=session.id,
            agent_id=teacher.id,
            agent_name=teacher.name,
            agent_type=AgentType.TEACHER,
            phase=TeachingPhase.TEACH_KNOWLEDGE,
            iteration=iteration,
            content=response.strip(),
            references=references if references else None,
        )
        session.messages.append(msg)
        database.save_teaching_message(msg.to_dict())
        await self._broadcast_message(session.id, msg)

        logger.info(f"[TeachingManager] Teacher taught iteration {iteration}, references count: {len(references)}")

    def _format_framework_for_teaching(self, framework: Dict[str, Any]) -> str:
        """将教学框架格式化为教学用的文本"""
        parts = []

        # 课程概述
        overview = framework.get("course_overview", {})
        parts.append(f"### 课程主题: {overview.get('topic', '未指定')}")
        parts.append(f"**教学目标**: {', '.join(overview.get('objectives', []))}")
        parts.append(f"**预期成果**: {overview.get('outcomes', '未指定')}\n")

        # 知识点列表
        parts.append("### 知识点列表（必须全部覆盖）")
        for i, kp in enumerate(framework.get("knowledge_points", []), 1):
            parts.append(f"\n**{i}. {kp.get('title', '未命名')}**")
            parts.append(f"- 重点内容: {kp.get('key_content', '未指定')}")
            examples = kp.get('examples', [])
            if examples:
                parts.append(f"- 关联例子: {', '.join(examples)}")

        # 教学重点和难点
        key_diff = framework.get("key_points_and_difficulties", {})
        parts.append("\n### 教学重点")
        for kp in key_diff.get('key_points', []):
            parts.append(f"- {kp}")

        parts.append("\n### 教学难点")
        for diff in key_diff.get('difficulties', []):
            parts.append(f"- {diff}")

        parts.append("\n### 突破策略")
        for strategy in key_diff.get('strategies', []):
            parts.append(f"- {strategy}")

        # 教学顺序
        parts.append("\n### 教学顺序")
        for seq in framework.get("teaching_sequence", []):
            parts.append(f"{seq.get('order', 1)}. {seq.get('knowledge_point', '未指定')} ({seq.get('duration', '未指定')})")

        return "\n".join(parts)

    def _format_framework_knowledge_points(self, framework: Dict[str, Any]) -> str:
        """格式化框架中的知识点信息"""
        kp_list = framework.get("knowledge_points", [])
        if not kp_list:
            return "无特定知识点"

        lines = []
        for kp in kp_list:
            title = kp.get('title', '未命名')
            key_content = kp.get('key_content', '')
            examples = kp.get('examples', [])
            lines.append(f"- {title}")
            if key_content:
                lines.append(f"  重点: {key_content[:100]}...")
            if examples:
                lines.append(f"  例子: {', '.join(examples[:2])}")
        return "\n".join(lines)

    async def _students_question(self, session: TeachingSession, iteration: int):
        """学生提问"""
        students = self._get_agents_by_type(session, AgentType.STUDENT)

        # 获取之前的教师讲授内容
        teach_msg = None
        for msg in reversed(session.messages):
            if msg.phase == TeachingPhase.TEACH_KNOWLEDGE and msg.iteration == iteration:
                teach_msg = msg
                break

        teach_content = teach_msg.content if teach_msg else ""

        for student in students:
            context = f"""## 当前迭代
第 {iteration} 轮 / 共 {session.max_iterations} 轮

## 教师讲授内容
{teach_content}

## 请根据教师讲授，提出你的1个问题。"""

            # 调用 LLM（使用优化参数）
            try:
                from backend.main import call_minimax_llm
                # 学生提问简短即可
                response = await call_minimax_llm(
                    prompt=context,
                    system_prompt=student.system_prompt,
                    conversation_history=[],
                    max_tokens=500,  # 问题简短
                    timeout_seconds=20.0,
                )
            except Exception as e:
                logger.error(f"[TeachingManager] LLM call failed for student: {e}")
                response = f"请问老师，关于刚才讲解的内容，能否再详细说明一下？"

            msg = TeachingMessage(
                session_id=session.id,
                agent_id=student.id,
                agent_name=student.name,
                agent_type=AgentType.STUDENT,
                phase=TeachingPhase.STUDENT_QUESTION,
                iteration=iteration,
                content=response.strip() if response else "请问老师，关于刚才讲解的内容，能否再详细说明一下？",
            )
            session.messages.append(msg)
            database.save_teaching_message(msg.to_dict())
            await self._broadcast_message(session.id, msg)

            # 记录学生提问到互动路径
            self.record_interaction(
                session_id=session.id,
                interaction_data={
                    "agent_id": student.id,
                    "agent_name": student.name,
                    "agent_type": AgentType.STUDENT.value,
                    "content": response.strip(),
                    "interaction_type": InteractionType.QUESTION.value,
                    "knowledge_point_id": None,
                    "parent_id": None,  # 学生提问是问答链的起点
                },
            )

        logger.info(f"[TeachingManager] Students questioned in iteration {iteration}")

    async def _teacher_answers(self, session: TeachingSession, iteration: int):
        """教师回答"""
        teacher = self._get_agent_by_type(session, AgentType.TEACHER)
        if not teacher:
            return

        # 收集本轮学生的问题及其消息ID（用于关联回答）
        questions = []
        question_msg_map = {}  # 用于存储问题内容和消息ID的映射
        for msg in session.messages:
            if msg.phase == TeachingPhase.STUDENT_QUESTION and msg.iteration == iteration:
                questions.append(msg.content)
                question_msg_map[msg.content] = msg.id

        questions_text = "\n".join([f"- {q}" for q in questions]) if questions else "无问题"

        context = f"""## 当前迭代
第 {iteration} 轮 / 共 {session.max_iterations} 轮

## 学生的问题
{questions_text}

请简洁地回答学生的问题。"""

        # 调用 LLM（使用优化参数）
        try:
            from backend.main import call_minimax_llm
            # 回答问题适中长度
            response = await call_minimax_llm(
                prompt=context,
                system_prompt=teacher.system_prompt,
                conversation_history=[],
                max_tokens=1500,  # 回答简洁但完整
                timeout_seconds=30.0,
            )
        except Exception as e:
            logger.error(f"[TeachingManager] LLM call failed for teacher answering: {e}")
            response = f"针对同学们提出的问题，我来简要回答：\n\n{questions_text}\n\n这些问题涉及到本节课程的核心内容，建议大家课后进一步思考和练习。"

        msg = TeachingMessage(
            session_id=session.id,
            agent_id=teacher.id,
            agent_name=teacher.name,
            agent_type=AgentType.TEACHER,
            phase=TeachingPhase.TEACHER_ANSWER,
            iteration=iteration,
            content=response.strip() if response else f"针对同学们提出的问题，这些问题涉及到本节课程的核心内容，建议大家课后进一步思考和练习。",
        )
        session.messages.append(msg)
        database.save_teaching_message(msg.to_dict())
        await self._broadcast_message(session.id, msg)

        # 记录教师回答到互动路径
        # 获取当前轮次学生提问对应的互动节点ID作为 parent_id
        parent_id = None
        for node_data in session.interaction_path:
            if (node_data.get("agent_type") == AgentType.STUDENT.value and
                node_data.get("interaction_type") == InteractionType.QUESTION.value):
                # 获取最新的学生提问节点
                parent_id = node_data.get("id")

        self.record_interaction(
            session_id=session.id,
            interaction_data={
                "agent_id": teacher.id,
                "agent_name": teacher.name,
                "agent_type": AgentType.TEACHER.value,
                "content": response.strip(),
                "interaction_type": InteractionType.ANSWER.value,
                "knowledge_point_id": None,
                "parent_id": parent_id,  # 关联到最后一个学生提问
            },
        )

        logger.info(f"[TeachingManager] Teacher answered in iteration {iteration}")

    def _parse_supervisor_suggestions(self, content: str, supervisor_id: str, supervisor_name: str, session_id: str, iteration: int) -> List[SupervisorSuggestion]:
        """解析督导点评内容，提取两个维度的建议（简化版）
        
        Args:
            content: 督导点评原文
            supervisor_id: 督导Agent ID
            supervisor_name: 督导Agent名称
            session_id: 会话ID
            iteration: 当前轮次
            
        Returns:
            SupervisorSuggestion 对象列表
        """
        suggestions = []
        
        # 定义维度映射（简化版，只有2个维度）
        dimension_patterns = {
            "teaching_design": ["教学设计", "教学设计点评"],
            "delivery_method": ["讲授方式", "讲授方式点评"],
        }
        
        # 按维度解析建议内容
        for dimension, keywords in dimension_patterns.items():
            for keyword in keywords:
                # 匹配 【关键词】 或 **【关键词】** 等格式
                pattern = rf"(?:^|\n)\s*\*?\s*(?:【)?\s*{re.escape(keyword)}\s*(?:】)?\s*\*?\s*\n(.*?)(?=\n\s*\*?\s*(?:【|总结|$))"
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                
                if match:
                    suggestion_text = match.group(1).strip()
                    # 清理内容，保留结构
                    suggestion_text = re.sub(r'^\s*[-\*]\s*', '- ', suggestion_text, flags=re.MULTILINE)
                    
                    if suggestion_text and len(suggestion_text) > 5:  # 确保内容有意义
                        suggestion = SupervisorSuggestion(
                            session_id=session_id,
                            agent_id=supervisor_id,
                            agent_name=supervisor_name,
                            iteration=iteration,
                            phase=TeachingPhase.SUPERVISOR_COMMENT,
                            suggestion_content=suggestion_text,
                            dimension=dimension,
                        )
                        suggestions.append(suggestion)
                        break  # 找到该维度的建议后跳出关键词循环
        
        # 如果没有解析到任何建议，将整个内容作为一个通用建议
        if not suggestions:
            suggestion = SupervisorSuggestion(
                session_id=session_id,
                agent_id=supervisor_id,
                agent_name=supervisor_name,
                iteration=iteration,
                phase=TeachingPhase.SUPERVISOR_COMMENT,
                suggestion_content=content.strip(),
                dimension="general",
            )
            suggestions.append(suggestion)
        
        return suggestions

    async def _supervisors_comment(self, session: TeachingSession, iteration: int):
        """督导点评"""
        supervisors = self._get_agents_by_type(session, AgentType.SUPERVISOR)

        # 收集本轮各环节的教学内容（完整内容，不截断）
        teaching_content = ""  # 教师讲授内容
        student_questions = []  # 学生问题列表
        teacher_answers = ""  # 教师回答内容
        design_content = ""  # 教学设计内容

        for msg in session.messages:
            if msg.iteration == iteration:
                if msg.phase == TeachingPhase.TEACH_KNOWLEDGE:
                    teaching_content = msg.content
                elif msg.phase == TeachingPhase.STUDENT_QUESTION:
                    student_questions.append(f"{msg.agent_name}: {msg.content}")
                elif msg.phase == TeachingPhase.TEACHER_ANSWER:
                    teacher_answers = msg.content
                elif msg.phase == TeachingPhase.DESIGN:
                    design_content = msg.content

        # 如果没有找到教学设计内容，使用默认的讲课稿
        if not design_content:
            design_content = session.teaching_script if session.teaching_script else "暂无教学设计"

        # 格式化学生问题
        questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(student_questions)]) if student_questions else "本轮学生未提问"

        for supervisor in supervisors:
            context = f"""## 当前教学轮次
第 {iteration} 轮 / 共 {session.max_iterations} 轮

## 教学设计参考
{design_content}

## 本轮教师讲授内容
{teaching_content}

## 本轮学生提出的问题
{questions_text}

## 本轮教师对学生问题的回答
{teacher_answers}

请基于以上完整的教学过程，从教学设计、讲授方式、回答质量三个维度进行全面、深入的专业点评。"""

            # 调用 LLM（使用优化参数）
            try:
                from backend.main import call_minimax_llm
                # 督导点评使用更长的超时时间和更多重试
                response = await call_minimax_llm(
                    prompt=context,
                    system_prompt=supervisor.system_prompt,
                    conversation_history=[],
                    max_tokens=800,  # 限制生成长度
                    timeout_seconds=45.0,  # 增加超时时间
                )
            except Exception as e:
                logger.error(f"[TeachingManager] LLM call failed for supervisor: {e}")
                # 使用预设的降级内容
                response = self._get_default_supervisor_comment(iteration)

            msg = TeachingMessage(
                session_id=session.id,
                agent_id=supervisor.id,
                agent_name=supervisor.name,
                agent_type=AgentType.SUPERVISOR,
                phase=TeachingPhase.SUPERVISOR_COMMENT,
                iteration=iteration,
                content=response.strip(),
            )
            session.messages.append(msg)
            database.save_teaching_message(msg.to_dict())
            await self._broadcast_message(session.id, msg)

            # 解析督导建议并保存
            suggestions = self._parse_supervisor_suggestions(
                content=response.strip(),
                supervisor_id=supervisor.id,
                supervisor_name=supervisor.name,
                session_id=session.id,
                iteration=iteration,
            )
            
            # 保存建议到会话和数据库
            for suggestion in suggestions:
                session.supervisor_suggestions.append(suggestion)
                database.save_supervisor_suggestion(suggestion.to_dict())
                logger.info(f"[TeachingManager] Saved supervisor suggestion: {suggestion.dimension} from {supervisor.name}")

        logger.info(f"[TeachingManager] Supervisors commented in iteration {iteration}")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_agent_by_type(self, session: TeachingSession, agent_type: AgentType) -> Optional[TeachingAgent]:
        """获取指定类型的 Agent"""
        for agent in session.agents:
            if agent.agent_type == agent_type:
                return agent
        return None

    def _get_agents_by_type(self, session: TeachingSession, agent_type: AgentType) -> List[TeachingAgent]:
        """获取所有指定类型的 Agent"""
        return [agent for agent in session.agents if agent.agent_type == agent_type]

    def _get_default_supervisor_comment(self, iteration: int) -> str:
        """获取默认督导点评（降级策略）"""
        default_comments = [
            """**【教学设计】**
优点：教学目标明确，内容结构完整。
建议：可增加更多实际案例辅助理解。

**【讲授方式】**
优点：逻辑清晰，重点突出。
建议：适当调整节奏，给予学生更多思考时间。

**【总结】**
整体教学设计合理，建议在互动性和案例丰富度上进一步优化。""",
            """**【教学设计】**
优点：知识框架清晰，重点难点把握准确。
建议：知识点之间的过渡可以更加自然。

**【讲授方式】**
优点：表达专业规范，符合教学要求。
建议：增加启发式提问，激发学生思考。

**【总结】**
教学基本功扎实，建议在引导学生主动思考方面加强。""",
            """**【教学设计】**
优点：内容充实，覆盖了核心知识点。
建议：难点突破策略可以更加具体。

**【讲授方式】**
优点：讲解细致，易于理解。
建议：适当控制信息量，避免内容过载。

**【总结】**
教学效果良好，建议在内容取舍和学生接受度之间找到更好平衡。""",
        ]
        import random
        return random.choice(default_comments)

    def _get_default_teacher_lecture(self, session: TeachingSession, framework: Dict[str, Any], iteration: int) -> str:
        """获取默认教师讲授内容（降级策略）"""
        topic = framework.get("course_overview", {}).get("topic", "本课程")
        knowledge_points = framework.get("knowledge_points", [])
        kp_titles = [kp.get("title", f"知识点{i+1}") for i, kp in enumerate(knowledge_points[:3])]
        
        if iteration == 1:
            return f"""## 【教学目标】
- 知识目标：掌握{topic}的核心概念与基本原理
- 能力目标：能够运用所学知识分析相关问题
- 素养目标：培养系统思维和问题解决能力

## 【知识框架】
本节课程涵盖以下核心内容：
{chr(10).join([f"- {title}" for title in kp_titles])}

重点：核心概念的理解与应用
难点：知识点的综合运用

## 【详细讲解】
{topic}是本专业的重要组成部分。本节课程将系统介绍相关概念、原理及应用。

首先，我们来看核心概念的定义与内涵。通过理论阐述与实例分析，帮助学习者建立系统的认知框架。

其次，重点讲解关键原理的内在逻辑，分析其适用条件与边界。

最后，结合具体场景，演示如何运用所学知识解决实际问题。

## 【案例分析】
以典型应用场景为例，分析如何将理论知识转化为实践方案。通过案例剖析，深化对知识点的理解。

## 【互动设计】
- 预设问题：学习者可能在概念理解环节存在困惑
- 启发提问：如何将该知识点与已有知识建立联系？
- 思考框架：概念→原理→应用→反思

## 【总结回顾】
本节系统阐述了{topic}的核心内容，包括：
{chr(10).join([f"- {title}的基本概念与原理" for title in kp_titles])}

延伸思考：如何将这些知识点整合应用于复杂问题解决？"""
        else:
            return f"""## 【教学目标】（第{iteration}轮优化）
- 知识目标：深化对{topic}核心概念的理解
- 能力目标：提升知识综合应用能力
- 素养目标：培养批判性思维

## 【知识框架】
基于上一轮督导建议，优化以下内容：
{chr(10).join([f"- {title}" for title in kp_titles])}

## 【详细讲解】
本节在上一轮讲授基础上进行优化。首先，更加精炼地阐述核心概念，避免冗余表述。

其次，针对督导建议，强化重点内容的讲解深度，补充必要的例子说明。

最后，优化知识点的呈现顺序，使逻辑更加清晰，便于学习者理解和记忆。

## 【案例分析】
更新案例选择，确保案例与知识点对应更加精准，分析更加深入。

## 【互动设计】
- 优化问题设计，使其更具启发性
- 增加引导性提示，帮助学习者建立知识联系

## 【总结回顾】
本节优化了{topic}的讲授方式，重点改进了内容组织和呈现方式。"""

    def _format_knowledge_points(self, kps: List[KnowledgePoint]) -> str:
        """格式化知识点列表"""
        if not kps:
            return "无特定知识点"
        return "\n".join([
            f"- {kp.title} ({kp.chapter or '通用'}, {kp.difficulty_level})"
            for kp in kps
        ])

    async def _broadcast_message(self, session_id: str, msg: TeachingMessage):
        """广播消息到 WebSocket"""
        try:
            from backend.main import manager
            if manager:
                await manager.broadcast_to_session(session_id, {
                    "type": "message",
                    "payload": msg.to_dict(),
                })
                logger.debug(f"[TeachingManager] Broadcasted message to session {session_id}")
            else:
                logger.warning(f"[TeachingManager] Cannot broadcast message: manager not available")
        except Exception as e:
            logger.error(f"[TeachingManager] Failed to broadcast message for session {session_id}: {e}")
            # 广播失败不中断教学流程

    async def _broadcast_phase_change(self, session: TeachingSession):
        """广播阶段变化"""
        try:
            from backend.main import manager
            if manager:
                await manager.broadcast_to_session(session.id, {
                    "type": "phase_change",
                    "payload": {
                        "phase": session.current_phase.value if isinstance(session.current_phase, Enum) else session.current_phase,
                    },
                })
                logger.debug(f"[TeachingManager] Broadcasted phase change to {session.current_phase} for session {session.id}")
            else:
                logger.warning(f"[TeachingManager] Cannot broadcast phase change: manager not available")
        except Exception as e:
            logger.error(f"[TeachingManager] Failed to broadcast phase change for session {session.id}: {e}")
            # 广播失败不中断教学流程

    async def _broadcast_iteration_change(self, session: TeachingSession):
        """广播迭代变化"""
        try:
            from backend.main import manager
            if manager:
                await manager.broadcast_to_session(session.id, {
                    "type": "iteration_change",
                    "payload": {
                        "iteration": session.current_iteration,
                        "max_iterations": session.max_iterations,
                    },
                })
                logger.debug(f"[TeachingManager] Broadcasted iteration change to {session.current_iteration} for session {session.id}")
            else:
                logger.warning(f"[TeachingManager] Cannot broadcast iteration change: manager not available")
        except Exception as e:
            logger.error(f"[TeachingManager] Failed to broadcast iteration change for session {session.id}: {e}")
            # 广播失败不中断教学流程

    async def _broadcast_completion(self, session: TeachingSession):
        """广播完成"""
        try:
            from backend.main import manager
            if manager:
                await manager.broadcast_to_session(session.id, {
                    "type": "completion",
                    "payload": {
                        "status": "completed",
                        "teaching_script": session.teaching_script,
                    },
                })
                logger.info(f"[TeachingManager] Broadcasted completion for session {session.id}")
            else:
                logger.warning(f"[TeachingManager] Cannot broadcast completion: manager not available")
        except Exception as e:
            logger.error(f"[TeachingManager] Failed to broadcast completion for session {session.id}: {e}")
            # 广播失败不中断教学流程

    def pause_teaching(self, session_id: str) -> bool:
        """暂停教学"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = TeachingStatus.PAUSED
        session.updated_at = datetime.now()
        database.update_teaching_session(session_id, {"status": TeachingStatus.PAUSED})
        return True

    def resume_teaching(self, session_id: str) -> bool:
        """恢复教学"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = TeachingStatus.TEACHING
        session.updated_at = datetime.now()
        database.update_teaching_session(session_id, {"status": TeachingStatus.TEACHING})

        # 重新启动教学任务
        task = asyncio.create_task(self._run_teaching(session_id))
        self._running_tasks[session_id] = task
        return True

    def stop_teaching(self, session_id: str) -> bool:
        """停止教学"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        # 取消运行中的任务
        if session_id in self._running_tasks:
            self._running_tasks[session_id].cancel()
            del self._running_tasks[session_id]

        session.status = TeachingStatus.FAILED
        session.updated_at = datetime.now()
        database.update_teaching_session(session_id, {"status": TeachingStatus.FAILED})
        return True

    async def next_teaching_step(self, session_id: str) -> bool:
        """教学下一步（手动触发）"""
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] next_teaching_step: Session not found: {session_id}")
            return False

        logger.info(f"[TeachingManager] next_teaching_step called for session {session_id}, current_phase: {session.current_phase}, status: {session.status}")

        if session.status not in [TeachingStatus.TEACHING, TeachingStatus.PAUSED]:
            logger.warning(f"[TeachingManager] Cannot next step, invalid status: {session.status}")
            return False

        try:
            # 根据当前阶段执行相应的教学步骤
            # 如果当前阶段为None或空，从设计阶段开始
            current_phase = session.current_phase
            if current_phase is None or current_phase == "":
                current_phase = TeachingPhase.DESIGN
                session.current_phase = current_phase

            if current_phase == TeachingPhase.DESIGN:
                logger.info(f"[TeachingManager] Executing DESIGN phase step")
                await self._broadcast_phase_change(session)
                await self._design_teaching_process(session)
                # 设计阶段完成后，进入讲授阶段
                session.current_phase = TeachingPhase.TEACH_KNOWLEDGE

            elif current_phase == TeachingPhase.TEACH_KNOWLEDGE:
                logger.info(f"[TeachingManager] Executing TEACH_KNOWLEDGE phase step, iteration {session.current_iteration}")
                await self._broadcast_phase_change(session)
                await self._teacher_teaches(session, session.current_iteration)
                # 讲授完成后，进入提问阶段
                session.current_phase = TeachingPhase.STUDENT_QUESTION

            elif current_phase == TeachingPhase.STUDENT_QUESTION:
                logger.info(f"[TeachingManager] Executing STUDENT_QUESTION phase step, iteration {session.current_iteration}")
                await self._broadcast_phase_change(session)
                await self._students_question(session, session.current_iteration)
                # 提问完成后，进入回答阶段
                session.current_phase = TeachingPhase.TEACHER_ANSWER

            elif current_phase == TeachingPhase.TEACHER_ANSWER:
                logger.info(f"[TeachingManager] Executing TEACHER_ANSWER phase step, iteration {session.current_iteration}")
                await self._broadcast_phase_change(session)
                await self._teacher_answers(session, session.current_iteration)
                # 回答完成后，进入督导点评阶段
                session.current_phase = TeachingPhase.SUPERVISOR_COMMENT

            elif current_phase == TeachingPhase.SUPERVISOR_COMMENT:
                logger.info(f"[TeachingManager] Executing SUPERVISOR_COMMENT phase step, iteration {session.current_iteration}")
                await self._broadcast_phase_change(session)
                await self._supervisors_comment(session, session.current_iteration)
                # 督导点评完成后，进入迭代完成阶段
                session.current_phase = TeachingPhase.ITERATION_COMPLETE

            elif current_phase == TeachingPhase.ITERATION_COMPLETE:
                logger.info(f"[TeachingManager] Current iteration {session.current_iteration} completed")
                # 检查是否还有下一轮
                if session.current_iteration < session.max_iterations:
                    session.current_iteration += 1
                    session.updated_at = datetime.now()
                    try:
                        database.update_teaching_session(session_id, {
                            "current_iteration": session.current_iteration,
                            "current_phase": TeachingPhase.TEACH_KNOWLEDGE.value if isinstance(TeachingPhase.TEACH_KNOWLEDGE, Enum) else TeachingPhase.TEACH_KNOWLEDGE,
                        })
                    except Exception as e:
                        logger.error(f"[TeachingManager] Failed to update session for next iteration: {e}")
                    # 广播迭代变化
                    await self._broadcast_iteration_change(session)
                    # 进入下一轮讲授阶段
                    session.current_phase = TeachingPhase.TEACH_KNOWLEDGE
                    logger.info(f"[TeachingManager] Starting iteration {session.current_iteration}")
                else:
                    # 所有迭代完成
                    logger.info(f"[TeachingManager] All iterations completed, finishing teaching")
                    session.status = TeachingStatus.COMPLETED
                    session.completed_at = datetime.now()
                    try:
                        database.update_teaching_session(session_id, {
                            "status": TeachingStatus.COMPLETED.value if isinstance(TeachingStatus.COMPLETED, Enum) else TeachingStatus.COMPLETED,
                            "completed_at": session.completed_at.isoformat(),
                        })
                    except Exception as e:
                        logger.error(f"[TeachingManager] Failed to update session status to COMPLETED: {e}")
                    await self._broadcast_completion(session)

            else:
                logger.warning(f"[TeachingManager] Unknown phase: {current_phase}")
                return False

            # 保存当前状态到数据库
            try:
                database.update_teaching_session(session_id, {
                    "current_phase": session.current_phase.value if isinstance(session.current_phase, Enum) else session.current_phase,
                    "current_iteration": session.current_iteration,
                })
            except Exception as e:
                logger.error(f"[TeachingManager] Failed to save session state: {e}")

            logger.info(f"[TeachingManager] next_teaching_step completed, new phase: {session.current_phase}")
            return True

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to execute next step: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[TeachingManager] Traceback: {traceback.format_exc()}")
            return False

    # =========================================================================
    # Learning Objectives Management
    # =========================================================================

    def create_learning_objective(
        self,
        session_id: str,
        description: str,
        objective_type: str = "knowledge",
        priority: str = "medium",
        related_knowledge_points: Optional[List[str]] = None,
    ) -> Optional[LearningObjective]:
        """创建学习目标

        Args:
            session_id: 会话ID
            description: 目标描述
            objective_type: 目标类型 (knowledge/skill/attitude)
            priority: 优先级 (high/medium/low)
            related_knowledge_points: 关联的知识点ID列表

        Returns:
            创建的 LearningObjective 对象
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return None

        try:
            # 验证 objective_type
            valid_types = ["knowledge", "skill", "attitude"]
            if objective_type not in valid_types:
                objective_type = "knowledge"

            # 验证 priority
            valid_priorities = ["high", "medium", "low"]
            if priority not in valid_priorities:
                priority = "medium"

            # 创建学习目标
            objective = LearningObjective(
                session_id=session_id,
                description=description,
                objective_type=objective_type,
                priority=priority,
                related_knowledge_points=related_knowledge_points or [],
            )

            # 添加到会话
            session.learning_objectives.append(objective.to_dict())
            session.updated_at = datetime.now()

            # 持久化到数据库
            database.update_teaching_session(session_id, {
                "learning_objectives": session.learning_objectives,
                "updated_at": session.updated_at.isoformat(),
            })

            logger.info(f"[TeachingManager] Created learning objective {objective.id} for session {session_id}")
            return objective

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to create learning objective: {e}")
            return None

    def get_learning_objectives(self, session_id: str) -> List[LearningObjective]:
        """获取会话的所有学习目标

        Args:
            session_id: 会话ID

        Returns:
            LearningObjective 对象列表
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return []

        try:
            objectives = []
            for obj_data in session.learning_objectives:
                try:
                    objective = LearningObjective.from_dict(obj_data)
                    objectives.append(objective)
                except Exception as e:
                    logger.warning(f"[TeachingManager] Failed to parse learning objective: {e}")
                    continue
            return objectives

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to get learning objectives: {e}")
            return []

    def delete_learning_objective(self, session_id: str, objective_id: str) -> bool:
        """删除学习目标

        Args:
            session_id: 会话ID
            objective_id: 目标ID

        Returns:
            是否删除成功
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return False

        try:
            # 找到并删除目标
            original_count = len(session.learning_objectives)
            session.learning_objectives = [
                obj for obj in session.learning_objectives
                if obj.get("id") != objective_id
            ]

            if len(session.learning_objectives) == original_count:
                logger.warning(f"[TeachingManager] Learning objective not found: {objective_id}")
                return False

            # 同时删除相关的评估结果
            session.objective_assessments = [
                ass for ass in session.objective_assessments
                if ass.get("objective_id") != objective_id
            ]

            session.updated_at = datetime.now()

            # 持久化到数据库
            database.update_teaching_session(session_id, {
                "learning_objectives": session.learning_objectives,
                "objective_assessments": session.objective_assessments,
                "updated_at": session.updated_at.isoformat(),
            })

            logger.info(f"[TeachingManager] Deleted learning objective {objective_id}")
            return True

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to delete learning objective: {e}")
            return False

    # =========================================================================
    # Objective Assessment (LLM-based Coverage Analysis)
    # =========================================================================

    async def assess_objective_coverage(
        self,
        session_id: str,
        objective_id: str,
    ) -> Optional[ObjectiveAssessment]:
        """评估单个学习目标的覆盖度（使用LLM分析）

        Args:
            session_id: 会话ID
            objective_id: 目标ID

        Returns:
            ObjectiveAssessment 对象
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return None

        try:
            # 获取学习目标
            objective_data = None
            for obj in session.learning_objectives:
                if obj.get("id") == objective_id:
                    objective_data = obj
                    break

            if not objective_data:
                logger.warning(f"[TeachingManager] Learning objective not found: {objective_id}")
                return None

            objective = LearningObjective.from_dict(objective_data)

            # 收集教学内容
            teaching_content = self._collect_teaching_content(session)

            # 构建LLM提示词
            prompt = self._build_assessment_prompt(objective, teaching_content)

            # 调用LLM进行评估（使用优化参数）
            from backend.main import call_minimax_llm
            response = await call_minimax_llm(
                prompt=prompt,
                system_prompt=self._get_assessment_system_prompt(),
                conversation_history=[],
                max_tokens=1500,  # 评估结果适中长度
                timeout_seconds=30.0,
            )

            # 解析评估结果
            assessment_data = self._parse_assessment_response(response, objective_id)

            # 创建评估对象
            assessment = ObjectiveAssessment(
                session_id=session_id,
                objective_id=objective_id,
                coverage_score=assessment_data.get("coverage_score", 0.0),
                evidence=assessment_data.get("evidence", ""),
                gaps=assessment_data.get("gaps", []),
                suggestions=assessment_data.get("suggestions", []),
            )

            # 保存评估结果（更新或添加）
            self._save_objective_assessment(session, assessment)

            logger.info(f"[TeachingManager] Assessed objective {objective_id}, score: {assessment.coverage_score}")
            return assessment

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to assess objective coverage: {e}")
            return None

    async def assess_all_objectives(self, session_id: str) -> List[ObjectiveAssessment]:
        """评估会话的所有学习目标

        Args:
            session_id: 会话ID

        Returns:
            ObjectiveAssessment 对象列表
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return []

        objectives = self.get_learning_objectives(session_id)
        if not objectives:
            logger.info(f"[TeachingManager] No learning objectives to assess for session {session_id}")
            return []

        assessments = []
        for objective in objectives:
            assessment = await self.assess_objective_coverage(session_id, objective.id)
            if assessment:
                assessments.append(assessment)

        logger.info(f"[TeachingManager] Assessed {len(assessments)} objectives for session {session_id}")
        return assessments

    def _collect_teaching_content(self, session: TeachingSession) -> Dict[str, str]:
        """收集教学内容用于评估

        Args:
            session: 教学会话

        Returns:
            包含教学内容的字典
        """
        # 收集讲课稿
        teaching_script = session.teaching_script or ""

        # 收集所有教师讲授的消息
        teacher_messages = []
        for msg in session.messages:
            if msg.agent_type == AgentType.TEACHER and msg.content:
                teacher_messages.append(f"[{msg.phase.value if isinstance(msg.phase, Enum) else msg.phase}] {msg.agent_name}: {msg.content}")

        # 收集互动内容
        interaction_content = []
        for node_data in session.interaction_path:
            content = node_data.get("content", "")
            agent_name = node_data.get("agent_name", "")
            if content:
                interaction_content.append(f"{agent_name}: {content}")

        return {
            "teaching_script": teaching_script,
            "teacher_messages": "\n\n".join(teacher_messages),
            "interactions": "\n".join(interaction_content),
        }

    def _build_assessment_prompt(
        self,
        objective: LearningObjective,
        teaching_content: Dict[str, str],
    ) -> str:
        """构建评估提示词

        Args:
            objective: 学习目标
            teaching_content: 教学内容

        Returns:
            提示词字符串
        """
        # 构建关联知识点信息
        related_kp_text = ""
        if objective.related_knowledge_points:
            related_kp_text = "关联知识点: " + ", ".join(objective.related_knowledge_points)

        prompt = f"""## 学习目标评估任务

### 学习目标
- 描述: {objective.description}
- 类型: {objective.objective_type}
- 优先级: {objective.priority}
{related_kp_text}

### 教学内容

#### 讲课稿
{teaching_content['teaching_script'][:2000] if teaching_content['teaching_script'] else '（无讲课稿）'}

#### 教师讲授内容
{teaching_content['teacher_messages'][:2000] if teaching_content['teacher_messages'] else '（无讲授内容）'}

#### 互动内容
{teaching_content['interactions'][:1500] if teaching_content['interactions'] else '（无互动内容）'}

### 评估要求

请分析教学内容与学习目标的相关性，并按以下JSON格式返回评估结果:

```json
{{
    "coverage_score": 0-100之间的数值,
    "evidence": "支持评估结论的具体证据文本，引用教学内容中的相关内容",
    "gaps": ["未覆盖的内容1", "未覆盖的内容2"],
    "suggestions": ["改进建议1", "改进建议2"]
}}
```

评分标准:
- 90-100: 完全覆盖，讲解深入透彻
- 70-89: 基本覆盖，但深度或广度有所欠缺
- 50-69: 部分覆盖，有明显遗漏
- 0-49: 覆盖度低，几乎未涉及

请确保返回格式严格符合JSON要求。"""

        return prompt

    def _get_assessment_system_prompt(self) -> str:
        """获取评估系统的提示词"""
        return """你是一名专业的教学评估专家，擅长分析教学内容与学习目标的匹配度。

你的任务是:
1. 仔细阅读学习目标，理解其核心要求
2. 分析教学内容，找出与目标相关的内容
3. 客观评估覆盖程度，给出0-100的分数
4. 提供具体证据支持你的评估
5. 指出未覆盖的内容（gaps）
6. 给出可操作的改进建议（suggestions）

评估原则:
- 客观公正，基于实际内容评估
- 证据要具体，引用原文内容
- gaps要明确指出缺失的内容
- suggestions要具体可操作
- 必须以JSON格式返回结果"""

    def _parse_assessment_response(self, response: str, objective_id: str) -> Dict[str, Any]:
        """解析LLM返回的评估结果

        Args:
            response: LLM响应内容
            objective_id: 目标ID

        Returns:
            解析后的评估数据字典
        """
        import json
        import re

        try:
            # 尝试从响应中提取JSON
            # 首先尝试找到```json ... ```格式的内容
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试找到```...```格式的内容
                json_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # 尝试找到{...}格式的内容
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                    else:
                        json_str = response

            # 清理JSON字符串
            json_str = json_str.strip()

            # 解析JSON
            data = json.loads(json_str)

            # 验证和规范化数据
            result = {
                "coverage_score": float(data.get("coverage_score", 0)),
                "evidence": str(data.get("evidence", "")),
                "gaps": data.get("gaps", []) if isinstance(data.get("gaps"), list) else [],
                "suggestions": data.get("suggestions", []) if isinstance(data.get("suggestions"), list) else [],
            }

            # 确保分数在0-100范围内
            result["coverage_score"] = max(0, min(100, result["coverage_score"]))

            return result

        except Exception as e:
            logger.warning(f"[TeachingManager] Failed to parse assessment response: {e}")
            # 返回默认评估结果
            return {
                "coverage_score": 0.0,
                "evidence": "解析评估结果失败",
                "gaps": ["无法确定"],
                "suggestions": ["请重新进行评估"],
            }

    def _save_objective_assessment(self, session: TeachingSession, assessment: ObjectiveAssessment):
        """保存或更新目标评估结果

        Args:
            session: 教学会话
            assessment: 评估对象
        """
        # 查找是否已存在该目标的评估
        existing_index = None
        for i, ass_data in enumerate(session.objective_assessments):
            if ass_data.get("objective_id") == assessment.objective_id:
                existing_index = i
                break

        if existing_index is not None:
            # 更新现有评估
            session.objective_assessments[existing_index] = assessment.to_dict()
        else:
            # 添加新评估
            session.objective_assessments.append(assessment.to_dict())

        session.updated_at = datetime.now()

        # 持久化到数据库
        database.update_teaching_session(session.id, {
            "objective_assessments": session.objective_assessments,
            "updated_at": session.updated_at.isoformat(),
        })

    def get_objective_assessments(self, session_id: str) -> List[ObjectiveAssessment]:
        """获取会话的所有目标评估结果

        Args:
            session_id: 会话ID

        Returns:
            ObjectiveAssessment 对象列表
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return []

        try:
            assessments = []
            for ass_data in session.objective_assessments:
                try:
                    assessment = ObjectiveAssessment.from_dict(ass_data)
                    assessments.append(assessment)
                except Exception as e:
                    logger.warning(f"[TeachingManager] Failed to parse objective assessment: {e}")
                    continue
            return assessments

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to get objective assessments: {e}")
            return []

    # =========================================================================
    # Quiz Management
    # =========================================================================

    def _load_quizzes_from_db(self):
        """从数据库加载测验数据"""
        try:
            quizzes_data = database.load_quizzes()
            for data in quizzes_data:
                quiz = Quiz.from_dict(data)
                self._quizzes[quiz.id] = quiz

                # 加载题目
                questions_data = database.load_quiz_questions(quiz.id)
                quiz.questions = [QuizQuestion.from_dict(q) for q in questions_data]
                self._quiz_questions[quiz.id] = quiz.questions

            logger.info(f"[TeachingManager] Loaded {len(self._quizzes)} quizzes from database")
        except Exception as e:
            logger.warning(f"[TeachingManager] Failed to load quizzes: {e}")

    async def generate_quiz(
        self,
        session_id: str,
        title: Optional[str] = None,
        question_count: int = 10,
        question_types: Optional[List[str]] = None,
    ) -> Optional[Quiz]:
        """基于教学内容自动生成测验

        Args:
            session_id: 会话ID
            title: 测验标题（可选，默认自动生成）
            question_count: 题目数量（默认10题）
            question_types: 题型列表（默认 ["single_choice", "fill_blank"]）

        Returns:
            Quiz 对象
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[TeachingManager] Session not found: {session_id}")
            return None

        try:
            # 设置默认值
            if not question_types:
                question_types = ["single_choice", "fill_blank"]

            if not title:
                title = f"{session.title} - 知识点测验"

            # 创建测验对象
            quiz = Quiz(
                session_id=session_id,
                title=title,
                description=f"基于教学内容自动生成的测验，共{question_count}题",
                total_score=question_count * 10.0,
                passing_score=question_count * 10.0 * 0.6,
            )

            # 使用LLM生成题目
            questions = await self._generate_quiz_questions_with_llm(
                session=session,
                quiz_id=quiz.id,
                question_count=question_count,
                question_types=question_types,
            )

            if not questions:
                logger.warning(f"[TeachingManager] Failed to generate quiz questions")
                return None

            # 设置题目
            quiz.questions = questions
            self._quiz_questions[quiz.id] = questions
            self._quizzes[quiz.id] = quiz

            # 更新会话的测验ID
            session.quiz_id = quiz.id
            database.update_teaching_session(session_id, {"quiz_id": quiz.id})

            # 持久化到数据库
            database.save_quiz(quiz.to_dict())
            for question in questions:
                database.save_quiz_question(question.to_dict())

            logger.info(f"[TeachingManager] Generated quiz {quiz.id} with {len(questions)} questions")
            return quiz

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to generate quiz: {e}")
            return None

    async def _generate_quiz_questions_with_llm(
        self,
        session: TeachingSession,
        quiz_id: str,
        question_count: int,
        question_types: List[str],
    ) -> List[QuizQuestion]:
        """使用LLM生成测验题目

        Args:
            session: 教学会话
            quiz_id: 测验ID
            question_count: 题目数量
            question_types: 题型列表

        Returns:
            QuizQuestion 列表
        """
        # 构建教学内容文本
        teaching_content = self._build_teaching_content_for_quiz(session)

        # 构建知识点文本
        knowledge_points_text = self._format_knowledge_points_for_quiz(session.knowledge_points)

        # 构建提示词
        prompt = self._build_quiz_generation_prompt(
            teaching_content=teaching_content,
            knowledge_points=knowledge_points_text,
            question_count=question_count,
            question_types=question_types,
        )

        # 调用LLM（使用优化参数）
        from backend.main import call_minimax_llm
        response = await call_minimax_llm(
            prompt=prompt,
            system_prompt=self._get_quiz_generation_system_prompt(),
            conversation_history=[],
            max_tokens=3000,  # 测验生成需要较多token
            timeout_seconds=45.0,  # 测验生成需要更多时间
        )

        # 解析生成的题目
        questions = self._parse_quiz_questions(response, quiz_id, question_types)

        return questions

    def _build_teaching_content_for_quiz(self, session: TeachingSession) -> str:
        """构建用于生成测验的教学内容"""
        content_parts = []

        # 讲课稿
        if session.teaching_script:
            content_parts.append(f"## 讲课稿\n{session.teaching_script}")

        # 教学框架
        if session.teaching_framework:
            framework = session.teaching_framework
            if "knowledge_points" in framework:
                content_parts.append("## 知识点详情")
                for kp in framework["knowledge_points"]:
                    content_parts.append(f"- {kp.get('title', '')}: {kp.get('key_content', '')}")

        # 教师消息
        teacher_messages = [
            msg.content for msg in session.messages
            if msg.agent_type == AgentType.TEACHER and msg.content
        ]
        if teacher_messages:
            content_parts.append("## 教师讲授内容")
            for i, msg in enumerate(teacher_messages[-3:], 1):  # 取最近3条
                content_parts.append(f"{i}. {msg[:300]}...")

        return "\n\n".join(content_parts)

    def _format_knowledge_points_for_quiz(self, knowledge_points: List) -> str:
        """格式化知识点用于生成测验"""
        if not knowledge_points:
            return "无特定知识点"

        lines = []
        for i, kp in enumerate(knowledge_points, 1):
            line = f"{i}. {kp.title}"
            if hasattr(kp, 'chapter') and kp.chapter:
                line += f" (章节: {kp.chapter})"
            if hasattr(kp, 'is_key_point') and kp.is_key_point:
                line += " [重点]"
            if hasattr(kp, 'difficulty_level') and kp.difficulty_level:
                line += f" [难度: {kp.difficulty_level}]"
            lines.append(line)

        return "\n".join(lines)

    def _build_quiz_generation_prompt(
        self,
        teaching_content: str,
        knowledge_points: str,
        question_count: int,
        question_types: List[str],
    ) -> str:
        """构建生成测验题目的提示词"""
        type_descriptions = {
            "single_choice": "单选题（4个选项，只有一个正确答案）",
            "multi_choice": "多选题（4个选项，有多个正确答案）",
            "fill_blank": "填空题（填写关键词或短语）",
            "short_answer": "简答题（用几句话回答）",
        }

        type_desc_text = "\n".join([
            f"- {t}: {type_descriptions.get(t, t)}"
            for t in question_types
        ])

        return f"""## 任务
基于以下教学内容和知识点，生成{question_count}道测验题目。

## 教学内容
{teaching_content[:3000]}

## 知识点列表
{knowledge_points}

## 题目要求
1. 题目总数：{question_count}道
2. 可选题型：
{type_desc_text}

3. 难度分布：
   - easy（简单）: 40%
   - medium（中等）: 40%
   - hard（困难）: 20%

4. 每题必须包含：
   - 题目文本
   - 题型（从上面可选题型中选择）
   - 正确答案
   - 答案解析（解释为什么是这个答案）
   - 关联知识点（从知识点列表中选择）
   - 难度等级（easy/medium/hard）

## 输出格式
请以JSON数组格式输出，每道题一个对象：

```json
[
  {{
    "question_type": "single_choice",
    "question_text": "题目内容",
    "options": ["选项A", "选项B", "选项C", "选项D"],
    "correct_answer": "选项A",
    "explanation": "答案解析",
    "knowledge_point_title": "关联的知识点名称",
    "difficulty": "medium"
  }},
  {{
    "question_type": "fill_blank",
    "question_text": "填空题内容，用____表示填空位置",
    "options": [],
    "correct_answer": "正确答案",
    "explanation": "答案解析",
    "knowledge_point_title": "关联的知识点名称",
    "difficulty": "easy"
  }},
  {{
    "question_type": "short_answer",
    "question_text": "简答题内容",
    "options": [],
    "correct_answer": "参考答案要点",
    "explanation": "评分标准和答案解析",
    "knowledge_point_title": "关联的知识点名称",
    "difficulty": "hard"
  }}
]
```

## 注意事项
1. 单选题和多选题必须有4个选项
2. 多选题的correct_answer可以是多个选项，用逗号分隔，如"选项A,选项B"
3. 填空题用____表示填空位置
4. 确保题目与教学内容紧密相关
5. 难度分布要合理
6. 覆盖不同的知识点

请生成高质量的测验题目。"""

    def _get_quiz_generation_system_prompt(self) -> str:
        """获取生成测验的系统提示词"""
        return """你是一位资深的教育专家，擅长设计高质量的测验题目。

你的任务是：
1. 深入理解教学内容
2. 针对每个知识点设计恰当的题目
3. 确保题目考察学生对知识点的理解程度
4. 提供清晰的答案解析
5. 合理设置难度等级

设计要求：
- 单选题：考查基础知识的识记和理解
- 多选题：考查知识的综合运用能力
- 填空题：考查关键概念的准确掌握
- 简答题：考查知识的深入理解和表达能力

输出要求：
- 必须以有效的JSON格式输出
- 确保所有字段完整
- 题目表述清晰准确
- 答案解析详尽有帮助"""

    def _parse_quiz_questions(
        self,
        response: str,
        quiz_id: str,
        allowed_types: List[str],
    ) -> List[QuizQuestion]:
        """解析LLM生成的测验题目"""
        questions = []

        try:
            # 提取JSON内容
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if not json_match:
                # 尝试找到 ```json ... ``` 格式
                json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response
            else:
                json_str = json_match.group(0)

            data = json.loads(json_str)

            if not isinstance(data, list):
                logger.warning("[TeachingManager] Quiz generation response is not a list")
                return questions

            for item in data:
                try:
                    question_type_str = item.get("question_type", "single_choice")
                    if question_type_str not in allowed_types:
                        question_type_str = allowed_types[0] if allowed_types else "single_choice"

                    question_type = QuizType(question_type_str)

                    question = QuizQuestion(
                        quiz_id=quiz_id,
                        question_type=question_type,
                        question_text=item.get("question_text", ""),
                        options=item.get("options", []),
                        correct_answer=item.get("correct_answer", ""),
                        explanation=item.get("explanation", ""),
                        knowledge_point_title=item.get("knowledge_point_title", ""),
                        difficulty=item.get("difficulty", "medium"),
                        score=10.0,
                    )
                    questions.append(question)
                except Exception as e:
                    logger.warning(f"[TeachingManager] Failed to parse quiz question: {e}")
                    continue

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to parse quiz questions: {e}")

        return questions

    def get_quiz(self, quiz_id: str) -> Optional[Quiz]:
        """获取测验信息（包含题目列表）

        Args:
            quiz_id: 测验ID

        Returns:
            Quiz 对象（包含 questions 列表）
        """
        quiz = self._quizzes.get(quiz_id)
        if not quiz:
            logger.warning(f"[TeachingManager] Quiz not found: {quiz_id}")
            return None

        # 确保包含题目列表
        quiz.questions = self._quiz_questions.get(quiz_id, [])
        return quiz

    async def submit_quiz_answers(
        self,
        quiz_id: str,
        answers: List[Dict[str, Any]],
    ) -> Optional[QuizResult]:
        """提交测验答案并评分

        Args:
            quiz_id: 测验ID
            answers: 答案列表，每项包含 question_id 和 answer_text

        Returns:
            QuizResult 对象
        """
        quiz = self._quizzes.get(quiz_id)
        if not quiz:
            logger.warning(f"[TeachingManager] Quiz not found: {quiz_id}")
            return None

        questions = self._quiz_questions.get(quiz_id, [])
        if not questions:
            logger.warning(f"[TeachingManager] No questions found for quiz: {quiz_id}")
            return None

        try:
            # 构建题目字典
            questions_dict = {q.id: q for q in questions}

            # 评分
            quiz_answers = []
            total_score = 0.0
            max_score = 0.0
            weak_knowledge_points = []

            for answer_data in answers:
                question_id = answer_data.get("question_id")
                answer_text = answer_data.get("answer_text", "")

                question = questions_dict.get(question_id)
                if not question:
                    continue

                # 计算得分
                score, is_correct = await self._score_answer(question, answer_text)

                quiz_answer = QuizAnswer(
                    quiz_id=quiz_id,
                    question_id=question_id,
                    answer_text=answer_text,
                    is_correct=is_correct,
                    score=score,
                )
                quiz_answers.append(quiz_answer)
                total_score += score
                max_score += question.score

                # 记录薄弱知识点
                if not is_correct and question.knowledge_point_title:
                    weak_knowledge_points.append(question.knowledge_point_title)

            # 判断是否通过
            passed = total_score >= quiz.passing_score

            # 生成改进建议
            improvement_suggestions = self._generate_improvement_suggestions(
                quiz_answers, questions_dict, weak_knowledge_points
            )

            # 去重薄弱知识点
            weak_knowledge_points = list(set(weak_knowledge_points))

            # 创建结果
            result = QuizResult(
                quiz_id=quiz_id,
                total_score=round(total_score, 2),
                max_score=max_score,
                passed=passed,
                answers=quiz_answers,
                weak_knowledge_points=weak_knowledge_points,
                improvement_suggestions=improvement_suggestions,
            )

            # 保存结果
            self._quiz_results[quiz_id] = result
            database.save_quiz_result(result.to_dict())

            logger.info(f"[TeachingManager] Quiz {quiz_id} submitted, score: {total_score}/{max_score}")
            return result

        except Exception as e:
            logger.error(f"[TeachingManager] Failed to submit quiz answers: {e}")
            return None

    async def _score_answer(self, question: QuizQuestion, answer_text: str) -> tuple[float, bool]:
        """评分单个答案

        Args:
            question: 题目
            answer_text: 用户答案

        Returns:
            (得分, 是否正确)
        """
        answer_text = answer_text.strip()
        correct_answer = question.correct_answer.strip()

        if question.question_type == QuizType.SINGLE_CHOICE:
            # 单选题：完全匹配
            is_correct = answer_text.lower() == correct_answer.lower()
            score = question.score if is_correct else 0.0

        elif question.question_type == QuizType.MULTI_CHOICE:
            # 多选题：完全匹配所有正确选项
            user_answers = set(a.strip().lower() for a in answer_text.split(","))
            correct_answers = set(a.strip().lower() for a in correct_answer.split(","))
            is_correct = user_answers == correct_answers
            score = question.score if is_correct else 0.0

        elif question.question_type == QuizType.FILL_BLANK:
            # 填空题：关键词匹配
            score, is_correct = self._score_fill_blank(question, answer_text)

        elif question.question_type == QuizType.SHORT_ANSWER:
            # 简答题：使用LLM评估
            score, is_correct = await self._score_short_answer(question, answer_text)

        else:
            score = 0.0
            is_correct = False

        return score, is_correct

    def _score_fill_blank(self, question: QuizQuestion, answer_text: str) -> tuple[float, bool]:
        """评分填空题

        使用关键词匹配算法，匹配核心关键词
        """
        correct_answer = question.correct_answer.strip()

        # 简单匹配：完全匹配得满分
        if answer_text.lower() == correct_answer.lower():
            return question.score, True

        # 提取关键词（去掉停用词）
        def extract_keywords(text: str) -> set:
            stop_words = {"的", "了", "在", "是", "和", "与", "或", "等", "及", "而", "但", "为", "有", "被", "把", "从", "到", "对", "向", "比", "跟", "同", "给", "让", "叫", "使", "令", "由于", "根据", "按照", "通过", "对于", "关于", "至于", "由于", "因为", "所以", "因此", "如果", "虽然", "但是", "然而", "可是", "不过", "只是", "即使", "尽管", "不管", "无论", "不论", "不但", "而且", "并且", "或者", "还是", "要么", "假如", "假定", "譬如", "例如", "比如", "像是", "像是", "像", "似的", "似乎", "好像", "如同", "好比", "一样", "一般", "通常", "常常", "经常", "往往", "一直", "始终", "永远", "永久", "暂时", "临时", "目前", "当前", "现在", "如今", "今天", "明天", "昨天", "前天", "后天", "上午", "下午", "晚上", "早上", "中午", "午夜", "凌晨", "傍晚", "清晨", "深夜", "时刻", "时候", "时间", "时期", "期间", "阶段", "时代", "年代", "年份", "月份", "日期", "星期", "季节", "春天", "夏天", "秋天", "冬天", "一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"}
            words = re.findall(r'\b\w+\b', text.lower())
            return set(w for w in words if w not in stop_words and len(w) > 1)

        correct_keywords = extract_keywords(correct_answer)
        answer_keywords = extract_keywords(answer_text)

        if not correct_keywords:
            return (question.score * 0.5, False) if answer_text else (0.0, False)

        # 计算匹配度
        matched = correct_keywords & answer_keywords
        match_ratio = len(matched) / len(correct_keywords)

        # 根据匹配度给分
        if match_ratio >= 0.8:
            return question.score, True
        elif match_ratio >= 0.5:
            return question.score * 0.5, False
        elif match_ratio > 0:
            return question.score * 0.2, False
        else:
            return 0.0, False

    async def _score_short_answer(self, question: QuizQuestion, answer_text: str) -> tuple[float, bool]:
        """使用LLM评估简答题

        返回得分和是否正确（得分>=60%视为正确）
        """
        if not answer_text.strip():
            return 0.0, False

        prompt = f"""## 简答题评分任务

### 题目
{question.question_text}

### 参考答案
{question.correct_answer}

### 学生答案
{answer_text}

### 评分要求
请评估学生答案的质量，给出0-100的分数。

评分标准：
- 90-100分：答案完整准确，表达清晰，完全覆盖参考答案的要点
- 70-89分：答案基本正确，涵盖了主要要点，但可能缺少一些细节
- 50-69分：答案部分正确，涵盖了一些要点，但有明显遗漏或错误
- 30-49分：答案与问题相关，但内容较少或有不准确之处
- 0-29分：答案错误或与问题无关

### 输出格式
请只输出一个JSON对象：
```json
{{
    "score": 0-100之间的整数,
    "reasoning": "评分的简要理由"
}}
```"""

        try:
            from backend.main import call_minimax_llm
            # 评分调用使用较短超时
            response = await call_minimax_llm(
                prompt=prompt,
                system_prompt="你是一位严谨的评分专家，擅长评估学生答案的质量。请客观公正地评分。",
                conversation_history=[],
                max_tokens=500,  # 评分结果简短
                timeout_seconds=15.0,  # 评分快速完成
            )

            # 解析分数
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                score_ratio = float(data.get("score", 0)) / 100.0
            else:
                # 尝试直接提取数字
                numbers = re.findall(r'\b(\d+)\b', response)
                if numbers:
                    score_ratio = int(numbers[0]) / 100.0
                else:
                    score_ratio = 0.5  # 默认中等分数

            # 限制范围
            score_ratio = max(0.0, min(1.0, score_ratio))
            final_score = question.score * score_ratio
            is_correct = score_ratio >= 0.6

            return round(final_score, 2), is_correct

        except Exception as e:
            logger.warning(f"[TeachingManager] LLM scoring failed: {e}")
            # LLM评分失败时，使用简单匹配
            if answer_text.strip():
                return question.score * 0.5, False
            return 0.0, False

    def _generate_improvement_suggestions(
        self,
        answers: List[QuizAnswer],
        questions_dict: Dict[str, QuizQuestion],
        weak_knowledge_points: List[str],
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 统计正确率
        total = len(answers)
        correct = sum(1 for a in answers if a.is_correct)
        accuracy = correct / total if total > 0 else 0

        # 根据正确率给出总体建议
        if accuracy < 0.4:
            suggestions.append("整体掌握程度较低，建议重新学习相关知识点")
        elif accuracy < 0.7:
            suggestions.append("整体掌握尚可，但需要加强对重点知识的理解")
        else:
            suggestions.append("整体掌握良好，继续保持并深化理解")

        # 针对薄弱知识点给出建议
        if weak_knowledge_points:
            unique_weak_points = list(set(weak_knowledge_points))[:3]  # 最多3个
            suggestions.append(f"建议重点复习以下知识点：{', '.join(unique_weak_points)}")

        # 针对题型给出建议
        wrong_questions = [
            questions_dict.get(a.question_id)
            for a in answers
            if not a.is_correct and a.question_id in questions_dict
        ]

        type_stats = {}
        for q in wrong_questions:
            if q:
                type_name = q.question_type.value if hasattr(q.question_type, 'value') else str(q.question_type)
                type_stats[type_name] = type_stats.get(type_name, 0) + 1

        if "short_answer" in type_stats and type_stats["short_answer"] > 1:
            suggestions.append("简答题得分较低，建议多练习开放性问题的表达能力")

        if "fill_blank" in type_stats and type_stats["fill_blank"] > 1:
            suggestions.append("填空题需要加强对关键词汇的记忆")

        return suggestions

    def get_quiz_results(self, quiz_id: str) -> Optional[QuizResult]:
        """获取测验结果

        Args:
            quiz_id: 测验ID

        Returns:
            QuizResult 对象
        """
        # 先检查内存
        result = self._quiz_results.get(quiz_id)
        if result:
            return result

        # 从数据库加载
        try:
            result_data = database.load_quiz_result(quiz_id)
            if result_data:
                result = QuizResult.from_dict(result_data)
                self._quiz_results[quiz_id] = result
                return result
        except Exception as e:
            logger.warning(f"[TeachingManager] Failed to load quiz result: {e}")

        return None


# 全局单例
_teaching_manager: Optional[TeachingSessionManager] = None


def get_teaching_manager() -> TeachingSessionManager:
    """获取教学管理器单例"""
    global _teaching_manager
    if _teaching_manager is None:
        _teaching_manager = TeachingSessionManager()
    return _teaching_manager
