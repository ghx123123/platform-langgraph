# 多智能体课程教学设计平台

基于 FastAPI、LangChain 和 LangGraph 的课程教学设计工作区。项目从原 `multi_agent_platform` 复制演进，默认入口保留原项目的教学核心语义：教师读取课程文档、剖析重难点、设计教学环节并讲授，分层学生提问，教师答疑，教学督导点评，再根据反馈进入下一轮。

## 教学流程

```text
数据中台（跨学期、跨课程、全局检索与本地目录更新）
  -> 资料单元（原文件、提取正文、章节讲次、主材料）
  -> 课程设计（材料预览、范围确认、多智能体同范围打磨）
  -> 成果中心（教案定稿与教学资料包分别编辑、预览和导出）
```

其中课程设计阶段内部执行：

```text
课程内容剖析
  -> 教学目标与环节设计
  -> 教师讲授
  -> 优秀 / 中等 / 基础学生分层提问
  -> 教师答疑
  -> 督导评价
  -> 下一轮改进或形成教学成果
```

平台使用 LangGraph `StateGraph` 执行和循环上述流程，使用 SQLite 保存运行记录、事件和 checkpoint，并通过 WebSocket 实时推送课堂阶段与智能体产出。原项目的教学目标、测验、互动路径与 PDF 报告源码仍被保留，可继续作为教学会话的扩展能力。

四个教师页面可直接访问：`/hub`、`/materials`、`/design`、`/exports`。课程设计记录把上游数据分为原始文件、提取正文、结构化讲次和生成成果四层引用；每条引用保留资料库 ID、材料/文档 ID、SHA-256、来源路径、正文定位和原页/原文件地址，下游编辑和导出不会切断来源链。

## 当前能力

