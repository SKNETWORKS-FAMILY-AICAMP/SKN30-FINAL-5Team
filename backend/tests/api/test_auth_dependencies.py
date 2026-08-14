from contextlib import nullcontext
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_deletion_lifecycle_user,
    get_identity_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.ports import (
    FirebaseVerifierUnavailableError,
    IdentityUserRecord,
    InvalidFirebaseTokenError,
    VerifiedFirebaseIdentity,
)
from backend.app.modules.identity.service import CurrentUser


class FakeSession:
    def begin(self) -> nullcontext[None]:
        return nullcontext()


class FailingSession:
    def begin(self) -> None:
        raise OperationalError("SELECT secret", {}, RuntimeError("database unavailable"))


class StaticVerifier:
    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        assert token == "safe-id-token"
        return VerifiedFirebaseIdentity(firebase_subject="private-firebase-subject")


class FailingVerifier:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        del token
        raise self.error


class FakeIdentityRepository:
    def __init__(self, status_code: UserStatusCode = UserStatusCode.ACTIVE) -> None:
        self.record: IdentityUserRecord | None = None
        self.status_code = status_code
        self.created_count = 0

    def acquire_subject_lock(self, session: FakeSession, firebase_subject: str) -> None:
        del session, firebase_subject

    def get_active_by_firebase_subject(
        self,
        session: FakeSession,
        firebase_subject: str,
    ) -> IdentityUserRecord | None:
        del session, firebase_subject
        return self.record

    def create_firebase_user(
        self,
        session: FakeSession,
        firebase_subject: str,
        now: datetime,
    ) -> IdentityUserRecord:
        del session, firebase_subject, now
        self.created_count += 1
        self.record = IdentityUserRecord(user_id=uuid4(), status_code=self.status_code)
        return self.record

    def touch_last_active(self, session: FakeSession, user_id: UUID, now: datetime) -> None:
        del session, user_id, now


def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://test_user:test_password@localhost:5432/test_db",
    )


def protected_app(
    verifier: StaticVerifier | FailingVerifier,
    repository: FakeIdentityRepository | None = None,
    session: FakeSession | FailingSession | None = None,
):
    application = create_app(
        settings=settings(),
        readiness_probe=lambda: None,
        firebase_token_verifier=verifier,
    )
    resolved_repository = repository or FakeIdentityRepository()
    resolved_session = session or FakeSession()

    def session_override():
        yield resolved_session

    application.dependency_overrides[get_db_session] = session_override
    application.dependency_overrides[get_identity_repository] = lambda: resolved_repository

    def protected(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> dict[str, str]:
        return {"user_id": str(current_user.user_id)}

    application.add_api_route("/api/v1/test-protected", protected)
    return application


def deletion_lifecycle_app(repository: FakeIdentityRepository):
    application = protected_app(StaticVerifier(), repository)

    def deletion_lifecycle(
        current_user: Annotated[CurrentUser, Depends(get_deletion_lifecycle_user)],
    ) -> dict[str, str]:
        return {"status_code": current_user.status_code}

    application.add_api_route(
        "/api/v1/test-deletion-lifecycle",
        deletion_lifecycle,
    )
    return application


def test_missing_bearer_token_returns_authentication_required() -> None:
    with TestClient(protected_app(StaticVerifier())) as client:
        response = client.get("/api/v1/test-protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_valid_token_returns_only_internal_user_id() -> None:
    with TestClient(protected_app(StaticVerifier())) as client:
        response = client.get(
            "/api/v1/test-protected",
            headers={"Authorization": "Bearer safe-id-token"},
        )

    assert response.status_code == 200
    UUID(response.json()["user_id"])
    assert "private-firebase-subject" not in response.text
    assert "safe-id-token" not in response.text


def test_invalid_token_uses_safe_common_error(caplog) -> None:
    secret = "raw-token-must-not-leak"
    application = protected_app(FailingVerifier(InvalidFirebaseTokenError(secret)))

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/test-protected",
            headers={"Authorization": f"Bearer {secret}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
    assert response.json()["error"]["details"] == []
    assert secret not in response.text
    assert secret not in caplog.text


def test_provider_failure_is_not_reported_as_invalid_token() -> None:
    application = protected_app(FailingVerifier(FirebaseVerifierUnavailableError()))

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/test-protected",
            headers={"Authorization": "Bearer raw-provider-token"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"
    assert "raw-provider-token" not in response.text


def test_inactive_internal_account_is_blocked() -> None:
    repository = FakeIdentityRepository(UserStatusCode.DISABLED)
    application = protected_app(StaticVerifier(), repository)

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/test-protected",
            headers={"Authorization": "Bearer safe-id-token"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_deletion_pending_account_is_blocked_from_ordinary_api() -> None:
    repository = FakeIdentityRepository(UserStatusCode.DELETION_PENDING)
    application = protected_app(StaticVerifier(), repository)

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/test-protected",
            headers={"Authorization": "Bearer safe-id-token"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_deletion_lifecycle_auth_allows_existing_pending_account() -> None:
    repository = FakeIdentityRepository(UserStatusCode.DELETION_PENDING)
    repository.record = IdentityUserRecord(
        user_id=uuid4(),
        status_code=UserStatusCode.DELETION_PENDING,
    )
    with TestClient(deletion_lifecycle_app(repository)) as client:
        response = client.get(
            "/api/v1/test-deletion-lifecycle",
            headers={"Authorization": "Bearer safe-id-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status_code": "DELETION_PENDING"}
    assert repository.created_count == 0


def test_deletion_lifecycle_auth_does_not_recreate_hard_deleted_account() -> None:
    repository = FakeIdentityRepository()
    with TestClient(deletion_lifecycle_app(repository)) as client:
        response = client.get(
            "/api/v1/test-deletion-lifecycle",
            headers={"Authorization": "Bearer safe-id-token"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert repository.created_count == 0


def test_database_failure_uses_safe_service_unavailable_error() -> None:
    application = protected_app(StaticVerifier(), session=FailingSession())

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/test-protected",
            headers={"Authorization": "Bearer safe-id-token"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "SELECT secret" not in response.text
