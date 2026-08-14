from datetime import UTC, datetime, timedelta
from uuid import UUID

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
    InvalidDeletionTransitionError,
    RetentionDispositionCode,
    RetentionTargetCode,
    account_access_allowed,
    complete_current_stage,
    create_deletion_request_receipt,
    create_restore_block_tombstone,
    decide_retention,
    finalize_external_revocation_failure,
    initial_deletion_job,
    record_external_revocation_success,
    record_retryable_failure,
    replay_deletion_request,
    start_or_resume_job,
    tombstone_blocks_restore,
    verify_backup_expiry,
)

REQUESTED_AT = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)
REQUEST_ID = UUID("337b2369-9599-4a8f-9648-5a182695188f")
JOB_ID = UUID("f5c285a5-e1c2-4415-b28e-c48a225cbf91")
USER_ID = UUID("3a208cf5-9b17-4ce8-850e-07e993fd6941")


def _advance_to_external_revocation() -> DeletionJobState:
    state = start_or_resume_job(
        initial_deletion_job(requested_at=REQUESTED_AT, external_connection_present=True)
    )
    return complete_current_stage(state)


def _complete_local_stages(state: DeletionJobState) -> DeletionJobState:
    state = complete_current_stage(state)
    state = complete_current_stage(state)
    state = complete_current_stage(state)
    return complete_current_stage(state)


def test_golden_active_user_request_blocks_access_and_is_resource_idempotent() -> None:
    receipt = create_deletion_request_receipt(
        deletion_request_id=REQUEST_ID,
        deletion_job_id=JOB_ID,
        requested_at=REQUESTED_AT,
    )

    replayed_with_new_key = replay_deletion_request(receipt)

    assert receipt.status_code is AccountStatusCode.DELETION_PENDING
    assert replayed_with_new_key is receipt
    assert receipt.deadlines.operational_delete_by == REQUESTED_AT + timedelta(days=7)
    assert (
        account_access_allowed(
            account_status_code=receipt.status_code,
            access_class_code=EndpointAccessClassCode.AUTHENTICATED_PRODUCT,
        )
        is False
    )


def test_golden_provider_failure_retries_then_local_delete_still_meets_deadline() -> None:
    revocation = _advance_to_external_revocation()
    retry_pending = record_retryable_failure(
        revocation, failure_code="EXTERNAL_PROVIDER_UNAVAILABLE"
    )
    retried = start_or_resume_job(retry_pending)
    provider_final = finalize_external_revocation_failure(
        retried, evaluated_at=retried.deadlines.operational_delete_by
    )

    backup_pending = _complete_local_stages(provider_final)

    assert backup_pending.status_code is DeletionJobStatusCode.BACKUP_EXPIRY_PENDING
    assert (
        backup_pending.external_revocation_status_code is ExternalRevocationStatusCode.FAILED_FINAL
    )
    assert DeletionStageCode.OPERATIONAL_DATA_DELETE in backup_pending.completed_stage_codes


def test_golden_operational_deadline_boundary_is_inclusive() -> None:
    revocation = _advance_to_external_revocation()

    with pytest.raises(InvalidDeletionTransitionError, match="before the deadline"):
        finalize_external_revocation_failure(
            revocation,
            evaluated_at=revocation.deadlines.operational_delete_by - timedelta(microseconds=1),
        )

    final_failure = finalize_external_revocation_failure(
        revocation,
        evaluated_at=revocation.deadlines.operational_delete_by,
    )
    assert (
        final_failure.external_revocation_status_code is ExternalRevocationStatusCode.FAILED_FINAL
    )


def test_golden_partial_repository_failure_resumes_at_same_checkpoint() -> None:
    revocation = _advance_to_external_revocation()
    revocation = record_external_revocation_success(revocation)
    operational_delete = complete_current_stage(revocation)
    failed = record_retryable_failure(
        operational_delete, failure_code="OPERATIONAL_DATA_DELETE_FAILED"
    )

    resumed = start_or_resume_job(failed)

    assert resumed.current_stage_code is DeletionStageCode.OPERATIONAL_DATA_DELETE
    assert resumed.completed_stage_codes == (
        DeletionStageCode.ACCESS_BLOCK,
        DeletionStageCode.EXTERNAL_REVOCATION,
    )
    assert DeletionStageCode.OPERATIONAL_DATA_DELETE not in resumed.completed_stage_codes