- 数据中台按学期、课程和章节资料单元统一管理多个课程库；当前目录支持上传文件、上传文件夹、新建子文件夹、移动、重命名、单项/批量删除和非空文件夹递归删除。中台只展示原始文件、原页预览与文件信息。
- 本地单机部署可登记后端可访问的课程文件夹路径，重复扫描时返回新增、变化、未变和移除数量。上传和目录扫描只保存原件与元数据；教师在资料单元明确选择本次备课材料后，平台才按需提取正文。
- 成果中心的“教案定稿”支持编辑课程名称、讲次、知识点、重难点、教学过程和评价等结构化字段；可搜索资料库中的 DOCX 教案模板，选择后按需加载原件并预检可填充字段。兼容模板保持原页版式导出，不兼容模板必须由教师明确改用内置模板，不会静默降级。
- 教案定稿可从同源进度表、教学大纲、已确认知识大纲和已完成多智能体会话中逐项选择内容，预览后指定插入区域和覆盖/前置/追加方式；每次插入生成新版本并保留来源定位。课程思政可单独编排，教学后记由教师独立填写且不会被智能体同步覆盖。
- 每次教案导出均保存设计版本、模板来源、SHA-256、文件大小和时间，可在成果历史中预览原页、重新下载 Word 或删除平台副本；中台成果数量使用真实导出记录统计。
- 教学资料包支持从中台插入内容块、调整顺序、编辑副本、保存版本和打印预览；支持导入 DOCX/PDF/PPTX/Markdown/TXT/中台 JSON，并导出可编辑 DOCX、Markdown 和可回导 JSON。
- 导入完整学期资料文件夹，形成课程、章节、讲次、资料类型、版本与重复文件的全局视图；教师可按章节筛选并多选教材、课件、教案、进度表和历史迭代记录，指定主材料后组装当前讲次备课包。
- 从真实资料证据中凝练可复用备课习惯，展示证据置信度并提供一键复制；备课包会把所选资料、进度表讲次和历史经验作为辅助上下文带入现有材料预览与教学设计流程。
- 在 PDF、DOCX、PPTX 原页预览中按页执行可选视觉复核：使用当前 OpenAI 兼容视觉模型补充二维码、图表、公式、流程和版式关系；提供三档动态分辨率、实时耗时、结构化证据、复制、历史回显与失败回退。视觉证据只作为备课补充，不覆盖本地 OCR 原文。
- 上传并结构化解析 PDF、DOCX、PPTX、Markdown 和 TXT 课程材料，单文件最大 30 MB；扫描 PDF、整页图片叠加隐藏 OCR 层的教材和 Office 嵌入图片优先使用 RapidOCR v6，加载失败时自动回退 CnOCR，DOCX 同时使用 `python-docx + MarkItDown` 恢复标题、表格和阅读顺序。
- 显示材料解析质量、章节目录、全文覆盖率和逐区分析证据；PDF 逐页记录字符数、OCR 置信度和来源类型，内容分区带原始页码。支持原页/提取文本切换、目录定位、搜索与复制，点击分区可定位原页。PDF 直接显示原稿，DOCX/PPTX 首次预览转换为缓存 PDF。
- 自动提取候选知识点，由教师智能体识别重点、难点、先备知识和常见误区。
- 由教师多选知识范围，设置 10–180 分钟课时、概览/标准/深入三档深度和 1–3 轮迭代。
- 生成学习目标、教学环节、教学策略与形成性评价方案。
- 执行 1 至 3 轮教学设计打磨、教师讲授、分层学生提问、教师答疑和督导点评；各轮固定围绕同一知识范围优化。
- 保存完整课堂消息、督导维度评分、迭代建议和最终教学设计成果。
- 提供“材料预览、生成过程、教学成果”三个教师工作页；生成过程显示步骤、耗时、心跳、Token 和输出速度。
- 教学成果支持按资料块预览、编辑、局部生成、自动恢复、保存版本、教师审核和历史恢复。
- 导出教师版或学生版 Markdown/PDF，教师版优先使用最近保存或审核稿。
- 首屏引导 + 内置示例课程，新用户可一键体验完整教学流程。
- 启动前可编辑 AI 抽取的候选知识点：设重点、改标题、增删。
- 会话列表展示综合评分与轮次；运行中实时显示当前轮次与已运行时长。
- “课程与会话”由页面左侧图标独立控制，切换会话不会自动收起侧栏。
- 提供模型设置界面，可切换本地演示模型或任意 OpenAI 兼容接口。
- API Key 只写入后端本地配置，读取接口仅返回 `has_api_key`，不会返回密钥值。

## 学期资料库备课流程

1. 点击左侧“导入一学期资料文件夹”，选择一个课程或一学期的备课目录。
2. 等待系统建立完整文件清单并抽取代表性正文。建库阶段优先保证全局覆盖：PDF 使用 PyMuPDF 原生文本，DOCX 使用 `python-docx` 读取段落与表格，不对整本资料执行图片 OCR。
3. 在“学期资料”页选择章节和讲次，筛选并勾选本次需要共同分析的材料，用圆点指定主材料。
4. 检查右侧历史备课习惯及证据，必要时复制经验提示词，再点击“创建并进入材料预览”。
5. 在材料预览中检查原页、提取文本、内容目录和知识点范围。扫描 PDF、Office 嵌入图片或低质量材料需要完整识别时，继续使用单文档上传链路执行 RapidOCR/CnOCR，而不是依赖快速建库结果。
6. 明确教学范围、课时和深度后启动教学设计；后续多轮始终打磨同一知识范围。

首次导入大型学期资料夹需要遍历、分类、去重和抽取代表性正文。实测 1,659 份资料约需 80–93 秒；完成建库后，按章节组装备课包通常低于 1 秒。

## 本地启动

要求 Python 3.11+、Node.js 20+。

```powershell
cd D:\paper\cc\projects\multi_agent_platform_langgraph
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
npm --prefix frontend install
```

分别启动：

