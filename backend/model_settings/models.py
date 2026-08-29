from typing import Literal

from pydantic import BaseModel, Field, model_validator

Provider = Literal["mock", "openai_compatible", "dsh"]


class RuntimeModelConfig(BaseModel):
    provider: Provider = "mock"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    api_key: str = ""
    temperature: float = Field(default=0.2, ge=0, le=2)
    timeout_seconds: float = Field(default=90, ge=5, le=600)

    @model_validator(mode="after")
    def validate_provider(self) -> "RuntimeModelConfig":
        if self.provider == "openai_compatible" and not self.api_key:
            raise ValueError("使用 OpenAI 兼容模型时必须配置 API Key")
        if self.provider == "dsh" and (self.model in {"", "gpt-4.1-mini"} or self.model.startswith("mock")):
            raise ValueError("dsh 引擎必须指定可用的智能体模型（如 minimax-m3）")
        return self


class ModelSettingsPublic(BaseModel):
    provider: Provider
    base_url: str
    model: str
    temperature: float
    timeout_seconds: float
    has_api_key: bool


class ModelHistoryItem(BaseModel):
    provider: Provider
    base_url: str
    model: str
    has_api_key: bool = False
    last_used_at: str
    use_count: int = Field(default=1, ge=1)


class ModelSettingsUpdate(BaseModel):
    provider: Provider
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(default="", max_length=1000)
    temperature: float = Field(default=0.2, ge=0, le=2)
    timeout_seconds: float = Field(default=90, ge=5, le=600)


class ModelTestResult(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int
    message: str


class ModelDiscoveryResult(BaseModel):
    ok: bool
    provider: str
    base_url: str
    models: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    message: str
