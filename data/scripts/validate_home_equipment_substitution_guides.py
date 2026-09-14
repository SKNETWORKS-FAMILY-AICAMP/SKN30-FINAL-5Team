#!/usr/bin/env python3
"""Validate HOME equipment substitution review artifacts against the v2.0.6 catalog."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_GUIDES = ROOT / "data/normalized/home_equipment_substitution_guides_v1.jsonl"
DEFAULT_VARIANTS = ROOT / "data/normalized/resistance_band_bodyweight_variant_candidates_v1.jsonl"
DEFAULT_DUMBBELL_VARIANTS = ROOT / "data/normalized/dumbbell_bodyweight_variant_candidates_v1.jsonl"
DEFAULT_FOAM_VARIANTS = ROOT / "data/normalized/foam_roller_bodyweight_variant_candidates_v1.jsonl"
DEFAULT_GAPS = ROOT / "data/reports/resistance_band_bodyweight_variant_gap_report_v1.json"
DEFAULT_STRETCH = ROOT / "data/normalized/stretch_strap_home_suitability_review_v1.jsonl"
DEFAULT_REPORT = ROOT / "data/reports/home_equipment_substitution_guides_v1_validation.json"
APPROVED_REVIEW_STATUS = "DOMAIN_APPROVED"

ALLOWED_GUIDE_EQUIPMENT = {"DUMBBELL", "FOAM_ROLLER", "RESISTANCE_BAND"}
DIFFICULTY_RANK = {"BEGINNER": 1, "INTERMEDIATE": 2, "ADVANCED": 3}
GUIDE_FIELDS = {
    "exercise_stable_code",
    "equipment_code",
    "proposal_ko",
    "examples_ko",
    "cautions_ko",
    "review_status_code",
    "content_version",
}
VARIANT_FIELDS = {
    "source_exercise_stable_code",
    "missing_equipment_code",
    "candidate_exercise_stable_code",
    "reason_code",
    "selection_rationale_ko",
    "review_status_code",
}
STRETCH_FIELDS = {
    "exercise_stable_code",
    "exercise_name_ko",
    "current_location_codes",
    "home_suitability_decision",
    "substitute_tool_candidates_ko",
    "proposed_guide_ko",
    "cautions_ko",
    "review_rationale_ko",
    "review_status_code",
}


def codes(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value if str(item)}
    if value is None:
        return set()
    return {item for item in str(value).split("|") if item}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_array(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                if not raw_line.strip():
                    continue
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}: line {line_number}: invalid JSON: {exc.msg}")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"{path}: line {line_number}: row must be a JSON object")
                    continue
                rows.append(value)
    except OSError as exc:
        errors.append(f"{path}: cannot read JSONL: {exc}")
    return rows


def read_json(path: Path, errors: list[str]) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: cannot read JSON: {exc}")
        return None


def load_catalog(path: Path, errors: list[str]) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), 2):
                stable_code = row.get("stable_code", "")
                if not stable_code:
                    errors.append(f"{path}: row {row_number}: missing stable_code")
                elif stable_code in catalog:
                    errors.append(f"{path}: duplicate stable_code: {stable_code}")
                else:
                    catalog[stable_code] = row
    except OSError as exc:
        errors.append(f"{path}: cannot read catalog: {exc}")
    return catalog


def check_required_fields(
    row: dict[str, Any], expected: set[str], label: str, errors: list[str]
) -> None:
    missing = expected - row.keys()
    if missing:
        errors.append(f"{label}: missing fields: {', '.join(sorted(missing))}")


def validate_guides(
    catalog: dict[str, dict[str, str]], rows: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any]:
    keys: list[tuple[str, str]] = []
    expected: set[tuple[str, str]] = set()
    for stable_code, row in catalog.items():
        location_codes = codes(row.get("location_codes"))
        equipment_codes = codes(row.get("equipment_codes"))
        if "HOME" in location_codes:
            for equipment_code in equipment_codes & ALLOWED_GUIDE_EQUIPMENT:
                expected.add((stable_code, equipment_code))

    for index, row in enumerate(rows, 1):
        label = f"guide row {index}"
        check_required_fields(row, GUIDE_FIELDS, label, errors)
        stable_code = row.get("exercise_stable_code")
        equipment_code = row.get("equipment_code")
        key = (stable_code, equipment_code)
        keys.append(key)
        if key in keys[:-1]:
            errors.append(f"{label}: duplicate exercise/equipment combination: {key}")
        if stable_code not in catalog:
            errors.append(f"{label}: unknown stable_code: {stable_code}")
            continue
        catalog_row = catalog[stable_code]
        if "HOME" not in codes(catalog_row.get("location_codes")):
            errors.append(f"{label}: guide exercise is not HOME: {stable_code}")
        if equipment_code not in ALLOWED_GUIDE_EQUIPMENT:
            errors.append(f"{label}: disallowed equipment_code: {equipment_code}")
        if equipment_code not in codes(catalog_row.get("equipment_codes")):
            errors.append(
                f"{label}: equipment is not required by exercise: {stable_code}/{equipment_code}"
            )
        if row.get("review_status_code") != APPROVED_REVIEW_STATUS:
            errors.append(f"{label}: review_status_code must be {APPROVED_REVIEW_STATUS}")
        if equipment_code != "RESISTANCE_BAND" and not nonempty_string(row.get("proposal_ko")):
            errors.append(f"{label}: proposal_ko must be non-empty")
        if not string_array(row.get("examples_ko")):
            errors.append(f"{label}: examples_ko must be a string array")
        if not string_array(row.get("cautions_ko")):
            errors.append(f"{label}: cautions_ko must be a string array")
        text_values = (
            [row.get("proposal_ko", "")] + row.get("examples_ko", []) + row.get("cautions_ko", [])
        )
        if any(
            mark in value
            for value in text_values
            for mark in (".", "。", "!", "！", "?", "？", "·")
        ):
            errors.append(f"{label}: user-facing sentences must not contain sentence punctuation")
        if equipment_code == "RESISTANCE_BAND":
            if row.get("examples_ko") != []:
                errors.append(f"{label}: resistance-band examples_ko must be empty")
            band_proposal = row.get("proposal_ko", "")
            if band_proposal and not (
                "밴드를 대신할 생활도구 사용은 권장하지 않습니다" in band_proposal
                or "밴드 대신 권장하는 생활도구가 없습니다" in band_proposal
                or "대체 가능한 생활도구가 없습니다" in band_proposal
            ):
                errors.append(
                    f"{label}: resistance-band proposal must reject household substitutions"
                )
            forbidden = re.compile(r"수건|고무줄|스타킹|문손잡이|가구")
            if not forbidden.search(
                " ".join(row.get("examples_ko", []) + row.get("cautions_ko", []))
            ):
                errors.append(f"{label}: resistance-band safety cautions are incomplete")
        if equipment_code == "FOAM_ROLLER" and (
            row.get("examples_ko") != [] or row.get("cautions_ko") != []
        ):
            errors.append(
                f"{label}: foam-roller rows without a substitute must have empty "
                "examples and cautions"
            )
        if equipment_code == "STRETCH_STRAP" or equipment_code == "JUMP_ROPE":
            errors.append(f"{label}: stretch strap/jump rope must not be in guide data")

    actual = set(keys)
    missing = expected - actual
    unexpected = actual - expected
    for key in sorted(missing):
        errors.append(f"missing guide for HOME exercise/equipment: {key}")
    for key in sorted(unexpected):
        errors.append(f"guide is not an expected HOME exercise/equipment combination: {key}")
    return {
        "count": len(rows),
        "expected_count": len(expected),
        "unique_combination_count": len(actual),
        "all_expected_combinations_present": not missing and not unexpected,
    }


def body_areas(row: dict[str, str]) -> set[str]:
    return codes(row.get("primary_body_area_codes")) | codes(row.get("secondary_body_area_codes"))


SIMILAR_BODY_AREA_CODES = {
    "ankles": {"ankle stabilizers"},
    "ankle stabilizers": {"ankles", "feet"},
    "hip flexors": {"glutes", "quadriceps"},
}


def body_area_overlap(source: dict[str, str], candidate: dict[str, str]) -> bool:
    source_areas = body_areas(source)
    candidate_areas = body_areas(candidate)
    if source_areas & candidate_areas:
        return True
    return any(
        candidate_area in SIMILAR_BODY_AREA_CODES.get(source_area, set())
        for source_area in source_areas
        for candidate_area in candidate_areas
    )


def validate_variants(
    catalog: dict[str, dict[str, str]],
    rows: list[dict[str, Any]],
    gap_data: Any,
    errors: list[str],
    source_equipment_code: str = "RESISTANCE_BAND",
) -> dict[str, Any]:
    source_rows = {
        code: row
        for code, row in catalog.items()
        if "HOME" in codes(row.get("location_codes"))
        and source_equipment_code in codes(row.get("equipment_codes"))
    }
    candidate_sources: set[str] = set()
    for index, row in enumerate(rows, 1):
        label = f"variant row {index}"
        check_required_fields(row, VARIANT_FIELDS, label, errors)
        source_code = row.get("source_exercise_stable_code")
        candidate_code = row.get("candidate_exercise_stable_code")
        if source_code in candidate_sources:
            errors.append(f"{label}: duplicate candidate source: {source_code}")
        candidate_sources.add(source_code)
        if source_code not in source_rows:
            errors.append(
                f"{label}: source is not a HOME {source_equipment_code} exercise: {source_code}"
            )
            continue
        if row.get("missing_equipment_code") != source_equipment_code:
            errors.append(f"{label}: missing_equipment_code must be {source_equipment_code}")
        if candidate_code not in catalog:
            errors.append(f"{label}: unknown candidate stable_code: {candidate_code}")
            continue
        candidate = catalog[candidate_code]
        if codes(candidate.get("equipment_codes")) != {"BODYWEIGHT"}:
            errors.append(f"{label}: candidate must be BODYWEIGHT-only: {candidate_code}")
        if "HOME" not in codes(candidate.get("location_codes")):
            errors.append(f"{label}: candidate is not HOME: {candidate_code}")
        source = source_rows[source_code]
        if candidate.get("training_type_code") != source.get("training_type_code"):
            errors.append(f"{label}: training_type_code does not match source")
        if not body_area_overlap(source, candidate):
            errors.append(f"{label}: candidate body areas do not overlap source")
        source_rank = DIFFICULTY_RANK.get(source.get("difficulty_code"), 99)
        candidate_rank = DIFFICULTY_RANK.get(candidate.get("difficulty_code"), 99)
        if candidate_rank > source_rank:
            errors.append(f"{label}: candidate is more difficult than source")
        if row.get("reason_code") != "EQUIPMENT":
            errors.append(f"{label}: reason_code must be EQUIPMENT")
        if row.get("review_status_code") != APPROVED_REVIEW_STATUS:
            errors.append(f"{label}: review_status_code must be {APPROVED_REVIEW_STATUS}")
        if not nonempty_string(row.get("selection_rationale_ko")):
            errors.append(f"{label}: selection_rationale_ko must be non-empty")

    if gap_data is None:
        return {
            "source_equipment_code": source_equipment_code,
            "source_home_count": len(source_rows),
            "candidate_count": len(rows),
        }
    if not isinstance(gap_data, list):
        errors.append("gap report must be a JSON array")
        gap_data = []
    gap_sources: set[str] = set()
    for index, row in enumerate(gap_data, 1):
        label = f"gap row {index}"
        if not isinstance(row, dict):
            errors.append(f"{label}: row must be a JSON object")
            continue
        required = {
            "source_exercise_stable_code",
            "source_exercise_name_ko",
            "resolution_code",
            "message_ko",
        }
        check_required_fields(row, required, label, errors)
        source_code = row.get("source_exercise_stable_code")
        if source_code in gap_sources:
            errors.append(f"{label}: duplicate gap source: {source_code}")
        gap_sources.add(source_code)
        if source_code not in source_rows:
            errors.append(
                f"{label}: source is not a HOME {source_equipment_code} exercise: {source_code}"
            )
        elif row.get("source_exercise_name_ko") != source_rows[source_code].get("name_ko"):
            errors.append(f"{label}: source exercise name does not match catalog: {source_code}")
        if row.get("resolution_code") != "BAND_REQUIRED":
            errors.append(f"{label}: resolution_code must be BAND_REQUIRED")
        if not nonempty_string(row.get("message_ko")):
            errors.append(f"{label}: message_ko must be non-empty")

    overlap = candidate_sources & gap_sources
    if overlap:
        errors.append(f"candidate and gap report overlap: {sorted(overlap)}")
    covered = candidate_sources | gap_sources
    missing = set(source_rows) - covered
    unexpected = covered - set(source_rows)
    for source_code in sorted(missing):
        errors.append(f"band HOME exercise has neither candidate nor gap record: {source_code}")
    for source_code in sorted(unexpected):
        errors.append(f"candidate/gap source is not a band HOME exercise: {source_code}")
    return {
        "source_equipment_code": source_equipment_code,
        "source_home_count": len(source_rows),
        "candidate_count": len(rows),
        "gap_count": len(gap_data),
        "all_source_home_exercises_resolved": not overlap and not missing and not unexpected,
    }


def validate_stretch(
    catalog: dict[str, dict[str, str]], rows: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any]:
    source_rows = {
        code: row
        for code, row in catalog.items()
        if "STRETCH_STRAP" in codes(row.get("equipment_codes"))
    }
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        label = f"stretch row {index}"
        check_required_fields(row, STRETCH_FIELDS, label, errors)
        code = row.get("exercise_stable_code")
        if code in seen:
            errors.append(f"{label}: duplicate stable_code: {code}")
        seen.add(code)
        if code not in source_rows:
            errors.append(f"{label}: exercise is not a STRETCH_STRAP catalog row: {code}")
            continue
        source = source_rows[code]
        if row.get("exercise_name_ko") != source.get("name_ko"):
            errors.append(f"{label}: exercise name does not match catalog")
        if row.get("current_location_codes") != sorted(codes(source.get("location_codes"))):
            errors.append(f"{label}: current_location_codes changed from catalog")
        if row.get("home_suitability_decision") != "REVIEW_REQUIRED":
            errors.append(f"{label}: home_suitability_decision must be REVIEW_REQUIRED")
        if row.get("review_status_code") != APPROVED_REVIEW_STATUS:
            errors.append(f"{label}: review_status_code must be {APPROVED_REVIEW_STATUS}")
        for field in ("substitute_tool_candidates_ko", "cautions_ko"):
            if not string_array(row.get(field)):
                errors.append(f"{label}: {field} must be a string array")
        if not nonempty_string(row.get("proposed_guide_ko")) or not nonempty_string(
            row.get("review_rationale_ko")
        ):
            errors.append(f"{label}: proposed guide and rationale must be non-empty")
        combined = " ".join(row.get("substitute_tool_candidates_ko", []))
        if re.search(r"탄성 밴드|고무줄|저항 밴드", combined):
            errors.append(f"{label}: elastic-band or rubber-band substitute is forbidden")
        if "JUMP_ROPE" in codes(source.get("equipment_codes")) or "줄넘기" in source.get(
            "name_ko", ""
        ):
            errors.append(f"{label}: stretch strap and jump rope are confused")

    missing = set(source_rows) - seen
    for code in sorted(missing):
        errors.append(f"missing stretch strap review row: {code}")
    return {
        "catalog_stretch_strap_count": len(source_rows),
        "review_count": len(rows),
        "all_catalog_stretch_strap_rows_reviewed": not missing,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--guides", type=Path, default=DEFAULT_GUIDES)
    parser.add_argument("--variants", type=Path, default=DEFAULT_VARIANTS)
    parser.add_argument("--dumbbell-variants", type=Path, default=DEFAULT_DUMBBELL_VARIANTS)
    parser.add_argument("--foam-variants", type=Path, default=DEFAULT_FOAM_VARIANTS)
    parser.add_argument("--gaps", type=Path, default=DEFAULT_GAPS)
    parser.add_argument("--stretch", type=Path, default=DEFAULT_STRETCH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    catalog = load_catalog(args.catalog, errors)
    guides = read_jsonl(args.guides, errors)
    variants = read_jsonl(args.variants, errors)
    dumbbell_variants = read_jsonl(args.dumbbell_variants, errors)
    foam_variants = read_jsonl(args.foam_variants, errors)
    stretch = read_jsonl(args.stretch, errors)
    gaps = read_json(args.gaps, errors)

    guide_summary = validate_guides(catalog, guides, errors)
    variant_summary = validate_variants(catalog, variants, gaps, errors)
    dumbbell_variant_summary = validate_variants(
        catalog,
        dumbbell_variants,
        None,
        errors,
        source_equipment_code="DUMBBELL",
    )
    foam_variant_summary = validate_variants(
        catalog,
        foam_variants,
        None,
        errors,
        source_equipment_code="FOAM_ROLLER",
    )
    stretch_summary = validate_stretch(catalog, stretch, errors)
    checks = {
        "jsonl_and_json_parse": not any(
            "invalid JSON" in error or "cannot read JSON" in error for error in errors
        ),
        "guide_checks": not any(
            error.startswith("guide ") or "guide for HOME" in error for error in errors
        ),
        "variant_checks": not any(
            error.startswith("variant ") or error.startswith("gap ") for error in errors
        ),
        "stretch_checks": not any(
            error.startswith("stretch ") or "stretch strap review" in error for error in errors
        ),
    }
    report = {
        "validation_status": "PASS" if not errors else "FAIL",
        "review_status_code": APPROVED_REVIEW_STATUS,
        "review_method_code": "USER_CONFIRMED",
        "reviewed_at": "2026-09-04T00:00:00+09:00",
        "production_eligible": False,
        "catalog_path": str(
            args.catalog.relative_to(ROOT)
            if args.catalog.is_absolute() and args.catalog.is_relative_to(ROOT)
            else args.catalog
        ),
        "guide_summary": guide_summary,
        "variant_and_gap_summary": variant_summary,
        "dumbbell_variant_summary": dumbbell_variant_summary,
        "foam_variant_summary": foam_variant_summary,
        "stretch_summary": stretch_summary,
        "checks": checks,
        "error_count": len(errors),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
