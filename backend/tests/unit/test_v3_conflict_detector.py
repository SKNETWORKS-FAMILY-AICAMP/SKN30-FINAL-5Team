import pytest

from backend.app.domain.agents.v3_conflicts import (
    AgentReviewResult,
    ConflictCode,
    ReviewStatusCode,
    ReviewValidationStatusCode,
    detect_proposal_conflicts,
    validate_agent_reviews,
)
from backend.app.domain.agents.v3_contracts import (
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)
from backend.tests.unit.test_v3_agent_contracts import (
    OUTSIDE,
    A,
    envelope,
    pool,
    prescription,
    proposal,
)
from backend.tests.unit.test_v3_coordinator_contracts import proposals


def replace_proposal(value: SpecialistAgentProposal, **updates: object) -> SpecialistAgentProposal:
    payload = value.model_dump(exclude={"proposal_hash"})
    payload.update(updates)
    return SpecialistAgentProposal.create(**payload)


def test_no_conflict_skips_review_and_result_is_stable() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    canonical = proposals(current_envelope, current_pool)

    first = detect_proposal_conflicts(canonical, current_envelope, current_pool)
    second = detect_proposal_conflicts(
        (canonical[2], canonical[0], canonical[1]), current_envelope, current_pool
    )

    assert first.violations == ()
    assert first.review_target_agent_types == ()
    assert first.result_hash == second.result_hash


@pytest.mark.parametrize(
    ("status", "expected_code"),
    (
        (V3ProposalStatusCode.FAILED, ConflictCode.PROPOSAL_FAILED),
        (V3ProposalStatusCode.NEEDS_INPUT, ConflictCode.PROPOSAL_NEEDS_INPUT),
    ),
)
def test_missing_failed_or_needs_input_prohibits_review_and_coordinator(
    status: V3ProposalStatusCode,
    expected_code: ConflictCode,
) -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    canonical = proposals(current_envelope, current_pool)
    changed = proposal(
        SpecialistAgentTypeCode.RECOVERY,
        current_envelope,
        current_pool,
        status=status,
    )

    missing = detect_proposal_conflicts(canonical[:2], current_envelope, current_pool)
    invalid = detect_proposal_conflicts(
        (canonical[0], changed, canonical[2]), current_envelope, current_pool
    )

    assert ConflictCode.PROPOSAL_MISSING in {item.code for item in missing.violations}
    assert expected_code in {item.code for item in invalid.violations}
    assert missing.review_target_agent_types == ()
    assert invalid.review_target_agent_types == ()


def test_pool_safety_and_recovery_conflicts_are_canonical() -> None:
    current_envelope = envelope(excluded_ids=(OUTSIDE,))
    current_pool = pool(current_envelope)
    unsafe = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(A, 1, sets=4), prescription(OUTSIDE, 2)),
    )
    remaining = proposals(current_envelope, current_pool)[1:]

    result = detect_proposal_conflicts((unsafe, *remaining), current_envelope, current_pool)
    codes = tuple(item.code for item in result.violations)

    assert ConflictCode.EXERCISE_OUTSIDE_POOL in codes
    assert ConflictCode.SAFETY_EXCLUDED_EXERCISE_INCLUDED in codes
    assert ConflictCode.RECOVERY_CEILING_EXCEEDED in codes
    assert result.review_target_agent_types == (SpecialistAgentTypeCode.TRAINING,)


def test_location_equipment_and_structured_plan_disagreement_are_detected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    canonical = proposals(current_envelope, current_pool)
    disallowed = prescription(A, 1).model_copy(
        update={"location_code": "GYM", "equipment_codes": ("DUMBBELL",)}
    )
    feasibility = proposal(
        SpecialistAgentTypeCode.FEASIBILITY,
        current_envelope,
        current_pool,
        prescriptions=(disallowed,),
    )

    result = detect_proposal_conflicts(
        (canonical[0], canonical[1], feasibility), current_envelope, current_pool
    )
    codes = {item.code for item in result.violations}

    assert ConflictCode.LOCATION_NOT_ALLOWED in codes
    assert ConflictCode.EQUIPMENT_NOT_AVAILABLE in codes
    assert ConflictCode.STRUCTURED_PROPOSALS_INCOMPATIBLE in codes
    assert result.review_target_agent_types == (
        SpecialistAgentTypeCode.TRAINING,
        SpecialistAgentTypeCode.FEASIBILITY,
    )


