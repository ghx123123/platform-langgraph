"""
Tool Registry - 工具注册表
支持内置工具和 MCP 工具集成
"""
import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolSource(str, Enum):
    """工具来源"""
    BUILTIN = "builtin"    # 内置工具
    MCP = "mcp"           # MCP 服务器工具
    CUSTOM = "custom"     # 自定义工具


class ToolCategory(str, Enum):
    """工具类别"""
    SEARCH = "search"      # 搜索
    COMPUTATION = "computation"  # 计算
    CODE = "code"         # 代码执行
    FILE = "file"         # 文件操作
    WEB = "web"           # Web 请求
    DATA = "data"         # 数据处理
    UTILITY = "utility"   # 通用工具


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


class ToolSchema(BaseModel):
    """工具 schema"""
    name: str
    description: str
    parameters: List[ToolParameter] = Field(default_factory=list)
    returns: Optional[str] = None


class Tool(BaseModel):
    """工具定义"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    category: ToolCategory = ToolCategory.UTILITY
    source: ToolSource = ToolSource.BUILTIN
    tool_schema: ToolSchema
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)

    def validate_args(self, args: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证参数"""
        for param in self.tool_schema.parameters:
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"

            if param.name in args:
                value = args[param.name]
                expected_type = param.type

                # Type checking
                if expected_type == "string" and not isinstance(value, str):
                    return False, f"Parameter '{param.name}' must be string"
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    return False, f"Parameter '{param.name}' must be number"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return False, f"Parameter '{param.name}' must be boolean"
                elif expected_type == "array" and not isinstance(value, list):
                    return False, f"Parameter '{param.name}' must be array"
                elif expected_type == "object" and not isinstance(value, dict):
                    return False, f"Parameter '{param.name}' must be object"

                # Enum checking
                if param.enum and value not in param.enum:
                    return False, f"Parameter '{param.name}' must be one of {param.enum}"

        return True, None


class MCPTool(Tool):
    """MCP 工具"""
    server_config: Dict[str, Any] = Field(default_factory=dict)
    transport: str = "stdio"  # stdio, sse, http, ws


class ToolExecutionResult(BaseModel):
    """工具执行结果"""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


class ToolRegistry:
    """
    工具注册表

    功能：
    - 注册/注销工具
    - 获取工具详情
    - 执行工具调用
    - 按来源/类别筛选
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._handlers: Dict[str, Callable] = {}
        self._mcp_clients: Dict[str, Any] = {}  # MCP client instances
        self._logs: List[Dict] = []

    # =========================================================================
    # Registration
    # =========================================================================

    def register(self, tool: Tool, handler: Optional[Callable] = None):
        """注册工具"""
        self._tools[tool.name] = tool
        if handler:
            self._handlers[tool.name] = handler

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
        if name in self._handlers:
            del self._handlers[name]
        return True

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def list_all(self) -> List[Tool]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_by_source(self, source: ToolSource) -> List[Tool]:
        """按来源筛选"""
        return [t for t in self._tools.values() if t.source == source]

    def list_by_category(self, category: ToolCategory) -> List[Tool]:
        """按类别筛选"""
        return [t for t in self._tools.values() if t.category == category]

    def list_enabled(self) -> List[Tool]:
        """列出已启用的工具"""
        return [t for t in self._tools.values() if t.enabled]

    # =========================================================================
    # Execution
    # =========================================================================

    async def execute(
        self,
        agent_id: str,
        tool_name: str,
        args: Dict[str, Any]
    ) -> ToolExecutionResult:
        """
        执行工具调用

        流程：
        1. 验证工具存在且已启用
        2. 验证 Agent 有权限调用
        3. 验证参数
        4. 执行工具
        5. 记录日志
        """
        start_time = asyncio.get_event_loop().time()

        # Check tool exists
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolExecutionResult(
                success=False,
                error=f"Tool '{tool_name}' not found"
            )

        # Check tool enabled
        if not tool.enabled:
            return ToolExecutionResult(
                success=False,
                error=f"Tool '{tool_name}' is disabled"
            )

        # Validate args
        valid, error = tool.validate_args(args)
        if not valid:
            return ToolExecutionResult(
                success=False,
                error=f"Invalid arguments: {error}"
            )

        # Execute
        try:
            handler = self._handlers.get(tool_name)
            if not handler:
                return ToolExecutionResult(
                    success=False,
                    error=f"No handler for tool '{tool_name}'"
                )

            # Execute handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**args)
            else:
                result = handler(**args)

            execution_time = asyncio.get_event_loop().time() - start_time

            # Log
            self._log_execution(agent_id, tool_name, args, result, execution_time, True)

            return ToolExecutionResult(
                success=True,
                result=result,
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            self._log_execution(agent_id, tool_name, args, str(e), execution_time, False)

            return ToolExecutionResult(
                success=False,
                error=str(e),
                execution_time=execution_time
            )

    def _log_execution(
        self,
        agent_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        execution_time: float,
        success: bool
    ):
        """记录工具调用日志"""
        log = {
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "tool_name": tool_name,
            "args": args,
            "result": str(result)[:500] if result else None,  # Truncate long results
            "execution_time": execution_time,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        self._logs.append(log)

        # Keep only last 1000 logs
        if len(self._logs) > 1000:
            self._logs = self._logs[-1000:]

    def get_logs(self, agent_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取工具调用日志"""
        logs = self._logs
        if agent_id:
            logs = [l for l in logs if l["agent_id"] == agent_id]
        return logs[-limit:]


