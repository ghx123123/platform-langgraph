"""
Agent Coordinator - 协作协调器
负责任务分配、状态追踪和迭代控制
"""
import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .runtime import Agent, AgentRegistry, AgentStatus


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    """任务优先级"""
    P0 = "P0"  # 立即处理
    P1 = "P1"  # 尽快处理
    P2 = "P2"  # 按顺序处理


class Task(BaseModel):
    """协作任务"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    task_type: str = "general"  # general, review, design, coding, diagnosis
    priority: TaskPriority = TaskPriority.P2
    status: TaskStatus = TaskStatus.PENDING
    requester: str = ""  # 请求者 Agent
    assignee: Optional[str] = None  # 执行者 Agent
    depends_on: List[str] = Field(default_factory=list)  # 依赖任务
    subtasks: List[str] = Field(default_factory=list)  # 子任务列表
    iterations: int = 0
    max_iterations: int = 3
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class Coordinator:
    """
    协作协调器

    职责：
    - 任务创建和分配
    - 状态追踪和迭代控制
    - 冲突仲裁
    - 超时处理
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        message_bus=None
    ):
        self._agent_registry = agent_registry
        self._message_bus = message_bus
        self._tasks: Dict[str, Task] = {}
        self._task_history: List[Task] = []
        self._iteration_counts: Dict[str, int] = {}  # agent_id -> iteration count

    # =========================================================================
    # Task Management
    # =========================================================================

    async def create_task(
        self,
        title: str,
        requester: str,
        task_type: str = "general",
        priority: TaskPriority = TaskPriority.P2,
        description: str = "",
        assignee: Optional[str] = None,
        depends_on: Optional[List[str]] = None
    ) -> Task:
        """创建任务"""
        task = Task(
            title=title,
            description=description,
            task_type=task_type,
            priority=priority,
            requester=requester,
            assignee=assignee,
            depends_on=depends_on or []
        )

        self._tasks[task.id] = task
        return task

    async def assign_task(self, task_id: str, assignee: str) -> bool:
        """分配任务给 Agent"""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.assignee = assignee
        task.status = TaskStatus.IN_PROGRESS
        task.updated_at = datetime.now()

        # Send message to assignee
        if self._message_bus:
            from .runtime import Message
            message = Message(
                msg_type="subtask_request",
                from_agent="coordinator",
                to=assignee,
                content={
                    "task_id": task.id,
                    "task": task.title,
                    "description": task.description,
                    "priority": task.priority.value
                },
                deadline="2min",
                callback="coordinator"
            )
            await self._message_bus.send_direct(assignee, message)

        return True

    async def complete_task(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """完成任务"""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        task.result = result
        task.updated_at = datetime.now()

        # Notify requester
        if self._message_bus and task.requester:
            from .runtime import Message
            message = Message(
                msg_type="response",
                from_agent="coordinator",
                to=task.requester,
                content={
                    "task_id": task.id,
                    "status": "completed",
                    "result": result
                }
            )
            await self._message_bus.send_direct(task.requester, message)

        # Move to history
        self._task_history.append(task)
        del self._tasks[task_id]

        return True

    async def fail_task(self, task_id: str, error: str) -> bool:
        """标记任务失败"""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.status = TaskStatus.FAILED
        task.error = error
        task.updated_at = datetime.now()

        # Notify requester
        if self._message_bus and task.requester:
            from .runtime import Message
            message = Message(
                msg_type="response",
                from_agent="coordinator",
                to=task.requester,
                content={
                    "task_id": task.id,
                    "status": "failed",
                    "error": error
                }
            )
            await self._message_bus.send_direct(task.requester, message)

        return True

    async def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        assignee: Optional[str] = None
    ) -> List[Task]:
        """列出任务"""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        if assignee:
            tasks = [t for t in tasks if t.assignee == assignee]

        return tasks

    # =========================================================================
    # Collaboration
    # =========================================================================

    async def start_collaboration(
        self,
        task_title: str,
        requester: str,
        agents: List[str],
        roles: Dict[str, str]  # agent_name -> role
    ) -> Task:
        """
        启动多 Agent 协作

        流程：
        1. 创建主任务
        2. 分配子任务给各 Agent
        3. 追踪执行状态
        """
        # Create main task
        main_task = await self.create_task(
            title=task_title,
            requester=requester,
            task_type="general",
            priority=TaskPriority.P1
        )

        # Create subtasks for each agent
        for agent_name, role in roles.items():
            subtask = await self.create_task(
                title=f"[{role}] {task_title}",
                requester=main_task.id,
                task_type=role,
                priority=TaskPriority.P1,
                assignee=agent_name
            )
            main_task.subtasks.append(subtask.id)

        return main_task

    async def handle_escalation(
        self,
        from_agent: str,
        reason: str,
        history: List[str]
    ) -> Dict[str, Any]:
        """处理升级请求"""
        # Log escalation
        print(f"[Coordinator] ESCALATION from {from_agent}: {reason}")

        # Track iteration
        if from_agent not in self._iteration_counts:
            self._iteration_counts[from_agent] = 0
        self._iteration_counts[from_agent] += 1

        # Decide action based on iteration count
        count = self._iteration_counts[from_agent]

        if count >= 3:
            # After 3 escalations, mark as blocked
            return {
                "action": "block",
                "message": f"Agent {from_agent} blocked after 3 escalations"
            }

        # Try to resolve or reassign
        return {
            "action": "retry",
            "message": f"Attempting to resolve (iteration {count})"
        }

    # =========================================================================
    # State Management
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """获取协调器状态"""
        return {
            "active_tasks": len(self._tasks),
            "completed_tasks": len(self._task_history),
            "agent_iterations": self._iteration_counts,
            "online_agents": [a.name for a in self._agent_registry.list_online()]
        }

    def get_pending_tasks(self) -> List[Task]:
        """获取待处理任务"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    def get_blocked_tasks(self) -> List[Task]:
        """获取阻塞任务"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.BLOCKED]


