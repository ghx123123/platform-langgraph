import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response

from backend.core.errors import NotFoundError
from backend.workflows.catalog import list_templates
from backend.workflows.models import (
    ContinueRequest,
    CreateRunRequest,
    EventListResponse,
    ResumeRequest,
    RunListResponse,
    RunRecord,
    TeacherDraftResponse,
    TeacherDraftUpdate,
    TeacherDraftVersionList,
    TeacherSectionGenerationRequest,
    TeacherSectionGenerationResponse,
    WorkflowTemplate,
)
from backend.workflows.report import build_markdown, build_pdf, build_teacher_draft_pdf, report_filename
from backend.workflows.service import WorkflowService


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def get_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


@router.get("/templates", response_model=list[WorkflowTemplate])
async def templates() -> list[WorkflowTemplate]:
    return list_templates()


@router.get("/runs", response_model=RunListResponse)
async def runs(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> RunListResponse:
    service = get_service(request)
    return RunListResponse(items=await service.repository.list_runs(limit))


@router.post("/runs", response_model=RunRecord, status_code=status.HTTP_202_ACCEPTED)
async def create_run(payload: CreateRunRequest, request: Request) -> RunRecord:
    return await get_service(request).create_run(payload)


@router.get("/runs/{run_id}", response_model=RunRecord)
async def get_run(run_id: str, request: Request) -> RunRecord:
    return await get_service(request).get_run(run_id)


@router.get("/runs/{run_id}/events", response_model=EventListResponse)
async def get_events(run_id: str, request: Request, after: int = Query(default=0, ge=0)) -> EventListResponse:
    service = get_service(request)
    await service.get_run(run_id)
    return EventListResponse(items=await service.repository.list_events(run_id, after))


@router.post("/runs/{run_id}/cancel", response_model=RunRecord)
async def cancel_run(run_id: str, request: Request) -> RunRecord:
    return await get_service(request).cancel_run(run_id)


@router.post("/runs/{run_id}/resume", response_model=RunRecord)
async def resume_run(run_id: str, payload: ResumeRequest, request: Request) -> RunRecord:
    return await get_service(request).resume_run(run_id, payload)


@router.post("/runs/{run_id}/continue", response_model=RunRecord, status_code=status.HTTP_202_ACCEPTED)
async def continue_run(run_id: str, payload: ContinueRequest, request: Request) -> RunRecord:
    return await get_service(request).continue_run(run_id, payload)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: str, request: Request) -> Response:
    await get_service(request).delete_run(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs/{run_id}/teacher-draft", response_model=TeacherDraftResponse)
async def get_teacher_draft(run_id: str, request: Request) -> TeacherDraftResponse:
    return await get_service(request).get_teacher_draft(run_id)


@router.put("/runs/{run_id}/teacher-draft", response_model=TeacherDraftResponse)
async def save_teacher_draft(
    run_id: str, payload: TeacherDraftUpdate, request: Request
) -> TeacherDraftResponse:
    return await get_service(request).save_teacher_draft(run_id, payload)


@router.get("/runs/{run_id}/teacher-draft/versions", response_model=TeacherDraftVersionList)
async def list_teacher_draft_versions(
    run_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
) -> TeacherDraftVersionList:
    return await get_service(request).list_teacher_draft_versions(run_id, limit)


@router.post(
    "/runs/{run_id}/teacher-draft/generations",
    response_model=TeacherSectionGenerationResponse,
)
async def generate_teacher_section(
    run_id: str,
    payload: TeacherSectionGenerationRequest,
    request: Request,
) -> TeacherSectionGenerationResponse:
    return await get_service(request).generate_teacher_section(run_id, payload)


def _attachment_headers(filename: str) -> dict[str, str]:
    # 中文文件名需 RFC 5987 编码，同时保留 ASCII 回退供旧客户端使用
    ascii_fallback = filename.encode("ascii", "ignore").decode() or "teaching-report"
    return {"Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"}


@router.get("/runs/{run_id}/report.md")
async def export_markdown(
    run_id: str, request: Request,
    variant: str = Query(default="teacher", pattern="^(teacher|student)$"),
) -> Response:
    run = await get_service(request).get_run(run_id)
    student = variant == "student"
    draft = None if student else await get_service(request).repository.get_teacher_draft(run_id)
    content = draft.content if draft else build_markdown(run, student=student)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers=_attachment_headers(report_filename(run, "md", student)),
    )


@router.get("/runs/{run_id}/report.pdf")
async def export_pdf(
    run_id: str, request: Request,
    variant: str = Query(default="teacher", pattern="^(teacher|student)$"),
) -> Response:
    run = await get_service(request).get_run(run_id)
    student = variant == "student"
    draft = None if student else await get_service(request).repository.get_teacher_draft(run_id)
    pdf = await asyncio.to_thread(
        build_teacher_draft_pdf if draft else build_pdf,
        run,
        draft.content if draft else student,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers=_attachment_headers(report_filename(run, "pdf", student)),
    )


@router.websocket("/runs/{run_id}/events/ws")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    service: WorkflowService = websocket.app.state.workflow_service
    try:
        run = await service.get_run(run_id)
    except NotFoundError:
        await websocket.close(code=4404, reason="Run not found")
        return

    await websocket.accept()
    queue = await service.event_hub.subscribe(run_id)
    try:
        history = await service.repository.list_events(run_id)
        last_sequence = 0
        for event in history:
            last_sequence = event.sequence
            await websocket.send_json(event.model_dump(mode="json"))
        terminal = {"completed", "failed", "cancelled"}
        if run.status in terminal:
            await websocket.send_json({"type": "stream.closed", "status": run.status})
            await websocket.close(code=1000)
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                latest = await service.get_run(run_id)
                await websocket.send_json({"type": "heartbeat", "status": latest.status})
                if latest.status in terminal:
                    await websocket.close(code=1000)
                    return
                continue
            if event.sequence <= last_sequence:
                continue
            last_sequence = event.sequence
            await websocket.send_json(event.model_dump(mode="json"))
            if event.event_type in {"run.completed", "run.failed", "run.cancelled"}:
                await websocket.close(code=1000)
                return
    except WebSocketDisconnect:
        pass
    finally:
        await service.event_hub.unsubscribe(run_id, queue)
