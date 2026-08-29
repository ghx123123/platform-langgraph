import asyncio
import json

import httpx

from backend.core.config import Settings
from backend.model_settings.models import ModelSettingsUpdate
from backend.model_settings.service import ModelSettingsService


def test_model_settings_masks_and_retains_api_key(tmp_path):
    path = tmp_path / "model_settings.json"
    settings = Settings(app_env="test", llm_provider="mock")
    service = ModelSettingsService(settings, path)
    first = ModelSettingsUpdate(
        provider="openai_compatible",
        base_url="https://models.example.test/v1",
        model="teaching-model",
        api_key="secret-value",
        temperature=0.3,
        timeout_seconds=45,
    )
    asyncio.run(service.update(first))
    public = service.public().model_dump()
    assert public["has_api_key"] is True
    assert "api_key" not in public
    assert "secret-value" not in json.dumps(public)

    second = first.model_copy(update={"model": "teaching-model-v2", "api_key": ""})
    asyncio.run(service.update(second))
    assert service.config.api_key == "secret-value"
    assert service.public().model == "teaching-model-v2"


def test_model_history_counts_reuse_without_storing_api_key(tmp_path):
    path = tmp_path / "model_settings.json"
    service = ModelSettingsService(Settings(app_env="test", llm_provider="mock"), path)
    payload = ModelSettingsUpdate(
        provider="openai_compatible",
        base_url="https://models.example.test/v1/",
        model="teaching-model",
        api_key="secret-value",
    )

    asyncio.run(service.update(payload))
    asyncio.run(service.update(payload.model_copy(update={"api_key": ""})))

    history = service.public_history()
    assert len(history) == 1
    assert history[0].use_count == 2
    assert history[0].has_api_key is True
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "api_key" not in stored["history"][0]
    assert "secret-value" not in json.dumps(stored["history"])


def test_model_settings_retains_key_when_saved_url_only_differs_by_trailing_slash(tmp_path):
    path = tmp_path / "model_settings.json"
    service = ModelSettingsService(Settings(app_env="test", llm_provider="mock"), path)
    first = ModelSettingsUpdate(
        provider="openai_compatible",
        base_url="https://models.example.test/v1/",
        model="teaching-model",
        api_key="secret-value",
    )
    asyncio.run(service.update(first))

    asyncio.run(service.update(first.model_copy(update={"base_url": "https://models.example.test/v1", "api_key": ""})))

    assert service.config.api_key == "secret-value"


def test_mock_model_discovery_returns_selectable_models(tmp_path):
    service = ModelSettingsService(Settings(app_env="test", llm_provider="mock"), tmp_path / "settings.json")
    payload = ModelSettingsUpdate(
        provider="mock",
        base_url="https://api.openai.com/v1",
        model="deterministic-mock",
    )

    result = asyncio.run(service.discover(payload))

    assert result.ok is True
    assert result.models == service.MOCK_MODELS


def test_openai_compatible_model_discovery_parses_models_response(tmp_path, monkeypatch):
    service = ModelSettingsService(Settings(app_env="test", llm_provider="mock"), tmp_path / "settings.json")
    payload = ModelSettingsUpdate(
        provider="openai_compatible",
        base_url="https://models.example.test/v1",
        model="teaching-model",
        api_key="secret-value",
    )
    requests: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": "model-a"}, {"id": "model-a"}, {"name": "model-b"}]}

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str]) -> FakeResponse:
            requests.append((url, headers))
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(service.discover(payload))

    assert result.ok is True
    assert result.models == ["model-a", "model-b"]
    assert requests == [("https://models.example.test/v1/models", {"Accept": "application/json", "Authorization": "Bearer secret-value"})]
