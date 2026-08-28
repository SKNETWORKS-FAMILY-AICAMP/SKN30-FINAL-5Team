from dataclasses import replace
from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord
from backend.app.domain.rules.safety import (
    BodyAreaCode,
    DiscomfortSeverityCode,
    SafetyReviewStatusCode,
    SafetyRule,
    SafetyRuleEffectCode,
    SafetyRuleScopeCode,
    SafetyRuleSet,
)
from backend.app.modules.decisions.v3_application import (
    DeterministicV3SafetyPolicyAdapter,
    PostgreSQLV3ExercisePoolSource,
    V3ApplicationContext,
)
from backend.app.modules.decisions.v3_creation import V3CreationSource
from backend.tests.unit.test_decision_service import FakeRepository, _context


def _exercise(
    exercise_id: UUID,
    difficulty_code: str,
    movement_pattern_code: str = "PUSH",
) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=exercise_id,
        catalog_version="catalog-v1",
        content_version="content-v1",
        stable_code=f"exercise-{exercise_id.int}",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=(movement_pattern_code,),
        difficulty_code=difficulty_code,
        timing_mode_code="REPS",
        default_seconds_per_rep=3,
        default_rest_seconds=30,
        default_transition_seconds=15,
        recovery_eligible=False,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=(),
        location_codes=("HOME",),
        prescription_reference_codes=(f"prescription-{difficulty_code.lower()}",),
        source_reference_codes=("catalog-v1",),
        review_reference_codes=("DOMAIN_APPROVED",),
    )


def _shoulder_rule_set(
    *,
    scope_code: SafetyRuleScopeCode,
    exercise_code: str | None = None,
    movement_pattern_code: str | None = None,
) -> SafetyRuleSet:
    return SafetyRuleSet(
        version_code="safety-v2",
        review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
        production_eligible=True,
        rules=(
            SafetyRule(
                rule_code="SHOULDER_EXCLUDE",
                catalog_version_code="catalog-v1",
                body_area_code=BodyAreaCode.SHOULDER,
                minimum_severity_code=DiscomfortSeverityCode.MODERATE,
                maximum_severity_code=DiscomfortSeverityCode.SEVERE,
                effect_code=SafetyRuleEffectCode.EXCLUDE,
                reason_code="DIRECT_JOINT_LOAD",
                scope_code=scope_code,
                rule_version="2.0.0",
                exercise_code=exercise_code,
                movement_pattern_code=movement_pattern_code,
            ),
        ),
    )


def _source(
    *,
    emergency: bool = False,
    experience_level_code: str | None = None,
    exercises: tuple[ExercisePoolExerciseRecord, ...] = (),
    discomforts: tuple[tuple[str, str], ...] = (),
    safety_rule_set: SafetyRuleSet | None = None,
) -> V3CreationSource:
    context = _context(discomforts=discomforts)
    if emergency:
        context = replace(context, adverse_reaction_codes=("CHEST_DISCOMFORT",))
    assembly = FakeRepository(context, safety_rule_set=safety_rule_set).assembly
    return V3CreationSource(
        local_date=context.local_date,
        context_version=context.context_version,
        normalized_values={
            "duration_adjustment_source_code": context.duration_adjustment_source_code,
            "experience_level_code": experience_level_code or context.experience_level_code,
            "location_code": context.location_code,
        },
        application_context=V3ApplicationContext(assembly, exercises),
    )


def test_application_context_is_excluded_from_serialized_source() -> None:
    source = _source()

    payload = source.model_dump(mode="json")

    assert "application_context" not in payload
    assert "daily_context_id" not in str(payload)


def test_deterministic_safety_veto_is_immutable_and_terminal() -> None:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(_source(emergency=True))

    assert not envelope.plan_generation_allowed
    assert envelope.safety_required_action_code == "STOP_AND_SEEK_HELP"


def test_v3_pool_beginner_user_excludes_intermediate_exercise() -> None:
    beginner_id = UUID(int=101)
    intermediate_id = UUID(int=102)
    source = _source(
        experience_level_code="BEGINNER",
        exercises=(
            _exercise(beginner_id, "BEGINNER"),
            _exercise(intermediate_id, "INTERMEDIATE"),
        ),
    )
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(
        source=source,
        envelope=envelope,
    )

    assert tuple(item.exercise_id for item in eligible.exercises) == (beginner_id,)


def test_v3_pool_intermediate_user_includes_both_difficulties() -> None:
    beginner_id = UUID(int=101)
    intermediate_id = UUID(int=102)
    source = _source(
        experience_level_code="INTERMEDIATE",
        exercises=(
            _exercise(beginner_id, "BEGINNER"),
            _exercise(intermediate_id, "INTERMEDIATE"),
        ),
    )
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(
        source=source,
        envelope=envelope,
    )

    assert tuple(item.exercise_id for item in eligible.exercises) == (
        beginner_id,
        intermediate_id,
    )


def test_v3_envelope_excludes_pool_exercise_matching_reported_pain() -> None:
    """A pool exercise outside the base routine must still face the pain rules.

    Reproduces the staging defect: with SHOULDER pain reported the envelope
    excluded nothing, because safety only ever saw the base routine day while the
    agents chose from the catalog-wide pool.
    """

    unsafe_id = UUID(int=101)
    safe_id = UUID(int=102)
    source = _source(
        exercises=(_exercise(unsafe_id, "BEGINNER"), _exercise(safe_id, "BEGINNER")),
        discomforts=(("SHOULDER", "MODERATE"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.EXERCISE,
            exercise_code=str(unsafe_id),
        ),
    )

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    assert envelope.excluded_exercise_ids == (unsafe_id,)
    assert envelope.plan_generation_allowed

    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(source=source, envelope=envelope)

    assert tuple(item.exercise_id for item in eligible.exercises) == (safe_id,)


def test_v3_envelope_excludes_pool_exercise_by_movement_pattern() -> None:
    """Pattern-scoped rules need the catalog pattern, not a placeholder."""

    unsafe_id = UUID(int=101)
    safe_id = UUID(int=102)
    source = _source(
        exercises=(
            _exercise(unsafe_id, "BEGINNER", movement_pattern_code="PUSH"),
            _exercise(safe_id, "BEGINNER", movement_pattern_code="HINGE"),
        ),
        discomforts=(("SHOULDER", "MODERATE"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.MOVEMENT_PATTERN,
            movement_pattern_code="PUSH",
        ),
    )

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    assert envelope.excluded_exercise_ids == (unsafe_id,)


def test_v3_plan_generation_blocked_when_every_pool_exercise_is_excluded() -> None:
    """Fail closed rather than plan from an empty pool."""

    source = _source(
        exercises=(
            _exercise(UUID(int=101), "BEGINNER", movement_pattern_code="PUSH"),
            _exercise(UUID(int=102), "BEGINNER", movement_pattern_code="PUSH"),
        ),
        discomforts=(("SHOULDER", "MODERATE"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.MOVEMENT_PATTERN,
            movement_pattern_code="PUSH",
        ),
    )

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    assert not envelope.plan_generation_allowed
    assert envelope.safety_required_action_code == "REST"
