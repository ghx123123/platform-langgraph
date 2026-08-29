# LangGraph 多智能体架构

## 执行图

```text
START
  |
planner
  |
  +---- Send(researcher/feasibility/teacher) ----+
  +---- Send(analyst/risk/learner) --------------+--> synthesizer --> reviewer
  +---- Send(challenger/value/assessor) ---------+                       |
                                                                          +-- score < threshold --> refine --+
                                                                          |                               |
                                                                          +-- PASS / revision limit ------+--> finalize --> END
```

`planner` 根据模板角色生成任务。条件边使用 LangGraph `Send` 动态扇出，专家结果通过 reducer 合并。`reviewer` 输出结构化评分；低于模板阈值且未达到修订上限时进入 `refine`，再回到审阅节点。

## 模块边界

```text
backend/app.py
  -> workflows/router.py       HTTP / WebSocket 边界
  -> workflows/service.py      运行生命周期与异步任务
  -> workflows/graph.py        LangGraph 状态、节点和路由
  -> workflows/llm.py          OpenAI 兼容模型适配
  -> workflows/repository.py   SQLite 运行与事件仓库
  -> workflows/events.py       进程内实时事件分发
  -> core/*                    配置、异常和请求上下文
```

控制器不包含编排逻辑，服务层不依赖 FastAPI 请求类型。所有请求由 Pydantic 在边界校验，业务异常由应用级处理器转换成统一错误结构。

## 持久化与恢复

- `workflow_runs` 保存运行状态、最终输出、质量报告和模型提供方。
- `workflow_events` 以自增序列保存节点事件，WebSocket 新连接先回放再订阅实时队列。
- `AsyncSqliteSaver` 保存每个 `thread_id` 的 LangGraph checkpoint。
- SQLite 启用 WAL，运行仓库和 checkpoint 使用独立文件以降低锁冲突。
- `backend/migrations` 中的版本化 SQL 由 `schema_migrations` 表记录并按顺序执行。

当前版本保存了恢复所需的 checkpoint，但 UI 只开放新建、查看和取消。后续可在服务层基于 `thread_id` 增加从 checkpoint 继续、人工中断审批和时间旅行调试。

## 模型适配

`LLM_PROVIDER=mock` 仅用于本地确定性测试，界面会显示 `mock:deterministic-mock`。`openai_compatible` 使用 `ChatOpenAI`，通过 `LLM_BASE_URL` 连接兼容服务。配置在启动时校验；生产环境禁止通配 CORS。

## 实时语义

事件类型包括：

- `run.queued`、`run.started`、`run.completed`、`run.failed`、`run.cancelled`
- `node.started`、`node.completed`
- `review.completed`

节点事件包含 `node`、人类可读消息和结构化 `payload`。前端用事件重建节点状态，不依赖易丢失的瞬时内存状态。
