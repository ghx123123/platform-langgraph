"""
Agent Runtime Tests
"""
import asyncio
import pytest
from datetime import datetime

from backend.agent.runtime import Agent, AgentConfig, AgentRegistry, AgentStatus, MemoryScope


@pytest.fixture
def agent_config():
    return AgentConfig(
        name="测试Agent",
        role="你是一个有用的助手",
        description="测试用Agent",
        avatar="🤖",
        tools=["calculator", "search"],
        memory_scope=MemoryScope.PRIVATE
    )


@pytest.fixture
def agent(agent_config):
    return Agent(config=agent_config)


class TestAgent:
    """Agent 核心功能测试"""

    def test_agent_creation(self, agent):
        """测试 Agent 创建"""
        assert agent.name == "测试Agent"
        assert agent.role == "你是一个有用的助手"
        assert agent.status == AgentStatus.OFFLINE
        assert len(agent.tools) == 2
        assert agent.tools == ["calculator", "search"]

    def test_agent_state(self, agent):
        """测试 Agent 状态"""
        assert agent.status == AgentStatus.OFFLINE

        agent.update_status(AgentStatus.ONLINE)
        assert agent.status == AgentStatus.ONLINE

        agent.update_status(AgentStatus.BUSY)
        assert agent.status == AgentStatus.BUSY

    def test_agent_get_state(self, agent):
        """测试获取 Agent 状态"""
        state = agent.get_state()

        assert state["name"] == "测试Agent"
        assert state["role"] == "你是一个有用的助手"
        assert state["status"] == "offline"
        assert "id" in state
        assert "created_at" in state

    @pytest.mark.asyncio
    async def test_think(self, agent):
        """测试思考功能"""
        response = await agent.think("Hello")
        assert "测试Agent" in response
        assert "Hello" in response

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self, agent):
        """测试 Agent 生命周期"""
        # Start
        await agent.start()
        assert agent.status == AgentStatus.ONLINE

        # Stop
        await agent.stop()
        assert agent.status == AgentStatus.OFFLINE


class TestAgentRegistry:
    """Agent 注册表测试"""

    def test_registry_operations(self, agent):
        """测试注册表操作"""
        registry = AgentRegistry()

        # Register
        registry.register(agent)
        assert agent.id in [a.id for a in registry.list_all()]

        # Get by id
        retrieved = registry.get(agent.id)
        assert retrieved is not None
        assert retrieved.id == agent.id

        # Get by name
        retrieved = registry.get_by_name("测试Agent")
        assert retrieved is not None
        assert retrieved.id == agent.id

        # Unregister
        registry.unregister(agent.id)
        assert registry.get(agent.id) is None

    def test_list_online(self, agent):
        """测试在线列表"""
        registry = AgentRegistry()

        registry.register(agent)
        assert len(registry.list_online()) == 0

        agent.status = AgentStatus.ONLINE
        assert len(registry.list_online()) == 1

    def test_agent_config_validation(self):
        """测试配置验证"""
        config = AgentConfig(
            name="Test",
            role="Test role"
        )

        assert config.name == "Test"
        assert config.tools == []  # Default empty list
        assert config.memory_scope == MemoryScope.PRIVATE  # Default


class TestAgentCollaboration:
    """Agent 协作测试"""

    @pytest.mark.asyncio
    async def test_send_message(self, agent):
        """测试发送消息"""
        agent._message_bus = MockMessageBus()

        message = await agent.send_message(
            to="另一个Agent",
            content={"text": "Hello"},
            msg_type="chat"
        )

        assert message.from_agent == agent.name
        assert message.to == "另一个Agent"
        assert message.content["text"] == "Hello"

    @pytest.mark.asyncio
    async def test_broadcast(self, agent):
        """测试广播"""
        agent._message_bus = MockMessageBus()

        message = await agent.broadcast(content={"text": "Broadcast"})

        assert message.from_agent == agent.name
        assert message.to == "*"


class MockMessageBus:
    """模拟消息总线"""

    def __init__(self):
        self.messages = []

    async def send_direct(self, to_agent: str, message):
        self.messages.append(message)

    async def broadcast(self, message):
        self.messages.append(message)


# Property-based tests
from hypothesis import given, strategies as st


@given(st.text())
def test_agent_name_validation(name):
    """属性测试：Agent 名称验证"""
    if len(name) > 0 and len(name) <= 100:
        config = AgentConfig(name=name, role="test")
        assert config.name == name


@given(st.lists(st.text(), max_size=10))
def test_agent_tools_list(tools):
    """属性测试：Agent 工具列表"""
    config = AgentConfig(name="Test", role="test", tools=tools)
    assert len(config.tools) <= 10
