import asyncio
import logging
from contextlib import suppress
from time import monotonic
from typing import Any

from backend.core.errors import ConflictError, NotFoundError
from backend.workflows.catalog import get_template
from backend.workflows.events import EventHub
from backend.workflows.graph import build_workflow_graph
from backend.workflows.llm import ModelClient
from langgraph.types import Command

from backend.workflows.models import (
    ContinueRequest,
    CreateRunRequest,
    ResumeRequest,
    RunEvent,
    RunRecord,
    TeacherDraftResponse,
    TeacherDraftUpdate,
    TeacherDraftVersionList,
    TeacherSectionGenerationRequest,
    TeacherSectionGenerationResponse,
    utc_now,
)
from backend.workflows.report import build_markdown
from backend.workflows.repository import WorkflowRepository


logger = logging.getLogger("multi_agent_platform.workflows")
WORKFLOW_HEARTBEAT_SECONDS = 10.0


class WorkflowService:
    def __init__(
        self,
        model: ModelClient,
        repository: WorkflowRepository,
        event_hub: EventHub,
        checkpointer: Any,
    ) -> None:
        self.repository = repository
        self.event_hub = event_hub
        self.checkpointer = checkpointer
        self.model = model
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def create_run(self, request: CreateRunRequest) -> RunRecord:
        template = get_template(request.template_id)
        if template is None:
            raise NotFoundError("Workflow template", request.template_id)
        run = RunRecord(
            template_id=request.template_id,
            objective=request.title.strip(),
            context=request.context.strip(),
            provider=f"{self.model.provider}:{self.model.model_name}",
        )
        await self.repository.create_run(run)
        await self._emit(run.id, "run.queued", None, "工作流已进入执行队列", {})
        run = (await self.repository.update_run(run.id, teaching_data={
            "archive_id": request.archive_id,
            "design_id": request.design_id,
            "document_id": request.document_id,
            "document_name": request.document_name,
            "knowledge_points": [item.model_dump() for item in request.knowledge_points],
            "document_sections": [item.model_dump() for item in request.document_sections],
            "extraction_report": request.extraction_report.model_dump() if request.extraction_report else None,
            "max_iterations": request.max_iterations,
            # 恢复与追加轮次需要重建图输入，这些参数必须随会话持久化
            "document_text": request.document_text,
            "interventions": request.interventions.model_dump(),
            "scope": request.scope.model_dump(),
        })) or run
        self._start(run, self._graph_input(run, request))
        return run

    @staticmethod
    def _graph_input(run: RunRecord, request: CreateRunRequest) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "title": run.objective,
            "document_name": request.document_name,
            "document_text": request.document_text,
            "context": run.context,
            "template_id": run.template_id,
            "knowledge_points": [item.model_dump() for item in request.knowledge_points],
            "document_sections": [item.model_dump() for item in request.document_sections],
            "messages": [],
            "current_iteration": 0,
            "max_iterations": request.max_iterations,
            "interventions": request.interventions.model_dump(),
            "scope": request.scope.model_dump(),
            "status": "running",
        }

    def _start(self, run: RunRecord, graph_input: Any) -> None:
        task = asyncio.create_task(self._execute(run, graph_input), name=f"workflow-{run.id}")
        self._tasks[run.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run.id, None))

    async def _execute(self, run: RunRecord, graph_input: Any) -> None:
        template = get_template(run.template_id)
        if template is None:
            return

        history = await self.repository.list_events(run.id)
        completed_steps = sum(
            event.event_type in {"node.completed", "review.completed"} for event in history
        )
        source_data = graph_input if isinstance(graph_input, dict) else run.teaching_data
        max_iterations = max(1, int(source_data.get("max_iterations", 1)))
        total_steps = 2 + 5 * max_iterations
        runtime: dict[str, Any] = {
            "node": None,
            "message": "",
            "started_monotonic": monotonic(),
            "started_at": utc_now().isoformat(),
            "metrics_index": 0,
        }
        metrics_token = self.model.begin_metrics_trace()

        async def emit(event_type: str, node: str | None, message: str, payload: dict[str, Any]) -> None:
            nonlocal completed_steps
            payload = dict(payload)
            if event_type == "node.started":
                await self.repository.update_run(run.id, status="running", current_node=node)
                runtime.update({
                    "node": node,
                    "message": message,
                    "started_monotonic": monotonic(),
                    "started_at": utc_now().isoformat(),
                    "metrics_index": self.model.metrics_count(),
                })
                payload.update({
                    "task_started_at": runtime["started_at"],
                    "step_index": completed_steps + 1,
                    "total_steps": total_steps,
                })
            elif event_type in {"node.completed", "review.completed"}:
                duration_ms = max(1, round((monotonic() - runtime["started_monotonic"]) * 1000))
                completed_steps += 1
                payload.update({
                    "duration_ms": duration_ms,
                    "model_metrics": self.model.metrics_since(int(runtime["metrics_index"])),
                    "completed_steps": completed_steps,
                    "total_steps": total_steps,
                })
            await self._emit(run.id, event_type, node, message, payload)

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(WORKFLOW_HEARTBEAT_SECONDS)
                if runtime["node"] is None:
                    continue
                await self._emit(
                    run.id,
                    "run.heartbeat",
                    runtime["node"],
                    runtime["message"] or "智能体仍在处理当前任务",
                    {
                        "task_started_at": runtime["started_at"],
                        "elapsed_ms": max(1, round((monotonic() - runtime["started_monotonic"]) * 1000)),
                        "step_index": completed_steps + 1,
                        "completed_steps": completed_steps,
                        "total_steps": total_steps,
                    },
                )

        heartbeat_task = asyncio.create_task(heartbeat(), name=f"workflow-heartbeat-{run.id}")

        try:
            await self.repository.update_run(run.id, status="running", error=None, pending_input=None)
            if not isinstance(graph_input, Command):
                await self._emit(run.id, "run.started", "content_analysis", "LangGraph 教学设计流程已启动", {})
            graph = build_workflow_graph(template, self.model, emit, self.checkpointer)
            config = {"configurable": {"thread_id": run.thread_id}, "recursion_limit": 96}
            result = await graph.ainvoke(graph_input, config)

            # __interrupt__ 表示流程停在断点，等待用户输入而非结束
            if "__interrupt__" in result:
                await self._pause(run, graph, config)
                return

            await self._finish(run, result)
        except asyncio.CancelledError:
            await self.repository.update_run(run.id, status="cancelled", error="Run cancelled by user")
            await self._emit(run.id, "run.cancelled", None, "工作流已取消", {})
            raise
        except Exception as exc:
            logger.exception("Workflow run failed", extra={"run_id": run.id})
            await self.repository.update_run(run.id, status="failed", error=str(exc))
            await self._emit(run.id, "run.failed", None, "工作流执行失败", {"error": str(exc)})
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            self.model.end_metrics_trace(metrics_token)

    async def _pause(self, run: RunRecord, graph: Any, config: dict[str, Any]) -> None:
        snapshot = await graph.aget_state(config)
        pending = snapshot.interrupts[0].value if snapshot.interrupts else {}
        await self.repository.update_run(
            run.id,
            status="paused",
            teaching_data={**(await self.get_run(run.id)).teaching_data, **self._snapshot_data(run, snapshot.values)},
            pending_input=pending,
        )
        await self._emit(run.id, "run.paused", pending.get("kind"), pending.get("prompt", "流程已暂停，等待你的处理"), {"pending_input": pending})

    def _snapshot_data(self, run: RunRecord, values: dict[str, Any]) -> dict[str, Any]:
        """暂停时也要把已产出的内容落库，否则前端刷新后看不到断点前的进展。"""
        return {
            "knowledge_points": values.get("knowledge_points", []),
            "document_sections": values.get("document_sections", []),
            "content_analysis": values.get("content_analysis", {}),
            "teaching_framework": values.get("teaching_framework", {}),
            "messages": values.get("messages", []),
            "current_iteration": values.get("current_iteration", 0),
        }

    async def _finish(self, run: RunRecord, result: dict[str, Any]) -> None:
        stored = await self.get_run(run.id)
        teaching_data = {**stored.teaching_data, **self._snapshot_data(run, result)}
        await self.repository.update_run(
            run.id,
            status="completed",
            current_node="finalize",
            final_output=result.get("final_output", result.get("draft", "")),
            review=result.get("supervisor_review", {}),
            teaching_data=teaching_data,
            pending_input=None,
        )
        await self._emit(
            run.id,
            "run.completed",
            "finalize",
            "全部智能体节点执行完成",
            {"review": result.get("supervisor_review", {}), "teaching_data": teaching_data},
        )

    async def resume_run(self, run_id: str, payload: ResumeRequest) -> RunRecord:
        run = await self.get_run(run_id)
        if run.status != "paused":
            raise ConflictError(f"Run in status '{run.status}' is not waiting for input")
        await self._emit(run.id, "run.resumed", None, "已收到你的处理，流程继续", {"action": payload.action})
        self._start(run, Command(resume=payload.model_dump()))
        return (await self.repository.get_run(run_id)) or run

    async def continue_run(self, run_id: str, payload: ContinueRequest) -> RunRecord:
        """在已完成的会话上追加教学轮次，沿用已有督导建议继续迭代。"""
        run = await self.get_run(run_id)
        if run.status != "completed":
            raise ConflictError(f"Run in status '{run.status}' cannot be continued")
        data = run.teaching_data or {}
        if not data.get("document_text"):
            raise ConflictError("该会话缺少原始材料，无法继续迭代")

        done = int(data.get("current_iteration", 0))
        target = done + payload.additional_iterations
        context = "\n".join(filter(None, [run.context, payload.context.strip()]))
        # 新线程重新入图：原线程已走到 END，复用会被 checkpointer 直接判定为已完成
        thread_id = f"{run.thread_id}-r{target}"
        await self.repository.update_run(
            run.id, status="running", error=None, pending_input=None,
            teaching_data={**data, "max_iterations": target},
            context=context,
            thread_id=thread_id,
        )
        await self._emit(run.id, "run.continued", None, f"在已有 {done} 轮基础上追加 {payload.additional_iterations} 轮教学", {"from_iteration": done, "max_iterations": target})
        self._start(run.model_copy(update={"thread_id": thread_id, "context": context}), {
            "run_id": run.id,
            "title": run.objective,
            "document_name": data.get("document_name", "课程材料"),
            "document_text": data["document_text"],
            "context": context,
            "template_id": run.template_id,
            "knowledge_points": data.get("knowledge_points", []),
            "document_sections": data.get("document_sections", []),
            "content_analysis": data.get("content_analysis", {}),
            "teaching_framework": data.get("teaching_framework", {}),
            # 历史消息带入新线程，导出与前端才能看到连续的全过程
            "messages": data.get("messages", []),
            "supervisor_review": run.review or {},
            "current_iteration": done,
            "max_iterations": target,
            "interventions": data.get("interventions", {}),
            "scope": data.get("scope", {}),
            "status": "running",
        })
        return (await self.repository.get_run(run_id)) or run

    async def _emit(
        self,
        run_id: str,
        event_type: str,
        node: str | None,
        message: str,
        payload: dict[str, Any],
    ) -> RunEvent:
        event = await self.repository.append_event(
            RunEvent(run_id=run_id, event_type=event_type, node=node, message=message, payload=payload)
        )
        await self.event_hub.publish(event)
        return event

    async def get_run(self, run_id: str) -> RunRecord:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError("Workflow run", run_id)
        return run

    async def get_teacher_draft(self, run_id: str) -> TeacherDraftResponse:
        run = await self.get_run(run_id)
        if not run.final_output:
            raise ConflictError("教学成果尚未生成，暂时不能编辑教师资料")
        draft = await self.repository.get_teacher_draft(run_id)
        if draft:
            return TeacherDraftResponse(
                run_id=run_id,
                version=draft.version,
                content=draft.content,
                status=draft.status,
                source="teacher",
                updated_at=draft.created_at,
            )
        return TeacherDraftResponse(
            run_id=run_id,
            version=0,
            content=build_markdown(run),
            status="draft",
            source="generated",
            updated_at=run.updated_at,
        )

    async def save_teacher_draft(
        self, run_id: str, payload: TeacherDraftUpdate
    ) -> TeacherDraftResponse:
        await self.get_teacher_draft(run_id)
        saved = await self.repository.save_teacher_draft(
            run_id,
            payload.content.strip(),
            payload.status,
            payload.base_version,
        )
        if saved is None:
            raise ConflictError("教师稿已在其他页面更新，请刷新后再保存")
        return TeacherDraftResponse(
            run_id=run_id,
            version=saved.version,
            content=saved.content,
            status=saved.status,
            source="teacher",
            updated_at=saved.created_at,
        )

    async def list_teacher_draft_versions(
        self, run_id: str, limit: int = 20
    ) -> TeacherDraftVersionList:
        await self.get_run(run_id)
        return TeacherDraftVersionList(
            items=await self.repository.list_teacher_draft_versions(run_id, limit)
        )

    async def generate_teacher_section(
        self, run_id: str, payload: TeacherSectionGenerationRequest
    ) -> TeacherSectionGenerationResponse:
        run = await self.get_run(run_id)
        if not run.final_output:
            raise ConflictError("教学成果尚未生成，暂时不能局部生成")
        points = [
            str(item.get("title", "")).strip()
            for item in (run.teaching_data or {}).get("knowledge_points", [])
            if item.get("title")
        ]
        instruction = payload.instruction.strip() or "提升准确性、条理性和教师可直接使用程度"
        content = await self.model.generate(
            """你是教师资料编辑助手。只改写用户指定的当前资料块，不扩写其他章节。
必须保留教材中的事实、公式、代码和条件边界；没有材料依据时不得新增事实。
输出可直接替换原资料块的 Markdown，不要解释修改过程，不要包裹代码围栏。""",
            f"""课程：{run.objective}
教材知识点：{'；'.join(points) or '以当前资料为准'}
资料标题：{payload.section_title}
修改要求：{instruction}
当前资料：
{payload.current_content}""",
        )
        return TeacherSectionGenerationResponse(
            section_title=payload.section_title,
            content=content.strip(),
        )

    async def cancel_run(self, run_id: str) -> RunRecord:
        run = await self.get_run(run_id)
        if run.status not in {"queued", "running", "paused"}:
            raise ConflictError(f"Run in status '{run.status}' cannot be cancelled")
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            # 暂停中的会话没有运行中的 task，需直接落库
            await self.repository.update_run(run_id, status="cancelled", error="Run cancelled by user", pending_input=None)
            await self._emit(run_id, "run.cancelled", None, "工作流已取消", {})
        return (await self.repository.get_run(run_id)) or run

    async def delete_run(self, run_id: str) -> None:
        run = await self.get_run(run_id)
        # 运行中的会话必须先停掉后台任务，否则它会继续向已删除的记录写事件
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.repository.delete_run(run.id)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def replace_model(self, model: ModelClient) -> None:
        self.model = model
