from fastapi import APIRouter, Request

from backend.model_settings.models import (
    ModelDiscoveryResult,
    ModelHistoryItem,
    ModelSettingsPublic,
    ModelSettingsUpdate,
    ModelTestResult,
)
from backend.model_settings.service import ModelSettingsService
from backend.workflows.llm import ModelClient


router = APIRouter(prefix="/api/settings/model", tags=["model-settings"])


def service(request: Request) -> ModelSettingsService:
    return request.app.state.model_settings_service


@router.get("", response_model=ModelSettingsPublic)
async def get_model_settings(request: Request) -> ModelSettingsPublic:
    return service(request).public()


@router.put("", response_model=ModelSettingsPublic)
async def update_model_settings(payload: ModelSettingsUpdate, request: Request) -> ModelSettingsPublic:
    config = await service(request).update(payload)
    request.app.state.workflow_service.replace_model(ModelClient(config))
    return service(request).public()


@router.get("/history", response_model=list[ModelHistoryItem])
async def get_model_history(request: Request) -> list[ModelHistoryItem]:
    return service(request).public_history()


@router.post("/discover", response_model=ModelDiscoveryResult)
async def discover_models(payload: ModelSettingsUpdate, request: Request) -> ModelDiscoveryResult:
    return await service(request).discover(payload)


@router.post("/test", response_model=ModelTestResult)
async def test_model_settings(payload: ModelSettingsUpdate, request: Request) -> ModelTestResult:
    return await service(request).test(payload)
