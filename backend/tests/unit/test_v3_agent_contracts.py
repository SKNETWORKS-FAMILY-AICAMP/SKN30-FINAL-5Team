import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    RetrievalMetadata,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    ExercisePrescription,
    LLMInvocationMetadata,
    LLMInvocationStatusCode,
    RecoveryCeiling,
    SpecialistAgentInput,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)

A = UUID("00000000-0000-0000-0000-000000000001")
B = UUID("00000000-0000-0000-0000-000000000002")
C = UUID("00000000-0000-0000-0000-000000000003")
# A fourth pool member so a plan can close with a cooldown without occupying an
# id that exclusion tests need free.
D = UUID("00000000-0000-0000-0000-000000000004")
OUTSIDE = UUID("00000000-0000-0000-0000-000000000099")
QUERY_HASH = "b" * 64


def exercise(exercise_id: UUID) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=exercise_id,
        catalog_version="catalog-v3",
        content_version=f"content-{exercise_id.int}",
        stable_code=f"exercise-{exercise_id.int}",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=("PUSH",),
        difficulty_code="BEGINNER",
        timing_mode_code="REPS",
        default_seconds_per_rep=3,
        default_rest_seconds=30,
        default_transition_seconds=15,
        recovery_eligible=True,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=("BODYWEIGHT",),
        location_codes=("HOME",),
        prescription_reference_codes=("prescription-v1",),
        source_reference_codes=("source-v1",),
        review_reference_codes=("review-v1",),
    )


def envelope(
    *,
    excluded_ids: tuple[UUID, ...] = (),
    mandatory_ids: tuple[UUID, ...] = (A,),
    # Production sends an empty tuple: the 2026-08-27 approval dropped
    # equipment from onboarding, so a real user has no UserEquipment rows.
    # The default here stays non-empty for the older cases, but every gate
    # that reads it has to be exercised with () as well.
    allowed_equipment_codes: tuple[str, ...] = ("BODYWEIGHT",),
) -> ConstraintEnvelope:
    return ConstraintEnvelope.create(
        requested_duration_minutes=6,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=allowed_equipment_codes,
        excluded_exercise_ids=excluded_ids,
        mandatory_exercise_ids=mandatory_ids,
        recovery_ceiling=RecoveryCeiling(
            policy_version="recovery-policy-v1",
            allowed_intensity_codes=("LOW", "MODERATE"),
            allowed_load_codes=("BODYWEIGHT",),
            maximum_sets_per_exercise=3,
            maximum_repetitions_per_set=12,
            maximum_work_seconds_per_set=60,
            minimum_rest_seconds_between_sets=30,
        ),
        plan_generation_allowed=True,
        policy_version="decision-policy-v3",
        catalog_version="catalog-v3",
        safety_rule_version="safety-rules-v3",
    )


def pool(current_envelope: ConstraintEnvelope) -> ExercisePoolSnapshot:
    records = tuple(exercise(value) for value in (A, B, C, D))
    return ExercisePoolSnapshot.create(
        catalog_version="catalog-v3",
        constraint_envelope_hash=current_envelope.envelope_hash,
        exercises=records,
        mandatory_exercise_ids=(A,),
        vector_ranked_exercise_ids=(B, C, D),
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


def prescription(
    exercise_id: UUID,
    sequence: int,
    *,
    sets: int = 3,
    intensity_code: str = "MODERATE",
    phase_code: str = "MAIN",
) -> ExercisePrescription:
    return ExercisePrescription(
        exercise_id=exercise_id,
        sequence=sequence,
        phase_code=phase_code,
        sets=sets,
        repetitions_per_set=10,
        rest_seconds_between_sets=30,
        transition_seconds=15,
        intensity_code=intensity_code,
        load_code="BODYWEIGHT",
        location_code="HOME",
        equipment_codes=("BODYWEIGHT",),
    )


def proposal(
    agent_type: SpecialistAgentTypeCode,
    current_envelope: ConstraintEnvelope,
    current_pool: ExercisePoolSnapshot,
    *,
    status: V3ProposalStatusCode = V3ProposalStatusCode.READY,
    prescriptions: tuple[ExercisePrescription, ...] | None = None,
    requested_duration_minutes: int = 6,
) -> SpecialistAgentProposal:
    if prescriptions is None:
        prescriptions = (
            (prescription(A, 1), prescription(B, 2))
            if agent_type is SpecialistAgentTypeCode.TRAINING
            else ()
        )
    ready = status is V3ProposalStatusCode.READY
    return SpecialistAgentProposal.create(
        agent_type_code=agent_type,
        proposal_status_code=status,
        envelope_hash=current_envelope.envelope_hash,
        pool_hash=current_pool.pool_hash,
        requested_duration_minutes=requested_duration_minutes,
        estimated_duration_seconds=requested_duration_minutes * 60 if ready else None,
        exercise_prescriptions=prescriptions,
        adjustment_codes=(
            ()
            if agent_type is SpecialistAgentTypeCode.TRAINING or not ready
            else (f"{agent_type.value}_CONSTRAINTS_PRESERVED",)
        ),
        hard_constraint_codes=("DURATION_PRESERVED",),
        reason_codes=("GOAL_PRESERVED",),
        evidence_reference_codes=("ENVELOPE", "POOL"),
        public_summary_code=(f"{agent_type.value}_READY" if ready else None),
    )


def agent_input(
    agent_type: SpecialistAgentTypeCode,
    current_envelope: ConstraintEnvelope,
    current_pool: ExercisePoolSnapshot,
) -> SpecialistAgentInput:
    return SpecialistAgentInput(
        agent_type_code=agent_type,
        constraint_envelope=current_envelope,
        envelope_hash=current_envelope.envelope_hash,
        exercise_pool=current_pool,
        pool_hash=current_pool.pool_hash,
    )


@pytest.mark.parametrize("agent_type", tuple(SpecialistAgentTypeCode))
def test_three_specialist_inputs_and_proposals_are_valid(
    agent_type: SpecialistAgentTypeCode,
) -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = agent_input(agent_type, current_envelope, current_pool)
    current_proposal = proposal(agent_type, current_envelope, current_pool)

    current_input.validate_proposal(current_proposal)

    assert current_input.schema_version == "specialist-agent-input-v1"
    assert current_proposal.schema_version == "specialist-agent-proposal-v1"


@pytest.mark.parametrize(
    "agent_type",
    (
        SpecialistAgentTypeCode.RECOVERY,
        SpecialistAgentTypeCode.FEASIBILITY,
    ),
)
def test_advisory_specialists_cannot_submit_exercise_prescriptions(
    agent_type: SpecialistAgentTypeCode,
) -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(
        ValidationError,
        match="only TRAINING proposals may include exercise_prescriptions",
    ):
        proposal(
            agent_type,
            current_envelope,
            current_pool,
            prescriptions=(prescription(A, 1),),
        )


def test_safety_agent_type_is_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(ValidationError):
        SpecialistAgentInput(
            agent_type_code="SAFETY",
            constraint_envelope=current_envelope,
            envelope_hash=current_envelope.envelope_hash,
            exercise_pool=current_pool,
            pool_hash=current_pool.pool_hash,
        )


def test_role_mismatch_is_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(ValueError, match="role"):
        agent_input(
            SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool
        ).validate_proposal(
            proposal(SpecialistAgentTypeCode.RECOVERY, current_envelope, current_pool)
        )


def test_pool_outside_exercise_id_is_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    outside_proposal = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(OUTSIDE, 1),),
    )

    with pytest.raises(ValueError, match="outside ExercisePoolSnapshot"):
        agent_input(
            SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool
        ).validate_proposal(outside_proposal)


