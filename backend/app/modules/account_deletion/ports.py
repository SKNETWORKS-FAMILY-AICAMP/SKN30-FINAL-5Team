from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.account_deletion.codes import (
    DeletionFailureCode,
    DeletionJobStatusCode,
    DeletionStageCode,
    ExternalRevocationStatusCode,
)
from backend.app.modules.identity.codes import UserStatusCode


class ExternalIdentityRevocationError(Exception):
    """An external identity could not be revoked during this attempt."""


class BackupVerificationUnavailableError(Exception):
    """Approved backup-expiry evidence is not currently available."""


@dataclass(frozen=True)
class IdempotencyUseRecord:
    endpoint_code: str
    request_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True)
class DeletionRequestRecord:
    deletion_request_id: UUID
    deletion_job_id: UUID
    user_id: UUID | None
    status_code: DeletionJobStatusCode
    current_stage_code: DeletionStageCode
    external_revocation_status_code: ExternalRevocationStatusCode
    completion_code: str | None
    policy_version: str
    attempt_count: int
    requested_at: datetime
    operational_data_delete_by: datetime
    operational_deleted_at: datetime | None
    backup_expiry_due_at: datetime
    backup_expiry_verified_at: datetime | None
    completed_at: datetime | None
    failure_code: DeletionFailureCode | None
    audit_expires_at: datetime | None


@dataclass(frozen=True)
class ExternalIdentityRecord:
    identity_id: UUID
    provider_code: str
    provider_subject: str


@dataclass(frozen=True)
class BackupExpiryEvidence:
    verified_at: datetime


class ExternalIdentityRevocationPort(Protocol):
    def revoke(self, provider_code: str, provider_subject: str) -> None: ...


class BackupExpiryVerificationPort(Protocol):
    def verify_expiry(
        self,
        deletion_job_id: UUID,
        backup_expiry_due_at: datetime,
    ) -> BackupExpiryEvidence | None: ...


class AccountDeletionRepositoryPort(Protocol):
    def acquire_request_lock(self, session: Session, user_id: UUID) -> None: ...

    def get_idempotency_use(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> IdempotencyUseRecord | None: ...

    def save_idempotency_response(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        response_schema_version: str,
        now: datetime,
    ) -> None: ...

    def get_user_status_for_update(
        self,
        session: Session,
        user_id: UUID,
    ) -> UserStatusCode | None: ...

    def get_user_request_for_update(
        self,
        session: Session,
        user_id: UUID,
    ) -> DeletionRequestRecord | None: ...

    def create_request(
        self,
        session: Session,
        user_id: UUID,
        requested_at: datetime,
        operational_data_delete_by: datetime,
        backup_expiry_due_at: datetime,
        policy_version: str,
    ) -> DeletionRequestRecord: ...

    def list_runnable_job_ids(
        self,
        session: Session,
        now: datetime,
        limit: int,
    ) -> tuple[UUID, ...]: ...

    def begin_job_attempt(
        self,
        session: Session,
        deletion_job_id: UUID,
        now: datetime,
    ) -> DeletionRequestRecord | None: ...

    def list_pending_external_identities(
        self,
        session: Session,
        deletion_job_id: UUID,
    ) -> tuple[ExternalIdentityRecord, ...]: ...

    def mark_identity_revoked(
        self,
        session: Session,
        deletion_job_id: UUID,
        identity_id: UUID,
        now: datetime,
    ) -> None: ...

    def mark_external_retry_pending(
        self,
        session: Session,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord: ...

    def mark_external_final_failure(
        self,
        session: Session,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord: ...

    def mark_external_succeeded(
        self,
        session: Session,
        deletion_job_id: UUID,
    ) -> DeletionRequestRecord: ...

    def hard_delete_user_data_and_deidentify(
        self,
        session: Session,
        deletion_job_id: UUID,
        now: datetime,
    ) -> DeletionRequestRecord: ...

    def mark_operational_delete_failed(
        self,
        session: Session,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord: ...

    def finalize_backup_expiry(
        self,
        session: Session,
        deletion_job_id: UUID,
        evidence: BackupExpiryEvidence,
        now: datetime,
    ) -> DeletionRequestRecord: ...


__all__ = [
    "AccountDeletionRepositoryPort",
    "BackupExpiryEvidence",
    "BackupExpiryVerificationPort",
    "BackupVerificationUnavailableError",
    "DeletionRequestRecord",
    "ExternalIdentityRecord",
    "ExternalIdentityRevocationError",
    "ExternalIdentityRevocationPort",
    "IdempotencyUseRecord",
]
