#!/usr/bin/env python3
"""Fail-closed review pipeline for the representative exercise catalog.

The representative catalog is an upstream selection artifact.  This pipeline
does not edit it in place and never removes a review code without a complete,
auditable approval record.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/reports/representative_exercise_catalog.csv"
DEFAULT_INTEGRATED = ROOT / "data/reports/integrated_exercise_review_updated.csv"
DEFAULT_OUTPUT = ROOT / "data/reports/reviewed_exercise_catalog.csv"
DEFAULT_LOG = ROOT / "data/reports/review_log.csv"
DEFAULT_PRODUCTION = ROOT / "data/reports/production_ready_catalog.csv"

REVIEW_CODE_FIELDS = ("removable_review_required_codes", "additional_review_required_codes")
REVIEW_DECISION = "PENDING"
PENDING_REASON = "REVIEW_EVIDENCE_NOT_AVAILABLE"
FINAL_GATE_REASON = "FINAL_APPROVAL_REVIEW_NOT_COMPLETED"

REVIEWED_FIELDS = (
    "reviewed_family",
    "reviewed_variant_relation",
    "reviewed_movement_pattern",
    "reviewed_equipment",
    "reviewed_name",
    "reviewed_description",
    "beginner_suitability",
    "reviewed_dosage",
    "reviewed_load_profile",
    "safety_rule",
    "contraindication",
    "stop_condition",
    "alternative_exercise_id",
)

OUTPUT_FIELDS = (
    "review_required",
    "review_required_codes",
    *REVIEWED_FIELDS,
    "media_source",
    "license_type",
    "attribution_text",
    "usage_permission",
    "review_decision",
    "review_reason_code",
    "review_reason",
    "reviewer",
    "reviewed_at",
    "review_status",
    "production_eligible",
    "production_eligibility_blockers",
)

LOG_FIELDS = (
    "exercise_id",
    "review_type",
    "previous_status",
    "review_decision",
    "review_reason_code",
    "reviewer",
    "reviewed_at",
)


def split_codes(value: str) -> list[str]:
    return [code for code in value.split("|") if code]


def merge_codes(row: dict[str, str]) -> list[str]:
    """Derive codes from upstream code fields without trusting a status flag."""

    codes: list[str] = []
    for field in REVIEW_CODE_FIELDS:
        for code in split_codes(row.get(field, "")):
            if code not in codes:
                codes.append(code)
    return codes


def load_integrated_metadata(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        metadata: dict[str, dict[str, str]] = {}
        for row in rows:
            key = f"{row.get('source_system', '')}:{row.get('source_id', '')}"
            if key != ":":
                metadata[key] = row
        return metadata


def source_metadata(row: dict[str, str], integrated: dict[str, dict[str, str]]) -> dict[str, str]:
    source = integrated.get(row.get("representative_source_id", ""), {})
    return {
        "media_source": source.get("source_media_reference", "") or "REVIEW_REQUIRED",
        "license_type": (
            source.get("license_name", "")
            or source.get("source_license", "")
            or "REVIEW_REQUIRED"
        ),
        "attribution_text": source.get("attribution_text", "") or "REVIEW_REQUIRED",
        # Source metadata is not the same as a completed rights decision.
        "usage_permission": "REVIEW_REQUIRED",
    }


def make_row(row: dict[str, str], integrated: dict[str, dict[str, str]]) -> dict[str, str]:
    codes = merge_codes(row)
    blockers = []
    if codes:
        blockers.append("REVIEW_REQUIRED_CODES_PRESENT")
    blockers.extend(
        (
            "REVIEW_DECISION_NOT_APPROVED",
            "FINAL_REVIEWER_REQUIRED",
            "FINAL_REVIEWED_AT_REQUIRED",
        )
    )
    result = dict(row)
    result.update(
        {
            "review_required": "true" if codes else "false",
            "review_required_codes": "|".join(codes),
            # No completed review evidence exists in the current repository.
            **{field: "REVIEW_REQUIRED" for field in REVIEWED_FIELDS},
            **source_metadata(row, integrated),
            "review_decision": REVIEW_DECISION,
            "review_reason_code": PENDING_REASON,
            "review_reason": (
                "선행 검수 결과가 PENDING이거나 reviewer/reviewed_at/승인 근거가 없어 "
                "코드를 제거하지 않고 보류함."
            ),
            "reviewer": "",
            "reviewed_at": "",
            "review_status": "REVIEW_REQUIRED",
            "production_eligible": "false",
            "production_eligibility_blockers": "|".join(blockers),
        }
    )
    return result


def make_log(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    log: list[dict[str, str]] = []
    for row in rows:
        codes = split_codes(row["review_required_codes"])
        review_types = codes or ["FINAL_APPROVAL"]
        for review_type in review_types:
            log.append(
                {
                    "exercise_id": row["representative_id"],
                    "review_type": review_type,
                    "previous_status": row.get("representative_review_status", ""),
                    "review_decision": row["review_decision"],
                    "review_reason_code": (
                        PENDING_REASON if review_type != "FINAL_APPROVAL" else FINAL_GATE_REASON
                    ),
                    "reviewer": row["reviewer"],
                    "reviewed_at": row["reviewed_at"],
                }
            )
    return log


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(
    input_path: Path = DEFAULT_INPUT,
    integrated_path: Path = DEFAULT_INTEGRATED,
    output_path: Path = DEFAULT_OUTPUT,
    log_path: Path = DEFAULT_LOG,
    production_path: Path = DEFAULT_PRODUCTION,
) -> dict[str, object]:
    with input_path.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    if not source_rows:
        raise ValueError("representative catalog is empty")
    if len({row.get("representative_id", "") for row in source_rows}) != len(source_rows):
        raise ValueError("representative_id must be unique")

    integrated = load_integrated_metadata(integrated_path)
    reviewed_rows = [make_row(row, integrated) for row in source_rows]
    fields = list(dict.fromkeys([*source_rows[0].keys(), *OUTPUT_FIELDS]))
    write_csv(output_path, reviewed_rows, fields)

    log_rows = make_log(reviewed_rows)
    write_csv(log_path, log_rows, list(LOG_FIELDS))

    production_rows = [
        row
        for row in reviewed_rows
        if row["review_status"] == "FINAL_APPROVED" and row["production_eligible"] == "true"
    ]
    write_csv(production_path, production_rows, fields)

    unresolved = Counter(
        code
        for row in reviewed_rows
        for code in split_codes(row["review_required_codes"])
    )
    return {
        "input": str(input_path),
        "reviewed_output": str(output_path),
        "review_log": str(log_path),
        "production_output": str(production_path),
        "input_rows": len(source_rows),
        "reviewed_rows": len(reviewed_rows),
        "final_approved_rows": len(production_rows),
        "review_required_rows": sum(row["review_required"] == "true" for row in reviewed_rows),
        "unresolved_review_required_codes": dict(unresolved),
        "review_log_rows": len(log_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--integrated", type=Path, default=DEFAULT_INTEGRATED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--production", type=Path, default=DEFAULT_PRODUCTION)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run(args.input, args.integrated, args.output, args.log, args.production),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
