# 多智能体协作平台 - 需求规格文档

> 文档状态：v1.0
> 创建日期：2026-04-23

> 当前教学产品的重构需求与验收基线见
> `docs/平台逻辑重构需求基线_2026-08-11.md`。本文其余章节主要保留原始通用 Agent 平台设想，不作为当前网页功能开发依据。

---

## ⚠️ 实现状态说明（2026-07-26 核实）

本文档描述的是**原始设想**（通用 Agent 协作平台：Agent CRUD、分层记忆、工具注册、消息总线）。
当前实际运行的产品是**多智能体课程教学设计平台**，形态与本文档存在显著差异。

以 `backend/app.py` 实际挂载的路由为准：

| 子系统 | 目录 | 状态 |
|--------|------|------|
| 教学工作流 | `backend/workflows/` | ✅ 已挂载，产品主线 |
| 文档解析 | `backend/documents/` | ✅ 已挂载 |
| 模型设置 | `backend/model_settings/` | ✅ 已挂载 |
| Agent 运行时 | `backend/agent/` | ⚠️ 未挂载，本文档第 2.1/5.1 节的遗留实现 |
| 分层记忆 | `backend/memory/` | ⚠️ 未挂载，对应第 2.2/5.2 节 |
| 工具注册 | `backend/tools/` | ⚠️ 未挂载，对应第 2.3/5.3 节 |
| 消息总线 | `backend/message_bus/` | ⚠️ 未挂载，对应第 2.4/5.4 节 |
| 辩论子系统 | `backend/debate/` | ⚠️ 未挂载 |
| 教学子系统（旧版） | `backend/teaching/` | ⚠️ 未挂载，已被 `workflows/` 取代 |
| 执行状态 | `backend/execution/` | ⚠️ 未挂载 |

**当前产品的真实能力**见 `README.md`；教学流程的实现见 `backend/workflows/graph.py`。
未挂载子系统的代码仍保留在仓库中，如需启用需重新接入 `app.py` 并补充测试。

---

## 一、项目概述

### 1.1 项目目标

开发一个独立的**多智能体协作平台**，支持：
- Web 前端界面（React）
- 可视化创建和配置 Agent 角色
- Agent 独立记忆存储（分层记忆系统）
- 工具调用（MCP 协议支持）
- 多 Agent 实时协作

### 1.2 术语定义

| 术语 | 定义 |
|------|------|
| Agent | 智能体，具有独立思考、沟通、工具调用能力的实体 |
| 角色 (Role) | Agent 的行为描述，决定其响应方式和能力范围 |
| 记忆 (Memory) | Agent 的上下文存储，分短期/长期/事件记忆 |
| 工具 (Tool) | Agent 可调用的外部能力（MCP 协议） |
| 协作 (Collaboration) | 多 Agent 之间的消息传递和任务协调 |

---

## 二、功能需求

### 2.1 Agent 管理

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 创建 Agent | 指定名称、角色描述、头像 emoji | P0 |
| 配置工具权限 | 设定 Agent 可调用的工具列表 | P0 |
| 查看状态 | 显示 online/busy/offline 状态 | P0 |
| 删除 Agent | 移除 Agent 及关联记忆 | P1 |
| 克隆 Agent | 复制现有 Agent 配置创建新实例 | P2 |
| 查看 Agent 详情 | 查看配置、状态、工具列表 | P1 |

### 2.2 记忆系统

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 短期记忆 | 基于 Redis 的会话上下文，自动 24h 过期 | P0 |
| 长期记忆 | 基于 SQLite 的持久存储，支持向量检索 | P0 |
| 记忆搜索 | 基于 Qdrant 的语义搜索能力 | P1 |
| 记忆查看/编辑 | Web 界面查看和手动修改记忆 | P1 |
| 记忆隔离 | 每个 Agent 独立的记忆空间 | P0 |
| 事件记忆 | 记录关键交互事件用于回溯 | P2 |

### 2.3 工具系统

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 内置工具 | 搜索、计算、代码执行等基础工具 | P0 |
| MCP 工具集成 | 连接外部 MCP 服务器 | P1 |
| 工具权限配置 | 按 Agent 分配工具访问权限 | P0 |
| 工具使用日志 | 记录工具调用历史和结果 | P1 |
| 自定义工具 | 用户注册自定义工具 | P2 |

### 2.4 协作系统

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 点对点消息 | Agent 之间的直接消息传递 | P0 |
| 广播消息 | 向所有 Agent 或特定话题广播 | P1 |
| 话题订阅 | Agent 订阅感兴趣的话题 | P1 |
| 任务分配 | 主协调者向子 Agent 分配任务 | P0 |
| 角色预设 | 7 种预设角色（见 2.4.1） | P0 |

#### 2.4.1 预设角色

| 角色 | 职责 | 触发场景 |
|------|------|---------|
| 澄清者 | 发现需求矛盾、识别技术难点 | 输入不明确 |
| 验证者 | 审查发现的问题、验证方案 | 需要审查 |
| 设计者 | 完成模块设计、方案规划 | 需要设计 |
| 诊断者 | 检查系统问题、分析根因 | 发现严重问题 |
| 质询者 | 挑战逻辑漏洞、验证假设 | 发现逻辑问题 |
| 编码者 | 执行具体编码任务 | 需要实现 |
| 审查者 | 代码审查、规范检查 | 需要审查 |

