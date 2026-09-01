import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.modules.decisions.v3_promotion import (
    V3PromotionEvidence,
    V3PromotionReasonCode,
    V3PromotionStatusCode,
    V3PromotionThresholdReference,
    canonical_json,
    evaluate_v3_promotion,
)

HASH = "a" * 64


def _threshold(**updates: object) -> V3PromotionThresholdReference:
    values: dict[str, object] = {
        "threshold_policy_version": "promotion-policy-v1",
        "fixture_version": "fixture-v1",
        "harness_version": "harness-v1",
        "graph_version": "graph-v1",
        "policy_version": "policy-v1",
        "catalog_version": "catalog-v1",
        "prompt_version": "prompt-v1",
        "provider_code": "OPENAI",
        "model_version": "model-v1",
        "min_shadow_case_count": 20,
        "min_repeat_count": 2,
        "required_safety_invariant_pass_rate": Decimal("1"),
        "max_safety_veto_override_count": 0,
        "max_constraint_violation_rate": Decimal("0"),
        "min_structured_output_success_rate": Decimal("0.95"),
        "max_p95_latency_ms": 200,
        "max_average_cost_per_decision": Decimal("0.02"),
        "max_deterministic_fallback_rate": Decimal("0.20"),
        "min_expert_review_completion_rate": Decimal("1"),
        "min_expert_agreement_rate": Decimal("0.80"),
        "currency_code": "USD",
        "pricing_reference_version": "v3-approved-pricing-v1",
        "pricing_source_reference": "approved-pricing-registry-v1",
        "approval_reference": "approval-record-v1",
        "approved_manifest_sha256": HASH,
        "effective_at": datetime(2026, 8, 25, tzinfo=UTC),
    }
    values.update(updates)
    return V3PromotionThresholdReference.create(**values)


def _evidence(**updates: object) -> V3PromotionEvidence:
    values: dict[str, object] = {
        "fixture_version": "fixture-v1",
        "harness_version": "harness-v1",
        "graph_version": "graph-v1",
        "policy_version": "policy-v1",
        "catalog_version": "catalog-v1",
        "prompt_version": "prompt-v1",
        "provider_code": "OPENAI",
        "model_version": "model-v1",
        "total_case_count": 40,
        "repeat_count": 2,
        "safety_invariant_pass_rate": Decimal("1"),
        "safety_veto_override_count": 0,
        "constraint_violation_rate": Decimal("0"),
        "structured_output_success_rate": Decimal("0.99"),
        "p95_latency_ms": 100,
        "input_token_count_total": 1000,
        "output_token_count_total": 500,
        "average_cost_per_decision": Decimal("0.01"),
        "deterministic_fallback_rate": Decimal("0.10"),
        "expert_review_completion_rate": Decimal("1"),
        "expert_agreement_rate": Decimal("0.90"),
        "expert_reviews_pending": False,
        "reviewer_evidence_complete": True,
        "currency_code": "USD",
        "pricing_reference_version": "v3-approved-pricing-v1",
        "pricing_source_reference": "approved-pricing-registry-v1",
        "artifact_hashes_match": True,
        "artifact_record_counts_match": True,
        "summary_hash_valid": True,
        "result_hashes_valid": True,
        "privacy_validation_passed": True,
        "artifact_versions_consistent": True,
        "pricing_reference_supplied": True,
        "pricing_reference_matches_evidence": True,
        "summary_hash": HASH,
        "summary_file_sha256": HASH,
        "manifest_sha256": HASH,
        "results_sha256": HASH,
        "expert_reviews_sha256": HASH,
    }
    values.update(updates)
    return V3PromotionEvidence.create(**values)


def _with_evidence(evidence: V3PromotionEvidence, **updates: object) -> V3PromotionEvidence:
    values = evidence.model_dump(exclude={"evidence_hash"})
    values.update(updates)
    return V3PromotionEvidence.create(**values)


