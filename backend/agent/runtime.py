"""
Agent Runtime - Core Agent implementation
智能体运行时核心
"""
import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Agent 状态"""
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_COLLABORATION = "waiting_collaboration"
    ESCALATE = "escalate"
    BLOCKED = "blocked"


class MemoryScope(str, Enum):
    """记忆隔离范围"""
    PRIVATE = "private"   # 仅自己可见
    TEAM = "team"        # 团队共享
    SHARED = "shared"    # 全局共享


class Message(BaseModel):
    """消息模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: str = "chat"  # chat, subtask_request, realtime_review, etc.
    priority: str = "P2"     # P0, P1, P2
    from_agent: str = ""
    to: str = ""             # agent_name, "*", or "topic_name"
    content: Dict[str, Any] = Field(default_factory=dict)
    deadline: str = "immediate"
    callback: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str
    role: str                    # system prompt / 角色描述
    description: str = ""
    avatar: str = "🤖"
    tools: List[str] = Field(default_factory=list)
    memory_scope: MemoryScope = MemoryScope.PRIVATE


class Agent:
    """
    Agent 运行时

    核心能力：
    - think(): 思考并生成响应
    - call_tool(): 调用工具
    - send_message(): 发送消息
    - broadcast(): 广播消息
    - remember(): 存储记忆
    - recall(): 检索记忆
    """

    def __init__(
        self,
        config: AgentConfig,
        message_bus=None,
        memory_store=None,
        tool_registry=None,
    ):
        self.id: str = str(uuid.uuid4())
        self.name: str = config.name
        self.role: str = config.role
        self.description: str = config.description
        self.avatar: str = config.avatar
        self.tools: List[str] = config.tools
        self.memory_scope: MemoryScope = config.memory_scope

        # Runtime state
        self.status: AgentStatus = AgentStatus.OFFLINE
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()

        # Dependencies (injected, not instantiated here)
        self._message_bus = message_bus
        self._memory_store = memory_store
        self._tool_registry = tool_registry

        # Internal state
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """启动 Agent"""
        self.status = AgentStatus.ONLINE
        self._shutdown_event.clear()
        self._running_task = asyncio.create_task(self._message_loop())
        self._load_memory()

    async def stop(self):
        """停止 Agent"""
        self._shutdown_event.set()
        if self._running_task:
            self._running_task.cancel()
            try:
                await self._running_task
            except asyncio.CancelledError:
                pass
        self.status = AgentStatus.OFFLINE

    async def _message_loop(self):
        """消息处理循环"""
        while not self._shutdown_event.is_set():
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )
                await self._handle_message(message)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{self.name}] Error in message loop: {e}")

    async def _handle_message(self, message: Message):
        """处理收到的消息"""
        self.status = AgentStatus.PROCESSING

        try:
            if message.msg_type == "chat":
                response = await self.think(message.content.get("prompt", ""))
                await self.send_message(
                    to=message.from_agent,
                    content={"response": response},
                    msg_type="response"
                )

            elif message.msg_type == "subtask_request":
                result = await self._handle_subtask(message)
                if message.callback:
                    await self.send_message(
                        to=message.callback,
                        content={"result": result, "task_id": message.id},
                        msg_type="response"
                    )

            elif message.msg_type == "clarification_request":
                await self._handle_clarification(message)

            elif message.msg_type == "realtime_review":
                await self._handle_review(message)

            elif message.msg_type == "escalation":
                await self._handle_escalation(message)

            elif message.msg_type == "ping":
                await self.send_message(to=message.from_agent, content={}, msg_type="pong")

        finally:
            self.status = AgentStatus.ONLINE

    def _load_memory(self):
        """加载记忆到短期存储"""
        # Implemented by memory store integration
        pass

    # =========================================================================
    # Core Methods
    # =========================================================================

    async def think(self, prompt: str) -> str:
        """
        思考并生成响应

        在实际实现中，这里会调用 LLM API。
        当前为模拟实现。
        """
        self.status = AgentStatus.BUSY
        self.updated_at = datetime.now()

        # Simulate thinking (replace with actual LLM call)
        response = f"[{self.name}] received: {prompt}"

        # Store interaction in memory
        if self._memory_store:
            await self._memory_store.ltm_store(
                agent_id=self.id,
                content=f"User: {prompt}\nAssistant: {response}",
                metadata={"type": "interaction"}
            )

        self.status = AgentStatus.ONLINE
        return response

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        调用工具

        通过工具注册表执行工具调用。
        """
        if not self._tool_registry:
            return {"error": "Tool registry not configured"}

        if tool_name not in self.tools:
            return {"error": f"Tool '{tool_name}' not authorized"}

        try:
            result = await self._tool_registry.execute(
                agent_id=self.id,
                tool_name=tool_name,
                args=args
            )
            return result
        except Exception as e:
            return {"error": str(e)}

    async def send_message(
        self,
        to: str,
        content: Dict[str, Any],
        msg_type: str = "chat",
        priority: str = "P2",
        deadline: str = "immediate"
    ) -> Message:
        """
        发送消息给指定 Agent
        """
        message = Message(
            msg_type=msg_type,
            priority=priority,
            from_agent=self.name,
            to=to,
            content=content,
            deadline=deadline,
            callback=self.name
        )

        if self._message_bus:
            await self._message_bus.send_direct(to_agent=to, message=message)

        return message

    async def broadcast(self, content: Dict[str, Any], topic: str = "*") -> Message:
        """
        广播消息到所有 Agent
        """
        message = Message(
            msg_type="broadcast",
            from_agent=self.name,
            to="*",
            content=content
        )

        if self._message_bus:
            await self._message_bus.broadcast(message)

        return message

    async def remember(self, key: str, value: Any, ttl: int = 86400):
        """
        存储短期记忆
        """
        if self._memory_store:
            await self._memory_store.stm_set(
                agent_id=self.id,
                key=key,
                value=value,
                ttl=ttl
            )

    async def recall(self, query: str, limit: int = 10) -> List[Any]:
        """
        检索长期记忆
        """
        if self._memory_store:
            memories = await self._memory_store.ltm_search(
                agent_id=self.id,
                query=query,
                limit=limit
            )
            return memories
        return []

    # =========================================================================
    # Collaboration Handlers
    # =========================================================================

    async def _handle_subtask(self, message: Message) -> Dict[str, Any]:
        """处理子任务请求"""
        task = message.content.get("task", "")
        # Execute subtask
        result = await self.think(task)
        return {"status": "completed", "result": result}

    async def _handle_clarification(self, message: Message):
        """处理澄清请求"""
        ambiguity = message.content.get("ambiguity", "")
        response = await self.think(f"Clarify: {ambiguity}")
        await self.send_message(
            to=message.from_agent,
            content={"clarification": response},
            msg_type="response"
        )

    async def _handle_review(self, message: Message):
        """处理审查请求"""
        target = message.content.get("target", "")
        issue = message.content.get("description", "")
        response = await self.think(f"Review {target}: {issue}")
        await self.send_message(
            to=message.from_agent,
            content={"review": response},
            msg_type="response"
        )

    async def _handle_escalation(self, message: Message):
        """处理升级请求"""
        reason = message.content.get("reason", "")
        # Log escalation and take action
        print(f"[{self.name}] ESCALATION: {reason}")

    # =========================================================================
    # State Management
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """获取 Agent 状态"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "role": self.role,
            "tools": self.tools,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def update_status(self, status: AgentStatus):
        """更新状态"""
        self.status = status
        self.updated_at = datetime.now()


class AgentRegistry:
    """
    Agent 注册表

    管理所有 Agent 实例。
    """

    def __init__(self):
        self._agents: Dict[str, Agent] = {}

    def register(self, agent: Agent):
        """注册 Agent"""
        self._agents[agent.id] = agent

    def unregister(self, agent_id: str):
        """取消注册"""
        if agent_id in self._agents:
            del self._agents[agent_id]

    def get(self, agent_id: str) -> Optional[Agent]:
        """获取 Agent"""
        return self._agents.get(agent_id)

    def get_by_name(self, name: str) -> Optional[Agent]:
        """通过名称获取 Agent"""
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def list_all(self) -> List[Agent]:
        """列出所有 Agent"""
        return list(self._agents.values())

    def list_online(self) -> List[Agent]:
        """列出在线 Agent"""
        return [a for a in self._agents.values() if a.status == AgentStatus.ONLINE]
