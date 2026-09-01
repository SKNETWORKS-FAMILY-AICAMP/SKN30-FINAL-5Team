from datetime import UTC, datetime
from decimal import Decimal

import pytest

from backend.app.modules.decisions.v3_evaluation import (
    V3ApprovedPricingReference,
    V3EvaluationPrivacyError,
    V3EvaluationStatusCode,
    V3ExpertReviewStatusCode,
    V3PricingMismatchError,
    V3ReviewerDecisionCode,
    build_expert_review_artifact,
    calculate_decision_cost,
    compare_shadow_result,
    evaluate_shadow_results,
    summarize_expert_reviews,
    validate_report_privacy,
)
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    build_synthetic_fixture_bundle,
)
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowExecutionResult,
    V3ShadowSafetyMetric,
    V3ShadowSafetyViolationCode,
)


def _fixture(code: str):
    return next(
        item
        for item in build_synthetic_fixture_bundle().fixtures
        if item.case.scenario_code == code
    )


def _result_with(result: V3ShadowExecutionResult, **updates: object) -> V3ShadowExecutionResult:
    payload = result.model_dump(exclude={"result_hash"})
    payload.update(updates)
    return V3ShadowExecutionResult.create(**payload)


@pytest.mark.parametrize(
    "violation_code",
    tuple(V3ShadowSafetyViolationCode),
)
def test_every_hard_safety_violation_fails_the_evaluation(
    violation_code: V3ShadowSafetyViolationCode,
) -> None:
    result = _fixture("HEALTHY_ORIGINAL").stored_result
    failed = _result_with(
        result,
        safety=V3ShadowSafetyMetric(
            invariant_passed=False,
            violation_codes=(violation_code,),
        ),
    )

    summary = evaluate_shadow_results((failed,))

    assert summary.evaluation_status_code is V3EvaluationStatusCode.FAILED
    assert summary.safety_invariant_pass_rate == Decimal("0.000000")
    assert summary.hard_gate_violation_counts[0].violation_code == violation_code.value


def test_constraint_and_pool_violations_are_detected() -> None:
    result = _fixture("HEALTHY_ORIGINAL").stored_result
    constraint_failed = _result_with(
        result,
        constraint_violation_codes=("DURATION_CONSTRAINT_VIOLATED",),
    )
    pool_failed = _result_with(
        result,
        safety=V3ShadowSafetyMetric(
            invariant_passed=False,
            violation_codes=(V3ShadowSafetyViolationCode.EXERCISE_POOL_MEMBERSHIP_VIOLATED,),
        ),
    )

    summary = evaluate_shadow_results((constraint_failed, pool_failed))

    assert summary.evaluation_status_code is V3EvaluationStatusCode.FAILED
    assert summary.constraint_violation_rate == Decimal("0.500000")
    assert summary.pool_membership_violation_rate == Decimal("0.500000")


def test_summary_ordering_and_hash_are_canonical() -> None:
    first = _fixture("HEALTHY_ORIGINAL").stored_result
    second = _fixture("REQUIRED_LLM_FAILURE_FALLBACK").stored_result

    forward = evaluate_shadow_results((first, second))
    reversed_summary = evaluate_shadow_results((second, first))

    assert forward == reversed_summary
    assert forward.summary_hash == reversed_summary.summary_hash


def test_nearest_rank_p50_and_p95_are_exact() -> None:
    base = _fixture("SAFETY_VETO_PRECEDENCE").stored_result
    results = tuple(
        _result_with(base, scenario_code=f"LATENCY_{index}", total_latency_ms=value)
        for index, value in enumerate((1, 2, 3, 4, 100), start=1)
    )

    summary = evaluate_shadow_results(results)

    assert summary.total_latency.p50_ms == 3
    assert summary.total_latency.p95_ms == 100


def test_empty_sample_uses_not_available_instead_of_zero_rates() -> None:
    summary = evaluate_shadow_results(())

    assert summary.evaluation_status_code is V3EvaluationStatusCode.NOT_AVAILABLE
    assert summary.safety_invariant_pass_rate is None
    assert summary.total_latency.p50_ms is None
    assert summary.total_latency.p95_ms is None
    assert summary.expert_review_status_code is V3ExpertReviewStatusCode.NOT_REVIEWED
    assert summary.expert_review_agreement_rate is None


def test_fallback_review_and_repair_metrics_are_aggregated() -> None:
    fixtures = (
        _fixture("REQUIRED_LLM_FAILURE_FALLBACK").stored_result,
        _fixture("CONFLICT_AFFECTED_REVIEW_ONLY").stored_result,
        _fixture("REPAIRABLE_VALIDATION_ONE_REPAIR").stored_result,
    )

    summary = evaluate_shadow_results(fixtures)

    assert summary.deterministic_fallback_rate == Decimal("0.333333")
    assert summary.review_routing_rate == Decimal("0.333333")
    assert summary.repair_rate == Decimal("0.333333")
    assert summary.repair_success_rate == Decimal("1.000000")


