from decimal import Decimal

from backend.app.modules.decisions.v3_evaluation import (
    V3EvaluationStatusCode,
    compare_shadow_result,
    evaluate_shadow_results,
    validate_report_privacy,
)
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    build_synthetic_fixture_bundle,
)

EXPECTED_SCENARIOS = (
    "HEALTHY_ORIGINAL",
    "LIMITED_TIME_DURATION_PRESERVED",
    "KNEE_LOAD_EXCLUDED_GOAL_PRESERVED",
    "WEARABLE_MISSING_MANUAL_FALLBACK",
    "REQUIRED_LLM_FAILURE_FALLBACK",
    "SAFETY_VETO_PRECEDENCE",
    "NO_CONFLICT_NO_REVIEW",
    "CONFLICT_AFFECTED_REVIEW_ONLY",
    "REPAIRABLE_VALIDATION_ONE_REPAIR",
    "REPEATED_ERROR_NO_EXTRA_REPAIR",
    "QDRANT_TIMEOUT_POOL_FALLBACK",
    "STALE_CATALOG_INDEX_DISCARDED",
    "REGENERATION_EXACT_DUPLICATE_REJECTED",
    "REGENERATION_MEANINGFUL_DIFFERENCE",
    "REGENERATION_MAX_TWO",
    "PROVIDER_INVALID_STRUCTURED_OUTPUT",
    "PROVIDER_TOTAL_TIMEOUT",
    "NO_APPROVED_SAFE_EXERCISE",
    "STOP_AND_SEEK_HELP",
    "PRIVACY_ALLOWLIST",
)


def test_synthetic_v3_shadow_fixture_is_deterministic_and_complete() -> None:
    first = build_synthetic_fixture_bundle()
    second = build_synthetic_fixture_bundle()

    assert first == second
    assert first.fixture_hash == second.fixture_hash
    assert tuple(item.case.scenario_code for item in first.fixtures) == EXPECTED_SCENARIOS
    assert len({item.case.case_hash for item in first.fixtures}) == 20
    assert len({item.stored_result.result_hash for item in first.fixtures}) == 20


def test_synthetic_golden_matrix_passes_hard_safety_gates() -> None:
    bundle = build_synthetic_fixture_bundle()
    results = tuple(item.stored_result for item in bundle.fixtures)

    summary = evaluate_shadow_results(results)

    assert summary.evaluation_status_code is V3EvaluationStatusCode.PASSED
    assert summary.safety_invariant_pass_rate == Decimal("1.000000")
    assert summary.safety_veto_override_count == 0
    assert summary.constraint_violation_rate == Decimal("0.000000")
    assert summary.pool_membership_violation_rate == Decimal("0.000000")
    assert summary.report_only_thresholds_applied is False


def test_synthetic_comparisons_allow_safe_v1_v3_differences() -> None:
    bundle = build_synthetic_fixture_bundle()
    comparisons = tuple(
        compare_shadow_result(item.case.baseline_plan, item.stored_result)
        for item in bundle.fixtures
    )

    assert any(item.difference_codes for item in comparisons)
    assert not any(item.hard_constraint_failed for item in comparisons)
    for item in bundle.fixtures:
        validate_report_privacy(item.stored_result)
