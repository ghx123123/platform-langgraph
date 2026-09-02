# 项目上下文引导提示词（新会话快速上手版）

> 把下面整段粘贴给新会话，或用 `!` 前缀运行 `cat docs/PROJECT_CONTEXT.md` 让它读（我已在 `docs/PROJECT_CONTEXT.md` 存了一份）。

---

## 你正在接手什么

**多智能体课程教学平台**（`D:\paper\dsh\platform-langgraph`）：教师对照教学大纲/教材组织一节课的教学设计，由多个 AI 智能体（教材分析、教学设计、讲授、分层学生、答疑、督导、成果整理）协作完成，最终导出可编辑 Word 教案。

**它有两个底层的 AI 引擎**，别混淆：

| 引擎 | 角色 | 现状 |
|---|---|---|
| **dsh**（DeepSeek Harness SDK，走 stdio 桥进程）| 智能体内核：读教材/生成/答疑/督导 | 已是主引擎（面板模型 `minimax-m3`）|
| LangGraph | 流程编排骨架（7 节点 DAG）| 保留，但**节点内部已换成 dsh 智能体** |

## 已打通的关键链路（2026-09-02 全实测）

```
用户一句话 → LangGraph 编排(7节点) → 每节点调 dsh 智能体
  ├─ content_analysis: dsh agent_iterate(2轮多轮记忆+自主迭代) → JSON
  ├─ teach_knowledge/teacher_answer: dsh 流式生成(on_chunk) → node.token 逐段事件
  └─ 全程事件流: node.started/heartbeat/node.token/node.completed → WebSocket → 前端
```

**"真实正在做的事"**：SDK `on_notification` 流式回调 → 桥 v0.3.3 stdio 逐 chunk → 引擎 `generate_stream` → workflow `emit node.token`（40字符合并）→ 前端 `tokenTexts[phase]` 真实追加。

**实测**：真实 run `fa66c227` completed/finalize/final_len 2703；node.token 113 条（讲授66+答疑47）；51 chunks/7.1s 流式；后端 232 tests 全绿。

## 你现在能立刻做的验证

```bash
# 服务(通常已在跑)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/material-units   # 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/                     # 200

# 自动截图看 UI（我写的工具, 会用 Playwright+本机Chrome）
python scripts/auto_screenshot.py --page=flow      # 进课程设计→选completed会话→生成过程视图
python scripts/auto_screenshot.py --probe          # 输出页面可交互元素

# 后端测试
python -m pytest tests/ -q --ignore=tests/test_langgraph_workflow.py --ignore=tests/test_agent_runtime.py \
  --deselect=tests/test_course_archives.py::test_requested_pdf_extraction_uses_full_document_parser \
  --deselect=tests/test_document_parser.py::test_knowledge_points_filter_code_and_ocr_noise \
  --deselect=tests/test_document_parser.py::test_parse_document_pdf_restores_reading_order_and_removes_repeated_margins \
  --deselect=tests/test_document_parser.py::test_pdf_replaces_hidden_ocr_overlay_and_reports_every_page
# 期望 232 passed(4个需真实OCR引擎的deselect)
```

## 必须知道的坑（都是血泪，别重踩）

1. **Windows + uvicorn `--reload`**: uvicorn 强制 `WindowsSelectorEventLoopPolicy`（不支持 `create_subprocess_exec`）→ 会直接导致 dsh 桥 spawn 失败。**已根治**：`dsh_engine.py` 配**常驻独立 Proactor loop 线程**，桥的 spawn/IO 全在它上面，与主 loop 解耦。**请保留这个设计**，下次改别把它拆了。
2. **SDK 流式回调的坑**：`on_notification` 收到的 `method` **永远是 `session.event`/`session.status`**；真正的事件（`assistant/chunk` 的 `text-delta`、`turn/start`）在 `payload.event`（一个 dict，有 `type`/`data`）。`Notification(method, payload)`。
3. **跨 loop future**：`loop.run_coroutine_threadsafe` 不存在（是 `asyncio.run_coroutine_threadsafe`）；跨 loop 投递用 `main_loop.call_soon_threadsafe(queue.put_nowait, msg)`（线程安全）。
4. **`unknown dsh error`**（DshEngineError 无 error 字段）= 桥进程死了/响应非 JSON；**重启后端可解**，桥本身 probe 正常不代表 uvicorn 内实例正常。
5. **思维链限制**：`deepseek-v4-flash` 的 chunk `blockType: null`（compat 禁了 thinkingFormat）→ **没有 thinking 流**；要思维链得换 `deepseek-v4-pro`。
6. **JSON 提取**：`_extract_json_text` 已加固（剥代码块+取最大括号配平对象）；`agent_iterate` 末轮 round_focus 必须强约束"完整合法 JSON 且不要代码块包裹"。
7. **token 事件节流**：`service.py` 里 `node.token` 按 ≥40 字符合并（防事件表爆炸），`node.completed` 时 flush 残留。
8. **前端 node→phase 映射**：事件 `node` 字段是 phase（`teach_knowledge`），不是前端节点 key（`teach`）——`AgentFlowWorkspace` 里有 `nodePhaseByKey` 映射表。