### 2.5 前端界面

| 功能 | 描述 | 优先级 |
|------|------|--------|
| Agent 列表 | 展示所有 Agent 及状态 | P0 |
| 创建 Agent | 弹窗表单创建新 Agent | P0 |
| Chat 对话 | 与 Agent 进行对话交互 | P0 |
| 消息历史 | 查看对话和广播消息记录 | P1 |
| 记忆面板 | 查看/编辑 Agent 记忆 | P1 |
| 工具面板 | 配置 Agent 工具权限 | P1 |
| 实时状态 | WebSocket 实时更新状态 | P0 |

---

## 三、非功能需求

### 3.1 性能指标

| 指标 | 要求 |
|------|------|
| API 响应时间 | < 200ms (p95) |
| WebSocket 消息延迟 | < 100ms (p95) |
| 并发 Agent 数量 | 支持 10+ 并发 |
| 记忆搜索延迟 | < 500ms |
| 系统可用性 | 7x24 运行 |

### 3.2 安全要求

| 要求 | 说明 |
|------|------|
| 工具权限隔离 | Agent 只能调用授权的工具 |
| 路径遍历防护 | 禁止工具访问指定目录外的文件 |
| 消息来源验证 | 验证消息发送者身份 |
| 记忆访问控制 | Agent 只能访问自己的记忆 |

### 3.3 可维护性

| 要求 | 说明 |
|------|------|
| 模块化设计 | 各组件松耦合，易于替换 |
| 日志完整 | 关键操作有审计日志 |
| 配置外置 | 敏感配置通过环境变量注入 |

---

## 四、数据模型

### 4.1 Agent

```python
{
    "id": "uuid",
    "name": "显示名称",
    "role": "角色描述 (system prompt)",
    "description": "简短描述",
    "avatar": "emoji",
    "tools": ["tool1", "tool2"],
    "memory_scope": "private | team | shared",
    "status": "online | busy | offline",
    "created_at": "datetime",
    "updated_at": "datetime"
}
```

### 4.2 Message

```python
{
    "id": "uuid",
    "msg_type": "subtask_request | realtime_review | clarification_request | response | escalation | chat",
    "priority": "P0 | P1 | P2",
    "from": "agent_name",
    "to": "agent_name | * | topic_name",
    "content": {},
    "deadline": "immediate | 2min | 5min",
    "callback": "agent_name",
    "created_at": "datetime"
}
```

### 4.3 Memory

```python
{
    "id": "uuid",
    "agent_id": "uuid",
    "memory_type": "stm | ltm | episodic",
    "key": "optional for stm",
    "content": "记忆内容",
    "embedding": "vector (for ltm)",
    "metadata": {},
    "created_at": "datetime",
    "expires_at": "datetime (for stm)"
}
```

---

## 五、API 设计

### 5.1 Agent API

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/agents | 创建 Agent |
| GET | /api/agents | 获取 Agent 列表 |
| GET | /api/agents/{id} | 获取 Agent 详情 |
| PUT | /api/agents/{id} | 更新 Agent |
| DELETE | /api/agents/{id} | 删除 Agent |
| POST | /api/agents/{id}/clone | 克隆 Agent |
| POST | /api/agents/{id}/think | 发送对话请求 |
| GET | /api/agents/{id}/status | 获取状态 |

### 5.2 Memory API

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/agents/{id}/memories | 获取记忆列表 |
| POST | /api/agents/{id}/memories | 添加记忆 |
| GET | /api/agents/{id}/memories/{mid} | 获取记忆详情 |
| PUT | /api/agents/{id}/memories/{mid} | 更新记忆 |
| DELETE | /api/agents/{id}/memories/{mid} | 删除记忆 |
| GET | /api/agents/{id}/memories/search | 搜索记忆 |

### 5.3 Tool API

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/tools | 获取工具列表 |
| POST | /api/tools | 注册自定义工具 |
| GET | /api/tools/{name} | 获取工具详情 |
| DELETE | /api/tools/{name} | 移除工具 |

### 5.4 Collaboration API

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/messages/send | 发送消息 |
| POST | /api/messages/broadcast | 广播消息 |
| GET | /api/messages/history | 获取消息历史 |
| GET | /api/topics | 获取话题列表 |
| POST | /api/topics/{name}/subscribe | 订阅话题 |

---

## 六、验证方案

### 6.1 单元测试

```bash
cd backend && pytest tests/ -v
```

### 6.2 集成测试

```bash
docker-compose up -d
curl -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "助手", "role": "你是一个有帮助的助手"}'
```

### 6.3 协作测试

1. 创建多个 Agent（澄清者、验证者、编码者）
2. 配置协作任务
3. 验证消息传递和记忆隔离

---

## 七、待办事项

- [x] 创建 SPEC.md 需求规格文档
- [ ] 创建 ARCHITECTURE.md 架构设计文档
- [ ] 实现 Agent Runtime
- [ ] 实现 Memory Store
- [ ] 实现 Message Bus
- [ ] 实现 Tool Registry
- [x] 实现 Web 前端（React + Vite + Tailwind + Radix UI）
- [x] 多智能体流程可视化（Agent图谱 + 数据导入 + 执行看板 + 结果仪表板）
- [ ] 编写单元测试
- [ ] Docker 部署配置

---

*文档版本: v1.1 | 更新日期: 2026-05-07*
