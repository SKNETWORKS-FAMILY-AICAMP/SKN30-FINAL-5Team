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
    V3DecisionResponseProjector,
)
from backend.app.modules.decisions.v3_creation import V3CreationSource
from backend.tests.unit.test_decision_service import BASE_EXERCISE_ID, FakeRepository, _context
from backend.tests.unit.test_v3_persistence_service import make_bundle


class FailIfNarrated:
    def __init__(self) -> None:
        self.calls = 0

    def narrate(self, prompt):
        del prompt
        self.calls += 1
        raise AssertionError("a safety-vetoed decision must not be narrated")


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
    minimum_severity_code: DiscomfortSeverityCode = DiscomfortSeverityCode.MODERATE,
    effect_code: SafetyRuleEffectCode = SafetyRuleEffectCode.EXCLUDE,
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
                minimum_severity_code=minimum_severity_code,
                maximum_severity_code=DiscomfortSeverityCode.SEVERE,
                effect_code=effect_code,
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
    pains: tuple[tuple[str, int, str, str], ...] = (),
    red_flag_present: bool = False,
    sleep_minutes: int | None = None,
    fatigue_level_code: str | None = None,
    safety_rule_set: SafetyRuleSet | None = None,
    latest_difficulty_code: str | None = None,
    latest_difficulty_reason_codes: tuple[str, ...] = (),
) -> V3CreationSource:
    context = _context(discomforts=discomforts)
    context = replace(
        context,
        pains=pains,
        red_flag_present=red_flag_present,
        sleep_minutes=sleep_minutes,
        fatigue_level_code=fatigue_level_code or context.fatigue_level_code,
        latest_difficulty_code=latest_difficulty_code,
        latest_difficulty_reason_codes=latest_difficulty_reason_codes,
    )
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


def test_red_flag_is_an_immutable_terminal_safety_veto() -> None:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(_source(red_flag_present=True))

    assert not envelope.plan_generation_allowed
    assert envelope.safety_required_action_code == "STOP_AND_SEEK_HELP"


def test_nrs_seven_to_ten_blocks_plan_generation() -> None:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(
        _source(
            discomforts=(("SHOULDER", "SEVERE"),),
            pains=(("SHOULDER", 7, "SEVERE", "pain-intensity-action-v2"),),
        )
    )

    assert not envelope.plan_generation_allowed
    assert envelope.safety_required_action_code == "REST"


def test_nrs_moderate_pain_applies_immutable_low_intensity_ceiling() -> None:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(
        _source(
            discomforts=(("SHOULDER", "MODERATE"),),
            pains=(("SHOULDER", 6, "MODERATE", "pain-intensity-action-v2"),),
            safety_rule_set=_shoulder_rule_set(
                scope_code=SafetyRuleScopeCode.EXERCISE,
                exercise_code=str(BASE_EXERCISE_ID),
            ),
        )
    )

    assert envelope.recovery_ceiling.allowed_intensity_codes == ("LOW",)


def test_sleep_and_fatigue_light_recovery_applies_low_intensity_ceiling() -> None:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(
        _source(sleep_minutes=360, fatigue_level_code="MODERATE")
    )

    assert envelope.recovery_ceiling.allowed_intensity_codes == ("LOW",)


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


def test_v3_pool_keeps_exercises_the_user_lacks_equipment_for() -> None:
    # The 2026-08-27 approval removed the issubset equipment filter: owning
    # every listed piece is not a condition of suitability, and the variant
    # lookup is what covers missing kit. Routine creation dropped the gate then
    # and this path kept it, leaving a bodyweight profile with a pool that was
    # mostly stretching.
    bodyweight_id = UUID(int=201)
    barbell_id = UUID(int=202)
    source = _source(
        experience_level_code="BEGINNER",
        exercises=(
            _exercise(bodyweight_id, "BEGINNER"),
            _exercise(barbell_id, "BEGINNER").model_copy(update={"equipment_codes": ("BARBELL",)}),
        ),
    )
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(
        source=source,
        envelope=envelope,
    )

    assert {item.exercise_id for item in eligible.exercises} == {bodyweight_id, barbell_id}


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


