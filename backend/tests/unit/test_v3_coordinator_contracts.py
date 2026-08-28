from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.retrieval import (
    ExercisePoolSnapshot,
    RetrievalMetadata,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    CoordinatorInput,
    ExercisePrescription,
    PlanActionCode,
    PlanSpec,
    ProposalReference,
    RecoveryCeiling,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.tests.unit.test_v3_agent_contracts import (
    QUERY_HASH,
    A,
    B,
    C,
    envelope,
    exercise,
    pool,
    prescription,
    proposal,
)


def proposals(
    current_envelope: ConstraintEnvelope,
    current_pool: ExercisePoolSnapshot,
) -> tuple[SpecialistAgentProposal, ...]:
    return tuple(
        proposal(agent_type, current_envelope, current_pool)
        for agent_type in (
            SpecialistAgentTypeCode.TRAINING,
            SpecialistAgentTypeCode.RECOVERY,
            SpecialistAgentTypeCode.FEASIBILITY,
        )
    )


def coordinator_input(
    current_envelope: ConstraintEnvelope,
    current_pool: ExercisePoolSnapshot,
    *,
    current_proposals: tuple[SpecialistAgentProposal, ...] | None = None,
    repair_attempt: int = 0,
    repair_codes: tuple[str, ...] = (),
) -> CoordinatorInput:
    return CoordinatorInput(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=(
            proposals(current_envelope, current_pool)
            if current_proposals is None
            else current_proposals
        ),
        repair_attempt=repair_attempt,
        repair_violation_codes=repair_codes,
    )


def plan(
    current_input: CoordinatorInput,
    *,
    requested_duration_minutes: int = 6,
    plan_prescriptions: tuple[ExercisePrescription, ...] | None = None,
    repair_attempt: int | None = None,
) -> PlanSpec:
    if plan_prescriptions is None:
        plan_prescriptions = (prescription(A, 1), prescription(B, 2))
    return PlanSpec.create(
        envelope_hash=current_input.constraint_envelope.envelope_hash,
        pool_hash=current_input.exercise_pool.pool_hash,
        action_code=PlanActionCode.KEEP,
        requested_duration_minutes=requested_duration_minutes,
        estimated_duration_seconds=requested_duration_minutes * 60,
        exercise_prescriptions=plan_prescriptions,
        proposal_references=tuple(
            ProposalReference(
                agent_type_code=item.agent_type_code,
                proposal_hash=item.proposal_hash,
            )
            for item in current_input.proposals
        ),
        repair_attempt=(current_input.repair_attempt if repair_attempt is None else repair_attempt),
        decision_codes=("ALL_CONSTRAINTS_PRESERVED",),
        public_summary_code="PLAN_READY",
    )


def test_coordinator_accepts_canonical_three_proposal_input_and_one_plan() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    current_plan = plan(current_input)

    current_plan.validate_against(current_input)

    assert current_input.schema_version == "v3-coordinator-input-v1"
    assert current_plan.schema_version == "plan-spec-v1"


def test_missing_or_noncanonical_proposals_are_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    valid = proposals(current_envelope, current_pool)

    with pytest.raises(ValidationError, match="canonical role order"):
        coordinator_input(current_envelope, current_pool, current_proposals=valid[:2])
    with pytest.raises(ValidationError, match="canonical role order"):
        coordinator_input(
            current_envelope,
            current_pool,
            current_proposals=(valid[1], valid[0], valid[2]),
        )


def test_failed_proposal_blocks_coordinator_input() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    valid = proposals(current_envelope, current_pool)
    failed = proposal(
        SpecialistAgentTypeCode.RECOVERY,
        current_envelope,
        current_pool,
        status=V3ProposalStatusCode.FAILED,
    )

    with pytest.raises(ValidationError, match="non-ready"):
        coordinator_input(
            current_envelope,
            current_pool,
            current_proposals=(valid[0], failed, valid[2]),
        )


def test_repair_attempt_two_or_more_is_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(ValidationError):
        coordinator_input(
            current_envelope,
            current_pool,
            repair_attempt=2,
            repair_codes=("DURATION_MISMATCH",),
        )


def test_plan_cannot_reference_exercise_outside_pool() -> None:
    current_envelope = envelope()
    # Construct a pool without C, then let a PlanSpec attempt to reference C.
    reduced_pool = ExercisePoolSnapshot.create(
        catalog_version="catalog-v3",
        constraint_envelope_hash=current_envelope.envelope_hash,
        exercises=(exercise(A), exercise(B)),
        mandatory_exercise_ids=(A,),
        vector_ranked_exercise_ids=(B,),
        retrieval_metadata=RetrievalMetadata(
            collection_name="exercise-catalog-v3",
            vector_index_version="vector-index-v3",
            embedding_model_version="embedding-v3",
            query_hash=QUERY_HASH,
            retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
            deterministic_pool_fallback_used=False,
        ),
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )
    reduced_input = coordinator_input(current_envelope, reduced_pool)
    outside_plan = plan(
        reduced_input,
        plan_prescriptions=(prescription(A, 1), prescription(C, 2)),
    )

    with pytest.raises(ValueError, match="outside ExercisePoolSnapshot"):
        outside_plan.validate_against(reduced_input)


def test_plan_cannot_change_requested_duration() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    changed = plan(current_input, requested_duration_minutes=5)

    with pytest.raises(ValueError, match="requested duration"):
        changed.validate_against(current_input)


def test_recovery_ceiling_cannot_be_relaxed() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    over_ceiling = plan(
        current_input,
        plan_prescriptions=(prescription(A, 1, sets=4), prescription(B, 2)),
    )

    with pytest.raises(ValueError, match="Recovery sets ceiling"):
        over_ceiling.validate_against(current_input)


def test_safety_exclusion_cannot_be_relaxed() -> None:
    current_envelope = envelope(excluded_ids=(C,))
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    unsafe = plan(
        current_input,
        plan_prescriptions=(prescription(A, 1), prescription(C, 2)),
    )

    with pytest.raises(ValueError, match="Safety exclusions"):
        unsafe.validate_against(current_input)


@pytest.mark.parametrize(
    "required_action",
    (
        SafetyRequiredActionCode.REST,
        SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
    ),
)
def test_rest_or_stop_envelope_cannot_enter_coordinator(
    required_action: SafetyRequiredActionCode,
) -> None:
    blocked = ConstraintEnvelope.create(
        requested_duration_minutes=6,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=("BODYWEIGHT",),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=RecoveryCeiling(policy_version="recovery-policy-v1"),
        plan_generation_allowed=False,
        safety_required_action_code=required_action,
        policy_version="decision-policy-v3",
        catalog_version="catalog-v3",
        safety_rule_version="safety-rules-v3",
    )
    blocked_pool = pool(blocked)
    allowed = envelope()
    allowed_pool = pool(allowed)

    with pytest.raises(ValidationError, match="plan generation"):
        CoordinatorInput(
            constraint_envelope=blocked,
            exercise_pool=blocked_pool,
            proposals=proposals(allowed, allowed_pool),
            repair_attempt=0,
        )


def test_plan_hash_and_canonical_proposal_order_are_stable() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)

    first = plan(current_input)
    second = plan(current_input)

    assert first.plan_hash == second.plan_hash
    assert tuple(ref.agent_type_code for ref in first.proposal_references) == (
        SpecialistAgentTypeCode.TRAINING,
        SpecialistAgentTypeCode.RECOVERY,
        SpecialistAgentTypeCode.FEASIBILITY,
    )
