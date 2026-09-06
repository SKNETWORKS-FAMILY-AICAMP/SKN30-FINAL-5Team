"""V3 plan duration is measured from the catalog timing basis, not asserted."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    RetrievalMetadata,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_compiler import (
    DURATION_VERIFICATION_CODE,
    DeterministicFallbackPlanSpec,
    compile_plan,
)
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    ExercisePrescription,
    PlanActionCode,
    RecoveryCeiling,
)
from backend.app.domain.agents.v3_duration import (
    POOL_SIZE_MAXIMUM,
    POOL_SIZE_MINIMUM,
    TimingBasisUnavailableError,
    plan_duration_seconds,
    pool_size_for_duration,
    prescription_item_duration,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityViolationCode,
    validate_plan_integrity,
)

REPS_EXERCISE = UUID("00000000-0000-0000-0000-0000000000a1")
TIMED_EXERCISE = UUID("00000000-0000-0000-0000-0000000000a2")
QUERY_HASH = "c" * 64
VALIDATOR_VERSION = "v3-integrity-validator-v1"


# The catalog approves each exercise for the phases it may serve, and the pool
# snapshot carries that projection forward. These fixtures exercise duration
# arithmetic rather than session shape, so they default to a record every phase
# can use; the shape tests pass the narrower values they need.
ALL_PHASES: tuple[str, ...] = ("WARMUP", "MAIN", "COOLDOWN")


def reps_record(
    exercise_id: UUID = REPS_EXERCISE,
    phase_codes: tuple[str, ...] = ALL_PHASES,
) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        phase_codes=phase_codes,
        exercise_id=exercise_id,
        catalog_version="catalog-v3",
        content_version="content-v1",
        stable_code=f"reps-exercise-{exercise_id.int}",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=("PUSH",),
        difficulty_code="BEGINNER",
        timing_mode_code="REPS",
        default_seconds_per_rep=4,
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


def timed_record(
    exercise_id: UUID = TIMED_EXERCISE,
    phase_codes: tuple[str, ...] = ALL_PHASES,
) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        phase_codes=phase_codes,
        exercise_id=exercise_id,
        catalog_version="catalog-v3",
        content_version="content-v1",
        stable_code=f"timed-exercise-{exercise_id.int}",
        training_type_code="MOBILITY",
        body_focus_code="CORE",
        movement_pattern_codes=("CORE_BRACE",),
        difficulty_code="BEGINNER",
        timing_mode_code="DURATION",
        default_work_seconds=45,
        default_rest_seconds=20,
        default_transition_seconds=10,
        recovery_eligible=True,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=("MAT",),
        location_codes=("HOME",),
        prescription_reference_codes=("prescription-v1",),
        source_reference_codes=("source-v1",),
        review_reference_codes=("review-v1",),
    )


def reps_prescription(
    *, sets: int = 3, repetitions: int = 10, rest: int = 30, sequence: int = 1
) -> ExercisePrescription:
    return ExercisePrescription(
        exercise_id=REPS_EXERCISE,
        sequence=sequence,
        sets=sets,
        repetitions_per_set=repetitions,
        rest_seconds_between_sets=rest,
        transition_seconds=15,
        intensity_code="MODERATE",
        load_code="BODYWEIGHT",
        location_code="HOME",
        equipment_codes=("BODYWEIGHT",),
    )


def test_repetition_based_work_is_timed_through_the_catalog_seconds_per_rep() -> None:
    # The response projection previously read work_seconds_per_set only, so a
    # repetition-based exercise contributed zero work seconds to the plan.
    duration = prescription_item_duration(reps_prescription(), reps_record())

    assert duration.work_seconds == 3 * 10 * 4
    assert duration.rest_seconds == 2 * 30
    assert duration.transition_seconds == 15
    assert duration.estimated_item_seconds == 195


def test_duration_based_work_uses_the_prescribed_work_seconds() -> None:
    prescription = ExercisePrescription(
        exercise_id=TIMED_EXERCISE,
        sequence=1,
        sets=2,
        work_seconds_per_set=45,
        rest_seconds_between_sets=20,
        transition_seconds=10,
        intensity_code="LOW",
        location_code="HOME",
        equipment_codes=("MAT",),
    )

    duration = prescription_item_duration(prescription, timed_record())

    assert duration.work_seconds == 90
    assert duration.estimated_item_seconds == 90 + 20 + 10


def test_transition_seconds_come_from_the_catalog_not_the_prescription() -> None:
    # A model-supplied transition cannot shorten the plan's measured duration.
    prescription = reps_prescription().model_copy(update={"transition_seconds": 0})

    duration = prescription_item_duration(prescription, reps_record())

    assert duration.transition_seconds == 15


def test_a_prescription_outside_the_pool_cannot_be_timed() -> None:
    with pytest.raises(TimingBasisUnavailableError):
        plan_duration_seconds((reps_prescription(),), {})


def test_repetitions_without_a_catalog_basis_fail_instead_of_counting_zero() -> None:
    record = reps_record().model_copy(
        update={"default_seconds_per_rep": None, "default_work_seconds": 30}
    )

    with pytest.raises(TimingBasisUnavailableError):
        prescription_item_duration(reps_prescription(), record)


def test_pool_size_grows_with_the_requested_duration() -> None:
    exercises = tuple(reps_record(UUID(int=index)) for index in range(1, POOL_SIZE_MAXIMUM + 20))

    short = pool_size_for_duration(requested_duration_minutes=20, exercises=exercises)
    long = pool_size_for_duration(requested_duration_minutes=60, exercises=exercises)

    assert short < long
    assert short >= POOL_SIZE_MINIMUM
    assert long <= POOL_SIZE_MAXIMUM


def test_pool_size_never_exceeds_the_eligible_exercises() -> None:
    exercises = (reps_record(UUID(int=1)), reps_record(UUID(int=2)))

    assert pool_size_for_duration(requested_duration_minutes=60, exercises=exercises) == 2


def test_pool_size_requires_at_least_one_eligible_exercise() -> None:
    with pytest.raises(TimingBasisUnavailableError):
        pool_size_for_duration(requested_duration_minutes=30, exercises=())


def _envelope(
    *,
    requested_duration_minutes: int,
    # Production sends (): the 2026-08-27 approval dropped equipment from
    # onboarding, so a real user has no UserEquipment rows.
    allowed_equipment_codes: tuple[str, ...] = ("BODYWEIGHT",),
) -> ConstraintEnvelope:
    return ConstraintEnvelope.create(
        requested_duration_minutes=requested_duration_minutes,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=allowed_equipment_codes,
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
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


def _pool(
    envelope: ConstraintEnvelope,
    exercises: tuple[ExercisePoolExerciseRecord, ...] = (),
) -> ExercisePoolSnapshot:
    records = exercises or (reps_record(),)
    return ExercisePoolSnapshot.create(
        catalog_version="catalog-v3",
        constraint_envelope_hash=envelope.envelope_hash,
        exercises=records,
        mandatory_exercise_ids=(),
        vector_ranked_exercise_ids=tuple(item.exercise_id for item in records),
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


def _fallback_spec(
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    prescriptions: tuple[ExercisePrescription, ...],
) -> DeterministicFallbackPlanSpec:
    return DeterministicFallbackPlanSpec.create(
        envelope_hash=envelope.envelope_hash,
        pool_hash=pool.pool_hash,
        action_code=PlanActionCode.DOWNSHIFT,
        requested_duration_minutes=envelope.requested_duration_minutes,
        estimated_duration_seconds=envelope.requested_duration_minutes * 60,
        exercise_prescriptions=prescriptions,
        reason_codes=("LLM_PROVIDER_FALLBACK",),
        fallback_version="fallback-v1",
    )


def test_compilation_rejects_a_plan_that_cannot_fill_the_requested_duration() -> None:
    # The reported defect: a plan declaring the requested duration while
    # prescribing a fraction of it. Compilation now measures the prescriptions,
    # so the claim can no longer stand in for the work.
    envelope = _envelope(requested_duration_minutes=30)
    pool = _pool(envelope)
    spec = _fallback_spec(envelope, pool, (reps_prescription(),))

    with pytest.raises(ValidationError):
        compile_plan(
            spec,
            envelope=envelope,
            pool=pool,
            compiler_version="v3-plan-compiler-v1",
        )


def test_compiled_duration_is_the_measured_sum_of_its_prescriptions() -> None:
    envelope = _envelope(requested_duration_minutes=30)
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))
    pool = _pool(envelope, records)
    prescriptions = tuple(
        reps_prescription(sequence=index).model_copy(update={"exercise_id": record.exercise_id})
        for index, record in enumerate(records, start=1)
    )

    compiled = compile_plan(
        _fallback_spec(envelope, pool, prescriptions),
        envelope=envelope,
        pool=pool,
        compiler_version="v3-plan-compiler-v1",
    )

    assert compiled.estimated_duration_seconds == 10 * 195
    assert compiled.duration_verification_code == DURATION_VERIFICATION_CODE


class _StubCompiledExercise:
    def __init__(
        self,
        prescription: ExercisePrescription,
        catalog_record: ExercisePoolExerciseRecord,
    ) -> None:
        self.prescription = prescription
        self.catalog_record = catalog_record


class _StubCompiledPlan:
    """A compiled plan whose measured duration can be set independently.

    CompiledPlan itself now rejects an out-of-window duration, so reaching the
    validator's own duration rule needs a stand-in that skips that constructor.
    """

    def __init__(
        self,
        *,
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
        estimated_duration_seconds: int,
    ) -> None:
        self.envelope_hash = envelope.envelope_hash
        self.pool_hash = pool.pool_hash
        self.requested_duration_minutes = envelope.requested_duration_minutes
        self.estimated_duration_seconds = estimated_duration_seconds
        self.exercises = (_StubCompiledExercise(reps_prescription(), reps_record()),)
        self.compiled_plan_hash = "d" * 64


@pytest.mark.parametrize(
    ("estimated_seconds", "expected_violation"),
    [
        (1800, False),
        (1800 + 300, False),
        (1800 - 300, False),
        (1800 + 301, True),
        (195, True),
    ],
)
def test_validator_compares_the_measured_duration_with_the_request(
    estimated_seconds: int, expected_violation: bool
) -> None:
    # A 30-minute request paired with a 195-second plan is the reported defect:
    # comparing estimated_duration_seconds with requested_duration_minutes * 60
    # cannot catch it once the server derives the former from the latter.
    envelope = _envelope(requested_duration_minutes=30)
    pool = _pool(envelope)
    compiled = _StubCompiledPlan(
        envelope=envelope,
        pool=pool,
        estimated_duration_seconds=estimated_seconds,
    )

    result = validate_plan_integrity(
        compiled,  # type: ignore[arg-type]
        envelope=envelope,
        pool=pool,
        repair_attempt=0,
        validator_version=VALIDATOR_VERSION,
        context=IntegrityValidationContext(),
    )

    codes = {item.code for item in result.violations}
    assert (IntegrityViolationCode.REQUESTED_DURATION_MISMATCH in codes) is expected_violation
