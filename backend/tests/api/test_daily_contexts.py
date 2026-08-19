from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_daily_context_repository,
    get_db_session,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_daily_context_service import (
    FakeDailyContextRepository,
    FakeSession,
)

LOCAL_DATE = date(2026, 8, 14)


def _payload(fatigue: str = "MODERATE") -> dict[str, object]:
    return {
        "fatigue_level_code": fatigue,
        "requested_duration_minutes": 40,
        "duration_adjustment_source_code": "USER_OVERRIDE",
        "location_code": "HOME",
        "sleep_minutes": None,
        "fasting_state_code": None,
        "hydration_state_code": None,
        "discomforts": [{"body_area_code": "KNEE", "severity_code": "MILD"}],
        "adverse_reaction_codes": [],
    }


def _client(repository: FakeDailyContextRepository) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    user = CurrentUser(user_id=uuid4(), status_code=UserStatusCode.ACTIVE)
    app.dependency_overrides[get_current_user] = lambda: user

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_daily_context_repository] = lambda: repository
    return TestClient(app)


def test_put_and_get_support_complete_manual_flow() -> None:
    client = _client(FakeDailyContextRepository())
    with client:
        created = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload(),
            headers={"Idempotency-Key": str(uuid4())},
        )
        fetched = client.get(f"/api/v1/daily-contexts/{LOCAL_DATE}")

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    assert created.json()["context_version"] == 1
    assert "date_of_birth" not in created.text
    assert "age" not in created.text


def test_if_match_updates_and_stale_version_returns_contract_error() -> None:
    client = _client(FakeDailyContextRepository())
    with client:
        client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload(),
            headers={"Idempotency-Key": str(uuid4())},
        )
        updated = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload("HIGH"),
            headers={"Idempotency-Key": str(uuid4()), "If-Match": '"1"'},
        )
        stale = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload("LOW"),
            headers={"Idempotency-Key": str(uuid4()), "If-Match": "1"},
        )

    assert updated.status_code == 200
    assert updated.json()["context_version"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_CONTEXT"


def test_idempotent_retry_and_reuse_conflict() -> None:
    client = _client(FakeDailyContextRepository())
    key = str(uuid4())
    with client:
        first = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload(),
            headers={"Idempotency-Key": key},
        )
        retry = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload(),
            headers={"Idempotency-Key": key},
        )
        conflict = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=_payload("HIGH"),
            headers={"Idempotency-Key": key, "If-Match": "1"},
        )
    assert retry.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_missing_context_and_invalid_duplicate_input_use_common_errors() -> None:
    client = _client(FakeDailyContextRepository())
    duplicate = _payload()
    duplicate["discomforts"] = [
        {"body_area_code": "KNEE", "severity_code": "MILD"},
        {"body_area_code": "KNEE", "severity_code": "MODERATE"},
    ]
    with client:
        missing = client.get(f"/api/v1/daily-contexts/{LOCAL_DATE}")
        invalid = client.put(
            f"/api/v1/daily-contexts/{LOCAL_DATE}",
            json=duplicate,
            headers={"Idempotency-Key": str(uuid4())},
        )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DAILY_CONTEXT_NOT_FOUND"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "DUPLICATE_BODY_AREA"
