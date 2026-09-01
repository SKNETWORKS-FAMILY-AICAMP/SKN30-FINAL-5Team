import ast
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backend.app.modules.decisions.v3_evaluation import (
    PRICING_SCHEMA_VERSION,
    V3ApprovedPricingReference,
    V3ReviewerDecisionCode,
    calculate_decision_cost,
)
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    build_synthetic_fixture_bundle,
)
from backend.app.modules.decisions.v3_promotion import (
    V3PromotionDecision,
    V3PromotionReasonCode,
    V3PromotionStatusCode,
    V3PromotionThresholdReference,
    canonical_json,
)
from backend.app.modules.decisions.v3_shadow import V3ShadowExecutionResult
from backend.scripts.evaluate_v3_promotion import main
from backend.scripts.run_v3_shadow_evaluation import write_reports


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(f"{canonical_json(value, pretty=True)}\n", encoding="utf-8", newline="\n")


def _refresh_manifest_entry(manifest_path: Path, file_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["file_name"] == file_path.name)
    entry["sha256"] = _sha256(file_path)
    entry["record_count"] = (
        sum(bool(line.strip()) for line in file_path.read_text(encoding="utf-8").splitlines())
        if file_path.suffix == ".jsonl"
        else 1
    )
    _write_json(manifest_path, manifest)


