from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_routine_repository,
    get_weekly_plan_repository,
    get_weekly_report_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_weekly_plan_service import (
    FakeRoutineRepository,
    FakeWeeklyPlanRepository,
    _fixture,
)
from backend.tests.unit.test_weekly_report_service import (
    FakeSession,
    FakeWeeklyReportRepository,
)

LOCAL_TODAY = datetime.now(ZoneInfo("Asia/Seoul")).date()
OPEN_WEEK_START = LOCAL_TODAY - timedelta(days=LOCAL_TODAY.weekday())


def _client(
    plan_repository: FakeWeeklyPlanRepository,
    routine_repository: FakeRoutineRepository,
    user_id: UUID,
) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    current_user = CurrentUser(user_id=user_id, status_code=UserStatusCode.ACTIVE)
    app.dependency_overrides[get_current_user] = lambda: current_user

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_weekly_plan_repository] = lambda: plan_repository
    app.dependency_overrides[get_routine_repository] = lambda: routine_repository
    app.dependency_overrides[get_weekly_report_repository] = FakeWeeklyReportRepository
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def test_initial_ai_user_and_ai_limit_api_contract() -> None:
    _, repository, _, user_id, routine_id = _fixture()
    repository.context = replace(
        repository.context,
        week_start=OPEN_WEEK_START,
        week_end=OPEN_WEEK_START + timedelta(days=6),
    )
    routine_repository = FakeRoutineRepository(routine_id)
    with _client(repository, routine_repository, user_id) as client:
        initial = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan",
            headers=_headers(),
            json={},
        )
        ai_one = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan-revisions",
            headers=_headers(),
            json={"source_code": "AI", "expected_revision_sequence": 1},
        )
        user = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan-revisions",
            headers=_headers(),
            json={
                "source_code": "USER",
                "expected_revision_sequence": 2,
                "user_edits": {"routine_id": str(routine_id), "location_code": "HOME"},
            },
        )
        ai_two = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan-revisions",
            headers=_headers(),
            json={"source_code": "AI", "expected_revision_sequence": 3},
        )
        limited = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan-revisions",
            headers=_headers(),
            json={"source_code": "AI", "expected_revision_sequence": 4},
        )

    assert initial.status_code == 201
    assert initial.json()["source_code"] == "INITIAL"
    assert initial.json()["finalized"] is True
    assert ai_one.status_code == 201 and ai_one.json()["ai_revision_count"] == 1
    assert user.status_code == 201 and user.json()["ai_revision_count"] == 1
    assert ai_two.status_code == 201 and ai_two.json()["ai_revision_count"] == 2
    assert limited.status_code == 409
    assert limited.json()["error"]["code"] == "AI_REVISION_LIMIT_REACHED"


def test_user_location_constraint_and_source_payload_are_enforced() -> None:
    _, repository, _, user_id, routine_id = _fixture()
    repository.context = replace(
        repository.context,
        week_start=OPEN_WEEK_START,
        week_end=OPEN_WEEK_START + timedelta(days=6),
    )
    with _client(repository, FakeRoutineRepository(routine_id), user_id) as client:
        client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan",
            headers=_headers(),
            json={},
        )
        invalid_location = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan-revisions",
            headers=_headers(),
            json={
                "source_code": "USER",
                "expected_revision_sequence": 1,
                "user_edits": {"routine_id": str(routine_id), "location_code": "GYM"},
            },
        )
        invalid_ai_payload = client.post(
            f"/api/v1/weeks/{OPEN_WEEK_START.isoformat()}/plan-revisions",
            headers=_headers(),
            json={
                "source_code": "AI",
                "expected_revision_sequence": 1,
                "user_edits": {"routine_id": str(routine_id), "location_code": "HOME"},
            },
        )

    assert invalid_location.status_code == 422
    assert invalid_location.json()["error"]["code"] == "PLAN_REVISION_REJECTED"
    assert invalid_location.json()["error"]["details"] == [
        {"reason_code": "LOCATION_CONSTRAINT_NOT_SATISFIED"}
    ]
    assert invalid_ai_payload.status_code == 400
    assert invalid_ai_payload.json()["error"]["code"] == "INVALID_REQUEST"
