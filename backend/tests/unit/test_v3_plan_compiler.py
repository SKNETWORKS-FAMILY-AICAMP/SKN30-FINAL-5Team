import pytest

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import (
    DURATION_VERIFICATION_CODE,
    DeterministicFallbackPlanSpec,
    compile_plan,
)
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, PlanActionCode
from backend.tests.unit.test_v3_agent_contracts import (
    OUTSIDE,
    A,
    B,
    D,
    envelope,
    pool,
    prescription,
)
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan

COMPILER_VERSION = "v3-plan-compiler-v1"


def fallback_plan(
    current_envelope: ConstraintEnvelope,
    current_pool: ExercisePoolSnapshot,
) -> DeterministicFallbackPlanSpec:
    return DeterministicFallbackPlanSpec.create(
        envelope_hash=current_envelope.envelope_hash,
        pool_hash=current_pool.pool_hash,
        action_code=PlanActionCode.KEEP,
        requested_duration_minutes=6,
        estimated_duration_seconds=495,
        exercise_prescriptions=(
            prescription(A, 1, phase_code="WARMUP"),
            prescription(B, 2),
            prescription(D, 3, phase_code="COOLDOWN"),
        ),
        reason_codes=("DETERMINISTIC_FALLBACK",),
        fallback_version="fallback-v1",
    )


def test_plan_compiler_resolves_pool_records_without_reselecting_exercises() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    source = plan(current_input)

    compiled = compile_plan(
        source,
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )

    assert tuple(item.prescription.exercise_id for item in compiled.exercises) == (A, B, D)
    assert tuple(item.catalog_record.exercise_id for item in compiled.exercises) == (A, B, D)
    assert compiled.duration_verification_code == DURATION_VERIFICATION_CODE
    assert compiled.estimated_duration_seconds == 495


def test_compiled_plan_order_and_hash_are_stable() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    source = plan(current_input)

    first = compile_plan(
        source,
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )
    second = compile_plan(
        source,
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )

    assert first == second
    assert first.compiled_plan_hash == second.compiled_plan_hash


def test_compiler_rejects_pool_outside_exercise_and_duration_change() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    outside = plan(
        current_input,
        plan_prescriptions=(
            prescription(A, 1, phase_code="WARMUP"),
            prescription(OUTSIDE, 2),
            prescription(D, 3, phase_code="COOLDOWN"),
        ),
    )
    changed_duration = plan(current_input, requested_duration_minutes=29)

    with pytest.raises(ValueError, match="outside ExercisePoolSnapshot"):
        compile_plan(
            outside,
            envelope=current_envelope,
            pool=current_pool,
            compiler_version=COMPILER_VERSION,
            coordinator_input=current_input,
        )
    with pytest.raises(ValueError, match="requested duration"):
        compile_plan(
            changed_duration,
            envelope=current_envelope,
            pool=current_pool,
            compiler_version=COMPILER_VERSION,
            coordinator_input=current_input,
        )


def test_fallback_compiles_through_same_domain_compiler_without_llm_references() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    source = fallback_plan(current_envelope, current_pool)

    compiled = compile_plan(
        source,
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
    )

    assert compiled.source_plan_hash == source.fallback_plan_hash
    assert compiled.requested_duration_minutes == current_envelope.requested_duration_minutes


def test_compiler_does_not_accept_coordinator_context_for_fallback() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)

    with pytest.raises(ValueError, match="cannot claim LLM"):
        compile_plan(
            fallback_plan(current_envelope, current_pool),
            envelope=current_envelope,
            pool=current_pool,
            compiler_version=COMPILER_VERSION,
            coordinator_input=current_input,
        )
