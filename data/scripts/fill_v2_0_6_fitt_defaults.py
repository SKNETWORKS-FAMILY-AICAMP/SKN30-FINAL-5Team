"""Fill v2.0.6 FITT timing defaults in the normalized catalog.

Timing is selected from the exercise description and movement character, not
from body-focus values. Difficulty controls the strength rest default. The
values are conservative catalog defaults, not an individual prescription.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data/normalized/v2_0_6_fitt_defaults_source_map.json"

TIMING_MODES = {"REPS", "DURATION"}
DIFFICULTIES = {"BEGINNER", "INTERMEDIATE"}
SECONDS_PER_REP = 4
TRANSITION_SECONDS = 15

# These strength rows are continuous or explicitly hold a position in their
# Korean execution descriptions. Other strength rows are repetition-based.
DURATION_STRENGTH_IDS = {
    "2133",  # farmer's walk: continuous walking
    "3147",  # pelvic tilt: explicitly maintains the position
    "3552",  # quick feet: continuous footwork
}


class FittDefaultsError(ValueError):
    """Raised when the catalog cannot receive a complete FITT mapping."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            field_order = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        raise FittDefaultsError(f"cannot read catalog: {path}") from exc
    required = {
        "source_identity",
        "difficulty_code",
        "training_type_code",
        "primary_movement_pattern_code",
        "instruction_summary_ko",
        "timing_mode_code",
        "default_seconds_per_rep",
        "default_work_seconds",
        "default_rest_seconds",
        "default_transition_seconds",
    }
    if not required.issubset(field_order):
        raise FittDefaultsError(f"catalog is missing fields: {sorted(required - set(field_order))}")
    identities = [row["source_identity"].strip() for row in rows]
    if any(not identity for identity in identities) or len(set(identities)) != len(identities):
        raise FittDefaultsError("source_identity must be non-empty and unique")
    if any(None in row for row in rows):
        raise FittDefaultsError("catalog contains a row wider than its header")
    return rows, field_order


def _timing_mode(row: dict[str, str]) -> tuple[str, str]:
    identity = row["source_identity"].strip()
    training_type = row["training_type_code"].strip()
    if training_type == "MOBILITY":
        return "DURATION", "MOBILITY stretching is time-based"
    if training_type == "CARDIO":
        return "DURATION", "CARDIO continuous activity is time-based"
    if identity in DURATION_STRENGTH_IDS:
        return "DURATION", "instruction describes continuous movement or position hold"
    return "REPS", "instruction describes repeatable movement cycles"


def _rest_seconds(row: dict[str, str]) -> int:
    training_type = row["training_type_code"].strip()
    if training_type == "MOBILITY":
        return 30
    if training_type == "CARDIO":
        return 60
    difficulty = row["difficulty_code"].strip()
    if difficulty not in DIFFICULTIES:
        raise FittDefaultsError(
            f"difficulty_code must be BEGINNER or INTERMEDIATE: {row['source_identity']}"
        )
    return 60 if difficulty == "BEGINNER" else 90


def _work_seconds(row: dict[str, str], timing_mode: str) -> int | None:
    if timing_mode != "DURATION":
        return None
    training_type = row["training_type_code"].strip()
    if training_type == "MOBILITY":
        return 30
    if training_type == "CARDIO":
        return 60
    return 30


def apply(
    catalog_path: Path = DEFAULT_CATALOG,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    rows, field_order = _read_catalog(catalog_path)
    changes: list[dict[str, Any]] = []
    mode_counts = {mode: 0 for mode in sorted(TIMING_MODES)}
    changed_fields = {field: 0 for field in (
        "timing_mode_code",
        "default_seconds_per_rep",
        "default_work_seconds",
        "default_rest_seconds",
        "default_transition_seconds",
    )}

    for row in rows:
        timing_mode, timing_basis = _timing_mode(row)
        mode_counts[timing_mode] += 1
        rest_seconds = _rest_seconds(row)
        work_seconds = _work_seconds(row, timing_mode)
        values = {
            "timing_mode_code": timing_mode,
            "default_seconds_per_rep": str(SECONDS_PER_REP) if timing_mode == "REPS" else "",
            "default_work_seconds": str(work_seconds) if work_seconds is not None else "",
            "default_rest_seconds": str(rest_seconds),
            "default_transition_seconds": str(TRANSITION_SECONDS),
        }
        before = {field: row[field] for field in values}
        for field, value in values.items():
            if row[field] != value:
                changed_fields[field] += 1
                row[field] = value
        changes.append(
            {
                "source_identity": row["source_identity"],
                "name_en": row["name_en"],
                "difficulty_code": row["difficulty_code"],
                "training_type_code": row["training_type_code"],
                "primary_movement_pattern_code": row["primary_movement_pattern_code"],
                "timing_basis": timing_basis,
                "before": before,
                "after": values,
            }
        )

    with catalog_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_order, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "status": "DRAFT",
        "policy": {
            "timing_mode": "instruction_description_and_movement_character",
            "strength_rest_seconds_by_difficulty": {
                "BEGINNER": 60,
                "INTERMEDIATE": 90,
            },
            "mobility": {"timing_mode_code": "DURATION", "work_seconds": 30, "rest_seconds": 30},
            "cardio": {"timing_mode_code": "DURATION", "work_seconds": 60, "rest_seconds": 60},
            "strength_reps": {"seconds_per_rep": SECONDS_PER_REP},
            "strength_duration_work_seconds": 30,
            "transition_seconds": TRANSITION_SECONDS,
        },
        "catalog_source": {"path": str(catalog_path), "sha256": _sha256(catalog_path)},
        "counts": {
            "catalog_records": len(rows),
            "timing_mode_counts": mode_counts,
            "changed_field_counts": changed_fields,
        },
        "records": changes,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"catalog_records": len(rows), "timing_mode_counts": mode_counts, "report": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print(json.dumps(apply(args.catalog, args.report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