class RolePreset:
    """
    角色预设

    定义 7 种预设角色的系统提示和行为模式。
    """

    PRESETS = {
        "clarifier": {
            "name": "澄清者",
            "description": "发现需求矛盾、识别技术难点、澄清不明确之处",
            "system_prompt": """你是一个澄清者 (Clarifier)。

职责：
- 发现需求中的矛盾和不一致
- 识别技术实现中的难点
- 澄清模糊或不明确的需求
- 在发现问题时主动沟通

当遇到以下情况时，必须主动发消息：
- 发现需求有矛盾
- 识别到无法实现的技术点
- 输入信息不完整或模糊
- 发现潜在的风险

你的目标是确保需求清晰、技术可行。""",
            "triggers": ["需求矛盾", "技术难点", "输入不明确", "风险识别"]
        },

        "verifier": {
            "name": "验证者",
            "description": "审查发现的问题、验证方案正确性",
            "system_prompt": """你是一个验证者 (Verifier)。

职责：
- 审查发现的问题
- 验证方案的正确性和完整性
- 确保解决方案满足需求
- 检查是否有遗漏的边界情况

当收到审查请求时，你必须：
- 仔细检查目标内容
- 识别所有问题（按严重程度分类）
- 提供明确的修复建议
- 如果通过，明确标注 APPROVED

你的目标是确保交付质量。""",
            "triggers": ["需要审查", "问题发现", "方案验证"]
        },

        "designer": {
            "name": "设计者",
            "description": "完成模块设计、制定技术方案",
            "system_prompt": """你是一个设计者 (Designer)。

职责：
- 制定技术实现方案
- 设计模块架构和接口
- 评估技术选型和权衡
- 考虑可扩展性和可维护性

当需要设计时，你必须：
- 明确设计目标
- 提供多种方案供选择
- 说明每种方案的优缺点
- 给出推荐方案

你的目标是产出高质量、可实现的设计。""",
            "triggers": ["需要设计", "方案规划", "架构设计"]
        },

        "diagnostician": {
            "name": "诊断者",
            "description": "检查系统问题、分析根因",
            "system_prompt": """你是一个诊断者 (Diagnostician)。

职责：
- 检查系统问题
- 分析问题根因
- 提出修复建议
- 防止问题再次发生

当发现问题时，你必须：
- 收集相关日志和信息
- 分析可能的根因
- 给出修复步骤
- 建议预防措施

你的目标是快速定位并解决问题。""",
            "triggers": ["系统问题", "错误分析", "根因诊断"]
        },

        "challenger": {
            "name": "质询者",
            "description": "挑战逻辑漏洞、验证假设",
            "system_prompt": """你是一个质询者 (Challenger)。

职责：
- 挑战现有的逻辑和假设
- 发现潜在的漏洞
- 提出反例和边界情况
- 确保方案的健壮性

当你质疑时，你必须：
- 明确指出质疑点
- 提供支持质疑的证据
- 考虑反驳的可能性
- 给出建设性的替代方案

你的目标是确保方案经得起推敲。""",
            "triggers": ["逻辑质疑", "假设验证", "边界挑战"]
        },

        "coder": {
            "name": "编码者",
            "description": "执行具体编码任务",
            "system_prompt": """你是一个编码者 (Coder)。

职责：
- 按照设计实现代码
- 遵循代码规范
- 编写测试用例
- 确保代码质量

当你实现时，你必须：
- 严格按照设计执行
- 编写清晰、可读的代码
- 包含必要的注释
- 确保测试通过

你的目标是产出高质量的生产代码。""",
            "triggers": ["需要实现", "编码任务", "功能开发"]
        },

        "reviewer": {
            "name": "审查者",
            "description": "代码审查、规范检查",
            "system_prompt": """你是一个审查者 (Reviewer)。

职责：
- 审查代码质量和规范
- 检查是否符合最佳实践
- 确保代码可维护性
- 提供改进建议

当你审查时，你必须：
- 检查代码风格和规范
- 验证安全和性能
- 评估可维护性
- 给出明确的审查结论

你的目标是提升整体代码质量。""",
            "triggers": ["代码审查", "规范检查", "质量评估"]
        }
    }

    @classmethod
    def get_preset(cls, role: str) -> Optional[Dict[str, Any]]:
        """获取角色预设"""
        return cls.PRESETS.get(role)

    @classmethod
    def list_roles(cls) -> List[str]:
        """列出所有角色"""
        return list(cls.PRESETS.keys())

    @classmethod
    def create_agent_config(cls, role: str, name: str) -> Dict[str, Any]:
        """创建角色配置"""
        preset = cls.get_preset(role)
        if not preset:
            raise ValueError(f"Unknown role: {role}")

        return {
            "name": name,
            "role": preset["system_prompt"],
            "description": preset["description"],
            "avatar": cls._get_role_emoji(role)
        }

    @classmethod
    def _get_role_emoji(cls, role: str) -> str:
        """获取角色 emoji"""
        emojis = {
            "clarifier": "🔍",
            "verifier": "✅",
            "designer": "📐",
            "diagnostician": "🩺",
            "challenger": "⚔️",
            "coder": "💻",
            "reviewer": "🔎"
        }
        return emojis.get(role, "🤖")