def test_golden_job_reexecution_preserves_completed_stages() -> None:
    revocation = _advance_to_external_revocation()
    revocation = record_external_revocation_success(revocation)
    operational_delete = complete_current_stage(revocation)
    cache_delete = complete_current_stage(operational_delete)

    assert cache_delete.completed_stage_codes == (
        DeletionStageCode.ACCESS_BLOCK,
        DeletionStageCode.EXTERNAL_REVOCATION,
        DeletionStageCode.OPERATIONAL_DATA_DELETE,
    )
    assert cache_delete.current_stage_code is DeletionStageCode.CACHE_AND_WORK_DELETE


def test_golden_decision_proposal_and_feedback_are_always_deleted() -> None:
    deadlines = create_deletion_request_receipt(
        deletion_request_id=REQUEST_ID,
        deletion_job_id=JOB_ID,
        requested_at=REQUESTED_AT,
    ).deadlines

    for target in (
        RetentionTargetCode.DECISION_PROPOSAL,
        RetentionTargetCode.WORKOUT_FEEDBACK,
        RetentionTargetCode.WEEKLY_PLAN_REPORT,
    ):
        decision = decide_retention(target_code=target, deadlines=deadlines)
        assert decision.disposition_code is RetentionDispositionCode.DELETE_FROM_OPERATIONAL_DATA
        assert decision.delete_or_expire_by == deadlines.operational_delete_by


def test_golden_reidentifiable_aggregate_is_not_treated_as_anonymous() -> None:
    deadlines = create_deletion_request_receipt(
        deletion_request_id=REQUEST_ID,
        deletion_job_id=JOB_ID,
        requested_at=REQUESTED_AT,
    ).deadlines

    reidentifiable = decide_retention(
        target_code=RetentionTargetCode.REIDENTIFIABLE_AGGREGATE,
        deadlines=deadlines,
    )
    anonymous = decide_retention(
        target_code=RetentionTargetCode.IRREVERSIBLY_ANONYMOUS_AGGREGATE,
        deadlines=deadlines,
    )

    assert reidentifiable.delete_or_expire_by == deadlines.operational_delete_by
    assert anonymous.delete_or_expire_by is None


def test_golden_restore_tombstone_blocks_resurrection_only_during_backup_window() -> None:
    secret = b"synthetic-golden-tombstone-key"
    tombstone = create_restore_block_tombstone(
        deletion_request_id=REQUEST_ID,
        internal_user_id=USER_ID,
        secret=secret,
        created_at=REQUESTED_AT,
    )

    assert tombstone.policy_version == ACCOUNT_DELETION_POLICY_VERSION
    assert (
        tombstone_blocks_restore(
            tombstone,
            internal_user_id=USER_ID,
            secret=secret,
            evaluated_at=REQUESTED_AT + timedelta(days=29),
        )
        is True
    )
    assert (
        tombstone_blocks_restore(
            tombstone,
            internal_user_id=USER_ID,
            secret=secret,
            evaluated_at=REQUESTED_AT + timedelta(days=30),
        )
        is False
    )


def test_golden_backup_verification_records_provider_failure_terminal_state() -> None:
    revocation = _advance_to_external_revocation()
    provider_final = finalize_external_revocation_failure(
        revocation, evaluated_at=revocation.deadlines.operational_delete_by
    )
    backup_pending = _complete_local_stages(provider_final)

    completed = verify_backup_expiry(
        backup_pending,
        verified_at=backup_pending.deadlines.backup_expiry_due_at,
    )

    assert completed.status_code is DeletionJobStatusCode.COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE


def test_golden_post_delete_audit_field_contract_contains_no_identifiers_or_snapshots() -> None:
    prohibited_fragments = (
        "user",
        "subject",
        "email",
        "birth",
        "token",
        "idempotency",
        "request_body",
        "snapshot",
        "exception",
    )

    assert not any(
        fragment in field_name
        for field_name in OPAQUE_AUDIT_FIELD_NAMES
        for fragment in prohibited_fragments
    )