def _build_ready_bundle(root: Path) -> dict[str, Path]:
    bundle = build_synthetic_fixture_bundle()
    result = next(
        item.stored_result
        for item in bundle.fixtures
        if item.case.scenario_code == "HEALTHY_ORIGINAL"
    )
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
    cost = calculate_decision_cost(result, pricing)
    assert cost is not None
    usage = result.usage.model_copy(
        update={
            "decision_cost": cost,
            "currency_code": pricing.currency_code,
            "pricing_reference_version": pricing.pricing_schema_version,
        }
    )
    result_values = result.model_dump(exclude={"result_hash"})
    result_values["usage"] = usage
    priced_result = V3ShadowExecutionResult.create(**result_values)

    evidence = root / "evidence"
    write_reports(
        evidence,
        bundle=bundle,
        results=(priced_result,),
        repeat_count=1,
        provider_calls_allowed=False,
    )

    reviews_path = evidence / "expert_review_template.jsonl"
    review = json.loads(reviews_path.read_text(encoding="utf-8"))
    review.update(
        {
            "reviewer_decision": V3ReviewerDecisionCode.V3_PREFERRED.value,
            "reviewer_reason_codes": ["SAFE_AND_GOAL_ALIGNED"],
            "reviewer_role_code": "EXERCISE_EXPERT",
            "reviewed_at": datetime(2026, 8, 25, tzinfo=UTC).isoformat(),
        }
    )
    reviews_path.write_text(f"{canonical_json(review)}\n", encoding="utf-8", newline="\n")
    _refresh_manifest_entry(evidence / "manifest.json", reviews_path)

    pricing_path = root / "pricing.json"
    _write_json(pricing_path, pricing)
    threshold = V3PromotionThresholdReference.create(
        threshold_policy_version="promotion-policy-v1",
        fixture_version=bundle.fixture_version,
        harness_version="v3-shadow-evaluation-harness-v1",
        graph_version=priced_result.graph_version,
        policy_version=priced_result.policy_version,
        catalog_version=priced_result.catalog_version,
        prompt_version=priced_result.prompt_version,
        provider_code=priced_result.provider_code,
        model_version=priced_result.model_version,
        min_shadow_case_count=1,
        min_repeat_count=1,
        required_safety_invariant_pass_rate=Decimal("1"),
        max_safety_veto_override_count=0,
        max_constraint_violation_rate=Decimal("0"),
        min_structured_output_success_rate=Decimal("1"),
        max_p95_latency_ms=priced_result.total_latency_ms,
        max_average_cost_per_decision=cost,
        max_deterministic_fallback_rate=Decimal("0"),
        min_expert_review_completion_rate=Decimal("1"),
        min_expert_agreement_rate=Decimal("1"),
        currency_code=pricing.currency_code,
        pricing_reference_version=PRICING_SCHEMA_VERSION,
        pricing_source_reference=pricing.source_reference,
        approval_reference="approved-threshold-record-v1",
        approved_manifest_sha256=_sha256(evidence / "manifest.json"),
        effective_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    threshold_path = root / "threshold.json"
    _write_json(threshold_path, threshold)
    return {
        "summary": evidence / "summary.json",
        "manifest": evidence / "manifest.json",
        "reviews": reviews_path,
        "pricing": pricing_path,
        "threshold": threshold_path,
    }


def _args(paths: dict[str, Path], output: str = "outputs/v3-shadow/promotion") -> list[str]:
    return [
        "--summary",
        str(paths["summary"]),
        "--manifest",
        str(paths["manifest"]),
        "--expert-reviews",
        str(paths["reviews"]),
        "--threshold-reference",
        str(paths["threshold"]),
        "--pricing-reference",
        str(paths["pricing"]),
        "--output-directory",
        output,
    ]


def test_cli_writes_a_stable_ready_for_human_approval_decision(tmp_path: Path, monkeypatch) -> None:
    paths = _build_ready_bundle(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(_args(paths, "outputs/v3-shadow/first")) == 0
    assert main(_args(paths, "outputs/v3-shadow/second")) == 0

    first = tmp_path / "outputs/v3-shadow/first/promotion_decision.json"
    second = tmp_path / "outputs/v3-shadow/second/promotion_decision.json"
    decision = V3PromotionDecision.model_validate_json(first.read_text(encoding="utf-8"))
    assert decision.status_code is V3PromotionStatusCode.READY_FOR_HUMAN_APPROVAL
    assert first.read_bytes() == second.read_bytes()
    markdown = (tmp_path / "outputs/v3-shadow/first/promotion_decision.md").read_text("utf-8")
    assert "Production activated: `false`" in markdown
    assert "Human approval still required: `true`" in markdown


def test_cli_emits_blocked_for_summary_hash_tampering(tmp_path: Path, monkeypatch) -> None:
    paths = _build_ready_bundle(tmp_path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["summary_hash"] = "0" * 64
    _write_json(paths["summary"], summary)
    _refresh_manifest_entry(paths["manifest"], paths["summary"])
    monkeypatch.chdir(tmp_path)

    assert main(_args(paths)) == 0
    decision = V3PromotionDecision.model_validate_json(
        (tmp_path / "outputs/v3-shadow/promotion/promotion_decision.json").read_text("utf-8")
    )
    assert decision.status_code is V3PromotionStatusCode.BLOCKED
    assert V3PromotionReasonCode.SUMMARY_HASH_MISMATCH in decision.reason_codes


def test_cli_emits_blocked_for_manifest_hash_or_record_count_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _build_ready_bundle(tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    summary_entry = next(item for item in manifest["files"] if item["file_name"] == "summary.json")
    summary_entry["sha256"] = "0" * 64
    summary_entry["record_count"] = 2
    _write_json(paths["manifest"], manifest)
    monkeypatch.chdir(tmp_path)

    assert main(_args(paths)) == 0
    decision = V3PromotionDecision.model_validate_json(
        (tmp_path / "outputs/v3-shadow/promotion/promotion_decision.json").read_text("utf-8")
    )
    assert V3PromotionReasonCode.ARTIFACT_HASH_MISMATCH in decision.reason_codes
    assert V3PromotionReasonCode.ARTIFACT_RECORD_COUNT_MISMATCH in decision.reason_codes


def test_cli_emits_blocked_for_result_hash_tampering(tmp_path: Path, monkeypatch) -> None:
    paths = _build_ready_bundle(tmp_path)
    results_path = paths["manifest"].parent / "results.jsonl"
    result = json.loads(results_path.read_text(encoding="utf-8"))
    result["result_hash"] = "0" * 64
    results_path.write_text(f"{canonical_json(result)}\n", encoding="utf-8", newline="\n")
    _refresh_manifest_entry(paths["manifest"], results_path)
    monkeypatch.chdir(tmp_path)

    assert main(_args(paths)) == 0
    decision = V3PromotionDecision.model_validate_json(
        (tmp_path / "outputs/v3-shadow/promotion/promotion_decision.json").read_text("utf-8")
    )
    assert V3PromotionReasonCode.RESULT_HASH_MISMATCH in decision.reason_codes


def test_cli_rejects_privacy_extra_fields_as_contract_errors(tmp_path: Path, monkeypatch) -> None:
    paths = _build_ready_bundle(tmp_path)
    review = json.loads(paths["reviews"].read_text(encoding="utf-8"))
    review["user_id"] = "forbidden"
    paths["reviews"].write_text(f"{canonical_json(review)}\n", encoding="utf-8")
    _refresh_manifest_entry(paths["manifest"], paths["reviews"])
    monkeypatch.chdir(tmp_path)

    assert main(_args(paths)) == 2
    assert not (tmp_path / "outputs/v3-shadow/promotion/promotion_decision.json").exists()


def test_cli_rejects_free_text_or_identifiers_in_review_codes(tmp_path: Path, monkeypatch) -> None:
    paths = _build_ready_bundle(tmp_path)
    review = json.loads(paths["reviews"].read_text(encoding="utf-8"))
    review["reviewer_reason_codes"] = ["person@example.com"]
    paths["reviews"].write_text(f"{canonical_json(review)}\n", encoding="utf-8")
    _refresh_manifest_entry(paths["manifest"], paths["reviews"])
    monkeypatch.chdir(tmp_path)

    assert main(_args(paths)) == 2


def test_cli_rejects_nan_and_output_path_escape(tmp_path: Path, monkeypatch) -> None:
    paths = _build_ready_bundle(tmp_path)
    paths["threshold"].write_text('{"max_p95_latency_ms": NaN}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(_args(paths)) == 2

    paths = _build_ready_bundle(tmp_path / "second")
    assert main(_args(paths, "../escaped")) == 2
    assert not (tmp_path / "escaped/promotion_decision.json").exists()


def test_cli_has_no_provider_db_fastapi_or_feature_flag_imports() -> None:
    path = Path("backend/scripts/evaluate_v3_promotion.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(name.startswith(("fastapi", "sqlalchemy", "openai")) for name in imported)
    assert not any(
        name.startswith(("backend.app.db", "backend.app.integrations", "backend.app.core.config"))
        for name in imported
    )