# ============================================================================
# Built-in Tools
# =========================================================================

def create_builtin_tools() -> List[Tool]:
    """创建内置工具列表"""

    tools = [
        Tool(
            name="calculator",
            description="执行数学计算",
            category=ToolCategory.COMPUTATION,
            source=ToolSource.BUILTIN,
            tool_schema=ToolSchema(
                name="calculator",
                description="执行数学计算",
                parameters=[
                    ToolParameter(
                        name="expression",
                        type="string",
                        description="数学表达式，如 '2 + 3 * 4'",
                        required=True
                    )
                ],
                returns="计算结果"
            )
        ),
        Tool(
            name="search",
            description="搜索信息",
            category=ToolCategory.SEARCH,
            source=ToolSource.BUILTIN,
            tool_schema=ToolSchema(
                name="search",
                description="搜索信息",
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索查询",
                        required=True
                    ),
                    ToolParameter(
                        name="limit",
                        type="number",
                        description="返回结果数量",
                        required=False,
                        default=5
                    )
                ],
                returns="搜索结果列表"
            )
        ),
        Tool(
            name="code_executor",
            description="执行 Python 代码",
            category=ToolCategory.CODE,
            source=ToolSource.BUILTIN,
            tool_schema=ToolSchema(
                name="code_executor",
                description="执行 Python 代码",
                parameters=[
                    ToolParameter(
                        name="code",
                        type="string",
                        description="要执行的 Python 代码",
                        required=True
                    ),
                    ToolParameter(
                        name="timeout",
                        type="number",
                        description="超时时间（秒）",
                        required=False,
                        default=30
                    )
                ],
                returns="代码执行结果"
            )
        ),
        Tool(
            name="text_processor",
            description="文本处理工具",
            category=ToolCategory.DATA,
            source=ToolSource.BUILTIN,
            tool_schema=ToolSchema(
                name="text_processor",
                description="文本处理",
                parameters=[
                    ToolParameter(
                        name="text",
                        type="string",
                        description="输入文本",
                        required=True
                    ),
                    ToolParameter(
                        name="operation",
                        type="string",
                        description="操作类型",
                        required=True,
                        enum=["upper", "lower", "reverse", "length", "word_count"]
                    )
                ],
                returns="处理结果"
            )
        ),
        Tool(
            name="current_time",
            description="获取当前时间",
            category=ToolCategory.UTILITY,
            source=ToolSource.BUILTIN,
            tool_schema=ToolSchema(
                name="current_time",
                description="获取当前时间",
                parameters=[],
                returns="当前日期时间"
            )
        ),
    ]

    return tools


# ============================================================================
# Built-in Tool Handlers
# =========================================================================

def calculator_handler(expression: str) -> str:
    """计算器处理器"""
    try:
        # 安全评估数学表达式（生产环境应使用 ast.parse 或专用解析器）
        # 注意：这里仅用于演示，生产环境禁止使用 eval
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"


def search_handler(query: str, limit: int = 5) -> List[Dict]:
    """搜索处理器（模拟）"""
    # 实际实现应调用搜索 API
    return [
        {"title": f"Result {i+1} for '{query}'", "url": f"https://example.com/{i+1}"}
        for i in range(min(limit, 3))
    ]


async def code_executor_handler(code: str, timeout: int = 30) -> str:
    """代码执行处理器"""
    try:
        # 创建隔离的命名空间执行代码
        namespace = {}
        exec(code, namespace, namespace)
        result = namespace.get("result", "Code executed successfully")
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"


def text_processor_handler(text: str, operation: str) -> str:
    """文本处理处理器"""
    operations = {
        "upper": str.upper,
        "lower": str.lower,
        "reverse": lambda x: x[::-1],
        "length": len,
        "word_count": lambda x: len(x.split())
    }

    if operation not in operations:
        return f"Unknown operation: {operation}"

    result = operations[operation](text)
    return str(result)


def current_time_handler() -> str:
    """当前时间处理器"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_builtin_handlers() -> Dict[str, Callable]:
    """获取内置工具处理器"""
    return {
        "calculator": calculator_handler,
        "search": search_handler,
        "code_executor": code_executor_handler,
        "text_processor": text_processor_handler,
        "current_time": current_time_handler
    }
