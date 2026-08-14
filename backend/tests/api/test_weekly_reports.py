from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_weekly_report_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_weekly_report_service import (
    FakeSession,
    FakeWeeklyReportRepository,
    _evidence,
)

LOCAL_TODAY = datetime.now(ZoneInfo("Asia/Seoul")).date()
CURRENT_WEEK_START = LOCAL_TODAY - timedelta(days=LOCAL_TODAY.weekday())
CLOSED_WEEK_START = CURRENT_WEEK_START - timedelta(days=7)


def _client(repository: FakeWeeklyReportRepository, user_id: UUID | None = None) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    current_user = CurrentUser(user_id=user_id or uuid4(), status_code=UserStatusCode.ACTIVE)
    app.dependency_overrides[get_current_user] = lambda: current_user

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_weekly_report_repository] = lambda: repository
    return TestClient(app)


def _headers(key: UUID | None = None) -> dict[str, str]:
    return {"Idempotency-Key": str(key or uuid4())}


def test_week_report_get_and_acknowledgement_contract() -> None:
    repository = FakeWeeklyReportRepository()
    repository.evidence = _evidence()
    with _client(repository) as client:
        week = client.get(f"/api/v1/weeks/{CLOSED_WEEK_START.isoformat()}")
        created = client.post(
            f"/api/v1/weeks/{CLOSED_WEEK_START.isoformat()}/report",
            headers=_headers(),
            json={"expected_week_status_code": "CLOSED"},
        )
        report_id = created.json()["report_id"]
        fetched = client.get(f"/api/v1/weekly-reports/{report_id}")
        acknowledged = client.post(
            f"/api/v1/weekly-reports/{report_id}/acknowledgement",
            headers=_headers(),
            json={"acknowledged_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat()},
        )

    assert week.status_code == 200
    assert week.json()["status_code"] == "CLOSED"
    assert week.json()["week_end"] == (CLOSED_WEEK_START + timedelta(days=6)).isoformat()
    assert created.status_code == 201
    assert created.json()["counts"]["completed"] == 1
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status_code"] == "ACKNOWLEDGED"
    assert acknowledged.json()["acknowledged_at"] is not None


def test_open_week_and_non_monday_use_contract_errors() -> None:
    with _client(FakeWeeklyReportRepository()) as client:
        open_report = client.post(
            f"/api/v1/weeks/{CURRENT_WEEK_START.isoformat()}/report",
            headers=_headers(),
            json={"expected_week_status_code": "CLOSED"},
        )
        invalid_week = client.get(
            f"/api/v1/weeks/{(CURRENT_WEEK_START + timedelta(days=1)).isoformat()}"
        )

    assert open_report.status_code == 409
    assert open_report.json()["error"]["code"] == "WEEK_NOT_CLOSED"
    assert invalid_week.status_code == 422
    assert invalid_week.json()["error"]["code"] == "INVALID_WEEK_START"


def test_report_creation_replays_same_idempotency_key() -> None:
    repository = FakeWeeklyReportRepository()
    key = uuid4()
    with _client(repository) as client:
        first = client.post(
            f"/api/v1/weeks/{CLOSED_WEEK_START.isoformat()}/report",
            headers=_headers(key),
            json={"expected_week_status_code": "CLOSED"},
        )
        retry = client.post(
            f"/api/v1/weeks/{CLOSED_WEEK_START.isoformat()}/report",
            headers=_headers(key),
            json={"expected_week_status_code": "CLOSED"},
        )
    assert retry.status_code == 201
    assert retry.json() == first.json()
    assert repository.created_report_count == 1
