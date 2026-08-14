from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_account_deletion_repository,
    get_db_session,
    get_deletion_lifecycle_user,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.account_deletion.codes import (
    ACCOUNT_DELETION_POLICY_VERSION,
    DELETION_ENDPOINT_CODE,
    DeletionJobStatusCode,
    DeletionStageCode,
    ExternalRevocationStatusCode,
)
from backend.app.modules.account_deletion.ports import (
    DeletionRequestRecord,
    IdempotencyUseRecord,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser

NOW = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)


class FakeSession:
    def begin(self):
        return nullcontext()


class FakeDeletionRepository:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.user_status = UserStatusCode.ACTIVE
        self.request: DeletionRequestRecord | None = None
        self.idempotency: dict[UUID, IdempotencyUseRecord] = {}
        self.create_count = 0

    def acquire_request_lock(self, session: FakeSession, user_id: UUID) -> None:
        del session
        assert user_id == self.user_id

    def get_idempotency_use(
        self, session: FakeSession, user_id: UUID, idempotency_key: UUID
    ) -> IdempotencyUseRecord | None:
        del session
        assert user_id == self.user_id
        return self.idempotency.get(idempotency_key)

    def save_idempotency_response(
        self,
        session: FakeSession,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        response_schema_version: str,
        now: datetime,
    ) -> None:
        del session, response_schema_version, now
        assert user_id == self.user_id
        self.idempotency[idempotency_key] = IdempotencyUseRecord(
            endpoint_code=DELETION_ENDPOINT_CODE,
            request_hash=request_hash,
            response_payload=response_payload,
        )

    def get_user_status_for_update(self, session: FakeSession, user_id: UUID) -> UserStatusCode:
        del session
        assert user_id == self.user_id
        return self.user_status

    def get_user_request_for_update(
        self, session: FakeSession, user_id: UUID
    ) -> DeletionRequestRecord | None:
        del session
        assert user_id == self.user_id
        return self.request

    def create_request(
        self,
        session: FakeSession,
        user_id: UUID,
        requested_at: datetime,
        operational_data_delete_by: datetime,
        backup_expiry_due_at: datetime,
        policy_version: str,
    ) -> DeletionRequestRecord:
        del session
        self.create_count += 1
        self.user_status = UserStatusCode.DELETION_PENDING
        self.request = DeletionRequestRecord(
            deletion_request_id=uuid4(),
            deletion_job_id=uuid4(),
            user_id=user_id,
            status_code=DeletionJobStatusCode.PENDING,
            current_stage_code=DeletionStageCode.ACCESS_BLOCK,
            external_revocation_status_code=ExternalRevocationStatusCode.PENDING,
            completion_code=None,
            policy_version=policy_version,
            attempt_count=0,
            requested_at=requested_at,
            operational_data_delete_by=operational_data_delete_by,
            operational_deleted_at=None,
            backup_expiry_due_at=backup_expiry_due_at,
            backup_expiry_verified_at=None,
            completed_at=None,
            failure_code=None,
            audit_expires_at=None,
        )
        return self.request


def _client(repository: FakeDeletionRepository) -> TestClient:
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
    )
    app = create_app(settings=settings, readiness_probe=lambda: None)
    app.dependency_overrides[get_deletion_lifecycle_user] = lambda: CurrentUser(
        user_id=repository.user_id,
        status_code=repository.user_status,
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_account_deletion_repository] = lambda: repository
    return TestClient(app)


def test_delete_me_returns_accepted_opaque_response_and_replays_new_key() -> None:
    user_id = uuid4()
    repository = FakeDeletionRepository(user_id)
    first_key = str(uuid4())
    second_key = str(uuid4())
    with _client(repository) as client:
        first = client.delete(
            "/api/v1/me",
            headers={"Idempotency-Key": first_key},
        )
        second = client.delete(
            "/api/v1/me",
            headers={"Idempotency-Key": second_key},
        )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert first.json()["status_code"] == "DELETION_PENDING"
    assert first.json()["backup_expiry_days"] == 30
    assert repository.create_count == 1
    assert str(user_id) not in first.text
    assert first_key not in first.text
    assert second_key not in second.text
    assert first.json()["operational_data_delete_by"].endswith("Z")


def test_delete_me_requires_uuid_idempotency_key() -> None:
    repository = FakeDeletionRepository(uuid4())
    with _client(repository) as client:
        missing = client.delete("/api/v1/me")
        malformed = client.delete(
            "/api/v1/me",
            headers={"Idempotency-Key": "not-a-uuid"},
        )

    assert missing.status_code == 400
    assert malformed.status_code == 400
    assert repository.create_count == 0


def test_deadlines_are_derived_from_the_first_request() -> None:
    repository = FakeDeletionRepository(uuid4())
    repository.request = DeletionRequestRecord(
        deletion_request_id=uuid4(),
        deletion_job_id=uuid4(),
        user_id=repository.user_id,
        status_code=DeletionJobStatusCode.RETRY_PENDING,
        current_stage_code=DeletionStageCode.EXTERNAL_REVOCATION,
        external_revocation_status_code=ExternalRevocationStatusCode.RETRY_PENDING,
        completion_code=None,
        policy_version=ACCOUNT_DELETION_POLICY_VERSION,
        attempt_count=2,
        requested_at=NOW,
        operational_data_delete_by=NOW + timedelta(days=7),
        operational_deleted_at=None,
        backup_expiry_due_at=NOW + timedelta(days=30),
        backup_expiry_verified_at=None,
        completed_at=None,
        failure_code=None,
        audit_expires_at=None,
    )
    repository.user_status = UserStatusCode.DELETION_PENDING
    with _client(repository) as client:
        response = client.delete(
            "/api/v1/me",
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 202
    assert response.json()["deletion_request_id"] == str(repository.request.deletion_request_id)
    assert response.json()["operational_data_delete_by"] == "2026-08-21T04:00:00Z"
    assert repository.create_count == 0