def test_complete_evidence_is_ready_for_human_approval_review() -> None:
    decision = evaluate_v3_promotion(_evidence(), _threshold())

    assert decision.status_code is V3PromotionStatusCode.READY_FOR_HUMAN_APPROVAL
    assert decision.reason_codes == ()


def test_missing_threshold_is_not_evaluated() -> None:
    decision = evaluate_v3_promotion(_evidence(), None)

    assert decision.status_code is V3PromotionStatusCode.NOT_EVALUATED
    assert decision.reason_codes == (V3PromotionReasonCode.THRESHOLD_REFERENCE_MISSING,)


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        (
            {"safety_invariant_pass_rate": Decimal("0.99")},
            V3PromotionReasonCode.SAFETY_INVARIANT_RATE_BELOW_REQUIRED,
        ),
        ({"safety_veto_override_count": 1}, V3PromotionReasonCode.SAFETY_VETO_OVERRIDE_PRESENT),
        (
            {"constraint_violation_rate": Decimal("0.01")},
            V3PromotionReasonCode.CONSTRAINT_VIOLATION_PRESENT,
        ),
        ({"total_case_count": 19}, V3PromotionReasonCode.SHADOW_CASE_COUNT_BELOW_MINIMUM),
        ({"repeat_count": 1}, V3PromotionReasonCode.REPEAT_COUNT_BELOW_MINIMUM),
        ({"p95_latency_ms": 201}, V3PromotionReasonCode.P95_LATENCY_ABOVE_MAXIMUM),
        (
            {"average_cost_per_decision": Decimal("0.03")},
            V3PromotionReasonCode.AVERAGE_COST_ABOVE_MAXIMUM,
        ),
        (
            {"deterministic_fallback_rate": Decimal("0.21")},
            V3PromotionReasonCode.FALLBACK_RATE_ABOVE_MAXIMUM,
        ),
        (
            {"structured_output_success_rate": Decimal("0.94")},
            V3PromotionReasonCode.STRUCTURED_OUTPUT_RATE_BELOW_MINIMUM,
        ),
        (
            {"expert_agreement_rate": Decimal("0.79")},
            V3PromotionReasonCode.EXPERT_AGREEMENT_BELOW_MINIMUM,
        ),
        (
            {"expert_review_completion_rate": Decimal("0.99")},
            V3PromotionReasonCode.EXPERT_REVIEW_COMPLETION_BELOW_MINIMUM,
        ),
        ({"expert_reviews_pending": True}, V3PromotionReasonCode.EXPERT_REVIEW_PENDING),
        (
            {"reviewer_evidence_complete": False},
            V3PromotionReasonCode.EXPERT_REVIEW_EVIDENCE_INCOMPLETE,
        ),
        ({"artifact_hashes_match": False}, V3PromotionReasonCode.ARTIFACT_HASH_MISMATCH),
        (
            {"artifact_record_counts_match": False},
            V3PromotionReasonCode.ARTIFACT_RECORD_COUNT_MISMATCH,
        ),
        ({"summary_hash_valid": False}, V3PromotionReasonCode.SUMMARY_HASH_MISMATCH),
        ({"result_hashes_valid": False}, V3PromotionReasonCode.RESULT_HASH_MISMATCH),
        ({"privacy_validation_passed": False}, V3PromotionReasonCode.PRIVACY_VALIDATION_FAILED),
        (
            {"artifact_versions_consistent": False},
            V3PromotionReasonCode.ARTIFACT_VERSION_INCONSISTENT,
        ),
        (
            {"manifest_sha256": "b" * 64},
            V3PromotionReasonCode.ARTIFACT_HASH_MISMATCH,
        ),
    ),
)
def test_fail_closed_metric_and_artifact_conditions(
    updates: dict[str, object], reason: V3PromotionReasonCode
) -> None:
    decision = evaluate_v3_promotion(_evidence(**updates), _threshold())

    assert decision.status_code is V3PromotionStatusCode.BLOCKED
    assert reason in decision.reason_codes


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("fixture_version", V3PromotionReasonCode.FIXTURE_VERSION_MISMATCH),
        ("harness_version", V3PromotionReasonCode.HARNESS_VERSION_MISMATCH),
        ("graph_version", V3PromotionReasonCode.GRAPH_VERSION_MISMATCH),
        ("policy_version", V3PromotionReasonCode.POLICY_VERSION_MISMATCH),
        ("catalog_version", V3PromotionReasonCode.CATALOG_VERSION_MISMATCH),
        ("prompt_version", V3PromotionReasonCode.PROMPT_VERSION_MISMATCH),
        ("provider_code", V3PromotionReasonCode.PROVIDER_VERSION_MISMATCH),
        ("model_version", V3PromotionReasonCode.MODEL_VERSION_MISMATCH),
    ),
)
def test_every_version_boundary_is_fail_closed(field: str, reason: V3PromotionReasonCode) -> None:
    decision = evaluate_v3_promotion(_evidence(**{field: "unexpected-v2"}), _threshold())

    assert reason in decision.reason_codes


