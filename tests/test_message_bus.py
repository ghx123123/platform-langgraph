"""
Message Bus Tests
"""
import asyncio
import pytest
from datetime import datetime

from backend.message_bus.bus import (
    MessageBus,
    Message,
    MessageType,
    Priority,
    CoordinationProtocol
)


@pytest.fixture
def message_bus():
    return MessageBus()


class TestMessageBus:
    """消息总线测试"""

    @pytest.mark.asyncio
    async def test_register_agent(self, message_bus):
        """测试注册 Agent"""
        queue = message_bus.register_agent("agent1")
        assert queue is not None

        agents = message_bus.get_online_agents()
        assert "agent1" in agents

    @pytest.mark.asyncio
    async def test_unregister_agent(self, message_bus):
        """测试取消注册"""
        message_bus.register_agent("agent1")
        message_bus.unregister_agent("agent1")

        assert "agent1" not in message_bus.get_online_agents()

    @pytest.mark.asyncio
    async def test_send_direct(self, message_bus):
        """测试点对点消息"""
        # Register receiver first
        message_bus.register_agent("receiver")

        message = Message(
            msg_type=MessageType.CHAT,
            from_agent="sender",
            to="receiver",
            content={"text": "Hello"}
        )

        await message_bus.send_direct("receiver", message)

        # Verify message in history
        history = message_bus.get_history()
        assert any(m.id == message.id for m in history)

    @pytest.mark.asyncio
    async def test_broadcast(self, message_bus):
        """测试广播"""
        # Register multiple agents
        message_bus.register_agent("agent1")
        message_bus.register_agent("agent2")
        message_bus.register_agent("agent3")

        message = Message(
            msg_type=MessageType.BROADCAST,
            from_agent="broadcaster",
            to="*",
            content={"text": "Broadcast message"}
        )

        await message_bus.broadcast(message)

        # All agents should receive
        history = message_bus.get_history()
        assert any(m.id == message.id for m in history)

    @pytest.mark.asyncio
    async def test_topic_subscription(self, message_bus):
        """测试话题订阅"""
        message_bus.register_agent("subscriber")

        await message_bus.subscribe("subscriber", ["topic1", "topic2"])

        subscribers = message_bus.get_subscribers("topic1")
        assert "subscriber" in subscribers

        subscribers = message_bus.get_subscribers("topic2")
        assert "subscriber" in subscribers

    @pytest.mark.asyncio
    async def test_publish_to_topic(self, message_bus):
        """测试发布到话题"""
        message_bus.register_agent("subscriber")

        await message_bus.subscribe("subscriber", ["tech"])

        message = Message(
            msg_type=MessageType.CHAT,
            from_agent="publisher",
            to="tech",
            content={"text": "Tech news"}
        )

        await message_bus.publish("tech", message)

        history = message_bus.get_history()
        assert any(m.id == message.id for m in history)

    @pytest.mark.asyncio
    async def test_unsubscribe(self, message_bus):
        """测试取消订阅"""
        message_bus.register_agent("agent1")

        await message_bus.subscribe("agent1", ["topic1", "topic2"])
        await message_bus.unsubscribe("agent1", ["topic1"])

        subscribers = message_bus.get_subscribers("topic1")
        assert "agent1" not in subscribers

        # topic2 should still be subscribed
        subscribers = message_bus.get_subscribers("topic2")
        assert "agent1" in subscribers

    @pytest.mark.asyncio
    async def test_message_history(self, message_bus):
        """测试消息历史"""
        message_bus.register_agent("agent1")

        for i in range(5):
            message = Message(
                msg_type=MessageType.CHAT,
                from_agent="agent1",
                to="*",
                content={"index": i}
            )
            await message_bus.broadcast(message)

        history = message_bus.get_history(limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_topics(self, message_bus):
        """测试获取话题列表"""
        message_bus.register_agent("agent1")
        await message_bus.subscribe("agent1", ["topic1", "topic2", "topic3"])

        topics = message_bus.get_topics()
        assert len(topics) >= 3
        assert "topic1" in topics


class TestMessage:
    """消息模型测试"""

    def test_message_creation(self):
        """测试消息创建"""
        message = Message(
            msg_type=MessageType.CHAT,
            from_agent="agent1",
            to="agent2",
            content={"text": "Hello"}
        )

        assert message.msg_type == MessageType.CHAT
        assert message.from_agent == "agent1"
        assert message.to == "agent2"
        assert message.content["text"] == "Hello"
        assert message.id is not None

    def test_message_to_json(self):
        """测试消息序列化"""
        message = Message(
            msg_type=MessageType.CHAT,
            from_agent="agent1",
            to="agent2",
            content={"text": "Hello"}
        )

        json_str = message.to_json()
        assert "agent1" in json_str
        assert "agent2" in json_str

    def test_message_from_json(self):
        """测试消息反序列化"""
        message = Message(
            msg_type=MessageType.CHAT,
            from_agent="agent1",
            to="agent2",
            content={"text": "Hello"}
        )

        json_str = message.to_json()
        restored = Message.from_json(json_str)

        assert restored.id == message.id
        assert restored.from_agent == message.from_agent


class TestCoordinationProtocol:
    """协作协议测试"""

    @pytest.mark.asyncio
    async def test_request_subtask(self, message_bus):
        """测试子任务请求"""
        message_bus.register_agent("worker")
        protocol = CoordinationProtocol(message_bus)

        message = await protocol.request_subtask(
            from_agent="manager",
            to_agent="worker",
            task="完成代码审查",
            deadline="5min"
        )

        assert message.msg_type == MessageType.SUBTASK_REQUEST
        assert message.from_agent == "manager"
        assert message.to == "worker"
        assert message.content["task"] == "完成代码审查"

    @pytest.mark.asyncio
    async def test_request_clarification(self, message_bus):
        """测试澄清请求"""
        message_bus.register_agent("designer")
        protocol = CoordinationProtocol(message_bus)

        message = await protocol.request_clarification(
            from_agent="coder",
            to_agent="designer",
            location="design.md:100",
            ambiguity="这个接口的返回值是什么？",
            options=["返回用户对象", "返回用户ID", "返回布尔值"]
        )

        assert message.msg_type == MessageType.CLARIFICATION_REQUEST
        assert message.content["ambiguity"] == "这个接口的返回值是什么？"

    @pytest.mark.asyncio
    async def test_send_review(self, message_bus):
        """测试发送审查"""
        message_bus.register_agent("reviewer")
        protocol = CoordinationProtocol(message_bus)

        message = await protocol.send_review(
            from_agent="reviewer",
            to_agent="coder",
            target="src/main.py",
            issue_id="R1",
            severity="P1",
            description="缺少错误处理",
            suggestion="添加 try-except 块"
        )

        assert message.msg_type == MessageType.REALTIME_REVIEW
        assert message.content["issue_id"] == "R1"

    @pytest.mark.asyncio
    async def test_escalate(self, message_bus):
        """测试问题升级"""
        message_bus.register_agent("coordinator")
        protocol = CoordinationProtocol(message_bus)

        message = await protocol.escalate(
            from_agent="agent1",
            to_coordinator="coordinator",
            reason="无法解决的技术分歧",
            history=["讨论了3轮", "无法达成一致"],
            blocking_issue="架构设计争议"
        )

        assert message.msg_type == MessageType.ESCALATION
        assert message.priority == Priority.P0


# Property-based tests
from hypothesis import given, strategies as st


@given(st.text())
def test_message_content(content):
    """属性测试：消息内容"""
    message = Message(
        msg_type=MessageType.CHAT,
        from_agent="agent1",
        to="agent2",
        content={"text": content}
    )
    assert message.content["text"] == content


@given(st.sampled_from(["P0", "P1", "P2"]))
def test_priority_values(priority):
    """属性测试：优先级值"""
    p = Priority(priority)
    assert p.value == priority
