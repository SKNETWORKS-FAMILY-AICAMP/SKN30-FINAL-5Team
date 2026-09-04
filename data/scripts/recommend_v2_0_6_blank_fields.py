#!/usr/bin/env python3
"""Report source-bound recommendations for blank v2.0.6 catalog fields."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/blank_field_recommendations.json"
RECOMMENDATIONS = {
    "body_focus_code": (
        "TAXONOMY_REVIEW_REQUIRED",
        "Use only the approved body-focus code set; ADDUCTORS is now represented in "
        "the data taxonomy and still requires human review before production promotion.",
        "data/normalized/body_focus_codes_v2.md",
    ),
    "training_type_code": (
        "NEXT_SAFE_GENERATOR_STEP",
        "Derive from completed body_focus_code: CARDIO->CARDIO, "
        "MOBILITY->MOBILITY, other allowed body focus->STRENGTH; "
        "preserve blank when body focus is blank.",
        "data/validation/review_batches/v2_0_6_training_body_focus_review.csv#body_focus_code",
    ),
    "name_ko": (
        "HUMAN_REVIEW_REQUIRED",
        "Use reviewed/localized display-name input or an exact source-name mapping; "
        "do not machine-translate into a production display name without review.",
        "review batch name_ko or exact Gymvisual raw id/name mapping",
    ),
    "primary_body_area_codes": (
        "SOURCE_MAPPING_REVIEW_REQUIRED",
        "Map raw body_part/muscle evidence to controlled codes with explicit primary "
        "selection; do not copy body_focus_code.",
        "data/raw/gym_visual/exercises.json exact source_identity",
    ),
    "secondary_body_area_codes": (
        "SOURCE_MAPPING_REVIEW_REQUIRED",
        "Map only explicitly supported secondary muscles to controlled codes; "
        "do not infer from primary or body focus.",
        "data/raw/gym_visual/exercises.json exact source_identity",
    ),
    "safety_relevant_body_area_codes": (
        "KEEP_BLANK",
        "Excluded from this task; fill only after a direct source value and separate "
        "safety review.",
        "no direct source mapping accepted in this task",
    ),
    "family_code": (
        "KEEP_BLANK_UNTIL_FAMILY_REVIEW",
        "Representative/family confirmation is excluded; do not derive from exercise "
        "name or movement category alone.",
        "separate family review artifact required",
    ),
    "timing_mode_code": (
        "HUMAN_REVIEW_REQUIRED",
        "Confirm REPS vs DURATION from reviewed execution/dosage evidence; "
        "do not infer from MET or name.",
        "explicit dosage review evidence",
    ),
    "default_work_seconds": (
        "HUMAN_REVIEW_REQUIRED",
        "Fill only from reviewed exercise dosage policy or explicit source value; "
        "no default substitution.",
        "explicit dosage review evidence",
    ),
    "default_seconds_per_rep": (
        "HUMAN_REVIEW_REQUIRED",
        "Fill only from reviewed dosage policy; do not calculate from timing or difficulty.",
        "explicit dosage review evidence",
    ),
    "default_rest_seconds": (
        "HUMAN_REVIEW_REQUIRED",
        "Fill only from reviewed dosage policy; do not copy by category.",
        "explicit dosage review evidence",
    ),
    "default_transition_seconds": (
        "HUMAN_REVIEW_REQUIRED",
        "Fill only from reviewed transition policy; no blanket default.",
        "explicit dosage review evidence",
    ),
    "difficulty_code": (
        "HUMAN_REVIEW_REQUIRED",
        "Require explicit difficulty review; never use rank or infer from equipment/body focus.",
        "difficulty review evidence; rank prohibited",
    ),
    "equipment_codes": (
        "EXACT_SOURCE_MAPPING",
        "For the single blank row, map the exact raw equipment label through the "
        "controlled vocabulary mapper and retain unresolved values blank.",
        "data/raw/gym_visual/exercises.json exact source_identity",
    ),
    "location_codes": (
        "HUMAN_REVIEW_REQUIRED",
        "Fill only when source or explicit location review supports HOME/GYM/OUTDOOR; "
        "do not infer from equipment.",
        "explicit location evidence",
    ),
    "form_cues_source": (
        "EXACT_SOURCE_PROVENANCE",
        "Record the exact raw source identity/path for existing form cues; do not "
        "rewrite cue content in this step.",
        "data/raw/gym_visual/exercises.json exact source_identity",
    ),
    "form_cues_review_status": (
        "REVIEW_REQUIRED",
        "Mark existing imported cues as REVIEW_REQUIRED until content review evidence exists.",
        "content review evidence",
    ),
    "instruction_summary_ko": (
        "HUMAN_CONTENT_REVIEW_REQUIRED",
        "Create a reviewed user-facing summary from exact source steps; do not treat "
        "raw Korean text as approved copy.",
        "data/raw/gym_visual/exercises.json instruction_steps.ko",
    ),
    "instruction_content_version": (
        "GENERATOR_METADATA",
        "Set only when the content generator/version is explicitly applied and audited.",
        "content naturalization audit",
    ),
    "record_type": (
        "KEEP_BLANK_UNTIL_REPRESENTATIVE_REVIEW",
        "Do not decide representative/variant record type in this task.",
        "separate representative review",
    ),
    "recovery_eligible": (
        "HUMAN_REVIEW_REQUIRED",
        "Require explicit recovery eligibility review; do not infer from mobility/body focus.",
        "recovery review evidence",
    ),
    "review_status_code": (
        "REVIEW_GATE",
        "Set REVIEW_REQUIRED when the row has been assembled but remains unreviewed; "
        "never promote to DOMAIN_APPROVED automatically.",
        "review gate evidence",
    ),
    "met_value": (
        "KEEP_BLANK_UNLESS_DIRECT_COMPENDIUM_MATCH",
        "Use only direct activity evidence from the designated Compendium; no estimate, "
        "category transfer, or intensity inference.",
        "data/raw/physical_activity_guidelines/adult_compendium_mvp_reference_subset.jsonl",
    ),
    "met_source_code": (
        "KEEP_BLANK_WITH_MET",
        "Populate only together with a directly matched met_value and exact source_id.",
        "designated Compendium source_id",
    ),
    "met_source_activity_code": (
        "KEEP_BLANK_WITH_MET",
        "Populate only together with a directly matched met_value and exact activity_code.",
        "designated Compendium activity_code",
    ),
    "representative_stable_code": (
        "KEEP_BLANK",
        "Representative selection is excluded from this task.",
        "separate representative review",
    ),
}


def read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    return rows, fields


def recommend(
    catalog_path: Path = DEFAULT_CATALOG, output_path: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    rows, fields = read_catalog(catalog_path)
    output_rows = []
    for field in fields:
        empty_count = sum(not (row.get(field) or "").strip() for row in rows)
        if not empty_count:
            continue
        code, recommendation, evidence = RECOMMENDATIONS.get(
            field,
            (
                "SOURCE_REVIEW_REQUIRED",
                "Identify a direct source mapping and preserve blank values until "
                "reviewed; no inference or defaulting.",
                "field-specific source evidence",
            ),
        )
        output_rows.append(
            {
                "column_name": field,
                "empty_count": empty_count,
                "recommendation_code": code,
                "recommended_action": recommendation,
                "evidence_source": evidence,
            }
        )
    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "catalog": {"path": str(catalog_path), "records": len(rows)},
        "policy": {
            "no_inference": True,
            "no_rank_usage": True,
            "met_direct_source_only": True,
            "safety_columns_not_filled": True,
        },
        "blank_fields": output_rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with output_path.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "column_name",
                "empty_count",
                "recommendation_code",
                "recommended_action",
                "evidence_source",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = recommend(args.catalog, args.output)
    print(json.dumps({"blank_fields": len(report["blank_fields"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
