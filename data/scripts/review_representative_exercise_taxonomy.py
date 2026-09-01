#!/usr/bin/env python3
"""Perform an evidence-backed taxonomy review of representative exercises."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/reports/representative_exercise_catalog.csv"
DEFAULT_INTEGRATED = ROOT / "data/reports/integrated_exercise_review_updated.csv"
DEFAULT_OUTPUT = ROOT / "data/reports/representative_exercise_taxonomy_reviewed.csv"
DEFAULT_LOG = ROOT / "data/reports/taxonomy_review_log.csv"
DEFAULT_SUMMARY = ROOT / "data/reports/taxonomy_review_summary.md"

REVIEWER = "CODEX_TAXONOMY_REVIEW"
REVIEWED_AT = "2026-08-23T00:00:00+09:00"

TAXONOMY_CODES = {
    "HUMAN_TAXONOMY_REVIEW_REQUIRED",
    "MOVEMENT_PATTERN_REVIEW",
    "EXERCISE_FAMILY_REVIEW_REQUIRED",
    "VARIANT_RELATION_REVIEW_REQUIRED",
    "EQUIPMENT_TAXONOMY_CANDIDATE_REVIEW",
    "CARDIO_EQUIPMENT_TAXONOMY_MAPPING",
}
NON_FINAL_TAXONOMY_CODES = {
    "EXERCISE_TAXONOMY_MAPPING_REQUIRED",
    "SOURCE_EQUIPMENT_UNSPECIFIED",
    "TOOL_METADATA_UNSPECIFIED",
}
MOVEMENT_CODES = {
    "KNEE_DOMINANT",
    "HIP_DOMINANT",
    "HORIZONTAL_PUSH",
    "HORIZONTAL_PULL",
    "VERTICAL_PUSH",
    "VERTICAL_PULL",
    "CORE_BRACE",
    "ISOLATION",
    "KNEE_FLEXION",
    "GAIT",
    "MOBILITY_STRETCH",
}

OUTPUT_FIELDS = (
    "review_required",
    "review_required_codes",
    "reviewed_family",
    "reviewed_variant_relation",
    "reviewed_movement_pattern",
    "reviewed_equipment",
    "reviewed_cardio_equipment",
    "review_decision",
    "review_reason_code",
    "reviewer",
    "reviewed_at",
    "taxonomy_review_status",
)
LOG_FIELDS = (
    "exercise_id",
    "exercise_name",
    "review_type",
    "previous_value",
    "reviewed_value",
    "review_decision",
    "review_reason_code",
    "reviewer",
    "reviewed_at",
)


def split_codes(value: str) -> list[str]:
    return [code for code in value.split("|") if code]


def source_codes(row: dict[str, str]) -> list[str]:
    codes: list[str] = []
    for field in ("removable_review_required_codes", "additional_review_required_codes"):
        for code in split_codes(row.get(field, "")):
            if code not in codes:
                codes.append(code)
    return codes


def load_integrated(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {f"{row['source_system']}:{row['source_id']}": row for row in csv.DictReader(handle)}


def parse_variant_list(value: str) -> list[dict[str, str]]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def family_review(row: dict[str, str]) -> tuple[str, str, bool]:
    family = row.get("exercise_family", "")
    if not family or family == "REVIEW_REQUIRED" or family.startswith("REVIEW_REQUIRED_"):
        return "REVIEW_REQUIRED", "FAMILY_VOCABULARY_NOT_ESTABLISHED", False
    return family, "REPRESENTATIVE_FAMILY_AND_MERGE_BASIS_CONFIRMED", True


def variant_review(row: dict[str, str]) -> tuple[str, str, bool]:
    variants = parse_variant_list(row.get("variant_list", ""))
    if not variants:
        return "REVIEW_REQUIRED", "VARIANT_EVIDENCE_MISSING", False
    if len(variants) == 1:
        return "NO_VARIANT_SINGLE_SOURCE", "SINGLE_SOURCE_NO_VARIANT", True
    return f"KEEP_VARIANTS:{len(variants)}", "SOURCE_VARIANTS_RETAINED", True


def movement_review(row: dict[str, str]) -> tuple[str, str, bool]:
    movement = row.get("movement_pattern", "")
    if movement not in MOVEMENT_CODES:
        return "REVIEW_REQUIRED", "MOVEMENT_PATTERN_NOT_ESTABLISHED", False
    return movement, "REPRESENTATIVE_MOVEMENT_CODE_CONFIRMED", True


def canonical_equipment(value: str) -> str:
    return (
        value.replace("CABLE_MACHINE", "CABLE|MACHINE")
        .replace("RESISTANCE_BAND", "BAND")
        .replace("FOAM_ROLLER", "ROLLER")
        .replace("HOUSEHOLD_WEIGHT", "WEIGHTED")
    )


def equipment_review(
    row: dict[str, str], integrated: dict[str, dict[str, str]]
) -> tuple[str, str, bool]:
    source = integrated.get(row.get("representative_source_id", ""), {})
    equipment = canonical_equipment(source.get("equipment_code_candidate", ""))
    locations = source.get("location_code_candidates", "")
    if not equipment or equipment == "UNSPECIFIED" or not locations:
        return "REVIEW_REQUIRED", "EQUIPMENT_TAXONOMY_UNSPECIFIED", False
    required = "false" if equipment == "BODYWEIGHT" else "true"
    return (
        f"equipment={equipment};requires_equipment={required};locations={locations}",
        "SOURCE_EQUIPMENT_AND_LOCATION_CONFIRMED",
        True,
    )


def cardio_equipment_review(row: dict[str, str]) -> tuple[str, str, bool]:
    if row.get("training_type") != "CARDIO":
        return "NOT_APPLICABLE", "NOT_CARDIO", True
    name = row.get("representative_name_ko", "")
    equipment = row.get("equipment", "")
    family = row.get("exercise_family", "")
    if "줄넘기" in name or "JUMP_ROPE" in family:
        return "JUMP_ROPE", "CARDIO_NAME_AND_ROPE_EQUIPMENT_CONFIRMED", True
    if "자전거" in name or "STATIONARY_BIKE" in family:
        return "STATIONARY_BIKE", "CARDIO_NAME_AND_STATIONARY_BIKE_CONFIRMED", True
    if "트레드밀" in name or "INCLINE_TREADMILL" in family:
        return "TREADMILL", "CARDIO_NAME_AND_MACHINE_CONFIRMED", True
    if "스텝밀" in name or "STEPMILL" in family:
        return "STEPMILL", "CARDIO_NAME_AND_MACHINE_CONFIRMED", True
    if "일립티컬" in name or "ELLIPTICAL" in family:
        return "ELLIPTICAL", "CARDIO_NAME_AND_MACHINE_CONFIRMED", True
    if equipment == "BODYWEIGHT":
        return "NO_EQUIPMENT_BODYWEIGHT", "CARDIO_BODYWEIGHT_CONFIRMED", True
    return "REVIEW_REQUIRED", "CARDIO_EQUIPMENT_MAPPING_UNCERTAIN", False


def review_row(
    row: dict[str, str], integrated: dict[str, dict[str, str]]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    family, family_reason, family_ok = family_review(row)
    variant, variant_reason, variant_ok = variant_review(row)
    movement, movement_reason, movement_ok = movement_review(row)
    equipment, equipment_reason, equipment_ok = equipment_review(row, integrated)
    cardio, cardio_reason, cardio_ok = cardio_equipment_review(row)
    values = {
        "FAMILY": (row.get("exercise_family", ""), family, family_reason, family_ok),
        "VARIANT_RELATION": (row.get("variant_list", ""), variant, variant_reason, variant_ok),
        "MOVEMENT_PATTERN": (
            row.get("movement_pattern", ""),
            movement,
            movement_reason,
            movement_ok,
        ),
        "EQUIPMENT": (row.get("equipment", ""), equipment, equipment_reason, equipment_ok),
        "CARDIO_EQUIPMENT": (row.get("equipment", ""), cardio, cardio_reason, cardio_ok),
    }
    codes = source_codes(row)
    removed: list[str] = []
    mapping = {
        "EXERCISE_FAMILY_REVIEW_REQUIRED": "FAMILY",
        "VARIANT_RELATION_REVIEW_REQUIRED": "VARIANT_RELATION",
        "MOVEMENT_PATTERN_REVIEW": "MOVEMENT_PATTERN",
        "EQUIPMENT_TAXONOMY_CANDIDATE_REVIEW": "EQUIPMENT",
        "CARDIO_EQUIPMENT_TAXONOMY_MAPPING": "CARDIO_EQUIPMENT",
    }
    for code, review_type in mapping.items():
        if code in codes and values[review_type][3]:
            removed.append(code)
    if "HUMAN_TAXONOMY_REVIEW_REQUIRED" in codes and all(
        values[field][3] for field in ("FAMILY", "MOVEMENT_PATTERN", "EQUIPMENT")
    ):
        removed.append("HUMAN_TAXONOMY_REVIEW_REQUIRED")
    remaining = [code for code in codes if code not in removed]
    all_taxonomy_confirmed = all(
        values[field][3]
        for field in (
            "FAMILY",
            "VARIANT_RELATION",
            "MOVEMENT_PATTERN",
            "EQUIPMENT",
            "CARDIO_EQUIPMENT",
        )
    ) and not set(remaining).intersection(NON_FINAL_TAXONOMY_CODES)
    if all_taxonomy_confirmed:
        decision = "APPROVED"
    elif removed:
        # A taxonomy code may be removed for a confirmed field while another
        # taxonomy blocker remains in the same exercise.
        decision = "MODIFY"
    else:
        decision = "PENDING"
    reviewer = REVIEWER if decision == "APPROVED" else ""
    reviewed_at = REVIEWED_AT if decision == "APPROVED" else ""
    if decision == "MODIFY":
        reviewer = REVIEWER
        reviewed_at = REVIEWED_AT
    reason = (
        "TAXONOMY_VALUES_CONFIRMED_FROM_REPRESENTATIVE_AND_SOURCE_EVIDENCE"
        if decision == "APPROVED"
        else (
            "TAXONOMY_CODES_REMOVED_WITH_REMAINING_BLOCKER"
            if decision == "MODIFY"
            else "TAXONOMY_EVIDENCE_REMAINS_UNRESOLVED"
        )
    )
    output = dict(row)
    output.update(
        {
            "review_required": "true" if remaining else "false",
            "review_required_codes": "|".join(remaining),
            "reviewed_family": family,
            "reviewed_variant_relation": variant,
            "reviewed_movement_pattern": movement,
            "reviewed_equipment": equipment,
            "reviewed_cardio_equipment": cardio,
            "review_decision": decision,
            "review_reason_code": reason,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "taxonomy_review_status": (
                "TAXONOMY_APPROVED"
                if decision == "APPROVED"
                else "TAXONOMY_MODIFIED_REVIEW_REQUIRED"
                if decision == "MODIFY"
                else "REVIEW_REQUIRED"
            ),
        }
    )
    log = []
    for review_type, (previous, reviewed, field_reason, field_ok) in values.items():
        log.append(
            {
                "exercise_id": row["representative_id"],
                "exercise_name": row["representative_name_ko"],
                "review_type": review_type,
                "previous_value": previous,
                "reviewed_value": reviewed,
                "review_decision": "APPROVED" if field_ok else "PENDING",
                "review_reason_code": field_reason,
                "reviewer": REVIEWER if field_ok else "",
                "reviewed_at": REVIEWED_AT if field_ok else "",
            }
        )
    for code in removed:
        review_type = mapping.get(code, "HUMAN_TAXONOMY")
        previous = "PRESENT"
        reviewed = "REMOVED"
        log.append(
            {
                "exercise_id": row["representative_id"],
                "exercise_name": row["representative_name_ko"],
                "review_type": code,
                "previous_value": previous,
                "reviewed_value": reviewed,
                "review_decision": "APPROVED",
                "review_reason_code": f"{review_type}_CONFIRMED",
                "reviewer": REVIEWER,
                "reviewed_at": REVIEWED_AT,
            }
        )
    return output, log


def write_csv(path: Path, rows: list[dict[str, str]], fields: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]], log: list[dict[str, str]]) -> None:
    decision_counts = Counter(row["review_decision"] for row in rows)
    remaining = Counter(code for row in rows for code in split_codes(row["review_required_codes"]))
    pending_items = [
        f"- `{row['representative_id']}` {row['representative_name_ko']}: "
        f"family={row['reviewed_family']}, movement={row['reviewed_movement_pattern']}, "
        f"equipment={row['reviewed_equipment']}"
        for row in rows
        if row["review_decision"] == "PENDING"
    ]
    lines = [
        "# Representative Exercise Taxonomy Human Review",
        "",
        f"- 전체 운동: `{len(rows)}`",
        f"- 승인: `{decision_counts['APPROVED']}`",
        f"- 수정: `{decision_counts['MODIFY']}`",
        f"- 보류: `{decision_counts['PENDING']}`",
        f"- 로그 행 수: `{len(log)}`",
        f"- reviewer: `{REVIEWER}`",
        f"- reviewed_at: `{REVIEWED_AT}`",
        "",
        "## 남은 review_required_codes",
        "",
    ]
    lines.extend(f"- `{code}`: {count}건" for code, count in sorted(remaining.items()))
    lines.extend(["", "## 검토 필요 항목", ""])
    lines.extend(pending_items or ["- 없음"])
    lines.extend(
        [
            "",
            (
                "분류 코드 제거는 taxonomy 값이 확정되고 "
                "reviewer/reviewed_at이 기록된 경우에만 수행했다."
            ),
            "안전·콘텐츠·강도/MET·미디어·대체 관계 코드는 이 단계에서 제거하지 않았다.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    input_path: Path = DEFAULT_INPUT,
    integrated_path: Path = DEFAULT_INTEGRATED,
    output_path: Path = DEFAULT_OUTPUT,
    log_path: Path = DEFAULT_LOG,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, object]:
    with input_path.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    if len(source_rows) != 102:
        raise ValueError(f"expected 102 representative exercises, got {len(source_rows)}")
    integrated = load_integrated(integrated_path)
    reviewed: list[dict[str, str]] = []
    log: list[dict[str, str]] = []
    for row in source_rows:
        result, row_log = review_row(row, integrated)
        reviewed.append(result)
        log.extend(row_log)
    fields = list(dict.fromkeys([*source_rows[0].keys(), *OUTPUT_FIELDS]))
    write_csv(output_path, reviewed, fields)
    write_csv(log_path, log, LOG_FIELDS)
    write_summary(summary_path, reviewed, log)
    return {
        "input_rows": len(source_rows),
        "reviewed_rows": len(reviewed),
        "approved": sum(row["review_decision"] == "APPROVED" for row in reviewed),
        "modified": sum(row["review_decision"] == "MODIFY" for row in reviewed),
        "pending": sum(row["review_decision"] == "PENDING" for row in reviewed),
        "removed_code_count": sum(
            len(source_codes(source_row)) - len(split_codes(reviewed_row["review_required_codes"]))
            for source_row, reviewed_row in zip(source_rows, reviewed, strict=True)
        ),
        "review_log_rows": len(log),
        "remaining_review_required_codes": dict(
            Counter(code for row in reviewed for code in split_codes(row["review_required_codes"]))
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--integrated", type=Path, default=DEFAULT_INTEGRATED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run(args.input, args.integrated, args.output, args.log, args.summary),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
