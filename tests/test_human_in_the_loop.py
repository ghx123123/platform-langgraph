import asyncio

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.model_settings.models import RuntimeModelConfig
from backend.workflows.events import EventHub
from backend.workflows.llm import ModelClient
from backend.workflows.models import (
    ContinueRequest,
    CreateRunRequest,
    InterventionPoint,
    ResumeRequest,
)
from backend.workflows.repository import WorkflowRepository
from backend.workflows.service import WorkflowService

DOCUMENT = (
    "# 牛顿运动定律\n"
    "## 第一章 牛顿第一定律\n物体不受外力时保持静止或匀速直线运动。\n"
    "## 第二章 牛顿第二定律\n加速度与合外力成正比，与质量成反比。\n"
)


class Harness:
    """封装建会话与轮询，避免每个用例重复写等待逻辑。"""

    def __init__(self, service: WorkflowService) -> None:
        self.service = service
        self.run_id = ""

    async def create(self, **interventions: bool):
        run = await self.service.create_run(
            CreateRunRequest(
                title="牛顿运动定律",
                document_name="newton.md",
                document_text=DOCUMENT,
                max_iterations=1,
                interventions=InterventionPoint(**interventions),
            )
        )
        self.run_id = run.id
        return run

    async def wait(self, status: str, attempts: int = 600):
        for _ in range(attempts):
            stored = await self.service.get_run(self.run_id)
            if stored.status == status:
                return stored
            if stored.status == "failed":
                raise AssertionError(f"run failed: {stored.error}")
            await asyncio.sleep(0.01)
        raise AssertionError(f"timeout waiting for {status}")


def run_with_service(tmp_path, scenario):
    async def main():
        repository = WorkflowRepository(tmp_path / "platform.db")
        await repository.initialize()
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.db")) as checkpointer:
            await checkpointer.setup()
            service = WorkflowService(
                ModelClient(RuntimeModelConfig(provider="mock")), repository, EventHub(), checkpointer
            )
            try:
                return await scenario(Harness(service))
            finally:
                await service.shutdown()

    return asyncio.run(main())


def test_run_without_interventions_never_pauses(tmp_path):
    """未勾选断点时保持全自动，行为与改造前一致。"""

    async def scenario(harness: Harness):
        await harness.create()
        stored = await harness.wait("completed")
        return stored

    stored = run_with_service(tmp_path, scenario)
    assert stored.pending_input is None
    assert stored.teaching_data["current_iteration"] == 1


def test_design_breakpoint_applies_user_revision(tmp_path):
    """设计断点：用户意见入档，教师产出修订版方案。"""

    async def scenario(harness: Harness):
        await harness.create(after_design=True)
        paused = await harness.wait("paused")
        assert paused.pending_input["kind"] == "design_review"
        assert paused.pending_input["context"]["stages"]
        await harness.service.resume_run(
            harness.run_id, ResumeRequest(action="revise", content="难点环节延长到 15 分钟")
        )
        return await harness.wait("completed")

    stored = run_with_service(tmp_path, scenario)
    design = [m for m in stored.teaching_data["messages"] if m["phase"] == "design"]
    assert any(m["agent_id"] == "user" and "15 分钟" in m["content"] for m in design)
    assert any("已根据你的意见调整教学方案" in m["content"] for m in design)


@pytest.mark.parametrize(
    ("action", "content", "expected_author"),
    [
        ("user", "惯性是物体属性，不是力。", "教研员（你）"),
        ("outline", "强调合外力是矢量和", "课程教师"),
        ("agent", "", "课程教师"),
    ],
)
def test_answer_breakpoint_supports_three_modes(tmp_path, action, content, expected_author):
    async def scenario(harness: Harness):
        await harness.create(after_question=True)
        paused = await harness.wait("paused")
        assert paused.pending_input["kind"] == "answer_choice"
        assert len(paused.pending_input["context"]["questions"]) == 3
        await harness.service.resume_run(harness.run_id, ResumeRequest(action=action, content=content))
        return await harness.wait("completed")

    stored = run_with_service(tmp_path, scenario)
    answers = [m for m in stored.teaching_data["messages"] if m["phase"] == "teacher_answer"]
    assert answers[-1]["agent_name"] == expected_author
    if action == "user":
        assert answers[-1]["content"] == content
    if action == "outline":
        # 要点单独入档，答疑正文仍由教师产出
        assert any(m["agent_id"] == "user" and content in m["content"] for m in answers)


def test_continue_run_refines_design_before_reteaching(tmp_path):
    """追加轮次要先打磨同一教学设计，再进入新的讲授闭环。"""

    async def scenario(harness: Harness):
        await harness.create()
        first = await harness.wait("completed")
        await harness.service.continue_run(harness.run_id, ContinueRequest(additional_iterations=1))
        second = await harness.wait("completed")
        return first, second

    first, second = run_with_service(tmp_path, scenario)
    assert first.teaching_data["current_iteration"] == 1
    assert second.teaching_data["current_iteration"] == 2
    iterations = {m["iteration"] for m in second.teaching_data["messages"]}
    assert {0, 1, 2} <= iterations
    # 追加轮次会多出一条设计打磨消息，而不是直接顺延讲新内容。
    designs = [m for m in second.teaching_data["messages"] if m["phase"] == "design"]
    first_designs = [m for m in first.teaching_data["messages"] if m["phase"] == "design"]
    assert len(designs) == len(first_designs) + 1
    assert designs[-1]["iteration"] == 2
    assert "可复用优化提示词" in designs[-1]["content"]


def test_continue_run_rejects_unfinished_session(tmp_path):
    async def scenario(harness: Harness):
        await harness.create(after_design=True)
        await harness.wait("paused")
        with pytest.raises(Exception) as error:
            await harness.service.continue_run(harness.run_id, ContinueRequest())
        return str(error.value)

    message = run_with_service(tmp_path, scenario)
    assert "paused" in message
