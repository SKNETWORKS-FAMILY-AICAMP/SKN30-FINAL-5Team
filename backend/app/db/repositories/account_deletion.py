from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import case, delete, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.account_deletion import AccountDeletionAudit, AccountDeletionJob
from backend.app.db.models.checkin import DailyContext
from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.identity import User, UserIdentity
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAttentionArea,
    UserAvailableLocation,
    UserConsent,
    UserConsentEvent,
    UserEquipment,
    UserPreferredExerciseType,
    UserProfile,
)
from backend.app.db.models.routine import Routine
from backend.app.db.models.weekly_report import UserWeek
from backend.app.db.models.workout import ScheduledWorkout, WorkoutSession
from backend.app.modules.account_deletion.codes import (
    ACCOUNT_DELETION_RESPONSE_SCHEMA_VERSION,
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
    IdempotencyUseRecord,
)
from backend.app.modules.identity.codes import UserStatusCode


def _request_lock_key(user_id: UUID) -> int:
    digest = sha256(f"account-deletion:{user_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _record(row: AccountDeletionJob | AccountDeletionAudit) -> DeletionRequestRecord:
    return DeletionRequestRecord(
        deletion_request_id=row.deletion_request_id,
        deletion_job_id=row.deletion_job_id,
        user_id=row.user_id if isinstance(row, AccountDeletionJob) else None,
        status_code=DeletionJobStatusCode(row.status_code),
        current_stage_code=DeletionStageCode(row.current_stage_code),
        external_revocation_status_code=ExternalRevocationStatusCode(
            row.external_revocation_status_code
        ),
        completion_code=row.completion_code,
        policy_version=row.policy_version,
        attempt_count=row.attempt_count,
        requested_at=row.requested_at,
        operational_data_delete_by=row.operational_data_delete_by,
        operational_deleted_at=row.operational_deleted_at,
        backup_expiry_due_at=row.backup_expiry_due_at,
        backup_expiry_verified_at=row.backup_expiry_verified_at,
        completed_at=row.completed_at,
        failure_code=DeletionFailureCode(row.failure_code) if row.failure_code else None,
        audit_expires_at=row.audit_expires_at,
    )


class AccountDeletionRepository:
    def acquire_request_lock(self, session: Session, user_id: UUID) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _request_lock_key(user_id)},
        )

    def get_idempotency_use(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> IdempotencyUseRecord | None:
        row = session.scalar(
            select(MutationIdempotencyRecord)
            .where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .order_by(
                case(
                    (MutationIdempotencyRecord.endpoint_code == DELETION_ENDPOINT_CODE, 1),
                    else_=0,
                )
            )
            .limit(1)
        )
        if row is None:
            return None
        return IdempotencyUseRecord(
            endpoint_code=row.endpoint_code,
            request_hash=row.request_hash,
            response_payload=row.response_payload,
        )

    def save_idempotency_response(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, object],
        response_schema_version: str,
        now: datetime,
    ) -> None:
        if response_schema_version != ACCOUNT_DELETION_RESPONSE_SCHEMA_VERSION:
            raise ValueError("unsupported account deletion response schema")
        session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code=DELETION_ENDPOINT_CODE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_schema_version=response_schema_version,
                created_at=now,
            )
        )

    def get_user_status_for_update(
        self,
        session: Session,
        user_id: UUID,
    ) -> UserStatusCode | None:
        status = session.scalar(
            select(User.status_code).where(User.id == user_id).with_for_update()
        )
        return UserStatusCode(status) if status is not None else None

    def get_user_request_for_update(
        self,
        session: Session,
        user_id: UUID,
    ) -> DeletionRequestRecord | None:
        row = session.scalar(
            select(AccountDeletionJob)
            .where(AccountDeletionJob.user_id == user_id)
            .with_for_update()
        )
        return _record(row) if row is not None else None

    def create_request(
        self,
        session: Session,
        user_id: UUID,
        requested_at: datetime,
        operational_data_delete_by: datetime,
        backup_expiry_due_at: datetime,
        policy_version: str,
    ) -> DeletionRequestRecord:
        user = session.get(User, user_id)
        if user is None or UserStatusCode(user.status_code) is not UserStatusCode.ACTIVE:
            raise RuntimeError("account deletion requires an active user")
        has_identity = (
            session.scalar(
                select(UserIdentity.id)
                .where(
                    UserIdentity.user_id == user_id,
                    UserIdentity.revoked_at.is_(None),
                )
                .limit(1)
            )
            is not None
        )
        user.status_code = UserStatusCode.DELETION_PENDING
        user.deletion_requested_at = requested_at
        user.updated_at = requested_at
        row = AccountDeletionJob(
            deletion_request_id=uuid4(),
            deletion_job_id=uuid4(),
            user_id=user_id,
            status_code=DeletionJobStatusCode.PENDING,
            current_stage_code=DeletionStageCode.ACCESS_BLOCK,
            external_revocation_status_code=(
                ExternalRevocationStatusCode.PENDING
                if has_identity
                else ExternalRevocationStatusCode.NOT_REQUIRED
            ),
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
        session.add(row)
        session.flush()
        return _record(row)

    def list_runnable_job_ids(
        self,
        session: Session,
        now: datetime,
        limit: int,
    ) -> tuple[UUID, ...]:
        linked = list(
            session.execute(
                select(AccountDeletionJob.deletion_job_id, AccountDeletionJob.requested_at)
                .where(
                    AccountDeletionJob.status_code.in_(
                        (
                            DeletionJobStatusCode.PENDING,
                            DeletionJobStatusCode.RUNNING,
                            DeletionJobStatusCode.RETRY_PENDING,
                        )
                    ),
                    AccountDeletionJob.requested_at <= now,
                )
                .limit(limit)
            )
        )
        audits = list(
            session.execute(
                select(AccountDeletionAudit.deletion_job_id, AccountDeletionAudit.requested_at)
                .where(
                    AccountDeletionAudit.status_code == DeletionJobStatusCode.BACKUP_EXPIRY_PENDING,
                    AccountDeletionAudit.requested_at <= now,
                )
                .limit(limit)
            )
        )
        candidates = sorted((*linked, *audits), key=lambda item: (item[1], item[0]))
        return tuple(item[0] for item in candidates[:limit])

    def begin_job_attempt(
        self,
        session: Session,
        deletion_job_id: UUID,
        now: datetime,
    ) -> DeletionRequestRecord | None:
        del now
        row = self._job_for_update(session, deletion_job_id)
        if row is None:
            audit = self._audit_for_update(session, deletion_job_id)
            if audit is None:
                return None
            if (
                DeletionJobStatusCode(audit.status_code)
                is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
            ):
                audit.attempt_count += 1
                session.flush()
            return _record(audit)
        status = DeletionJobStatusCode(row.status_code)
        if status is DeletionJobStatusCode.FAILED_REQUIRES_REVIEW:
            return _record(row)
        row.attempt_count += 1
        if status in {DeletionJobStatusCode.PENDING, DeletionJobStatusCode.RETRY_PENDING}:
            row.status_code = DeletionJobStatusCode.RUNNING
            row.current_stage_code = DeletionStageCode.EXTERNAL_REVOCATION
        session.flush()
        return _record(row)

    def list_pending_external_identities(
        self,
        session: Session,
        deletion_job_id: UUID,
    ) -> tuple[ExternalIdentityRecord, ...]:
        row = self._required_job(session, deletion_job_id)
        if row.user_id is None:
            return ()
        return tuple(
            ExternalIdentityRecord(
                identity_id=identity.id,
                provider_code=identity.provider_code,
                provider_subject=identity.provider_subject,
            )
            for identity in session.scalars(
                select(UserIdentity)
                .where(
                    UserIdentity.user_id == row.user_id,
                    UserIdentity.revoked_at.is_(None),
                )
                .order_by(UserIdentity.id)
            )
        )

    def mark_identity_revoked(
        self,
        session: Session,
        deletion_job_id: UUID,
        identity_id: UUID,
        now: datetime,
    ) -> None:
        row = self._required_job(session, deletion_job_id)
        if row.user_id is None:
            return
        identity = session.scalar(
            select(UserIdentity)
            .where(
                UserIdentity.id == identity_id,
                UserIdentity.user_id == row.user_id,
            )
            .with_for_update()
        )
        if identity is not None and identity.revoked_at is None:
            identity.revoked_at = now

    def mark_external_retry_pending(
        self,
        session: Session,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord:
        row = self._required_job_for_update(session, deletion_job_id)
        row.status_code = DeletionJobStatusCode.RETRY_PENDING
        row.current_stage_code = DeletionStageCode.EXTERNAL_REVOCATION
        row.external_revocation_status_code = ExternalRevocationStatusCode.RETRY_PENDING
        row.failure_code = failure_code
        session.flush()
        return _record(row)

    def mark_external_final_failure(
        self,
        session: Session,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord:
        row = self._required_job_for_update(session, deletion_job_id)
        row.status_code = DeletionJobStatusCode.RUNNING
        row.current_stage_code = DeletionStageCode.OPERATIONAL_DATA_DELETE
        row.external_revocation_status_code = ExternalRevocationStatusCode.FAILED_FINAL
        row.failure_code = failure_code
        session.flush()
        return _record(row)

    def mark_external_succeeded(
        self,
        session: Session,
        deletion_job_id: UUID,
    ) -> DeletionRequestRecord:
        row = self._required_job_for_update(session, deletion_job_id)
        row.status_code = DeletionJobStatusCode.RUNNING
        row.current_stage_code = DeletionStageCode.OPERATIONAL_DATA_DELETE
        if (
            ExternalRevocationStatusCode(row.external_revocation_status_code)
            is not ExternalRevocationStatusCode.NOT_REQUIRED
        ):
            row.external_revocation_status_code = ExternalRevocationStatusCode.SUCCEEDED
        row.failure_code = None
        session.flush()
        return _record(row)

    def hard_delete_user_data_and_deidentify(
        self,
        session: Session,
        deletion_job_id: UUID,
        now: datetime,
    ) -> DeletionRequestRecord:
        row = self._required_job_for_update(session, deletion_job_id)
        if DeletionJobStatusCode(row.status_code) is not DeletionJobStatusCode.RUNNING:
            raise RuntimeError("account deletion job is not running")
        external_status = ExternalRevocationStatusCode(row.external_revocation_status_code)
        if external_status not in {
            ExternalRevocationStatusCode.NOT_REQUIRED,
            ExternalRevocationStatusCode.SUCCEEDED,
            ExternalRevocationStatusCode.FAILED_FINAL,
        }:
            raise RuntimeError("external revocation is not resolved")

        user_id = row.user_id
        # ADR-0016 retired the calendar integration, so there is no stored provider
        # credential left to wait on before operational data is deleted.
        row.current_stage_code = DeletionStageCode.OPERATIONAL_DATA_DELETE
        session.flush()

        # RESTRICT links require this root deletion order. Descendants use ON DELETE CASCADE.
        session.execute(delete(WorkoutSession).where(WorkoutSession.user_id == user_id))
        session.execute(delete(ScheduledWorkout).where(ScheduledWorkout.user_id == user_id))
        session.execute(delete(UserWeek).where(UserWeek.user_id == user_id))
        session.execute(delete(DecisionRun).where(DecisionRun.user_id == user_id))
        session.execute(delete(Routine).where(Routine.user_id == user_id))
        session.execute(delete(DailyContext).where(DailyContext.user_id == user_id))
        for model in (
            MutationIdempotencyRecord,
            UserConsentEvent,
            UserConsent,
            UserAttentionArea,
            UserPreferredExerciseType,
            UserAvailableLocation,
            UserEquipment,
            UserProfile,
        ):
            session.execute(delete(model).where(model.user_id == user_id))

        row.current_stage_code = DeletionStageCode.CACHE_AND_WORK_DELETE
        # No cache/work persistence exists in this release; the checkpoint remains explicit.
        row.current_stage_code = DeletionStageCode.AUDIT_DEIDENTIFICATION
        session.execute(delete(UserIdentity).where(UserIdentity.user_id == user_id))
        failure_code = row.failure_code
        if external_status is not ExternalRevocationStatusCode.FAILED_FINAL:
            failure_code = None
        audit = AccountDeletionAudit(
            deletion_request_id=row.deletion_request_id,
            deletion_job_id=row.deletion_job_id,
            status_code=DeletionJobStatusCode.BACKUP_EXPIRY_PENDING,
            current_stage_code=DeletionStageCode.BACKUP_EXPIRY_VERIFICATION,
            external_revocation_status_code=external_status,
            completion_code=None,
            policy_version=row.policy_version,
            attempt_count=row.attempt_count,
            requested_at=row.requested_at,
            operational_data_delete_by=row.operational_data_delete_by,
            operational_deleted_at=now,
            backup_expiry_due_at=row.backup_expiry_due_at,
            backup_expiry_verified_at=None,
            completed_at=None,
            failure_code=failure_code,
            audit_expires_at=None,
        )
        session.add(audit)
        session.delete(row)
        session.flush()
        session.execute(delete(User).where(User.id == user_id))
        session.flush()
        return _record(audit)

    def mark_operational_delete_failed(
        self,
        session: Session,
        deletion_job_id: UUID,
        failure_code: DeletionFailureCode,
    ) -> DeletionRequestRecord:
        row = self._required_job_for_update(session, deletion_job_id)
        row.status_code = DeletionJobStatusCode.FAILED_REQUIRES_REVIEW
        row.current_stage_code = DeletionStageCode.OPERATIONAL_DATA_DELETE
        row.failure_code = failure_code
        session.flush()
        return _record(row)

    def finalize_backup_expiry(
        self,
        session: Session,
        deletion_job_id: UUID,
        evidence: BackupExpiryEvidence,
        now: datetime,
    ) -> DeletionRequestRecord:
        row = self._required_audit_for_update(session, deletion_job_id)
        if (
            DeletionJobStatusCode(row.status_code)
            is not DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
        ):
            return _record(row)
        if evidence.verified_at > now:
            raise ValueError("backup evidence timestamp cannot be in the future")
        row.backup_expiry_verified_at = evidence.verified_at
        row.completed_at = now
        if (
            ExternalRevocationStatusCode(row.external_revocation_status_code)
            is ExternalRevocationStatusCode.FAILED_FINAL
        ):
            completion = DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
        else:
            completion = DeletionJobStatusCode.COMPLETED
            row.failure_code = None
        row.status_code = completion
        row.completion_code = completion
        session.flush()
        return _record(row)

    @staticmethod
    def _job_for_update(
        session: Session,
        deletion_job_id: UUID,
    ) -> AccountDeletionJob | None:
        return session.scalar(
            select(AccountDeletionJob)
            .where(AccountDeletionJob.deletion_job_id == deletion_job_id)
            .with_for_update()
        )

    @staticmethod
    def _audit_for_update(
        session: Session,
        deletion_job_id: UUID,
    ) -> AccountDeletionAudit | None:
        return session.scalar(
            select(AccountDeletionAudit)
            .where(AccountDeletionAudit.deletion_job_id == deletion_job_id)
            .with_for_update()
        )

    @classmethod
    def _required_job_for_update(
        cls,
        session: Session,
        deletion_job_id: UUID,
    ) -> AccountDeletionJob:
        row = cls._job_for_update(session, deletion_job_id)
        if row is None:
            raise RuntimeError("account deletion job does not exist")
        return row

    @staticmethod
    def _required_job(session: Session, deletion_job_id: UUID) -> AccountDeletionJob:
        row = session.scalar(
            select(AccountDeletionJob).where(AccountDeletionJob.deletion_job_id == deletion_job_id)
        )
        if row is None:
            raise RuntimeError("account deletion job does not exist")
        return row

    @classmethod
    def _required_audit_for_update(
        cls,
        session: Session,
        deletion_job_id: UUID,
    ) -> AccountDeletionAudit:
        row = cls._audit_for_update(session, deletion_job_id)
        if row is None:
            raise RuntimeError("account deletion audit does not exist")
        return row


__all__ = ["AccountDeletionRepository"]
