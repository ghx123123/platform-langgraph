"""
Tool Registry Tests
"""
import asyncio
import pytest

from backend.tools.registry import (
    ToolRegistry,
    Tool,
    ToolSchema,
    ToolParameter,
    ToolSource,
    ToolCategory,
    ToolExecutionResult,
    MCPTool,
    create_builtin_tools,
    get_builtin_handlers,
    calculator_handler,
    text_processor_handler,
    current_time_handler
)


@pytest.fixture
def tool_registry():
    registry = ToolRegistry()

    # Register built-in tools
    for tool in create_builtin_tools():
        handlers = get_builtin_handlers()
        registry.register(tool, handlers.get(tool.name))

    return registry


class TestToolRegistry:
    """工具注册表测试"""

    def test_register_tool(self, tool_registry):
        """测试注册工具"""
        tools = tool_registry.list_all()
        assert len(tools) > 0

        # Check calculator exists
        calc = tool_registry.get("calculator")
        assert calc is not None
        assert calc.name == "calculator"

    def test_unregister_tool(self, tool_registry):
        """测试注销工具"""
        result = tool_registry.unregister("calculator")
        assert result is True

        calc = tool_registry.get("calculator")
        assert calc is None

    def test_list_by_source(self, tool_registry):
        """测试按来源筛选"""
        builtin = tool_registry.list_by_source(ToolSource.BUILTIN)
        assert len(builtin) > 0
        assert all(t.source == ToolSource.BUILTIN for t in builtin)

    def test_list_by_category(self, tool_registry):
        """测试按类别筛选"""
        search = tool_registry.list_by_category(ToolCategory.SEARCH)
        assert len(search) > 0
        assert all(t.category == ToolCategory.SEARCH for t in search)

    def test_list_enabled(self, tool_registry):
        """测试列出已启用工具"""
        enabled = tool_registry.list_enabled()
        assert len(enabled) > 0
        assert all(t.enabled for t in enabled)


class TestToolExecution:
    """工具执行测试"""

    @pytest.mark.asyncio
    async def test_execute_calculator(self, tool_registry):
        """测试计算器工具"""
        result = await tool_registry.execute(
            agent_id="agent1",
            tool_name="calculator",
            args={"expression": "2 + 3 * 4"}
        )

        assert result.success is True
        assert result.result == "14"

    @pytest.mark.asyncio
    async def test_execute_text_processor(self, tool_registry):
        """测试文本处理工具"""
        result = await tool_registry.execute(
            agent_id="agent1",
            tool_name="text_processor",
            args={"text": "hello world", "operation": "upper"}
        )

        assert result.success is True
        assert result.result == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_execute_current_time(self, tool_registry):
        """测试获取当前时间"""
        result = await tool_registry.execute(
            agent_id="agent1",
            tool_name="current_time",
            args={}
        )

        assert result.success is True
        assert result.result is not None

    @pytest.mark.asyncio
    async def test_execute_invalid_tool(self, tool_registry):
        """测试调用不存在的工具"""
        result = await tool_registry.execute(
            agent_id="agent1",
            tool_name="nonexistent_tool",
            args={}
        )

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_invalid_args(self, tool_registry):
        """测试无效参数"""
        result = await tool_registry.execute(
            agent_id="agent1",
            tool_name="calculator",
            args={"expression": "invalid + expression"}
        )

        # Calculator should handle this gracefully
        assert result.success is False or "Error" in str(result.result)


