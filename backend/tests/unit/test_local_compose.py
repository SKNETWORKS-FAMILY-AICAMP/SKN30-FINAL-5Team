from pathlib import Path
from typing import Any

import yaml

COMPOSE_PATH = Path("infra/docker/compose.yaml")
ENV_EXAMPLE_PATH = Path("infra/docker/.env.example")
DOCKERFILE_PATH = Path("backend/Dockerfile")
BACKEND_IGNORE_PATH = Path("backend/.dockerignore")
DOCKERFILE_IGNORE_PATH = Path("backend/Dockerfile.dockerignore")
RUNBOOK_PATH = Path("infra/docker/README.md")


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _environment(service: dict[str, Any]) -> dict[str, str]:
    environment = service["environment"]
    assert isinstance(environment, dict)
    return {str(key): str(value) for key, value in environment.items()}


def test_compose_declares_only_the_approved_services_and_separate_volumes() -> None:
    compose = _compose()
    services = compose["services"]

    assert set(services) == {"api", "postgres", "qdrant"}
    assert services["postgres"]["image"] == "postgres:16"
    assert services["qdrant"]["image"] == (
        "qdrant/qdrant:v1.18.2@"
        "sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c"
    )
    assert set(compose["volumes"]) == {"postgres_data", "qdrant_data"}
    assert services["postgres"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert services["qdrant"]["volumes"] == ["qdrant_data:/qdrant/storage"]


def test_every_service_has_a_bounded_healthcheck_and_api_waits_for_postgres() -> None:
    services = _compose()["services"]

    assert all("healthcheck" in service for service in services.values())
    assert "health/ready" in " ".join(services["api"]["healthcheck"]["test"])
    assert "pg_isready" in " ".join(services["postgres"]["healthcheck"]["test"])
    assert "/readyz" in " ".join(services["qdrant"]["healthcheck"]["test"])
    assert services["api"]["depends_on"] == {"postgres": {"condition": "service_healthy"}}
    assert all(service["healthcheck"]["timeout"] == "5s" for service in services.values())


def test_api_defaults_preserve_legacy_and_disable_optional_production_paths() -> None:
    api_environment = _environment(_compose()["services"]["api"])

    assert api_environment["V3_EXECUTION_PROFILE"] == "LEGACY"
    for flag in (
        "LLM_ENABLED",
        "LLM_AGENTS_ENABLED",
        "V3_LANGGRAPH_ENABLED",
        "V3_SHADOW_EVALUATION_ENABLED",
        "V3_REGENERATION_ENABLED",
        "V3_PRODUCTION_PROMOTION_APPROVED",
        "QDRANT_ENABLED",
    ):
        assert api_environment[flag].lower() == "false"
    assert api_environment["EMBEDDING_PROVIDER_CODE"] == "UNCONFIGURED"
    assert api_environment["EMBEDDING_VECTOR_DIMENSION"] == "0"


def test_api_startup_does_not_hide_migration_import_or_activation() -> None:
    compose = _compose()
    command = " ".join(compose["services"]["api"]["command"]).lower()
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8").lower()

    assert "uvicorn backend.app.main:app" in command
    for forbidden in ("alembic", "catalog_promote", "catalog_activate", "docker compose"):
        assert forbidden not in command
        assert forbidden not in dockerfile

    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "alembic -c backend/alembic.ini upgrade head" in runbook
    assert "python -m backend.scripts.catalog_promote_v2" in runbook
    assert (
        "python -m backend.scripts.catalog_activate activate "
        "exercise-catalog-v2.0.1-final" in runbook
    )
    assert "exercise-catalog-v2.0.0-final" not in runbook


def test_demo_and_test_database_names_and_host_ports_are_separate() -> None:
    env_lines = {
        key: value
        for key, value in (
            line.split("=", 1)
            for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        )
    }
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert env_lines["POSTGRES_DB"].endswith("_demo")
    assert env_lines["POSTGRES_TEST_DB"].endswith("_test")
    assert env_lines["POSTGRES_DB"] != env_lines["POSTGRES_TEST_DB"]
    postgres_environment = _environment(_compose()["services"]["postgres"])
    assert "POSTGRES_TEST_DB" in postgres_environment
    for variable in ("API_PORT", "POSTGRES_PORT", "QDRANT_HTTP_PORT", "QDRANT_GRPC_PORT"):
        assert "${" + variable + ":-" in compose_text


def test_docker_build_is_non_root_and_context_excludes_sensitive_artifacts() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    backend_ignore = BACKEND_IGNORE_PATH.read_text(encoding="utf-8")
    build_ignore = DOCKERFILE_IGNORE_PATH.read_text(encoding="utf-8")

    assert "USER app" in dockerfile
    assert "USER root" not in dockerfile
    assert "--no-dev" in dockerfile
    assert "COPY ." not in dockerfile
    for pattern in (".env", ".git", "*.dump", "*.db", "__pycache__"):
        assert pattern in backend_ignore
        assert pattern in build_ignore


def test_compose_contains_no_external_credentials_or_provider_services() -> None:
    compose = _compose()
    serialized = yaml.safe_dump(compose).lower()

    for forbidden_service in ("redis", "celery", "kafka", "worker"):
        assert forbidden_service not in compose["services"]
    for secret_key in (
        "openai_api_key",
        "qdrant_api_key",
        "google_application_credentials",
        "firebase_project_id",
        "kakao_client_secret",
        "naver_client_secret",
    ):
        assert secret_key not in serialized
    assert "production" not in str(_environment(compose["services"]["api"])["APP_ENV"]).lower()
