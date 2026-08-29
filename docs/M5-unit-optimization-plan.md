# M5 资料单元优化计划：导入解析预览 + MinerU + 痛点修复

**日期**: 2026-08-26
**目标**: 让资料单元(材料/文档) 导入后 = 原文预览(正确识别)+ 解析状态可视化 + MinerU 可选 + 缓存免重解析；并修复痛点 1(导入慢) 2(无材料细化) 3(NameError)。

**结论**:
- **MinerU 不重装**：已存在 `D:/software/anaconda/envs/mineru/Scripts/mineru.exe`（magic-pdf 1.3.12 CLI）; dsh-graph 已封装调用(host.js:524-547 `MINERU_BIN`/local-mineru 引擎)，输出 `.mineru.md` 直接可复用。
- **原文预览已有** preview_url/original_url(预解析页) 但**无解析后原文提取结果的预览**。
- **痛点1慢的根因**：导入默认全量解析(extract_uploads=True)。
- **痛点2缺**：`_model_refined_nodes`(material_units/router.py:464) 依赖 selected_anchors，纯 teacher_instruction 无材料时不可用。
- **痛点3确诊**：`material_units/router.py` 缺 `import re`（第1-31行无import re，492行用`re.search`→NameError）。

---

## 一、具体改动设计（不重改平台大结构）

### A. 解析引擎层（documents/service.py）
1. **加 `_mineru_engine()`**：调用 `mineru.exe` CLI（`mineru -p <input.pdf> -o <outdir>`）产出 Markdown，读取为文本。**同 rapidocr/cnocr 模式**（documents/service.py:335-363 的 provider 选择函数，加第三分支）。
2. **解析时引擎可配**：`parse_document` 调用选择引擎（env `TC_DOC_PARSER` 或配置传入：rapidocr / cnocr / mineru）。
3. **状态保留**：解析成功 → `parse_status="parsed"` + raw_text 存 document；失败 → `parse_failed` + 原因。
4. **缓存**：保持现有 sha256/document_id 复用逻辑(service.py:731)，不改。

### B. 导入慢修复（痛点1）
1. **course_archives `analyze` 接口默认 `extract_uploads` 可变**：默认 False（轻量导入，只登记元数据/原文件快速保存）。全量解析仅当 `extract_uploads=True`（或单独"提取正文"按钮）时才跑。
2. **新增 `POST /api/course-archives/{id}/extract`**（已有）：`ExtractArchiveRequest` 里增加 `engine` 字段,让提取时选 rapidocr/mineru。
3. **前端**："导入文件/文件夹" 保持轻量（秒级）；资料列表/文件信息"提取正文"（触发全量分析+原文预览）。

### C. 痛点2 无材料细化（前端+后端）
1. `_model_refined_nodes`（router.py:464）加分支：
   - 若 `material_ids` 为空且 `teacher_instruction` 非空 → 直接基于 instruction + 当前 outline 让 LLM 生成 `model_nodes`（`evidence_source="teacher_instruction"`，无 section 依据，但可作为 user 自添节点）。
2. **前端** KnowledgeOutlineRefine 对话框：当（无材料选择）时显示"可基于教师补充说明扩展"提示；instruction 输入框必填。

### D. 痛点3 NameError
- `material_units/router.py` imports 加 `import re`（第1行）。
- **防御**：`_model_refined_nodes` 里 `re.search(...)` 前 try/except 已处理（若不需 fallback 直接加 import 即可）。
- **验证**：重启后端,刷新页面打开某课程→资料单元→知识大纲→发起细化(无材料, 仅instruction)→ 不再 "name 're' is not defined"。

### E. 前端预览增强（原文预览 + 状态）
1. **文件信息 tab**（DataHubWorkspace 978-979 行）：把 `dl` 里的"正文提取：未在数据中台执行"改为显示真实状态：
   - parse_status `parsed`→"已提取（MinerU/OCR）" + 原文预览按钮
   - `metadata_only`→"未提取，可按需提取" + "提取正文"按钮
   - `parse_failed`→"提取失败：原因"
   - `unsupported`→"格式不支持提取"
2. **新增"提取正文"按钮**(在 dl 里)：触发 analyze(extract_uploads=true, engine 可选)。
3. **原文(解析后文本)预览**：新增端点 `GET /api/documents/{document_id}/text`（返回 html 化 raw_text 或直接纯文本），前端 iframe/新窗口看解析结果正文（替代只预览原页）。

---

## 二、实施顺序（每个完成后验证/审核）

| 步骤 | 改动 | 验证方式 | 风险 |
|---|---|---|---|
| S1 | `material_units/router.py` 加 `import re`（痛点3，最小） | 重启后端 → 前端发起细化(有/无材料) → 不再 NameError | 低 |
| S2 | 痛点2：`_model_refined_nodes` 无材料分支 | 重启 → 不选材料, 只填 instruction → 细化能生成节点 | 中 |
| S3 | 痛点1：`analyze` 默认 extract_uploads=False; 新增 engine 参数 | 重启 → 导入大 PDF → <3 秒;导入后"提取正文"按钮触发全量解析 | 中 |
| S4 | 文档引擎加 MinerU provider（documents/service.py）+ engine 配置 | 重启 → 提取正文时选 mineru → 输出 md 并 raw_text 保存 | 中(依赖 mineru CLI) |
| S5 | 前端：文件信息状态渲染 + 提取正文按钮 + 原文预览 | vite dev → 浏览器验证各状态正确渲染 | 中 |
| S6 | 全链路审核 | 完整走一遍：导入→轻量→提取(选用引擎)→预览→细化→生成教案 | 需审核通过 |

---

## 三、接口/路由改动清单

| 路由 | 改动 |
|---|---|
| `POST /api/course-archives/analyze` | 加 `engine` 字段（默认 rapidocr）；extract_uploads 默认 false |
| `POST /api/course-archives/{id}/extract`（已有）| 加 engine 字段 |
| `GET /api/documents/{doc_id}/text`（新增）| 返回解析后原文文本 |
| `GET /api/documents/{doc_id}/original`（已有）| 原页下载，不动 |
| 前端 DataHubWorkspace.tsx | 文件信息 dl 渲染状态 + 提取正文按钮 + 原文预览打开 |

---

## 四、测试要点

1. **MinerU 单元测试**：`mineru.exe` 处理一份扫描 PDF（dsh-graph 已有样本 `p_*.pdf`）→ `.mineru.md` 输出可读。
2. **无材料细化回归**：`material_units/router.py` 无材料+instruction → 无 NameError → 节点生成。
3. **导入快速性计时**：导入 200 页 PDF（extract_uploads=false）→ < 5s；提取正文（true）→ 完成且状态 parsed。
4. **缓存**：同一文件重复导入 → 复用 document_id + 不重复解析。
5. **前端状态渲染**：vite dev 刷新，各种 parse_status 正确显示。
6. **审核**：改完的 diff + 重启后端测试，确认无回归。

---

## 五、已知限制（诚实声明）

- MinerU 需要 GPU/CPU 时间，**提取正文走它**明显比 rapidocr 慢（dsh-graph 里"mineru 深解析"是"按需"，不是"默认"）。
- MinerU 模型路径、并发：仅单文件顺序解析。
- 保留现有 rapidocr/cnocr 作为默认（内存占用小、速度可接受），MinerU 作为**可选**（版面识别更准）。默认配置仍是 rapidocr——避免默认就变慢。
