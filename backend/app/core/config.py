import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    firebase_project_id: str | None = None
    birthdate_encryption_key_base64: SecretStr | None = None
    birthdate_encryption_key_id: str = "local-v1"
    consent_policy_version: str | None = None
    # NoDecode hands the raw environment string to the validator below. Without
    # it pydantic-settings JSON-decodes these fields first, so a plain
    # comma-separated value fails at startup with an opaque SettingsError.
    onboarding_primary_goal_codes: Annotated[tuple[str, ...], NoDecode] = ()
    onboarding_experience_level_codes: Annotated[tuple[str, ...], NoDecode] = ()
    # Exact browser origins allowed to call the API. Empty disables CORS
    # entirely, which is the right default for the mobile app: native clients
    # do not send an Origin header and need no relaxation.
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()

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

    @field_validator("firebase_project_id", mode="before")
    @classmethod
    def normalize_firebase_project_id(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("consent_policy_version", mode="before")
    @classmethod
    def normalize_optional_version(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("birthdate_encryption_key_base64", mode="before")
    @classmethod
    def normalize_birthdate_key(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "onboarding_primary_goal_codes",
        "onboarding_experience_level_codes",
        "cors_allowed_origins",
        mode="before",
    )
    @classmethod
    def parse_code_tuple(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return ()
        # Accept a JSON array as well, so existing .env files keep working.
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("value must be a JSON array or a comma-separated list") from exc
            if not isinstance(decoded, list):
                raise ValueError("value must be a JSON array or a comma-separated list")
            return tuple(str(item).strip() for item in decoded if str(item).strip())
        return tuple(part.strip() for part in text.split(",") if part.strip())

    @field_validator("cors_allowed_origins")
    @classmethod
    def reject_wildcard_origin(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # A wildcard origin combined with credentialed requests would let any
        # site call the API with a user's bearer token, so it is never allowed.
        if any(origin.strip() == "*" for origin in value):
            raise ValueError("CORS_ALLOWED_ORIGINS must list exact origins, not '*'")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