```powershell
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

- 教学工作区：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

也可运行根目录的 `run.bat`。默认使用可完整执行教学流程的本地演示模型；进入网页后点击右上角齿轮，即可填写自定义兼容接口、模型名和 API Key，并在保存前测试连接。

## 核心接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/documents/parse` | 解析课程文档与候选知识点 |
| GET | `/api/documents/{id}/preview` | 获取原页预览 PDF；Office 文件按需转换并缓存 |
| GET | `/api/documents/{id}/original` | 获取上传的原始课程材料 |
| POST | `/api/course-archives/analyze` | 导入并分析学期资料文件夹 |
| GET | `/api/course-archives` | 查询已保存的学期资料库 |
| GET/DELETE | `/api/course-archives/{id}` | 读取或删除资料库 |
| POST | `/api/course-archives/{id}/prepare` | 按章节与所选材料组装备课包 |
| GET | `/api/data-hub/catalog` | 跨学期、课程、单元和内容类型全局检索 |
| GET | `/api/data-hub/blocks/{id}` | 读取统一内容块完整正文与来源定位 |
| PUT | `/api/data-hub/archives/{id}/metadata` | 更新课程学期、名称和课程代码 |
| POST | `/api/data-hub/local-sources/scan` | 新建或增量更新本地课程目录 |
| GET/POST | `/api/data-hub/compositions` | 查询或创建成果编排 |
| POST | `/api/data-hub/compositions/import` | 导入文件并转换为可编辑成果 |
| GET | `/api/data-hub/compositions/{id}/preview` | 获取成果打印预览页 |
| GET | `/api/data-hub/compositions/{id}/export` | 导出 DOCX、Markdown 或中台 JSON |
| GET/POST | `/api/course-designs` | 查询或创建带来源链的课程设计稿 |
| GET/PUT/DELETE | `/api/course-designs/{id}` | 读取、保存版本或删除课程设计稿 |
| GET | `/api/course-designs/{id}/versions` | 查询课程设计版本快照 |
| GET | `/api/course-designs/{id}/references/{reference_id}` | 读取某条原始/提取/结构化/生成引用 |
| POST | `/api/course-designs/{id}/sync-run/{run_id}` | 将多智能体成果同步到可编辑设计字段 |
| POST | `/api/course-designs/{id}/template-inspection` | 预检 DOCX 模板字段和原格式兼容性 |
| POST | `/api/course-designs/{id}/export.docx` | 按资料库模板、上传模板或内置模板导出 DOCX |
| GET | `/api/course-designs/{id}/exports` | 查询课程设计的导出成果历史 |
| DELETE | `/api/course-designs/{id}/exports/{export_id}` | 删除平台保存的单个导出成果 |
| POST | `/api/workflows/runs` | 创建教学设计会话 |
| GET | `/api/workflows/runs` | 查询教学会话历史 |
| GET | `/api/workflows/runs/{id}` | 查询教学状态与成果 |
| GET | `/api/workflows/runs/{id}/events` | 获取持久化课堂事件 |
| WS | `/api/workflows/runs/{id}/events/ws` | 实时事件与历史回放 |
| GET/PUT | `/api/workflows/runs/{id}/teacher-draft` | 读取或保存教师稿 |
| GET | `/api/workflows/runs/{id}/teacher-draft/versions` | 查询教师稿版本历史 |
| POST | `/api/workflows/runs/{id}/teacher-draft/generations` | 重新生成当前资料块 |
| GET | `/api/workflows/runs/{id}/report.md` | 导出教师版或学生版 Markdown |
| GET | `/api/workflows/runs/{id}/report.pdf` | 导出教师版或学生版 PDF |
| GET | `/api/settings/model` | 获取脱敏后的模型设置 |
| PUT | `/api/settings/model` | 保存并热切换模型 |
| POST | `/api/settings/model/test` | 测试候选模型连接 |

## 验证

```powershell
python -m pytest tests -q
npm --prefix frontend run build
node frontend\scripts\visual-check.mjs
```

浏览器验证截图位于 `frontend/screenshots/teaching-desktop.png`、`teaching-mobile.png` 和 `model-settings.png`。
