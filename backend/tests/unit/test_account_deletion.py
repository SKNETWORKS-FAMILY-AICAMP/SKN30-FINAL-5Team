from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.domain.rules.account_deletion import (
    ACCOUNT_DELETION_POLICY_VERSION,
    OPAQUE_AUDIT_FIELD_NAMES,
    AccountStatusCode,
    DeletionJobState,
    DeletionJobStatusCode,
    DeletionStageCode,
    EndpointAccessClassCode,
    ExternalRevocationStatusCode,
    InvalidDeletionAuditError,
    InvalidDeletionTransitionError,
    OpaqueDeletionAuditRecord,
    RetentionDispositionCode,
    RetentionTargetCode,
    account_access_allowed,
    complete_current_stage,
    create_restore_block_tombstone,
    decide_retention,
    deletion_deadlines,
    finalize_external_revocation_failure,
    initial_deletion_job,
    record_external_revocation_success,
    record_retryable_failure,
    start_or_resume_job,
    tombstone_blocks_restore,
    validate_opaque_audit_fields,
    verify_backup_expiry,
)

REQUESTED_AT = datetime(2026, 8, 14, 1, 30, tzinfo=UTC)


def _advance_to_backup_pending(*, provider_failed: bool = False) -> DeletionJobState:
    state = start_or_resume_job(
        initial_deletion_job(requested_at=REQUESTED_AT, external_connection_present=True)
    )
    state = complete_current_stage(state)
    if provider_failed:
        state = finalize_external_revocation_failure(
            state, evaluated_at=state.deadlines.operational_delete_by
        )
    else:
        state = record_external_revocation_success(state)
    state = complete_current_stage(state)
    state = complete_current_stage(state)
    state = complete_current_stage(state)
    return complete_current_stage(state)


def test_deletion_is_immediately_eligible_with_seven_and_thirty_day_deadlines() -> None:
    deadlines = deletion_deadlines(REQUESTED_AT)

    assert deadlines.requested_at == REQUESTED_AT
    assert deadlines.operational_delete_by == REQUESTED_AT + timedelta(days=7)
    assert deadlines.backup_expiry_due_at == REQUESTED_AT + timedelta(days=30)
    assert deadlines.tombstone_expires_at == REQUESTED_AT + timedelta(days=30)
    assert deadlines.policy_version == ACCOUNT_DELETION_POLICY_VERSION


def test_deletion_pending_blocks_product_access_but_allows_lifecycle_replay() -> None:
    assert (
        account_access_allowed(
            account_status_code=AccountStatusCode.DELETION_PENDING,
            access_class_code=EndpointAccessClassCode.AUTHENTICATED_PRODUCT,
        )
        is False
    )
    assert (
        account_access_allowed(
            account_status_code=AccountStatusCode.DELETION_PENDING,
            access_class_code=EndpointAccessClassCode.DELETION_LIFECYCLE,
        )
        is True
    )
    assert (
        account_access_allowed(
            account_status_code=AccountStatusCode.DELETION_PENDING,
            access_class_code=EndpointAccessClassCode.PUBLIC_UNAUTHENTICATED,
        )
        is True
    )


def test_retry_resumes_failed_stage_without_losing_checkpoint() -> None:
    state = start_or_resume_job(
        initial_deletion_job(requested_at=REQUESTED_AT, external_connection_present=True)
    )
    state = complete_current_stage(state)
    failed = record_retryable_failure(state, failure_code="EXTERNAL_PROVIDER_UNAVAILABLE")
    resumed = start_or_resume_job(failed)

    assert failed.status_code is DeletionJobStatusCode.RETRY_PENDING
    assert failed.external_revocation_status_code is ExternalRevocationStatusCode.RETRY_PENDING
    assert resumed.status_code is DeletionJobStatusCode.RUNNING
    assert resumed.current_stage_code is DeletionStageCode.EXTERNAL_REVOCATION
    assert resumed.completed_stage_codes == (DeletionStageCode.ACCESS_BLOCK,)
    assert resumed.attempt_count == 2


def test_provider_failure_cannot_be_final_before_operational_deadline() -> None:
    state = start_or_resume_job(
        initial_deletion_job(requested_at=REQUESTED_AT, external_connection_present=True)
    )
    state = complete_current_stage(state)

    with pytest.raises(InvalidDeletionTransitionError, match="before the deadline"):
        finalize_external_revocation_failure(
            state,
            evaluated_at=state.deadlines.operational_delete_by - timedelta(microseconds=1),
        )

    final_failure = finalize_external_revocation_failure(
        state, evaluated_at=state.deadlines.operational_delete_by
    )
    assert (
        final_failure.external_revocation_status_code is ExternalRevocationStatusCode.FAILED_FINAL
    )


def test_backup_verification_selects_terminal_state_from_provider_result() -> None:
    succeeded = _advance_to_backup_pending(provider_failed=False)
    failed = _advance_to_backup_pending(provider_failed=True)

    with pytest.raises(InvalidDeletionTransitionError, match="before its deadline"):
        verify_backup_expiry(
            succeeded,
            verified_at=succeeded.deadlines.backup_expiry_due_at - timedelta(microseconds=1),
        )

    completed = verify_backup_expiry(
        succeeded, verified_at=succeeded.deadlines.backup_expiry_due_at
    )
    completed_with_failure = verify_backup_expiry(
        failed, verified_at=failed.deadlines.backup_expiry_due_at
    )

    assert completed.status_code is DeletionJobStatusCode.COMPLETED
    assert (
        completed_with_failure.status_code
        is DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
    )


