import pytest

from backend.app.domain.rules.safety import (
    SAFETY_ENGINE_VERSION,
    AdverseReactionCode,
    BodyAreaCode,
    Discomfort,
    DiscomfortSeverityCode,
    InvalidSafetyInputError,
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyContext,
    SafetyRequiredActionCode,
    SafetyReviewStatusCode,
    SafetyRule,
    SafetyRuleAvailabilityCode,
    SafetyRuleEffectCode,
    SafetyRuleScopeCode,
    SafetyRuleSet,
    SafetyStatusCode,
    evaluate_safety,
    severity_from_intensity_score,
)


def _candidate() -> SafetyCandidate:
    return SafetyCandidate(
        items=(
            SafetyCandidateItem("squat", "catalog-v1", "KNEE_DOMINANT"),
            SafetyCandidateItem("row", "catalog-v1", "HORIZONTAL_PULL"),
        )
    )


def _rule(
    *,
    rule_code: str = "KNEE_DOMINANT_MILD_EXCLUDE",
    scope_code: SafetyRuleScopeCode = SafetyRuleScopeCode.MOVEMENT_PATTERN,
    effect_code: SafetyRuleEffectCode = SafetyRuleEffectCode.EXCLUDE,
    exercise_code: str | None = None,
    movement_pattern_code: str | None = "KNEE_DOMINANT",
    catalog_version_code: str = "catalog-v1",
    body_area_code: BodyAreaCode = BodyAreaCode.KNEE,
    minimum_severity_code: DiscomfortSeverityCode = DiscomfortSeverityCode.MILD,
    maximum_severity_code: DiscomfortSeverityCode = DiscomfortSeverityCode.MODERATE,
    review_status_code: SafetyReviewStatusCode = SafetyReviewStatusCode.DOMAIN_APPROVED,
) -> SafetyRule:
    return SafetyRule(
        rule_code=rule_code,
        catalog_version_code=catalog_version_code,
        body_area_code=body_area_code,
        minimum_severity_code=minimum_severity_code,
        maximum_severity_code=maximum_severity_code,
        effect_code=effect_code,
        reason_code="DIRECT_JOINT_LOAD",
        scope_code=scope_code,
        rule_version="1.0.0",
        exercise_code=exercise_code,
        movement_pattern_code=movement_pattern_code,
        review_status_code=review_status_code,
    )


def _approved_rule_set(*rules: SafetyRule) -> SafetyRuleSet:
    return SafetyRuleSet(
        version_code="safety-v1",
        review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
        production_eligible=True,
        rules=rules or (_rule(),),
    )


@pytest.mark.parametrize(
    "emergency_code",
    [
        AdverseReactionCode.CHEST_DISCOMFORT,
        AdverseReactionCode.UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH,
        AdverseReactionCode.SEVERE_DIZZINESS,
        AdverseReactionCode.FAINTING,
        AdverseReactionCode.SUDDEN_WEAKNESS_OR_NUMBNESS,
        AdverseReactionCode.RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS,
        AdverseReactionCode.OTHER_SERIOUS_REACTION,
    ],
)
def test_each_emergency_reaction_blocks_with_stop_and_seek_help(
    emergency_code: AdverseReactionCode,
) -> None:
    context = SafetyContext(adverse_reaction_codes=(emergency_code,))

    result = evaluate_safety(context, _candidate(), None)

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert result.veto is True
    assert result.plan_allowed is False
    assert result.emergency_reaction_codes == (emergency_code,)


def test_emergency_reaction_has_priority_over_acute_and_severe_inputs() -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.SEVERE),),
        adverse_reaction_codes=(
            AdverseReactionCode.SUDDEN_SEVERE_PAIN,
            AdverseReactionCode.CHEST_DISCOMFORT,
        ),
    )

    result = evaluate_safety(context, _candidate(), None)

    assert result.required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert result.emergency_reaction_codes == (AdverseReactionCode.CHEST_DISCOMFORT,)
    assert result.acute_reaction_codes == (AdverseReactionCode.SUDDEN_SEVERE_PAIN,)
    assert result.severe_body_area_codes == (BodyAreaCode.KNEE,)


