"""
Message Bus - 消息总线实现
支持 Pub/Sub、点对点消息、广播
"""
import asyncio
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """消息类型"""
    CHAT = "chat"
    SUBTASK_REQUEST = "subtask_request"
    REALTIME_REVIEW = "realtime_review"
    CLARIFICATION_REQUEST = "clarification_request"
    RESPONSE = "response"
    ESCALATION = "escalation"
    BROADCAST = "broadcast"
    PING = "ping"
    PONG = "pong"


class Priority(str, Enum):
    """消息优先级"""
    P0 = "P0"  # 立即处理
    P1 = "P1"  # 尽快处理
    P2 = "P2"  # 按顺序处理


class Message(BaseModel):
    """消息模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: MessageType = MessageType.CHAT
    priority: Priority = Priority.P2
    from_agent: str = ""
    to: str = ""              # agent_name, "*", or "topic_name"
    content: Dict[str, Any] = Field(default_factory=dict)
    deadline: str = "immediate"
    callback: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)

    @classmethod
    def from_json(cls, data: str) -> "Message":
        return cls(**json.loads(data))


class Subscriber(BaseModel):
    """订阅者"""
    agent_id: str
    handler: Callable[[Message], Any]
    topics: List[str] = Field(default_factory=list)  # 订阅的话题


class MessageBus:
    """
    消息总线

    功能：
    - publish/subscribe: 话题订阅
    - send_direct: 点对点消息
    - broadcast: 广播消息
    """

    def __init__(self):
        # Agent message queues
        self._queues: Dict[str, asyncio.Queue] = {}

        # Topic subscribers: topic -> [subscriber_ids]
        self._topic_subscribers: Dict[str, List[str]] = {}

        # Agent subscriptions: agent_id -> [topics]
        self._agent_topics: Dict[str, List[str]] = {}

        # Message history (last N messages)
        self._history: List[Message] = []
        self._max_history = 1000

    # =========================================================================
    # Queue Management
    # =========================================================================

    def register_agent(self, agent_id: str) -> asyncio.Queue:
        """注册 Agent，创建消息队列"""
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
        return self._queues[agent_id]

    def unregister_agent(self, agent_id: str):
        """取消注册 Agent"""
        if agent_id in self._queues:
            del self._queues[agent_id]

        # Remove from topics
        if agent_id in self._agent_topics:
            topics = self._agent_topics.pop(agent_id)
            for topic in topics:
                if topic in self._topic_subscribers:
                    self._topic_subscribers[topic].remove(agent_id)

    def get_queue(self, agent_id: str) -> Optional[asyncio.Queue]:
        """获取 Agent 的消息队列"""
        return self._queues.get(agent_id)

    # =========================================================================
    # Topic Subscription
    # =========================================================================

    async def subscribe(self, agent_id: str, topics: List[str]):
        """订阅话题"""
        if agent_id not in self._queues:
            self.register_agent(agent_id)

        for topic in topics:
            if topic not in self._topic_subscribers:
                self._topic_subscribers[topic] = []
            if agent_id not in self._topic_subscribers[topic]:
                self._topic_subscribers[topic].append(agent_id)

        self._agent_topics[agent_id] = topics

    async def unsubscribe(self, agent_id: str, topics: Optional[List[str]] = None):
        """取消订阅"""
        if topics is None:
            topics = self._agent_topics.get(agent_id, [])

        for topic in topics:
            if topic in self._topic_subscribers:
                if agent_id in self._topic_subscribers[topic]:
                    self._topic_subscribers[topic].remove(agent_id)

        if agent_id in self._agent_topics:
            if topics:
                self._agent_topics[agent_id] = [
                    t for t in self._agent_topics[agent_id] if t not in topics
                ]
            else:
                del self._agent_topics[agent_id]

    # =========================================================================
    # Message Sending
    # =========================================================================

    async def send_direct(self, to_agent: str, message: Message):
        """
        发送点对点消息

        将消息放入目标 Agent 的队列。
        """
        self._add_to_history(message)

        queue = self.get_queue(to_agent)
        if queue:
            await queue.put(message)
        else:
            print(f"[MessageBus] Agent '{to_agent}' not found, message queued to history")

    async def broadcast(self, message: Message):
        """
        广播消息到所有在线 Agent
        """
        self._add_to_history(message)

        for agent_id, queue in self._queues.items():
            # Don't send back to sender
            if agent_id != message.from_agent:
                await queue.put(message)

    async def publish(self, topic: str, message: Message):
        """
        发布消息到指定话题

        所有订阅该话题的 Agent 都会收到消息。
        """
        self._add_to_history(message)

        if topic in self._topic_subscribers:
            for agent_id in self._topic_subscribers[topic]:
                # Don't send back to sender
                if agent_id != message.from_agent:
                    queue = self.get_queue(agent_id)
                    if queue:
                        await queue.put(message)

    async def send_to_topic(
        self,
        topic: str,
        from_agent: str,
        content: Dict[str, Any],
        msg_type: MessageType = MessageType.CHAT,
        priority: Priority = Priority.P2
    ) -> Message:
        """发送消息到话题"""
        message = Message(
            msg_type=msg_type,
            priority=priority,
            from_agent=from_agent,
            to=topic,
            content=content
        )
        await self.publish(topic, message)
        return message

    # =========================================================================
    # Message Retrieval
    # =========================================================================

    async def receive(self, agent_id: str, timeout: float = 5.0) -> Optional[Message]:
        """
        从队列接收消息

        阻塞等待直到收到消息或超时。
        """
        queue = self.get_queue(agent_id)
        if not queue:
            return None

        try:
            message = await asyncio.wait_for(queue.get(), timeout=timeout)
            return message
        except asyncio.TimeoutError:
            return None

    def get_history(self, limit: int = 100) -> List[Message]:
        """获取消息历史"""
        return self._history[-limit:]

    def get_agent_history(self, agent_id: str, limit: int = 50) -> List[Message]:
        """获取与特定 Agent 相关的消息历史"""
        relevant = [
            m for m in self._history
            if m.from_agent == agent_id or m.to == agent_id or m.to == "*"
        ]
        return relevant[-limit:]

    # =========================================================================
    # Utility
    # =========================================================================

    def _add_to_history(self, message: Message):
        """添加到历史记录"""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_topics(self) -> List[str]:
        """获取所有话题"""
        return list(self._topic_subscribers.keys())

    def get_subscribers(self, topic: str) -> List[str]:
        """获取话题订阅者"""
        return self._topic_subscribers.get(topic, [])

    def get_online_agents(self) -> List[str]:
        """获取所有在线 Agent"""
        return list(self._queues.keys())


class CoordinationProtocol:
    """
    协作协议

    实现多智能体协作的标准化流程。
    """

    def __init__(self, message_bus: MessageBus):
        self._bus = message_bus

    async def request_subtask(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        input_ref: Optional[str] = None,
        deadline: str = "2min"
    ) -> Message:
        """请求子任务"""
        message = Message(
            msg_type=MessageType.SUBTASK_REQUEST,
            priority=Priority.P1,
            from_agent=from_agent,
            to=to_agent,
            content={
                "task": task,
                "input_ref": input_ref
            },
            deadline=deadline,
            callback=from_agent
        )
        await self._bus.send_direct(to_agent, message)
        return message

    async def request_clarification(
        self,
        from_agent: str,
        to_agent: str,
        location: str,
        ambiguity: str,
        options: Optional[List[str]] = None,
        deadline: str = "1min"
    ) -> Message:
        """请求澄清"""
        message = Message(
            msg_type=MessageType.CLARIFICATION_REQUEST,
            priority=Priority.P1,
            from_agent=from_agent,
            to=to_agent,
            content={
                "location": location,
                "ambiguity": ambiguity,
                "options": options or []
            },
            deadline=deadline,
            callback=from_agent
        )
        await self._bus.send_direct(to_agent, message)
        return message

    async def send_review(
        self,
        from_agent: str,
        to_agent: str,
        target: str,
        issue_id: str,
        severity: str,
        description: str,
        suggestion: str,
        deadline: str = "immediate"
    ) -> Message:
        """发送审查反馈"""
        message = Message(
            msg_type=MessageType.REALTIME_REVIEW,
            priority=Priority(severity),
            from_agent=from_agent,
            to=to_agent,
            content={
                "target": target,
                "issue_id": issue_id,
                "severity": severity,
                "description": description,
                "suggestion": suggestion
            },
            deadline=deadline,
            callback=from_agent
        )
        await self._bus.send_direct(to_agent, message)
        return message

    async def escalate(
        self,
        from_agent: str,
        to_coordinator: str,
        reason: str,
        history: List[str],
        blocking_issue: str,
        options: Optional[List[str]] = None
    ) -> Message:
        """升级问题"""
        message = Message(
            msg_type=MessageType.ESCALATION,
            priority=Priority.P0,
            from_agent=from_agent,
            to=to_coordinator,
            content={
                "reason": reason,
                "history": history,
                "blocking_issue": blocking_issue,
                "options": options or []
            }
        )
        await self._bus.send_direct(to_coordinator, message)
        return message