def test_duplicate_exercise_id_is_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(ValidationError, match="duplicate exercise IDs"):
        proposal(
            SpecialistAgentTypeCode.TRAINING,
            current_envelope,
            current_pool,
            prescriptions=(prescription(A, 1), prescription(A, 2)),
        )


def test_envelope_and_pool_hash_mismatch_is_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(ValidationError, match="envelope_hash"):
        SpecialistAgentInput(
            agent_type_code=SpecialistAgentTypeCode.TRAINING,
            constraint_envelope=current_envelope,
            envelope_hash="f" * 64,
            exercise_pool=current_pool,
            pool_hash=current_pool.pool_hash,
        )
    with pytest.raises(ValidationError, match="pool_hash"):
        SpecialistAgentInput(
            agent_type_code=SpecialistAgentTypeCode.TRAINING,
            constraint_envelope=current_envelope,
            envelope_hash=current_envelope.envelope_hash,
            exercise_pool=current_pool,
            pool_hash="f" * 64,
        )


def test_proposal_cannot_change_requested_duration() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    changed = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        requested_duration_minutes=29,
    )

    with pytest.raises(ValueError, match="requested duration"):
        agent_input(
            SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool
        ).validate_proposal(changed)


def test_envelope_and_proposal_hashes_are_stable() -> None:
    first_envelope = envelope()
    second_envelope = envelope()
    first_pool = pool(first_envelope)
    second_pool = pool(second_envelope)
    first_proposal = proposal(SpecialistAgentTypeCode.TRAINING, first_envelope, first_pool)
    second_proposal = proposal(SpecialistAgentTypeCode.TRAINING, second_envelope, second_pool)

    assert first_envelope.envelope_hash == second_envelope.envelope_hash
    assert first_proposal.proposal_hash == second_proposal.proposal_hash


def test_extra_sensitive_fields_and_raw_prompt_metadata_are_rejected() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    with pytest.raises(ValidationError, match="Extra inputs"):
        SpecialistAgentInput(
            agent_type_code=SpecialistAgentTypeCode.TRAINING,
            constraint_envelope=current_envelope,
            envelope_hash=current_envelope.envelope_hash,
            exercise_pool=current_pool,
            pool_hash=current_pool.pool_hash,
            user_id="forbidden",
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        LLMInvocationMetadata(
            provider_code="OPENAI",
            model_version="model-v1",
            prompt_version="prompt-v1",
            output_schema_version="specialist-agent-proposal-v1",
            attempt=0,
            status_code=LLMInvocationStatusCode.SUCCEEDED,
            latency_ms=100,
            prompt_text="forbidden",
        )


def test_v3_contract_module_has_no_framework_or_infrastructure_imports() -> None:
    module_path = Path(__file__).parents[2] / "app" / "domain" / "agents" / "v3_contracts.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_roots = {
        "fastapi",
        "langchain",
        "langgraph",
        "qdrant_client",
        "sqlalchemy",
    }
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)
