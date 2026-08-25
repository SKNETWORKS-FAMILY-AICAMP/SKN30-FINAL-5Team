#!/usr/bin/env python3
"""Build a human-review batch from unresolved MET mappings.

This script is intentionally one-way: it creates a review worksheet and does
not modify the source mapping or approve any row.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

BATCH_FIELDS = [
    "exercise_id",
    "exercise_name",
    "representative_id",
    "family",
    "movement_pattern",
    "equipment",
    "difficulty",
    "intensity",
    "current_candidate_met",
    "candidate_compendium_activity",
    "review_reason",
    "recommended_met",
    "alternative_met_options",
    "compendium_reference",
    "decision_required",
    "reviewer_decision",
    "reviewer_comment",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BATCH_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in BATCH_FIELDS} for row in rows)


def first_value(*values: str) -> str:
    return next((value.strip() for value in values if value and value.strip()), "REVIEW_REQUIRED")


def candidate_met_values(text: str) -> str:
    values = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*MET", text, flags=re.IGNORECASE)
    if not values:
        return "NO_DIRECT_MATCH_IDENTIFIED"
    return " | ".join(value.upper().replace(" MET", "") for value in values)


def build_batch(
    mapping_rows: list[dict[str, str]],
    review_rows: list[dict[str, str]],
    representative_rows: list[dict[str, str]],
    catalog_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    mapping_by_id = {row["exercise_id"]: row for row in mapping_rows}
    catalog_by_id = {row["normalized_exercise_id"]: row for row in catalog_rows}
    representative_by_id = {row["representative_id"]: row for row in representative_rows}
    batch: list[dict[str, Any]] = []

    for review in sorted(review_rows, key=lambda row: row["exercise_id"]):
        exercise_id = review["exercise_id"]
        mapping = mapping_by_id[exercise_id]
        catalog = catalog_by_id[exercise_id]
        representative = representative_by_id[mapping["representative_id"]]
        candidate_activity = mapping["source_activity_name"] or review["suggested_mapping"]
        batch.append(
            {
                "exercise_id": exercise_id,
                "exercise_name": review["exercise_name"],
                "representative_id": mapping["representative_id"],
                "family": first_value(
                    catalog.get("exercise_family", ""),
                    representative.get("reviewed_family", ""),
                    representative.get("exercise_family", ""),
                ),
                "movement_pattern": first_value(
                    catalog.get("movement_pattern_code_candidate", ""),
                    representative.get("reviewed_movement_pattern", ""),
                    representative.get("movement_pattern", ""),
                ),
                "equipment": first_value(
                    catalog.get("equipment_code_candidate", ""),
                    representative.get("reviewed_equipment", ""),
                    representative.get("equipment", ""),
                ),
                "difficulty": first_value(
                    catalog.get("difficulty_code_candidate", ""),
                    representative.get("difficulty", ""),
                ),
                "intensity": first_value(catalog.get("intensity_level_candidate", "")),
                "current_candidate_met": candidate_met_values(review["suggested_mapping"]),
                "candidate_compendium_activity": candidate_activity,
                "review_reason": review["reason"],
                # No recommendation is made before expert review.
                "recommended_met": "",
                "alternative_met_options": review["suggested_mapping"]
                or "NO_DIRECT_MATCH_IDENTIFIED",
                "compendium_reference": mapping["met_source"],
                "decision_required": (
                    f"{review['issue_type']}: 수행 조건을 확인하고 공식 Compendium "
                    "activity/MET를 하나 선택하거나 "
                    "REVIEW_REQUIRED 유지"
                ),
                "reviewer_decision": "",
                "reviewer_comment": "",
            }
        )
    return batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--review-log", type=Path, required=True)
    parser.add_argument("--representative", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mapping_rows = read_csv(args.mapping)
    review_rows = read_csv(args.review_log)
    representative_rows = read_csv(args.representative)
    catalog_rows = read_csv(args.catalog)
    unresolved_ids = {
        row["exercise_id"] for row in mapping_rows if row["review_status"] == "REVIEW_REQUIRED"
    }
    review_ids = {row["exercise_id"] for row in review_rows}
    if unresolved_ids != review_ids:
        raise ValueError("mapping and review log REVIEW_REQUIRED IDs do not match")
    batch = build_batch(mapping_rows, review_rows, representative_rows, catalog_rows)
    write_csv(args.output, batch)


if __name__ == "__main__":
    main()
