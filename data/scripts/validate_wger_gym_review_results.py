"""Validate edited wger gym review CSVs against an immutable DRAFT batch."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from build_wger_gym_review_batch import (
    CSV_FIELDS,
    PENDING_REVIEW_FIELDS,
    REVIEW_EVIDENCE_FIELDS,
    REVIEWER_ROLE_CODES,
    verify_review_batch,
)
from korean_display_name_rules import (
    display_name_problems,
    duplicate_display_names,
)
from profile_wger_exercises import canonical_text
from wger_exercise_pipeline import PipelineError

RESULT_VALIDATOR_VERSION = "0.1.0"
ALLOWED_REVIEW_DECISIONS = {"PENDING", "INCLUDE", "EXCLUDE", "MERGE"}
ALLOWED_BEGINNER_VALUES = {"PENDING", "YES", "CONDITIONAL", "NO"}
ALLOWED_APPROVAL_VALUES = {"PENDING", "APPROVED", "REJECTED"}
ALLOWED_REVIEW_STATUS_CODES = {
    "DRAFT",
    "TECH_REVIEWED",
    "DOMAIN_APPROVED",
    "REJECTED",
    "DEPRECATED",
}
MACHINE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
DEFAULT_TAXONOMY_REGISTRY = (
    Path(__file__).resolve().parents[1] / "normalized" / "exercise_taxonomy_codes.json"
)
OPAQUE_REVIEWER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$")

MAPPING_EDITABLE_FIELDS = set(PENDING_REVIEW_FIELDS)
EVIDENCE_EDITABLE_FIELDS = {
    "review_status_code",
    "reviewer_reference",
    "evidence_reference",
    "reviewed_at",
}

REQUIRED_EVIDENCE_STATUS_BY_ROLE = {
    "DATA_OWNER": {"TECH_REVIEWED", "DOMAIN_APPROVED"},
    "BACKEND_REVIEWER": {"TECH_REVIEWED", "DOMAIN_APPROVED"},
    "PM_REVIEWER": {"TECH_REVIEWED", "DOMAIN_APPROVED"},
    "DOMAIN_REVIEWER": {"DOMAIN_APPROVED"},
}


def read_csv(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    try:
        with path.resolve().open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != expected_fields:
                raise PipelineError(f"CSV columns do not match the template: {path.name}")
            return list(reader)
    except FileNotFoundError as exc:
        raise PipelineError(f"review result CSV is missing: {path}") from exc


def compare_immutable_fields(
    template: dict[str, str],
    result: dict[str, str],
    editable_fields: set[str],
    *,
    record_label: str,
) -> None:
    for field, template_value in template.items():
        if field in editable_fields:
            continue
        if result.get(field, "") != template_value:
            raise PipelineError(f"immutable {record_label} field changed: {field}")


def parse_timezone_timestamp(value: str, field_name: str) -> str:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PipelineError(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PipelineError(f"{field_name} must include timezone information")
    return value.strip()


def validate_mapping_row(
    row: dict[str, str], row_number: int, approved_movement_patterns: set[str]
) -> None:
    decision = row["review_decision"].strip()
    beginner = row["review_beginner_suitability"].strip()
    if decision not in ALLOWED_REVIEW_DECISIONS:
        raise PipelineError(f"mapping row {row_number} review_decision is invalid")
    if beginner not in ALLOWED_BEGINNER_VALUES:
        raise PipelineError(f"mapping row {row_number} review_beginner_suitability is invalid")
    for field in (
        "review_execution_guidance_status",
        "review_license_status",
        "review_domain_safety_status",
    ):
        if row[field].strip() not in ALLOWED_APPROVAL_VALUES:
            raise PipelineError(f"mapping row {row_number} {field} is invalid")

    if decision in {"INCLUDE", "MERGE"}:
        stable_code = row["review_normalized_exercise_id"].strip()
        taxonomy_code = row["review_taxonomy_code"].strip()
        if not MACHINE_CODE_PATTERN.fullmatch(stable_code):
            raise PipelineError(f"mapping row {row_number} normalized exercise ID is invalid")
        problems = display_name_problems(
            row["review_display_name_ko"], source_name=row["primary_source_name_en"]
        )
        if problems:
            raise PipelineError(f"mapping row {row_number} {problems[0]}")
        if taxonomy_code not in approved_movement_patterns:
            raise PipelineError(
                f"mapping row {row_number} taxonomy code is not an approved "
                f"movement pattern: {taxonomy_code}"
            )
        if beginner == "PENDING":
            raise PipelineError(f"mapping row {row_number} beginner suitability is still PENDING")
        for field in (
            "review_execution_guidance_status",
            "review_license_status",
            "review_domain_safety_status",
        ):
            if row[field].strip() != "APPROVED":
                raise PipelineError(
                    f"mapping row {row_number} cannot be {decision} while {field} is not APPROVED"
                )
    elif decision == "EXCLUDE" and not canonical_text(row["reviewer_notes"]):
        raise PipelineError(f"mapping row {row_number} exclusion reason is missing")


def validate_evidence_row(row: dict[str, str], row_number: int) -> None:
    role_code = row["reviewer_role_code"].strip()
    status_code = row["review_status_code"].strip()
    if role_code not in REVIEWER_ROLE_CODES:
        raise PipelineError(f"evidence row {row_number} reviewer role is invalid")
    if status_code not in ALLOWED_REVIEW_STATUS_CODES:
        raise PipelineError(f"evidence row {row_number} review status is invalid")

    reviewer_reference = row["reviewer_reference"].strip()
    evidence_reference = row["evidence_reference"].strip()
    reviewed_at = row["reviewed_at"].strip()
    if status_code == "DRAFT":
        if reviewer_reference or evidence_reference or reviewed_at:
            raise PipelineError(
                f"evidence row {row_number} DRAFT record must keep evidence fields blank"
            )
        return
    if not OPAQUE_REVIEWER_PATTERN.fullmatch(reviewer_reference) or "@" in reviewer_reference:
        raise PipelineError(
            f"evidence row {row_number} reviewer_reference must be an opaque internal code"
        )
    if not evidence_reference:
        raise PipelineError(f"evidence row {row_number} evidence_reference is missing")
    parse_timezone_timestamp(reviewed_at, f"evidence row {row_number} reviewed_at")


def load_approved_movement_patterns(registry_path: Path) -> set[str]:
    """승인된 movement pattern 코드 집합. 승인 registry가 없으면 실패한다."""

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"taxonomy registry is missing: {registry_path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("taxonomy registry is not valid JSON") from exc
    if registry.get("status") != "APPROVED":
        raise PipelineError("taxonomy registry is not APPROVED")
    entries = registry.get("code_sets", {}).get("movement_pattern_code")
    if not isinstance(entries, list) or not entries:
        raise PipelineError("taxonomy registry has no movement_pattern_code list")
    return {str(entry["code"]) for entry in entries if isinstance(entry, dict)}


def validate_review_results(
    batch_dir: Path,
    mapping_results_path: Path,
    evidence_results_path: Path,
    taxonomy_registry_path: Path = DEFAULT_TAXONOMY_REGISTRY,
) -> dict[str, object]:
    batch_dir = batch_dir.resolve()
    verify_review_batch(batch_dir)
    approved_movement_patterns = load_approved_movement_patterns(taxonomy_registry_path)
    template_mapping = read_csv(batch_dir / "gym_core_review_batch.csv", CSV_FIELDS)
    template_evidence = read_csv(
        batch_dir / "catalog_review_records_template.csv", REVIEW_EVIDENCE_FIELDS
    )
    result_mapping = read_csv(mapping_results_path, CSV_FIELDS)
    result_evidence = read_csv(evidence_results_path, REVIEW_EVIDENCE_FIELDS)
    if len(result_mapping) != len(template_mapping):
        raise PipelineError("mapping result row count does not match the batch")
    if len(result_evidence) != len(template_evidence):
        raise PipelineError("evidence result row count does not match the batch")

    mapping_by_exercise_id: dict[int, dict[str, str]] = {}
    decision_counts = {code: 0 for code in sorted(ALLOWED_REVIEW_DECISIONS)}
    for row_number, (template, result) in enumerate(
        zip(template_mapping, result_mapping, strict=True), start=2
    ):
        compare_immutable_fields(
            template,
            result,
            MAPPING_EDITABLE_FIELDS,
            record_label="mapping",
        )
        validate_mapping_row(result, row_number, approved_movement_patterns)
        exercise_id = int(result["source_exercise_id"])
        if exercise_id in mapping_by_exercise_id:
            raise PipelineError("mapping result source_exercise_id must be unique")
        mapping_by_exercise_id[exercise_id] = result
        decision_counts[result["review_decision"].strip()] += 1

    evidence_by_key: dict[tuple[int, str], dict[str, str]] = {}
    evidence_status_counts = {code: 0 for code in sorted(ALLOWED_REVIEW_STATUS_CODES)}
    for row_number, (template, result) in enumerate(
        zip(template_evidence, result_evidence, strict=True), start=2
    ):
        compare_immutable_fields(
            template,
            result,
            EVIDENCE_EDITABLE_FIELDS,
            record_label="evidence",
        )
        validate_evidence_row(result, row_number)
        exercise_id = int(result["source_exercise_id"])
        role_code = result["reviewer_role_code"].strip()
        key = (exercise_id, role_code)
        if key in evidence_by_key:
            raise PipelineError("evidence source and reviewer role must be unique")
        evidence_by_key[key] = result
        evidence_status_counts[result["review_status_code"].strip()] += 1

    duplicates = duplicate_display_names(
        mapping["review_display_name_ko"]
        for mapping in mapping_by_exercise_id.values()
        if mapping["review_decision"].strip() in {"INCLUDE", "MERGE"}
    )
    if duplicates:
        raise PipelineError(
            "Korean display name is used by more than one exercise: " + ", ".join(duplicates)
        )

    review_complete_rows = 0
    for exercise_id, mapping in mapping_by_exercise_id.items():
        decision = mapping["review_decision"].strip()
        if decision not in {"INCLUDE", "MERGE"}:
            continue
        for role_code, accepted_statuses in REQUIRED_EVIDENCE_STATUS_BY_ROLE.items():
            evidence = evidence_by_key.get((exercise_id, role_code))
            if evidence is None or evidence["review_status_code"].strip() not in accepted_statuses:
                raise PipelineError(
                    f"exercise {exercise_id} cannot be {decision} "
                    f"without completed {role_code} evidence"
                )
        review_complete_rows += 1

    return {
        "validator_version": RESULT_VALIDATOR_VERSION,
        "taxonomy_registry_status": "APPROVED",
        "batch": batch_dir.name,
        "mapping_rows": len(result_mapping),
        "evidence_rows": len(result_evidence),
        "decision_counts": decision_counts,
        "evidence_status_counts": evidence_status_counts,
        "review_complete_rows": review_complete_rows,
        "status": "valid",
        "production_eligible": False,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("mapping_results", type=Path)
    parser.add_argument("evidence_results", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        result = validate_review_results(args.batch, args.mapping_results, args.evidence_results)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
