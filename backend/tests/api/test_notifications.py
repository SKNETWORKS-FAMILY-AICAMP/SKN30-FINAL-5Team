from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_notification_repository,
    get_workout_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_notification_service import (
    FakeNotificationRepository,
    FakeSession,
    FakeWorkoutRepository,
)


def test_notification_list_and_read_contract() -> None:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    repository = FakeNotificationRepository()
    repository.progress = None
    user_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id,
        status_code=UserStatusCode.ACTIVE,
        previous_last_active_at=datetime.now(UTC) - timedelta(days=3),
    )
    app.dependency_overrides[get_notification_repository] = lambda: repository
    app.dependency_overrides[get_workout_repository] = lambda: FakeWorkoutRepository()

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    with TestClient(app) as client:
        listed = client.get("/api/v1/notifications")
        notification_id = listed.json()["items"][0]["notification_id"]
        read = client.patch(f"/api/v1/notifications/{notification_id}/read")
        repeated_read = client.patch(f"/api/v1/notifications/{notification_id}/read")

    assert listed.status_code == 200
    assert listed.json()["unread_count"] == 2
    assert {item["type"] for item in listed.json()["items"]} == {
        "DAILY_REWARD",
        "KIKKI_RETURN",
    }
    assert read.status_code == 200
    assert read.json()["is_read"] is True
    assert repeated_read.status_code == 200
    assert repeated_read.json()["read_at"] == read.json()["read_at"]