def test_unavailable_usage_keeps_tokens_and_cost_null() -> None:
    result = _fixture("PROVIDER_TOTAL_TIMEOUT").stored_result

    summary = evaluate_shadow_results((result,))

    assert summary.input_token_count_total is None
    assert summary.output_token_count_total is None
    assert summary.average_token_count_per_decision is None
    assert summary.average_cost_per_decision is None


def test_pricing_mismatch_is_rejected() -> None:
    result = _fixture("HEALTHY_ORIGINAL").stored_result
    pricing = V3ApprovedPricingReference(
        provider_code="ANOTHER_PROVIDER",
        model_code=result.model_version,
        currency_code="USD",
        input_token_unit=1_000_000,
        output_token_unit=1_000_000,
        input_unit_price=Decimal("1"),
        output_unit_price=Decimal("2"),
        effective_at=datetime(2026, 8, 25, tzinfo=UTC),
        source_reference="approved-pricing-registry-v1",
    )

    with pytest.raises(V3PricingMismatchError):
        calculate_decision_cost(result, pricing)


def test_approved_pricing_calculates_exact_decision_cost() -> None:
    result = _fixture("HEALTHY_ORIGINAL").stored_result
    pricing = V3ApprovedPricingReference(
        provider_code=result.provider_code,
        model_code=result.model_version,
        currency_code="USD",
        input_token_unit=1_000,
        output_token_unit=1_000,
        input_unit_price=Decimal("0.001"),
        output_unit_price=Decimal("0.002"),
        effective_at=datetime(2026, 8, 25, tzinfo=UTC),
        source_reference="approved-pricing-registry-v1",
    )

    assert calculate_decision_cost(result, pricing) == Decimal("0.000160000000")


def test_unreviewed_expert_artifact_does_not_claim_agreement() -> None:
    fixture = _fixture("KNEE_LOAD_EXCLUDED_GOAL_PRESERVED")
    comparison = compare_shadow_result(fixture.case.baseline_plan, fixture.stored_result)
    artifact = build_expert_review_artifact(
        comparison,
        fixture.stored_result,
        review_policy_version="v3-expert-review-policy-v1",
    )

    assert artifact.reviewer_decision is V3ReviewerDecisionCode.PENDING
    assert artifact.reviewer_role_code is None
    assert artifact.reviewed_at is None
    assert summarize_expert_reviews((artifact,)) == (
        V3ExpertReviewStatusCode.NOT_REVIEWED,
        None,
    )


def test_expert_agreement_uses_only_completed_reviews() -> None:
    fixture = _fixture("KNEE_LOAD_EXCLUDED_GOAL_PRESERVED")
    pending = build_expert_review_artifact(
        compare_shadow_result(fixture.case.baseline_plan, fixture.stored_result),
        fixture.stored_result,
        review_policy_version="v3-expert-review-policy-v1",
    )
    reviewed_at = datetime(2026, 8, 25, tzinfo=UTC)
    agreed = pending.model_copy(
        update={
            "reviewer_decision": V3ReviewerDecisionCode.V3_PREFERRED,
            "reviewer_reason_codes": ("SAFER_CONSTRAINT_FIT",),
            "reviewer_role_code": "EXERCISE_EXPERT",
            "reviewed_at": reviewed_at,
        }
    )
    disagreed = pending.model_copy(
        update={
            "case_code": "SECOND_REVIEW",
            "reviewer_decision": V3ReviewerDecisionCode.V1_PREFERRED,
            "reviewer_reason_codes": ("BETTER_GOAL_FIT",),
            "reviewer_role_code": "EXERCISE_EXPERT",
            "reviewed_at": reviewed_at,
        }
    )

    assert summarize_expert_reviews((pending, agreed, disagreed)) == (
        V3ExpertReviewStatusCode.REVIEWED,
        Decimal("0.500000"),
    )


def test_v1_v3_difference_alone_is_not_a_hard_safety_failure() -> None:
    fixture = _fixture("KNEE_LOAD_EXCLUDED_GOAL_PRESERVED")
    comparison = compare_shadow_result(fixture.case.baseline_plan, fixture.stored_result)
    summary = evaluate_shadow_results((fixture.stored_result,))

    assert comparison.difference_codes == ("EXERCISE_SET_CHANGED",)
    assert comparison.hard_constraint_failed is False
    assert summary.evaluation_status_code is V3EvaluationStatusCode.PASSED


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "user_id",
        "email",
        "date_of_birth",
        "provider_subject",
        "raw_health",
        "prompt",
        "messages",
        "provider_raw_response",
        "provider_exception",
        "chain_of_thought",
        "api_key",
        "access_token",
        "refresh_token",
    ),
)
def test_privacy_allowlist_rejects_forbidden_report_keys(forbidden_key: str) -> None:
    with pytest.raises(V3EvaluationPrivacyError):
        validate_report_privacy({forbidden_key: "synthetic"})
