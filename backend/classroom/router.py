"""Classroom Domain API (read/recovery/control boundary for Phase 6)."""
from __future__ import annotations

import asyncio
from html import escape
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response
import json
from pydantic import BaseModel, Field

from .integration import ClassroomIntegrationService
from .lesson_blueprint import BlueprintValidationError
from .lesson_review import LessonReviewService
from .models import ClassroomAgentInstance, LessonReviewMessage, LessonSlide
from .prompts import DEFAULT_SUPERVISOR_PROFILE

router = APIRouter(prefix="/api/classroom", tags=["classroom"])


@router.get('/runs/{run_id}/role-settings/{role}')
async def role_settings(run_id: str, role: str, request: Request):
    if role not in {'teacher', 'student:high', 'student:medium', 'student:low', 'supervisor'}:
        raise HTTPException(404, 'Unknown role')
    instance = await service(request).repository.get_agent_instance(run_id, role)
    config = instance.config if instance else {}
    default = DEFAULT_SUPERVISOR_PROFILE if role == 'supervisor' else {
        'role_definition': '按当前角色身份与课堂任务进行教学或学习。',
        'system_prompt': '遵循课堂目标、角色能力和当前可见上下文。', 'evaluation_focus': []}
    return {'profile': config.get('supervisor_profile' if role == 'supervisor' else 'role_profile', default),
            'versions': config.get('prompt_versions', [])}


@router.put('/runs/{run_id}/role-settings/{role}')
async def save_role_settings(run_id: str, role: str, request: Request, payload: dict):
    import uuid
    from .models import utc_now
    await role_settings(run_id, role, request)
    profile = SupervisorProfileRequest.model_validate(payload)
    if not profile.role_definition.strip() or not profile.system_prompt.strip():
        raise HTTPException(422, 'Role and prompt must not be blank')
    repo = service(request).repository
    instance = await repo.get_agent_instance(run_id, role)
    instance = instance or ClassroomAgentInstance(run_id=run_id, agent_key=role,
        role='student' if role.startswith('student:') else role, display_name=role)
    config = dict(instance.config)
    value = profile.model_dump()
    config['supervisor_profile' if role == 'supervisor' else 'role_profile'] = value
    config['prompt_versions'] = ([{'id': uuid.uuid4().hex, 'created_at': utc_now().isoformat(), **value}]
                                + config.get('prompt_versions', []))[:3]
    await repo.save_agent_instance(instance.model_copy(update={'config': config}))
    return await role_settings(run_id, role, request)


@router.delete('/runs/{run_id}/role-settings/{role}/versions/{version_id}')
async def delete_role_version(run_id: str, role: str, version_id: str, request: Request):
    await role_settings(run_id, role, request)
    repo = service(request).repository
    instance = await repo.get_agent_instance(run_id, role)
    if instance:
        config = dict(instance.config)
        config['prompt_versions'] = [v for v in config.get('prompt_versions', []) if v['id'] != version_id]
        await repo.save_agent_instance(instance.model_copy(update={'config': config}))
    return await role_settings(run_id, role, request)


