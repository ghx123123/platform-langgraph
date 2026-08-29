"""
Integration Tests
"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.agent.runtime import Agent, AgentConfig, AgentRegistry, MemoryScope
from backend.memory.store import MemoryStore
from backend.message_bus.bus import MessageBus, Message, MessageType
from backend.tools.registry import ToolRegistry, create_builtin_tools, get_builtin_handlers


@pytest.fixture
async def client():
    """Create test client"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def agent_registry():
    return AgentRegistry()


@pytest.fixture
def memory_store(tmp_path):
    db_file = tmp_path / "test.db"
    return MemoryStore(str(db_file))


@pytest.fixture
def message_bus():
    return MessageBus()


@pytest.fixture
def tool_registry():
    registry = ToolRegistry()
    for tool in create_builtin_tools():
        handlers = get_builtin_handlers()
        registry.register(tool, handlers.get(tool.name))
    return registry


class TestAgentIntegration:
    """Agent 集成测试"""

    @pytest.mark.asyncio
    async def test_create_and_chat_agent(self, client):
        """测试创建 Agent 并对话"""
        # Create agent
        response = await client.post("/api/agents", json={
            "name": "TestAgent",
            "role": "You are a helpful assistant",
            "description": "Test agent"
        })
        assert response.status_code == 200
        agent_data = response.json()
        agent_id = agent_data["id"]

        # Chat with agent
        response = await client.post(f"/api/agents/{agent_id}/think", json={
            "prompt": "Hello"
        })
        assert response.status_code == 200
        result = response.json()
        assert "response" in result

        # Get agent
        response = await client.get(f"/api/agents/{agent_id}")
        assert response.status_code == 200
        agent = response.json()
        assert agent["name"] == "TestAgent"

    @pytest.mark.asyncio
    async def test_agent_memory(self, client):
        """测试 Agent 记忆"""
        # Create agent
        response = await client.post("/api/agents", json={
            "name": "MemoryAgent",
            "role": "You have memory"
        })
        agent_id = response.json()["id"]

        # Add memory
        response = await client.post(f"/api/agents/{agent_id}/memories", json={
            "memory_type": "ltm",
            "content": "This is an important memory",
            "metadata": {"type": "test"}
        })
        assert response.status_code == 200
        memory_id = response.json()["id"]

        # List memories
        response = await client.get(f"/api/agents/{agent_id}/memories")
        assert response.status_code == 200
        memories = response.json()
        assert len(memories) >= 1

        # Delete memory
        response = await client.delete(f"/api/agents/{agent_id}/memories/{memory_id}")
        assert response.status_code == 200


class TestMessageBusIntegration:
    """消息总线集成测试"""

    @pytest.mark.asyncio
    async def test_full_message_flow(self, message_bus, agent_registry):
        """测试完整消息流程"""
        # Create and register agents
        agent1_config = AgentConfig(name="Agent1", role="role1")
        agent1 = Agent(config=agent1_config)
        agent_registry.register(agent1)

        agent2_config = AgentConfig(name="Agent2", role="role2")
        agent2 = Agent(config=agent2_config)
        agent_registry.register(agent2)

        # Register with message bus
        message_bus.register_agent(agent1.id)
        message_bus.register_agent(agent2.id)

        # Send direct message
        message = Message(
            msg_type=MessageType.CHAT,
            from_agent="Agent1",
            to="Agent2",
            content={"text": "Hello Agent2"}
        )
        await message_bus.send_direct("Agent2", message)

        # Verify message in history
        history = message_bus.get_history()
        assert any(m.from_agent == "Agent1" and m.to == "Agent2" for m in history)


class TestToolExecutionIntegration:
    """工具执行集成测试"""

    @pytest.mark.asyncio
    async def test_agent_with_tool(self, tool_registry, memory_store, message_bus):
        """测试 Agent 使用工具"""
        config = AgentConfig(
            name="ToolAgent",
            role="You can use tools",
            tools=["calculator", "text_processor"]
        )
        agent = Agent(
            config=config,
            tool_registry=tool_registry,
            memory_store=memory_store,
            message_bus=message_bus
        )

        # Execute tool through agent
        result = await agent.call_tool("calculator", {"expression": "10 + 20"})
        assert result.success is True
        assert result.result == "30"

        # Test unauthorized tool
        result = await agent.call_tool("search", {"query": "test", "limit": 5})
        if isinstance(result, dict):
            assert "not authorized" in str(result.get("error", ""))
        else:
            assert "not authorized" in str(result.error or "")


class TestMemoryIsolation:
    """记忆隔离集成测试"""

    @pytest.mark.asyncio
    async def test_agent_memory_isolation(self, memory_store):
        """测试 Agent 记忆隔离"""
        # Create two agents with different memories
        await memory_store.ltm_store(
            agent_id="agent1",
            content="Secret from Agent 1",
            metadata={"owner": "agent1"}
        )
        await memory_store.ltm_store(
            agent_id="agent2",
            content="Secret from Agent 2",
            metadata={"owner": "agent2"}
        )

        # Verify isolation
        agent1_memories = await memory_store.ltm_list("agent1")
        agent2_memories = await memory_store.ltm_list("agent2")

        assert any("Agent 1" in m.content for m in agent1_memories)
        assert any("Agent 2" in m.content for m in agent2_memories)
        assert not any("Agent 2" in m.content for m in agent1_memories)


class TestHealthCheck:
    """健康检查测试"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """测试健康检查端点"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
