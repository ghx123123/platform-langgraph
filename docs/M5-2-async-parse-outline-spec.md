# M5-2 资料单元：后台异步解析 + 知识大纲双模式 实施规格

**日期**: 2026-08-26
**范围**: 仅 material_units 路径；并行2(内存安全)；知识大纲"直列(现有)+整合(LLM概括,支持无材料提示词优化)"。

---

## Part 1: 后台异步解析引擎 (仅 material_units 路径)

### 1.1 新状态模型 (materials/单元文档)
在 `material_units` 引入 **parse_task** 概念(复用 refine-task 模式, 不改 course_archives):
- 新文件 `backend/material_units/parse_tasks.py`:
  - `_running_tasks: dict[str, set]` + `_parse_pool: ThreadPoolExecutor(max_workers=2)` (模块级)
  - `start_parse_task(unit_id, material_ids, engine)` → 立即返回 task_id; 后台拆开逐材料:
    - 每材料: `material.parse_status="parsing"`, 更新到 archive 内存态并定期 save; 进度 progress 0→100 (按页, 由 parse 回调粗略)
    - 调 `_parse_uploaded(..., full_extraction=True, engine=...)` (engine 传给 documents.service.parse_document)
    - 成功: parse_status=parsed, progress=100, parse_message 含 engine 名; 失败: parse_failed + 原因
- 进度**持久化**: 每周 save_archive 一次 (材料 parse_status/parse_message 在 archive JSON), 前端轮询 `GET /material-units/{unit_id}/parse-tasks/{task_id}` 读内存态+archive 字段。

### 1.2 端点 (material_units/router.py)
- `POST /{unit_id}/parse-tasks` {material_ids, engine?} → {task_id} (立即返回)
- `GET /material-units/{unit_id}/parse-tasks/{task_id}` → {status, progress, materials:[{id, name, parse_status, progress, message}]}
- 引擎: engine 参数支持 "rapidocr"(默认)/"mineru"; 内部透传 `documents.service.parse_document(engine=...)`。

### 1.3 前端"导入资料单元"
- 导入后若 `extract_immediately=False` (快速登记) → **自动发起 parse-task**(后台) → UI 显示"解析中 x%" 轮询进度条; 完成后状态更新。
- 也可以在导入对话框加"立即解析"默认勾选(快速登记+后台解析并行)。

## Part 2: 知识大纲双模式

### 2.1 直列模式 (现有不变)
- `build_initial_outline`/`create_knowledge_outline` 保持映射直列(教材目录/大纲要求→nodes)。

### 2.2 整合模式 (LLM 概括, 新增)
- 新端点 `POST /material-units/{unit_id}/knowledge-outlines/synthesize`:
  - 输入: {title?, teaching_item_ids, syllabus_item_ids, outline_node_ids, teacher_instruction?, mode="synthesize"}
  - 模式 A (有材料): 读取所选材料正文摘要 → LLM 整合为 **连贯大纲**(level 1-3 层级 + is_key_point/is_difficult_point 标记 + 描述)
  - 模式 B (仅 teacher_instruction): 无材料 → LLM **基于提示词**生成整合大纲(不指定文件)
- LLM 输出 → 验证 KnowledgeOutline schema → 保存 (version 递增, 标记 "synthesized")
- 整合 prompt: 明确"大纲应结构化、合并重复、层级连贯、标注重点难点; 不擅自新增未出现概念(除非 teacher_instruction 明确)".

### 2.3 优化 (无材料提示词, 已有 S2 基础)
- refine 的 free_instruction_mode (S2) 保留: 无材料 + teacher_instruction → 在**现有大纲**上优化(update/add)。
- 整合模式优化: 在 synthesize 后, 用户输入优化提示词 → 同样走 free 模式 refine (对整合结果做优化)。

## Part 3: 最终实现优先序

| # | 内容 | 交付物 |
|---|---|---|
| P1 | parse_tasks 模块 + 端点(后台并发2 + 进度轮询) | 后台解析可跑, 进度可见 |
| P2 | 前端: 导入单元自动后台解析 + 进度条 | 体验: 导入=快速登记+后台解析进度 |
| P3 | 大纲整合模式: synthesize 端点(有/无材料两模式) | 直列/整合切换 |
| P4 | 整合模式前端(按钮) + 优化提示词 | 用户体验完整 |
| P5 | 全链路审核 | 导入→解析(进度)→大纲(直列/整合)→优化→备课 |

---

## 测试/审核
- P1: 并发 2 文件解析, 轮询进度走完; 重复导入复用缓存
- P2: UI 显示"解析中 x%"→"已提取(engine)"
- P3: 同材料 直列 vs 整合输出对比; 无材料+提示词生成
- P4: 优化提示词对整合大纲生效
- P5: 回归: 原 refine/大纲/备课 不破坏