@router.post('/runs/{run_id}/role-settings/{role}/generate')
async def generate_role_settings(run_id: str, role: str, request: Request, payload: dict):
    """Generate editable personality guidance only; orchestration contracts stay fixed."""
    if role not in {'teacher', 'student:high', 'student:medium', 'student:low', 'supervisor'}:
        raise HTTPException(404, 'Unknown role')
    requirement = str(payload.get('requirement') or '').strip()
    if not requirement:
        raise HTTPException(422, '请输入希望补充的性格或行为要求')
    workflow = getattr(request.app.state, 'workflow_service', None)
    if workflow is None or getattr(workflow.model, 'provider', None) != 'dsh':
        raise HTTPException(503, '当前模型运行时不可用')
    labels = {'teacher': '教师', 'student:high': '拓展型学生', 'student:medium': '进阶型学生', 'student:low': '基础型学生', 'supervisor': '督导'}
    system = ('你是教学平台的角色提示词设计助手。只生成角色性格、表达习惯、教学/学习倾向、'
              '边界和可观察行为，不修改编排接口、状态机、动作枚举、发言权限、轮次限制或 JSON 协议。'
              '输出 JSON：role_definition、system_prompt、evaluation_focus。')
    if len(requirement) > 4000:
        raise HTTPException(422, '补充要求不能超过 4000 字')
    current = SupervisorProfileRequest.model_validate(payload.get('profile') or {
        'role_definition': labels[role], 'system_prompt': '保持现有角色职责。'})
    user = (f'角色：{labels[role]}\n用户补充要求：{requirement}\n'
            f'当前配置：{json.dumps(current.model_dump(), ensure_ascii=False)}\n'
            '保留未要求改变的内容和评价维度，按性格、表达习惯、面对困难的反应、与他人交流方式分段细化，'
            '约 600–1200 字。不改变学生能力基线或预先编造课堂对话。')
    try:
        raw = await asyncio.wait_for(workflow.model.ensure_dsh_engine().generate(system, user), timeout=90)
        import re
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(raw).strip(), flags=re.I)
        data = json.loads(text[text.find('{'):text.rfind('}') + 1])
        result = SupervisorProfileRequest.model_validate(data)
        if len(result.role_definition.strip()) < 50 or len(result.system_prompt.strip()) < 180:
            repair_user = user + '\n上一次结果过短。请重新输出不少于600字的详细角色提示词，必须分段包含性格、表达方式、行为策略、边界和至少6条可观察行为。只输出JSON。'
            raw = await asyncio.wait_for(workflow.model.ensure_dsh_engine().generate(system, repair_user), timeout=90)
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(raw).strip(), flags=re.I)
            data = json.loads(text[text.find('{'):text.rfind('}') + 1])
            result = SupervisorProfileRequest.model_validate(data)
        if len(result.role_definition.strip()) < 50 or len(result.system_prompt.strip()) < 180:
            # Provider models can occasionally return a terse valid object. Keep
            # the user's request and add a deterministic, role-specific scaffold
            # instead of saving an unusably short prompt.
            scaffold = {
                'teacher': '性格：耐心、清晰、关注学生反应。表达：先给结论，再用例子解释。行为：围绕当前目标讲解；发现错误先指出正确部分，再追问误区，最后给出纠正和小结。边界：不切换页面、不结束课堂、不修改学生身份。',
                'student:high': '性格：主动、善于迁移但保持学生身份。表达：可以联系旧知识，但说明推理依据。行为：遇到真正的概念边界才提问；回答后接受教师追问；不替教师总结课堂。',
                'student:medium': '性格：有基础但理解不稳定。表达：回答中等长度，不能确定时明确说不确定。行为：关注概念边界和应用条件；可以部分正确；根据教师反馈修正理解；不使用专家口吻。',
                'student:low': '性格：谨慎、基础薄弱。表达：使用简单语言，允许沉默、错误和部分正确。行为：术语不理解时表达困惑；只有真实疑问才主动提问；接受教师提示后再尝试回答。',
                'supervisor': '性格：冷静、客观、证据导向。表达：结论先行，逐条引用 Slide、Block 和 ClassroomEvent。行为：比较 PPT、讲稿和实际讲解；分析学生回答及教师反馈；指出误区和可执行修改。边界：旁听，不参与课堂，不改变流程。',
            }[role]
            result.role_definition = (result.role_definition.strip() + '\n\n' + scaffold).strip()
            result.system_prompt = (result.system_prompt.strip() + '\n\n' + scaffold + '\n\n用户补充要求：' + requirement).strip()
        result.evaluation_focus = current.evaluation_focus
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(502, f'提示词生成失败：{str(exc)[:300]}') from exc


class ClassroomInterventionRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    # 意图: 提问只回答; 纠正改内容(生成补丁); 要求改形式(约束后续行为)
    intent: Literal["question", "correct", "require"] = "question"
    # 范围: 本页 / 本轮剩余 / 整节课
    scope: Literal["slide", "round", "lesson"] = "round"


class LessonDraftUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    learning_objectives: list[str] | None = None
    knowledge_points: list[str] | None = None
    estimated_minutes: int = Field(ge=1, le=600)
    slides: list[LessonSlide] = Field(min_length=1, max_length=120)


class LessonSlideRevisionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class SupervisorProfileRequest(BaseModel):
    role_definition: str = Field(min_length=1, max_length=4000)
    system_prompt: str = Field(min_length=1, max_length=8000)
    evaluation_focus: list[str] = Field(default_factory=list, max_length=12)


def service(request: Request) -> ClassroomIntegrationService:
    value = getattr(request.app.state, "classroom_service", None)
    if value is None:
        raise HTTPException(status_code=503, detail="classroom service is not initialized")
    return value


