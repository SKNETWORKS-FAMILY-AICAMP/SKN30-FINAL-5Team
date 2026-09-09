#!/usr/bin/env python3
"""Apply the reviewed v2.0.8 catalog and initial-FITT corrections in place.

The two normalized CSV files are the editable release inputs.  This script is
deliberately idempotent: it preserves their schemas, rows, and immutable source
identity fields while making the review decisions explicit and checkable.
"""

from __future__ import annotations

import csv
from pathlib import Path

from assign_v2_0_6_family_representatives import apply_family_assignments, read_catalog

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
FITT = ROOT / "data/normalized/catalog_enrichment_v3_fitt.csv"
IMMUTABLE_CATALOG_FIELDS = ("stable_code", "source_identity", "source_track")

# Machine and steady-state gait entries are prescribed as one continuous block.
CONTINUOUS_CARDIO_SECONDS = {
    "cardio_gait_bodyweight": 600,
    "cardio_gait_machine": 600,
    "cardio_gait_machine_rex_000071": 600,
    "run_equipment": 600,
    "stationary_bike_walk": 600,
    "walk_elliptical_cross_trainer": 600,
    "short_stride_run": 600,
}

# These are interval-style bodyweight movements, so their work block remains
# short rather than being converted into a ten-minute continuous prescription.
INTERVAL_CARDIO_SECONDS = {
    "cardio_gait_bodyweight_rex_000058": 30,
    "mountain_climber": 30,
    "left_hook_boxing": 30,
    "astride_jumps_male": 30,
    "half_knee_bends_male": 30,
    "quick_feet": 30,
    "ski_step": 30,
}

# Corrections where the existing movement classification conflicts with the
# actual primary motion.  We intentionally do not combine cardio families here.
CLASSIFICATION_OVERRIDES = {
    "quick_feet": {
        "training_type_code": "CARDIO",
        "body_focus_code": "CARDIO",
        "primary_movement_pattern_code": "GAIT",
        "recovery_eligible": "False",
    },
    "pelvic_tilt": {"recovery_eligible": "True"},
    "barbell_rack_pull": {"primary_movement_pattern_code": "HIP_DOMINANT"},
}

# The reviewed catalog records these dynamic core movements by repetitions.
# Their old DURATION FITT rows were the five timing-reference mismatches found
# by the exact stable-code join; normalize the FITT side without changing IDs.
REPS_FITT_EXERCISE_IDS = {
    "NEX-000029",
    "NEX-000030",
    "NEX-000080",
    "NEX-000094",
    "NEX-000112",
}
INTERVAL_FITT_EXERCISE_IDS = {"NEX-000158", "NEX-000164", "NEX-000168"}


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def _write_csv(
    path: Path, rows: list[dict[str, str]], fields: list[str], *, bom: bool
) -> None:
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def apply_catalog_corrections(rows: list[dict[str, str]]) -> None:
    if len(rows) != 237:
        raise ValueError(f"v2.0.8 requires exactly 237 catalog rows, received {len(rows)}")
    before = {
        row["stable_code"]: tuple(row[field] for field in IMMUTABLE_CATALOG_FIELDS) for row in rows
    }
    apply_family_assignments(rows)
    for row in rows:
        code = row["stable_code"]
        if code in CONTINUOUS_CARDIO_SECONDS:
            row.update(
                {
                    "timing_mode_code": "DURATION",
                    "default_work_seconds": str(CONTINUOUS_CARDIO_SECONDS[code]),
                    "default_rest_seconds": "0",
                }
            )
        elif code in INTERVAL_CARDIO_SECONDS:
            row.update(
                {
                    "timing_mode_code": "DURATION",
                    "default_work_seconds": str(INTERVAL_CARDIO_SECONDS[code]),
                    "default_rest_seconds": "30",
                }
            )
        row.update(CLASSIFICATION_OVERRIDES.get(code, {}))
        if not row["recovery_eligible"]:
            # Every remaining blank is a strength movement.  Record the existing
            # conservative policy explicitly instead of delegating it to runtime.
            row["recovery_eligible"] = "False"
    after = {
        row["stable_code"]: tuple(row[field] for field in IMMUTABLE_CATALOG_FIELDS) for row in rows
    }
    if before != after:
        raise ValueError("stable_code, source_identity, and source_track must not change")


def apply_fitt_corrections(rows: list[dict[str, str]]) -> None:
    if len(rows) != 208:
        raise ValueError(f"v2.0.8 requires exactly 208 FITT rows, received {len(rows)}")
    for row in rows:
        if row["current_training_type"] == "CARDIO":
            if row["exercise_id"] in INTERVAL_FITT_EXERCISE_IDS:
                row.update(
                    {
                        "fitt_template_id": "FITT-CARDIO-INTERVAL-V1",
                        "default_work_seconds": "30-60",
                        "default_rest_seconds": "30-60",
                        "default_intensity": "LIGHT_MODERATE",
                        "intensity_level": "LIGHT_MODERATE",
                    }
                )
            else:
                row.update(
                    {
                        "fitt_template_id": "FITT-CARDIO-CONTINUOUS-V1",
                        "default_work_seconds": "600-2400",
                        "default_rest_seconds": "0",
                        "default_intensity": "MODERATE",
                        "intensity_level": "MODERATE",
                    }
                )
        if row["exercise_id"] in REPS_FITT_EXERCISE_IDS:
            row["timing_mode_code"] = "REPS"
            row["default_work_seconds"] = ""
        if row["timing_mode_code"] != "REPS" or row["current_training_type"] != "STRENGTH":
            continue
        compound = row["fitt_template_id"].startswith("FITT-COMPOUND-")
        isolation = row["fitt_template_id"] == "FITT-ISOLATION-STRENGTH-V1"
        if not (compound or isolation):
            continue
        row["default_sets"] = "2"
        row["default_reps"] = "10-15" if compound else "12-20"
        row["default_intensity"] = "LIGHT_MODERATE" if compound else "LIGHT"
        row["intensity_level"] = row["default_intensity"]


def main() -> None:
    catalog_rows, catalog_fields = read_catalog(CATALOG)
    fitt_rows, fitt_fields = _read_csv(FITT)
    apply_catalog_corrections(catalog_rows)
    apply_fitt_corrections(fitt_rows)
    _write_csv(CATALOG, catalog_rows, catalog_fields, bom=True)
    # The integrated-bundle importer reads this legacy FITT reference as UTF-8
    # (not UTF-8-SIG), so its header must remain byte-for-byte BOM-free.
    _write_csv(FITT, fitt_rows, fitt_fields, bom=False)


if __name__ == "__main__":
    main()
