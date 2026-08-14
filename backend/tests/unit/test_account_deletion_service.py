from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError

from backend.app.modules.account_deletion.codes import (
    ACCOUNT_DELETION_POLICY_VERSION,
    DELETION_ENDPOINT_CODE,
    DeletionFailureCode,
    DeletionJobStatusCode,
    DeletionStageCode,
    ExternalRevocationStatusCode,
)
from backend.app.modules.account_deletion.ports import (
    BackupExpiryEvidence,
    DeletionRequestRecord,
    ExternalIdentityRecord,
    ExternalIdentityRevocationError,
    IdempotencyUseRecord,
)
from backend.app.modules.account_deletion.service import (
    AccountDeletionJobService,
    AccountDeletionService,
    IdempotencyKeyReusedError,
)
from backend.app.modules.identity.codes import UserStatusCode

NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)


def _job(
    *,
    user_id: UUID | None = None,
    status: DeletionJobStatusCode = DeletionJobStatusCode.PENDING,
    external_status: ExternalRevocationStatusCode = ExternalRevocationStatusCode.PENDING,
    requested_at: datetime = NOW,
) -> DeletionRequestRecord:
    linked_user_id = user_id if user_id is not None else uuid4()
    operational_deleted_at = None
    if status in {
        DeletionJobStatusCode.BACKUP_EXPIRY_PENDING,
        DeletionJobStatusCode.COMPLETED,
        DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE,
    }:
        linked_user_id = None
        operational_deleted_at = requested_at
    return DeletionRequestRecord(
        deletion_request_id=uuid4(),
        deletion_job_id=uuid4(),
        user_id=linked_user_id,
        status_code=status,
        current_stage_code=(
            DeletionStageCode.BACKUP_EXPIRY_VERIFICATION
            if linked_user_id is None
            else DeletionStageCode.ACCESS_BLOCK
        ),
        external_revocation_status_code=external_status,
        completion_code=(status if status.name.startswith("COMPLETED") else None),
        policy_version=ACCOUNT_DELETION_POLICY_VERSION,
        attempt_count=0,
        requested_at=requested_at,
        operational_data_delete_by=requested_at + timedelta(days=7),
        operational_deleted_at=operational_deleted_at,
        backup_expiry_due_at=requested_at + timedelta(days=30),
        backup_expiry_verified_at=(requested_at if status.name.startswith("COMPLETED") else None),
        completed_at=(requested_at if status.name.startswith("COMPLETED") else None),
        failure_code=None,
        audit_expires_at=None,
    )


class RequestSession:
    def __init__(self, repository: "FakeRequestRepository") -> None:
        self.repository = repository

    @contextmanager
    def begin(self):
        snapshot = deepcopy(self.repository.__dict__)
        try:
            yield
        except Exception:
            self.repository.__dict__.clear()
            self.repository.__dict__.update(snapshot)
            raise


