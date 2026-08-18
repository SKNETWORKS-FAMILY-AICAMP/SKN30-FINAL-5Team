from typing import Annotated
from uuid import UUID

from fastapi import Query
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://test_user:test_password@localhost:5432/test_db",
    )


def test_liveness_does_not_call_database() -> None:
    def unexpected_probe() -> None:
        raise AssertionError("liveness must not call the database")

    with TestClient(create_app(settings=settings(), readiness_probe=unexpected_probe)) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status_code": "OK"}
    UUID(response.headers["X-Request-ID"])


def test_readiness_returns_success_when_database_is_ready() -> None:
    with TestClient(create_app(settings=settings(), readiness_probe=lambda: None)) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status_code": "READY"}
    UUID(response.headers["X-Request-ID"])


def test_readiness_uses_safe_common_error_when_database_fails() -> None:
    secret_url = "postgresql+psycopg://user:supersecret@db.internal:5432/app"

    def failing_probe() -> None:
        raise RuntimeError(secret_url)

    with TestClient(create_app(settings=settings(), readiness_probe=failing_probe)) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert payload["error"]["details"] == []
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]
    assert secret_url not in response.text
    assert "supersecret" not in response.text


def test_not_found_uses_common_error_envelope() -> None:
    with TestClient(create_app(settings=settings(), readiness_probe=lambda: None)) as client:
        response = client.get("/api/v1/unknown")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_validation_error_uses_safe_common_error_envelope() -> None:
    application = create_app(settings=settings(), readiness_probe=lambda: None)

    def validate(limit: Annotated[int, Query(gt=0)]) -> dict[str, int]:
        return {"limit": limit}

    application.add_api_route("/api/v1/test-validation", validate)
    with TestClient(application) as client:
        response = client.get("/api/v1/test-validation", params={"limit": "secret-value"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.json()["error"]["details"][0]["field"] == "query.limit"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert "secret-value" not in response.text


def test_unhandled_error_does_not_expose_exception_message() -> None:
    secret = "raw-health-record-must-not-leak"
    application = create_app(settings=settings(), readiness_probe=lambda: None)

    def fail() -> None:
        raise RuntimeError(secret)

    application.add_api_route("/api/v1/test-failure", fail)
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/test-failure")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert secret not in response.text


def test_cors_preflight_allows_a_configured_browser_origin() -> None:
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url="postgresql+psycopg://test:test@localhost/test",
            cors_allowed_origins="http://localhost:8081",
        ),
        readiness_probe=lambda: None,
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/me",
            headers={
                "Origin": "http://localhost:8081",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8081"


def test_cors_preflight_rejects_an_unlisted_origin() -> None:
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url="postgresql+psycopg://test:test@localhost/test",
            cors_allowed_origins="http://localhost:8081",
        ),
        readiness_probe=lambda: None,
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/me",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers


def test_no_cors_headers_when_origins_are_not_configured() -> None:
    app = create_app(
        # Passed explicitly: Settings() would otherwise inherit an ambient
        # CORS_ALLOWED_ORIGINS from the developer's shell.
        settings=Settings(
            app_env="test",
            database_url="postgresql+psycopg://test:test@localhost/test",
            cors_allowed_origins=(),
        ),
        readiness_probe=lambda: None,
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health/live",
            headers={"Origin": "http://localhost:8081"},
        )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