async def _round_or_404(svc: ClassroomIntegrationService, run_id: str, round_id: str):
    item = await svc.repository.get_simulation_round(round_id)
    if item is None or item.run_id != run_id:
        raise HTTPException(status_code=404, detail="Simulation round not found")
    return item


@router.get("/runs/{run_id}/lesson-versions")
async def list_lesson_versions(run_id: str, request: Request) -> dict:
    return {"items": [item.model_dump(mode="json") for item in await service(request).repository.list_lesson_versions(run_id)]}


def _supervisor_profile_response(run_id: str, instance: ClassroomAgentInstance | None) -> dict:
    configured = instance.config.get("supervisor_profile") if instance and isinstance(instance.config, dict) else None
    profile = dict(DEFAULT_SUPERVISOR_PROFILE)
    if isinstance(configured, dict):
        profile.update(configured)
    return {
        "run_id": run_id,
        "agent_key": "supervisor",
        "role_definition": str(profile.get("role_definition", "")),
        "system_prompt": str(profile.get("system_prompt", "")),
        "evaluation_focus": [str(item) for item in profile.get("evaluation_focus", [])],
        "persisted": bool(configured),
        "updated_at": instance.created_at.isoformat() if instance else None,
    }


@router.get("/runs/{run_id}/agent-configs/supervisor")
async def get_supervisor_profile(run_id: str, request: Request) -> dict:
    instance = await service(request).repository.get_agent_instance(run_id, "supervisor")
    return _supervisor_profile_response(run_id, instance)


@router.put("/runs/{run_id}/agent-configs/supervisor")
async def update_supervisor_profile(run_id: str, payload: SupervisorProfileRequest, request: Request) -> dict:
    repo = service(request).repository
    instance = await repo.get_agent_instance(run_id, "supervisor")
    config = dict(instance.config) if instance and isinstance(instance.config, dict) else {}
    config["supervisor_profile"] = {
        "role_definition": payload.role_definition.strip(),
        "system_prompt": payload.system_prompt.strip(),
        "evaluation_focus": [item.strip() for item in payload.evaluation_focus if item.strip()],
    }
    saved = await repo.save_agent_instance(
        instance.model_copy(update={"config": config})
        if instance
        else ClassroomAgentInstance(
            run_id=run_id,
            agent_key="supervisor",
            role="supervisor",
            display_name="Supervisor Agent",
            config=config,
        )
    )
    return _supervisor_profile_response(run_id, saved)


