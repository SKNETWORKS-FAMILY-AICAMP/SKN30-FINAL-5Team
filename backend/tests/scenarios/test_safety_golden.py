import pytest

from backend.app.domain.rules.safety import (
    AdverseReactionCode,
    BodyAreaCode,
    Discomfort,
    DiscomfortSeverityCode,
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyContext,
    SafetyRequiredActionCode,
    SafetyReviewStatusCode,
    SafetyRule,
    SafetyRuleEffectCode,
    SafetyRuleScopeCode,
    SafetyRuleSet,
    SafetyStatusCode,
    evaluate_safety,
)


@pytest.fixture
def upper_body_candidate() -> SafetyCandidate:
    return SafetyCandidate(
        items=(
            SafetyCandidateItem(
                exercise_code="kneeling_push_up",
                catalog_version_code="approved-catalog-v1",
                movement_pattern_code="HORIZONTAL_PUSH",
            ),
            SafetyCandidateItem(
                exercise_code="supported_row",
                catalog_version_code="approved-catalog-v1",
                movement_pattern_code="HORIZONTAL_PULL",
            ),
        )
    )


@pytest.fixture
def approved_knee_rule_set() -> SafetyRuleSet:
    return SafetyRuleSet(
        version_code="approved-safety-v1",
        review_status_code=SafetyReviewStatusCode.DOMAIN_APPROVED,
        production_eligible=True,
        rules=(
            SafetyRule(
                rule_code="KNEE_KNEELING_PUSH_UP_EXCLUDE",
                catalog_version_code="approved-catalog-v1",
                body_area_code=BodyAreaCode.KNEE,
                minimum_severity_code=DiscomfortSeverityCode.MILD,
                maximum_severity_code=DiscomfortSeverityCode.MODERATE,
                effect_code=SafetyRuleEffectCode.EXCLUDE,
                reason_code="DIRECT_JOINT_LOAD",
                scope_code=SafetyRuleScopeCode.EXERCISE,
                rule_version="1.0.0",
                exercise_code="kneeling_push_up",
            ),
        ),
    )


@pytest.mark.parametrize(
    "severity",
    [DiscomfortSeverityCode.MILD, DiscomfortSeverityCode.MODERATE],
)
def test_golden_knee_discomfort_vetoes_conflicting_exercise(
    severity: DiscomfortSeverityCode,
    upper_body_candidate: SafetyCandidate,
    approved_knee_rule_set: SafetyRuleSet,
) -> None:
    context = SafetyContext(discomforts=(Discomfort(BodyAreaCode.KNEE, severity),))

    result = evaluate_safety(context, upper_body_candidate, approved_knee_rule_set)

    assert result.status_code is SafetyStatusCode.REVISE
    assert result.veto is True
    assert result.plan_allowed is False
    assert result.excluded_exercise_codes == ("kneeling_push_up",)
    assert result.applied_rule_codes == ("KNEE_KNEELING_PUSH_UP_EXCLUDE",)


def test_golden_severe_knee_discomfort_returns_rest_without_plan(
    upper_body_candidate: SafetyCandidate,
) -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.SEVERE),)
    )

    result = evaluate_safety(context, upper_body_candidate, None)

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.REST
    assert result.plan_allowed is False


def test_golden_emergency_reaction_returns_stop_without_plan(
    upper_body_candidate: SafetyCandidate,
) -> None:
    context = SafetyContext(adverse_reaction_codes=(AdverseReactionCode.CHEST_DISCOMFORT,))

    result = evaluate_safety(context, upper_body_candidate, None)

    assert result.status_code is SafetyStatusCode.BLOCKED
    assert result.required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert result.veto is True
    assert result.plan_allowed is False


def test_golden_vetoed_candidate_cannot_be_treated_as_plan_allowed(
    upper_body_candidate: SafetyCandidate,
    approved_knee_rule_set: SafetyRuleSet,
) -> None:
    context = SafetyContext(
        discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MODERATE),)
    )

    result = evaluate_safety(context, upper_body_candidate, approved_knee_rule_set)

    assert result.veto is True
    assert result.plan_allowed is False
    assert "kneeling_push_up" in result.excluded_exercise_codes