def test_v3_rebuilds_mild_pain_excluded_base_routine_from_remaining_safe_pool() -> None:
    """Mild pain must not force REST when an approved safe pool survives."""

    safe_id = UUID(int=102)
    source = _source(
        exercises=(
            _exercise(BASE_EXERCISE_ID, "BEGINNER", movement_pattern_code="KNEE_DOMINANT"),
            _exercise(safe_id, "BEGINNER", movement_pattern_code="HINGE"),
        ),
        discomforts=(("SHOULDER", "MILD"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.EXERCISE,
            exercise_code=str(BASE_EXERCISE_ID),
            minimum_severity_code=DiscomfortSeverityCode.MILD,
        ),
    )

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    assert envelope.plan_generation_allowed
    assert envelope.safety_required_action_code is None
    assert envelope.excluded_exercise_ids == (BASE_EXERCISE_ID,)
    # Rebuilding from the pool must preserve the original workload ceiling
    # even when every item in the base routine was excluded.
    assert envelope.recovery_ceiling.allowed_intensity_codes == ("MODERATE",)
    assert envelope.recovery_ceiling.maximum_sets_per_exercise == 1

    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(source=source, envelope=envelope)

    assert tuple(item.exercise_id for item in eligible.exercises) == (safe_id,)


def test_v3_rebuild_blocks_when_only_safety_survivor_is_not_user_eligible() -> None:
    """Fail closed before retrieval when difficulty removes the last survivor."""

    source = _source(
        experience_level_code="BEGINNER",
        exercises=(
            _exercise(BASE_EXERCISE_ID, "BEGINNER", movement_pattern_code="KNEE_DOMINANT"),
            _exercise(UUID(int=102), "INTERMEDIATE", movement_pattern_code="HINGE"),
        ),
        discomforts=(("SHOULDER", "MODERATE"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.EXERCISE,
            exercise_code=str(BASE_EXERCISE_ID),
        ),
    )

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    assert not envelope.plan_generation_allowed
    assert envelope.safety_required_action_code == "REST"


def test_v3_caution_freezes_low_intensity_downshift_ceiling() -> None:
    """A caution cannot surface as REVISE while allowing a moderate KEEP plan."""

    source = _source(
        exercises=(_exercise(BASE_EXERCISE_ID, "BEGINNER", movement_pattern_code="KNEE_DOMINANT"),),
        discomforts=(("SHOULDER", "MILD"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.EXERCISE,
            exercise_code=str(BASE_EXERCISE_ID),
            minimum_severity_code=DiscomfortSeverityCode.MILD,
            effect_code=SafetyRuleEffectCode.CAUTION,
        ),
    )

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)

    assert envelope.plan_generation_allowed
    assert envelope.excluded_exercise_ids == ()
    assert envelope.recovery_ceiling.allowed_intensity_codes == ("LOW",)


def test_v3_projector_reports_exclusion_rebuild_as_revised_change() -> None:
    safe_id = UUID(int=102)
    source = _source(
        exercises=(
            _exercise(BASE_EXERCISE_ID, "BEGINNER", movement_pattern_code="KNEE_DOMINANT"),
            _exercise(safe_id, "BEGINNER", movement_pattern_code="HINGE"),
        ),
        discomforts=(("SHOULDER", "MODERATE"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.EXERCISE,
            exercise_code=str(BASE_EXERCISE_ID),
        ),
    )
    DeterministicV3SafetyPolicyAdapter().evaluate(source)

    provider = FailIfNarrated()
    projection = V3DecisionResponseProjector(narration_provider=provider).project_success(
        source=source,
        bundle=make_bundle(),
    )
    response = projection.response

    assert response.safety_status_code == "REVISE"
    assert response.action_code == "CHANGE"
    assert response.final_plan is not None
    assert response.final_plan.action_code == "CHANGE"
    assert response.safety_summary is not None
    assert response.safety_summary.vetoed
    assert response.safety_summary.reason_codes == ["DIRECT_JOINT_LOAD"]
    assert provider.calls == 0
    assert response.public_agent_summaries is not None
    assert [item.agent_type_code for item in response.public_agent_summaries] == [
        "TRAINING",
        "RECOVERY",
        "SAFETY",
        "FEASIBILITY",
        "COORDINATOR",
    ]


def test_v3_projector_reports_caution_as_revised_downshift() -> None:
    source = _source(
        exercises=(_exercise(BASE_EXERCISE_ID, "BEGINNER"),),
        discomforts=(("SHOULDER", "MILD"),),
        safety_rule_set=_shoulder_rule_set(
            scope_code=SafetyRuleScopeCode.EXERCISE,
            exercise_code=str(BASE_EXERCISE_ID),
            minimum_severity_code=DiscomfortSeverityCode.MILD,
            effect_code=SafetyRuleEffectCode.CAUTION,
        ),
    )
    DeterministicV3SafetyPolicyAdapter().evaluate(source)

    projection = V3DecisionResponseProjector().project_success(
        source=source,
        bundle=make_bundle(),
    )
    response = projection.response

    assert response.safety_status_code == "REVISE"
    assert response.action_code == "DOWNSHIFT"
    assert response.safety_summary is not None
    assert not response.safety_summary.vetoed


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
