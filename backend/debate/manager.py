"""
辩论会话管理器 - DebateSessionManager
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend import database
from backend.message_bus.bus import MessageBus, Message

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

logger = logging.getLogger(__name__)


# 辩论 Agent 系统提示词模板
DEBATE_PROMPTS = {
    AgentRole.PROPONENT: """你是一名辩论正方。你需要支持文档中的观点，提供有力的论据。

## 辩论主题
{topic}

## 关键知识点
{points}

## 你的角色
- 你是正方，支持文档中的主要观点
- 用清晰、有逻辑的论据支持你的立场
- 可以质疑反方的论点，但要有理有据
- 用中文回答

## 回复格式
直接输出你的辩论内容，不要有额外的格式。""",

    AgentRole.OPPONENT: """你是一名辩论反方。你需要质疑和反驳文档中的观点。

## 辩论主题
{topic}

## 关键知识点
{points}

## 你的角色
- 你是反方，对文档中的观点持怀疑态度
- 寻找论点中的漏洞和不足
- 提出合理的质疑和反驳
- 用中文回答

## 回复格式
直接输出你的辩论内容，不要有额外的格式。""",

    AgentRole.MODERATOR: """你是一名辩论主持人。你需要引导辩论走向中立，点评双方的论点。

## 辩论主题
{topic}

## 关键知识点
{points}

## 你的角色
- 你是主持人，保持中立
- 点评正方和反方的论点
- 引导辩论聚焦于核心分歧
- 用中文回答

## 回复格式
直接输出你的点评内容，不要有额外的格式。""",

    AgentRole.REPORTER: """你是一名辩论汇报员。你需要根据辩论内容生成一份综合报告。

## 辩论主题
{topic}

## 辩论过程
{debate_history}

## 你的任务
1. 总结正方和反方的主要观点
2. 指出双方的论据优势和弱点
3. 分析辩论的焦点和分歧
4. 提出客观的结论和建议
5. 用中文输出

