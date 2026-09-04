#!/usr/bin/env python3
"""Normalize requested v2.0.6 catalog names, equipment, and locations.

The normalized CSV is the editable source for the draft bundle.  Every
exercise is available in a gym.  Home is additionally available only when a
non-empty equipment set contains exclusively user-approved home equipment.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REPORT = (
    PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/catalog_field_normalization_report.json"
)

REQUIRED_FIELDS = {
    "source_identity",
    "stable_code",
    "name_en",
    "equipment_codes",
    "location_codes",
}
HOME_ELIGIBLE_EQUIPMENT_CODES = frozenset(
    {
        "FOAM_ROLLER",
        "MAT",
        "CHAIR",
        "BENCH",
        "DUMBBELL",
        "RESISTANCE_BAND",
        "BODYWEIGHT",
        "HOUSEHOLD_WEIGHT",
    }
)
ROW_187_SOURCE_IDENTITY = "1259"
VERSION_SUFFIX_RE = re.compile(r"(?:\s*[-–—,]?\s*)v\.?\s*\d+\s*$", re.IGNORECASE)
ENGLISH_NAME_OVERRIDES = {
    "2203": "foam roller hamstring stretch",
    "2204": "foam roller thigh stretch",
    "2205": "foam roller outer thigh stretch",
    "2206": "foam roller calf stretch",
    "2207": "foam roller outer thigh stretch",
    "2209": "foam roller calf stretch",
    "0514": "bodyweight squat",
}
KOREAN_NAME_OVERRIDES = {"0514": "맨몸 스쿼트"}
# Foam-roller stable codes follow the normalized name_en.  Duplicate display
# names retain source_identity as a deterministic uniqueness suffix.
STABLE_CODE_OVERRIDES = {
    "0514": "bodyweight_squat",
    "2202": "roller_hip_stretch",
    "2203": "foam_roller_hamstring_stretch",
    "2204": "foam_roller_thigh_stretch",
    "2205": "foam_roller_outer_thigh_stretch_2205",
    "2206": "foam_roller_calf_stretch_2206",
    "2207": "foam_roller_outer_thigh_stretch_2207",
    "2208": "roller_back_stretch",
    "2209": "foam_roller_calf_stretch_2209",
}

# These exercises require gym fixtures, a bench, parallel bars, a pull-up
# cage, or a loaded object that is not treated as ordinary home equipment.
GYM_ONLY_STABLE_CODES = frozenset(
    {
        "bodyweight_back_extension_hip_dominant_bodyweight",
        "45_degree_side_bend",
        "single_leg_platform_slide",
        "weighted_svend_press",
        "dumbbell_incline_bench_press",
        "resistance_band_leg_extension",
        "dumbbell_incline_curl",
        "dumbbell_incline_hammer_press",
        "dumbbell_incline_rear_lateral_raise",
        "dumbbell_incline_row",
        "dumbbell_decline_hammer_press",
        "dumbbell_preacher_curl_isolation_dumbbell",
        "inverted_row_horizontal_pull_bodyweight",
        "lying_leg_raise_flat_bench",
        "reverse_hyper_on_flat_bench",
        "side_hip_on_parallel_bars",
        "chest_dip_on_dip_pull_up_cage",
        "incline_scapula_push_up",
        "bodyweight_incline_side_plank",
        "rear_decline_bridge",
    }
)


class CatalogFieldNormalizationError(ValueError):
    """Raised when the editable catalog cannot be normalized safely."""


def read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
            ]
    except OSError as exc:
        raise CatalogFieldNormalizationError(f"cannot read catalog: {path}") from exc
    if not REQUIRED_FIELDS.issubset(fields):
        missing = sorted(REQUIRED_FIELDS - set(fields))
        raise CatalogFieldNormalizationError(f"catalog is missing columns: {', '.join(missing)}")
    identities = [row["source_identity"] for row in rows]
    if not rows or not all(identities) or len(identities) != len(set(identities)):
        raise CatalogFieldNormalizationError("source_identity values must be unique and non-empty")
    return rows, fields


def equipment_codes(value: str) -> list[str]:
    return list(dict.fromkeys(code.strip() for code in value.split("|") if code.strip()))


def normalize_name_en(value: str) -> str:
    return VERSION_SUFFIX_RE.sub("", value).strip()


def location_codes(codes: list[str]) -> str:
    if codes and set(codes).issubset(HOME_ELIGIBLE_EQUIPMENT_CODES):
        return "GYM|HOME"
    return "GYM"


def apply_normalization(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    name_en_updates: list[dict[str, str]] = []
    name_ko_updates: list[dict[str, str]] = []
    stable_code_updates: list[dict[str, str]] = []
    equipment_updates: list[dict[str, str]] = []
    location_updates: list[dict[str, str]] = []
    row_187_seen = False

    for row in rows:
        identity = row["source_identity"]
        original_stable_code = row["stable_code"]
        normalized_stable_code = STABLE_CODE_OVERRIDES.get(identity, original_stable_code)
        if original_stable_code != normalized_stable_code:
            row["stable_code"] = normalized_stable_code
            stable_code_updates.append(
                {
                    "source_identity": identity,
                    "before": original_stable_code,
                    "after": normalized_stable_code,
                }
            )
        original_name = row["name_en"]
        normalized_name = ENGLISH_NAME_OVERRIDES.get(identity, normalize_name_en(original_name))
        if original_name != normalized_name:
            row["name_en"] = normalized_name
            name_en_updates.append(
                {"source_identity": identity, "before": original_name, "after": normalized_name}
            )

        original_name_ko = row.get("name_ko", "")
        normalized_name_ko = KOREAN_NAME_OVERRIDES.get(identity, original_name_ko)
        if original_name_ko != normalized_name_ko:
            row["name_ko"] = normalized_name_ko
            name_ko_updates.append(
                {
                    "source_identity": identity,
                    "before": original_name_ko,
                    "after": normalized_name_ko,
                }
            )

        if identity == ROW_187_SOURCE_IDENTITY:
            row_187_seen = True
            if row["equipment_codes"] != "BODYWEIGHT":
                equipment_updates.append(
                    {
                        "source_identity": identity,
                        "before": row["equipment_codes"],
                        "after": "BODYWEIGHT",
                    }
                )
                row["equipment_codes"] = "BODYWEIGHT"

        normalized_location = (
            "GYM"
            if row["stable_code"] in GYM_ONLY_STABLE_CODES
            else location_codes(equipment_codes(row["equipment_codes"]))
        )
        if row["location_codes"] != normalized_location:
            location_updates.append(
                {
                    "source_identity": identity,
                    "before": row["location_codes"],
                    "after": normalized_location,
                }
            )
            row["location_codes"] = normalized_location

    if not row_187_seen:
        raise CatalogFieldNormalizationError("catalog does not contain requested row 187")
    return rows, {
        "status": "DRAFT",
        "production_eligible": False,
        "input_record_count": len(rows),
        "row_187_source_identity": ROW_187_SOURCE_IDENTITY,
        "name_en_version_suffix_updates": name_en_updates,
        "name_ko_updates": name_ko_updates,
        "stable_code_updates": stable_code_updates,
        "equipment_updates": equipment_updates,
        "location_updates": location_updates,
        "gym_only_count": sum(row["location_codes"] == "GYM" for row in rows),
        "gym_home_count": sum(row["location_codes"] == "GYM|HOME" for row in rows),
        "home_eligible_equipment_codes": sorted(HOME_ELIGIBLE_EQUIPMENT_CODES),
    }


def write_catalog(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, fields = read_catalog(args.catalog)
    rows, report = apply_normalization(rows)
    if not args.dry_run:
        write_catalog(args.catalog, rows, fields)
        write_report(args.report, report)
    print(
        json.dumps(
            {
                "name_en_updates": len(report["name_en_version_suffix_updates"]),
                "equipment_updates": len(report["equipment_updates"]),
                "location_updates": len(report["location_updates"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