def test_red_flag_blocks_plan_generation_before_rule_evaluation() -> None:
    result = evaluate_safety(SafetyContext(red_flag_present=True), _candidate(), None)

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert result.veto is True
    assert result.plan_allowed is False


@pytest.mark.parametrize(
    ("intensity_score", "severity"),
    [
        (1, DiscomfortSeverityCode.MILD),
        (3, DiscomfortSeverityCode.MILD),
        (4, DiscomfortSeverityCode.MODERATE),
        (6, DiscomfortSeverityCode.MODERATE),
        (7, DiscomfortSeverityCode.SEVERE),
        (10, DiscomfortSeverityCode.SEVERE),
    ],
)
def test_nrs_intensity_maps_to_the_approved_safety_band(
    intensity_score: int, severity: DiscomfortSeverityCode
) -> None:
    assert severity_from_intensity_score(intensity_score) is severity


@pytest.mark.parametrize("intensity_score", [0, 11])
def test_nrs_intensity_outside_approved_range_is_rejected(intensity_score: int) -> None:
    with pytest.raises(InvalidSafetyInputError):
        severity_from_intensity_score(intensity_score)


@pytest.mark.parametrize(
    "acute_code",
    [
        AdverseReactionCode.SUDDEN_SEVERE_PAIN,
        AdverseReactionCode.ACUTE_SWELLING_OR_DEFORMITY,
        AdverseReactionCode.CANNOT_BEAR_WEIGHT,
    ],
)
def test_acute_musculoskeletal_reaction_blocks_with_rest(
    acute_code: AdverseReactionCode,
) -> None:
    result = evaluate_safety(
        SafetyContext(adverse_reaction_codes=(acute_code,)),
        _candidate(),
        None,
    )

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.REST
    assert result.veto is True
    assert result.plan_allowed is False
    assert result.acute_reaction_codes == (acute_code,)


def test_severe_discomfort_blocks_with_rest_without_rule_set() -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.SEVERE),)
    )

    result = evaluate_safety(context, _candidate(), None)

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.REST
    assert result.severe_body_area_codes == (BodyAreaCode.KNEE,)


def test_no_discomfort_passes_without_rule_set() -> None:
    result = evaluate_safety(SafetyContext(), _candidate(), None)

    assert result.status_code is SafetyStatusCode.PASS
    assert result.required_action_code is None
    assert result.veto is False
    assert result.plan_allowed is True
    assert result.rule_availability_code is SafetyRuleAvailabilityCode.NOT_REQUIRED
    assert result.safety_engine_version == SAFETY_ENGINE_VERSION


@pytest.mark.parametrize("severity", [DiscomfortSeverityCode.MILD, DiscomfortSeverityCode.MODERATE])
def test_knee_discomfort_excludes_matching_movement_pattern(
    severity: DiscomfortSeverityCode,
) -> None:
    context = SafetyContext(discomforts=(Discomfort(BodyAreaCode.KNEE, severity),))

    result = evaluate_safety(context, _candidate(), _approved_rule_set())

    assert result.status_code is SafetyStatusCode.REVISE
    assert result.required_action_code is None
    assert result.veto is True
    assert result.plan_allowed is False
    assert result.excluded_exercise_codes == ("squat",)
    assert result.applied_rule_codes == ("KNEE_DOMINANT_MILD_EXCLUDE",)
    assert result.reason_codes == ("DIRECT_JOINT_LOAD",)
    assert result.safety_rule_set_version == "safety-v1"


def test_exercise_scoped_rule_applies_only_to_matching_exercise() -> None:
    rule = _rule(
        rule_code="SQUAT_KNEE_EXCLUDE",
        scope_code=SafetyRuleScopeCode.EXERCISE,
        exercise_code="squat",
        movement_pattern_code=None,
    )
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(context, _candidate(), _approved_rule_set(rule))

    assert result.excluded_exercise_codes == ("squat",)


