from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from backend.app.core.config import Settings

COMPOSE_PATH = Path("infra/deployment/compose.staging.yaml")
CADDYFILE_PATH = Path("infra/deployment/Caddyfile")
ENV_EXAMPLE_PATH = Path("infra/deployment/.env.staging.example")
USER_DATA_PATH = Path("infra/aws/user-data.sh")


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _environment(service: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in service["environment"].items()}


def test_staging_compose_uses_aurora_and_keeps_internal_ports_private() -> None:
    compose = _compose()
    services = compose["services"]

    assert set(services) == {"api", "caddy", "qdrant"}
    assert "postgres" not in services
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert "ports" not in services["qdrant"]
    assert set(services["qdrant"]["expose"]) == {"6333", "6334"}
    assert services["qdrant"]["volumes"] == ["qdrant_data:/qdrant/storage"]


def test_qdrant_release_is_digest_pinned_and_ready_before_api_start() -> None:
    services = _compose()["services"]
    qdrant = services["qdrant"]

    assert qdrant["image"] == (
        "qdrant/qdrant:v1.18.2@"
        "sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c"
    )
    assert "GET /readyz HTTP/1.1" in " ".join(qdrant["healthcheck"]["test"])
    assert services["api"]["depends_on"]["qdrant"]["condition"] == "service_healthy"


def test_only_caddy_is_publicly_published() -> None:
    """The API port stays on loopback; 443 is the single public entry point."""
    services = _compose()["services"]

    assert services["caddy"]["ports"] == ["80:80", "443:443", "443:443/udp"]
    # Anything bound without an explicit 127.0.0.1 prefix reaches the internet
    # once the security group opens, so the API must never look like that.
    for name, service in services.items():
        if name == "caddy":
            continue
        for published in service.get("ports", []):
            assert str(published).startswith("127.0.0.1:"), (
                f"{name} publishes {published} beyond loopback"
            )


def test_caddy_persists_certificates_and_reverse_proxies_the_api() -> None:
    """Losing /data would re-request certificates and hit the ACME rate limit."""
    compose = _compose()
    caddy = compose["services"]["caddy"]
    caddyfile = CADDYFILE_PATH.read_text(encoding="utf-8")

    assert "caddy_data:/data" in caddy["volumes"]
    assert "./Caddyfile:/etc/caddy/Caddyfile:ro" in caddy["volumes"]
    assert {"caddy_data", "caddy_config"} <= set(compose["volumes"])
    assert caddy["depends_on"]["api"]["condition"] == "service_healthy"
    assert "reverse_proxy api:8000" in caddyfile
    # The domain and contact are supplied per deployment, never baked in.
    assert "{$API_DOMAIN}" in caddyfile
    assert "{$ACME_EMAIL}" in caddyfile


def test_tls_configuration_carries_no_literal_domain_or_secret() -> None:
    caddyfile = CADDYFILE_PATH.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert "API_DOMAIN=<" in env_example
    assert "ACME_EMAIL=<" in env_example
    assert ".rds.amazonaws.com" not in caddyfile
    assert "sk-" not in caddyfile
    # A wildcard origin plus a bearer token would let any site call the API.
    assert "CORS_ALLOWED_ORIGINS=*" not in env_example


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


def test_plaintext_compose_qdrant_cannot_be_enabled_in_staging() -> None:
    """Record the approval blocker instead of weakening the Settings gate."""
    environment = _environment(_compose()["services"]["api"])

    assert environment["QDRANT_URL"] == "http://qdrant:6333"
    assert environment["QDRANT_TLS_ENABLED"].lower() == "false"
    with pytest.raises(ValidationError, match="staging/production Qdrant requires TLS"):
        Settings(
            _env_file=None,
            app_env="staging",
            qdrant_enabled=True,
            qdrant_url=environment["QDRANT_URL"],
            qdrant_tls_enabled=False,
            qdrant_api_key="redacted-test-only-value",
            embedding_provider_code="APPROVED_PROVIDER",
            embedding_model_version="approved-model-v1",
            embedding_vector_dimension=4,
        )

    with pytest.raises(ValidationError, match="staging/production Qdrant requires QDRANT_API_KEY"):
        Settings(
            _env_file=None,
            app_env="staging",
            qdrant_enabled=True,
            qdrant_url="https://qdrant.example.invalid",
            qdrant_tls_enabled=True,
            embedding_provider_code="APPROVED_PROVIDER",
            embedding_model_version="approved-model-v1",
            embedding_vector_dimension=4,
        )


def test_staging_env_example_and_bootstrap_contain_no_secret_values() -> None:
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    user_data = USER_DATA_PATH.read_text(encoding="utf-8")

    assert "DATABASE_URL=<aws-secrets-manager-injected-postgresql-url>" in env_example
    assert "OPENAI_API_KEY" not in env_example
    assert "sk-" not in env_example
    assert "sk-" not in user_data
    assert "v2.40.3" in user_data
    assert "v0.36.1" in user_data
    assert "sha256sum --check" in user_data
