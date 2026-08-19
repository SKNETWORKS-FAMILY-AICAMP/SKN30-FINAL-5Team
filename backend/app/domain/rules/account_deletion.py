"""Deterministic account-deletion lifecycle, retention, and privacy contracts."""

import hashlib
import hmac
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

ACCOUNT_DELETION_POLICY_VERSION = "account-deletion-policy-v1"
OPERATIONAL_DELETE_DEADLINE_DAYS = 7
BACKUP_EXPIRY_DAYS = 30
TOMBSTONE_RETENTION_DAYS = 30

ALLOWED_DELETION_FAILURE_CODES = frozenset(
    {
        "EXTERNAL_PROVIDER_UNAVAILABLE",
        "EXTERNAL_REVOCATION_FAILED_FINAL",
        "OPERATIONAL_DATA_DELETE_FAILED",
        "CACHE_AND_WORK_DELETE_FAILED",
        "AUDIT_DEIDENTIFICATION_FAILED",
        "BACKUP_EXPIRY_NOT_VERIFIED",
        "OPERATIONAL_DELETE_DEADLINE_EXCEEDED",
    }
)


class AccountStatusCode(StrEnum):
    ACTIVE = "ACTIVE"
    DELETION_PENDING = "DELETION_PENDING"


class DeletionJobStatusCode(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_PENDING = "RETRY_PENDING"
    BACKUP_EXPIRY_PENDING = "BACKUP_EXPIRY_PENDING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE = "COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE"
    FAILED_REQUIRES_REVIEW = "FAILED_REQUIRES_REVIEW"


class DeletionStageCode(StrEnum):
    ACCESS_BLOCK = "ACCESS_BLOCK"
    EXTERNAL_REVOCATION = "EXTERNAL_REVOCATION"
    OPERATIONAL_DATA_DELETE = "OPERATIONAL_DATA_DELETE"
    CACHE_AND_WORK_DELETE = "CACHE_AND_WORK_DELETE"
    AUDIT_DEIDENTIFICATION = "AUDIT_DEIDENTIFICATION"
    BACKUP_EXPIRY_VERIFICATION = "BACKUP_EXPIRY_VERIFICATION"


DELETION_STAGE_ORDER = (
    DeletionStageCode.ACCESS_BLOCK,
    DeletionStageCode.EXTERNAL_REVOCATION,
    DeletionStageCode.OPERATIONAL_DATA_DELETE,
    DeletionStageCode.CACHE_AND_WORK_DELETE,
    DeletionStageCode.AUDIT_DEIDENTIFICATION,
    DeletionStageCode.BACKUP_EXPIRY_VERIFICATION,
)


class ExternalRevocationStatusCode(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED_FINAL = "FAILED_FINAL"


class DeletionCompletionCode(StrEnum):
    ALL_STAGES_COMPLETED = "ALL_STAGES_COMPLETED"
    LOCAL_DELETE_COMPLETED_EXTERNAL_REVOCATION_FAILED = (
        "LOCAL_DELETE_COMPLETED_EXTERNAL_REVOCATION_FAILED"
    )


class EndpointAccessClassCode(StrEnum):
    PUBLIC_UNAUTHENTICATED = "PUBLIC_UNAUTHENTICATED"
    DELETION_LIFECYCLE = "DELETION_LIFECYCLE"
    AUTHENTICATED_PRODUCT = "AUTHENTICATED_PRODUCT"


class RetentionTargetCode(StrEnum):
    USER_IDENTITY_PROFILE = "USER_IDENTITY_PROFILE"
    CONSENT = "CONSENT"
    ROUTINE_CONTEXT = "ROUTINE_CONTEXT"
    DECISION_PROPOSAL = "DECISION_PROPOSAL"
    WORKOUT_FEEDBACK = "WORKOUT_FEEDBACK"
    WEEKLY_PLAN_REPORT = "WEEKLY_PLAN_REPORT"
    INTEGRATION_CONNECTION = "INTEGRATION_CONNECTION"
    IDEMPOTENCY_RECORD = "IDEMPOTENCY_RECORD"
    CACHE_WORK_PAYLOAD = "CACHE_WORK_PAYLOAD"
    REIDENTIFIABLE_AGGREGATE = "REIDENTIFIABLE_AGGREGATE"
    IRREVERSIBLY_ANONYMOUS_AGGREGATE = "IRREVERSIBLY_ANONYMOUS_AGGREGATE"
    OPAQUE_DELETION_AUDIT = "OPAQUE_DELETION_AUDIT"
    RESTORE_BLOCK_TOMBSTONE = "RESTORE_BLOCK_TOMBSTONE"
    BACKUP_RECOVERY_POINT = "BACKUP_RECOVERY_POINT"


class RetentionDispositionCode(StrEnum):
    DELETE_FROM_OPERATIONAL_DATA = "DELETE_FROM_OPERATIONAL_DATA"
    RETAIN_IRREVERSIBLY_ANONYMOUS = "RETAIN_IRREVERSIBLY_ANONYMOUS"
    REQUIRES_APPROVED_RETENTION_POLICY = "REQUIRES_APPROVED_RETENTION_POLICY"
    EXPIRE_RESTORE_BLOCK_TOMBSTONE = "EXPIRE_RESTORE_BLOCK_TOMBSTONE"
    EXPIRE_BACKUP_RECOVERY_POINT = "EXPIRE_BACKUP_RECOVERY_POINT"


class AccountDeletionRuleError(ValueError):
    """Raised when account-deletion input violates the approved policy contract."""


class InvalidDeletionTransitionError(AccountDeletionRuleError):
    """Raised when a deletion job attempts an unsupported state transition."""


class InvalidDeletionAuditError(AccountDeletionRuleError):
    """Raised when a post-delete audit record is not opaque and identifier-free."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AccountDeletionRuleError(f"{field_name} must include timezone information")


def _require_uuid4(value: UUID, *, field_name: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise AccountDeletionRuleError(f"{field_name} must be an opaque UUIDv4")


@dataclass(frozen=True, slots=True)
class DeletionDeadlines:
    requested_at: datetime
    operational_delete_by: datetime
    backup_expiry_due_at: datetime
    tombstone_expires_at: datetime
    policy_version: str = ACCOUNT_DELETION_POLICY_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "requested_at",
            "operational_delete_by",
            "backup_expiry_due_at",
            "tombstone_expires_at",
        ):
            _require_aware(getattr(self, field_name), field_name=field_name)
        if self.operational_delete_by != self.requested_at + timedelta(
            days=OPERATIONAL_DELETE_DEADLINE_DAYS
        ):
            raise AccountDeletionRuleError("operational deletion must be due exactly after 7 days")
        expected_backup_expiry = self.requested_at + timedelta(days=BACKUP_EXPIRY_DAYS)
        if self.backup_expiry_due_at != expected_backup_expiry:
            raise AccountDeletionRuleError("backup recovery points must expire within 30 days")
        if self.tombstone_expires_at != self.requested_at + timedelta(
            days=TOMBSTONE_RETENTION_DAYS
        ):
            raise AccountDeletionRuleError("restore-block tombstones must expire after 30 days")
        if self.policy_version != ACCOUNT_DELETION_POLICY_VERSION:
            raise AccountDeletionRuleError("account deletion policy version must be exact")


def deletion_deadlines(requested_at: datetime) -> DeletionDeadlines:
    """Create immediate-eligibility deadlines; seven days is an upper bound, not a delay."""

    _require_aware(requested_at, field_name="requested_at")
    return DeletionDeadlines(
        requested_at=requested_at,
        operational_delete_by=requested_at + timedelta(days=OPERATIONAL_DELETE_DEADLINE_DAYS),
        backup_expiry_due_at=requested_at + timedelta(days=BACKUP_EXPIRY_DAYS),
        tombstone_expires_at=requested_at + timedelta(days=TOMBSTONE_RETENTION_DAYS),
    )


def account_access_allowed(
    *, account_status_code: AccountStatusCode, access_class_code: EndpointAccessClassCode
) -> bool:
    """Block every user-bound product API immediately after a deletion request."""

    if access_class_code is EndpointAccessClassCode.PUBLIC_UNAUTHENTICATED:
        return True
    if account_status_code is AccountStatusCode.ACTIVE:
        return True
    return access_class_code is EndpointAccessClassCode.DELETION_LIFECYCLE


@dataclass(frozen=True, slots=True)
class DeletionRequestReceipt:
    """Stable resource-level response reused across different idempotency keys."""

    deletion_request_id: UUID
    deletion_job_id: UUID
    status_code: AccountStatusCode
    deadlines: DeletionDeadlines

    def __post_init__(self) -> None:
        _require_uuid4(self.deletion_request_id, field_name="deletion_request_id")
        _require_uuid4(self.deletion_job_id, field_name="deletion_job_id")
        if self.status_code is not AccountStatusCode.DELETION_PENDING:
            raise AccountDeletionRuleError("a deletion receipt must block the account immediately")


def create_deletion_request_receipt(
    *, deletion_request_id: UUID, deletion_job_id: UUID, requested_at: datetime
) -> DeletionRequestReceipt:
    return DeletionRequestReceipt(
        deletion_request_id=deletion_request_id,
        deletion_job_id=deletion_job_id,
        status_code=AccountStatusCode.DELETION_PENDING,
        deadlines=deletion_deadlines(requested_at),
    )


def replay_deletion_request(existing_receipt: DeletionRequestReceipt) -> DeletionRequestReceipt:
    """Return the first receipt even when a pending user supplies a new idempotency key."""

    return existing_receipt


@dataclass(frozen=True, slots=True)
class DeletionJobState:
    status_code: DeletionJobStatusCode
    current_stage_code: DeletionStageCode
    external_revocation_status_code: ExternalRevocationStatusCode
    completed_stage_codes: tuple[DeletionStageCode, ...]
    attempt_count: int
    deadlines: DeletionDeadlines
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt_count, bool)
            or not isinstance(self.attempt_count, int)
            or self.attempt_count < 0
        ):
            raise AccountDeletionRuleError("attempt_count must be a non-negative integer")
        expected_prefix = DELETION_STAGE_ORDER[: len(self.completed_stage_codes)]
        if self.completed_stage_codes != expected_prefix:
            raise AccountDeletionRuleError("completed stages must be a canonical ordered prefix")
        terminal = {
            DeletionJobStatusCode.COMPLETED,
            DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE,
        }
        if self.status_code in terminal:
            if self.completed_stage_codes != DELETION_STAGE_ORDER:
                raise AccountDeletionRuleError("terminal deletion jobs require every stage")
            if self.current_stage_code is not DeletionStageCode.BACKUP_EXPIRY_VERIFICATION:
                raise AccountDeletionRuleError("terminal deletion jobs end at backup verification")
        elif self.current_stage_code in self.completed_stage_codes:
            raise AccountDeletionRuleError("current stage cannot already be completed")
        if self.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING:
            if self.current_stage_code is not DeletionStageCode.BACKUP_EXPIRY_VERIFICATION:
                raise AccountDeletionRuleError("backup pending jobs must await backup verification")
        if self.failure_code is not None:
            if self.failure_code not in ALLOWED_DELETION_FAILURE_CODES:
                raise AccountDeletionRuleError("failure_code must be an allowlisted machine code")


def initial_deletion_job(
    *, requested_at: datetime, external_connection_present: bool
) -> DeletionJobState:
    return DeletionJobState(
        status_code=DeletionJobStatusCode.PENDING,
        current_stage_code=DeletionStageCode.ACCESS_BLOCK,
        external_revocation_status_code=(
            ExternalRevocationStatusCode.PENDING
            if external_connection_present
            else ExternalRevocationStatusCode.NOT_REQUIRED
        ),
        completed_stage_codes=(),
        attempt_count=0,
        deadlines=deletion_deadlines(requested_at),
    )


def start_or_resume_job(state: DeletionJobState) -> DeletionJobState:
    if state.status_code not in {
        DeletionJobStatusCode.PENDING,
        DeletionJobStatusCode.RETRY_PENDING,
        DeletionJobStatusCode.FAILED_REQUIRES_REVIEW,
    }:
        raise InvalidDeletionTransitionError("only pending or reviewable jobs can start")
    return DeletionJobState(
        status_code=DeletionJobStatusCode.RUNNING,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=state.external_revocation_status_code,
        completed_stage_codes=state.completed_stage_codes,
        attempt_count=state.attempt_count + 1,
        deadlines=state.deadlines,
    )


def record_retryable_failure(state: DeletionJobState, *, failure_code: str) -> DeletionJobState:
    if state.status_code is not DeletionJobStatusCode.RUNNING:
        raise InvalidDeletionTransitionError("only a running job can schedule a retry")
    external_status = state.external_revocation_status_code
    if state.current_stage_code is DeletionStageCode.EXTERNAL_REVOCATION:
        external_status = ExternalRevocationStatusCode.RETRY_PENDING
    return DeletionJobState(
        status_code=DeletionJobStatusCode.RETRY_PENDING,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=external_status,
        completed_stage_codes=state.completed_stage_codes,
        attempt_count=state.attempt_count,
        deadlines=state.deadlines,
        failure_code=failure_code,
    )


def record_failure_requiring_review(
    state: DeletionJobState, *, failure_code: str
) -> DeletionJobState:
    if state.status_code not in {
        DeletionJobStatusCode.RUNNING,
        DeletionJobStatusCode.RETRY_PENDING,
    }:
        raise InvalidDeletionTransitionError("only active jobs can require manual review")
    return DeletionJobState(
        status_code=DeletionJobStatusCode.FAILED_REQUIRES_REVIEW,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=state.external_revocation_status_code,
        completed_stage_codes=state.completed_stage_codes,
        attempt_count=state.attempt_count,
        deadlines=state.deadlines,
        failure_code=failure_code,
    )


def complete_current_stage(state: DeletionJobState) -> DeletionJobState:
    """Checkpoint a stage and advance without repeating earlier successful work."""

    if state.status_code is not DeletionJobStatusCode.RUNNING:
        raise InvalidDeletionTransitionError("only a running job can complete a stage")
    stage_index = len(state.completed_stage_codes)
    expected_stage = DELETION_STAGE_ORDER[stage_index]
    if state.current_stage_code is not expected_stage:
        raise InvalidDeletionTransitionError("current stage does not match checkpoint order")
    if expected_stage is DeletionStageCode.EXTERNAL_REVOCATION:
        if state.external_revocation_status_code not in {
            ExternalRevocationStatusCode.NOT_REQUIRED,
            ExternalRevocationStatusCode.SUCCEEDED,
            ExternalRevocationStatusCode.FAILED_FINAL,
        }:
            raise InvalidDeletionTransitionError("external revocation must have a final result")
    completed = (*state.completed_stage_codes, expected_stage)
    if completed == DELETION_STAGE_ORDER:
        raise InvalidDeletionTransitionError(
            "backup verification requires its dedicated transition"
        )
    next_stage = DELETION_STAGE_ORDER[len(completed)]
    next_status = (
        DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
        if next_stage is DeletionStageCode.BACKUP_EXPIRY_VERIFICATION
        else DeletionJobStatusCode.RUNNING
    )
    return DeletionJobState(
        status_code=next_status,
        current_stage_code=next_stage,
        external_revocation_status_code=state.external_revocation_status_code,
        completed_stage_codes=completed,
        attempt_count=state.attempt_count,
        deadlines=state.deadlines,
    )


def record_external_revocation_success(state: DeletionJobState) -> DeletionJobState:
    if (
        state.status_code is not DeletionJobStatusCode.RUNNING
        or state.current_stage_code is not DeletionStageCode.EXTERNAL_REVOCATION
    ):
        raise InvalidDeletionTransitionError("external success requires a running revocation stage")
    return DeletionJobState(
        status_code=state.status_code,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=ExternalRevocationStatusCode.SUCCEEDED,
        completed_stage_codes=state.completed_stage_codes,
        attempt_count=state.attempt_count,
        deadlines=state.deadlines,
    )


def finalize_external_revocation_failure(
    state: DeletionJobState, *, evaluated_at: datetime
) -> DeletionJobState:
    """Stop retaining provider linkage at the operational deletion deadline."""

    _require_aware(evaluated_at, field_name="evaluated_at")
    if (
        state.status_code
        not in {
            DeletionJobStatusCode.RUNNING,
            DeletionJobStatusCode.RETRY_PENDING,
        }
        or state.current_stage_code is not DeletionStageCode.EXTERNAL_REVOCATION
    ):
        raise InvalidDeletionTransitionError("final provider failure requires revocation stage")
    if evaluated_at < state.deadlines.operational_delete_by:
        raise InvalidDeletionTransitionError("provider failure cannot be final before the deadline")
    return DeletionJobState(
        status_code=DeletionJobStatusCode.RUNNING,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=ExternalRevocationStatusCode.FAILED_FINAL,
        completed_stage_codes=state.completed_stage_codes,
        attempt_count=state.attempt_count,
        deadlines=state.deadlines,
        failure_code="EXTERNAL_REVOCATION_FAILED_FINAL",
    )


def verify_backup_expiry(state: DeletionJobState, *, verified_at: datetime) -> DeletionJobState:
    _require_aware(verified_at, field_name="verified_at")
    if (
        state.status_code is not DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
        or state.current_stage_code is not DeletionStageCode.BACKUP_EXPIRY_VERIFICATION
    ):
        raise InvalidDeletionTransitionError("backup verification requires backup pending status")
    if verified_at < state.deadlines.backup_expiry_due_at:
        raise InvalidDeletionTransitionError("backup expiry cannot be verified before its deadline")
    status = (
        DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
        if state.external_revocation_status_code is ExternalRevocationStatusCode.FAILED_FINAL
        else DeletionJobStatusCode.COMPLETED
    )
    return DeletionJobState(
        status_code=status,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=state.external_revocation_status_code,
        completed_stage_codes=DELETION_STAGE_ORDER,
        attempt_count=state.attempt_count,
        deadlines=state.deadlines,
        failure_code=state.failure_code,
    )


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    target_code: RetentionTargetCode
    disposition_code: RetentionDispositionCode
    delete_or_expire_by: datetime | None
    policy_version: str = ACCOUNT_DELETION_POLICY_VERSION


_OPERATIONAL_DELETE_TARGETS = {
    RetentionTargetCode.USER_IDENTITY_PROFILE,
    RetentionTargetCode.CONSENT,
    RetentionTargetCode.ROUTINE_CONTEXT,
    RetentionTargetCode.DECISION_PROPOSAL,
    RetentionTargetCode.WORKOUT_FEEDBACK,
    RetentionTargetCode.WEEKLY_PLAN_REPORT,
    RetentionTargetCode.INTEGRATION_CONNECTION,
    RetentionTargetCode.IDEMPOTENCY_RECORD,
    RetentionTargetCode.CACHE_WORK_PAYLOAD,
    RetentionTargetCode.REIDENTIFIABLE_AGGREGATE,
}


def decide_retention(
    *, target_code: RetentionTargetCode, deadlines: DeletionDeadlines
) -> RetentionDecision:
    if target_code in _OPERATIONAL_DELETE_TARGETS:
        return RetentionDecision(
            target_code=target_code,
            disposition_code=RetentionDispositionCode.DELETE_FROM_OPERATIONAL_DATA,
            delete_or_expire_by=deadlines.operational_delete_by,
        )
    if target_code is RetentionTargetCode.IRREVERSIBLY_ANONYMOUS_AGGREGATE:
        return RetentionDecision(
            target_code=target_code,
            disposition_code=RetentionDispositionCode.RETAIN_IRREVERSIBLY_ANONYMOUS,
            delete_or_expire_by=None,
        )
    if target_code is RetentionTargetCode.OPAQUE_DELETION_AUDIT:
        return RetentionDecision(
            target_code=target_code,
            disposition_code=RetentionDispositionCode.REQUIRES_APPROVED_RETENTION_POLICY,
            delete_or_expire_by=None,
        )
    if target_code is RetentionTargetCode.RESTORE_BLOCK_TOMBSTONE:
        return RetentionDecision(
            target_code=target_code,
            disposition_code=RetentionDispositionCode.EXPIRE_RESTORE_BLOCK_TOMBSTONE,
            delete_or_expire_by=deadlines.tombstone_expires_at,
        )
    return RetentionDecision(
        target_code=target_code,
        disposition_code=RetentionDispositionCode.EXPIRE_BACKUP_RECOVERY_POINT,
        delete_or_expire_by=deadlines.backup_expiry_due_at,
    )


@dataclass(frozen=True, slots=True)
class RestoreBlockTombstone:
    deletion_request_id: UUID
    subject_digest: str
    created_at: datetime
    expires_at: datetime
    policy_version: str = ACCOUNT_DELETION_POLICY_VERSION

    def __post_init__(self) -> None:
        _require_uuid4(self.deletion_request_id, field_name="deletion_request_id")
        _require_aware(self.created_at, field_name="created_at")
        _require_aware(self.expires_at, field_name="expires_at")
        if len(self.subject_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.subject_digest
        ):
            raise AccountDeletionRuleError("subject_digest must be lowercase HMAC-SHA256")
        if self.expires_at != self.created_at + timedelta(days=TOMBSTONE_RETENTION_DAYS):
            raise AccountDeletionRuleError("restore-block tombstone cannot exceed 30 days")


def _subject_digest(*, internal_user_id: UUID, secret: bytes) -> str:
    if not secret:
        raise AccountDeletionRuleError("tombstone secret must not be empty")
    return hmac.new(secret, internal_user_id.bytes, hashlib.sha256).hexdigest()


def create_restore_block_tombstone(
    *, deletion_request_id: UUID, internal_user_id: UUID, secret: bytes, created_at: datetime
) -> RestoreBlockTombstone:
    _require_aware(created_at, field_name="created_at")
    return RestoreBlockTombstone(
        deletion_request_id=deletion_request_id,
        subject_digest=_subject_digest(internal_user_id=internal_user_id, secret=secret),
        created_at=created_at,
        expires_at=created_at + timedelta(days=TOMBSTONE_RETENTION_DAYS),
    )


def tombstone_blocks_restore(
    tombstone: RestoreBlockTombstone,
    *,
    internal_user_id: UUID,
    secret: bytes,
    evaluated_at: datetime,
) -> bool:
    _require_aware(evaluated_at, field_name="evaluated_at")
    if evaluated_at >= tombstone.expires_at:
        return False
    candidate = _subject_digest(internal_user_id=internal_user_id, secret=secret)
    return hmac.compare_digest(tombstone.subject_digest, candidate)


@dataclass(frozen=True, slots=True)
class OpaqueDeletionAuditRecord:
    deletion_request_id: UUID
    deletion_job_id: UUID
    status_code: DeletionJobStatusCode
    current_stage_code: DeletionStageCode
    external_revocation_status_code: ExternalRevocationStatusCode
    completion_code: DeletionCompletionCode | None
    policy_version: str
    attempt_count: int
    requested_at: datetime
    operational_delete_by: datetime
    operational_deleted_at: datetime
    backup_expiry_due_at: datetime
    backup_expiry_verified_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None

    def __post_init__(self) -> None:
        _require_uuid4(self.deletion_request_id, field_name="deletion_request_id")
        _require_uuid4(self.deletion_job_id, field_name="deletion_job_id")
        for field_name in (
            "requested_at",
            "operational_delete_by",
            "operational_deleted_at",
            "backup_expiry_due_at",
        ):
            _require_aware(getattr(self, field_name), field_name=field_name)
        for field_name in ("backup_expiry_verified_at", "completed_at"):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name=field_name)
        if self.policy_version != ACCOUNT_DELETION_POLICY_VERSION:
            raise InvalidDeletionAuditError("opaque audit must retain the deletion policy version")
        if (
            isinstance(self.attempt_count, bool)
            or not isinstance(self.attempt_count, int)
            or self.attempt_count < 0
        ):
            raise InvalidDeletionAuditError("opaque audit attempt_count must be non-negative")
        if self.operational_delete_by != self.requested_at + timedelta(
            days=OPERATIONAL_DELETE_DEADLINE_DAYS
        ):
            raise InvalidDeletionAuditError("opaque audit must retain the exact deletion deadline")
        if self.backup_expiry_due_at != self.requested_at + timedelta(days=BACKUP_EXPIRY_DAYS):
            raise InvalidDeletionAuditError("opaque audit must retain the exact backup deadline")
        if self.operational_deleted_at > self.operational_delete_by:
            raise InvalidDeletionAuditError("operational deletion exceeded the approved deadline")
        expected_completion_codes = {
            DeletionJobStatusCode.COMPLETED: DeletionCompletionCode.ALL_STAGES_COMPLETED,
            DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE: (
                DeletionCompletionCode.LOCAL_DELETE_COMPLETED_EXTERNAL_REVOCATION_FAILED
            ),
        }
        expected_completion_code = expected_completion_codes.get(self.status_code)
        if self.completion_code is not expected_completion_code:
            raise InvalidDeletionAuditError("completion code must match the terminal job status")
        if expected_completion_code is None:
            if self.backup_expiry_verified_at is not None or self.completed_at is not None:
                raise InvalidDeletionAuditError(
                    "non-terminal audit cannot contain completion times"
                )
        elif self.backup_expiry_verified_at is None or self.completed_at is None:
            raise InvalidDeletionAuditError(
                "terminal audit requires backup and completion evidence"
            )
        if (
            self.failure_code is not None
            and self.failure_code not in ALLOWED_DELETION_FAILURE_CODES
        ):
            raise InvalidDeletionAuditError("opaque audit failure code must be allowlisted")


OPAQUE_AUDIT_FIELD_NAMES = frozenset(field.name for field in fields(OpaqueDeletionAuditRecord))

PROHIBITED_POST_DELETE_FIELD_NAMES = frozenset(
    {
        "user_id",
        "firebase_subject",
        "provider_subject",
        "email",
        "full_name",
        "nickname",
        "date_of_birth",
        "protected_birthdate",
        "ip_address",
        "token",
        "authorization",
        "idempotency_key",
        "request_body",
        "response_body",
        "raw_exception",
        "stack_trace",
        "health_snapshot",
    }
)


def validate_opaque_audit_fields(field_names: set[str] | frozenset[str]) -> None:
    """Reject identifier, provider, request, and raw-health fields after hard delete."""

    prohibited = set(field_names) & PROHIBITED_POST_DELETE_FIELD_NAMES
    unknown = set(field_names) - OPAQUE_AUDIT_FIELD_NAMES
    if prohibited or unknown:
        raise InvalidDeletionAuditError("post-delete audit contains non-opaque fields")