## 输出格式
输出一个 JSON 对象：
{{
  "summary": "辩论总结（200字以内）",
  "proponent_points": ["要点1", "要点2", "要点3"],
  "opponent_points": ["要点1", "要点2", "要点3"],
  "key_disagreements": ["分歧1", "分歧2"],
  "conclusion": "客观结论",
  "suggestions": ["建议1", "建议2"]
}}
""",
}


class DebateSessionManager:
    """
    辩论会话管理器

    职责：
    - 创建和管理辩论会话
    - 创建辩论 Agent
    - 控制辩论流程（轮次）
    - 生成最终报告
    """

    def __init__(self, message_bus: Optional[MessageBus] = None):
        self._sessions: Dict[str, DebateSession] = {}
        self._message_bus = message_bus
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._load_sessions_from_db()

    def _load_sessions_from_db(self):
        """从数据库加载会话"""
        try:
            sessions_data = database.load_debate_sessions()
            for data in sessions_data:
                session = DebateSession.from_dict(data)
                self._sessions[session.id] = session

                # 加载 agents
                agents_data = database.load_debate_agents(session.id)
                session.agents = [DebateAgent.from_dict(a) for a in agents_data]

                # 加载消息
                messages_data = database.load_debate_messages(session.id)
                session.messages = [DebateMessage.from_dict(m) for m in messages_data]

                # 加载报告
                if session.status == SessionStatus.COMPLETED:
                    report_data = database.load_debate_report(session.id)
                    if report_data:
                        session.report = DebateReport.from_dict(report_data)

            logger.info(f"[DebateManager] Loaded {len(self._sessions)} sessions from database")
        except Exception as e:
            logger.warning(f"[DebateManager] Failed to load sessions: {e}")

    # =========================================================================
    # Session Management
    # =========================================================================

    def create_session(
        self,
        title: str,
        document_id: Optional[str] = None,
        max_rounds: int = 5,
        knowledge_points: Optional[List[KnowledgePoint]] = None,
        raw_text: str = "",
    ) -> DebateSession:
        """创建辩论会话"""
        session = DebateSession(
            title=title,
            document_id=document_id,
            max_rounds=max_rounds,
            knowledge_points=knowledge_points,
            raw_text=raw_text,
        )
        self._sessions[session.id] = session

        # 持久化到数据库
        database.save_debate_session(session.to_dict())

        logger.info(f"[DebateManager] Created session: {session.id}")
        return session

    def get_session(self, session_id: str) -> Optional[DebateSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[DebateSession]:
        """列出所有会话"""
        return list(self._sessions.values())

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            database.delete_debate_session(session_id)
            logger.info(f"[DebateManager] Deleted session: {session_id}")
            return True
        return False

    # =========================================================================
    # Agent Management
    # =========================================================================

    def create_agents(
        self,
        session_id: str,
        topic: str = "",
    ) -> List[DebateAgent]:
        """为会话创建辩论 Agent"""
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
            topic = session.raw_text[:500] if session.raw_text else "文档辩论主题"

        # 创建 Agent
        agents = []

        # 正方
        proponent = DebateAgent(
            session_id=session_id,
            name="正方",
            role=AgentRole.PROPONENT,
            stance="支持",
            system_prompt=DEBATE_PROMPTS[AgentRole.PROPONENT].format(
                topic=topic,
                points=points_text,
            ),
            avatar="✅",
        )
        agents.append(proponent)

        # 反方
        opponent = DebateAgent(
            session_id=session_id,
            name="反方",
            role=AgentRole.OPPONENT,
            stance="反对",
            system_prompt=DEBATE_PROMPTS[AgentRole.OPPONENT].format(
                topic=topic,
                points=points_text,
            ),
            avatar="❌",
        )
        agents.append(opponent)

        # 主持人
        moderator = DebateAgent(
            session_id=session_id,
            name="主持人",
            role=AgentRole.MODERATOR,
            stance="中立",
            system_prompt=DEBATE_PROMPTS[AgentRole.MODERATOR].format(
                topic=topic,
                points=points_text,
            ),
            avatar="🎯",
        )
        agents.append(moderator)

        # 汇报员
        reporter = DebateAgent(
            session_id=session_id,
            name="汇报员",
            role=AgentRole.REPORTER,
            stance="中立",
            system_prompt=DEBATE_PROMPTS[AgentRole.REPORTER].replace("{topic}", topic).replace("{debate_history}", "（辩论结束后填写）"),
            avatar="📝",
        )
        agents.append(reporter)

        # 保存到会话和数据库
        session.agents = agents
        for agent in agents:
            database.save_debate_agent(agent.to_dict())

        logger.info(f"[DebateManager] Created {len(agents)} agents for session {session_id}")
        return agents

    def get_agent(self, session_id: str, agent_id: str) -> Optional[DebateAgent]:
        """获取 Agent"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        for agent in session.agents:
            if agent.id == agent_id:
                return agent
        return None

    # =========================================================================
    # Debate Flow Control
    # =========================================================================

    async def start_debate(self, session_id: str) -> bool:
        """开始辩论"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.status == SessionStatus.ACTIVE:
            logger.warning(f"[DebateManager] Session {session_id} already active")
            return False

        # 更新状态
        session.status = SessionStatus.ACTIVE
        session.updated_at = datetime.now()
        database.update_debate_session(session_id, {"status": SessionStatus.ACTIVE})

        # 启动辩论任务
        task = asyncio.create_task(self._run_debate(session_id))
        self._running_tasks[session_id] = task

        logger.info(f"[DebateManager] Started debate for session {session_id}")
        return True

    async def _run_debate(self, session_id: str):
        """运行辩论主循环"""
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            # 等待一小段时间让前端连接 WebSocket
            await asyncio.sleep(1)

            # 辩论主循环
            while session.current_round < session.max_rounds and session.status == SessionStatus.ACTIVE:
                session.current_round += 1
                session.updated_at = datetime.now()
                database.update_debate_session(session_id, {
                    "current_round": session.current_round,
                    "status": SessionStatus.ACTIVE,
                })

                # 广播轮次变化
                await self._broadcast_round_change(session)

                # 正方发言
                await self._agent_speaks(session, AgentRole.PROPONENT, session.current_round)
                await asyncio.sleep(0.5)

                # 反方回应
                await self._agent_speaks(session, AgentRole.OPPONENT, session.current_round)
                await asyncio.sleep(0.5)

                # 主持人点评
                await self._agent_speaks(session, AgentRole.MODERATOR, session.current_round)
                await asyncio.sleep(1)

            # 辩论结束，生成报告
            if session.status == SessionStatus.ACTIVE:
                await self._generate_report(session)

        except Exception as e:
            logger.error(f"[DebateManager] Debate error for session {session_id}: {e}")
            session.status = SessionStatus.FAILED
            database.update_debate_session(session_id, {"status": SessionStatus.FAILED})

        finally:
            if session_id in self._running_tasks:
                del self._running_tasks[session_id]

    async def _agent_speaks(self, session: DebateSession, role: AgentRole, round_num: int):
        """Agent 发言"""
        # 找到对应角色的 Agent
        agent = None
        for a in session.agents:
            if a.role == role:
                agent = a
                break

        if not agent:
            logger.warning(f"[DebateManager] No agent found for role {role}")
            return

        # 构建上下文
        context = self._build_debate_context(session, round_num)

        # 调用 LLM
        from backend.main import call_minimax_llm
        response = await call_minimax_llm(
            prompt=context,
            system_prompt=agent.system_prompt,
            conversation_history=[],
        )

        # 创建消息
        msg = DebateMessage(
            session_id=session.id,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_role=agent.role,
            round_num=round_num,
            msg_type=DebateRole.DEBATE,
            content=response,
        )

        # 保存消息
        session.messages.append(msg)
        database.save_debate_message(msg.to_dict())

        # 广播消息
        await self._broadcast_message(session.id, msg)

        logger.info(f"[DebateManager] {agent.name} spoke in round {round_num}")

    def _build_debate_context(self, session: DebateSession, current_round: int) -> str:
        """构建辩论上下文"""
        # 获取之前的消息
        history = []
        for msg in session.messages:
            if msg.round < current_round:
                history.append(f"{msg.agent_name}：{msg.content}")

        history_text = "\n\n".join(history) if history else "（这是第一轮，正方先发言）"

        # 构建知识点文本
        points_text = "\n".join([
            f"- {kp.title}"
            for kp in session.knowledge_points[:5]  # 限制前5个
        ]) if session.knowledge_points else "无特定知识点"

        context = f"""## 当前轮次