## 关键文件地图

| 层 | 文件 | 职责 |
|---|---|---|
| 桥 | `scripts/dsh_agent_bridge.py` | stdio JSON-RPC：`probe`/`generate`/`agent_run`(stream:true 转发 chunk)；MODEL_ROUTES 映射模型→provider；translate_error 中文错误 |
| 引擎 | `backend/workflows/dsh_engine.py` | **核心**：常驻独立 Proactor loop + `generate`/`agent_run`/`generate_stream` + `_send`(支持预注册rid) |
| 客户端 | `backend/workflows/llm.py` | `ModelClient.generate(on_chunk)`/`generate_json`/`agent_iterate`/`_extract_json_text` |
| 编排 | `backend/workflows/graph.py` | 7 节点 DAG；content_analysis 用 agent_iterate；teach/answer 用 generate(on_chunk→emit node.token) |
| 服务 | `backend/workflows/service.py` | `_execute` 的 emit 闭包（node.token 40字符合并/flush）+ heartbeat + `_attach_outline_status` |
| 前端 | `frontend/src/components/AgentFlowWorkspace.tsx` | 多智能体协作流程视图（名册/流程图/节点详情+dsh流）|
| 前端工具 | `scripts/auto_screenshot.py` | Playwright 自动截图 |
| 文档 | `docs/`（CHANGELOG.md 有完整历史）| 阅读顺序：`CHANGELOG.md` → `docs/资料单元课程设计数据衔接_2026-08-30.md` → `docs/course-design-agent-team-preview.html`（原型）|
| 记忆 | `~/.claude/projects/D--paper-dsh/memory/` | `tc-dsh-stream-chain` / `tc-dsh-agent-iterate` / `tc-run-progress-window-fix` / `tc-ui-autoscreenshot` |

## 项目结构速览

```
platform-langgraph/
├── backend/
│   ├── workflows/          # dsh引擎+llm+graph+service(核心)
│   ├── material_units/     # 资料单元(教材解析/大纲/教学补充)
│   ├── course_designs/     # 课程设计(引用大纲版本/rebind升级)
│   ├── documents/          # 文档解析/预览
│   └── data/               # 数据目录(gitignore覆盖)
├── frontend/src/components/  # AgentFlowWorkspace等
├── scripts/dsh_agent_bridge.py  # dsh桥
└── docs/                   # CHANGELOG+说明文档
```

## 当前状态（2026-09-02）

- ✅ 前后端在跑（8000/5173, 模型 minimax-m3）；git 工作区干净（`40e6b72`）
- ✅ 流式链路/node.token/自动截图/232测试全绿
- ⚠️ **GitHub 推送未完成**（github.com 直连超时、无代理）；本地 git 备份安全，记忆+docs 已防丢失
- 下一步候选：①修 GitHub 推送 ②思维链（切 deepseek-v4-pro）③UI 微调

---

## 开发背景（为什么会有这个架构）

- **2026-08 初**：平台用 LangGraph 伪多智能体（6 节点各调一次 LLM，无记忆无工具）→ 用户嫌"不是真多智能体"
- **2026-08-30**：改造成 **dsh agent 化 B 方案**——关键节点（内容分析/教学设计）用一个能**自主迭代/多轮记忆**的 dsh agent 会话；讲授/答疑/督导保留 LangGraph（本就该单轮）
- **2026-08-30 晚**：诊断出「看不到生成过程」三个串联 bug（uvicorn reload Selector loop → 桥失败；selectRun 闪失；JSON 提取偶发失败）→ 全部根治
- **2026-09-02**：打通**真实流式**——SDK on_notification → node.token → 前端逐段显示（不再"播放成品"）
