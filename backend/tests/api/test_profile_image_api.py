from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_current_user, get_db_session, get_profile_repository
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_profile_images import PNG, FakeRepository, FakeSession, FakeStorage


def test_profile_image_multipart_contract_uses_etag_and_presigned_url() -> None:
    storage = FakeStorage()
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
        profile_image_storage=storage,
    )
    repository, user_id = FakeRepository(), uuid4()
    upload_key, delete_key = uuid4(), uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, status_code=UserStatusCode.ACTIVE
    )
    app.dependency_overrides[get_profile_repository] = lambda: repository

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/me/profile-image",
            headers={"If-Match": '"1"', "Idempotency-Key": str(upload_key)},
            files={"file": ("profile.png", PNG, "image/png")},
        )
        deleted = client.delete(
            "/api/v1/me/profile-image",
            headers={"If-Match": '"2"', "Idempotency-Key": str(delete_key)},
        )

    assert uploaded.status_code == 200
    assert uploaded.json()["profile_image_url"].startswith("https://example.test/profile-images/")
    assert uploaded.json()["profile_version"] == 2
    assert deleted.status_code == 200
    assert deleted.json()["profile_image_url"] is None
    assert storage.objects == {}