@pytest.mark.parametrize(
    "rule",
    [
        _rule(catalog_version_code="other-catalog"),
        _rule(body_area_code=BodyAreaCode.SHOULDER),
        _rule(minimum_severity_code=DiscomfortSeverityCode.MODERATE),
        _rule(movement_pattern_code="HIP_DOMINANT"),
    ],
)
def test_non_matching_rules_do_not_modify_candidate(rule: SafetyRule) -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(context, _candidate(), _approved_rule_set(rule))

    assert result.status_code is SafetyStatusCode.PASS
    assert result.plan_allowed is True
    assert result.applied_rule_codes == ()


def test_caution_requires_revision_without_plan_veto() -> None:
    caution_rule = _rule(effect_code=SafetyRuleEffectCode.CAUTION)
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(context, _candidate(), _approved_rule_set(caution_rule))

    assert result.status_code is SafetyStatusCode.REVISE
    assert result.caution_exercise_codes == ("squat",)
    assert result.excluded_exercise_codes == ()
    assert result.veto is False
    assert result.plan_allowed is False


def test_exclude_takes_priority_over_caution_for_same_exercise() -> None:
    caution = _rule(rule_code="KNEE_CAUTION", effect_code=SafetyRuleEffectCode.CAUTION)
    exclude = _rule(rule_code="KNEE_EXCLUDE")
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(
        context,
        _candidate(),
        _approved_rule_set(caution, exclude),
    )

    assert result.excluded_exercise_codes == ("squat",)
    assert result.caution_exercise_codes == ()
    assert result.applied_rule_codes == ("KNEE_CAUTION", "KNEE_EXCLUDE")


def test_all_candidate_exercises_excluded_blocks_with_rest() -> None:
    knee_rule = _rule()
    shoulder_rule = _rule(
        rule_code="SHOULDER_ROW_EXCLUDE",
        body_area_code=BodyAreaCode.SHOULDER,
        movement_pattern_code="HORIZONTAL_PULL",
    )
    context = SafetyContext(
        discomforts=(
            Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),
            Discomfort(BodyAreaCode.SHOULDER, DiscomfortSeverityCode.MODERATE),
        )
    )

    result = evaluate_safety(
        context,
        _candidate(),
        _approved_rule_set(knee_rule, shoulder_rule),
    )

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.REST
    assert result.excluded_exercise_codes == ("row", "squat")
    assert result.veto is True
    assert result.plan_allowed is False


def test_missing_rule_set_fails_closed_for_discomfort() -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(context, _candidate(), None)

    assert result.status_code is SafetyStatusCode.FAILED
    assert result.rule_availability_code is SafetyRuleAvailabilityCode.MISSING
    assert result.veto is True
    assert result.plan_allowed is False


@pytest.mark.parametrize(
    ("review_status", "production_eligible", "expected_availability"),
    [
        (
            SafetyReviewStatusCode.DRAFT,
            True,
            SafetyRuleAvailabilityCode.NOT_DOMAIN_APPROVED,
        ),
        (
            SafetyReviewStatusCode.DOMAIN_APPROVED,
            False,
            SafetyRuleAvailabilityCode.NOT_PRODUCTION_ELIGIBLE,
        ),
    ],
)
def test_unapproved_rule_set_fails_closed(
    review_status: SafetyReviewStatusCode,
    production_eligible: bool,
    expected_availability: SafetyRuleAvailabilityCode,
) -> None:
    rule_set = SafetyRuleSet(
        version_code="safety-v1",
        review_status_code=review_status,
        production_eligible=production_eligible,
        rules=(_rule(),),
    )
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(context, _candidate(), rule_set)

    assert result.status_code is SafetyStatusCode.FAILED
    assert result.rule_availability_code is expected_availability
    assert result.safety_rule_set_version == "safety-v1"
    assert result.plan_allowed is False


def test_unapproved_rule_inside_approved_set_fails_closed() -> None:
    rule_set = _approved_rule_set(_rule(review_status_code=SafetyReviewStatusCode.TECH_REVIEWED))
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
    )

    result = evaluate_safety(context, _candidate(), rule_set)

    assert result.status_code is SafetyStatusCode.FAILED
    assert result.rule_availability_code is SafetyRuleAvailabilityCode.NOT_DOMAIN_APPROVED


