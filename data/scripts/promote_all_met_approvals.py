#!/usr/bin/env python3
"""Promote a complete MET mapping only after an explicit owner attestation."""

from __future__ import annotations

import argparse
import csv
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
MANIFEST_FIELDS = [
    "approval_scope",
    "reviewer",
    "reviewed_at",
    "decision",
    "evidence_reference",
    "decision_basis",
    "production_eligible",
]
CHANGE_FIELDS = [
    "exercise_id",
    "representative_id",
    "existing_status",
    "final_status",
    "existing_production_eligible",
    "final_production_eligible",
    "reviewer",
    "reviewed_at",
    "decision_basis",
    "evidence_reference",
]


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


def promote(
    mapping: list[dict[str, str]], manifest: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if len(manifest) != 1:
        raise ValueError("exactly one approval manifest row is required")
    decision = manifest[0]
    required = {field for field in MANIFEST_FIELDS if not decision.get(field)} - {
        "production_eligible"
    }
    if required:
        raise ValueError(f"approval manifest missing fields: {sorted(required)}")
    if (
        decision["approval_scope"] != "ALL_MET_MAPPINGS"
        or decision["decision"] != "DOMAIN_APPROVED"
    ):
        raise ValueError("manifest must explicitly approve ALL_MET_MAPPINGS as DOMAIN_APPROVED")
    if decision["production_eligible"].lower() != "true":
        raise ValueError("all-MET promotion requires production_eligible=true")
    if decision["evidence_reference"] not in {
        "https://pacompendium.com/adult-compendium/",
        "https://pacompendium.com/conditioning-exercise/",
    }:
        raise ValueError("manifest must cite the official Compendium")
    ids = [row.get("exercise_id", "") for row in mapping]
    if not mapping or len(set(ids)) != len(ids) or "" in ids:
        raise ValueError("mapping must have unique non-empty exercise IDs")
    if any(not row.get("met_value") for row in mapping):
        raise ValueError("cannot promote a mapping with an unresolved MET value")
    if any("pacompendium.com" not in row.get("met_source", "") for row in mapping):
        raise ValueError("every MET row must retain Compendium evidence")

    updated: list[dict[str, str]] = []
    changes: list[dict[str, str]] = []
    for source in mapping:
        row = dict(source)
        row["review_status"] = "DOMAIN_APPROVED"
        row["production_eligible"] = "true"
        row["met_source"] = (
            f"{source['met_source']};domain_approval={decision['reviewer']};"
            f"reviewed_at={decision['reviewed_at']};approval_scope=ALL_MET_MAPPINGS"
        )
        updated.append(row)
        changes.append(
            {
                "exercise_id": source["exercise_id"],
                "representative_id": source["representative_id"],
                "existing_status": source.get("review_status", ""),
                "final_status": "DOMAIN_APPROVED",
                "existing_production_eligible": source.get("production_eligible", ""),
                "final_production_eligible": "true",
                "reviewer": decision["reviewer"],
                "reviewed_at": decision["reviewed_at"],
                "decision_basis": decision["decision_basis"],
                "evidence_reference": decision["evidence_reference"],
            }
        )
    return updated, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-mapping", type=Path, required=True)
    parser.add_argument("--output-change-log", type=Path, required=True)
    args = parser.parse_args()
    updated, changes = promote(read_csv(args.mapping), read_csv(args.manifest))
    write_csv(args.output_mapping, MAPPING_FIELDS, updated)
    write_csv(args.output_change_log, CHANGE_FIELDS, changes)


if __name__ == "__main__":
    main()
