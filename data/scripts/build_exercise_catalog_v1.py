"""Build Exercise Catalog v1 from the latest catalog enrichment v3 FITT artifact."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = DATA_ROOT / "normalized" / "catalog_enrichment_v3_fitt.csv"
DEFAULT_OUTPUT = DATA_ROOT / "generated" / "exercise-catalog-v1.0.0" / "exercise_catalog_v1.csv"
EXPECTED_RECORD_COUNT = 208

ENRICHMENT_COLUMNS = (
    "exercise_id",
    "exercise_name_ko",
    "name_en",
    "body_focus_code",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "proposed_body_focus_code",
    "proposed_difficulty_code",
    "difficulty_code",
    "timing_mode_code",
    "default_sets",
    "default_reps",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "intensity_level",
    "name_ko_status",
    "body_focus_status",
    "body_area_status",
    "difficulty_status",
    "fitt_status",
    "name_ko_basis",
    "body_focus_basis",
    "body_area_basis",
    "difficulty_basis",
    "fitt_basis",
    "catalog_exposure_code",
    "canonical_exercise_id",
    "variant_relation_code",
    "variant_basis",
    "reviewer",
    "reviewed_at",
)
CATALOG_COLUMNS = (
    "exercise_id",
    "exercise_name_ko",
    "name_en",
    "source_name_en",
    "training_type_code",
    "body_focus_code",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "target_body_area_codes",
    "difficulty_code",
    "timing_mode_code",
    "default_sets",
    "default_reps",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "intensity_level",
    "production_status",
)
VALID_BODY_FOCUS_CODES = {
    "CHEST",
    "BACK",
    "SHOULDERS",
    "BICEPS",
    "TRICEPS",
    "FOREARMS",
    "GLUTES",
    "QUADRICEPS",
    "HAMSTRINGS",
    "CALVES",
    "CORE",
    "FULL_BODY",
    "CARDIO",
    "MOBILITY",
}
VALID_TRAINING_TYPE_CODES = {"STRENGTH", "CARDIO", "MOBILITY"}
VALID_DIFFICULTY_CODES = {"BEGINNER", "INTERMEDIATE", "ADVANCED"}
VALID_TIMING_MODE_CODES = {"REPS", "DURATION"}
VALID_STATUSES = {"APPROVED", "REVIEW_REQUIRED"}
VALID_CATALOG_EXPOSURE_CODES = {"PRIMARY", "MEDIA_VARIANT", "DISTINCT_VARIANT"}
VALID_VARIANT_RELATION_CODES = {
    "NONE",
    "SAME_MOVEMENT_MEDIA_VARIANT",
    "RANGE_OF_MOTION_VARIANT",
}
SPECIAL_FOCUS_CODES = {"FULL_BODY", "CARDIO", "MOBILITY"}
FORBIDDEN_MACHINE_CODES = {"UNSPECIFIED", "UPPER_BODY", "LOWER_BODY", "REVIEW_REQUIRED", "UNKNOWN"}
FOCUS_PRIMARY_AREAS = {
    "CHEST": {"CHEST"},
    "BACK": {"UPPER_BACK", "LOWER_BACK"},
    "SHOULDERS": {"SHOULDER"},
    "BICEPS": {"ELBOW"},
    "TRICEPS": {"ELBOW"},
    "FOREARMS": {"WRIST_HAND"},
    "GLUTES": {"HIP"},
    "QUADRICEPS": {"KNEE"},
    "HAMSTRINGS": {"KNEE", "HIP"},
    "CALVES": {"ANKLE_FOOT"},
    "CORE": {"ABDOMEN", "LOWER_BACK"},
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"enrichment has no header: {path}")
        missing = sorted(set(ENRICHMENT_COLUMNS) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"enrichment columns are missing: {missing}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("enrichment is empty")
    return rows


def validate_code(value: str, allowed: set[str], field: str, *, required: bool = True) -> None:
    if not value:
        if required:
            raise ValueError(f"{field} is missing")
        return
    if value != value.strip() or any(token in value for token in (",", "|", " ")):
        raise ValueError(f"{field} must be one single machine code: {value!r}")
    if any("가" <= character <= "힣" for character in value):
        raise ValueError(f"{field} must not contain Korean text: {value!r}")
    if value in FORBIDDEN_MACHINE_CODES or value not in allowed:
        raise ValueError(f"{field} is not allowed: {value}")


def parse_area_codes(value: str, field: str, *, allow_empty: bool = False) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} must be a JSON array") from exc
    if (
        not isinstance(parsed, list)
        or (not allow_empty and not parsed)
        or any(not isinstance(item, str) or not item for item in parsed)
    ):
        raise ValueError(f"{field} must be a JSON string array")
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{field} contains duplicate body areas")
    return parsed


def validate_fitt_value(value: str, field: str, exercise_id: str) -> None:
    """Validate a non-negative FITT integer or inclusive integer range."""
    if not value:
        return
    matched = re.fullmatch(r"(\d+)(?:-(\d+))?", value)
    if not matched:
        raise ValueError(f"{field} must be a non-negative integer or range: {exercise_id}")
    lower = int(matched.group(1))
    upper = int(matched.group(2) or lower)
    if lower > upper:
        raise ValueError(f"{field} range is descending: {exercise_id}")


def require_approval_evidence(row: dict[str, str], group: str) -> None:
    if not row[f"{group}_basis"] or not row["reviewer"] or not row["reviewed_at"]:
        raise ValueError(
            f"APPROVED {group} lacks basis, reviewer, or reviewed_at: {row['exercise_id']}"
        )
    try:
        parsed = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"APPROVED {group} reviewed_at is invalid: {row['exercise_id']}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"APPROVED {group} reviewed_at lacks timezone: {row['exercise_id']}")


def validate_row(row: dict[str, str]) -> dict[str, object]:
    exercise_id = row["exercise_id"]
    if not exercise_id:
        raise ValueError("exercise_id is missing")
    if not row["exercise_name_ko"] or row["exercise_name_ko"] == "REVIEW_REQUIRED":
        raise ValueError(f"exercise_name_ko is missing: {exercise_id}")
    if not row["name_en"]:
        raise ValueError(f"name_en is missing: {exercise_id}")
    if row["catalog_exposure_code"] not in VALID_CATALOG_EXPOSURE_CODES:
        raise ValueError(
            f"catalog_exposure_code is not allowed: {exercise_id}:{row['catalog_exposure_code']}"
        )
    if not row["canonical_exercise_id"]:
        raise ValueError(f"canonical_exercise_id is missing: {exercise_id}")
    if row["variant_relation_code"] not in VALID_VARIANT_RELATION_CODES:
        raise ValueError(
            f"variant_relation_code is not allowed: {exercise_id}:{row['variant_relation_code']}"
        )
    if not row["variant_basis"]:
        raise ValueError(f"variant_basis is missing: {exercise_id}")
    for status_field in (
        "name_ko_status",
        "body_focus_status",
        "body_area_status",
        "difficulty_status",
        "fitt_status",
    ):
        if row[status_field] not in VALID_STATUSES:
            raise ValueError(f"{status_field} is not allowed: {exercise_id}:{row[status_field]}")
    for group, status_field in (
        ("name_ko", "name_ko_status"),
        ("body_focus", "body_focus_status"),
        ("body_area", "body_area_status"),
        ("difficulty", "difficulty_status"),
        ("fitt", "fitt_status"),
    ):
        if not row[f"{group}_basis"]:
            raise ValueError(f"{group}_basis is missing: {exercise_id}")
        if row[status_field] == "APPROVED":
            require_approval_evidence(row, group)
    validate_code(row["body_focus_code"], VALID_BODY_FOCUS_CODES, "body_focus_code")
    validate_code(
        row["proposed_body_focus_code"],
        VALID_BODY_FOCUS_CODES,
        "proposed_body_focus_code",
        required=False,
    )
    validate_code(
        row["proposed_difficulty_code"],
        VALID_DIFFICULTY_CODES,
        "proposed_difficulty_code",
        required=False,
    )
    validate_code(row["difficulty_code"], VALID_DIFFICULTY_CODES, "difficulty_code", required=False)
    if row["difficulty_status"] == "APPROVED" and not row["difficulty_code"]:
        raise ValueError(f"APPROVED difficulty_code is missing: {exercise_id}")
    if row["difficulty_status"] == "REVIEW_REQUIRED" and row["difficulty_code"]:
        raise ValueError(f"REVIEW_REQUIRED difficulty must remain blank: {exercise_id}")
    primary = parse_area_codes(row["primary_body_area_codes"], "primary_body_area_codes")
    secondary = parse_area_codes(
        row["secondary_body_area_codes"], "secondary_body_area_codes", allow_empty=True
    )
    if set(primary) & set(secondary):
        raise ValueError(f"primary and secondary body areas overlap: {exercise_id}")
    if row["body_focus_code"] not in SPECIAL_FOCUS_CODES and not (
        set(primary) & FOCUS_PRIMARY_AREAS[row["body_focus_code"]]
    ):
        raise ValueError(f"body_focus_code does not match primary body area: {exercise_id}")
    timing_mode = row["timing_mode_code"]
    validate_code(timing_mode, VALID_TIMING_MODE_CODES, "timing_mode_code", required=False)
    fitt_fields = (
        "default_sets",
        "default_reps",
        "default_work_seconds",
        "default_rest_seconds",
        "default_transition_seconds",
    )
    for field in fitt_fields:
        validate_fitt_value(row[field], field, exercise_id)
    if row["fitt_status"] == "APPROVED" and not timing_mode:
        raise ValueError(f"APPROVED FITT timing_mode_code is missing: {exercise_id}")
    if not timing_mode and any(row[field] for field in fitt_fields):
        raise ValueError(f"FITT values require timing_mode_code: {exercise_id}")
    training_type = (
        "CARDIO"
        if row["body_focus_code"] == "CARDIO"
        else "MOBILITY"
        if row["body_focus_code"] == "MOBILITY"
        else "STRENGTH"
    )
    target = list(dict.fromkeys(primary + secondary))
    production_status = (
        "READY_FOR_MEDIA"
        if all(
            row[field] == "APPROVED"
            for field in (
                "name_ko_status",
                "body_focus_status",
                "body_area_status",
                "difficulty_status",
                "fitt_status",
            )
        )
        else "REVIEW_REQUIRED"
    )
    return {
        "exercise_id": exercise_id,
        "exercise_name_ko": row["exercise_name_ko"],
        "name_en": row["name_en"],
        "source_name_en": row["name_en"],
        "training_type_code": training_type,
        "body_focus_code": row["body_focus_code"],
        "primary_body_area_codes": json.dumps(primary, ensure_ascii=False, separators=(",", ":")),
        "secondary_body_area_codes": json.dumps(
            secondary, ensure_ascii=False, separators=(",", ":")
        ),
        "target_body_area_codes": json.dumps(target, ensure_ascii=False, separators=(",", ":")),
        "difficulty_code": row["difficulty_code"],
        "timing_mode_code": timing_mode,
        "default_sets": row["default_sets"],
        "default_reps": row["default_reps"],
        "default_work_seconds": row["default_work_seconds"],
        "default_rest_seconds": row["default_rest_seconds"],
        "default_transition_seconds": row["default_transition_seconds"],
        "intensity_level": row["intensity_level"],
        "production_status": production_status,
    }


def build_catalog(input_path: Path) -> list[dict[str, object]]:
    rows = read_csv(input_path)
    ids = [row["exercise_id"] for row in rows]
    if len(ids) != EXPECTED_RECORD_COUNT:
        raise ValueError(f"enrichment record count must be {EXPECTED_RECORD_COUNT}: {len(ids)}")
    if len(ids) != len(set(ids)):
        raise ValueError("enrichment has duplicate exercise_id")
    rows_by_id = {row["exercise_id"]: row for row in rows}
    for row in rows:
        exposure = row["catalog_exposure_code"]
        canonical_id = row["canonical_exercise_id"]
        relation = row["variant_relation_code"]
        if canonical_id not in rows_by_id:
            raise ValueError(
                f"canonical_exercise_id does not exist: {row['exercise_id']}:{canonical_id}"
            )
        if exposure == "PRIMARY" and (canonical_id != row["exercise_id"] or relation != "NONE"):
            raise ValueError(
                f"PRIMARY exposure must be its own canonical record: {row['exercise_id']}"
            )
        if exposure == "MEDIA_VARIANT" and (
            canonical_id == row["exercise_id"] or relation != "SAME_MOVEMENT_MEDIA_VARIANT"
        ):
            raise ValueError(f"MEDIA_VARIANT relation is invalid: {row['exercise_id']}")
        if exposure == "DISTINCT_VARIANT" and (
            canonical_id == row["exercise_id"] or relation != "RANGE_OF_MOTION_VARIANT"
        ):
            raise ValueError(f"DISTINCT_VARIANT relation is invalid: {row['exercise_id']}")
    return [validate_row(row) for row in sorted(rows, key=lambda item: item["exercise_id"])]


def write_catalog(output_path: Path, rows: list[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> Counter[str]:
    rows = build_catalog(input_path)
    write_catalog(output_path, rows)
    return Counter(str(row["production_status"]) for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        statuses = build(args.input, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output": str(args.output),
                "records": EXPECTED_RECORD_COUNT,
                "production_status": statuses,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
