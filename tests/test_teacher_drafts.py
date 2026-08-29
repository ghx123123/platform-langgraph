import asyncio

import pytest

from backend.core.errors import ConflictError
from backend.model_settings.models import RuntimeModelConfig
from backend.workflows.events import EventHub
from backend.workflows.llm import ModelClient
from backend.workflows.models import (
    RunRecord,
    TeacherDraftUpdate,
    TeacherSectionGenerationRequest,
)
from backend.workflows.report import build_teacher_draft_pdf
from backend.workflows.repository import WorkflowRepository
from backend.workflows.service import WorkflowService


def _service(tmp_path):
    async def setup():
        repository = WorkflowRepository(tmp_path / "platform.db")
        await repository.initialize()
        run = RunRecord(
            template_id="teaching_design",
            objective="Python 函数教学",
            provider="mock:deterministic-mock",
            status="completed",
            final_output="# Python 函数教学设计成果\n\n## 学习目标\n\n理解函数定义。",
            teaching_data={
                "document_name": "python.md",
                "knowledge_points": [{"title": "函数定义"}],
                "content_analysis": {"summary": "函数用于封装可复用逻辑。"},
                "teaching_framework": {"learning_objectives": ["理解函数定义"]},
            },
        )
        await repository.create_run(run)
        service = WorkflowService(
            ModelClient(RuntimeModelConfig(provider="mock")),
            repository,
            EventHub(),
            None,
        )
        return service, run

    return asyncio.run(setup())


def test_teacher_draft_starts_from_generated_report_and_versions_saves(tmp_path):
    service, run = _service(tmp_path)

    async def scenario():
        initial = await service.get_teacher_draft(run.id)
        assert initial.version == 0
        assert initial.source == "generated"
        assert "Python 函数教学教学设计成果" in initial.content

        saved = await service.save_teacher_draft(
            run.id,
            TeacherDraftUpdate(
                content=initial.content + "\n\n## 教师补充\n\n增加一个课堂示例。",
                status="reviewed",
                base_version=0,
            ),
        )
        assert saved.version == 1
        assert saved.status == "reviewed"
        assert saved.source == "teacher"

        versions = await service.list_teacher_draft_versions(run.id)
        assert [item.version for item in versions.items] == [1]
        assert versions.items[0].content == saved.content

    asyncio.run(scenario())


def test_teacher_draft_rejects_stale_version(tmp_path):
    service, run = _service(tmp_path)

    async def scenario():
        initial = await service.get_teacher_draft(run.id)
        await service.save_teacher_draft(
            run.id,
            TeacherDraftUpdate(content=initial.content + "\n\n第一次修改。", base_version=0),
        )
        with pytest.raises(ConflictError, match="其他页面更新"):
            await service.save_teacher_draft(
                run.id,
                TeacherDraftUpdate(content=initial.content + "\n\n旧页面修改。", base_version=0),
            )

    asyncio.run(scenario())


def test_teacher_section_generation_is_scoped_and_not_persisted(tmp_path):
    service, run = _service(tmp_path)

    async def scenario():
        generated = await service.generate_teacher_section(
            run.id,
            TeacherSectionGenerationRequest(
                section_title="学习目标",
                current_content="## 学习目标\n\n理解函数定义。",
                instruction="精简表达",
            ),
        )
        assert generated.section_title == "学习目标"
        assert generated.content == "## 学习目标\n\n理解函数定义。"
        assert (await service.list_teacher_draft_versions(run.id)).items == []

    asyncio.run(scenario())


def test_teacher_draft_pdf_renders_edited_markdown(tmp_path):
    _, run = _service(tmp_path)
    markdown = """# 教师审核稿

## 教学目标

- 理解函数定义
- 能编写函数

| 环节 | 时间 |
| --- | --- |
| 示例 | 10 分钟 |

```python
def add(a, b):
    return a + b
```
"""
    pdf = build_teacher_draft_pdf(run, markdown)
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 3000


def test_teacher_draft_pdf_splits_tall_table_rows(tmp_path):
    _, run = _service(tmp_path)
    long_cell = "；".join(f"第{i}项课堂活动与学生产出说明" for i in range(180))
    markdown = f"""# 教师审核稿

## 教学流程

| 环节 | 教师活动 | 学生活动 | 证据 | 时间 |
| --- | --- | --- | --- | --- |
| 深度讲解 | {long_cell} | 记录并讨论 | 学习单 | 40 分钟 |
| 总结 | 回顾重点 | 完成出口票 | 出口票 | 5 分钟 |
"""

    pdf = build_teacher_draft_pdf(run, markdown)

    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 5000
