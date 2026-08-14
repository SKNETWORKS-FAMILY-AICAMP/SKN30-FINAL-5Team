import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.modules.account_deletion.codes import (
    ACCOUNT_DELETION_POLICY_VERSION,
    ACCOUNT_DELETION_RESPONSE_SCHEMA_VERSION,
    DELETION_ENDPOINT_CODE,
    DeletionFailureCode,
    DeletionJobStatusCode,
)
from backend.app.modules.account_deletion.ports import (
    AccountDeletionRepositoryPort,
    BackupExpiryVerificationPort,
    BackupVerificationUnavailableError,
    DeletionRequestRecord,
    ExternalIdentityRevocationError,
    ExternalIdentityRevocationPort,
)
from backend.app.modules.account_deletion.schemas import AccountDeletionResponse
from backend.app.modules.identity.codes import UserStatusCode

OPERATIONAL_DELETE_SLA = timedelta(days=7)
BACKUP_EXPIRY_SLA = timedelta(days=30)
_REQUEST_HASH = hashlib.sha256(b"DELETE /api/v1/me").hexdigest()


class IdempotencyKeyReusedError(Exception):
    """An idempotency key was previously used by another mutation."""


class AccountDeletionUnavailableError(Exception):
    """The account cannot enter or replay the approved deletion lifecycle."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _response(record: DeletionRequestRecord) -> AccountDeletionResponse:
    return AccountDeletionResponse(
        deletion_request_id=record.deletion_request_id,
        status_code=UserStatusCode.DELETION_PENDING,
        operational_data_delete_by=record.operational_data_delete_by,
        backup_expiry_days=BACKUP_EXPIRY_SLA.days,
    )


class AccountDeletionService:
    def __init__(
        self,
        repository: AccountDeletionRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        policy_version: str = ACCOUNT_DELETION_POLICY_VERSION,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._policy_version = policy_version

    def request_deletion(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> AccountDeletionResponse:
        now = self._clock()
        with session.begin():
            self._repository.acquire_request_lock(session, user_id)
            idempotency_use = self._repository.get_idempotency_use(
                session, user_id, idempotency_key
            )
            if idempotency_use is not None:
                if (
                    idempotency_use.endpoint_code != DELETION_ENDPOINT_CODE
                    or idempotency_use.request_hash != _REQUEST_HASH
                ):
                    raise IdempotencyKeyReusedError
                return AccountDeletionResponse.model_validate(idempotency_use.response_payload)

            user_status = self._repository.get_user_status_for_update(session, user_id)
            existing = self._repository.get_user_request_for_update(session, user_id)
            if existing is None:
                if user_status is not UserStatusCode.ACTIVE:
                    raise AccountDeletionUnavailableError
                existing = self._repository.create_request(
                    session,
                    user_id,
                    now,
                    now + OPERATIONAL_DELETE_SLA,
                    now + BACKUP_EXPIRY_SLA,
                    self._policy_version,
                )
            elif user_status is not UserStatusCode.DELETION_PENDING:
                raise AccountDeletionUnavailableError

            response = _response(existing)
            self._repository.save_idempotency_response(
                session,
                user_id,
                idempotency_key,
                _REQUEST_HASH,
                response.model_dump(mode="json"),
                ACCOUNT_DELETION_RESPONSE_SCHEMA_VERSION,
                now,
            )
        return response


class AccountDeletionJobService:
    def __init__(
        self,
        repository: AccountDeletionRepositoryPort,
        identity_revoker: ExternalIdentityRevocationPort,
        backup_verifier: BackupExpiryVerificationPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._identity_revoker = identity_revoker
        self._backup_verifier = backup_verifier
        self._clock = clock
        self._logger = logger or logging.getLogger(__name__)

    def runnable_job_ids(self, session: Session, *, limit: int = 100) -> tuple[UUID, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with session.begin():
            return self._repository.list_runnable_job_ids(session, self._clock(), limit)

    def run_job(
        self,
        session: Session,
        deletion_job_id: UUID,
    ) -> DeletionRequestRecord | None:
        now = self._clock()
        with session.begin():
            job = self._repository.begin_job_attempt(session, deletion_job_id, now)
        if job is None or job.status_code in {
            DeletionJobStatusCode.COMPLETED,
            DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE,
            DeletionJobStatusCode.FAILED_REQUIRES_REVIEW,
        }:
            return job
        if job.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING:
            return self._verify_backup_expiry(session, job, now)

        with session.begin():
            identities = self._repository.list_pending_external_identities(session, deletion_job_id)
        for identity in identities:
            try:
                self._identity_revoker.revoke(
                    identity.provider_code,
                    identity.provider_subject,
                )
            except ExternalIdentityRevocationError:
                if now < job.operational_data_delete_by:
                    with session.begin():
                        return self._repository.mark_external_retry_pending(
                            session,
                            deletion_job_id,
                            DeletionFailureCode.EXTERNAL_REVOCATION_RETRYABLE,
                        )
                with session.begin():
                    job = self._repository.mark_external_final_failure(
                        session,
                        deletion_job_id,
                        DeletionFailureCode.EXTERNAL_REVOCATION_FINAL,
                    )
                self._logger.warning(
                    "account deletion external revocation reached final failure",
                    extra={
                        "deletion_job_id": str(deletion_job_id),
                        "failure_code": DeletionFailureCode.EXTERNAL_REVOCATION_FINAL,
                    },
                )
                break
            else:
                with session.begin():
                    self._repository.mark_identity_revoked(
                        session,
                        deletion_job_id,
                        identity.identity_id,
                        now,
                    )
        else:
            with session.begin():
                job = self._repository.mark_external_succeeded(session, deletion_job_id)

        try:
            with session.begin():
                return self._repository.hard_delete_user_data_and_deidentify(
                    session,
                    deletion_job_id,
                    now,
                )
        except SQLAlchemyError:
            with session.begin():
                failed = self._repository.mark_operational_delete_failed(
                    session,
                    deletion_job_id,
                    DeletionFailureCode.OPERATIONAL_DATA_DELETE_FAILED,
                )
            self._logger.error(
                "account deletion operational data delete requires review",
                extra={
                    "deletion_job_id": str(deletion_job_id),
                    "failure_code": DeletionFailureCode.OPERATIONAL_DATA_DELETE_FAILED,
                },
            )
            return failed

    def _verify_backup_expiry(
        self,
        session: Session,
        job: DeletionRequestRecord,
        now: datetime,
    ) -> DeletionRequestRecord:
        try:
            evidence = self._backup_verifier.verify_expiry(
                job.deletion_job_id,
                job.backup_expiry_due_at,
            )
        except BackupVerificationUnavailableError:
            evidence = None
        if evidence is None:
            self._logger.info(
                "account deletion backup expiry evidence unavailable",
                extra={
                    "deletion_job_id": str(job.deletion_job_id),
                    "failure_code": DeletionFailureCode.BACKUP_EXPIRY_EVIDENCE_UNAVAILABLE,
                },
            )
            return job
        with session.begin():
            return self._repository.finalize_backup_expiry(
                session,
                job.deletion_job_id,
                evidence,
                now,
            )


__all__ = [
    "AccountDeletionJobService",
    "AccountDeletionService",
    "AccountDeletionUnavailableError",
    "IdempotencyKeyReusedError",
]