def test_only_affected_agent_is_reviewed_once_and_hard_constraints_are_preserved() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    canonical = proposals(current_envelope, current_pool)
    invalid_training = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(A, 1, sets=4),),
    )
    round_one = (invalid_training, canonical[1], canonical[2])
    conflicts = detect_proposal_conflicts(round_one, current_envelope, current_pool)
    revised = canonical[0]
    review = AgentReviewResult.create(
        agent_type_code=SpecialistAgentTypeCode.TRAINING,
        status_code=ReviewStatusCode.READY,
        baseline_proposal_hash=invalid_training.proposal_hash,
        reviewed_conflict_codes=("RECOVERY_CEILING_EXCEEDED",),
        revised_proposal=revised,
    )

    result = validate_agent_reviews(round_one, conflicts, (review,), current_envelope, current_pool)

    assert conflicts.review_target_agent_types == (SpecialistAgentTypeCode.TRAINING,)
    assert result.status_code is ReviewValidationStatusCode.READY
    assert result.effective_proposals[0] == revised


def test_non_target_review_and_hard_constraint_relaxation_are_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    canonical = proposals(current_envelope, current_pool)
    no_conflicts = detect_proposal_conflicts(canonical, current_envelope, current_pool)
    unnecessary = AgentReviewResult.create(
        agent_type_code=SpecialistAgentTypeCode.RECOVERY,
        status_code=ReviewStatusCode.READY,
        baseline_proposal_hash=canonical[1].proposal_hash,
        reviewed_conflict_codes=("RECOVERY_CEILING_EXCEEDED",),
        revised_proposal=canonical[1],
    )
    invalid_target_set = validate_agent_reviews(
        canonical, no_conflicts, (unnecessary,), current_envelope, current_pool
    )

    invalid_training = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(A, 1, sets=4),),
    )
    round_one = (invalid_training, canonical[1], canonical[2])
    conflicts = detect_proposal_conflicts(round_one, current_envelope, current_pool)
    relaxed = replace_proposal(canonical[0], hard_constraint_codes=())
    review = AgentReviewResult.create(
        agent_type_code=SpecialistAgentTypeCode.TRAINING,
        status_code=ReviewStatusCode.READY,
        baseline_proposal_hash=invalid_training.proposal_hash,
        reviewed_conflict_codes=("RECOVERY_CEILING_EXCEEDED",),
        revised_proposal=relaxed,
    )
    relaxed_result = validate_agent_reviews(
        round_one, conflicts, (review,), current_envelope, current_pool
    )

    assert invalid_target_set.status_code is ReviewValidationStatusCode.FAILED
    assert relaxed_result.failure_codes == ("REVIEW_HARD_CONSTRAINT_RELAXED",)


@pytest.mark.parametrize(
    ("status", "expected_status"),
    (
        (ReviewStatusCode.FAILED, ReviewValidationStatusCode.FAILED),
        (ReviewStatusCode.NEEDS_INPUT, ReviewValidationStatusCode.NEEDS_INPUT),
    ),
)
def test_failed_or_needs_input_review_never_exposes_partial_proposals(
    status: ReviewStatusCode,
    expected_status: ReviewValidationStatusCode,
) -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    canonical = proposals(current_envelope, current_pool)
    invalid_training = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(A, 1, sets=4),),
    )
    round_one = (invalid_training, canonical[1], canonical[2])
    conflicts = detect_proposal_conflicts(round_one, current_envelope, current_pool)
    review = AgentReviewResult.create(
        agent_type_code=SpecialistAgentTypeCode.TRAINING,
        status_code=status,
        baseline_proposal_hash=invalid_training.proposal_hash,
        reviewed_conflict_codes=("RECOVERY_CEILING_EXCEEDED",),
    )

    result = validate_agent_reviews(round_one, conflicts, (review,), current_envelope, current_pool)

    assert result.status_code is expected_status
    assert result.effective_proposals == ()
