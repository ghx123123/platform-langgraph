# 多智能体协作平台 - 架构设计文档

> 文档状态：v1.0
> 创建日期：2026-04-23

---

## ⚠️ 实现状态说明（2026-07-26 核实）

本文档第二至九章描述的是**原始设想架构**（Agent Runtime + Message Bus + Memory Store + Tool Registry）。
该架构的代码存在于 `backend/agent/`、`backend/memory/`、`backend/tools/`、`backend/message_bus/`，
但**均未挂载到 `backend/app.py`**，不参与实际运行。子系统清单见 `SPEC.md` 开头。

### 当前实际运行架构

```
┌──────────────────────────────────────────────────────┐
│  前端 React (frontend/src/App.tsx) — 三栏教学工作台   │
│  左：上传文档/建会话  中：课堂消息流  右：剖析/环节/督导 │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP + WebSocket
┌───────────────────────▼──────────────────────────────┐
│  FastAPI (backend/app.py) — 仅挂载 3 个路由           │
│  workflows/  │  documents/  │  model_settings/        │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│  LangGraph StateGraph (backend/workflows/graph.py)    │
│                                                       │
│  content_analysis → teaching_design → ┌─────────────┐ │
│                                        │teach_knowledge│
│                                        │      ↓       │ │
│                                        │student_question│
│                                        │      ↓       │ │
│                                        │teacher_answer│ │
│                                        │      ↓       │ │
│                                        │supervisor_comment│
│                                        └──────┬───────┘ │
│         达标(≥85分)或到达上限 ← route_iteration ┘        │
│                    ↓                                   │
│                finalize → END                          │
└───────────────────────┬──────────────────────────────┘
                        │
        ┌───────────────┴────────────────┐
        │  SQLite: platform.db (运行记录/事件)  │
        │          checkpoints.db (LangGraph)  │
        └──────────────────────────────────────┘
```

**模型层** (`backend/workflows/llm.py`)：`mock` 为确定性演示模型（产出由上传文档驱动）；
`openai_compatible` 走真实 LLM。二者通过 `/api/settings/model` 热切换。

---

## 一、架构概述

### 1.1 设计目标

- **模块化**: 各组件松耦合，易于独立开发和测试
- **可扩展**: 支持新增工具、Agent 类型、存储后端
- **可观测**: 完整日志和监控支持
- **高性能**: 支持 10+ 并发 Agent

### 1.2 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web 前端 (React)                          │
│   Agent 创建 │ 角色配置 │ 记忆管理 │ 工具管理 │ 实时协作      │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket / SSE / HTTP
┌────────────────────────▼────────────────────────────────────────┐
│                      API Gateway (FastAPI)                        │
│   Agent CRUD │ 消息路由 │ 工具调度 │ 记忆管理 │ 协作协调      │
└────┬───────────────┬───────────────┬───────────────┬─────────────┘
     │               │               │               │
┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐  ┌─────▼─────┐
│ Agent    │   │  Message  │  │  Tool   │  │  Memory   │
│ Runtime  │◄─┤   Bus     │◄─┤ Registry│◄─┤  Store    │
│          │   │           │  │         │  │           │
│ - 角色   │   │ - Pub/Sub│  │ - MCP   │  │ - SQLite  │
│ - 工具   │   │ - 队列   │  │ - HTTP  │  │ - Qdrant  │
│ - 记忆   │   │ - 广播   │  │ - Code  │  │ - Redis   │
└─────────┘   └───────────┘  └─────────┘  └───────────┘
```

---

## 二、核心组件

### 2.1 Agent Runtime

**职责**: 管理 Agent 的生命周期和核心能力

```
Agent 生命周期:
创建 ──► 初始化 ──► 运行 ──► 等待 ──► 完成/失败
              │            │            │
              ▼            ▼            ▼
           注册工具     消息循环      超时/错误
           加载记忆     工具调用     清理资源
```

**核心模块**:
- `runtime.py`: Agent 类定义和生命周期管理
- `coordinator.py`: 协作协调器和任务管理

**关键设计**:
1. **依赖注入**: Agent 不直接创建依赖，通过构造函数注入
2. **异步优先**: 所有 IO 操作使用 async/await
3. **消息驱动**: 通过消息队列处理协作请求

### 2.2 Message Bus

**职责**: 处理 Agent 之间的消息传递

**实现**:
```python
class MessageBus:
    async def send_direct(to_agent: str, message: Message)
    async def broadcast(message: Message)
    async def publish(topic: str, message: Message)