def test_unavailable_pricing_tokens_and_cost_are_not_coerced_to_zero() -> None:
    decision = evaluate_v3_promotion(
        _evidence(
            input_token_count_total=None,
            output_token_count_total=None,
            average_cost_per_decision=None,
            currency_code=None,
            pricing_reference_version=None,
            pricing_source_reference=None,
            pricing_reference_supplied=False,
            pricing_reference_matches_evidence=False,
        ),
        _threshold(),
    )

    assert V3PromotionReasonCode.TOKEN_USAGE_UNAVAILABLE in decision.reason_codes
    assert V3PromotionReasonCode.AVERAGE_COST_UNAVAILABLE in decision.reason_codes
    assert V3PromotionReasonCode.PRICING_REFERENCE_MISSING in decision.reason_codes


def test_pricing_provider_model_or_currency_mismatch_is_blocked() -> None:
    decision = evaluate_v3_promotion(
        _evidence(pricing_reference_matches_evidence=False), _threshold()
    )

    assert V3PromotionReasonCode.PRICING_REFERENCE_MISMATCH in decision.reason_codes


def test_reason_order_and_decision_hash_are_stable() -> None:
    evidence = _evidence(
        p95_latency_ms=999,
        safety_veto_override_count=1,
        artifact_hashes_match=False,
    )
    first = evaluate_v3_promotion(evidence, _threshold())
    second = evaluate_v3_promotion(evidence, _threshold())

    assert first == second
    assert canonical_json(first) == canonical_json(second)
    assert first.reason_codes == (
        V3PromotionReasonCode.ARTIFACT_HASH_MISMATCH,
        V3PromotionReasonCode.SAFETY_VETO_OVERRIDE_PRESENT,
        V3PromotionReasonCode.P95_LATENCY_ABOVE_MAXIMUM,
    )


def test_threshold_cannot_weaken_hard_safety_limits() -> None:
    with pytest.raises(ValidationError):
        _threshold(max_safety_veto_override_count=1)


def test_incomplete_threshold_approval_reference_is_blocked() -> None:
    decision = evaluate_v3_promotion(_evidence(), _threshold(approval_reference=None))

    assert V3PromotionReasonCode.THRESHOLD_APPROVAL_REFERENCE_INCOMPLETE in decision.reason_codes


def test_non_finite_and_extra_privacy_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _evidence(average_cost_per_decision=Decimal("NaN"))

    payload = _evidence().model_dump(mode="json")
    payload["user_id"] = "forbidden"
    with pytest.raises(ValidationError):
        V3PromotionEvidence.model_validate(payload)


def test_evaluator_has_no_provider_db_fastapi_or_settings_import() -> None:
    tree = ast.parse(Path("backend/app/modules/decisions/v3_promotion.py").read_text("utf-8"))
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imported.isdisjoint({"fastapi", "sqlalchemy", "openai"})
    source = Path("backend/app/modules/decisions/v3_promotion.py").read_text("utf-8")
    assert "backend.app.core.config" not in source
    assert "backend.app.db" not in source
    assert "backend.app.integrations" not in source
