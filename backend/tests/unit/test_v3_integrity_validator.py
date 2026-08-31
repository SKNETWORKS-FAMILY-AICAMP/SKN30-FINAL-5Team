from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import CompiledExercise, CompiledPlan, compile_plan
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RecoveryCeiling
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationStatusCode,
    IntegrityViolationCode,
    validate_plan_integrity,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.tests.unit.test_v3_agent_contracts import (
    A,
    B,
    C,
    envelope,
    exercise,
    pool,
    prescription,
)
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan

COMPILER_VERSION = "v3-plan-compiler-v1"
VALIDATOR_VERSION = "v3-integrity-validator-v1"


def compiled_plan(
    current_envelope: ConstraintEnvelope,
) -> tuple[CompiledPlan, ExercisePoolSnapshot]:
    current_pool = pool(current_envelope)
    current_input = coordinator_input(current_envelope, current_pool)
    compiled = compile_plan(
        plan(current_input),
        envelope=current_envelope,
        pool=current_pool,
        compiler_version=COMPILER_VERSION,
        coordinator_input=current_input,
    )
    return compiled, current_pool


def context(
    *,
    alternatives: tuple[UUID, ...] = (B,),
    fallback: bool = False,
) -> IntegrityValidationContext:
    return IntegrityValidationContext(
        approved_safe_alternative_ids=alternatives,
        fallback_plan_validation=fallback,
    )


def test_valid_compiled_plan_passes_with_stable_validation_hash() -> None:
    current_envelope = envelope()
    compiled, current_pool = compiled_plan(current_envelope)

    first = validate_plan_integrity(
        compiled,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )
    second = validate_plan_integrity(
        compiled,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )

    assert first.status_code is IntegrityValidationStatusCode.PASS
    assert first.validation_hash == second.validation_hash


def test_exact_duration_mismatch_is_repairable_only_with_approved_alternative() -> None:
    current_envelope = envelope()
    compiled, current_pool = compiled_plan(current_envelope)
    wrong_duration = compiled.model_copy(update={"estimated_duration_seconds": 1799})

    repairable = validate_plan_integrity(
        wrong_duration,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )
    terminal = validate_plan_integrity(
        wrong_duration,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(alternatives=()),
    )

    assert repairable.status_code is IntegrityValidationStatusCode.REPAIRABLE
    assert repairable.violations[0].code is IntegrityViolationCode.REQUESTED_DURATION_MISMATCH
    assert terminal.status_code is IntegrityValidationStatusCode.NON_REPAIRABLE


def test_recovery_ceiling_and_safety_exclusion_cannot_be_relaxed() -> None:
    current_envelope = envelope(excluded_ids=(C,))
    compiled, current_pool = compiled_plan(current_envelope)
    recovery_exercise = compiled.exercises[0].model_copy(
        update={"prescription": prescription(A, 1, sets=4)}
    )
    recovery_plan = compiled.model_copy(
        update={"exercises": (recovery_exercise, compiled.exercises[1])}
    )
    unsafe_exercise = CompiledExercise(prescription=prescription(C, 2), catalog_record=exercise(C))
    unsafe_plan = compiled.model_copy(
        update={"exercises": (compiled.exercises[0], unsafe_exercise)}
    )

    recovery_result = validate_plan_integrity(
        recovery_plan,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )
    unsafe_result = validate_plan_integrity(
        unsafe_plan,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )

    assert IntegrityViolationCode.RECOVERY_CEILING_EXCEEDED in {
        item.code for item in recovery_result.violations
    }
    assert IntegrityViolationCode.SAFETY_EXCLUDED_EXERCISE_INCLUDED in {
        item.code for item in unsafe_result.violations
    }


def test_repair_attempt_one_makes_every_repeated_violation_non_repairable() -> None:
    current_envelope = envelope()
    compiled, current_pool = compiled_plan(current_envelope)
    wrong_duration = compiled.model_copy(update={"estimated_duration_seconds": 1799})

    result = validate_plan_integrity(
        wrong_duration,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=1,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )

    assert result.status_code is IntegrityValidationStatusCode.NON_REPAIRABLE
    assert IntegrityViolationCode.REPAIR_ATTEMPT_EXHAUSTED in {
        item.code for item in result.violations
    }


def test_stop_and_seek_help_is_non_repairable_without_plan() -> None:
    blocked = ConstraintEnvelope.create(
        requested_duration_minutes=6,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=("BODYWEIGHT",),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=RecoveryCeiling(policy_version="recovery-policy-v1"),
        plan_generation_allowed=False,
        safety_required_action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
        policy_version="decision-policy-v3",
        catalog_version="catalog-v3",
        safety_rule_version="safety-rules-v3",
    )
    blocked_pool = pool(blocked)

    result = validate_plan_integrity(
        None,
        envelope=blocked,
        pool=blocked_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(alternatives=()),
    )

    assert result.status_code is IntegrityValidationStatusCode.NON_REPAIRABLE
    assert IntegrityViolationCode.STOP_AND_SEEK_HELP in {item.code for item in result.violations}


def test_invalid_fallback_is_explicitly_non_repairable() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)

    result = validate_plan_integrity(
        None,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(fallback=True),
    )

    assert result.status_code is IntegrityValidationStatusCode.NON_REPAIRABLE
    assert result.violations[0].code is IntegrityViolationCode.FALLBACK_PLAN_INVALID


def test_empty_equipment_allowlist_does_not_reject_a_catalog_consistent_plan() -> None:
    # The production shape. Onboarding stopped collecting equipment on
    # 2026-08-27, so a real user has no UserEquipment rows and the envelope
    # allowlist is empty. Intersecting against it flagged every prescription
    # that named any equipment at all -- BODYWEIGHT included -- so the graph
    # failed after all three agents had already answered READY.
    current_envelope = envelope(allowed_equipment_codes=())
    compiled, current_pool = compiled_plan(current_envelope)

    result = validate_plan_integrity(
        compiled,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )

    assert result.status_code is IntegrityValidationStatusCode.PASS
    assert IntegrityViolationCode.EQUIPMENT_NOT_AVAILABLE not in {
        item.code for item in result.violations
    }


def test_equipment_outside_the_catalog_record_is_still_rejected() -> None:
    # Dropping the allowlist must not drop the catalog link: a plan may not
    # claim equipment the reviewed record does not list.
    current_envelope = envelope(allowed_equipment_codes=())
    compiled, current_pool = compiled_plan(current_envelope)
    first = compiled.exercises[0]
    tampered = compiled.model_copy(
        update={
            "exercises": (
                first.model_copy(
                    update={
                        "prescription": first.prescription.model_copy(
                            update={"equipment_codes": ("BARBELL",)}
                        )
                    }
                ),
                *compiled.exercises[1:],
            )
        }
    )

    result = validate_plan_integrity(
        tampered,
        envelope=current_envelope,
        pool=current_pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=context(),
    )

    assert IntegrityViolationCode.EQUIPMENT_NOT_AVAILABLE in {
        item.code for item in result.violations
    }