def test_pipeline_compatibility_only_rule_set_is_not_treated_as_production_safe() -> None:
    current_generated_artifact_metadata = SafetyRuleSet(
        version_code="mvp-v0.3.0",
        review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
        production_eligible=False,
        rules=(_rule(),),
    )
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MODERATE),)
    )

    result = evaluate_safety(
        context,
        _candidate(),
        current_generated_artifact_metadata,
    )

    assert result.status_code is SafetyStatusCode.FAILED
    assert result.rule_availability_code is SafetyRuleAvailabilityCode.NOT_PRODUCTION_ELIGIBLE


@pytest.mark.parametrize(
    ("scope_code", "exercise_code", "movement_pattern_code"),
    [
        (SafetyRuleScopeCode.EXERCISE, None, None),
        (SafetyRuleScopeCode.EXERCISE, "squat", "KNEE_DOMINANT"),
        (SafetyRuleScopeCode.MOVEMENT_PATTERN, None, None),
        (SafetyRuleScopeCode.MOVEMENT_PATTERN, "squat", "KNEE_DOMINANT"),
    ],
)
def test_rule_scope_requires_exactly_one_matching_target(
    scope_code: SafetyRuleScopeCode,
    exercise_code: str | None,
    movement_pattern_code: str | None,
) -> None:
    with pytest.raises(InvalidSafetyInputError):
        _rule(
            scope_code=scope_code,
            exercise_code=exercise_code,
            movement_pattern_code=movement_pattern_code,
        )


def test_none_discomfort_must_be_omitted() -> None:
    with pytest.raises(InvalidSafetyInputError):
        Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.NONE)


def test_duplicate_discomfort_body_area_is_rejected() -> None:
    with pytest.raises(InvalidSafetyInputError):
        SafetyContext(
            discomforts=(
                Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),
                Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MODERATE),
            )
        )


def test_duplicate_candidate_exercise_code_is_rejected() -> None:
    with pytest.raises(InvalidSafetyInputError):
        SafetyCandidate(
            items=(
                SafetyCandidateItem("squat", "catalog-v1", "KNEE_DOMINANT"),
                SafetyCandidateItem("squat", "catalog-v1", "KNEE_DOMINANT"),
            )
        )


def test_semantically_equal_reordered_input_produces_same_result() -> None:
    knee_rule = _rule()
    shoulder_rule = _rule(
        rule_code="SHOULDER_ROW_CAUTION",
        body_area_code=BodyAreaCode.SHOULDER,
        movement_pattern_code="HORIZONTAL_PULL",
        effect_code=SafetyRuleEffectCode.CAUTION,
    )
    context_a = SafetyContext(
        discomforts=(
            Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),
            Discomfort(BodyAreaCode.SHOULDER, DiscomfortSeverityCode.MODERATE),
        )
    )
    context_b = SafetyContext(discomforts=tuple(reversed(context_a.discomforts)))
    candidate_a = _candidate()
    candidate_b = SafetyCandidate(items=tuple(reversed(candidate_a.items)))
    rules_a = _approved_rule_set(knee_rule, shoulder_rule)
    rules_b = _approved_rule_set(shoulder_rule, knee_rule)

    result_a = evaluate_safety(context_a, candidate_a, rules_a)
    result_b = evaluate_safety(context_b, candidate_b, rules_b)

    assert result_a == result_b
    assert result_a.excluded_exercise_codes == ("squat",)
    assert result_a.caution_exercise_codes == ("row",)
    assert result_a.safety_engine_version == SAFETY_ENGINE_VERSION


def test_chronic_attention_area_applies_caution_without_exclusion() -> None:
    context = SafetyContext(attention_area_codes=(BodyAreaCode.KNEE,))

    result = evaluate_safety(context, _candidate(), _approved_rule_set())

    assert result.status_code is SafetyStatusCode.REVISE
    assert result.caution_exercise_codes == ("squat",)
    assert result.excluded_exercise_codes == ()
    assert result.veto is False


def test_daily_discomfort_effect_takes_priority_over_chronic_attention() -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MODERATE),),
        attention_area_codes=(BodyAreaCode.KNEE,),
    )

    result = evaluate_safety(context, _candidate(), _approved_rule_set())

    assert result.excluded_exercise_codes == ("squat",)
    assert result.caution_exercise_codes == ()
