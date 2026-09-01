import asyncio
from typing import Awaitable, Callable

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.model_settings.models import RuntimeModelConfig
from backend.workflows.events import EventHub
from backend.workflows.llm import ModelClient
from backend.workflows.models import CreateRunRequest, KnowledgePoint
from backend.workflows.repository import WorkflowRepository
from backend.workflows.service import WorkflowService
import backend.workflows.service as workflow_service_module


def test_teaching_graph_preserves_phase_order_and_iterations(tmp_path):
    async def run_test():
        database = tmp_path / "platform.db"
        checkpoint = tmp_path / "checkpoints.db"
        repository = WorkflowRepository(database)
        await repository.initialize()
        model = ModelClient(RuntimeModelConfig(provider="mock"))

        async with AsyncSqliteSaver.from_conn_string(str(checkpoint)) as checkpointer:
            await checkpointer.setup()
            service = WorkflowService(model, repository, EventHub(), checkpointer)
            run = await service.create_run(
                CreateRunRequest(
                    title="数据结构课程设计",
                    archive_id="11111111-1111-4111-8111-111111111111",
                    design_id="22222222-2222-4222-8222-222222222222",
                    document_name="数据结构.md",
                    document_text="# 数据结构\n## 重点\n线性表的抽象结构\n## 难点\n算法复杂度分析",
                    knowledge_points=[KnowledgePoint(title="线性表", is_key_point=True)],
                    max_iterations=2,
                )
            )
            for _ in range(300):
                stored = await service.get_run(run.id)
                if stored.status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.01)
            events = await repository.list_events(run.id)
            await service.shutdown()
        return stored, events

    stored, events = asyncio.run(run_test())
    started = [event.node for event in events if event.event_type == "node.started"]
    assert started == [
        "content_analysis", "teaching_design",
        "teach_knowledge", "student_question", "teacher_answer", "supervisor_comment",
        "teaching_design",
        "teach_knowledge", "student_question", "teacher_answer", "supervisor_comment",
        "finalize",
    ]
    assert stored.status == "completed"
    assert stored.teaching_data["archive_id"] == "11111111-1111-4111-8111-111111111111"
    assert stored.teaching_data["design_id"] == "22222222-2222-4222-8222-222222222222"
    assert stored.teaching_data["current_iteration"] == 2
    assert len(stored.teaching_data["messages"]) == 15
    assert {message["agent_type"] for message in stored.teaching_data["messages"]} == {"teacher", "student", "supervisor"}
    assert stored.review["score"] == 86
    refinement = [message for message in stored.teaching_data["messages"] if message["phase"] == "design" and message["iteration"] == 2]
    assert refinement and "可复用优化提示词" in refinement[0]["content"]
    assert "教师讲授 - 学生提问 - 教师答疑 - 督导点评" in stored.final_output
    completed = [event for event in events if event.event_type in {"node.completed", "review.completed"}]
    assert completed
    assert all(event.payload["duration_ms"] >= 1 for event in completed)
    assert all(event.payload["total_steps"] == 12 for event in completed)
    model_steps = [event.payload["model_metrics"] for event in completed if event.payload["model_metrics"]["request_count"]]
    assert model_steps
    assert all(metrics["total_tokens"] > 0 for metrics in model_steps)
    assert any(metrics["request_count"] == 3 for metrics in model_steps)


def test_running_workflow_emits_observable_heartbeat(tmp_path, monkeypatch):
    class DelayedModelClient(ModelClient):
        async def generate(self, system_prompt: str, user_prompt: str, on_chunk: Callable[[str], Awaitable[None]] | None = None) -> str:
            await asyncio.sleep(0.03)
            return await super().generate(system_prompt, user_prompt)

    async def run_test():
        repository = WorkflowRepository(tmp_path / "heartbeat.db")
        await repository.initialize()
        model = DelayedModelClient(RuntimeModelConfig(provider="mock"))
        monkeypatch.setattr(workflow_service_module, "WORKFLOW_HEARTBEAT_SECONDS", 0.01)

        async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "heartbeat-cp.db")) as checkpointer:
            await checkpointer.setup()
            service = WorkflowService(model, repository, EventHub(), checkpointer)
            run = await service.create_run(
                CreateRunRequest(
                    title="热力学第一定律",
                    document_name="thermodynamics.md",
                    document_text="# 热力学第一定律\n## 能量守恒\n系统吸收的热量用于增加内能和对外做功。",
                    max_iterations=1,
                )
            )
            for _ in range(500):
                stored = await service.get_run(run.id)
                if stored.status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.01)
            events = await repository.list_events(run.id)
            await service.shutdown()
        return stored, events

    stored, events = asyncio.run(run_test())
    heartbeats = [event for event in events if event.event_type == "run.heartbeat"]

    assert stored.status == "completed"
    assert heartbeats
    assert all(event.node for event in heartbeats)
    assert all(event.payload["elapsed_ms"] >= 1 for event in heartbeats)
    assert all(event.payload["step_index"] >= 1 for event in heartbeats)
    assert all(event.payload["total_steps"] == 7 for event in heartbeats)


