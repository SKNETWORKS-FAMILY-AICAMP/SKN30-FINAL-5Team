#!/usr/bin/env python3
"""Apply an explicit, evidence-backed approval to final MET mapping rows.

The approval CSV is a review decision, not a generated catalog artifact.  The
script validates the selected activity against the normalized Compendium
subset, updates only approved IDs, and keeps production eligibility fail-closed.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

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
APPROVAL_FIELDS = [
    "exercise_id",
    "representative_id",
    "reviewer",
    "reviewed_at",
    "decision",
    "met_value",
    "intensity_level",
    "compendium_activity_code",
    "compendium_activity_name",
    "decision_basis",
    "evidence_reference",
    "production_eligible",
]
CHANGE_FIELDS = [
    "exercise_id",
    "representative_id",
    "existing_met_value",
    "approved_met_value",
    "existing_status",
    "final_status",
    "reviewer",
    "reviewed_at",
    "decision_basis",
    "evidence_reference",
]
COMPENDIUM_PATH = (
    Path(__file__).resolve().parents[1]
    / "normalized"
    / "physical_activity_reference_v0.1.0"
    / "adult_compendium_reference_subset.json"
)
COMPENDIUM_URL = "https://pacompendium.com/conditioning-exercise/"
# The MVP normalized subset does not include yoga rows.  This exact tuple is
# transcribed from the official Compendium page cited in the approval record.
EXTERNAL_COMPENDIUM_ROWS = {
    "02150": {"activity_description": "Yoga, Hatha", "met_value": 2.3},
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV header missing: {path}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def load_compendium() -> dict[str, dict[str, Any]]:
    payload = json.loads(COMPENDIUM_PATH.read_text(encoding="utf-8"))
    return {str(row["activity_code"]): row for row in payload["activities"]}


def validate_approval(
    row: dict[str, str],
    mapping_by_id: dict[str, dict[str, str]],
    compendium: dict[str, dict[str, Any]],
) -> None:
    required = {field for field in APPROVAL_FIELDS if not row.get(field)} - {"production_eligible"}
    if required:
        raise ValueError(
            f"approval missing fields for {row.get('exercise_id', '')}: {sorted(required)}"
        )
    if row["decision"] not in {"APPROVED", "DOMAIN_APPROVED"}:
        raise ValueError(
            f"only APPROVED or DOMAIN_APPROVED decisions can be applied: {row['exercise_id']}"
        )
    if row["production_eligible"].lower() == "true" and row["decision"] != "DOMAIN_APPROVED":
        raise ValueError("production_eligible=true requires DOMAIN_APPROVED")
    if row["exercise_id"] not in mapping_by_id:
        raise ValueError(f"approval references unknown exercise_id: {row['exercise_id']}")
    source = mapping_by_id[row["exercise_id"]]
    if source["representative_id"] != row["representative_id"]:
        raise ValueError(f"representative mismatch: {row['exercise_id']}")
    activity = compendium.get(row["compendium_activity_code"]) or EXTERNAL_COMPENDIUM_ROWS.get(
        row["compendium_activity_code"]
    )
    if activity is None:
        raise ValueError(f"unknown Compendium activity code: {row['compendium_activity_code']}")
    if activity["activity_description"] != row["compendium_activity_name"]:
        raise ValueError(f"Compendium activity name mismatch: {row['exercise_id']}")
    if float(str(activity["met_value"])) != float(row["met_value"]):
        raise ValueError(f"Compendium MET mismatch: {row['exercise_id']}")
    if row["evidence_reference"] != COMPENDIUM_URL:
        raise ValueError("approval must cite the official Compendium conditioning page")
    if "PROXY" not in row["decision_basis"]:
        raise ValueError("non-direct MET approval must state PROXY in decision_basis")


def apply(
    mapping_rows: list[dict[str, str]], approvals: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    mapping_by_id = {row["exercise_id"]: row for row in mapping_rows}
    if len(mapping_by_id) != len(mapping_rows):
        raise ValueError("duplicate exercise_id in mapping")
    approval_by_id = {row["exercise_id"]: row for row in approvals}
    if len(approval_by_id) != len(approvals):
        raise ValueError("duplicate exercise_id in approvals")
    compendium = load_compendium()
    for row in approvals:
        validate_approval(row, mapping_by_id, compendium)

    updated: list[dict[str, str]] = []
    changes: list[dict[str, str]] = []
    for source in mapping_rows:
        row = dict(source)
        approval = approval_by_id.get(source["exercise_id"])
        if approval is not None:
            code = approval["compendium_activity_code"]
            row.update(
                {
                    "met_value": approval["met_value"],
                    "intensity_level": approval["intensity_level"],
                    "met_source": (
                        f"ADULT_COMPENDIUM_2024;activity_code={code};"
                        f"url={approval['evidence_reference']};mapping_kind=USER_APPROVED_PROXY;"
                        f"reviewer={approval['reviewer']};reviewed_at={approval['reviewed_at']}"
                    ),
                    "source_activity_name": approval["compendium_activity_name"],
                    "mapping_basis": f"USER_APPROVED_PROXY_{code}_STATIC_BALANCE",
                    "review_status": approval["decision"],
                    "production_eligible": approval["production_eligible"].lower(),
                }
            )
            changes.append(
                {
                    "exercise_id": source["exercise_id"],
                    "representative_id": source["representative_id"],
                    "existing_met_value": source.get("met_value", ""),
                    "approved_met_value": approval["met_value"],
                    "existing_status": source.get("review_status", ""),
                    "final_status": approval["decision"],
                    "reviewer": approval["reviewer"],
                    "reviewed_at": approval["reviewed_at"],
                    "decision_basis": approval["decision_basis"],
                    "evidence_reference": approval["evidence_reference"],
                }
            )
        if approval is None:
            row["production_eligible"] = "false"
        updated.append(row)
    return updated, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--approvals", type=Path, required=True)
    parser.add_argument("--output-mapping", type=Path, required=True)
    parser.add_argument("--output-change-log", type=Path, required=True)
    args = parser.parse_args()
    updated, changes = apply(read_csv(args.mapping), read_csv(args.approvals))
    write_csv(args.output_mapping, MAPPING_FIELDS, updated)
    write_csv(args.output_change_log, CHANGE_FIELDS, changes)


if __name__ == "__main__":
    main()