class FakeRequestRepository:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.user_status = UserStatusCode.ACTIVE
        self.request: DeletionRequestRecord | None = None
        self.idempotency: dict[UUID, IdempotencyUseRecord] = {}
        self.create_count = 0
        self.fail_create = False

    def acquire_request_lock(self, session: RequestSession, user_id: UUID) -> None:
        assert session.repository is self
        assert user_id == self.user_id

    def get_idempotency_use(
        self, session: RequestSession, user_id: UUID, idempotency_key: UUID
    ) -> IdempotencyUseRecord | None:
        del session
        assert user_id == self.user_id
        return self.idempotency.get(idempotency_key)

    def save_idempotency_response(
        self,
        session: RequestSession,
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

    def get_user_status_for_update(self, session: RequestSession, user_id: UUID) -> UserStatusCode:
        del session
        assert user_id == self.user_id
        return self.user_status

    def get_user_request_for_update(
        self, session: RequestSession, user_id: UUID
    ) -> DeletionRequestRecord | None:
        del session
        assert user_id == self.user_id
        return self.request

    def create_request(
        self,
        session: RequestSession,
        user_id: UUID,
        requested_at: datetime,
        operational_data_delete_by: datetime,
        backup_expiry_due_at: datetime,
        policy_version: str,
    ) -> DeletionRequestRecord:
        del session, operational_data_delete_by, backup_expiry_due_at, policy_version
        self.user_status = UserStatusCode.DELETION_PENDING
        self.request = _job(user_id=user_id, requested_at=requested_at)
        self.create_count += 1
        if self.fail_create:
            raise OperationalError("INSERT", {}, RuntimeError("forced failure"))
        return self.request


def test_first_request_is_atomic_and_same_or_new_key_replays_first_response() -> None:
    user_id = uuid4()
    repository = FakeRequestRepository(user_id)
    service = AccountDeletionService(repository, clock=lambda: NOW)  # type: ignore[arg-type]
    session = RequestSession(repository)
    first_key = uuid4()

    first = service.request_deletion(session, user_id, first_key)  # type: ignore[arg-type]
    same_key = service.request_deletion(session, user_id, first_key)  # type: ignore[arg-type]
    new_key = service.request_deletion(session, user_id, uuid4())  # type: ignore[arg-type]

    assert repository.user_status is UserStatusCode.DELETION_PENDING
    assert repository.create_count == 1
    assert same_key == first
    assert new_key == first
    assert first.operational_data_delete_by == NOW + timedelta(days=7)
    assert first.backup_expiry_days == 30


def test_request_transaction_failure_rolls_back_status_and_job() -> None:
    user_id = uuid4()
    repository = FakeRequestRepository(user_id)
    repository.fail_create = True
    service = AccountDeletionService(repository, clock=lambda: NOW)  # type: ignore[arg-type]

    with pytest.raises(OperationalError):
        service.request_deletion(RequestSession(repository), user_id, uuid4())  # type: ignore[arg-type]

    assert repository.user_status is UserStatusCode.ACTIVE
    assert repository.request is None
    assert repository.create_count == 0


def test_key_used_by_another_mutation_is_rejected() -> None:
    user_id = uuid4()
    key = uuid4()
    repository = FakeRequestRepository(user_id)
    repository.idempotency[key] = IdempotencyUseRecord(
        endpoint_code="PUT_ME_ONBOARDING",
        request_hash="other",
        response_payload={},
    )
    service = AccountDeletionService(repository, clock=lambda: NOW)  # type: ignore[arg-type]

    with pytest.raises(IdempotencyKeyReusedError):
        service.request_deletion(RequestSession(repository), user_id, key)  # type: ignore[arg-type]


class JobSession:
    def begin(self):
        return nullcontext()


class FakeJobRepository:
    def __init__(self, job: DeletionRequestRecord) -> None:
        self.job = job
        self.identities = (
            ExternalIdentityRecord(uuid4(), "FIREBASE", "first-private-subject"),
            ExternalIdentityRecord(uuid4(), "FIREBASE", "second-private-subject"),
        )
        self.revoked: set[UUID] = set()
        self.hard_delete_count = 0
        self.fail_hard_delete = False

    def list_runnable_job_ids(
        self, session: JobSession, now: datetime, limit: int
    ) -> tuple[UUID, ...]:
        del session, limit
        return (self.job.deletion_job_id,) if self.job.requested_at <= now else ()

    def begin_job_attempt(
        self, session: JobSession, deletion_job_id: UUID, now: datetime
    ) -> DeletionRequestRecord | None:
        del session, now
        assert deletion_job_id == self.job.deletion_job_id
        if self.job.status_code in {
            DeletionJobStatusCode.COMPLETED,
            DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE,
            DeletionJobStatusCode.FAILED_REQUIRES_REVIEW,
        }:
            return self.job
        status = self.job.status_code
        self.job = replace(
            self.job,
            status_code=(
                DeletionJobStatusCode.RUNNING
                if status in {DeletionJobStatusCode.PENDING, DeletionJobStatusCode.RETRY_PENDING}
                else status
            ),
            current_stage_code=(
                DeletionStageCode.EXTERNAL_REVOCATION
                if status in {DeletionJobStatusCode.PENDING, DeletionJobStatusCode.RETRY_PENDING}
                else self.job.current_stage_code
            ),
            attempt_count=self.job.attempt_count + 1,
        )
        return self.job

    def list_pending_external_identities(
        self, session: JobSession, deletion_job_id: UUID
    ) -> tuple[ExternalIdentityRecord, ...]:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        return tuple(
            identity for identity in self.identities if identity.identity_id not in self.revoked
        )

    def mark_identity_revoked(
        self,
        session: JobSession,
        deletion_job_id: UUID,
        identity_id: UUID,
        now: datetime,
    ) -> None:
        del session, now
        assert deletion_job_id == self.job.deletion_job_id
        self.revoked.add(identity_id)

    def mark_external_retry_pending(
        self,
        session: JobSession,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        self.job = replace(
            self.job,
            status_code=DeletionJobStatusCode.RETRY_PENDING,
            external_revocation_status_code=ExternalRevocationStatusCode.RETRY_PENDING,
            failure_code=failure_code,
        )
        return self.job

    def mark_external_final_failure(
        self,
        session: JobSession,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        self.job = replace(
            self.job,
            status_code=DeletionJobStatusCode.RUNNING,
            current_stage_code=DeletionStageCode.OPERATIONAL_DATA_DELETE,
            external_revocation_status_code=ExternalRevocationStatusCode.FAILED_FINAL,
            failure_code=failure_code,
        )
        return self.job

    def mark_external_succeeded(
        self, session: JobSession, deletion_job_id: UUID
    ) -> DeletionRequestRecord:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        self.job = replace(
            self.job,
            status_code=DeletionJobStatusCode.RUNNING,
            current_stage_code=DeletionStageCode.OPERATIONAL_DATA_DELETE,
            external_revocation_status_code=ExternalRevocationStatusCode.SUCCEEDED,
            failure_code=None,
        )
        return self.job

    def hard_delete_user_data_and_deidentify(
        self, session: JobSession, deletion_job_id: UUID, now: datetime
    ) -> DeletionRequestRecord:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        if self.fail_hard_delete:
            raise OperationalError("DELETE private", {}, RuntimeError("private failure"))
        self.hard_delete_count += 1
        self.job = replace(
            self.job,
            user_id=None,
            status_code=DeletionJobStatusCode.BACKUP_EXPIRY_PENDING,
            current_stage_code=DeletionStageCode.BACKUP_EXPIRY_VERIFICATION,
            operational_deleted_at=now,
        )
        return self.job

    def mark_operational_delete_failed(
        self,
        session: JobSession,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        self.job = replace(
            self.job,
            status_code=DeletionJobStatusCode.FAILED_REQUIRES_REVIEW,
            current_stage_code=DeletionStageCode.OPERATIONAL_DATA_DELETE,
            failure_code=failure_code,
        )
        return self.job

    def finalize_backup_expiry(
        self,
        session: JobSession,
        deletion_job_id: UUID,
        evidence: BackupExpiryEvidence,
        now: datetime,
    ) -> DeletionRequestRecord:
        del session
        assert deletion_job_id == self.job.deletion_job_id
        completion = (
            DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
            if self.job.external_revocation_status_code is ExternalRevocationStatusCode.FAILED_FINAL
            else DeletionJobStatusCode.COMPLETED
        )
        self.job = replace(
            self.job,
            status_code=completion,
            completion_code=completion,
            backup_expiry_verified_at=evidence.verified_at,
            completed_at=now,
        )
        return self.job


class RecordingRevoker:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[str] = []

    def revoke(self, provider_code: str, provider_subject: str) -> None:
        assert provider_code == "FIREBASE"
        self.calls.append(provider_subject)
        if self.failures:
            self.failures -= 1
            raise ExternalIdentityRevocationError("raw-provider-secret")


class StaticBackupVerifier:
    def __init__(self, evidence: BackupExpiryEvidence | None = None) -> None:
        self.evidence = evidence

    def verify_expiry(
        self, deletion_job_id: UUID, backup_expiry_due_at: datetime
    ) -> BackupExpiryEvidence | None:
        del deletion_job_id, backup_expiry_due_at
        return self.evidence


def test_job_is_eligible_immediately_and_provider_failure_is_retryable(caplog) -> None:
    repository = FakeJobRepository(_job())
    revoker = RecordingRevoker(failures=1)
    service = AccountDeletionJobService(
        repository,  # type: ignore[arg-type]
        revoker,
        StaticBackupVerifier(),
        clock=lambda: NOW,
    )

    assert service.runnable_job_ids(JobSession()) == (repository.job.deletion_job_id,)  # type: ignore[arg-type]
    result = service.run_job(JobSession(), repository.job.deletion_job_id)  # type: ignore[arg-type]

    assert result is not None
    assert result.status_code is DeletionJobStatusCode.RETRY_PENDING
    assert repository.hard_delete_count == 0
    assert "raw-provider-secret" not in caplog.text


def test_retry_skips_successful_provider_and_resumes_failed_stage() -> None:
    repository = FakeJobRepository(_job())
    revoker = RecordingRevoker(failures=0)
    original_revoke = revoker.revoke
    failed_once = False

    def fail_second_once(provider_code: str, provider_subject: str) -> None:
        nonlocal failed_once
        if provider_subject == "second-private-subject" and not failed_once:
            revoker.calls.append(provider_subject)
            failed_once = True
            raise ExternalIdentityRevocationError
        original_revoke(provider_code, provider_subject)

    revoker.revoke = fail_second_once  # type: ignore[method-assign]
    service = AccountDeletionJobService(
        repository,  # type: ignore[arg-type]
        revoker,
        StaticBackupVerifier(),
        clock=lambda: NOW,
    )

    first = service.run_job(JobSession(), repository.job.deletion_job_id)  # type: ignore[arg-type]
    second = service.run_job(JobSession(), repository.job.deletion_job_id)  # type: ignore[arg-type]

    assert first is not None and first.status_code is DeletionJobStatusCode.RETRY_PENDING
    assert second is not None and second.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
    assert revoker.calls.count("first-private-subject") == 1
    assert repository.hard_delete_count == 1


def test_deadline_final_provider_failure_deletes_locally_but_needs_backup_evidence() -> None:
    repository = FakeJobRepository(_job())
    revoker = RecordingRevoker(failures=1)
    service = AccountDeletionJobService(
        repository,  # type: ignore[arg-type]
        revoker,
        StaticBackupVerifier(),
        clock=lambda: NOW + timedelta(days=7),
    )

    deleted = service.run_job(JobSession(), repository.job.deletion_job_id)  # type: ignore[arg-type]
    still_pending = service.run_job(JobSession(), repository.job.deletion_job_id)  # type: ignore[arg-type]

    assert deleted is not None
    assert deleted.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
    assert deleted.external_revocation_status_code is ExternalRevocationStatusCode.FAILED_FINAL
    assert still_pending is not None
    assert still_pending.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING


def test_backup_evidence_completes_external_failure_path_and_repeat_is_noop() -> None:
    pending = _job(
        status=DeletionJobStatusCode.BACKUP_EXPIRY_PENDING,
        external_status=ExternalRevocationStatusCode.FAILED_FINAL,
    )
    repository = FakeJobRepository(pending)
    revoker = RecordingRevoker()
    evidence = BackupExpiryEvidence(verified_at=NOW + timedelta(days=30))
    service = AccountDeletionJobService(
        repository,  # type: ignore[arg-type]
        revoker,
        StaticBackupVerifier(evidence),
        clock=lambda: NOW + timedelta(days=30),
    )

    completed = service.run_job(JobSession(), pending.deletion_job_id)  # type: ignore[arg-type]
    repeated = service.run_job(JobSession(), pending.deletion_job_id)  # type: ignore[arg-type]

    assert completed is not None
    assert completed.status_code is (
        DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
    )
    assert repeated == completed
    assert revoker.calls == []


def test_operational_delete_failure_is_not_completed(caplog) -> None:
    repository = FakeJobRepository(_job())
    repository.identities = ()
    repository.fail_hard_delete = True
    service = AccountDeletionJobService(
        repository,  # type: ignore[arg-type]
        RecordingRevoker(),
        StaticBackupVerifier(),
        clock=lambda: NOW,
    )

    result = service.run_job(JobSession(), repository.job.deletion_job_id)  # type: ignore[arg-type]

    assert result is not None
    assert result.status_code is DeletionJobStatusCode.FAILED_REQUIRES_REVIEW
    assert result.completed_at is None
    assert "private failure" not in caplog.text