第 {current_round} 轮 / 共 {session.max_rounds} 轮

## 辩论历史
{history_text}

## 关键知识点
{points_text}

请正方基于以上背景，发表你的辩论观点。"""

        return context

    async def _broadcast_message(self, session_id: str, msg: DebateMessage):
        """广播消息到 WebSocket"""
        if self._message_bus:
            # 通过 message_bus 广播
            message = Message(
                msg_type="debate_message",
                from_agent=msg.agent_name,
                to="*",
                content={
                    "type": "message",
                    "payload": msg.to_dict(),
                },
            )
            await self._message_bus.broadcast(message)
        else:
            # 直接通过 WebSocket 广播（如果可用）
            from backend.main import manager
            if manager:
                await manager.broadcast_to_session(session_id, {
                    "type": "message",
                    "payload": msg.to_dict(),
                })

    async def _broadcast_round_change(self, session: DebateSession):
        """广播轮次变化"""
        from backend.main import manager
        if manager:
            await manager.broadcast_to_session(session.id, {
                "type": "round_change",
                "payload": {
                    "round": session.current_round,
                    "max_rounds": session.max_rounds,
                },
            })

    async def _generate_report(self, session: DebateSession):
        """生成辩论报告"""
        # 找到 Reporter Agent
        reporter = None
        for agent in session.agents:
            if agent.role == AgentRole.REPORTER:
                reporter = agent
                break

        if not reporter:
            logger.warning(f"[DebateManager] No reporter found for session {session.id}")
            return

        # 构建辩论历史
        debate_history = []
        for msg in session.messages:
            debate_history.append(f"【{msg.agent_name}】{msg.content}")

        history_text = "\n\n".join(debate_history)

        # 构建 prompt
        prompt = f"""## 辩论主题
{session.title}

## 辩论过程
{history_text}

请根据以上辩论过程，生成一份综合报告。输出 JSON 格式。"""

        # 调用 LLM
        from backend.main import call_minimax_llm
        response = await call_minimax_llm(
            prompt=prompt,
            system_prompt=reporter.system_prompt,
            conversation_history=[],
        )

        # 解析 JSON 响应
        try:
            # 尝试提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                report_data = json.loads(json_match.group())
                report = DebateReport(
                    session_id=session.id,
                    **report_data,
                )
            else:
                # 如果没有 JSON，用默认格式
                report = DebateReport(
                    session_id=session.id,
                    summary=response[:500],
                    conclusion="辩论已完成",
                )
        except Exception as e:
            logger.error(f"[DebateManager] Failed to parse report JSON: {e}")
            report = DebateReport(
                session_id=session.id,
                summary=response[:500],
                conclusion="辩论已完成",
            )

        # 保存报告
        session.report = report
        database.save_debate_report(report.to_dict())

        # 更新会话状态
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now()
        database.update_debate_session(session.id, {
            "status": SessionStatus.COMPLETED,
            "completed_at": session.completed_at.isoformat(),
        })

        # 广播报告
        from backend.main import manager
        if manager:
            await manager.broadcast_to_session(session.id, {
                "type": "report",
                "payload": report.to_dict(),
            })

        logger.info(f"[DebateManager] Generated report for session {session.id}")

    def pause_debate(self, session_id: str) -> bool:
        """暂停辩论"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = SessionStatus.PAUSED
        session.updated_at = datetime.now()
        database.update_debate_session(session_id, {"status": SessionStatus.PAUSED})
        return True

    def resume_debate(self, session_id: str) -> bool:
        """恢复辩论"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = SessionStatus.ACTIVE
        session.updated_at = datetime.now()
        database.update_debate_session(session_id, {"status": SessionStatus.ACTIVE})

        # 重新启动辩论任务
        task = asyncio.create_task(self._run_debate(session_id))
        self._running_tasks[session_id] = task
        return True

    def stop_debate(self, session_id: str) -> bool:
        """停止辩论"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        # 取消运行中的任务
        if session_id in self._running_tasks:
            self._running_tasks[session_id].cancel()
            del self._running_tasks[session_id]

        session.status = SessionStatus.FAILED
        session.updated_at = datetime.now()
        database.update_debate_session(session_id, {"status": SessionStatus.FAILED})
        return True


# 全局单例
_debate_manager: Optional[DebateSessionManager] = None


def get_debate_manager() -> DebateSessionManager:
    """获取辩论管理器单例"""
    global _debate_manager
    if _debate_manager is None:
        _debate_manager = DebateSessionManager()
    return _debate_manager
