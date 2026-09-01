import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Windows: 强制 ProactorEventLoop —— asyncio.create_subprocess_exec 只有 Proactor loop 支持，
# 否则 dsh 引擎 spawn 桥子进程时抛 NotImplementedError。uvicorn 在 win+reload 会强制 Selector，
# 所以提供自定义 loop setup 传给 uvicorn.loop，确保无论 reload 与否都用 Proactor。
def _proactor_loop_setup(use_subprocess: bool = False) -> None:
    import asyncio as _aio

    if sys.platform == "win32":
        _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
        _aio.get_event_loop_policy().new_event_loop()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from starlette.middleware.gzip import GZipMiddleware

from backend.core.config import get_settings
from backend.core.errors import AppError
from backend.core.middleware import RequestContextMiddleware
from backend.course_archives.router import router as course_archive_router
from backend.course_designs.router import router as course_design_router
from backend.documents.router import router as document_router
from backend.data_hub.router import router as data_hub_router
from backend.model_settings.router import router as model_settings_router
from backend.material_units.router import router as material_unit_router
from backend.material_units.graph_router import router as material_unit_graph_router
from backend.model_settings.service import ModelSettingsService
from backend.workflows.events import EventHub
from backend.workflows.repository import WorkflowRepository
from backend.workflows.router import router as workflow_router
from backend.workflows.service import WorkflowService
from backend.workflows.llm import ModelClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("multi_agent_platform")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    repository = WorkflowRepository(settings.database_path)
    await repository.initialize()
    event_hub = EventHub()
    model_settings_service = ModelSettingsService(settings, settings.model_settings_path)
    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path)) as checkpointer:
        await checkpointer.setup()
        service = WorkflowService(ModelClient(model_settings_service.config), repository, event_hub, checkpointer)
        app.state.workflow_service = service
        app.state.model_settings_service = model_settings_service
        logger.info("Workflow platform started with provider=%s model=%s", service.model.provider, service.model.model_name)
        yield
        await service.shutdown()


app = FastAPI(
    title="LangGraph 多智能体课程教学设计平台",
    description="教师、分层学生与教学督导协作完成课程内容剖析、教学实施和迭代评价。",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
app.include_router(workflow_router)
app.include_router(document_router)
app.include_router(course_archive_router)
app.include_router(course_design_router)
app.include_router(data_hub_router)
app.include_router(model_settings_router)
app.include_router(material_unit_router)
app.include_router(material_unit_graph_router)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "title": exc.code,
            "status": exc.status_code,
            "detail": exc.message,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for item in exc.errors():
        sanitized = {key: value for key, value in item.items() if key not in {"input", "ctx"}}
        errors.append(sanitized)
    return JSONResponse(
        status_code=422,
        content={
            "title": "VALIDATION_ERROR",
            "status": 422,
            "detail": "Request validation failed",
            "errors": errors,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled application error", extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={
            "title": "INTERNAL_ERROR",
            "status": 500,
            "detail": "An unexpected server error occurred",
            "request_id": request_id,
        },
    )


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "multi-agent-platform", "version": "2.0.0"}


@app.get("/ready", tags=["system"])
async def ready(request: Request) -> dict[str, str]:
    service: WorkflowService = request.app.state.workflow_service
    await service.repository.list_runs(limit=1)
    return {"status": "ok", "database": "ready", "checkpointer": "ready"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.app_env == "development",
        loop=_proactor_loop_setup,
    )
