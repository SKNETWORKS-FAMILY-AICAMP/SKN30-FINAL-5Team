#!/usr/bin/env python3
"""Apply explicit human approval to the MET review recommendations.

Only recommendation rows with a non-empty MET and a type other than
NO_RECOMMENDATION are applied. The original exercise_met_mapping.csv is never
written by this script.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

from process_met_review_recommendations import read_recommendations

MAPPING_FIELDS = [
    "exercise_id",
    "exercise_name",
    "representative_id",
    "met_value",
    "intensity_level",
    "met_source",
    "source_activity_name",
    "mapping_basis",
    "review_status",
    "production_eligible",
]
CHANGE_FIELDS = [
    "exercise_id",
    "existing_status",
    "recommended_met",
    "final_decision",
    "decision_basis",
    "compendium_source",
]
COMPENDIUM_URL = "https://pacompendium.com/"
COMPENDIUM_NAMES = {
    "02022": "Calisthenics, moderate effort",
    "02048": "Elliptical trainer, moderate effort",
    "02050": (
        "Resistance (weight lifting - free weight, nautilus or universal-type), vigorous effort"
    ),
    "02052": "Resistance (weight) training, squats, deadlift, slow or explosive effort",
    "02054": "Resistance (weight) training, multiple exercises, 8-15 reps at varied resistance",
    "02056": "Body weight resistance exercises, general",
    "02057": "Body weight resistance exercises, high intensity",
    "02065": "Stair treadmill ergometer, general",
    "02068": "Rope skipping exercise, general",
    "02101": "Stretching, mild",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def selected_code(recommendation: dict[str, str]) -> str:
    code = recommendation.get("compendium_activity_code", "").strip()
    if code:
        return code
    match = re.search(r"(?:020\d\d|02101)", recommendation.get("recommendation_basis", ""))
    return match.group(0) if match else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--recommendations", type=Path, required=True)
    parser.add_argument("--decision-required", type=Path, required=True)
    parser.add_argument("--all-recommendations", type=Path, required=True)
    parser.add_argument("--output-mapping", type=Path, required=True)
    parser.add_argument("--output-change-log", type=Path, required=True)
    args = parser.parse_args()

    mapping_rows = read_csv(args.mapping)
    recommendation_rows = read_csv(args.recommendations)
    decision_rows = read_csv(args.decision_required)
    all_recommendation_rows = read_recommendations(args.all_recommendations)
    mapping_by_id = {row["exercise_id"]: row for row in mapping_rows}
    recommendation_by_id = {row["exercise_id"]: row for row in recommendation_rows}
    all_recommendation_by_id = {row["exercise_id"]: row for row in all_recommendation_rows}
    decision_ids = {row["exercise_id"] for row in decision_rows}
    if len(mapping_by_id) != len(mapping_rows):
        raise ValueError("duplicate exercise_id in source mapping")
    if decision_ids != set(recommendation_by_id):
        raise ValueError("decision-required and recommendation IDs do not match")
    review_ids = {
        row["exercise_id"] for row in mapping_rows if row["review_status"] == "REVIEW_REQUIRED"
    }
    if set(all_recommendation_by_id) != review_ids:
        raise ValueError(
            "all recommendations must contain exactly the 207 REVIEW_REQUIRED mapping IDs"
        )
    if not decision_ids <= set(mapping_by_id):
        raise ValueError("recommendation contains an unknown exercise_id")

    effective_by_id: dict[str, dict[str, str]] = {}
    for exercise_id, original in all_recommendation_by_id.items():
        effective = dict(original)
        if exercise_id in recommendation_by_id:
            for key, value in recommendation_by_id[exercise_id].items():
                if value != "":
                    effective[key] = value
        effective_by_id[exercise_id] = effective

    approved_ids = {
        exercise_id
        for exercise_id, row in effective_by_id.items()
        if row.get("recommendation_type") != "NO_RECOMMENDATION"
        and row.get("recommended_met", "").strip()
        and selected_code(row)
    }
    no_recommendation_ids = {
        exercise_id
        for exercise_id, row in effective_by_id.items()
        if row.get("recommendation_type") == "NO_RECOMMENDATION"
    }
    if approved_ids & no_recommendation_ids:
        raise ValueError("NO_RECOMMENDATION row cannot be approved")
    if approved_ids | no_recommendation_ids != set(all_recommendation_by_id):
        raise ValueError(
            "recommendation rows must have either an approved value or NO_RECOMMENDATION"
        )

    reviewed_rows: list[dict[str, Any]] = []
    for source in mapping_rows:
        row = dict(source)
        recommendation = effective_by_id.get(source["exercise_id"])
        if recommendation is not None and source["exercise_id"] in approved_ids:
            code = selected_code(recommendation)
            row["exercise_name"] = recommendation["exercise_name"]
            row["met_value"] = recommendation["recommended_met"]
            row["intensity_level"] = recommendation["recommended_intensity"]
            row["met_source"] = f"ADULT_COMPENDIUM_2024;activity_code={code};url={COMPENDIUM_URL}"
            row["source_activity_name"] = recommendation.get(
                "compendium_activity_name", ""
            ) or COMPENDIUM_NAMES.get(code, "")
            recommendation_label = recommendation.get(
                "recommendation_type", ""
            ) or recommendation.get("recommendation_basis", "")
            row["mapping_basis"] = f"USER_APPROVED_{recommendation_label}"
            row["review_status"] = "APPROVED"
        elif recommendation is not None and source["exercise_id"] in no_recommendation_ids:
            row["met_value"] = ""
            row["intensity_level"] = "REVIEW_REQUIRED"
            row["review_status"] = "REVIEW_REQUIRED"
        # The source catalog is DRAFT, so no row is production eligible.
        row["production_eligible"] = "false"
        reviewed_rows.append(row)

    change_rows: list[dict[str, Any]] = []
    for recommendation in sorted(all_recommendation_rows, key=lambda row: row["exercise_id"]):
        exercise_id = recommendation["exercise_id"]
        source = mapping_by_id[exercise_id]
        effective = effective_by_id[exercise_id]
        if exercise_id in approved_ids:
            final_decision = "APPROVED"
            basis_prefix = "USER_APPROVED"
            applied_recommendation = effective
        elif exercise_id in no_recommendation_ids:
            final_decision = "REVIEW_REQUIRED"
            basis_prefix = "NO_RECOMMENDATION_EXCLUDED_FROM_APPROVAL"
            applied_recommendation = effective
        else:
            final_decision = "REVIEW_REQUIRED"
            basis_prefix = "USER_APPROVAL_PENDING_OUTSIDE_CURRENT_BATCH"
            applied_recommendation = effective
        change_rows.append(
            {
                "exercise_id": exercise_id,
                "existing_status": source["review_status"],
                "recommended_met": applied_recommendation.get("recommended_met", ""),
                "final_decision": final_decision,
                "decision_basis": (
                    f"{basis_prefix}; recommendation_type="
                    f"{applied_recommendation.get('recommendation_type', '')}; "
                    "assumed_execution_condition="
                    f"{applied_recommendation.get('assumed_execution_condition', '')}; "
                    f"reason={applied_recommendation.get('recommendation_reason', '')}"
                ),
                "compendium_source": (
                    applied_recommendation.get("compendium_reference", "")
                    or "ADULT_COMPENDIUM_2024;activity_code="
                    f"{selected_code(applied_recommendation)};url={COMPENDIUM_URL}"
                ),
            }
        )

    write_csv(args.output_mapping, MAPPING_FIELDS, reviewed_rows)
    write_csv(args.output_change_log, CHANGE_FIELDS, change_rows)


if __name__ == "__main__":
    main()