@pytest.mark.parametrize(
    "target_code",
    [
        RetentionTargetCode.USER_IDENTITY_PROFILE,
        RetentionTargetCode.DECISION_PROPOSAL,
        RetentionTargetCode.WORKOUT_FEEDBACK,
        RetentionTargetCode.IDEMPOTENCY_RECORD,
        RetentionTargetCode.REIDENTIFIABLE_AGGREGATE,
    ],
)
def test_user_linked_and_reidentifiable_data_delete_by_operational_deadline(
    target_code: RetentionTargetCode,
) -> None:
    deadlines = deletion_deadlines(REQUESTED_AT)

    decision = decide_retention(target_code=target_code, deadlines=deadlines)

    assert decision.disposition_code is RetentionDispositionCode.DELETE_FROM_OPERATIONAL_DATA
    assert decision.delete_or_expire_by == deadlines.operational_delete_by


def test_only_irreversibly_anonymous_aggregate_can_be_retained_without_deadline() -> None:
    deadlines = deletion_deadlines(REQUESTED_AT)

    anonymous = decide_retention(
        target_code=RetentionTargetCode.IRREVERSIBLY_ANONYMOUS_AGGREGATE,
        deadlines=deadlines,
    )
    reidentifiable = decide_retention(
        target_code=RetentionTargetCode.REIDENTIFIABLE_AGGREGATE,
        deadlines=deadlines,
    )

    assert anonymous.disposition_code is RetentionDispositionCode.RETAIN_IRREVERSIBLY_ANONYMOUS
    assert anonymous.delete_or_expire_by is None
    assert reidentifiable.disposition_code is RetentionDispositionCode.DELETE_FROM_OPERATIONAL_DATA


def test_keyed_tombstone_blocks_only_matching_restore_for_thirty_days() -> None:
    request_id = uuid4()
    user_id = uuid4()
    secret = b"synthetic-test-only-tombstone-key"
    tombstone = create_restore_block_tombstone(
        deletion_request_id=request_id,
        internal_user_id=user_id,
        secret=secret,
        created_at=REQUESTED_AT,
    )

    assert tombstone.subject_digest != str(user_id)
    assert (
        tombstone_blocks_restore(
            tombstone,
            internal_user_id=user_id,
            secret=secret,
            evaluated_at=tombstone.expires_at - timedelta(microseconds=1),
        )
        is True
    )
    assert (
        tombstone_blocks_restore(
            tombstone,
            internal_user_id=uuid4(),
            secret=secret,
            evaluated_at=REQUESTED_AT,
        )
        is False
    )
    assert (
        tombstone_blocks_restore(
            tombstone,
            internal_user_id=user_id,
            secret=secret,
            evaluated_at=tombstone.expires_at,
        )
        is False
    )


def test_post_delete_audit_schema_contains_no_direct_or_provider_identifiers() -> None:
    prohibited = {
        "user_id",
        "provider_subject",
        "firebase_subject",
        "email",
        "date_of_birth",
        "protected_birthdate",
        "idempotency_key",
        "raw_exception",
        "health_snapshot",
    }

    assert not OPAQUE_AUDIT_FIELD_NAMES & prohibited
    assert {field.name for field in fields(OpaqueDeletionAuditRecord)} == OPAQUE_AUDIT_FIELD_NAMES
    validate_opaque_audit_fields(OPAQUE_AUDIT_FIELD_NAMES)
    with pytest.raises(InvalidDeletionAuditError, match="non-opaque"):
        validate_opaque_audit_fields(OPAQUE_AUDIT_FIELD_NAMES | {"user_id"})


def test_opaque_audit_retention_requires_a_separately_approved_policy() -> None:
    state = _advance_to_backup_pending(provider_failed=False)
    retention = decide_retention(
        target_code=RetentionTargetCode.OPAQUE_DELETION_AUDIT,
        deadlines=state.deadlines,
    )
    audit = OpaqueDeletionAuditRecord(
        deletion_request_id=uuid4(),
        deletion_job_id=uuid4(),
        status_code=state.status_code,
        current_stage_code=state.current_stage_code,
        external_revocation_status_code=state.external_revocation_status_code,
        completion_code=None,
        policy_version=ACCOUNT_DELETION_POLICY_VERSION,
        attempt_count=state.attempt_count,
        requested_at=REQUESTED_AT,
        operational_delete_by=state.deadlines.operational_delete_by,
        operational_deleted_at=REQUESTED_AT + timedelta(hours=1),
        backup_expiry_due_at=state.deadlines.backup_expiry_due_at,
        backup_expiry_verified_at=None,
        completed_at=None,
        failure_code=None,
    )

    assert audit.policy_version == ACCOUNT_DELETION_POLICY_VERSION
    assert retention.disposition_code is RetentionDispositionCode.REQUIRES_APPROVED_RETENTION_POLICY
    assert retention.delete_or_expire_by is None
    with pytest.raises(InvalidDeletionAuditError, match="completion code"):
        replace(audit, status_code=DeletionJobStatusCode.COMPLETED)
    with pytest.raises(InvalidDeletionAuditError, match="exceeded"):
        replace(
            audit,
            operational_deleted_at=audit.operational_delete_by + timedelta(microseconds=1),
        )