```

**协议支持**:
- 点对点消息
- 广播消息
- 话题订阅/发布

### 2.3 Memory Store

**职责**: 分层记忆管理

```
┌─────────────────────────────────────────┐
│              Memory Store                  │
├─────────────────────────────────────────┤
│  Short-term (Redis)                     │
│  - 当前会话上下文                        │
│  - 自动过期 (24h)                       │
├─────────────────────────────────────────┤
│  Long-term (SQLite + Qdrant)           │
│  - Agent 持久记忆                      │
│  - 向量索引 (Qdrant)                   │
├─────────────────────────────────────────┤
│  Episodic (SQLite)                     │
│  - 关键事件记录                        │
│  - 时间戳 + 内容                        │
└─────────────────────────────────────────┘
```

### 2.4 Tool Registry

**职责**: 工具注册和执行

**架构**:
```
┌─────────────────────────────────────────┐
│           Tool Registry                   │
├─────────────────────────────────────────┤
│  Built-in Tools                         │
│  - calculator, search, text_processor   │
├─────────────────────────────────────────┤
│  MCP Tools (mcp[cli] SDK)              │
│  - 外部 MCP 服务器连接                 │
├─────────────────────────────────────────┤
│  Custom Tools                          │
│  - 用户注册的自定义工具                │
└─────────────────────────────────────────┘
```

---

## 三、消息协议

### 3.1 消息格式

```json
{
  "id": "uuid",
  "msg_type": "chat | subtask_request | realtime_review | clarification_request | response | escalation",
  "priority": "P0 | P1 | P2",
  "from_agent": "agent_name",
  "to": "agent_name | * | topic_name",
  "content": { ... },
  "deadline": "immediate | 2min | 5min",
  "callback": "agent_name",
  "created_at": "ISO8601"
}
```

### 3.2 协作流程

```
澄清者 ──► 发现问题 ──► 发送 clarification_request ──► 设计者
                                                    │
设计者 ◄── 响应澄清 ──────────────────────────────────┘
    │
    ▼
设计者 ──► 完成设计 ──► 发送 subtask_request ──► 编码者
                                                   │
编码者 ◄── 响应结果 ─────────────────────────────────┘
    │
    ▼
编码者 ──► 完成编码 ──► 发送 realtime_review ──► 审查者
                                                     │
审查者 ◄── 审查通过 ─────────────────────────────────┘
```

---

## 四、数据模型

### 4.1 Agent

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 唯一标识 |
| name | string | 显示名称 |
| role | string | 角色描述 (system prompt) |
| description | string | 简短描述 |
| avatar | string | 头像 emoji |
| tools | string[] | 可用工具列表 |
| memory_scope | enum | private/team/shared |
| status | enum | online/busy/offline |

### 4.2 Message

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 唯一标识 |
| msg_type | enum | 消息类型 |
| priority | enum | 优先级 |
| from_agent | string | 发送者 |
| to | string | 接收者 (* = 广播) |
| content | object | 消息内容 |
| deadline | string | 截止时间 |

### 4.3 Memory

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 唯一标识 |
| agent_id | UUID | 所属 Agent |
| memory_type | enum | stm/ltm/episodic |
| content | string | 记忆内容 |
| embedding | float[] | 向量 (可选) |
| metadata | object | 元数据 |

---

## 五、技术选型

| 组件 | 技术 | 原因 |
|------|------|------|
| 后端框架 | FastAPI 0.100+ | async 原生支持，类型安全 |
| Agent Runtime | Python 3.11+ | 丰富 AI 生态 |
| 消息总线 | Redis Pub/Sub | 高性能、持久化 |
| 短期记忆 | Redis | 自动过期、TTL 支持 |
| 长期记忆 | SQLite + Qdrant | 简单 + 向量搜索 |
| MCP SDK | mcp[cli] | Claude Code 同款 |
| 前端框架 | React 18+ | 成熟生态 |
| 状态管理 | Zustand | 轻量、简单 |
| WebSocket | Socket.io | 自动重连、房间 |

---

## 六、部署架构

### 6.1 开发环境

```
┌─────────────────────────────────────┐
│          开发机器                    │
│  ┌───────────┐  ┌───────────┐      │
│  │  Frontend │  │  Backend  │      │
│  │  (Vite)   │  │  (FastAPI)│      │
│  └───────────┘  └───────────┘      │
│         │              │            │
│         └──────┬───────┘            │
│                ▼                    │
│         ┌───────────┐               │
│         │   Redis   │               │
│         └───────────┘               │
└─────────────────────────────────────┘
```

### 6.2 生产环境

```
┌─────────────────────────────────────────────────────────┐
│                      Docker Compose                       │
├─────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐          │
│  │  Frontend │  │  Backend  │  │   Redis   │          │
│  │  (nginx)  │  │  (FastAPI)│  │           │          │
│  └───────────┘  └───────────┘  └───────────┘          │
│         │              │                               │
│         │              ▼                               │
│         │       ┌───────────┐                         │
│         │       │  SQLite   │                         │
│         │       └───────────┘                         │
│         │                                           │
│         └──────────────────────────────────────────► WebSocket
└─────────────────────────────────────────────────────────┘
```

---

## 七、安全设计

### 7.1 工具权限隔离

```
Agent A ──► [tool1, tool2] ──► Tool Registry ──► 验证权限
Agent B ──► [tool2, tool3] ──► Tool Registry ──► 验证权限
```

### 7.2 记忆访问控制

```
Agent A ──► Memory Store ──► 验证 agent_id ──► 返回 A 的记忆
Agent B ──► Memory Store ──► 验证 agent_id ──► 返回 B 的记忆
```

### 7.3 消息来源验证

```
Message ──► 验证 from_agent ──► 验证 agent_id ──► 路由消息
```

---

## 八、可扩展性

### 8.1 新增工具类型

```python
class CustomTool(Tool):
    async def execute(self, args: dict) -> Any:
        # 自定义执行逻辑
        pass