class TestToolValidation:
    """工具参数验证测试"""

    def test_tool_validate_args(self):
        """测试参数验证"""
        tool = Tool(
            name="test_tool",
            description="Test tool",
            tool_schema=ToolSchema(
                name="test_tool",
                description="Test",
                parameters=[
                    ToolParameter(
                        name="arg1",
                        type="string",
                        description="First argument",
                        required=True
                    ),
                    ToolParameter(
                        name="arg2",
                        type="number",
                        description="Second argument",
                        required=False,
                        default=42
                    )
                ]
            )
        )

        # Valid args
        valid, error = tool.validate_args({"arg1": "value"})
        assert valid is True

        # Missing required
        valid, error = tool.validate_args({})
        assert valid is False
        assert "arg1" in error

        # Wrong type
        valid, error = tool.validate_args({"arg1": 123})
        assert valid is False
        assert "string" in error

    def test_tool_validate_enum(self):
        """测试枚举验证"""
        tool = Tool(
            name="test_tool",
            description="Test tool",
            tool_schema=ToolSchema(
                name="test_tool",
                description="Test",
                parameters=[
                    ToolParameter(
                        name="op",
                        type="string",
                        description="Operation",
                        required=True,
                        enum=["a", "b", "c"]
                    )
                ]
            )
        )

        # Valid enum
        valid, error = tool.validate_args({"op": "a"})
        assert valid is True

        # Invalid enum
        valid, error = tool.validate_args({"op": "d"})
        assert valid is False


class TestToolLogs:
    """工具日志测试"""

    @pytest.mark.asyncio
    async def test_execution_logged(self, tool_registry):
        """测试执行被记录"""
        await tool_registry.execute(
            agent_id="agent1",
            tool_name="calculator",
            args={"expression": "1+1"}
        )

        logs = tool_registry.get_logs(agent_id="agent1")
        assert len(logs) >= 1

        log = logs[-1]
        assert log["agent_id"] == "agent1"
        assert log["tool_name"] == "calculator"

    @pytest.mark.asyncio
    async def test_logs_filter_by_agent(self, tool_registry):
        """测试按 Agent 筛选日志"""
        await tool_registry.execute(agent_id="agent1", tool_name="calculator", args={"expression": "1+1"})
        await tool_registry.execute(agent_id="agent2", tool_name="calculator", args={"expression": "2+2"})

        logs_agent1 = tool_registry.get_logs(agent_id="agent1")
        assert all(log["agent_id"] == "agent1" for log in logs_agent1)


class TestBuiltinHandlers:
    """内置处理器测试"""

    def test_calculator_handler(self):
        """测试计算器处理器"""
        assert calculator_handler("2 + 3") == "5"
        assert calculator_handler("10 / 2") == "5.0"
        assert calculator_handler("2 ** 8") == "256"

    def test_text_processor_upper(self):
        """测试文本处理器 - 大写"""
        result = text_processor_handler("hello", "upper")
        assert result == "HELLO"

    def test_text_processor_lower(self):
        """测试文本处理器 - 小写"""
        result = text_processor_handler("HELLO", "lower")
        assert result == "hello"

    def test_text_processor_reverse(self):
        """测试文本处理器 - 反转"""
        result = text_processor_handler("hello", "reverse")
        assert result == "olleh"

    def test_text_processor_length(self):
        """测试文本处理器 - 长度"""
        result = text_processor_handler("hello", "length")
        assert result == "5"

    def test_text_processor_word_count(self):
        """测试文本处理器 - 词数"""
        result = text_processor_handler("hello world", "word_count")
        assert result == "2"

    def test_current_time_handler(self):
        """测试当前时间处理器"""
        result = current_time_handler()
        assert result is not None
        # Should be in format YYYY-MM-DD HH:MM:SS
        assert len(result) == 19


# Property-based tests
from hypothesis import given, strategies as st


@given(st.text())
def test_tool_name_length(name):
    """属性测试：工具名称长度"""
    if len(name) > 0:
        tool = Tool(
            name=name,
            description="Test",
            tool_schema=ToolSchema(name=name, description="Test")
        )
        assert tool.name == name


@given(st.text())
def test_tool_description(description):
    """属性测试：工具描述"""
    tool = Tool(
        name="test",
        description=description,
        tool_schema=ToolSchema(name="test", description=description)
    )
    assert tool.description == description
