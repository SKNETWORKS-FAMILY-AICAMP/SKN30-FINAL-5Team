from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "exercise-wellness-api"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://exercise_app:local_dev_only@localhost:5432/exercise_app"
    )
    catalog_manifest_paths: tuple[Path, ...] = ()

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if value != "/api/v1":
            raise ValueError("API_V1_PREFIX must remain /api/v1")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL is not supported")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
