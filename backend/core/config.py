from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    database_path: Path = Path("./backend/data/platform.db")
    checkpoint_path: Path = Path("./backend/data/checkpoints.db")
    model_settings_path: Path = Path("./backend/data/model_settings.json")
    document_store_path: Path = Path("./backend/data/tmp/documents")
    course_archive_store_path: Path = Path("./backend/data/course_archives")
    course_design_store_path: Path = Path("./backend/data/course_designs")
    material_unit_store_path: Path = Path("./backend/data/material_units")
    data_hub_store_path: Path = Path("./backend/data/data_hub")

    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=90, ge=5, le=600)
    # Semantic syllabus matching is an optional enhancement. Keep its request
    # budget independent from long-form generation so the planning UI can
    # always fall back to deterministic results promptly.
    syllabus_match_timeout_seconds: float = Field(default=15, ge=1, le=120)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_model_config(self) -> "Settings":
        if self.llm_provider == "openai_compatible" and not self.llm_api_key:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=openai_compatible")
        if self.app_env == "production" and any(origin == "*" for origin in self.cors_origins):
            raise ValueError("Wildcard CORS origins are not allowed in production")
        return self

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.document_store_path.mkdir(parents=True, exist_ok=True)
        self.course_archive_store_path.mkdir(parents=True, exist_ok=True)
        self.course_design_store_path.mkdir(parents=True, exist_ok=True)
        self.material_unit_store_path.mkdir(parents=True, exist_ok=True)
        self.data_hub_store_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
