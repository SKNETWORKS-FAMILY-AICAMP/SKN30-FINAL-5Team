import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_QDRANT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


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
    llm_model_code: str = "gpt-5.6-terra"
    llm_api_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 3.0
    llm_max_output_tokens: int = 400
    openai_api_key: SecretStr | None = None
    # V3 structured agents are independent from the optional narration provider.
    # A provider-specific BaseChatModel is injected only after deployment approval.
    llm_agents_enabled: bool = False
    llm_agents_provider_code: str = "UNCONFIGURED"
    llm_agents_model_code: str = "unconfigured"
    llm_agents_timeout_seconds: float = 5.0
    llm_agents_max_attempts: int = 2
    llm_agents_max_output_tokens: int = 1200
    llm_agents_approved_model_codes: Annotated[tuple[str, ...], NoDecode] = ()
    # V3 graph construction is separately gated so incomplete provider/domain
    # wiring cannot alter the existing V1/V2 production decision path.
    v3_langgraph_enabled: bool = False
    # Offline/staging synthetic evaluation is deliberately independent from the
    # public regeneration mutation. A CLI opt-in is still required at runtime.
    v3_shadow_evaluation_enabled: bool = False
    # Manual V3 regeneration has its own server-side activation gate. Provider
    # credentials and V3_LANGGRAPH_ENABLED never opt users into this mutation.
    v3_regeneration_enabled: bool = False
    # Server-owned application composition profile. Existing V3 flags remain
    # available during migration, but never change the default LEGACY path.
    v3_execution_profile: Literal["LEGACY", "SHADOW", "DEMO", "PRODUCTION"] = "LEGACY"
    # This is only the final deployment composition input. It must be set from
    # the separately reviewed promotion record; the evaluator never edits it.
    v3_production_promotion_approved: bool = False
    # Qdrant is a rebuildable catalog index and remains disabled until an
    # embedding contract and deployment credentials are explicitly approved.
    qdrant_enabled: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_timeout_seconds: float = 2.0
    qdrant_collection_prefix: str = "exercise_catalog"
    qdrant_collection_alias: str = "exercise_catalog_active"
    qdrant_tls_enabled: bool = False
    qdrant_batch_size: int = 64
    embedding_provider_code: str = "UNCONFIGURED"
    embedding_model_version: str = "unconfigured"
    embedding_input_schema_version: str = "exercise-embedding-input-v2"
    embedding_vector_dimension: int = 0
    embedding_distance_metric_code: Literal["COSINE", "DOT", "EUCLID", "MANHATTAN"] = "COSINE"
    embedding_timeout_seconds: float = 30.0
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

    @field_validator("qdrant_api_key", mode="before")
    @classmethod
    def normalize_qdrant_api_key(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("qdrant_url")
    @classmethod
    def validate_qdrant_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("QDRANT_URL must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("QDRANT_URL must not contain credentials")
        return normalized

    @field_validator("qdrant_timeout_seconds")
    @classmethod
    def validate_qdrant_timeout_seconds(cls, value: float) -> float:
        if not 0 < value <= 10:
            raise ValueError("QDRANT_TIMEOUT_SECONDS must be within (0, 10]")
        return value

    @field_validator("qdrant_batch_size")
    @classmethod
    def validate_qdrant_batch_size(cls, value: int) -> int:
        if not 0 < value <= 1000:
            raise ValueError("QDRANT_BATCH_SIZE must be within [1, 1000]")
        return value

    @field_validator("embedding_vector_dimension")
    @classmethod
    def validate_embedding_vector_dimension(cls, value: int) -> int:
        if not 0 <= value <= 65536:
            raise ValueError("EMBEDDING_VECTOR_DIMENSION must be within [0, 65536]")
        return value

    @field_validator("embedding_timeout_seconds")
    @classmethod
    def validate_embedding_timeout_seconds(cls, value: float) -> float:
        if not 0 < value <= 120:
            raise ValueError("EMBEDDING_TIMEOUT_SECONDS must be within (0, 120]")
        return value

    @field_validator("qdrant_collection_prefix", "qdrant_collection_alias")
    @classmethod
    def validate_qdrant_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _QDRANT_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("Qdrant collection prefix and alias must be allowlisted names")
        return normalized

    @field_validator(
        "embedding_provider_code",
        "embedding_model_version",
        "embedding_input_schema_version",
    )
    @classmethod
    def validate_qdrant_machine_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(normalized):
            raise ValueError("Qdrant and embedding references must be machine codes")
        return normalized

    @field_validator("llm_model_code")
    @classmethod
    def validate_llm_model_code(cls, value: str) -> str:
        normalized = value.strip()
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(normalized):
            raise ValueError("LLM_MODEL_CODE must be a machine reference without free text")
        return normalized

    @field_validator("llm_agents_provider_code", "llm_agents_model_code")
    @classmethod
    def validate_llm_agent_machine_references(cls, value: str) -> str:
        normalized = value.strip()
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(normalized):
            raise ValueError("LLM agent provider and model must be machine references")
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

    @field_validator("llm_agents_timeout_seconds")
    @classmethod
    def validate_llm_agents_timeout_seconds(cls, value: float) -> float:
        if not 0 < value <= 30:
            raise ValueError("LLM_AGENTS_TIMEOUT_SECONDS must be within (0, 30]")
        return value

    @field_validator("llm_agents_max_attempts")
    @classmethod
    def validate_llm_agents_max_attempts(cls, value: int) -> int:
        if value not in {1, 2}:
            raise ValueError("LLM_AGENTS_MAX_ATTEMPTS must be one or two")
        return value

    @field_validator("llm_agents_max_output_tokens")
    @classmethod
    def validate_llm_agents_max_output_tokens(cls, value: int) -> int:
        if not 0 < value <= 4000:
            raise ValueError("LLM_AGENTS_MAX_OUTPUT_TOKENS must be within (0, 4000]")
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
        "llm_agents_approved_model_codes",
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

    @field_validator("llm_agents_approved_model_codes")
    @classmethod
    def validate_approved_agent_models(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("LLM_AGENTS_APPROVED_MODEL_CODES must be unique and sorted")
        if any(not _MACHINE_REFERENCE_PATTERN.fullmatch(item) for item in normalized):
            raise ValueError("approved LLM agent models must be machine references")
        return normalized

    @model_validator(mode="after")
    def validate_llm_provider_credentials(self) -> Self:
        # 자격 증명이 없는 상태에서 활성화하면 조용히 실패하는 대신 기동을 막는다.
        if self.llm_enabled and self.llm_provider_code == "NONE":
            raise ValueError("LLM_ENABLED requires LLM_PROVIDER_CODE")
        if self.llm_enabled and self.llm_provider_code == "OPENAI" and self.openai_api_key is None:
            raise ValueError("LLM_PROVIDER_CODE=OPENAI requires OPENAI_API_KEY")
        if self.qdrant_enabled:
            if (
                self.embedding_provider_code == "UNCONFIGURED"
                or self.embedding_vector_dimension <= 0
            ):
                raise ValueError("QDRANT_ENABLED requires an approved embedding contract")
            if self.qdrant_tls_enabled != self.qdrant_url.startswith("https://"):
                raise ValueError("QDRANT_TLS_ENABLED must agree with QDRANT_URL")
            if self.app_env in {"staging", "production"} and self.qdrant_api_key is None:
                raise ValueError("staging/production Qdrant requires QDRANT_API_KEY")
            if self.app_env in {"staging", "production"} and not self.qdrant_tls_enabled:
                raise ValueError("staging/production Qdrant requires TLS")
        if self.v3_execution_profile == "DEMO" and self.app_env != "staging":
            raise ValueError("V3_EXECUTION_PROFILE=DEMO is allowed only when APP_ENV=staging")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
