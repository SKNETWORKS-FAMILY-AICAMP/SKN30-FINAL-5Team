import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


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
    # Firebase mints ID tokens against Google's clock. A server whose clock runs
    # even a second behind reads a fresh token's `iat` as being in the future and
    # rejects it as "used too early", which surfaces as an intermittent 401. The
    # SDK default is zero tolerance, so a small allowance is configured here.
    firebase_clock_skew_seconds: int = 60
    # Path to a service account key. When set, it is handed to the Firebase SDK
    # directly, so the credential no longer has to reach the process as an
    # exported environment variable. Left empty, the SDK falls back to
    # Application Default Credentials, which is what cloud deployments use.
    google_application_credentials: Path | None = None
    birthdate_encryption_key_base64: SecretStr | None = None
    birthdate_encryption_key_id: str = "local-v1"
    consent_policy_version: str | None = None
    # Narration은 선택 기능이다. 기본값은 비활성이며 결정적 템플릿만 사용한다.
    llm_enabled: bool = False
    llm_provider_code: Literal["NONE", "OPENAI"] = "NONE"
    llm_model_code: str = "gpt-5.1-mini"
    llm_api_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 3.0
    llm_max_output_tokens: int = 400
    openai_api_key: SecretStr | None = None
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

    @field_validator("google_application_credentials", mode="before")
    @classmethod
    def normalize_credentials_path(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("firebase_clock_skew_seconds")
    @classmethod
    def validate_firebase_clock_skew_seconds(cls, value: int) -> int:
        # The Firebase SDK accepts at most 60 seconds. A wider window would be
        # rejected at verification time rather than at startup.
        if not 0 <= value <= 60:
            raise ValueError("FIREBASE_CLOCK_SKEW_SECONDS must be within [0, 60]")
        return value

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_openai_api_key(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("llm_model_code")
    @classmethod
    def validate_llm_model_code(cls, value: str) -> str:
        normalized = value.strip()
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(normalized):
            raise ValueError("LLM_MODEL_CODE must be a machine reference without free text")
        return normalized

    @field_validator("llm_api_base_url")
    @classmethod
    def validate_llm_api_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("LLM_API_BASE_URL must use https")
        return normalized

    @field_validator("llm_timeout_seconds")
    @classmethod
    def validate_llm_timeout_seconds(cls, value: float) -> float:
        # 결정 생성은 동기 흐름이므로 narration이 응답 시간을 지배하지 못하게 상한을 둔다.
        if not 0 < value <= 10:
            raise ValueError("LLM_TIMEOUT_SECONDS must be within (0, 10]")
        return value

    @field_validator("llm_max_output_tokens")
    @classmethod
    def validate_llm_max_output_tokens(cls, value: int) -> int:
        if not 0 < value <= 2000:
            raise ValueError("LLM_MAX_OUTPUT_TOKENS must be within (0, 2000]")
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

    @model_validator(mode="after")
    def validate_llm_provider_credentials(self) -> Self:
        # 자격 증명이 없는 상태에서 활성화하면 조용히 실패하는 대신 기동을 막는다.
        if self.llm_enabled and self.llm_provider_code == "NONE":
            raise ValueError("LLM_ENABLED requires LLM_PROVIDER_CODE")
        if self.llm_enabled and self.llm_provider_code == "OPENAI" and self.openai_api_key is None:
            raise ValueError("LLM_PROVIDER_CODE=OPENAI requires OPENAI_API_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
