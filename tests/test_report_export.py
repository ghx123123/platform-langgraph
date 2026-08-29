import asyncio

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.model_settings.models import RuntimeModelConfig
from backend.workflows.events import EventHub
from backend.workflows.llm import ModelClient
from backend.workflows.models import CreateRunRequest
from backend.workflows.report import build_markdown, build_pdf, report_filename
from backend.workflows.repository import WorkflowRepository
from backend.workflows.service import WorkflowService


DOCUMENT = (
    "# 牛顿运动定律\n"
    "## 第一章 牛顿第一定律\n一切物体在没有受到外力作用时保持静止或匀速直线运动。\n"
    "## 第二章 牛顿第二定律\n加速度跟合外力成正比，跟质量成反比。\n"
)


def _completed_run(tmp_path):
    async def run_test():
        repository = WorkflowRepository(tmp_path / "platform.db")
        await repository.initialize()
        model = ModelClient(RuntimeModelConfig(provider="mock"))
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.db")) as checkpointer:
            await checkpointer.setup()
            service = WorkflowService(model, repository, EventHub(), checkpointer)
            run = await service.create_run(
                CreateRunRequest(
                    title="牛顿运动定律",
                    document_name="牛顿运动定律.md",
                    document_text=DOCUMENT,
                    max_iterations=1,
                    context="高一年级，突破作用力与反作用力难点",
                )
            )
            for _ in range(500):
                stored = await service.get_run(run.id)
                if stored.status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.01)
            await service.shutdown()
        return stored

    return asyncio.run(run_test())


def test_markdown_report_contains_all_sections(tmp_path):
    run = _completed_run(tmp_path)
    markdown = build_markdown(run)
    for section in ("教学设计成果", "一、课程内容剖析", "二、教学方案", "三、督导评价", "四、课堂全过程记录"):
        assert section in markdown
    # 补充教学要求应被带入报告
    assert "作用力与反作用力" in markdown
    # 课堂记录应包含三类学生
    for label in ("拓展型", "进阶型", "基础型"):
        assert label in markdown


def test_pdf_report_is_valid_and_non_trivial(tmp_path):
    run = _completed_run(tmp_path)
    pdf = build_pdf(run)
    assert pdf.startswith(b"%PDF-"), "应生成合法 PDF"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 5000, "报告不应是空壳"


def test_report_filename_sanitises_illegal_characters(tmp_path):
    run = _completed_run(tmp_path)
    run.objective = 'a/b:c*d?e"f<g>h|i'
    name = report_filename(run, "pdf")
    assert not set(name) & set('\\/:*?"<>|')
    assert name.endswith(".pdf")


def test_students_question_order_is_stable_under_concurrency(tmp_path):
    """三类学生改为并发调用后，消息顺序仍须为 拓展→进阶→基础。"""
    run = _completed_run(tmp_path)
    questions = [m for m in run.teaching_data["messages"] if m["phase"] == "student_question"]
    assert [m["level"] for m in questions] == ["high", "medium", "low"]
    assert [m["agent_name"] for m in questions] == ["拓展型学生", "进阶型学生", "基础型学生"]

def test_markdown_report_includes_exercises_with_answers(tmp_path):
    run = _completed_run(tmp_path)
    markdown = build_markdown(run)
    assert "### 课堂练习" in markdown
    for label in ("【基础】", "【进阶】", "【拓展】"):
        assert label in markdown
    assert "答案：" in markdown
    exercises = run.teaching_data["teaching_framework"].get("exercises") or []
    assert len(exercises) == 3
    assert {e["level"] for e in exercises} == {"low", "medium", "high"}


def test_student_markdown_omits_answers_and_teacher_sections(tmp_path):
    run = _completed_run(tmp_path)
    student = build_markdown(run, student=True)
    assert "### 课堂练习" in student
    assert "答案：" not in student
    assert "三、督导评价" not in student
    assert "四、课堂全过程记录" not in student


def test_student_pdf_is_valid_and_non_trivial(tmp_path):
    run = _completed_run(tmp_path)
    pdf = build_pdf(run, student=True)
    assert pdf.startswith(b"%PDF-"), "学生版应生成合法 PDF"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 3000


def test_report_filename_student_suffix(tmp_path):
    run = _completed_run(tmp_path)
    name = report_filename(run, "pdf", student=True)
    assert "学生版" in name
    assert name.endswith(".pdf")
