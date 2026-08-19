from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_routine_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_routine_service import (
    FakeRoutineRepository,
    FakeSession,
)


def _client(repository: FakeRoutineRepository) -> tuple[TestClient, CurrentUser]:
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url="postgresql+psycopg://test:test@localhost/test",
        ),
        readiness_probe=lambda: None,
    )
    user = CurrentUser(user_id=uuid4(), status_code=UserStatusCode.ACTIVE)
    app.dependency_overrides[get_current_user] = lambda: user

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_routine_repository] = lambda: repository
    return TestClient(app), user


def test_create_and_get_current_routine_contract() -> None:
    repository = FakeRoutineRepository()
    client, _ = _client(repository)

    with client:
        created = client.post(
            "/api/v1/routines",
            json={"effective_from": "2026-08-14", "goal_code": "GENERAL_FITNESS"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        current = client.get("/api/v1/routines/current", params={"local_date": "2026-08-14"})

    assert created.status_code == 201
    assert current.status_code == 200
    assert current.json() == created.json()
    day = created.json()["days"][0]
    assert day["estimated_duration_seconds"] == day["requested_duration_minutes"] * 60
    assert [item["phase_code"] for item in day["items"]] == [
        "WARMUP",
        "MAIN",
        "COOLDOWN",
    ]


def test_current_routine_missing_uses_common_error_envelope() -> None:
    client, _ = _client(FakeRoutineRepository())

    with client:
        response = client.get(
            "/api/v1/routines/current", params={"local_date": date(2026, 8, 14).isoformat()}
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTINE_NOT_FOUND"
    assert response.json()["error"]["request_id"]


def test_same_idempotency_key_with_changed_payload_returns_conflict() -> None:
    client, _ = _client(FakeRoutineRepository())
    key = str(uuid4())
    with client:
        first = client.post(
            "/api/v1/routines",
            json={"effective_from": "2026-08-14", "goal_code": "GENERAL_FITNESS"},
            headers={"Idempotency-Key": key},
        )
        conflict = client.post(
            "/api/v1/routines",
            json={"effective_from": "2026-08-15", "goal_code": "GENERAL_FITNESS"},
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_missing_production_approved_catalog_fails_closed() -> None:
    repository = FakeRoutineRepository()
    repository.context = None  # type: ignore[assignment]
    client, _ = _client(repository)

    with client:
        response = client.post(
            "/api/v1/routines",
            json={"effective_from": "2026-08-14", "goal_code": "GENERAL_FITNESS"},
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "APPROVED_CATALOG_UNAVAILABLE"
