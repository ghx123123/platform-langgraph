"""Application integration boundary for classroom_v2.

This module adapts persisted classroom facts to the existing workflow EventHub
without coupling classroom execution to the legacy LangGraph graph.
"""
from __future__ import annotations

from typing import Any
import asyncio
import json
import logging
import re

from backend.workflows.events import EventHub
from backend.workflows.models import RunEvent

from .models import ClassroomEvent
from .repository import ClassroomRepository
from .evaluation import SupervisorEvaluationService
from .revision import RevisionEngine
from .models import ClassroomEventType, LessonReviewMessage, SimulationRound, StudentPersona, RevisionPatch, SupervisorObservation
from .orchestrator import ClassroomOrchestrator
from .agent_services import TeacherAgentService, StudentAgentService
from .agent_runtime import HarnessAgentRuntime
from .actions import TeacherAction, TeacherActionType, StudentAction, StudentActionType
from .lesson_blueprint import LessonBlueprintService

from backend.workflows.models import utc_now


logger = logging.getLogger(__name__)


def _strip_code_fence(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    return text


def _json_candidates(text: str) -> list[str]:
    """Candidate JSON fragments inside a possibly prose-wrapped provider reply.

    Array fragments are tried before object fragments: a patch reply is normally a
    JSON array, and reaching for the first `{` would truncate the array to its first
    element and silently drop every other patch.
    """
    fragments: list[str] = []
    for opener, closer in (("[", "]"), ("{", "}")):
        position = text.find(opener)
        while position >= 0:
            end = text.rfind(closer)
            if end > position:
                fragments.append(text[position:end + 1])
            position = text.find(opener, position + 1)
    return fragments


def _parse_patch_payload(raw: Any) -> list[dict[str, Any]]:
    """Parse a provider patch response into a list of patch dicts.

    Accepts a bare list, a wrapped object ({"patches": [...]}), a JSON string with or
    without a code fence, and a reply that wraps the JSON in prose. Returns [] only
    when nothing usable can be recovered, logging the head of the raw response so a
    silently dropped correction stays diagnosable.
    """
    if isinstance(raw, dict):
        payload: Any = raw.get("patches", raw.get("items", raw))
    elif isinstance(raw, list):
        payload = raw
    elif isinstance(raw, str):
        text = _strip_code_fence(raw)
        payload = None
        for fragment in _json_candidates(text):
            try:
                payload = json.loads(fragment)
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            logger.warning(
                "directive patch payload was not parseable JSON; raw head=%r",
                text[:300],
            )
            return []
    else:
        return []
    if isinstance(payload, dict):
        payload = payload.get("patches", payload.get("items", []))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _extract_slide_previews(text: str) -> list[dict[str, Any]]:
    """Extract only fully closed slide objects from a streaming JSON response."""
    marker = text.find('"slides"')
    if marker < 0:
        return []
    start = text.find("[", marker)
    if start < 0:
        return []
    result: list[dict[str, Any]] = []
    depth = 0
    object_start = -1
    in_string = False
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                object_start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and object_start >= 0:
                try:
                    slide = json.loads(text[object_start:index + 1])
                except json.JSONDecodeError:
                    object_start = -1
                    continue
                ppt = slide.get("ppt_content") or {}
                result.append({
                    "title": str(ppt.get("title") or slide.get("title") or ""),
                    "subtitle": str(ppt.get("subtitle") or ""),
                    "bullets": [str(item) for item in (ppt.get("bullets") or [])[:4]],
                })
                object_start = -1
        elif char == "]" and depth == 0:
            break
    return result


def _pause_after_student_question(run: Any) -> bool:
    """教师是否勾选了「学生提问后暂停」。

    classroom_v2 过去完全不读这个开关, 导致勾选后什么都不会发生。
    """
    teaching_data = getattr(run, "teaching_data", None) or {}
    interventions = teaching_data.get("interventions") if isinstance(teaching_data, dict) else {}
    interventions = interventions if isinstance(interventions, dict) else {}
    return bool(interventions.get("after_question"))


def _requested_slide_count(run: Any) -> int | None:
    """Return the persisted page target for truthful generation progress."""
    teaching_data = getattr(run, "teaching_data", None) or {}
    scope = teaching_data.get("scope") if isinstance(teaching_data, dict) else {}
    scope = scope if isinstance(scope, dict) else {}
    raw = scope.get("ppt_slide_count") or teaching_data.get("ppt_slide_count")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class _MockTeacher:
    async def act(self, *args: Any, **kwargs: Any) -> TeacherAction:
        block = args[3] if len(args) > 3 else None
        if block is not None:
            return TeacherAction(action_type=TeacherActionType.SUMMARIZE if str(getattr(block, "block_type", "")).lower() == "summary" else TeacherActionType.EXPLAIN, speech=block.content)
        return TeacherAction(action_type=TeacherActionType.SUMMARIZE, speech="我们回顾本页要点。")


class _MockStudents:
    async def act(self, *args: Any, **kwargs: Any) -> StudentAction:
        return StudentAction(action_type=StudentActionType.ANSWER, content="我理解了这个概念。", confidence=.6)


class ClassroomIntegrationService:
    def __init__(self, repository: ClassroomRepository, event_hub: EventHub, *, evaluator: SupervisorEvaluationService | None = None, revision_engine: RevisionEngine | None = None) -> None:
        self.repository = repository
        self.event_hub = event_hub
        self._orchestrators: dict[str, Any] = {}
        self.evaluator = evaluator or SupervisorEvaluationService(repository)
        self.revision_engine = revision_engine or RevisionEngine(repository)
        self._custom_evaluator = evaluator is not None
        self._custom_revision_engine = revision_engine is not None
        self._max_rounds: dict[str, int] = {}
        self._tasks: dict[str, Any] = {}
        self._startup_tasks: dict[str, asyncio.Task[None]] = {}
        self._startup_status: dict[str, dict[str, Any]] = {}
        self._run_locks: dict[str, asyncio.Lock] = {}
        # 每次 run 的 agent runtime(用于把教师纠正转成补丁)
        self._agent_runtimes: dict[str, Any] = {}

    def _run_lock(self, run_id: str) -> asyncio.Lock:
        return self._run_locks.setdefault(run_id, asyncio.Lock())

    def start_status(self, run_id: str) -> dict[str, Any]:
        status = dict(self._startup_status.get(run_id) or {
            "run_id": run_id,
            "phase": "idle",
            "message": "尚未开始课堂准备",
            "generated_chars": 0,
            "preview": "",
            "slide_previews": [],
            "closed_slide_count": 0,
            "target_slide_count": None,
            "generation_attempt": 0,
            "generation_request_id": f"{run_id}:lesson:v1",
        })
        # Older lifecycle updates (and post-process states) may not carry the
        # new observability keys.  Fill them at the boundary so clients can
        # safely consume one stable contract throughout a run.
        status.setdefault("slide_previews", [])
        status.setdefault("closed_slide_count", 0)
        status.setdefault("target_slide_count", None)
        status.setdefault("generation_attempt", 0)
        status.setdefault("generation_request_id", f"{run_id}:lesson:v1")
        return status

    async def _status_from_rounds(self, run_id: str, rounds: list[Any]) -> dict[str, Any]:
        latest = rounds[-1]
        versions = await self.repository.list_lesson_versions(run_id)
        lesson = next((item for item in versions if item.id == latest.lesson_version_id), None)
        completed = latest.status in ("completed", "stopped", "failed")
        return {
            "run_id": run_id,
            "phase": "classroom_completed" if completed else "classroom_running",
            "message": (
                f"第 {latest.round_number} 轮课堂演练已完成"
                if completed
                else f"第 {latest.round_number} 轮课堂演练进行中"
            ),
            "round_id": latest.id,
            "generated_chars": 0,
            "preview": "",
            "slide_previews": [],
            "closed_slide_count": len(lesson.slides) if lesson else 0,
            "target_slide_count": len(lesson.slides) if lesson else None,
            "generation_attempt": 0,
            "generation_request_id": f"{run_id}:lesson:v1",
        }

    async def resolved_start_status(self, run_id: str) -> dict[str, Any]:
        current = self.start_status(run_id)
        if current["phase"] != "idle":
            # 进程内 phase 可能落后于持久事实（耗时任务的中间态不会被写回 DB）。
            # 若 DB 里已存在课堂轮次，就不要再报"正在创建 Session/正在生成 PPT"，
            # 否则同屏会出现「课堂运行中」的标签配上「等待审阅」的进度条。
            rounds = await self.repository.list_simulation_rounds(run_id)
            if rounds:
                return await self._status_from_rounds(run_id, rounds)
            return current
        rounds = await self.repository.list_simulation_rounds(run_id)
        if rounds:
            return await self._status_from_rounds(run_id, rounds)
        versions = await self.repository.list_lesson_versions(run_id)
        if versions:
            latest = versions[-1]
            return {
                "run_id": run_id,
                "phase": "awaiting_review" if latest.status == "draft" else "blueprint_ready",
                "message": "PPT V1 等待教师逐页审阅" if latest.status == "draft" else "Lesson Blueprint 已就绪",
                "version_id": latest.id,
                "generated_chars": 0,
                "preview": "",
                "slide_previews": [],
                "closed_slide_count": len(latest.slides),
                "target_slide_count": len(latest.slides),
                "generation_attempt": 0,
                "generation_request_id": f"{run_id}:lesson:v1",
            }
        return current

    async def begin_preparation(
        self,
        run_id: str,
        *,
        workflow_service: Any,
        retry: bool = False,
        max_slides: int | None = None,
    ) -> dict[str, Any]:
        """Queue Blueprint generation and stop at the persisted review gate.

        retry=True 时先清掉上次失败留下的 V1 与失败态, 再重新生成;
        max_slides 允许教师降级重试(例如 45 页失败后按 15 页重试)。
        """
        existing = self._startup_tasks.get(run_id)
        if existing is not None and not existing.done():
            return self.start_status(run_id)
        run = await workflow_service.get_run(run_id)
        if max_slides:
            # 降级重试: 把页数写回 run.scope, 后续 _requested_slide_count / 提示词都按新页数走。
            teaching_data = dict(run.teaching_data or {})
            scope = dict(teaching_data.get("scope") or {})
            scope["ppt_slide_count"] = int(max_slides)
            teaching_data["scope"] = scope
            await workflow_service.repository.update_run(run_id, teaching_data=teaching_data)
            run = await workflow_service.get_run(run_id)
        target = _requested_slide_count(run)
        if retry:
            await self._discard_failed_preparation(run_id)
        # A second prepare click after V1 is persisted is a recovery/read
        # operation.  It must not enqueue another model generation request.
        existing_rounds = await self.repository.list_simulation_rounds(run_id)
        if existing_rounds:
            # 后端重启后 orchestrator/_startup_status 都是进程内状态，会随进程消失。
            # 前端加载课堂时调用的就是这个接口，因此在这里把进行中的轮次重新拉起：
            # 否则暂停/继续/停止/介入一律 409「classroom runtime is not active」，
            # 教师只能看到界面显示"进行中"却完全无法控制（实测复现）。
            await self._reconnect_after_restart(run_id, existing_rounds, workflow_service)
            return await self.resolved_start_status(run_id)
        existing_versions = await self.repository.list_lesson_versions(run_id)
        if existing_versions:
            latest = existing_versions[-1]
            status = {
                "run_id": run_id,
                "phase": "awaiting_review" if latest.status == "draft" else "blueprint_ready",
                "message": f"PPT V{latest.version_number} 已生成，等待逐页审阅",
                "version_id": latest.id,
                "generated_chars": 0,
                "preview": "",
                "slide_previews": [],
                "closed_slide_count": len(latest.slides),
                "target_slide_count": target or len(latest.slides),
                "generation_attempt": 0,
                "generation_request_id": f"{run_id}:lesson:v1",
            }
            self._startup_status[run_id] = status
            await workflow_service.repository.update_run(run_id, status="paused", error=None)
            return dict(status)
        await workflow_service.repository.update_run(run_id, status="running", error=None)
        self._startup_status[run_id] = {
            "run_id": run_id,
            "phase": "queued",
            "message": "资料分析与 PPT 生成任务已进入队列",
            "generated_chars": 0,
            "preview": "",
            "slide_previews": [],
            "closed_slide_count": 0,
            "target_slide_count": target,
            "generation_attempt": 0,
            "generation_request_id": f"{run_id}:lesson:v1",
        }

        async def execute() -> None:
            try:
                result = await self.start_run(run_id, workflow_service=workflow_service, prepare_only=True)
                lesson = result["lesson_version"]
                messages = await self.repository.list_lesson_review_messages(run_id, lesson["id"])
                if not messages:
                    await self.repository.append_lesson_review_message(LessonReviewMessage(
                        run_id=run_id,
                        version_id=lesson["id"],
                        role="teacher",
                        content=f"PPT V{lesson['version_number']} 已完成，共 {len(lesson['slides'])} 页。请逐页审阅；你的意见只会修改当前页面。",
                    ))
                self._startup_status[run_id].update({
                    "phase": "awaiting_review",
                    "message": f"PPT V{lesson['version_number']} 已生成，等待逐页审阅",
                    "version_id": lesson["id"],
                    "closed_slide_count": len(lesson["slides"]),
                    "target_slide_count": target or len(lesson["slides"]),
                })
                await workflow_service.repository.update_run(run_id, status="paused")
            except Exception as exc:
                logger.exception("classroom preparation failed for run_id=%s", run_id)
                self._startup_status[run_id].update({
                    "phase": "failed",
                    "message": f"PPT 生成失败：{exc}",
                    "error": str(exc),
                })
                await workflow_service.repository.update_run(run_id, status="failed", error=str(exc))

        task = asyncio.create_task(execute(), name=f"classroom-prepare-{run_id}")
        self._startup_tasks[run_id] = task
        return self.start_status(run_id)

    async def _discard_failed_preparation(self, run_id: str) -> None:
        """清除上次失败留下的 PPT V1, 让教师能重新生成。

        只删除"没有进过课堂演练"的版本: 一旦有 simulation round 引用该版本, 删掉会破坏
        课堂记录, 此时拒绝重生成(调用方随后会走 resolved_start_status 读路径)。
        """
        rounds = await self.repository.list_simulation_rounds(run_id)
        if rounds:
            raise ValueError("该会话已进入课堂演练, 不能重新生成 PPT; 请新建会话")
        versions = await self.repository.list_lesson_versions(run_id)
        for version in versions:
            await self.repository.delete_lesson_version(version.id)
        self._startup_status.pop(run_id, None)

    async def _reconnect_after_restart(self, run_id: str, rounds: list[Any], workflow_service: Any) -> bool:
        """Rebind an in-flight round to a fresh orchestrator after a process restart.

        orchestrator/_startup_status/_tasks are per-process. Once uvicorn restarts they
        are gone while the DB still says status=running, so every control and
        intervention call answers 409「classroom runtime is not active」and the teacher
        is locked out of a classroom the UI still shows as running. Rebuild the runtime
        from the persisted LessonVersion and let the round continue from its cursor.

        Returns True when a live round is bound again.
        """
        # "paused" 是教师显式暂停的持久状态：重启后 orchestration 任务确实不在了，
        # 但仍必须重建 runtime，否则「继续 / 停止 / 介入」全部 409，课堂再也无法恢复。
        active = next(
            (item for item in rounds if item.status in ("running", "paused")),
            None,
        )
        if active is None:
            return False
        if self.orchestrator_for(run_id) is not None:
            return True
        if run_id in self._tasks and not self._tasks[run_id].done():
            return True
        versions = await self.repository.list_lesson_versions(run_id)
        lesson = next((item for item in versions if item.id == active.lesson_version_id), None)
        if lesson is None:
            return False
        logger.warning(
            "classroom runtime missing for run_id=%s round=%s (backend restarted?); rebinding",
            run_id, active.id,
        )
        try:
            await self._start_run_locked(
                run_id,
                workflow_service=workflow_service,
                max_rounds=self._max_rounds.get(run_id, 1),
                version_id=lesson.id,
            )
        except Exception:
            logger.exception("classroom runtime rebind failed for run_id=%s", run_id)
            return False
        return self.orchestrator_for(run_id) is not None

    async def begin_run(self, run_id: str, *, workflow_service: Any, max_rounds: int | None = None) -> dict[str, Any]:
        """Queue classroom preparation and return immediately.

        Blueprint generation can take several minutes with a real provider.
        Keeping it outside the request lifecycle prevents proxy/browser timeout
        errors and gives the product a truthful, observable preparation state.
        """
        existing = self._startup_tasks.get(run_id)
        if existing is not None and not existing.done():
            return self.start_status(run_id)
        # Validate the canonical workflow run before acknowledging the job.
        run = await workflow_service.get_run(run_id)
        target = _requested_slide_count(run)
        self._startup_status[run_id] = {
            "run_id": run_id,
            "phase": "queued",
            "message": "课堂准备任务已进入队列",
            "generated_chars": 0,
            "preview": "",
            "slide_previews": [],
            "closed_slide_count": 0,
            "target_slide_count": target,
            "generation_attempt": 0,
            "generation_request_id": f"{run_id}:lesson:v1",
        }

        async def execute() -> None:
            try:
                snapshot = await self.start_run(run_id, workflow_service=workflow_service, max_rounds=max_rounds)
                round_data = snapshot.get("round") or {}
                lesson_data = snapshot.get("lesson_version") or {}
                self._startup_status[run_id].update({
                    "phase": "classroom_running",
                    "message": "Lesson Blueprint 已完成，真实课堂演练已开始",
                    "round_id": round_data.get("id"),
                    "version_id": lesson_data.get("id"),
                    "closed_slide_count": len(lesson_data.get("slides") or []),
                    "target_slide_count": len(lesson_data.get("slides") or []) or target,
                })
            except Exception as exc:
                logger.exception("classroom startup failed for run_id=%s", run_id)
                detail = str(exc)
                if "learning objectives must not be empty" in detail.lower():
                    detail = "未找到学习目标，已根据所选知识点自动补齐；请重试课堂启动"
                self._startup_status[run_id].update({
                    "phase": "failed",
                    "message": f"课堂启动失败：{detail}",
                    "error": detail,
                })

        task = asyncio.create_task(execute(), name=f"classroom-start-{run_id}")
        self._startup_tasks[run_id] = task
        return self.start_status(run_id)

    async def start_run(self, run_id: str, *, workflow_service: Any, max_rounds: int | None = None, version_id: str | None = None, prepare_only: bool = False) -> dict[str, Any]:
        # All lifecycle entry points converge here.  Serializing by canonical
        # run_id prevents double-clicks/React remounts from generating V1 or
        # creating Round 1 twice while allowing different courses to proceed
        # independently.
        async with self._run_lock(run_id):
            return await self._start_run_locked(
                run_id,
                workflow_service=workflow_service,
                max_rounds=max_rounds,
                version_id=version_id,
                prepare_only=prepare_only,
            )

    async def _start_run_locked(self, run_id: str, *, workflow_service: Any, max_rounds: int | None = None, version_id: str | None = None, prepare_only: bool = False) -> dict[str, Any]:
        """Create/reuse a V1 blueprint, create the first round and run it.

        This is the product entry point for classroom_v2. Legacy workflow data
        remains untouched; classroom facts are written only to the classroom
        repository and every lookup is scoped by run_id.
        """
        run = await workflow_service.get_run(run_id)
        versions = await self.repository.list_lesson_versions(run_id)
        target_slide_count = _requested_slide_count(run)
        if not versions:
            self._startup_status.setdefault(run_id, {"run_id": run_id})
            self._startup_status[run_id].update({
                "phase": "blueprint_generating",
                "message": "DSH 正在生成逐页 Lesson Blueprint",
                "generated_chars": 0,
                "preview": "",
                "slide_previews": [],
                "closed_slide_count": 0,
                "target_slide_count": target_slide_count,
                "generation_attempt": 0,
                "generation_request_id": f"{run_id}:lesson:v1",
            })
            async def generate(system: str, user: str) -> Any:
                status = self._startup_status.setdefault(run_id, {
                    "run_id": run_id,
                    "phase": "blueprint_generating",
                    "generated_chars": 0,
                    "preview": "",
                    "slide_previews": [],
                    "closed_slide_count": 0,
                    "target_slide_count": target_slide_count,
                    "generation_request_id": f"{run_id}:lesson:v1",
                })
                status["generation_attempt"] = int(status.get("generation_attempt") or 0) + 1
                logger.info(
                    "classroom blueprint generation request",
                    extra={
                        "run_id": run_id,
                        "generation_request_id": f"{run_id}:lesson:v1",
                        "generation_attempt": status["generation_attempt"],
                    },
                )
                if workflow_service.model.is_mock:
                    # Keep local demos fully offline while preserving the same
                    # structured blueprint contract used by the real provider.
                    context = LessonBlueprintService(self.repository).build_generation_context(run.model_dump(mode="json"), run_id=run_id)
                    count = int(context.get("target_slide_count") or min(6, max(1, context["estimated_minutes"])))
                    per_slide = context["estimated_minutes"] / count
                    points = context["knowledge_points"] or [context["title"]]
                    slides = []
                    for index in range(count):
                        point = points[index % len(points)]
                        slides.append({
                            "title": point if count > 1 else context["title"],
                            "purpose": f"理解并应用{point}",
                            "learning_objectives": context["learning_objectives"],
                            "knowledge_points": [point],
                            "estimated_minutes": per_slide,
                            "ppt_content": {"title": point, "subtitle": context["title"], "bullets": [f"明确{point}的核心含义", f"结合材料判断{point}的适用条件"], "examples": [f"使用一个具体任务检验对{point}的理解"]},
                            "speaker_notes": [{"block_type": "EXPLANATION", "content": f"教师依据课程材料讲解{point}，说明核心概念、适用条件和常见误区。", "estimated_seconds": max(15, round(per_slide * 60))}],
                        })
                    return {"title": context["title"], "learning_objectives": context["learning_objectives"], "knowledge_points": context["knowledge_points"], "slides": slides}
                generated_parts: list[str] = []

                async def on_chunk(chunk: str) -> None:
                    generated_parts.append(chunk)
                    text = "".join(generated_parts)
                    all_previews = _extract_slide_previews(text)
                    self._startup_status[run_id].update({
                        "phase": "blueprint_generating",
                        "message": "DSH 正在生成逐页 PPT、讲稿与互动锚点",
                        "generated_chars": len(text),
                        # This is provider output, never hidden reasoning. Limit
                        # the runtime cache so long blueprints cannot grow it.
                        "preview": text[-2000:],
                        # Render a bounded recent window, but report the true
                        # number of fully closed slide objects separately.
                        "slide_previews": all_previews[-4:],
                        "closed_slide_count": len(all_previews),
                        "target_slide_count": target_slide_count,
                    })

                return await workflow_service.model.generate(system, user, on_chunk=on_chunk)
            async def on_blueprint_retry(reason: str) -> None:
                self._startup_status[run_id].update({
                    "message": "首次结构化输出未通过校验，正在自动修复后重试",
                    "generation_retry_reason": reason[:500],
                })

            blueprint = await LessonBlueprintService(
                self.repository,
                generate,
                on_retry=on_blueprint_retry,
            ).generate_blueprint(run_id, run.model_dump(mode="json"))
            versions = [blueprint]
            self._startup_status[run_id].update({
                "phase": "blueprint_ready",
                "message": f"Lesson Blueprint V{blueprint.version_number} 已通过结构校验",
                "version_id": blueprint.id,
                "closed_slide_count": len(blueprint.slides),
                "target_slide_count": target_slide_count or len(blueprint.slides),
                "generation_request_id": f"{run_id}:lesson:v1",
            })
        lesson = next((item for item in versions if item.id == version_id), None) if version_id else versions[-1]
        if lesson is None:
            raise LookupError("lesson version not found in run")
        if prepare_only:
            return {"run_id": run_id, "lesson_version": lesson.model_dump(mode="json"), "phase": "awaiting_review"}
        self._startup_status.setdefault(run_id, {"run_id": run_id})
        self._startup_status[run_id].update({
            "phase": "classroom_starting",
            "message": "正在创建独立 Teacher / Student Agent Session",
            "version_id": lesson.id,
            "closed_slide_count": len(lesson.slides),
            "target_slide_count": target_slide_count or len(lesson.slides),
            "generation_attempt": int(self._startup_status[run_id].get("generation_attempt") or 0),
            "generation_request_id": f"{run_id}:lesson:v1",
        })
        rounds = await self.repository.list_simulation_rounds(run_id)
        if rounds:
            round_item = rounds[-1]
            if self.orchestrator_for(run_id) is None:
                # Runtime reconstruction after process restart. Durable round,
                # lesson and event history remain the source of truth.
                personas = self._build_personas(run_id, round_item.scenario_seed)
                runtime = None
                if workflow_service.model.is_mock or workflow_service.model.provider != "dsh":
                    teacher, students = _MockTeacher(), _MockStudents()
                else:
                    runtime = HarnessAgentRuntime(workflow_service.model.ensure_dsh_engine())
                    teacher, students = TeacherAgentService(runtime, self.repository), StudentAgentService(runtime, self.repository)
                orchestrator = ClassroomOrchestrator(self.repository, teacher, students, personas=personas, pause_after_student_question=_pause_after_student_question(run))
                self.bind_orchestrator(
                    run_id, orchestrator,
                    max_rounds=max(1, int(max_rounds or (run.teaching_data or {}).get("max_iterations") or 1)),
                    workflow_service=workflow_service, runtime=runtime,
                )
                await orchestrator.restore_round(lesson, round_item)
                restored_states = await self.repository.list_student_cognitive_states(round_item.id)
                orchestrator.cognitive_states = {
                    persona.student_id: [state for state in restored_states if state.student_id == persona.student_id]
                    for persona in personas
                }
                restored_state = await self.repository.get_classroom_state(round_item.id)
                # 「paused」是教师显式暂停的持久状态：重建 runtime 后必须继续停住，
                # 等教师点「继续」再跑；只有 active 才重新拉起 run_round 任务。
                if restored_state is None or restored_state.status in {"active"}:
                    self._tasks[run_id] = asyncio.create_task(orchestrator.run_round(round_item.id), name=f"classroom-{run_id}")
                elif restored_state.status == "paused":
                    orchestrator.resume_phase = restored_state.phase if restored_state.phase != "paused" else "teacher_act"
        else:
            target_rounds = max(1, int(max_rounds or (run.teaching_data or {}).get("max_iterations") or 1))
            round_item = SimulationRound(run_id=run_id, round_number=1, lesson_version_id=lesson.id, scenario_seed=f"{run_id}:scenario")
            personas = self._build_personas(run_id, round_item.scenario_seed)
            runtime = None
            if workflow_service.model.is_mock or workflow_service.model.provider != "dsh":
                teacher, students = _MockTeacher(), _MockStudents()
            else:
                runtime = HarnessAgentRuntime(workflow_service.model.ensure_dsh_engine())
                teacher, students = TeacherAgentService(runtime, self.repository), StudentAgentService(runtime, self.repository)
            orchestrator = ClassroomOrchestrator(self.repository, teacher, students, personas=personas, pause_after_student_question=_pause_after_student_question(run))
            self.bind_orchestrator(
                run_id, orchestrator, max_rounds=target_rounds,
                workflow_service=workflow_service, runtime=runtime,
            )
            await orchestrator.start_round(lesson, round_item, personas=personas)
            initial_states = await self.revision_engine.initialize_round_cognitive_states(
                run_id, round_item, personas, lesson.knowledge_points,
            )
            orchestrator.cognitive_states = {
                persona.student_id: [state for state in initial_states if state.student_id == persona.student_id]
                for persona in personas
            }
            task = asyncio.create_task(orchestrator.run_round(round_item.id), name=f"classroom-{run_id}")
            self._tasks[run_id] = task
        return await self.get_snapshot(run_id, round_item.id)

    def register_orchestrator(self, run_id: str, orchestrator: Any) -> None:
        self._orchestrators[run_id] = orchestrator

    def bind_orchestrator(
        self,
        run_id: str,
        orchestrator: Any,
        *,
        max_rounds: int = 1,
        workflow_service: Any | None = None,
        runtime: HarnessAgentRuntime | None = None,
    ) -> None:
        """Attach persistence fan-out and post-boundary evaluation hooks."""
        self._orchestrators[run_id] = orchestrator
        self._max_rounds[run_id] = max(1, int(max_rounds))
        if runtime is not None:
            self._agent_runtimes[run_id] = runtime
        orchestrator.on_event = self.publish_event

        active_evaluator = self.evaluator
        if runtime is not None and not self._custom_evaluator:
            active_evaluator = SupervisorEvaluationService(self.repository, runtime=runtime)

        async def on_slide(lesson: Any, round_item: Any, slide: Any) -> None:
            # 教师指令要交给督导逐条判定是否被遵守(含已落实的历史指令, 便于解释为何没改)
            directives = await self.repository.list_teacher_directives(run_id, round_id=round_item.id)
            try:
                await active_evaluator.evaluate_slide(run_id, round_item, slide, directives=directives)
            except Exception:
                logger.exception("DSH supervisor slide evaluation failed for run_id=%s slide_id=%s; using evidence fallback", run_id, slide.slide_id)
                if active_evaluator is not self.evaluator:
                    await self.evaluator.evaluate_slide(run_id, round_item, slide, directives=directives)

        async def on_round(lesson: Any, round_item: Any) -> None:
            observations = await self.repository.list_supervisor_observations(round_item.id)
            try:
                report = await active_evaluator.evaluate_round(run_id, round_item, lesson.learning_objectives, observations=observations)
            except Exception:
                logger.exception("DSH supervisor report failed for run_id=%s round_id=%s; using evidence fallback", run_id, round_item.id)
                report = await self.evaluator.evaluate_round(run_id, round_item, lesson.learning_objectives, observations=observations)
            await self._append_postprocess_event(
                run_id, round_item, ClassroomEventType.EVALUATION_COMPLETED,
                f"督导完成第 {round_item.round_number} 轮复盘，综合评分 {report.overall_score}",
                actor_id="supervisor", actor_role="supervisor",
                metadata={"report_id": report.id, "overall_score": report.overall_score},
            )
            if workflow_service is not None:
                stored_run = await workflow_service.get_run(run_id)
                await workflow_service.repository.update_run(
                    run_id,
                    teaching_data={
                        **(stored_run.teaching_data or {}),
                        "current_iteration": round_item.round_number,
                    },
                )

            active_revision = self.revision_engine
            if runtime is not None and not self._custom_revision_engine:
                async def generate_revision(system: str, user: str) -> Any:
                    return await runtime.generate(run_id, round_item.round_number, "teacher", system, user)
                active_revision = RevisionEngine(self.repository, generator=generate_revision)
            try:
                next_lesson, patches, finalized = await active_revision.refine_round(
                    lesson, round_item, report, max_rounds=self._max_rounds[run_id], observations=observations,
                )
            except Exception:
                logger.exception("DSH lesson revision failed for run_id=%s round_id=%s; using deterministic patch fallback", run_id, round_item.id)
                next_lesson, patches, finalized = await self.revision_engine.refine_round(
                    lesson, round_item, report, max_rounds=self._max_rounds[run_id], observations=observations,
                )
            await self._append_postprocess_event(
                run_id, round_item, ClassroomEventType.REVISION_COMPLETED,
                "最终轮已定稿" if finalized else f"已生成 LessonVersion V{next_lesson.version_number}",
                actor_id="teacher", actor_role="teacher",
                metadata={"version_id": next_lesson.id, "version_number": next_lesson.version_number, "patch_count": len(patches), "finalized": finalized},
            )
            if finalized:
                # 定稿 = 整节课结束，lesson 范围的指令到此落实。
                # 过去只在 slide/round 边界 resolve，scope=lesson 的指令会永远停在
                # status='active'，复盘页一直显示「生效中」（实测复现）。
                resolved_lesson = await self.repository.resolve_teacher_directives(
                    run_id, round_id=round_item.id, scope="lesson"
                )
                if resolved_lesson:
                    await self._append_postprocess_event(
                        run_id, round_item, ClassroomEventType.REVISION_COMPLETED,
                        f"定稿，{resolved_lesson} 条整节课范围的教师指令已落实",
                        actor_id="system", actor_role="system",
                        metadata={
                            "version_id": next_lesson.id,
                            "resolved_lesson_directives": resolved_lesson,
                        },
                    )
                self._startup_status[run_id] = {
                    "run_id": run_id, "phase": "classroom_completed",
                    "message": f"{self._max_rounds[run_id]} 轮课堂演练已完成，V{next_lesson.version_number} 已定稿",
                    "round_id": round_item.id, "version_id": next_lesson.id,
                    "generated_chars": 0, "preview": "",
                    "slide_previews": [], "closed_slide_count": len(next_lesson.slides),
                    "target_slide_count": len(next_lesson.slides),
                    "generation_attempt": 0,
                    "generation_request_id": f"{run_id}:lesson:v1",
                }
                if workflow_service is not None:
                    final_output = (
                        f"# {next_lesson.title}\n\n"
                        f"最终 LessonVersion：V{next_lesson.version_number}\n\n"
                        f"课堂轮次：{round_item.round_number}\n\n"
                        f"督导综合评分：{report.overall_score}\n"
                    )
                    # 会话卡读的是 run.review.score(teaching_v1 遗留字段), 复盘页读的是
                    # supervisor_report.overall_score —— 过去两者不一致(实测 78 vs 85)。
                    # 定稿时把督导报告按前端约定字段写回, 让两处显示同一个分数。
                    review_payload = {
                        "score": report.overall_score,
                        "dimensions": {key: int(value) for key, value in (report.dimension_scores or {}).items()},
                        "strengths": list(report.strengths or []),
                        "weaknesses": list(report.critical_issues or []),
                        "suggestions": list(report.revision_priorities or []),
                        "next_focus": (report.observations or [""])[0] if report.observations else "",
                    }
                    await workflow_service.repository.update_run(
                        run_id, status="completed", current_node="finalize",
                        final_output=final_output, review=review_payload, error=None,
                    )
                return

            next_round = SimulationRound(
                run_id=run_id,
                round_number=round_item.round_number + 1,
                lesson_version_id=next_lesson.id,
                scenario_seed=round_item.scenario_seed,
            )
            await orchestrator.start_round(next_lesson, next_round, personas=orchestrator.personas)
            fresh_states = await active_revision.initialize_round_cognitive_states(
                run_id, next_round, orchestrator.personas, next_lesson.knowledge_points,
            )
            orchestrator.cognitive_states = {
                persona.student_id: [state for state in fresh_states if state.student_id == persona.student_id]
                for persona in orchestrator.personas
            }
            self._startup_status[run_id] = {
                "run_id": run_id, "phase": "classroom_running",
                "message": f"第 {next_round.round_number} / {self._max_rounds[run_id]} 轮课堂演练进行中",
                "round_id": next_round.id, "version_id": next_lesson.id,
                "generated_chars": 0, "preview": "",
                "slide_previews": [], "closed_slide_count": len(next_lesson.slides),
                "target_slide_count": len(next_lesson.slides),
                "generation_attempt": 0,
                "generation_request_id": f"{run_id}:lesson:v1",
            }
            self._tasks[run_id] = asyncio.create_task(
                orchestrator.run_round(next_round.id), name=f"classroom-{run_id}-r{next_round.round_number}",
            )

        orchestrator.on_slide_completed = on_slide
        orchestrator.on_round_completed = on_round

    @staticmethod
    def _build_personas(run_id: str, scenario_seed: str) -> list[StudentPersona]:
        return [
            StudentPersona(run_id=run_id, student_id="student:high", name="Student A", level="high", ability=.85, engagement=.8, confidence=.75, verbosity=.7, question_propensity=.6, answer_propensity=.8, misconception_profile={}, scenario_seed=scenario_seed),
            StudentPersona(run_id=run_id, student_id="student:medium", name="Student B", level="medium", ability=.65, engagement=.65, confidence=.55, verbosity=.55, question_propensity=.5, answer_propensity=.65, misconception_profile={}, scenario_seed=scenario_seed),
            StudentPersona(run_id=run_id, student_id="student:low", name="Student C", level="low", ability=.4, engagement=.5, confidence=.35, verbosity=.4, question_propensity=.35, answer_propensity=.45, misconception_profile={}, scenario_seed=scenario_seed),
        ]

    async def _append_postprocess_event(
        self,
        run_id: str,
        round_item: SimulationRound,
        event_type: ClassroomEventType,
        content: str,
        *,
        actor_id: str,
        actor_role: str,
        metadata: dict[str, Any],
    ) -> ClassroomEvent:
        state = await self.repository.get_classroom_state(round_item.id)
        event = ClassroomEvent(
            run_id=run_id, round_id=round_item.id, actor_id=actor_id,
            actor_role=actor_role, event_type=event_type, content=content,
            metadata=metadata, virtual_timestamp=state.virtual_elapsed_seconds if state else round_item.virtual_elapsed_seconds,
        )
        saved = await self.repository.append_classroom_event(event)
        await self.publish_event(saved)
        return saved

    def unregister_orchestrator(self, run_id: str) -> None:
        self._orchestrators.pop(run_id, None)

    def orchestrator_for(self, run_id: str) -> Any | None:
        return self._orchestrators.get(run_id)

    async def _apply_directive_patches(self, orchestrator: Any, directive: Any) -> list[dict[str, Any]]:
        """把「纠正」类介入变成补丁, 当场应用到下一版课件。

        补丁必须引用 observation(现有校验), 所以先生成一条「教师指令」来源的
        alignment observation 作为证据锚点, 再让模型产出最小补丁。
        """
        runtime = getattr(orchestrator, "_runs", {}).get(directive.round_id)
        if runtime is None:
            return []
        slide = next(
            (item for item in runtime.lesson.slides if item.slide_id == directive.slide_id),
            runtime.lesson.slides[runtime.state.current_slide_index]
            if runtime.state.current_slide_index < len(runtime.lesson.slides) else None,
        )
        if slide is None:
            return []
        observation = SupervisorObservation(
            round_id=directive.round_id,
            slide_id=slide.slide_id,
            event_ids=[directive.source_event_id],
            category="alignment",
            severity="major",
            issue=f"教师课堂纠正：{directive.content}",
            evidence=f"教师在第 {runtime.round.round_number} 轮课堂中下达了这条纠正指令。",
            recommendation=directive.content,
            analysis={"directive_id": directive.directive_id, "source": "teacher_directive"},
        )
        await self.repository.save_supervisor_observation(observation)
        try:
            patches = await self._generate_directive_patches(orchestrator, runtime, slide, directive, observation)
            if not patches:
                return []
            target = await self.revision_engine.apply_patches(runtime.lesson, runtime.round, patches)
        except Exception:
            logger.exception(
                "directive patch failed for run_id=%s directive_id=%s", directive.run_id, directive.directive_id
            )
            return []
        runtime.lesson = target
        return [
            {
                "patch_id": item.patch_id,
                "slide_id": item.slide_id,
                "field_path": item.field_path,
                "before": item.before,
                "after": item.after,
                "reason": item.reason,
                "status": "applied",
            }
            for item in patches
        ]

    async def _generate_directive_patches(
        self, orchestrator: Any, runtime: Any, slide: Any, directive: Any, observation: Any
    ) -> list[Any]:
        from .prompts import build_directive_patch_prompt

        context = {
            "slide": slide.model_dump(mode="json"),
            "teacher_directive": {"intent": directive.intent, "scope": directive.scope, "content": directive.content},
            "source_observation_id": observation.observation_id,
        }
        system, user = build_directive_patch_prompt(context)
        generator = self._revision_generator_for(orchestrator, runtime)
        if generator is None:
            return []
        raw = await generator(system, user)
        payload = _parse_patch_payload(raw)
        if not payload:
            return []
        patches: list[RevisionPatch] = []
        for item in payload:
            patches.append(RevisionPatch(
                run_id=runtime.round.run_id,
                source_version_id=runtime.lesson.id,
                source_round_id=runtime.round.id,
                target_type=str(item.get("target_type") or "slide"),
                slide_id=str(item.get("slide_id") or slide.slide_id),
                block_id=item.get("block_id"),
                field_path=str(item.get("field_path") or ""),
                before=item.get("before"),
                after=item.get("after"),
                reason=str(item.get("reason") or directive.content),
                source_observation_ids=[observation.observation_id],
                source_intervention_ids=[directive.directive_id],
            ))
        return patches

    def _revision_generator_for(self, orchestrator: Any, runtime: Any) -> Any | None:
        run_id = runtime.round.run_id
        runtime_service = self._agent_runtimes.get(run_id)
        if runtime_service is None:
            return None

        async def generate(system: str, user: str) -> Any:
            return await runtime_service.generate(
                runtime.round.run_id, runtime.round.round_number, "teacher", system, user
            )

        return generate

    async def control_round(self, run_id: str, round_id: str, operation: str):
        """Coordinate controls with the background runner for this run only."""
        orchestrator = self.orchestrator_for(run_id)
        if orchestrator is None:
            raise ValueError("classroom runtime is not active")
        if operation not in {"pause", "resume", "stop"}:
            raise ValueError(f"unsupported classroom operation: {operation}")
        state = await getattr(orchestrator, operation)(round_id)
        task = self._tasks.get(run_id)
        if operation in {"pause", "stop"} and task is not None and not task.done():
            # Pause/stop settles at the next complete Agent action/event
            # boundary. It never interrupts a streaming model response midway.
            try:
                await task
            except Exception:
                logger.exception("classroom runner failed while applying %s for run_id=%s", operation, run_id)
        if operation == "resume" and state.status == "active" and (task is None or task.done()):
            self._tasks[run_id] = asyncio.create_task(orchestrator.run_round(round_id), name=f"classroom-{run_id}")
        return state

    async def cancel_directive(self, run_id: str, directive_id: str) -> dict[str, Any]:
        """撤销一条未落实的教师指令。

        orchestrator 只在课堂活着时存在；课堂已结束的情况下也要允许撤销，
        否则一条说错的话会永远挂在复盘页的「生效中」。
        """
        orchestrator = self.orchestrator_for(run_id)
        if orchestrator is not None:
            directive = await orchestrator.cancel_directive(run_id, directive_id)
        else:
            directive = await self.repository.get_teacher_directive(directive_id)
            if directive is None or directive.run_id != run_id:
                raise KeyError("教师指令不存在")
            if directive.status != "active":
                raise ValueError("该指令已经落实或被覆盖，无需撤销")
            directive.status = "cancelled"
            directive.resolved_at = utc_now()
            await self.repository.save_teacher_directive(directive)
        return directive.model_dump(mode="json")

    async def intervene(
        self,
        run_id: str,
        round_id: str,
        content: str,
        *,
        intent: str = "question",
        scope: str = "round",
    ) -> dict[str, Any]:
        """Pause at an event boundary, persist user input, then ask Teacher.

        intent/scope 决定这条输入是「问一句」还是「约束后续」或「纠正内容」:
        - question: 只回答, 不产生约束也不产生补丁
        - require: 注入后续 agent 的 prompt, 督导会判定是否遵循
        - correct: 除约束外, 还生成 RevisionPatch 改到下一版课件
        """
        state = await self.control_round(run_id, round_id, "pause")
        if state.status != "paused":
            raise ValueError("only an active or paused classroom can be interrupted")
        orchestrator = self.orchestrator_for(run_id)
        if orchestrator is None:
            raise ValueError("classroom runtime is not active")
        user_event, teacher_event, state, directive = await orchestrator.intervene(
            round_id, content, intent=intent, scope=scope
        )
        patches: list[dict[str, Any]] = []
        if directive is not None and directive.intent == "correct":
            patches = await self._apply_directive_patches(orchestrator, directive)
        return {
            "user_event": user_event.model_dump(mode="json"),
            "teacher_event": teacher_event.model_dump(mode="json"),
            "state": state.model_dump(mode="json"),
            "directive": directive.model_dump(mode="json") if directive is not None else None,
            "patches": patches,
        }

    async def publish_event(self, event: ClassroomEvent) -> None:
        """Fan out a persisted ClassroomEvent through the existing run channel."""
        await self.event_hub.publish(RunEvent(
            run_id=event.run_id,
            event_type="classroom.event",
            node=str(getattr(event.event_type, "value", event.event_type)),
            message=event.content,
            payload={"classroom_event": event.model_dump(mode="json")},
        ))

    async def get_snapshot(self, run_id: str, round_id: str) -> dict[str, Any]:
        round_item = await self.repository.get_simulation_round(round_id)
        if round_item is None or round_item.run_id != run_id:
            raise LookupError("simulation round not found")
        lesson = await self.repository.get_lesson_version(round_item.lesson_version_id)
        if lesson is not None and lesson.run_id != run_id:
            raise LookupError("lesson version does not belong to run")
        state = await self.repository.get_classroom_state(round_id)
        events = await self.repository.list_classroom_events(run_id, round_id)
        personas = await self.repository.list_student_personas(run_id)
        cognitive_states = await self.repository.list_student_cognitive_states(round_id)
        return {
            "run_id": run_id,
            "round": round_item.model_dump(mode="json"),
            "lesson_version": lesson.model_dump(mode="json") if lesson else None,
            "state": state.model_dump(mode="json") if state else None,
            "events": [event.model_dump(mode="json") for event in events],
            "student_personas": [persona.model_dump(mode="json") for persona in personas],
            "student_cognitive_states": [item.model_dump(mode="json") for item in cognitive_states],
            "last_sequence": events[-1].sequence if events else 0,
        }

    async def reconstruct_context(self, run_id: str, round_id: str) -> dict[str, Any]:
        """Return the complete inputs required to rebuild a runtime after restart."""
        snapshot = await self.get_snapshot(run_id, round_id)
        snapshot["runtime_reconstruction"] = {
            "session_scope": f"{run_id}:r{snapshot['round']['round_number']}",
            "event_count": len(snapshot["events"]),
            "requires_new_runtime_sessions": True,
        }
        return snapshot