@router.post("/runs/{run_id}/prepare", status_code=202)
async def prepare_lesson(
    run_id: str,
    request: Request,
    retry: bool = Query(default=False, description="true 时清除失败态并重新生成 Lesson Blueprint"),
    max_slides: int | None = Query(default=None, ge=1, le=200, description="本次重试的页数上限（用于降级重试）"),
) -> dict:
    workflow = getattr(request.app.state, "workflow_service", None)
    if workflow is None:
        raise HTTPException(status_code=503, detail="workflow service is not initialized")
    try:
        return await service(request).begin_preparation(
            run_id, workflow_service=workflow, retry=retry, max_slides=max_slides
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/start", status_code=202)
async def start_classroom(run_id: str, request: Request, max_rounds: int | None = Query(default=None, ge=1, le=10)) -> dict:
    """Explicit classroom_v2 product entry point."""
    svc = service(request)
    workflow = getattr(request.app.state, "workflow_service", None)
    if workflow is None:
        raise HTTPException(status_code=503, detail="workflow service is not initialized")
    try:
        return await svc.begin_run(run_id, workflow_service=workflow, max_rounds=max_rounds)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BlueprintValidationError as exc:
        # A provider returning invalid structured output is actionable input,
        # not an opaque platform crash. Keep the message concise and localised.
        raise HTTPException(status_code=422, detail=f"Lesson Blueprint 结构校验失败：{exc}") from exc


@router.get("/runs/{run_id}/start-status")
async def classroom_start_status(run_id: str, request: Request) -> dict:
    return await service(request).resolved_start_status(run_id)


@router.get("/runs/{run_id}/lesson-versions/{version_id}")
async def get_lesson_version(run_id: str, version_id: str, request: Request) -> dict:
    item = await service(request).repository.get_lesson_version(version_id)
    if item is None or item.run_id != run_id:
        raise HTTPException(status_code=404, detail="Lesson version not found")
    return item.model_dump(mode="json")


@router.get("/runs/{run_id}/lesson-versions/{version_id}/export")
async def export_lesson_version(run_id: str, version_id: str, request: Request, format: str = Query(default="json", pattern="^(json|md|html)$")) -> Response:
    item = await service(request).repository.get_lesson_version(version_id)
    if item is None or item.run_id != run_id:
        raise HTTPException(status_code=404, detail="Lesson version not found")
    if format == "json":
        return Response(content=json.dumps(item.model_dump(mode="json"), ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="lesson-v{item.version_number}.json"'})
    if format == "html":
        return Response(content=_lesson_html(item), media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="lesson-v{item.version_number}.html"'})
    sections = [f"# {item.title}\n", f"\n## 学习目标\n" + "\n".join(f"- {x}" for x in item.learning_objectives)]
    for slide in item.slides:
        sections.append(f"\n## Slide {slide.order}: {slide.title}\n\n{slide.purpose}\n")
        sections.append("\n".join(f"- {x}" for x in slide.ppt_content.bullets))
        sections.append("\n### Speaker Notes\n" + "\n\n".join(block.content for block in slide.speaker_notes))
    return Response(content="\n".join(sections), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="lesson-v{item.version_number}.md"'})


@router.put("/runs/{run_id}/lesson-versions/{version_id}")
async def update_lesson_draft(run_id: str, version_id: str, payload: LessonDraftUpdateRequest, request: Request) -> dict:
    repo = service(request).repository
    current = await repo.get_lesson_version(version_id)
    if current is None or current.run_id != run_id:
        raise HTTPException(status_code=404, detail="Lesson version not found")
    candidate = current.model_copy(update={
        "learning_objectives": payload.learning_objectives or current.learning_objectives,
        "knowledge_points": payload.knowledge_points or current.knowledge_points,
    })
    reviewer = LessonReviewService(repo)
    try:
        updated = await reviewer.replace_draft(candidate, payload.slides, title=payload.title, estimated_minutes=payload.estimated_minutes)
    except (ValueError, BlueprintValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return updated.model_dump(mode="json")


@router.get("/runs/{run_id}/lesson-versions/{version_id}/review-messages")
async def lesson_review_messages(run_id: str, version_id: str, request: Request) -> dict:
    item = await service(request).repository.get_lesson_version(version_id)
    if item is None or item.run_id != run_id:
        raise HTTPException(status_code=404, detail="Lesson version not found")
    messages = await service(request).repository.list_lesson_review_messages(run_id, version_id)
    return {"items": [message.model_dump(mode="json") for message in messages]}


@router.post("/runs/{run_id}/lesson-versions/{version_id}/slides/{slide_id}/revise")
async def revise_lesson_slide(run_id: str, version_id: str, slide_id: str, payload: LessonSlideRevisionRequest, request: Request) -> dict:
    repo = service(request).repository
    current = await repo.get_lesson_version(version_id)
    if current is None or current.run_id != run_id:
        raise HTTPException(status_code=404, detail="Lesson version not found")
    workflow = getattr(request.app.state, "workflow_service", None)
    if workflow is None:
        raise HTTPException(status_code=503, detail="workflow service is not initialized")
    try:
        updated, message = await LessonReviewService(repo).revise_slide(current, slide_id, payload.instruction, workflow)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, BlueprintValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"lesson_version": updated.model_dump(mode="json"), "message": message.model_dump(mode="json")}


@router.post("/runs/{run_id}/lesson-versions/{version_id}/approve")
async def approve_lesson_version(
    run_id: str,
    version_id: str,
    request: Request,
    max_rounds: int | None = Query(default=None, ge=1, le=10),
    auto_start: bool = Query(default=True, description="false 时只确认 PPT 并停在审阅门，不自动进入课堂"),
) -> dict:
    svc = service(request)
    lesson = await svc.repository.get_lesson_version(version_id)
    if lesson is None or lesson.run_id != run_id:
        raise HTTPException(status_code=404, detail="Lesson version not found")
    if lesson.status not in {"draft", "ready"}:
        raise HTTPException(status_code=409, detail="lesson version has already entered simulation")
    try:
        LessonReviewService(svc.repository).validate_for_approval(lesson)
        if lesson.status == "draft":
            await svc.repository.update_lesson_version_status(version_id, "ready")
            await svc.repository.append_lesson_review_message(LessonReviewMessage(
                run_id=run_id, version_id=version_id, role="system", content="教师已确认 PPT，课堂演练开始。",
            ))
        if not auto_start:
            # 「教学设计后暂停」勾选时: 只确认 PPT, 停在审阅门等教师主动开始课堂
            return {"approved": True, "awaiting_start": True, "lesson_version": lesson.model_dump(mode="json")}
        workflow = getattr(request.app.state, "workflow_service", None)
        if workflow is None:
            raise RuntimeError("workflow service is not initialized")
        await workflow.repository.update_run(run_id, status="running")
        return await svc.start_run(run_id, workflow_service=workflow, max_rounds=max_rounds, version_id=version_id)
    except (ValueError, BlueprintValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs/{run_id}/rounds")
async def list_rounds(run_id: str, request: Request) -> dict:
    return {"items": [item.model_dump(mode="json") for item in await service(request).repository.list_simulation_rounds(run_id)]}


@router.get("/runs/{run_id}/rounds/{round_id}/state")
async def get_state(run_id: str, round_id: str, request: Request) -> dict:
    await _round_or_404(service(request), run_id, round_id)
    state = await service(request).repository.get_classroom_state(round_id)
    return state.model_dump(mode="json") if state else {"run_id": run_id, "round_id": round_id, "state": None}


@router.get("/runs/{run_id}/rounds/{round_id}/events")
async def get_classroom_events(run_id: str, round_id: str, request: Request, after: int = Query(default=0, ge=0)) -> dict:
    await _round_or_404(service(request), run_id, round_id)
    events = await service(request).repository.list_classroom_events(run_id, round_id, after)
    return {"items": [event.model_dump(mode="json") for event in events], "last_sequence": events[-1].sequence if events else after}


@router.get("/runs/{run_id}/rounds/{round_id}/snapshot")
async def get_snapshot(run_id: str, round_id: str, request: Request) -> dict:
    try:
        return await service(request).get_snapshot(run_id, round_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/rounds/{round_id}/reconstruction")
async def reconstruct(run_id: str, round_id: str, request: Request) -> dict:
    try:
        return await service(request).reconstruct_context(run_id, round_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/rounds/{round_id}/observations")
async def observations(run_id: str, round_id: str, request: Request) -> dict:
    await _round_or_404(service(request), run_id, round_id)
    items = await service(request).repository.list_supervisor_observations(round_id)
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.get("/runs/{run_id}/rounds/{round_id}/report")
async def report(run_id: str, round_id: str, request: Request) -> dict:
    await _round_or_404(service(request), run_id, round_id)
    item = await service(request).repository.get_supervisor_report(round_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Supervisor report not found")
    if item.run_id != run_id:
        raise HTTPException(status_code=404, detail="Supervisor report not found")
    return item.model_dump(mode="json")


@router.get("/runs/{run_id}/revision-patches")
async def revision_patches(run_id: str, request: Request, source_round_id: str | None = None) -> dict:
    items = await service(request).repository.list_revision_patches(run_id, source_round_id)
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.get("/runs/{run_id}/directives")
async def teacher_directives(run_id: str, request: Request, round_id: str | None = None) -> dict:
    """本轮教师指令: 复盘页据此展示「说了什么 / 是否被遵守 / 改了哪些地方」。"""
    items = await service(request).repository.list_teacher_directives(run_id, round_id=round_id)
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.delete("/runs/{run_id}/directives/{directive_id}")
async def cancel_teacher_directive(run_id: str, directive_id: str, request: Request) -> dict:
    """撤销一条生效中的教师指令。

    指令只在 slide/round/lesson 边界自动落实；教师说错了或课堂不再需要这条约束时，
    必须能主动撤销，否则它会在本轮剩余的所有 Agent 调用里持续生效。
    """
    try:
        directive = await service(request).cancel_directive(run_id, directive_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"directive": directive}


async def _control(run_id: str, round_id: str, request: Request, operation: str) -> dict:
    svc = service(request)
    await _round_or_404(svc, run_id, round_id)
    if svc.orchestrator_for(run_id) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="classroom runtime is not active")
    try:
        state = await svc.control_round(run_id, round_id, operation)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return state.model_dump(mode="json")


@router.post("/runs/{run_id}/rounds/{round_id}/pause")
async def pause(run_id: str, round_id: str, request: Request) -> dict:
    return await _control(run_id, round_id, request, "pause")


@router.post("/runs/{run_id}/rounds/{round_id}/resume")
async def resume(run_id: str, round_id: str, request: Request) -> dict:
    return await _control(run_id, round_id, request, "resume")


@router.post("/runs/{run_id}/rounds/{round_id}/stop")
async def stop(run_id: str, round_id: str, request: Request) -> dict:
    return await _control(run_id, round_id, request, "stop")


@router.post("/runs/{run_id}/rounds/{round_id}/interventions")
async def intervene(run_id: str, round_id: str, payload: ClassroomInterventionRequest, request: Request) -> dict:
    svc = service(request)
    await _round_or_404(svc, run_id, round_id)
    if svc.orchestrator_for(run_id) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="classroom runtime is not active")
    try:
        return await svc.intervene(run_id, round_id, payload.content, intent=payload.intent, scope=payload.scope)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.websocket("/runs/{run_id}/events/ws")
async def classroom_events_ws(websocket: WebSocket, run_id: str) -> None:
    """Replay classroom history, then stream incremental events via EventHub."""
    svc = getattr(websocket.app.state, "classroom_service", None)
    if svc is None:
        await websocket.close(code=1013, reason="classroom service unavailable")
        return
    await websocket.accept()
    queue = await svc.event_hub.subscribe(run_id)
    last_sequence = 0
    try:
        history = await svc.repository.list_classroom_events(run_id)
        for event in history:
            last_sequence = max(last_sequence, event.sequence)
            await websocket.send_json({"type": "classroom.event", "classroom_event": event.model_dump(mode="json")})
        while True:
            try:
                envelope = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "run_id": run_id, "last_sequence": last_sequence})
                continue
            if envelope.event_type != "classroom.event":
                continue
            payload = envelope.payload.get("classroom_event", {})
            sequence = int(payload.get("sequence", 0))
            if sequence <= last_sequence:
                continue
            last_sequence = sequence
            await websocket.send_json({"type": "classroom.event", "classroom_event": payload})
    except WebSocketDisconnect:
        pass
    finally:
        await svc.event_hub.unsubscribe(run_id, queue)


def _lesson_html(item) -> str:
    slides = []
    for index, slide in enumerate(item.slides):
        bullets = "".join(f"<li>{escape(text)}</li>" for text in slide.ppt_content.bullets)
        examples = "".join(f"<aside>{escape(text)}</aside>" for text in slide.ppt_content.examples)
        slides.append(
            f'<section class="slide{" active" if index == 0 else ""}">'
            f'<small>PPT V{item.version_number}</small><h1>{escape(slide.ppt_content.title or slide.title)}</h1>'
            f'<p class="subtitle">{escape(slide.ppt_content.subtitle)}</p><ul>{bullets}</ul>{examples}'
            f'<footer>{escape(item.title)}<span>{index + 1} / {len(item.slides)}</span></footer></section>'
        )
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lesson PPT</title><style>
*{box-sizing:border-box}body{margin:0;background:#17243a;color:#17243a;font-family:"Microsoft YaHei",sans-serif;overflow:hidden}.slide{display:none;position:relative;width:100vw;height:100vh;padding:8vh 9vw;background:#fbfcfd;border-left:1.2vw solid #276d9a}.slide.active{display:block}.slide small{color:#276d9a;font-weight:800}h1{max-width:82%;margin:2vh 0;font-size:4vw}.subtitle{color:#65758a;font-size:1.6vw}ul{display:grid;gap:2vh;width:72%;margin:5vh 0;padding-left:2vw;font-size:2vw}aside{margin-top:3vh;padding:2vw;background:#fff3d9;border-left:.5vw solid #d68b24;font-size:1.35vw}footer{position:absolute;left:9vw;right:7vw;bottom:5vh;display:flex;justify-content:space-between;color:#748196}.controls{position:fixed;right:20px;bottom:18px;display:flex;gap:8px}.controls button{width:48px;height:44px;border:1px solid #8fa4b9;border-radius:5px;background:#fff;font-size:20px;cursor:pointer}@media print{body{overflow:visible}.slide,.slide.active{display:block;page-break-after:always}.controls{display:none}}</style></head><body>""" + "".join(slides) + """<nav class="controls"><button id="prev" aria-label="上一页">&#8592;</button><button id="next" aria-label="下一页">&#8594;</button></nav><script>const s=[...document.querySelectorAll('.slide')];let i=0;function show(n){i=Math.max(0,Math.min(s.length-1,n));s.forEach((e,j)=>e.classList.toggle('active',i===j))}prev.onclick=()=>show(i-1);next.onclick=()=>show(i+1);addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(i-1);if(e.key==='ArrowRight'||e.key===' ')show(i+1)});</script></body></html>"""
