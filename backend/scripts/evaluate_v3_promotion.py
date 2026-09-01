"""Evaluate a saved V3 shadow bundle for human promotion-review readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.modules.decisions.v3_evaluation import (
    V3ApprovedPricingReference,
    V3EvaluationSummary,
    V3ExpertReviewArtifact,
    V3ReviewerDecisionCode,
    summarize_expert_reviews,
    validate_report_privacy,
)
from backend.app.modules.decisions.v3_promotion import (
    V3PromotionDecision,
    V3PromotionEvidence,
    V3PromotionThresholdReference,
    canonical_hash,
    canonical_json,
    evaluate_v3_promotion,
)
from backend.app.modules.decisions.v3_shadow import V3ShadowExecutionResult

_RATE_QUANTUM = Decimal("0.000001")
_MACHINE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_REQUIRED_MANIFEST_FILES = frozenset(
    {"results.jsonl", "summary.json", "expert_review_template.jsonl"}
)


class _ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    file_name: str
    sha256: str
    record_count: int = Field(ge=0)

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        if Path(value).name != value or value in {".", ".."}:
            raise ValueError("manifest file_name must not contain a path")
        return value


class _ShadowManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    generated_at: datetime
    harness_version: str
    fixture_version: str
    fixture_hash: str
    repeat_count: int = Field(gt=0)
    provider_calls_allowed: bool
    files: tuple[_ManifestFile, ...]

    @model_validator(mode="after")
    def validate_files(self) -> Self:
        names = tuple(item.file_name for item in self.files)
        if len(names) != len(set(names)):
            raise ValueError("manifest file names must be unique")
        if not _REQUIRED_MANIFEST_FILES.issubset(names):
            raise ValueError("manifest is missing required V3 shadow files")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("manifest generated_at must include timezone information")
        return self


def _reject_non_finite(raw: str) -> None:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON number is forbidden: {value}")

    json.loads(raw, parse_constant=reject)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(bool(line.strip()) for line in _read_text(path).splitlines())
    return 1


def _load_summary(path: Path) -> tuple[V3EvaluationSummary, bool]:
    raw = _read_text(path)
    _reject_non_finite(raw)
    payload = json.loads(raw, parse_float=Decimal)
    if not isinstance(payload, dict):
        raise ValueError("summary must be a JSON object")
    claimed = payload.get("summary_hash")
    if not isinstance(claimed, str):
        raise ValueError("summary_hash must be present")
    expected = canonical_hash(
        {key: value for key, value in payload.items() if key != "summary_hash"}
    )
    payload["summary_hash"] = expected
    summary = V3EvaluationSummary.model_validate_json(canonical_json(payload))
    validate_report_privacy(summary)
    return summary, claimed == expected


def _load_results(path: Path) -> tuple[tuple[V3ShadowExecutionResult, ...], bool]:
    results: list[V3ShadowExecutionResult] = []
    hashes_valid = True
    for line in _read_text(path).splitlines():
        if not line.strip():
            continue
        _reject_non_finite(line)
        payload = json.loads(line, parse_float=Decimal)
        if not isinstance(payload, dict):
            raise ValueError("every results.jsonl record must be an object")
        claimed = payload.get("result_hash")
        if not isinstance(claimed, str):
            raise ValueError("every shadow result requires result_hash")
        expected = canonical_hash(
            {key: value for key, value in payload.items() if key != "result_hash"}
        )
        hashes_valid = hashes_valid and claimed == expected
        payload["result_hash"] = expected
        result = V3ShadowExecutionResult.model_validate_json(canonical_json(payload))
        validate_report_privacy(result)
        results.append(result)
    return tuple(results), hashes_valid


def _load_reviews(path: Path) -> tuple[V3ExpertReviewArtifact, ...]:
    reviews: list[V3ExpertReviewArtifact] = []
    for line in _read_text(path).splitlines():
        if not line.strip():
            continue
        _reject_non_finite(line)
        review = V3ExpertReviewArtifact.model_validate_json(line)
        validate_report_privacy(review)
        review_codes = (
            review.case_code,
            review.review_policy_version,
            *review.safety_violation_codes,
            *review.constraint_violation_codes,
            *review.difference_codes,
            *review.reviewer_reason_codes,
        )
        if review.reviewer_role_code is not None:
            review_codes = (*review_codes, review.reviewer_role_code)
        if any(not _MACHINE_CODE_PATTERN.fullmatch(str(value)) for value in review_codes):
            raise ValueError("expert review fields must contain machine codes only")
        reviews.append(review)
    return tuple(reviews)


def _manifest_checks(
    manifest: _ShadowManifest,
    *,
    manifest_path: Path,
    summary_path: Path,
    reviews_path: Path,
) -> tuple[bool, bool, Path]:
    explicit_paths = {
        "summary.json": summary_path.resolve(),
        "expert_review_template.jsonl": reviews_path.resolve(),
    }
    hashes_match = True
    counts_match = True
    results_path: Path | None = None
    for item in manifest.files:
        path = explicit_paths.get(item.file_name, (manifest_path.parent / item.file_name).resolve())
        if not path.is_file():
            hashes_match = False
            counts_match = False
            continue
        hashes_match = hashes_match and _sha256_file(path) == item.sha256
        counts_match = counts_match and _record_count(path) == item.record_count
        if item.file_name == "results.jsonl":
            results_path = path
    if results_path is None or not results_path.is_file():
        raise ValueError("manifest results.jsonl is unavailable")
    return hashes_match, counts_match, results_path


def _single_version(
    results: tuple[V3ShadowExecutionResult, ...],
    field_name: str,
) -> tuple[str, bool]:
    values = {getattr(item, field_name) for item in results}
    if not values:
        raise ValueError("promotion evidence requires at least one shadow result")
    return sorted(values)[0], len(values) == 1


def build_promotion_evidence(
    *,
    summary_path: Path,
    manifest_path: Path,
    reviews_path: Path,
    pricing_reference: V3ApprovedPricingReference | None,
) -> V3PromotionEvidence:
    """Reconstruct and cross-check an immutable C1 report bundle."""

    manifest_raw = _read_text(manifest_path)
    _reject_non_finite(manifest_raw)
    manifest = _ShadowManifest.model_validate_json(manifest_raw)
    validate_report_privacy(manifest.model_dump(mode="json"))
    hashes_match, counts_match, results_path = _manifest_checks(
        manifest,
        manifest_path=manifest_path,
        summary_path=summary_path,
        reviews_path=reviews_path,
    )
    summary, summary_hash_valid = _load_summary(summary_path)
    results, result_hashes_valid = _load_results(results_path)
    reviews = _load_reviews(reviews_path)

    graph_version, graph_consistent = _single_version(results, "graph_version")
    policy_version, policy_consistent = _single_version(results, "policy_version")
    catalog_version, catalog_consistent = _single_version(results, "catalog_version")
    prompt_version, prompt_consistent = _single_version(results, "prompt_version")
    provider_code, provider_consistent = _single_version(results, "provider_code")
    model_version, model_consistent = _single_version(results, "model_version")
    versions_consistent = all(
        (
            graph_consistent,
            policy_consistent,
            catalog_consistent,
            prompt_consistent,
            provider_consistent,
            model_consistent,
        )
    )

    reviewed = tuple(
        item for item in reviews if item.reviewer_decision is not V3ReviewerDecisionCode.PENDING
    )
    completion_rate = (
        None
        if not reviews
        else (Decimal(len(reviewed)) / Decimal(len(reviews))).quantize(_RATE_QUANTUM)
    )
    _, agreement_rate = summarize_expert_reviews(reviews)
    reviewer_complete = all(
        item.reviewer_role_code is not None
        and bool(item.reviewer_reason_codes)
        and item.reviewed_at is not None
        for item in reviewed
    )

    counts_match = counts_match and (summary.total_case_count == len(results) == len(reviews))
    pricing_matches = pricing_reference is not None
    if pricing_reference is not None:
        pricing_matches = (
            pricing_reference.provider_code == provider_code
            and pricing_reference.model_code == model_version
            and summary.currency_code == pricing_reference.currency_code
            and all(
                item.usage.pricing_reference_version
                in {None, pricing_reference.pricing_schema_version}
                for item in results
            )
        )

    return V3PromotionEvidence.create(
        fixture_version=manifest.fixture_version,
        harness_version=manifest.harness_version,
        graph_version=graph_version,
        policy_version=policy_version,
        catalog_version=catalog_version,
        prompt_version=prompt_version,
        provider_code=provider_code,
        model_version=model_version,
        total_case_count=summary.total_case_count,
        repeat_count=manifest.repeat_count,
        safety_invariant_pass_rate=summary.safety_invariant_pass_rate,
        safety_veto_override_count=summary.safety_veto_override_count,
        constraint_violation_rate=summary.constraint_violation_rate,
        structured_output_success_rate=summary.structured_output_success_rate,
        p95_latency_ms=summary.total_latency.p95_ms,
        input_token_count_total=summary.input_token_count_total,
        output_token_count_total=summary.output_token_count_total,
        average_cost_per_decision=summary.average_cost_per_decision,
        deterministic_fallback_rate=summary.deterministic_fallback_rate,
        expert_review_completion_rate=completion_rate,
        expert_agreement_rate=agreement_rate,
        expert_reviews_pending=len(reviewed) != len(reviews),
        reviewer_evidence_complete=reviewer_complete,
        currency_code=(pricing_reference.currency_code if pricing_reference else None),
        pricing_reference_version=(
            pricing_reference.pricing_schema_version if pricing_reference else None
        ),
        pricing_source_reference=(
            pricing_reference.source_reference if pricing_reference else None
        ),
        artifact_hashes_match=hashes_match,
        artifact_record_counts_match=counts_match,
        summary_hash_valid=summary_hash_valid,
        result_hashes_valid=result_hashes_valid,
        privacy_validation_passed=True,
        artifact_versions_consistent=versions_consistent,
        pricing_reference_supplied=pricing_reference is not None,
        pricing_reference_matches_evidence=pricing_matches,
        summary_hash=summary.summary_hash,
        summary_file_sha256=_sha256_file(summary_path),
        manifest_sha256=_sha256_bytes(manifest_raw.encode("utf-8")),
        results_sha256=_sha256_file(results_path),
        expert_reviews_sha256=_sha256_file(reviews_path),
    )


def _load_threshold(path: Path | None) -> V3PromotionThresholdReference | None:
    if path is None:
        return None
    raw = _read_text(path)
    _reject_non_finite(raw)
    return V3PromotionThresholdReference.model_validate_json(raw)


def _load_pricing(path: Path | None) -> V3ApprovedPricingReference | None:
    if path is None:
        return None
    raw = _read_text(path)
    _reject_non_finite(raw)
    return V3ApprovedPricingReference.model_validate_json(raw)


def _safe_output_directory(path: Path, *, working_directory: Path) -> Path:
    allowed_root = (working_directory / "outputs" / "v3-shadow").resolve()
    resolved = (working_directory / path).resolve() if not path.is_absolute() else path.resolve()
    if not resolved.is_relative_to(allowed_root):
        raise ValueError("promotion output must remain under outputs/v3-shadow")
    return resolved


def _decision_markdown(decision: V3PromotionDecision) -> str:
    reasons = "\n".join(f"  - `{item.value}`" for item in decision.reason_codes) or "  - None"
    return (
        "# V3 production promotion review gate\n\n"
        f"- Status: `{decision.status_code.value}`\n"
        f"- Decision hash: `{decision.decision_hash}`\n"
        f"- Evidence hash: `{decision.evidence_hash}`\n"
        "- Production activated: `false`\n"
        "- Human approval still required: `true`\n"
        "- Reason codes:\n"
        f"{reasons}\n\n"
        "This result only determines whether evidence is ready for human approval review. "
        "It never approves or enables production V3.\n"
    )


def write_decision(output_directory: Path, decision: V3PromotionDecision) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "promotion_decision.json"
    markdown_path = output_directory / "promotion_decision.md"
    json_path.write_text(
        f"{canonical_json(decision, pretty=True)}\n", encoding="utf-8", newline="\n"
    )
    markdown_path.write_text(_decision_markdown(decision), encoding="utf-8", newline="\n")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expert-reviews", type=Path, required=True)
    parser.add_argument("--threshold-reference", type=Path)
    parser.add_argument("--pricing-reference", type=Path)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("outputs/v3-shadow/promotion"),
    )
    args = parser.parse_args(argv)
    try:
        evidence = build_promotion_evidence(
            summary_path=args.summary,
            manifest_path=args.manifest,
            reviews_path=args.expert_reviews,
            pricing_reference=_load_pricing(args.pricing_reference),
        )
        decision = evaluate_v3_promotion(evidence, _load_threshold(args.threshold_reference))
        output_directory = _safe_output_directory(
            args.output_directory, working_directory=Path.cwd()
        )
        paths = write_decision(output_directory, decision)
    except (OSError, ValueError) as exc:
        print(f"V3 promotion evaluation failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print("\n".join(str(path) for path in paths))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["build_promotion_evidence", "main", "write_decision"]