BIOLOGY_DOCUMENT = (
    "# 光合作用与细胞呼吸\n"
    "## 第一章 光合作用的光反应\n光反应发生在类囊体薄膜上，水在光照下裂解产生氧气。\n"
    "## 第二章 卡尔文循环\n暗反应在叶绿体基质中进行，RuBP 羧化酶是关键限速酶。\n"
    "## 第三章 细胞呼吸的三个阶段\n糖酵解在细胞质基质中，三羧酸循环在线粒体基质。\n"
)
EMBEDDED_DOCUMENT = (
    "# 嵌入式系统设计\n"
    "## 第一章 中断处理机制\n中断向量表存放在内存低端，中断服务程序需要保护现场。\n"
    "## 第二章 实时操作系统调度\n优先级抢占调度依赖任务控制块，信号量用于任务间同步。\n"
)


def _run_session(tmp_path, name, title, document, max_iterations):
    async def run_test():
        repository = WorkflowRepository(tmp_path / f"{name}.db")
        await repository.initialize()
        model = ModelClient(RuntimeModelConfig(provider="mock"))
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path / f"{name}-cp.db")) as checkpointer:
            await checkpointer.setup()
            service = WorkflowService(model, repository, EventHub(), checkpointer)
            run = await service.create_run(
                CreateRunRequest(
                    title=title,
                    document_name=f"{name}.md",
                    document_text=document,
                    max_iterations=max_iterations,
                )
            )
            for _ in range(500):
                stored = await service.get_run(run.id)
                if stored.status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.01)
            events = await repository.list_events(run.id)
            await service.shutdown()
        return stored, events

    return asyncio.run(run_test())


def test_mock_output_is_derived_from_uploaded_document(tmp_path):
    """演示模型的产出必须来自上传材料，不同学科不能雷同。"""
    bio, _ = _run_session(tmp_path, "bio", "光合作用与细胞呼吸", BIOLOGY_DOCUMENT, 1)
    emb, _ = _run_session(tmp_path, "emb", "嵌入式系统设计", EMBEDDED_DOCUMENT, 1)

    bio_key = bio.teaching_data["content_analysis"]["key_points"]
    emb_key = emb.teaching_data["content_analysis"]["key_points"]
    assert "卡尔文循环" in bio_key
    assert "中断处理机制" in emb_key
    assert not set(bio_key) & set(emb_key)

    bio_lecture = next(m["content"] for m in bio.teaching_data["messages"] if m["phase"] == "teach_knowledge")
    emb_lecture = next(m["content"] for m in emb.teaching_data["messages"] if m["phase"] == "teach_knowledge")
    assert bio_lecture != emb_lecture
    # 课程标题不应与知识点重复
    assert "光合作用与细胞呼吸" not in bio_key


def test_each_iteration_targets_a_different_focus(tmp_path):
    """多轮迭代的讲授内容必须逐轮变化，否则迭代没有意义。"""
    stored, _ = _run_session(tmp_path, "rounds", "光合作用与细胞呼吸", BIOLOGY_DOCUMENT, 2)
    lectures = [m["content"] for m in stored.teaching_data["messages"] if m["phase"] == "teach_knowledge"]
    assert len(lectures) == 2
    assert lectures[0] != lectures[1]
    assert "上一轮督导的建议" in lectures[1]


def test_student_questions_reference_real_knowledge_points(tmp_path):
    """学生提问必须引用知识点，不能把讲授稿的开场白当成术语。"""
    stored, _ = _run_session(tmp_path, "questions", "光合作用与细胞呼吸", BIOLOGY_DOCUMENT, 1)
    points = {item["title"] for item in stored.teaching_data["knowledge_points"]}
    questions = [m for m in stored.teaching_data["messages"] if m["phase"] == "student_question"]
    assert len(questions) == 3
    assert {m["level"] for m in questions} == {"high", "medium", "low"}
    for message in questions:
        assert any(point in message["content"] for point in points), message["content"]
        # 讲授稿开场白不应被当作知识点混入提问
        assert "这一节我们把重点放在" not in message["content"]

    contrast = next(m["content"] for m in questions if m["level"] == "low")
    # 辨析类提问是"分不清 A 和 B"句式：应同时引用本轮重点与另一个对照知识点，且对照点不是课程名
    focus = stored.teaching_data["knowledge_points"][0]["title"]
    course = stored.objective
    assert course not in contrast, "提问不应引用课程名本身"
    other_refs = [p for p in points if p in contrast and p != focus and p != course]
    assert other_refs, "辨析类提问应对照另一个知识点"


def test_iteration_runs_the_teacher_selected_number_of_refinement_rounds(tmp_path):
    """教师设置的迭代轮数优先：即使评分达标也继续完成设定的打磨轮次。"""
    stored, events = _run_session(tmp_path, "early", "光合作用与细胞呼吸", BIOLOGY_DOCUMENT, 3)
    rounds = [event for event in events if event.event_type == "node.started" and event.node == "teach_knowledge"]
    assert stored.status == "completed"
    assert len(rounds) == 3
    assert stored.review["score"] == 92
