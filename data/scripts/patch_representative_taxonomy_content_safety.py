#!/usr/bin/env python3
"""Apply the five approved taxonomy corrections and patch derived CSV rows."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from generate_representative_content_safety import (
    CONTENT_COLUMNS,
    LOG_COLUMNS,
    SAFETY_COLUMNS,
    content_for,
    read_rows,
    safety_for,
    write_csv,
)


PATCHES = {
    "REX-000059": {
        "exercise_family": "CARDIO",
        "movement_pattern": "JUMP_PLYOMETRIC",
        "equipment": "BODYWEIGHT",
        "training_type": "CARDIO",
        "reviewed_cardio_equipment": "NO_EQUIPMENT_BODYWEIGHT",
        "reviewed_equipment": "equipment=BODYWEIGHT;requires_equipment=false;locations=HOME|GYM",
        "reason": "JUMPING_JACK_CARDIO_TAXONOMY_CONFIRMED",
    },
    "REX-000060": {
        "exercise_family": "CARDIO",
        "movement_pattern": "JUMP_PLYOMETRIC",
        "equipment": "JUMP_ROPE",
        "training_type": "CARDIO",
        "reviewed_cardio_equipment": "JUMP_ROPE",
        "reviewed_equipment": "equipment=JUMP_ROPE;requires_equipment=true;locations=HOME|GYM",
        "reason": "JUMP_ROPE_CARDIO_TAXONOMY_CONFIRMED",
    },
    "REX-000066": {
        "exercise_family": "MOBILITY",
        "movement_pattern": "BALANCE",
        "equipment": "BODYWEIGHT",
        "training_type": "MOBILITY",
        "reviewed_cardio_equipment": "NOT_APPLICABLE",
        "reviewed_equipment": "equipment=BODYWEIGHT;requires_equipment=false;locations=HOME|GYM",
        "reason": "SINGLE_LEG_BALANCE_MOBILITY_TAXONOMY_CONFIRMED",
    },
    "REX-000067": {
        "exercise_family": "CARDIO",
        "movement_pattern": "CYCLING",
        "equipment": "STATIONARY_BIKE",
        "training_type": "CARDIO",
        "reviewed_cardio_equipment": "STATIONARY_BIKE",
        "reviewed_equipment": "equipment=STATIONARY_BIKE;requires_equipment=true;locations=GYM",
        "reason": "STATIONARY_BIKE_CARDIO_TAXONOMY_CONFIRMED",
    },
    "REX-000072": {
        "exercise_family": "CARDIO",
        "movement_pattern": "ELLIPTICAL",
        "equipment": "ELLIPTICAL_MACHINE",
        "training_type": "CARDIO",
        "reviewed_cardio_equipment": "ELLIPTICAL",
        "reviewed_equipment": "equipment=ELLIPTICAL_MACHINE;requires_equipment=true;locations=GYM",
        "reason": "ELLIPTICAL_CARDIO_TAXONOMY_CONFIRMED",
    },
}


def patch_taxonomy(path: Path) -> list[dict[str, str]]:
    rows = read_rows(path)
    by_id = {row["representative_id"]: row for row in rows}
    if set(PATCHES) - set(by_id):
        raise ValueError("one or more target IDs are missing from taxonomy")
    for representative_id, patch in PATCHES.items():
        row = by_id[representative_id]
        row.update(
            {
                key: value
                for key, value in patch.items()
                if key not in {"reason"}
            }
        )
        row.update(
            {
                "removable_review_required_codes": "",
                "additional_review_required_codes": "",
                "representative_review_status": "FAMILY_SELECTION_COMPLETE",
                "review_required": "false",
                "review_required_codes": "",
                "reviewed_family": patch["exercise_family"],
                "reviewed_movement_pattern": patch["movement_pattern"],
                "review_decision": "APPROVED",
                "review_reason_code": patch["reason"],
                "reviewer": "CODEX_TAXONOMY_REVIEW",
                "reviewed_at": "2026-08-24T00:00:00+09:00",
                "taxonomy_review_status": "TAXONOMY_APPROVED",
            }
        )
    fields = list(rows[0])
    write_csv(path, fields, rows)
    return rows


def patch_derived(output_dir: Path, taxonomy_rows: list[dict[str, str]]) -> None:
    ids = set(PATCHES)
    taxonomy_by_id = {row["representative_id"]: row for row in taxonomy_rows}

    def read_output(name: str) -> list[dict[str, str]]:
        with (output_dir / name).open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def update_content(row: dict[str, str]) -> dict[str, str]:
        source = taxonomy_by_id[row["representative_id"]]
        if row["representative_id"] not in ids:
            return row
        generated = content_for(source)
        row.update(
            {
                "exercise_name_ko": source["representative_name_ko"],
                **generated,
                "target_muscle": source["target_muscle"],
                "difficulty": source["difficulty"],
                "source_ids": source["source_ids"],
                "taxonomy_review_status": source["taxonomy_review_status"],
                "generation_basis_code": f"TAXONOMY:{source['movement_pattern']}|NAME:{source['exercise_family']}",
                "content_review_status": "GENERATED_CONTENT_REVIEW_REQUIRED",
            }
        )
        return row

    def update_safety(row: dict[str, str]) -> dict[str, str]:
        source = taxonomy_by_id[row["representative_id"]]
        if row["representative_id"] not in ids:
            return row
        generated = safety_for(source)
        row.update(
            {
                "exercise_name_ko": source["representative_name_ko"],
                **generated,
                "source_ids": source["source_ids"],
                "taxonomy_review_status": source["taxonomy_review_status"],
            }
        )
        return row

    content_rows = [update_content(row) for row in read_output("representative_exercise_content.csv")]
    safety_rows = [update_safety(row) for row in read_output("exercise_safety_rules.csv")]
    log_rows = read_output("content_safety_review_log.csv")
    for row in log_rows:
        if row["representative_id"] not in ids:
            continue
        source = taxonomy_by_id[row["representative_id"]]
        safety = next(item for item in safety_rows if item["representative_id"] == row["representative_id"])
        row.update(
            {
                "exercise_name_ko": source["representative_name_ko"],
                "taxonomy_review_status": source["taxonomy_review_status"],
                "review_required_codes": source["review_required_codes"],
                "content_description_required_present": "false",
                "content_description_resolution": "NOT_PRESENT",
                "safety_rule_required_present": "false",
                "safety_rule_resolution": "NOT_PRESENT",
                "content_review_status": "GENERATED_CONTENT_REVIEW_REQUIRED",
                "safety_review_status": safety["safety_review_status"],
                "unresolved_review_required_codes": source["review_required_codes"],
                "source_ids": source["source_ids"],
            }
        )

    write_csv(output_dir / "representative_exercise_content.csv", CONTENT_COLUMNS, content_rows)
    write_csv(output_dir / "exercise_safety_rules.csv", SAFETY_COLUMNS, safety_rows)
    write_csv(output_dir / "content_safety_review_log.csv", LOG_COLUMNS, log_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = patch_taxonomy(args.taxonomy)
    patch_derived(args.output_dir, rows)
    print("patched=" + ",".join(sorted(PATCHES)))


if __name__ == "__main__":
    main()