```

### 8.2 新增存储后端

```python
class VectorStore(ABC):
    @abstractmethod
    async def search(query: str, limit: int) -> List[Memory]:
        pass
```

### 8.3 新增 Agent 类型

```python
class SpecializedAgent(Agent):
    # 继承 Agent，扩展特定能力
    pass
```

---

## 九、监控和日志

### 9.1 关键指标

| 指标 | 说明 |
|------|------|
| Agent 在线数 | 实时在线 Agent 数量 |
| 消息延迟 | P95 消息传递延迟 |
| 工具调用成功率 | 工具调用成功率 |
| 记忆存储大小 | 各 Agent 记忆占用 |

### 9.2 日志分类

| 日志类型 | 内容 |
|----------|------|
| Agent 日志 | Agent 状态变化、消息收发 |
| 工具日志 | 工具调用输入输出 |
| 系统日志 | 启动、关闭、错误 |

---

## 十、目录结构

```
multi_agent_platform/
├── SPEC.md                          # 需求规格文档
├── ARCHITECTURE.md                  # 架构设计文档 (本文档)
├── README.md                        # 项目说明
│
├── backend/
│   ├── main.py                     # FastAPI 入口
│   ├── requirements.txt             # 后端依赖
│   │
│   ├── agent/
│   │   ├── runtime.py              # Agent 运行时
│   │   ├── coordinator.py          # 协作协调器
│   │   └── protocol.py            # 消息协议
│   │
│   ├── memory/
│   │   ├── store.py                # 记忆存储
│   │   ├── stm.py                 # 短期记忆
│   │   └── ltm.py                 # 长期记忆
│   │
│   ├── tools/
│   │   ├── registry.py            # 工具注册
│   │   ├── builtin.py             # 内置工具
│   │   └── mcp.py                 # MCP 集成
│   │
│   ├── message_bus/
│   │   └── bus.py                 # 消息总线
│   │
│   ├── execution/                  # 2026-05-07 新增
│   │   └── router.py              # 执行状态 API
│   │
│   └── models/
│       ├── agent.py                # Agent 模型
│       ├── message.py              # Message 模型
│       └── memory.py              # Memory 模型
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   │
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── visualization/       # 2026-05-07 新增：可视化组件库
│   │   │   │   ├── AgentGraph/      # Agent 协作图谱
│   │   │   │   ├── DataImport/      # 数据导入可视化
│   │   │   │   ├── TaskBoard/       # 任务执行看板
│   │   │   │   └── ResultDashboard/ # 结果仪表板
│   │   │   └── enhanced/            # 2026-05-07 新增：增强组件
│   │   ├── stores/
│   │   │   ├── importStore.ts       # 2026-05-07 新增
│   │   │   └── executionStore.ts   # 2026-05-07 新增
│   │   ├── types/
│   │   │   └── visualization.ts    # 2026-05-07 新增
│   │   └── utils/
│   │       └── cn.ts               # 2026-05-07 新增
│   │
│   └── index.html
│
├── tests/
│   ├── test_agent_runtime.py
│   ├── test_memory_store.py
│   ├── test_message_bus.py
│   ├── test_tool_registry.py
│   └── test_integration.py
│
└── docker/
    ├── docker-compose.yml
    └── Dockerfile
```

---

*文档版本: v1.1 | 更新日期: 2026-05-07*
