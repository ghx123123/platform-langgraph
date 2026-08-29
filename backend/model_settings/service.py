import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.core.config import Settings
from backend.model_settings.models import (
    ModelDiscoveryResult,
    ModelHistoryItem,
    ModelSettingsPublic,
    ModelSettingsUpdate,
    ModelTestResult,
    RuntimeModelConfig,
)
from backend.workflows.llm import ModelClient


class ModelSettingsService:
    MAX_HISTORY_ITEMS = 20
    MOCK_MODELS = ["deterministic-mock", "mock-teaching", "mock-fast"]
    # pi-ai catalog(0.82) 实际支持, 且桥 MODEL_ROUTES 认识的 dsh 模型。
    # 官网 /models 返回的模型若不在其中, 选择后 pi-ai 会报
    # "provider has no configured model" —— 探测时过滤掉。
    # 注意: bridge 启动时会自动给 pi-ai 目录注入 vision 模型(ensure_deepseek_vision_catalog),
    # 所以 vision-exp 也在可用列表内; 若 pi-ai 更新目录丢失注入, 桥会重新补上。
    PI_AI_DSH_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp", "minimax-m3", "minimax-m2.7"}

    def __init__(self, settings: Settings, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        defaults = {
            "provider": settings.llm_provider,
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "temperature": settings.llm_temperature,
            "timeout_seconds": settings.llm_timeout_seconds,
        }
        stored_history: object = []
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise ValueError("模型设置文件必须是 JSON 对象")
            stored_history = stored.pop("history", [])
            defaults.update(stored)
        self.config = RuntimeModelConfig.model_validate(defaults)
        self.history = self._load_history(stored_history)

    def public(self) -> ModelSettingsPublic:
        return ModelSettingsPublic(
            provider=self.config.provider,
            base_url=self.config.base_url,
            model=self.config.model,
            temperature=self.config.temperature,
            timeout_seconds=self.config.timeout_seconds,
            has_api_key=bool(self.config.api_key),
        )

    def public_history(self) -> list[ModelHistoryItem]:
        return list(self.history)

    @staticmethod
    def _load_history(value: object) -> list[ModelHistoryItem]:
        if not isinstance(value, list):
            return []
        history: list[ModelHistoryItem] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                history.append(ModelHistoryItem.model_validate(item))
            except ValueError:
                continue
        return history[: ModelSettingsService.MAX_HISTORY_ITEMS]

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        return value.strip().rstrip("/")

    def _merge(self, payload: ModelSettingsUpdate) -> RuntimeModelConfig:
        values = payload.model_dump()
        values["base_url"] = self._normalize_base_url(values["base_url"])
        same_endpoint = values["provider"] == self.config.provider and values["base_url"] == self._normalize_base_url(self.config.base_url)
        if not values["api_key"] and same_endpoint:
            values["api_key"] = self.config.api_key
        return RuntimeModelConfig.model_validate(values)

    def _record_history(self, config: RuntimeModelConfig) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        match = next(
            (
                item
                for item in self.history
                if item.provider == config.provider
                and item.base_url == config.base_url
                and item.model == config.model
            ),
            None,
        )
        if match:
            self.history.remove(match)
            match = match.model_copy(update={"has_api_key": bool(config.api_key), "last_used_at": now, "use_count": match.use_count + 1})
        else:
            match = ModelHistoryItem(
                provider=config.provider,
                base_url=config.base_url,
                model=config.model,
                has_api_key=bool(config.api_key),
                last_used_at=now,
            )
        self.history.insert(0, match)
        self.history = self.history[: self.MAX_HISTORY_ITEMS]

    async def _persist(self, config: RuntimeModelConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stored = config.model_dump()
        stored["history"] = [item.model_dump() for item in self.history]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.path)

    async def update(self, payload: ModelSettingsUpdate) -> RuntimeModelConfig:
        async with self._lock:
            config = self._merge(payload)
            self._record_history(config)
            await self._persist(config)
            self.config = config
            return config

    async def test(self, payload: ModelSettingsUpdate) -> ModelTestResult:
        config = self._merge(payload)
        client = ModelClient(config)
        started = time.perf_counter()
        response = await client.generate("你是模型连通性检测助手。", "只回复：连接成功")
        latency = int((time.perf_counter() - started) * 1000)
        return ModelTestResult(
            ok=bool(response.strip()),
            provider=client.provider,
            model=client.model_name,
            latency_ms=latency,
            message="模型连接正常" if response.strip() else "模型未返回内容",
        )

    @staticmethod
    def _models_url(base_url: str) -> str:
        normalized = ModelSettingsService._normalize_base_url(base_url)
        return normalized if normalized.lower().endswith("/models") else f"{normalized}/models"

    @staticmethod
    def _extract_model_ids(payload: object) -> list[str]:
        if isinstance(payload, dict):
            values = payload.get("data") or payload.get("models") or []
        elif isinstance(payload, list):
            values = payload
        else:
            values = []
        if not isinstance(values, list):
            return []
        models: list[str] = []
        for item in values:
            if isinstance(item, str):
                model_id = item.strip()
            elif isinstance(item, dict):
                model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
            else:
                model_id = ""
            if model_id and model_id not in models:
                models.append(model_id)
        return models

    @staticmethod
    def _connection_error(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "连接超时，请检查 URL、网络或超时时间设置"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"接口返回 HTTP {exc.response.status_code}，请检查 URL 或 API Key"
        if isinstance(exc, httpx.RequestError):
            return "无法连接接口，请检查 URL、网络或代理设置"
        return str(exc) or "模型接口连接失败"

    async def discover(self, payload: ModelSettingsUpdate) -> ModelDiscoveryResult:
        started = time.perf_counter()
        try:
            config = self._merge(payload)
        except ValueError as exc:
            return ModelDiscoveryResult(
                ok=False,
                provider=payload.provider,
                base_url=payload.base_url,
                latency_ms=0,
                message=str(exc),
            )

        if config.provider == "mock":
            return ModelDiscoveryResult(
                ok=True,
                provider=config.provider,
                base_url=config.base_url,
                models=list(self.MOCK_MODELS),
                latency_ms=0,
                message="本地演示模型列表已就绪",
            )

        if config.provider == "dsh":
            # dsh 也真实调官方 /models 探测: 给用户官网真实模型列表(而非离线照抄)。
            # 面板填的 api_key 由 ModelClient 传给桥, 这里模拟同样的 key + URL 请求官网。
            # 未填时按 endpoint 回退环境变量 key(DeepSeek/MiniMax 探测免填也能真实连上)。
            probe_key = config.api_key
            if not probe_key:
                probe_key = os.environ.get("DEEPSEEK_API_KEY", "") if "minimaxi" not in (config.base_url or "") else os.environ.get("MINIMAX_API_KEY", "")
            headers = {"Accept": "application/json"}
            if probe_key:
                headers["Authorization"] = f"Bearer {probe_key}"
            try:
                timeout = min(config.timeout_seconds, 15.0)
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(self._models_url(config.base_url), headers=headers)
                response.raise_for_status()
                models = self._extract_model_ids(response.json())
                latency = int((time.perf_counter() - started) * 1000)
                if not models:
                    # 官网无 /models 或无 key: 回退为桥已知的 dsh 模型(保证能用)
                    return ModelDiscoveryResult(
                        ok=True, provider=config.provider, base_url=config.base_url,
                        models=["deepseek-v4-flash", "minimax-m3", "minimax-m2.7"],
                        latency_ms=latency, message="接口未返回模型列表，已列出 dsh 默认可用模型",
                    )
                # 交集过滤: 官网可能返回 pi-ai 未收录的模型(如 vision-exp), 选了会跑不通;
                # 只展示 pi-ai 认识(且桥有路由)的模型, 避免"provider has no configured model"。
                known = [m for m in models if m in self.PI_AI_DSH_MODELS]
                skipped = len(models) - len(known)
                if not known:
                    return ModelDiscoveryResult(
                        ok=True, provider=config.provider, base_url=config.base_url,
                        models=["deepseek-v4-flash", "minimax-m3", "minimax-m2.7"],
                        latency_ms=latency, message="官网模型均为当前运行环境未收录，已列出可用模型",
                    )
                return ModelDiscoveryResult(
                    ok=True, provider=config.provider, base_url=config.base_url,
                    models=known, latency_ms=latency,
                    message=f"官网模型：{len(known)} 个可用",
                )
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
                # 官网不可达(无网/key 无效): 回退 dsh 预设, 说明原因
                return ModelDiscoveryResult(
                    ok=False, provider=config.provider, base_url=config.base_url,
                    models=["deepseek-v4-flash", "minimax-m3", "minimax-m2.7"],
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    message=self._connection_error(exc),
                )

        headers = {"Accept": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        try:
            # 发现模型不应长时间占用设置面板，最长等待 15 秒。
            timeout = min(config.timeout_seconds, 15.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(self._models_url(config.base_url), headers=headers)
            response.raise_for_status()
            models = self._extract_model_ids(response.json())
            latency = int((time.perf_counter() - started) * 1000)
            if not models:
                return ModelDiscoveryResult(
                    ok=False,
                    provider=config.provider,
                    base_url=config.base_url,
                    latency_ms=latency,
                    message="接口连接成功，但没有返回可用模型",
                )
            return ModelDiscoveryResult(
                ok=True,
                provider=config.provider,
                base_url=config.base_url,
                models=models,
                latency_ms=latency,
                message=f"已发现 {len(models)} 个模型",
            )
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            return ModelDiscoveryResult(
                ok=False,
                provider=config.provider,
                base_url=config.base_url,
                latency_ms=int((time.perf_counter() - started) * 1000),
                message=self._connection_error(exc),
            )
