from pathlib import Path
from typing import Any

import yaml

COMPOSE_PATH = Path("infra/deployment/compose.staging.yaml")
ENV_EXAMPLE_PATH = Path("infra/deployment/.env.staging.example")
USER_DATA_PATH = Path("infra/aws/user-data.sh")


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _environment(service: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in service["environment"].items()}


def test_staging_compose_uses_aurora_and_keeps_internal_ports_private() -> None:
    compose = _compose()
    services = compose["services"]

    assert set(services) == {"api", "qdrant"}
    assert "postgres" not in services
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert "ports" not in services["qdrant"]
    assert set(services["qdrant"]["expose"]) == {"6333", "6334"}
    assert services["qdrant"]["volumes"] == ["qdrant_data:/qdrant/storage"]


def test_staging_baseline_is_fail_closed_and_contains_no_provider_secret() -> None:
    api = _compose()["services"]["api"]
    environment = _environment(api)
    serialized = COMPOSE_PATH.read_text(encoding="utf-8").lower()

    assert environment["APP_ENV"] == "staging"
    assert environment["V3_EXECUTION_PROFILE"] == "LEGACY"
    for flag in (
        "LLM_ENABLED",
        "LLM_AGENTS_ENABLED",
        "V3_LANGGRAPH_ENABLED",
        "V3_SHADOW_EVALUATION_ENABLED",
        "V3_REGENERATION_ENABLED",
        "V3_PRODUCTION_PROMOTION_APPROVED",
        "QDRANT_ENABLED",
    ):
        assert environment[flag].lower() == "false"
    assert "openai_api_key" not in serialized
    assert "qdrant_api_key" not in serialized
    assert "database_url:" not in serialized


def test_staging_env_example_and_bootstrap_contain_no_secret_values() -> None:
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    user_data = USER_DATA_PATH.read_text(encoding="utf-8")

    assert "DATABASE_URL=<aws-secrets-manager-injected-postgresql-url>" in env_example
    assert "OPENAI_API_KEY" not in env_example
    assert "sk-" not in env_example
    assert "sk-" not in user_data
    assert "v2.40.3" in user_data
    assert "sha256sum --check" in user_data
