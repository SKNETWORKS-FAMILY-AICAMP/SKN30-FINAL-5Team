#!/usr/bin/env python3
# ruff: noqa: E501
"""Build HOME/GYM context defaults and coverage evidence for catalog v2.0.2.

This report is intentionally separate from the exercise catalog.  It selects
only representative/Variant rows in the same family, applies the approved
HOME equipment boundary, and never treats an alternative relation or a
SEPARATE_EXERCISE row as a context fallback.

The generated artifacts remain draft evidence.  A Variant default is useful
for deciding the intended context policy, but it cannot be operational until
its family, safety, FITT, and prescription review gates are complete.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DATA_ROOT.parent
DEFAULT_CATALOG = DATA_ROOT / (
    "generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/"
    "catalog/exercises.jsonl"
)
DEFAULT_GOALS = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.2-draft/prescriptions/goal_tag_links.jsonl"
)
DEFAULT_PRESCRIPTIONS = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.2-draft/prescriptions/prescription_profiles.jsonl"
)
DEFAULT_MANIFEST = DATA_ROOT / (
    "generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/"
    "intermediate_manifest.json"
)
DEFAULT_OUTPUT = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final/audit/context"
DEFAULT_REPORT = DATA_ROOT / "reports/V2_0_2_CONTEXT_DEFAULTS_AND_COVERAGE.md"

CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
REPORT_VERSION = "v2.0.2-context-defaults-coverage-v1.0.0"
GENERATED_AT = "2026-08-28T00:00:00+09:00"
CONTEXT_CODES = ("HOME", "GYM")
PHASE_CODES = ("WARMUP", "MAIN", "COOLDOWN")
EXPERIENCE_CODES = ("BEGINNER", "INTERMEDIATE")
SUPPORTED_DURATION_MINUTES = (10, 20, 30, 40, 50, 60)
HOME_SUPPORTED_EQUIPMENT = frozenset(
    {
        "BODYWEIGHT",
        "HOUSEHOLD_WEIGHT",
        "MAT",
        "DUMBBELL",
        "RESISTANCE_BAND",
        "FOAM_ROLLER",
        "JUMP_ROPE",
    }
)
VALID_VARIANT_TYPES = frozenset({"PRIMARY_VARIANT", "SECONDARY_VARIANT"})
INVALID_FAMILY_CODES = frozenset({"", "NONE", "N/A", "REVIEW_REQUIRED"})
VALID_FAMILY_RECORD_TYPES = frozenset({"REPRESENTATIVE", "VARIANT"})
DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1}


class ContextDefaultsError(ValueError):
    """Raised when the input cannot be evaluated safely."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--goals", type=Path, default=DEFAULT_GOALS)
    parser.add_argument("--prescriptions", type=Path, default=DEFAULT_PRESCRIPTIONS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ContextDefaultsError(f"cannot read JSONL: {path}") from error
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContextDefaultsError(f"invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise ContextDefaultsError(f"JSON object expected at {path}:{line_number}")
        rows.append(value)
    return rows


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContextDefaultsError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContextDefaultsError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: csv_value(row.get(key)) for key in columns} for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [item.strip() for item in value.split("|") if item.strip()]
    return as_list(parsed)


def compact(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def is_home_eligible(row: dict[str, Any]) -> bool:
    equipment = set(as_list(row.get("equipment_codes")))
    return "HOME" in as_list(row.get("location_codes")) and equipment <= HOME_SUPPORTED_EQUIPMENT


def is_context_eligible(row: dict[str, Any], context_code: str) -> bool:
    if context_code == "HOME":
        return is_home_eligible(row)
    return context_code in as_list(row.get("location_codes"))


def candidate_origin_rank(row: dict[str, Any]) -> int:
    if row.get("record_type") == "REPRESENTATIVE":
        return 0
    if row.get("variant_type_code") == "PRIMARY_VARIANT":
        return 1
    return 2


def candidate_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return (
        candidate_origin_rank(row),
        DIFFICULTY_RANK.get(str(row.get("difficulty_code")), 99),
        str(row.get("exercise_id", "")),
    )


def validate_catalog(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ContextDefaultsError("catalog is empty")
    exercise_ids = [str(row.get("exercise_id", "")) for row in rows]
    stable_codes = [str(row.get("stable_code", "")) for row in rows]
    if any(not value for value in exercise_ids + stable_codes):
        raise ContextDefaultsError("catalog has a blank exercise_id or stable_code")
    if len(exercise_ids) != len(set(exercise_ids)):
        raise ContextDefaultsError("catalog exercise_id is not unique")
    if len(stable_codes) != len(set(stable_codes)):
        raise ContextDefaultsError("catalog stable_code is not unique")
    invalid_versions = [
        row["exercise_id"] for row in rows if row.get("catalog_version_code") != CATALOG_VERSION
    ]
    if invalid_versions:
        raise ContextDefaultsError(f"catalog version mismatch: {invalid_versions[:3]}")
    representatives = {
        str(row["exercise_id"]): row
        for row in rows
        if row.get("record_type") == "REPRESENTATIVE" and row.get("is_representative") is True
    }
    invalid_variants: list[str] = []
    for row in rows:
        if row.get("record_type") != "VARIANT":
            continue
        representative_id = str(row.get("representative_exercise_id", ""))
        if (
            row.get("is_representative") is not False
            or row.get("variant_type_code") not in VALID_VARIANT_TYPES
            or representative_id not in representatives
            or row.get("family_code") != representatives[representative_id].get("family_code")
        ):
            invalid_variants.append(str(row.get("exercise_id", "")))
    if invalid_variants:
        raise ContextDefaultsError(f"invalid Variant relationship: {invalid_variants[:5]}")
    return {
        "exercise_ids": set(exercise_ids),
        "representatives": representatives,
        "variant_rows": [row for row in rows if row.get("record_type") == "VARIANT"],
        "invalid_family_representatives": [
            row
            for row in representatives.values()
            if str(row.get("family_code", "")) in INVALID_FAMILY_CODES
        ],
        "separate_exercise_count": sum(
            row.get("record_type") == "SEPARATE_EXERCISE" for row in rows
        ),
        "home_location_equipment_conflicts": [
            row
            for row in rows
            if "HOME" in as_list(row.get("location_codes"))
            and not set(as_list(row.get("equipment_codes"))) <= HOME_SUPPORTED_EQUIPMENT
        ],
        "home_without_gym_rows": [
            row
            for row in rows
            if "HOME" in as_list(row.get("location_codes"))
            and "GYM" not in as_list(row.get("location_codes"))
        ],
    }


def validate_goal_links(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        stable_code = str(row.get("exercise_stable_code", ""))
        goal_code = str(row.get("goal_code", ""))
        if not stable_code or not goal_code:
            continue
        key = f"{stable_code}:{goal_code}"
        if key in result and result[key] != row:
            raise ContextDefaultsError(f"duplicate goal link: {key}")
        result[key] = row
    return result


def validate_prescriptions(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        stable_code = str(row.get("exercise_stable_code", ""))
        goal_code = str(row.get("goal_code", ""))
        experience = str(row.get("experience_level_code", ""))
        phase = str(row.get("phase_code", ""))
        if stable_code and goal_code and experience and phase:
            result[(stable_code, goal_code, experience)].append(row)
    return result


def family_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("record_type") not in VALID_FAMILY_RECORD_TYPES:
            continue
        family_code = str(row.get("family_code", ""))
        if family_code in INVALID_FAMILY_CODES:
            continue
        groups[family_code].append(row)
    return dict(groups)


def representative_rows(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in group if row.get("record_type") == "REPRESENTATIVE"]


def exact_goal_link(
    representative: dict[str, Any] | None, goal_links: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    if representative is None:
        return None
    stable_code = str(representative.get("stable_code", ""))
    return goal_links.get(f"{stable_code}:GENERAL_FITNESS")


def family_review_status(
    default: dict[str, Any] | None,
    goal_link: dict[str, Any] | None,
    prescription_map: dict[tuple[str, str, str], list[dict[str, Any]]],
    representative: dict[str, Any] | None,
    ambiguous: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if ambiguous:
        reasons.append("MULTIPLE_REPRESENTATIVES_IN_FAMILY")
    if default is not None and default.get("record_type") == "VARIANT":
        reasons.append("DEFAULT_VARIANT_RELATION_REVIEW_REQUIRED")
    if representative is not None and goal_link is None:
        reasons.append("GOAL_LINK_NOT_FOUND")
    if representative is not None:
        stable_code = str(representative.get("stable_code", ""))
        if not any(
            prescription_map.get((stable_code, "GENERAL_FITNESS", experience))
            for experience in EXPERIENCE_CODES
        ):
            reasons.append("PRESCRIPTION_LINK_NOT_FOUND")
    return ("REVIEW_REQUIRED" if reasons else "DOMAIN_APPROVED", reasons)


def unavailable_reasons(group: list[dict[str, Any]], context_code: str) -> list[str]:
    if not group:
        return ["NO_FAMILY_CANDIDATE"]
    reasons: list[str] = []
    if context_code not in {code for row in group for code in as_list(row.get("location_codes"))}:
        reasons.append("LOCATION_NOT_DECLARED")
    if context_code == "HOME":
        unsupported = sorted(
            {
                equipment
                for row in group
                if "HOME" in as_list(row.get("location_codes"))
                for equipment in set(as_list(row.get("equipment_codes"))) - HOME_SUPPORTED_EQUIPMENT
            }
        )
        if unsupported:
            reasons.append("HOME_UNSUPPORTED_EQUIPMENT")
    return reasons or ["NO_CONTEXT_ELIGIBLE_CANDIDATE"]


def candidate_projection(row: dict[str, Any], rank: int, default_id: str) -> dict[str, Any]:
    return {
        "candidate_exercise_id": row["exercise_id"],
        "default_exercise_id": default_id,
        "priority_rank": rank,
        "fallback_candidate": rank > 1,
        "record_type": row.get("record_type", ""),
        "variant_type_code": row.get("variant_type_code", ""),
        "name_ko": row.get("name_ko", ""),
        "stable_code": row.get("stable_code", ""),
        "equipment_codes": as_list(row.get("equipment_codes")),
        "location_codes": as_list(row.get("location_codes")),
        "difficulty_code": row.get("difficulty_code", ""),
        "review_status_code": row.get("review_status_code", ""),
        "production_eligible": False,
    }


def build_context_artifacts(
    catalog_rows: list[dict[str, Any]],
    goal_rows: list[dict[str, Any]],
    prescription_rows: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    validation = validate_catalog(catalog_rows)
    goal_links = validate_goal_links(goal_rows)
    prescription_map = validate_prescriptions(prescription_rows)
    groups = family_groups(catalog_rows)
    defaults: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []

    def add_review(
        item_type: str,
        reason: str,
        *,
        family_code: str = "",
        representative_id: str = "",
        exercise_id: str = "",
        context_code: str = "",
        severity: str = "REVIEW",
        note: str = "",
    ) -> None:
        review_queue.append(
            {
                "review_item_id": f"CTX-{len(review_queue) + 1:04d}",
                "item_type_code": item_type,
                "family_code": family_code,
                "representative_exercise_id": representative_id,
                "exercise_id": exercise_id,
                "context_code": context_code,
                "review_status_code": "REVIEW_REQUIRED",
                "severity_code": severity,
                "reason_code": reason,
                "note_ko": note,
                "production_eligible": False,
            }
        )

    for row in validation["invalid_family_representatives"]:
        add_review(
            "INVALID_FAMILY_CODE",
            "INVALID_FAMILY_CODE",
            representative_id=str(row["exercise_id"]),
            exercise_id=str(row["exercise_id"]),
            severity="BLOCKER",
            note="대표운동의 family_code가 REVIEW_REQUIRED placeholder라 family default를 산출하지 않는다.",
        )

    for row in validation["home_location_equipment_conflicts"]:
        add_review(
            "HOME_LOCATION_EQUIPMENT_CONFLICT",
            "HOME_UNSUPPORTED_EQUIPMENT",
            family_code=str(row.get("family_code", "")),
            representative_id=str(row.get("representative_exercise_id", "")),
            exercise_id=str(row.get("exercise_id", "")),
            context_code="HOME",
            severity="REVIEW",
            note="catalog location_codes에 HOME이 있어도 서비스 허용 장비 밖이면 HOME 후보로 사용하지 않는다.",
        )

    for row in validation["home_without_gym_rows"]:
        add_review(
            "HOME_GYM_LOCATION_CONSISTENCY",
            "HOME_NOT_GYM_LOCATION",
            family_code=str(row.get("family_code", "")),
            representative_id=str(row.get("representative_exercise_id", "")),
            exercise_id=str(row.get("exercise_id", "")),
            context_code="GYM",
            severity="REVIEW",
            note="HOME 수행 가능 운동은 GYM에서도 수행 가능하도록 location_codes 일관성을 확인한다. 자동으로 GYM을 추가하지 않고 검수 대상으로 남긴다.",
        )

    for family_code in sorted(groups):
        group = groups[family_code]
        representatives = representative_rows(group)
        ambiguous = len(representatives) != 1
        representative = representatives[0] if not ambiguous else None
        representative_id = str(representative["exercise_id"]) if representative else ""
        representative_ids = [str(row["exercise_id"]) for row in representatives]
        if ambiguous:
            for context_code in CONTEXT_CODES:
                add_review(
                    "AMBIGUOUS_FAMILY_REPRESENTATIVE",
                    "MULTIPLE_REPRESENTATIVES_IN_FAMILY",
                    family_code=family_code,
                    context_code=context_code,
                    severity="BLOCKER",
                    note="하나의 family_code에 대표운동이 여러 개라 대표-Variant 방향과 Context Default를 확정하지 않는다.",
                )

        goal_link = exact_goal_link(representative, goal_links)
        for context_code in CONTEXT_CODES:
            raw_eligible = [row for row in group if is_context_eligible(row, context_code)]
            ranked = [] if ambiguous else sorted(raw_eligible, key=candidate_sort_key)
            default = ranked[0] if ranked else None
            default_id = str(default["exercise_id"]) if default is not None else ""
            fallback = [
                candidate_projection(row, index, default_id) for index, row in enumerate(ranked, 1)
            ][1:]
            if default is not None:
                candidate_rows.extend(
                    candidate_projection(row, index, default_id)
                    | {
                        "catalog_version_code": CATALOG_VERSION,
                        "family_code": family_code,
                        "representative_exercise_id": representative_id,
                        "context_code": context_code,
                    }
                    for index, row in enumerate(ranked, 1)
                )

            review_status, review_reasons = family_review_status(
                default, goal_link, prescription_map, representative, ambiguous
            )
            if default is None:
                context_status = "REVIEW_REQUIRED" if ambiguous else "UNAVAILABLE"
                if not ambiguous:
                    review_reasons = unavailable_reasons(group, context_code)
                    add_review(
                        "CONTEXT_DEFAULT_UNAVAILABLE",
                        review_reasons[0],
                        family_code=family_code,
                        representative_id=representative_id,
                        context_code=context_code,
                        severity="BLOCKER",
                        note="동일 family 내부에 해당 context에서 사용할 대표/Variant 후보가 없다.",
                    )
            else:
                context_status = "REVIEW_REQUIRED" if review_reasons else "COVERED_DRAFT"
                if default.get("record_type") == "VARIANT":
                    add_review(
                        "VARIANT_CONTEXT_DEFAULT",
                        "DEFAULT_VARIANT_RELATION_REVIEW_REQUIRED",
                        family_code=family_code,
                        representative_id=representative_id,
                        exercise_id=default_id,
                        context_code=context_code,
                        severity="REVIEW",
                        note="Context 적합성 때문에 Variant를 1순위로 두었지만 관계·안전·FITT 검수 전에는 운영 사용하지 않는다.",
                    )
                if "GOAL_LINK_NOT_FOUND" in review_reasons:
                    add_review(
                        "GOAL_LINK_MISSING",
                        "GOAL_LINK_NOT_FOUND",
                        family_code=family_code,
                        representative_id=representative_id,
                        context_code=context_code,
                        severity="BLOCKER",
                        note="대표운동 stable_code와 승인 goal link가 정확히 일치하지 않는다.",
                    )
                if "PRESCRIPTION_LINK_NOT_FOUND" in review_reasons:
                    add_review(
                        "PRESCRIPTION_MISSING",
                        "PRESCRIPTION_LINK_NOT_FOUND",
                        family_code=family_code,
                        representative_id=representative_id,
                        context_code=context_code,
                        severity="BLOCKER",
                        note="대표운동 stable_code와 service prescription이 정확히 일치하지 않는다.",
                    )

            selected_for_dimensions = raw_eligible
            training_types = sorted(
                {
                    str(row.get("training_type_code", ""))
                    for row in selected_for_dimensions
                    if row.get("training_type_code")
                }
            )
            movement_patterns = sorted(
                {
                    str(row.get("primary_movement_pattern_code", ""))
                    for row in selected_for_dimensions
                    if row.get("primary_movement_pattern_code")
                }
            )
            body_areas = sorted(
                {
                    area
                    for row in selected_for_dimensions
                    for area in as_list(row.get("primary_body_area_codes"))
                }
            )
            difficulties = sorted(
                {
                    str(row.get("difficulty_code", ""))
                    for row in selected_for_dimensions
                    if row.get("difficulty_code")
                },
                key=lambda value: (DIFFICULTY_RANK.get(value, 99), value),
            )
            phases = sorted(
                {
                    phase
                    for row in selected_for_dimensions
                    for phase in as_list(row.get("phase_codes"))
                },
                key=lambda value: (PHASE_CODES.index(value) if value in PHASE_CODES else 99, value),
            )
            coverage_rows.append(
                {
                    "catalog_version_code": CATALOG_VERSION,
                    "family_code": family_code,
                    "representative_exercise_id": representative_id,
                    "representative_exercise_ids": representative_ids,
                    "context_code": context_code,
                    "context_coverage_status_code": context_status,
                    "representative_context_eligible": bool(
                        representative and is_context_eligible(representative, context_code)
                    ),
                    "raw_context_candidate_count": len(raw_eligible),
                    "context_candidate_count": len(ranked),
                    "primary_variant_context_candidate_count": sum(
                        row.get("variant_type_code") == "PRIMARY_VARIANT" for row in raw_eligible
                    ),
                    "secondary_variant_context_candidate_count": sum(
                        row.get("variant_type_code") == "SECONDARY_VARIANT" for row in raw_eligible
                    ),
                    "default_exercise_id": default_id,
                    "default_priority_rank": 1 if default else None,
                    "default_record_type": default.get("record_type", "") if default else "",
                    "default_variant_type_code": default.get("variant_type_code", "")
                    if default
                    else "",
                    "default_name_ko": default.get("name_ko", "") if default else "",
                    "default_equipment_codes": as_list(default.get("equipment_codes"))
                    if default
                    else [],
                    "fallback_candidate_ids": [item["candidate_exercise_id"] for item in fallback],
                    "goal_codes": ["GENERAL_FITNESS"] if goal_link else [],
                    "goal_coverage_status_code": "COVERED" if goal_link else "REVIEW_REQUIRED",
                    "training_type_codes": training_types,
                    "movement_pattern_codes": movement_patterns,
                    "primary_body_area_codes": body_areas,
                    "difficulty_codes": difficulties,
                    "phase_codes": phases,
                    "review_status_code": review_status
                    if default or ambiguous
                    else "REVIEW_REQUIRED",
                    "review_reason_codes": review_reasons,
                    "production_eligible": False,
                }
            )

    for row in catalog_rows:
        if row.get("record_type") != "VARIANT":
            continue
        add_review(
            "VARIANT_MAPPING_PENDING",
            "VARIANT_SAFETY_FITT_REVIEW_REQUIRED",
            family_code=str(row.get("family_code", "")),
            representative_id=str(row.get("representative_exercise_id", "")),
            exercise_id=str(row.get("exercise_id", "")),
            severity="BLOCKER",
            note="Variant row는 관계·안전·FITT 상태가 REVIEW_REQUIRED라 운영 기본 후보로 승격하지 않는다.",
        )

    return {
        "validation": validation,
        "goal_links": goal_links,
        "prescription_map": prescription_map,
        "groups": groups,
        "defaults": sorted(
            defaults,
            key=lambda row: (str(row.get("family_code", "")), str(row.get("context_code", ""))),
        ),
        "candidate_rows": sorted(
            candidate_rows,
            key=lambda row: (row["family_code"], row["context_code"], row["priority_rank"]),
        ),
        "coverage_rows": sorted(
            coverage_rows, key=lambda row: (row["family_code"], row["context_code"])
        ),
        "review_queue": review_queue,
        "manifest": manifest,
    }


def make_defaults(
    coverage_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        candidates_by_key[(row["family_code"], row["context_code"])].append(row)
    result: list[dict[str, Any]] = []
    for coverage in coverage_rows:
        key = (coverage["family_code"], coverage["context_code"])
        ranked = candidates_by_key.get(key, [])
        fallback = [
            {
                "candidate_exercise_id": row["candidate_exercise_id"],
                "priority_rank": row["priority_rank"],
                "record_type": row["record_type"],
                "variant_type_code": row["variant_type_code"],
                "name_ko": row["name_ko"],
                "stable_code": row["stable_code"],
                "equipment_codes": row["equipment_codes"],
                "difficulty_code": row["difficulty_code"],
                "review_status_code": row["review_status_code"],
            }
            for row in ranked[1:]
        ]
        result.append(
            {
                "catalog_version_code": CATALOG_VERSION,
                "selection_policy_version": REPORT_VERSION,
                "family_code": coverage["family_code"],
                "representative_exercise_id": coverage["representative_exercise_id"],
                "representative_exercise_ids": coverage["representative_exercise_ids"],
                "context_code": coverage["context_code"],
                "default_exercise_id": coverage["default_exercise_id"],
                "priority_rank": coverage["default_priority_rank"],
                "default_record_type": coverage["default_record_type"],
                "default_variant_type_code": coverage["default_variant_type_code"],
                "default_name_ko": coverage["default_name_ko"],
                "default_equipment_codes": coverage["default_equipment_codes"],
                "fallback_candidates": fallback,
                "context_default_status_code": coverage["context_coverage_status_code"],
                "review_status_code": coverage["review_status_code"],
                "review_reason_codes": coverage["review_reason_codes"],
                "production_eligible": False,
                "decision_note_ko": (
                    "대표운동을 1순위로 유지하고 같은 family의 Variant를 fallback으로 둔다."
                    if coverage["default_record_type"] == "REPRESENTATIVE"
                    else "대표운동이 context에 없으므로 같은 family의 Variant를 1순위로 두되 운영 승격은 보류한다."
                    if coverage["default_record_type"] == "VARIANT"
                    else "context default를 확정하지 않고 review/blocker로 남긴다."
                ),
            }
        )
    return result


def item_seconds(row: dict[str, Any], prescription: dict[str, Any]) -> int | None:
    sets = prescription.get("sets")
    rest = prescription.get("rest_seconds_per_set")
    transition = row.get("default_transition_seconds")
    if not isinstance(sets, int) or isinstance(sets, bool):
        return None
    if not isinstance(rest, int) or isinstance(rest, bool):
        return None
    if not isinstance(transition, int) or isinstance(transition, bool):
        return None
    reps = prescription.get("reps")
    work_seconds = prescription.get("work_seconds_per_set")
    if reps is not None:
        seconds_per_rep = row.get("default_seconds_per_rep")
        if (
            row.get("timing_mode_code") != "REPS"
            or not isinstance(reps, int)
            or not isinstance(seconds_per_rep, int)
        ):
            return None
        work = reps * seconds_per_rep
    else:
        if row.get("timing_mode_code") != "DURATION" or not isinstance(work_seconds, int):
            return None
        work = work_seconds
    return sets * work + max(sets - 1, 0) * rest + transition


def subset_states(
    candidates: list[tuple[dict[str, Any], dict[str, Any], bool]], target: int
) -> dict[tuple[int, bool], tuple[tuple[dict[str, Any], dict[str, Any], bool], ...]]:
    states: dict[tuple[int, bool], tuple[tuple[dict[str, Any], dict[str, Any], bool], ...]] = {
        (0, False): ()
    }
    for candidate in sorted(
        candidates,
        key=lambda item: (str(item[0].get("name_ko", "")), str(item[0].get("exercise_id", ""))),
    ):
        seconds = item_seconds(candidate[0], candidate[1])
        if seconds is None:
            continue
        additions: dict[
            tuple[int, bool], tuple[tuple[dict[str, Any], dict[str, Any], bool], ...]
        ] = {}
        for (current, has_core), selected in states.items():
            total = current + seconds
            if total > target:
                continue
            key = (total, has_core or candidate[2])
            proposed = (*selected, candidate)
            existing = states.get(key) or additions.get(key)
            if existing is None or len(proposed) < len(existing):
                additions[key] = proposed
        states.update(additions)
    return states


def draft_duration_match(
    candidates: list[tuple[dict[str, Any], dict[str, Any], bool]], target_seconds: int
) -> bool:
    by_phase = {
        phase: [candidate for candidate in candidates if candidate[1].get("phase_code") == phase]
        for phase in PHASE_CODES
    }
    if any(not by_phase[phase] for phase in PHASE_CODES):
        return False
    warmups = subset_states(by_phase["WARMUP"], min(target_seconds, 180))
    mains = subset_states(by_phase["MAIN"], target_seconds + 300)
    cooldowns = subset_states(by_phase["COOLDOWN"], min(target_seconds, 120))
    for (warmup_seconds, _), _warmup_items in warmups.items():
        if not 60 <= warmup_seconds <= 180:
            continue
        for (main_seconds, has_core), _main_items in mains.items():
            if not has_core or main_seconds <= 0:
                continue
            for (cooldown_seconds, _), _cooldown_items in cooldowns.items():
                if not 45 <= cooldown_seconds <= 120:
                    continue
                content_seconds = warmup_seconds + main_seconds + cooldown_seconds
                setup_seconds = min(max(target_seconds - content_seconds, 0), 60)
                if abs(content_seconds + setup_seconds - target_seconds) <= 300:
                    return True
    return False


def build_routine_coverage(
    catalog_rows: list[dict[str, Any]],
    goal_links: dict[str, dict[str, Any]],
    prescription_map: dict[tuple[str, str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    representatives = [
        row
        for row in catalog_rows
        if row.get("record_type") == "REPRESENTATIVE"
        and str(row.get("family_code", "")) not in INVALID_FAMILY_CODES
    ]
    result: list[dict[str, Any]] = []
    for context_code in CONTEXT_CODES:
        for experience in EXPERIENCE_CODES:
            allowed_difficulties = (
                {"BEGINNER"} if experience == "BEGINNER" else {"BEGINNER", "INTERMEDIATE"}
            )
            pool: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            invalid_timing_count = 0
            profile_status_counts: Counter[str] = Counter()
            for row in representatives:
                if not is_context_eligible(row, context_code):
                    continue
                if row.get("difficulty_code") not in allowed_difficulties:
                    continue
                goal_link = goal_links.get(f"{row.get('stable_code')}:GENERAL_FITNESS")
                if goal_link is None:
                    continue
                profiles = prescription_map.get(
                    (str(row.get("stable_code")), "GENERAL_FITNESS", experience), []
                )
                for profile in profiles:
                    if profile.get("phase_code") not in as_list(row.get("phase_codes")):
                        continue
                    profile_status_counts[str(profile.get("review_status_code", ""))] += 1
                    if item_seconds(row, profile) is None:
                        invalid_timing_count += 1
                        continue
                    pool.append(
                        (
                            row,
                            profile,
                            goal_link.get("role_eligibility_code") == "CORE"
                            and profile.get("phase_code") == "MAIN",
                        )
                    )
            phase_counts = {
                phase: sum(item[1].get("phase_code") == phase for item in pool)
                for phase in PHASE_CODES
            }
            duration_support = {
                str(minutes): draft_duration_match(pool, minutes * 60)
                for minutes in SUPPORTED_DURATION_MINUTES
            }
            draft_composable = all(duration_support.values()) and all(phase_counts.values())
            result.append(
                {
                    "catalog_version_code": CATALOG_VERSION,
                    "context_code": context_code,
                    "experience_level_code": experience,
                    "candidate_exercise_count": len({item[0]["exercise_id"] for item in pool}),
                    "candidate_profile_count": len(pool),
                    "phase_candidate_counts": phase_counts,
                    "core_main_candidate_count": sum(item[2] for item in pool),
                    "invalid_timing_profile_count": invalid_timing_count,
                    "profile_review_status_counts": dict(sorted(profile_status_counts.items())),
                    "duration_support_by_requested_minutes": duration_support,
                    "draft_pool_status_code": "DRAFT_COMPOSABLE" if draft_composable else "BLOCKED",
                    "operational_status_code": "BLOCKED_PRODUCTION_GATE",
                    "production_eligible": False,
                }
            )
    return result


def build_coverage_report(
    artifacts: dict[str, Any], routine_coverage: list[dict[str, Any]]
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = artifacts["groups"]
    coverage_rows: list[dict[str, Any]] = artifacts["coverage_rows"]
    defaults = make_defaults(coverage_rows, artifacts["candidate_rows"])
    by_context: dict[str, list[dict[str, Any]]] = {
        context: [row for row in coverage_rows if row["context_code"] == context]
        for context in CONTEXT_CODES
    }

    def context_summary(context: str) -> dict[str, Any]:
        rows = by_context[context]
        return {
            "family_count": len(rows),
            "covered_draft_count": sum(
                row["context_coverage_status_code"] == "COVERED_DRAFT" for row in rows
            ),
            "review_required_count": sum(
                row["context_coverage_status_code"] == "REVIEW_REQUIRED" for row in rows
            ),
            "unavailable_count": sum(
                row["context_coverage_status_code"] == "UNAVAILABLE" for row in rows
            ),
            "representative_default_count": sum(
                row["default_record_type"] == "REPRESENTATIVE" for row in rows
            ),
            "variant_default_count": sum(row["default_record_type"] == "VARIANT" for row in rows),
            "default_exercise_count": sum(bool(row["default_exercise_id"]) for row in rows),
            "goal_covered_family_count": sum(
                row["goal_coverage_status_code"] == "COVERED"
                and row["raw_context_candidate_count"] > 0
                for row in rows
            ),
            "phase_family_counts": {
                phase: sum(
                    phase in row["phase_codes"] and row["raw_context_candidate_count"] > 0
                    for row in rows
                )
                for phase in PHASE_CODES
            },
        }

    # The reference axis is taken from all real family rows, including the
    # ambiguous CARDIO family, while selectable axes use resolved defaults.
    family_candidate_rows = [
        row
        for family_rows in groups.values()
        for row in family_rows
        if row.get("record_type") in VALID_FAMILY_RECORD_TYPES
    ]

    def axis_values(rows: list[dict[str, Any]], field: str, context: str) -> set[str]:
        context_rows = [row for row in rows if is_context_eligible(row, context)]
        if field == "primary_body_area_codes":
            return {value for row in context_rows for value in as_list(row.get(field))}
        if field == "phase_codes":
            return {value for row in context_rows for value in as_list(row.get(field))}
        return {str(row.get(field)) for row in context_rows if row.get(field)}

    axis_fields = {
        "goal": "goal_codes",
        "training_type": "training_type_code",
        "movement_pattern": "primary_movement_pattern_code",
        "primary_body_area": "primary_body_area_codes",
        "difficulty": "difficulty_code",
        "phase": "phase_codes",
    }
    coverage_axes: dict[str, Any] = {}
    for context in CONTEXT_CODES:
        selectable_rows = [
            row
            for row in coverage_rows
            if row["context_code"] == context
            and row["context_coverage_status_code"] == "COVERED_DRAFT"
        ]
        coverage_axes[context] = {}
        for axis, field in axis_fields.items():
            if axis == "goal":
                reference = {"GENERAL_FITNESS"}
                selectable = {goal for row in selectable_rows for goal in row["goal_codes"]}
            else:
                reference = axis_values(family_candidate_rows, field, context)
                selectable = (
                    {value for row in selectable_rows for value in row[field]}
                    if field in {"primary_body_area_codes", "phase_codes"}
                    else {
                        value
                        for row in selectable_rows
                        for value in row.get(
                            {
                                "training_type_code": "training_type_codes",
                                "primary_movement_pattern_code": "movement_pattern_codes",
                                "difficulty_code": "difficulty_codes",
                            }[field],
                            [],
                        )
                    }
                )
            coverage_axes[context][axis] = {
                "reference_values": sorted(reference),
                "selectable_values": sorted(selectable),
                "missing_from_selectable": sorted(reference - selectable),
            }

    invalid_timing = []
    profile_rows = artifacts["prescription_map"]
    catalog_by_stable = {
        str(row.get("stable_code")): row
        for row in artifacts["validation"]["representatives"].values()
    }
    for profiles in profile_rows.values():
        for profile in profiles:
            row = catalog_by_stable.get(str(profile.get("exercise_stable_code")))
            if row is not None and item_seconds(row, profile) is None:
                invalid_timing.append(profile)

    actual_canonical_count = (
        len(artifacts["validation"]["representatives"])
        + artifacts["validation"]["separate_exercise_count"]
    )
    manifest_count = None
    if artifacts["manifest"]:
        manifest_count = artifacts["manifest"].get("counts", {}).get("active_canonical_exercises")

    review_reason_counts = Counter(item["reason_code"] for item in artifacts["review_queue"])
    unavailable_count = sum(
        row["context_coverage_status_code"] == "UNAVAILABLE" for row in coverage_rows
    )
    routine_blockers = [
        {
            "reason_code": "CATALOG_NOT_PRODUCTION_ELIGIBLE",
            "count": 1,
            "note_ko": "v2.0.2 통합 카탈로그 production_eligible=false라 Context Default는 운영 추천으로 사용할 수 없다.",
        },
        {
            "reason_code": "VARIANT_SAFETY_FITT_REVIEW_REQUIRED",
            "count": len(artifacts["validation"]["variant_rows"]),
            "note_ko": "Variant의 관계·안전·FITT가 REVIEW_REQUIRED다.",
        },
        {
            "reason_code": "INVALID_TIMING_PROFILE",
            "count": len(invalid_timing),
            "note_ko": "REPS 처방인데 catalog timing_mode가 DURATION이거나 seconds_per_rep가 없어 시간 계산이 불가능한 처방이 있다.",
        },
        {
            "reason_code": "INVALID_FAMILY_CODE",
            "count": len(artifacts["validation"]["invalid_family_representatives"]),
            "note_ko": "대표운동 12건의 family_code가 REVIEW_REQUIRED placeholder다.",
        },
        {
            "reason_code": "AMBIGUOUS_FAMILY_REPRESENTATIVE",
            "count": sum(len(representative_rows(rows)) > 1 for rows in groups.values()),
            "note_ko": "CARDIO family처럼 하나의 family_code에 대표운동이 여러 개라 단일 default를 확정할 수 없다.",
        },
        {
            "reason_code": "CONTEXT_DEFAULT_UNAVAILABLE",
            "count": unavailable_count,
            "note_ko": "동일 family 내부에 해당 Context에서 사용할 대표/Variant 후보가 없어 실제 루틴 선택에서 제외된다.",
        },
        {
            "reason_code": "HOME_NOT_GYM_LOCATION",
            "count": len(artifacts["validation"]["home_without_gym_rows"]),
            "note_ko": "HOME 수행 가능 운동이 GYM location으로도 선언되어야 하는지 확인하는 일관성 검수 대상이다.",
        },
    ]
    routine_blockers = [item for item in routine_blockers if item["count"]]
    for reason_code, note in (
        (
            "GOAL_LINK_NOT_FOUND",
            "대표운동 stable_code와 승인 goal link가 정확히 일치하지 않아 목표 필터에 연결할 수 없다.",
        ),
        (
            "PRESCRIPTION_LINK_NOT_FOUND",
            "대표운동 stable_code와 service prescription이 정확히 일치하지 않아 처방을 계산할 수 없다.",
        ),
        (
            "LOCATION_NOT_DECLARED",
            "해당 Context가 location_codes에 선언되지 않아 Context 후보에서 제외한다.",
        ),
        (
            "HOME_UNSUPPORTED_EQUIPMENT",
            "HOME location이 선언되어도 허용 장비 집합 밖인 운동은 HOME 후보에서 제외한다.",
        ),
    ):
        reason_count = (
            len(artifacts["validation"]["home_location_equipment_conflicts"])
            if reason_code == "HOME_UNSUPPORTED_EQUIPMENT"
            else review_reason_counts.get(reason_code, 0)
        )
        if reason_count:
            routine_blockers.append(
                {
                    "reason_code": reason_code,
                    "count": reason_count,
                    "note_ko": note,
                }
            )
    if manifest_count != actual_canonical_count:
        routine_blockers.append(
            {
                "reason_code": "MANIFEST_CANONICAL_COUNT_MISMATCH",
                "count": 1,
                "note_ko": f"manifest active_canonical_exercises={manifest_count}와 catalog canonical rows={actual_canonical_count}가 다르다.",
            }
        )

    return {
        "schema_version": REPORT_VERSION,
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": "DRAFT_CONTEXT_DEFAULTS_REVIEW_REQUIRED",
        "production_eligible": False,
        "policy": {
            "home_supported_equipment_codes": sorted(HOME_SUPPORTED_EQUIPMENT),
            "equipment_metadata_role": "equipment_codes는 운동 분류와 수행 안내에만 사용하며 사용자 입력·개인화 필터로 사용하지 않는다.",
            "gym_equipment_policy": "GYM은 location_codes로만 Context를 판정하고, equipment_codes는 수행 안내에 노출한다.",
            "home_gym_location_invariant": "HOME 수행 가능 row는 GYM에서도 수행 가능하도록 HOME→GYM location 일관성을 검수하며, 미확정 row는 자동 수정하지 않는다.",
            "context_codes": list(CONTEXT_CODES),
            "context_priority": [
                "LOCATION_AND_HOME_EQUIPMENT_HARD_FILTER",
                "REPRESENTATIVE_IF_CONTEXT_ELIGIBLE",
                "PRIMARY_VARIANT_IF_REPRESENTATIVE_UNAVAILABLE",
                "SECONDARY_VARIANT_IF_PRIMARY_UNAVAILABLE",
                "BEGINNER_DIFFICULTY_THEN_EXERCISE_ID_TIEBREAK",
            ],
            "alternative_boundary": "통증/불편으로 운동을 교체하는 별도 관계이며 Context fallback에 사용하지 않는다.",
            "separate_exercise_policy": "SEPARATE_EXERCISE는 family fallback과 Context Default에서 제외한다.",
        },
        "counts": {
            "integrated_catalog_rows": len(artifacts["validation"]["exercise_ids"]),
            "representative_rows": len(artifacts["validation"]["representatives"]),
            "invalid_family_representative_rows": len(
                artifacts["validation"]["invalid_family_representatives"]
            ),
            "valid_family_code_count": len(groups),
            "unambiguous_family_count": sum(
                len(representative_rows(rows)) == 1 for rows in groups.values()
            ),
            "variant_rows": len(artifacts["validation"]["variant_rows"]),
            "separate_exercise_rows_excluded": artifacts["validation"]["separate_exercise_count"],
            "home_location_equipment_conflict_rows": len(
                artifacts["validation"]["home_location_equipment_conflicts"]
            ),
            "home_without_gym_rows": len(artifacts["validation"]["home_without_gym_rows"]),
            "context_default_rows": len(defaults),
            "context_candidate_rows": len(artifacts["candidate_rows"]),
            "review_queue_rows": len(artifacts["review_queue"]),
        },
        "context_summary": {context: context_summary(context) for context in CONTEXT_CODES},
        "coverage_axes": coverage_axes,
        "routine_coverage": routine_coverage,
        "routine_configuration_blockers": routine_blockers,
        "source_artifacts": {
            "catalog": repo_relative(DEFAULT_CATALOG),
            "goal_links": repo_relative(DEFAULT_GOALS),
            "prescriptions": repo_relative(DEFAULT_PRESCRIPTIONS),
            "manifest": repo_relative(DEFAULT_MANIFEST),
        },
        "notes": [
            "이 산출물은 신규 운동·Alternative를 생성하지 않는다.",
            "HOME location_codes가 있어도 장비가 HOME 허용 집합 밖이면 HOME 후보에서 제외한다.",
            "루틴 시간 coverage는 현재 service의 phase·CORE·±300초 조합 규칙을 draft timing/profile로 재현한 결과이며 production 승인 판정이 아니다.",
        ],
    }


def markdown_report(
    report: dict[str, Any], defaults: list[dict[str, Any]], review_queue: list[dict[str, Any]]
) -> str:
    summary = report["context_summary"]
    blockers = report["routine_configuration_blockers"]
    lines = [
        "# v2.0.2 HOME/GYM Context Default 및 Coverage 보고서",
        "",
        f"- 생성 시각: `{GENERATED_AT}`",
        f"- 상태: `{report['status']}`",
        "- 운영 적격: `false`",
        "",
        "## 결론",
        "",
        "Context fallback 우선순위는 `대표운동 → PRIMARY_VARIANT → SECONDARY_VARIANT`로 확정했다. "
        "단, 장소·장비 hard filter를 먼저 적용하고, HOME은 서비스 허용 장비만 통과시킨다. "
        "Variant가 default가 된 7개 HOME 항목은 관계·안전·FITT 검수 전까지 운영 default가 아니다.",
        "",
        "HOME 허용 장비: `BODYWEIGHT`, `HOUSEHOLD_WEIGHT`, `MAT`, `DUMBBELL`, "
        "`RESISTANCE_BAND`, `FOAM_ROLLER`, `JUMP_ROPE`.",
        "",
        "장비는 사용자 입력으로 받지 않으므로 GYM은 `location_codes=GYM`만으로 산출하고, "
        "`equipment_codes`는 운동 분류와 수행 안내에만 사용한다.",
        "",
        f"HOME 수행 가능 row는 GYM에서도 수행 가능하도록 `HOME ⊆ GYM` location 일관성을 검수한다. "
        f"검수 결과 현재 HOME-only row는 `{report['counts']['home_without_gym_rows']}`건이다.",
        "",
        "Alternative는 통증/불편에 의한 교체 관계로만 남기며, 장비·장소 fallback에는 사용하지 않는다. "
        "`SEPARATE_EXERCISE`도 family fallback에 사용하지 않는다.",
        "",
        "## Context 결과",
        "",
        "| Context | family | covered draft | representative default | Variant default | review | unavailable |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for context in CONTEXT_CODES:
        item = summary[context]
        lines.append(
            f"| {context} | {item['family_count']} | {item['covered_draft_count']} | "
            f"{item['representative_default_count']} | {item['variant_default_count']} | "
            f"{item['review_required_count']} | {item['unavailable_count']} |"
        )
    lines.extend(
        [
            "",
            "`representative/Variant default`는 선호 default 후보 유형 집계이고, `review/unavailable`은 상태 집계라 서로 겹칠 수 있다.",
            "",
        ]
    )
    lines.extend(
        [
            "",
            "## 선택 우선순위",
            "",
            "1. Context location과 HOME 허용 장비를 hard filter한다.",
            "2. 해당 family의 context-eligible 대표운동을 1순위로 둔다.",
            "3. 대표운동이 없을 때 PRIMARY_VARIANT, 그 다음 SECONDARY_VARIANT를 둔다.",
            "4. 같은 단계에서는 BEGINNER, exercise_id 순으로 tie-break한다. 장비 코드는 우선순위 계산에 사용하지 않는다.",
            "",
            "## Coverage 축",
            "",
        ]
    )
    for context in CONTEXT_CODES:
        lines.append(f"### {context}")
        lines.append("")
        for axis, values in report["coverage_axes"][context].items():
            missing = ", ".join(values["missing_from_selectable"]) or "없음"
            lines.append(
                f"- `{axis}`: 선택 가능 `{', '.join(values['selectable_values']) or '없음'}`; "
                f"reference 대비 미확정 `{missing}`"
            )
        lines.append("")
    lines.extend(
        [
            "## 루틴 구성 coverage",
            "",
            "현재 service의 WARMUP/MAIN/COOLDOWN, MAIN CORE, ±300초 규칙을 draft profile로 재현했다. "
            "서비스 지원 검사 시간 10·20·30·40·50·60분은 네 조합 모두 draft pool에서 구성 가능으로 확인되지만, "
            "카탈로그·처방이 production gate를 통과하지 않아 운영 가능을 의미하지 않는다.",
            "",
            "| Context | Experience | draft pool | operational | 10/20/30/40/50/60분 |",
            "|---|---|---|---|---|",
        ]
    )
    for row in report["routine_coverage"]:
        durations = "/".join(
            "Y" if row["duration_support_by_requested_minutes"][str(minutes)] else "N"
            for minutes in SUPPORTED_DURATION_MINUTES
        )
        lines.append(
            f"| {row['context_code']} | {row['experience_level_code']} | {row['draft_pool_status_code']} | "
            f"{row['operational_status_code']} | {durations} |"
        )
    lines.extend(["", "## 미확정·Blocker", ""])
    for blocker in blockers:
        lines.append(f"- `{blocker['reason_code']}`: {blocker['count']}건 — {blocker['note_ko']}")
    lines.extend(
        [
            "",
            f"Context review queue는 총 `{len(review_queue)}`건이며, 상세 row는 "
            "`context_default_review_queue_v2_0_2.jsonl/csv`에 보존했다.",
            "",
            "## 산출물",
            "",
            "- `context_defaults_v2_0_2.jsonl/csv`: family/context별 default와 fallback",
            "- `context_default_candidates_v2_0_2.jsonl/csv`: 우선순위별 후보",
            "- `family_context_coverage_v2_0_2.jsonl/csv`: family별 Context coverage",
            "- `routine_coverage_v2_0_2.jsonl/csv`: 시간별 draft 루틴 구성 검사",
            "- `context_default_review_queue_v2_0_2.jsonl/csv`: 미확정·review·blocker",
            "- `context_coverage_report_v2_0_2.json`: 재현 가능한 종합 report",
            "",
            "## 근거",
            "",
            "- `AGENTS.md` 7절·8절: HOME/GYM 실행 가능성, 안전·검수·운영 승격 원칙",
            "- `docs/DOMAIN_RULES.md` 4절·5절·6절: 장소·장비 우선순위, 시간 보존, 검수된 후보 사용",
            "- `docs/DATA_MODEL.md` 5.8: Alternative는 방향성 별도 관계이며 production 승인 row만 사용",
            "- `docs/tasks/TASK-ROUTINE-EQUIPMENT-AND-DURATION.md` 2.3·3절: Variant/Alternative 경계와 LOCATION 처리",
            "- `data/generated/exercise-catalog-v2.0.2-final/variant_integrity_report_v2_0_2.json`: Variant integrity 및 review gate",
        ]
    )
    return "\n".join(lines) + "\n"


def build(args: argparse.Namespace) -> dict[str, Any]:
    catalog_rows = read_jsonl(args.catalog)
    goal_rows = read_jsonl(args.goals)
    prescription_rows = read_jsonl(args.prescriptions)
    manifest = read_json(args.manifest) if args.manifest.exists() else None
    artifacts = build_context_artifacts(catalog_rows, goal_rows, prescription_rows, manifest)
    routine_coverage = build_routine_coverage(
        catalog_rows, artifacts["goal_links"], artifacts["prescription_map"]
    )
    defaults = make_defaults(artifacts["coverage_rows"], artifacts["candidate_rows"])
    report = build_coverage_report(artifacts, routine_coverage)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {
        "context_defaults_jsonl": output / "context_defaults_v2_0_2.jsonl",
        "context_defaults_csv": output / "context_defaults_v2_0_2.csv",
        "context_candidates_jsonl": output / "context_default_candidates_v2_0_2.jsonl",
        "context_candidates_csv": output / "context_default_candidates_v2_0_2.csv",
        "family_coverage_jsonl": output / "family_context_coverage_v2_0_2.jsonl",
        "family_coverage_csv": output / "family_context_coverage_v2_0_2.csv",
        "routine_coverage_jsonl": output / "routine_coverage_v2_0_2.jsonl",
        "routine_coverage_csv": output / "routine_coverage_v2_0_2.csv",
        "review_queue_jsonl": output / "context_default_review_queue_v2_0_2.jsonl",
        "review_queue_csv": output / "context_default_review_queue_v2_0_2.csv",
        "report_json": output / "context_coverage_report_v2_0_2.json",
    }
    write_jsonl(files["context_defaults_jsonl"], defaults)
    write_csv(files["context_defaults_csv"], defaults)
    write_jsonl(files["context_candidates_jsonl"], artifacts["candidate_rows"])
    write_csv(files["context_candidates_csv"], artifacts["candidate_rows"])
    write_jsonl(files["family_coverage_jsonl"], artifacts["coverage_rows"])
    write_csv(files["family_coverage_csv"], artifacts["coverage_rows"])
    write_jsonl(files["routine_coverage_jsonl"], routine_coverage)
    write_csv(files["routine_coverage_csv"], routine_coverage)
    write_jsonl(files["review_queue_jsonl"], artifacts["review_queue"])
    write_csv(files["review_queue_csv"], artifacts["review_queue"])
    write_json(files["report_json"], report)
    report_path = args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        markdown_report(report, defaults, artifacts["review_queue"]), encoding="utf-8"
    )
    manifest_value = {
        "schema_version": REPORT_VERSION,
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": report["status"],
        "production_eligible": False,
        "source": {
            "catalog": repo_relative(args.catalog),
            "goal_links": repo_relative(args.goals),
            "prescriptions": repo_relative(args.prescriptions),
            "manifest": repo_relative(args.manifest),
        },
        "counts": report["counts"],
        "artifact_sha256": {key: sha256(path) for key, path in files.items()},
        "report_path": repo_relative(report_path),
    }
    write_json(output / "context_manifest_v2_0_2.json", manifest_value)
    report["artifact_paths"] = {key: repo_relative(path) for key, path in files.items()}
    return report


def main(argv: list[str] | None = None) -> int:
    report = build(parse_args(argv))
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
