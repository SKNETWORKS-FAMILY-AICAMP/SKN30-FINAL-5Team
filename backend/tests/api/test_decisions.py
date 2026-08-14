from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_current_user, get_db_session, get_decision_repository
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_decision_service import FakeRepository, FakeSession, _context


def _client(repository: FakeRepository, user_id: object) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, status_code=UserStatusCode.ACTIVE
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_decision_repository] = lambda: repository
    return TestClient(app)


def test_post_and_get_decision_contract() -> None:
    context = _context()
    repository = FakeRepository(context)
    user_id = uuid4()
    client = _client(repository, user_id)
    with client:
        created = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": context.context_version,
            },
        )
        fetched = client.get(f"/api/v1/decisions/{created.json()['decision_id']}")
    assert created.status_code == 201
    assert fetched.status_code == 200
    assert created.json()["final_plan"]["estimated_duration_seconds"] == 600
    assert "date_of_birth" not in created.text
    assert "age" not in created.json()


def test_post_decision_rejects_stale_context() -> None:
    context = _context()
    client = _client(FakeRepository(context), uuid4())
    with client:
        response = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": 1,
            },
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_CONTEXT"
