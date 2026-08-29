"""Review the v2.0.2 discomfort target map with fail-closed filters.

Every candidate is either retained or removed.  Ambiguous candidates are not
sent to a human queue.  The original candidate map is preserved as audit
input; reviewed runtime candidates are written to separate artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE_MAP = (
    ROOT
    / "generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_v2_0_2.jsonl"
)
DEFAULT_CATALOG = ROOT / "generated/exercise-catalog-v2.0.2-final/catalog/exercises.jsonl"
DEFAULT_POLICY = ROOT / "normalized/discomfort_alternative_map_review_policy_v2_0_2.json"
DEFAULT_OUTPUT = ROOT / "generated/exercise-catalog-v2.0.2-final/alternatives"

POLICY_VERSION = "discomfort-alternative-map-review-v2.0.2-v1.0.0"
REVIEWED_AT = "2026-08-28T00:00:00+09:00"
# The map has passed the current domain review input.  Promotion remains
# blocked separately by production_eligible and the unresolved difficulty
# review batch.
REVIEW_STATUS = "DOMAIN_APPROVED"
PRODUCTION_ELIGIBLE = False
VALID_CONDITIONS = {"NRS_1_3", "NRS_4_6"}
VALID_LOCATIONS = {"HOME", "GYM"}
VALID_RECORD_TYPES = {"REPRESENTATIVE", "SEPARATE_EXERCISE"}
SOURCE_RECORD_TYPES = {"REPRESENTATIVE"}
DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}

BASE_FIELDS = [
    "map_relation_id",
    "pain_discomfort_area_code",
    "condition_code",
    "pain_score_min",
    "pain_score_max",
    "severity_code",
    "service_action_code",
    "target_strategy_code",
    "source_exercise_stable_code",
    "source_exercise_id",
    "source_record_type",
    "source_exercise_name_ko",
    "source_primary_movement_pattern_code",
    "source_primary_body_area_codes",
    "source_secondary_body_area_codes",
    "source_difficulty_code",
    "source_training_type_code",
    "target_exercise_stable_code",
    "target_exercise_id",
    "target_record_type",
    "target_exercise_name_ko",
    "target_primary_movement_pattern_code",
    "target_primary_body_area_codes",
    "target_secondary_body_area_codes",
    "target_difficulty_code",
    "target_training_type_code",
    "source_load_to_avoid_code",
    "source_load_to_avoid_roles",
    "target_area_exclusion_check_code",
    "target_pain_area_overlap",
    "target_difficulty_not_higher",
    "target_recovery_eligible",
    "selection_rank",
    "selection_score",
    "selection_basis_codes",
    "direction_code",
    "evidence_source",
    "evidence_reviewer",
    "evidence_reviewed_at",
    "review_status_code",
    "production_eligible",
]
REVIEW_FIELDS = BASE_FIELDS + [
    "target_equipment_codes",
    "target_location_codes",
    "target_body_focus_code",
    "target_timing_mode_code",
    "target_default_dosage_present",
    "review_decision",
    "review_stage_code",
    "review_reason_code",
    "review_reason_ko",
    "movement_load_impact_check_code",
    "nrs_recovery_check_code",
    "context_equipment_check_code",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"JSONL input is empty: {path}")
    return rows


def json_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json_value(row.get(field, "")) for field in fields})


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def area_codes(row: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for field in ("primary_body_area_codes", "secondary_body_area_codes")
        for value in row.get(field, [])
    }


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    catalog = read_jsonl(path)
    by_code: dict[str, dict[str, Any]] = {}
    for row in catalog:
        code = str(row.get("stable_code", "")).strip()
        exercise_id = str(row.get("exercise_id", "")).strip()
        if not code or not exercise_id or code in by_code:
            raise ValueError(f"catalog stable code/id is blank or duplicated: {code}/{exercise_id}")
        by_code[code] = row
    return by_code


def remove_result(stage: str, code: str, reason: str) -> tuple[str, str, str, str]:
    return (
        "REMOVE",
        stage,
        code,
        reason,
    )


def evaluate(
    row: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[str, str, str, str, str, str, str]:
    area = str(row.get("pain_discomfort_area_code", ""))
    condition = str(row.get("condition_code", ""))
    source = catalog.get(str(row.get("source_exercise_stable_code", "")))
    target = catalog.get(str(row.get("target_exercise_stable_code", "")))
    movement_check = "PASS"
    nrs_check = "PASS"
    context_check = "PASS"

    if source is None or target is None:
        return (
            *remove_result(
                "CATALOG_REFERENCE_ELIGIBILITY",
                "MISSING_EXERCISE_REFERENCE",
                "source 또는 target stable code가 catalog에 없다.",
            ),
            movement_check,
            nrs_check,
            context_check,
        )
    source_areas = area_codes(source)
    target_areas = area_codes(target)
    if area not in source_areas:
        return (
            *remove_result(
                "PRIMARY_SECONDARY_PAIN_AREA_OVERLAP",
                "SOURCE_PAIN_AREA_MISSING",
                "source가 입력된 통증 부위를 primary·secondary target으로 포함하지 않는다.",
            ),
            movement_check,
            nrs_check,
            context_check,
        )
    if area in target_areas:
        return (
            *remove_result(
                "PRIMARY_SECONDARY_PAIN_AREA_OVERLAP",
                "TARGET_PAIN_AREA_OVERLAP",
                "target이 입력된 통증 부위를 primary·secondary target으로 계속 포함한다.",
            ),
            movement_check,
            nrs_check,
            context_check,
        )
    if (
        source.get("record_type") not in SOURCE_RECORD_TYPES
        or target.get("record_type") not in VALID_RECORD_TYPES
        or target.get("review_status_code") != "DOMAIN_APPROVED"
        or source.get("review_status_code") != "DOMAIN_APPROVED"
        or row.get("source_exercise_stable_code") == row.get("target_exercise_stable_code")
    ):
        return (
            *remove_result(
                "CATALOG_REFERENCE_ELIGIBILITY",
                "CATALOG_REFERENCE_NOT_ELIGIBLE",
                "catalog record type·review 상태·self-reference 조건을 충족하지 않는다.",
            ),
            movement_check,
            nrs_check,
            context_check,
        )

    profile = policy["area_profiles"].get(area)
    if not isinstance(profile, dict):
        return (
            *remove_result(
                "MOVEMENT_LOAD_IMPACT_RISK",
                "PAIN_AREA_PROFILE_MISSING",
                "통증 부위별 movement/load/impact 안전 프로파일이 없다.",
            ),
            "FAIL",
            nrs_check,
            context_check,
        )
    pattern = str(target.get("primary_movement_pattern_code", ""))
    body_focus = str(target.get("body_focus_code", ""))
    target_areas_allowed = {str(value) for value in profile.get("allowed_target_body_areas", [])}
    target_focus_allowed = {
        str(value) for value in profile.get("allowed_target_body_focus_codes", [])
    }
    patterns_allowed = {str(value) for value in profile.get("allowed_movement_patterns", [])}
    blocked_patterns = {
        str(value) for value in policy["global_guards"]["blocked_movement_patterns"]
    }
    if (
        not pattern
        or pattern in blocked_patterns
        or pattern not in patterns_allowed
        or not body_focus
        or body_focus not in target_focus_allowed
        or not target_areas
        or (target_areas_allowed and not target_areas.issubset(target_areas_allowed))
        or not target.get("timing_mode_code")
        or target.get("default_rest_seconds") is None
        or (
            target.get("default_work_seconds") is None
            and target.get("default_seconds_per_rep") is None
        )
    ):
        return (
            *remove_result(
                "MOVEMENT_LOAD_IMPACT_RISK",
                "MOVEMENT_LOAD_IMPACT_RISK",
                "movement pattern·body focus·저부하 profile 중 하나라도 허용 목록에 없거나 "
                "dosage 근거가 불명확하다.",
            ),
            "FAIL",
            nrs_check,
            context_check,
        )

    if condition not in VALID_CONDITIONS:
        return (
            *remove_result(
                "NRS_INTENSITY_AND_RECOVERY",
                "UNSUPPORTED_NRS_CONDITION",
                "지원하지 않는 통증 강도 구간이다.",
            ),
            movement_check,
            "FAIL",
            context_check,
        )
    source_rank = DIFFICULTY_RANK.get(str(source.get("difficulty_code", "")))
    target_rank = DIFFICULTY_RANK.get(str(target.get("difficulty_code", "")))
    if source_rank is None or target_rank is None or target_rank > source_rank:
        return (
            *remove_result(
                "NRS_INTENSITY_AND_RECOVERY",
                "TARGET_DIFFICULTY_HIGHER_OR_UNKNOWN",
                "target 난이도가 source보다 높거나 비교값이 없다.",
            ),
            movement_check,
            "FAIL",
            context_check,
        )
    if condition == "NRS_4_6" and target.get("recovery_eligible") is not True:
        return (
            *remove_result(
                "NRS_INTENSITY_AND_RECOVERY",
                "MODERATE_TARGET_NOT_RECOVERY_ELIGIBLE",
                "moderate 구간은 recovery_eligible target만 허용한다.",
            ),
            movement_check,
            "FAIL",
            context_check,
        )

    locations = {str(value) for value in target.get("location_codes", [])}
    equipment = {str(value) for value in target.get("equipment_codes", [])}
    forbidden_equipment = {
        str(value) for value in policy["global_guards"]["forbidden_equipment_codes"]
    }
    if (
        not locations
        or not locations.issubset(VALID_LOCATIONS)
        or not equipment
        or equipment & forbidden_equipment
    ):
        return (
            *remove_result(
                "HOME_GYM_AND_EQUIPMENT",
                "CONTEXT_OR_EQUIPMENT_UNCERTAIN",
                "HOME/GYM 또는 장비 metadata가 없거나 허용 목록 밖이다.",
            ),
            movement_check,
            nrs_check,
            "FAIL",
        )
    return (
        "KEEP",
        "REMAINING_CANDIDATE_KEEP",
        "",
        "통증 부위 비중복·movement/load/impact·NRS·context/equipment 조건을 모두 통과했다.",
        movement_check,
        nrs_check,
        context_check,
    )


def reviewed_row(
    row: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    result: tuple[str, str, str, str, str, str, str],
) -> dict[str, Any]:
    decision, stage, reason_code, reason_ko, movement, nrs, context = result
    target = catalog.get(str(row.get("target_exercise_stable_code")), {})
    output = dict(row)
    output.update(
        {
            "target_equipment_codes": target.get("equipment_codes", []),
            "target_location_codes": target.get("location_codes", []),
            "target_body_focus_code": target.get("body_focus_code", ""),
            "target_timing_mode_code": target.get("timing_mode_code", ""),
            "target_default_dosage_present": target.get("default_rest_seconds") is not None
            and (
                target.get("default_work_seconds") is not None
                or target.get("default_seconds_per_rep") is not None
            ),
            "review_decision": decision,
            "review_stage_code": stage,
            "review_reason_code": reason_code,
            "review_reason_ko": reason_ko,
            "movement_load_impact_check_code": movement,
            "nrs_recovery_check_code": nrs,
            "context_equipment_check_code": context,
            "review_status_code": REVIEW_STATUS,
            "production_eligible": PRODUCTION_ELIGIBLE,
        }
    )
    return output


def target_sets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for area in sorted({str(row["pain_discomfort_area_code"]) for row in rows}):
        result[area] = {}
        area_rows = [row for row in rows if row["pain_discomfort_area_code"] == area]
        for condition in sorted({str(row["condition_code"]) for row in area_rows}):
            condition_rows = [row for row in area_rows if row["condition_code"] == condition]
            targets = sorted({str(row["target_exercise_stable_code"]) for row in condition_rows})
            target_ids = sorted({str(row["target_exercise_id"]) for row in condition_rows})
            home = sorted(
                {
                    str(row["target_exercise_stable_code"])
                    for row in condition_rows
                    if "HOME" in set(row["target_location_codes"])
                }
            )
            gym = sorted(
                {
                    str(row["target_exercise_stable_code"])
                    for row in condition_rows
                    if "GYM" in set(row["target_location_codes"])
                }
            )
            sources = {str(row["source_exercise_stable_code"]) for row in condition_rows}
            result[area][condition] = {
                "source_exercise_count": len(sources),
                "target_exercise_count": len(targets),
                "target_exercise_stable_codes": targets,
                "target_exercise_ids": target_ids,
                "home_target_exercise_stable_codes": home,
                "gym_target_exercise_stable_codes": gym,
            }
    return result


def integrity_report(
    candidate_rows: list[dict[str, Any]],
    kept_rows: list[dict[str, Any]],
    removed_rows: list[dict[str, Any]],
    candidate_map_path: Path,
    catalog_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    reviewed_rows = kept_rows + removed_rows
    stage_counts = Counter(row["review_stage_code"] for row in reviewed_rows)
    decision_counts = Counter(row["review_decision"] for row in reviewed_rows)
    natural_keys = [
        (
            row["source_exercise_stable_code"],
            row["target_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
        for row in kept_rows
    ]
    natural_counts = Counter(natural_keys)
    missing_refs = sum(
        row["source_exercise_stable_code"] not in catalog
        or row["target_exercise_stable_code"] not in catalog
        for row in kept_rows
    )
    excluded_refs = sum(
        catalog[row["source_exercise_stable_code"]].get("record_type") not in VALID_RECORD_TYPES
        or catalog[row["target_exercise_stable_code"]].get("record_type") not in VALID_RECORD_TYPES
        for row in kept_rows
        if row["source_exercise_stable_code"] in catalog
        and row["target_exercise_stable_code"] in catalog
    )
    unapproved_refs = sum(
        catalog[row["source_exercise_stable_code"]].get("review_status_code") != "DOMAIN_APPROVED"
        or catalog[row["target_exercise_stable_code"]].get("review_status_code")
        != "DOMAIN_APPROVED"
        for row in kept_rows
        if row["source_exercise_stable_code"] in catalog
        and row["target_exercise_stable_code"] in catalog
    )
    source_id_mismatches = sum(
        row["source_exercise_id"] != catalog[row["source_exercise_stable_code"]].get("exercise_id")
        for row in kept_rows
        if row["source_exercise_stable_code"] in catalog
    )
    target_id_mismatches = sum(
        row["target_exercise_id"] != catalog[row["target_exercise_stable_code"]].get("exercise_id")
        for row in kept_rows
        if row["target_exercise_stable_code"] in catalog
    )
    target_overlap = sum(
        row["pain_discomfort_area_code"]
        in (
            set(row["target_primary_body_area_codes"])
            | set(row["target_secondary_body_area_codes"])
        )
        for row in kept_rows
    )
    source_missing = sum(
        row["pain_discomfort_area_code"]
        not in (
            set(row["source_primary_body_area_codes"])
            | set(row["source_secondary_body_area_codes"])
        )
        for row in kept_rows
    )
    direction_errors = sum(
        row["direction_code"] != "A_TO_B"
        or row["source_exercise_stable_code"] == row["target_exercise_stable_code"]
        for row in kept_rows
    )
    forbidden_equipment = {"BENCH", "CHAIR", "REVIEW_REQUIRED"}
    context_errors = sum(
        not set(catalog[row["target_exercise_stable_code"]].get("location_codes", []))
        or not set(catalog[row["target_exercise_stable_code"]].get("location_codes", [])).issubset(
            VALID_LOCATIONS
        )
        or not set(catalog[row["target_exercise_stable_code"]].get("equipment_codes", []))
        or bool(
            set(catalog[row["target_exercise_stable_code"]].get("equipment_codes", []))
            & forbidden_equipment
        )
        for row in kept_rows
        if row["target_exercise_stable_code"] in catalog
    )
    check_errors = sum(
        row.get("movement_load_impact_check_code") != "PASS"
        or row.get("nrs_recovery_check_code") != "PASS"
        or row.get("context_equipment_check_code") != "PASS"
        for row in kept_rows
    )
    unsupported_condition_errors = sum(
        row.get("condition_code") not in VALID_CONDITIONS or row.get("condition_code") == "NRS_7_10"
        for row in kept_rows
    )
    report = {
        "schema_version": "discomfort-alternative-map-review-report-v2.0.2-v1",
        "policy_version": POLICY_VERSION,
        "reviewed_at": REVIEWED_AT,
        "status": "DRAFT_REVIEW_REQUIRED",
        "production_eligible": PRODUCTION_ELIGIBLE,
        "review_mode": "DETERMINISTIC_REMOVE_AMBIGUOUS",
        "source": {
            "candidate_map": {
                "path": str(candidate_map_path.relative_to(ROOT.parent)),
                "sha256": sha256_file(candidate_map_path),
            },
            "catalog": {
                "path": str(catalog_path.relative_to(ROOT.parent)),
                "sha256": sha256_file(catalog_path),
            },
            "policy": {
                "path": str(policy_path.relative_to(ROOT.parent)),
                "sha256": sha256_file(policy_path),
            },
        },
        "counts": {
            "candidate_map_count": len(candidate_rows),
            "reviewed_keep_count": len(kept_rows),
            "removed_count": len(removed_rows),
            "ambiguous_sent_to_human_review_count": 0,
            "decision_counts": dict(sorted(decision_counts.items())),
            "review_stage_counts": dict(sorted(stage_counts.items())),
            "removed_stage_counts": dict(
                sorted(Counter(row["review_stage_code"] for row in removed_rows).items())
            ),
            "removal_reason_counts": dict(
                sorted(Counter(row["review_reason_code"] for row in removed_rows).items())
            ),
            "reviewed_condition_counts": dict(
                sorted(Counter(row["condition_code"] for row in kept_rows).items())
            ),
        },
        "natural_key": [
            "source_exercise_stable_code",
            "target_exercise_stable_code",
            "pain_discomfort_area_code",
            "condition_code",
        ],
        "invariants": {
            "all_candidate_rows_accounted_for": len(reviewed_rows) == len(candidate_rows),
            "all_removed_rows_have_reason": all(
                row["review_decision"] == "REMOVE" and row["review_reason_code"]
                for row in removed_rows
            ),
            "no_self_reference": all(
                row["source_exercise_stable_code"] != row["target_exercise_stable_code"]
                for row in kept_rows
            ),
            "no_duplicate_natural_key": sum(
                count - 1 for count in natural_counts.values() if count > 1
            )
            == 0,
            "no_missing_exercise_reference": missing_refs == 0,
            "no_excluded_exercise_reference": excluded_refs == 0,
            "no_unapproved_exercise_reference": unapproved_refs == 0,
            "stable_code_id_traceability": source_id_mismatches == 0 and target_id_mismatches == 0,
            "no_target_pain_area_overlap": target_overlap == 0,
            "source_contains_pain_area": source_missing == 0,
            "no_directionality_error": direction_errors == 0,
            "all_kept_conditions_supported": unsupported_condition_errors == 0,
            "all_kept_filter_checks_pass": check_errors == 0,
            "all_kept_contexts_are_valid": context_errors == 0,
            "no_review_required_ambiguity_queue": not any(
                row["review_reason_code"] == "AMBIGUOUS_REVIEW_REQUIRED" for row in removed_rows
            ),
            "all_kept_rows_have_review_status": all(
                row["review_status_code"] == REVIEW_STATUS for row in kept_rows
            ),
        },
        "integrity_metrics": {
            "self_reference_count": sum(
                row["source_exercise_stable_code"] == row["target_exercise_stable_code"]
                for row in kept_rows
            ),
            "duplicate_natural_key_count": sum(
                count - 1 for count in natural_counts.values() if count > 1
            ),
            "missing_exercise_reference_count": missing_refs,
            "excluded_exercise_reference_count": excluded_refs,
            "unapproved_exercise_reference_count": unapproved_refs,
            "source_exercise_id_mismatch_count": source_id_mismatches,
            "target_exercise_id_mismatch_count": target_id_mismatches,
            "target_pain_area_overlap_count": target_overlap,
            "source_pain_area_missing_count": source_missing,
            "directionality_error_count": direction_errors,
            "context_or_equipment_error_count": context_errors,
            "filter_check_error_count": check_errors,
            "unsupported_condition_count": unsupported_condition_errors,
        },
    }
    return report


def build(
    candidate_map_path: Path = DEFAULT_CANDIDATE_MAP,
    catalog_path: Path = DEFAULT_CATALOG,
    policy_path: Path = DEFAULT_POLICY,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    policy = read_json(policy_path)
    if not isinstance(policy, dict) or policy.get("policy_version") != POLICY_VERSION:
        raise ValueError("map review policy version is invalid")
    candidate_rows = read_jsonl(candidate_map_path)
    catalog = load_catalog(catalog_path)
    evaluated_rows = [
        reviewed_row(row, catalog, evaluate(row, catalog, policy)) for row in candidate_rows
    ]
    kept_rows = [row for row in evaluated_rows if row["review_decision"] == "KEEP"]
    removed_rows = [row for row in evaluated_rows if row["review_decision"] == "REMOVE"]
    report = integrity_report(
        candidate_rows,
        kept_rows,
        removed_rows,
        candidate_map_path,
        catalog_path,
        policy_path,
    )
    if not all(report["invariants"].values()):
        failed = [key for key, value in report["invariants"].items() if not value]
        raise ValueError(f"discomfort alternative map review integrity failed: {failed}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "reviewed_jsonl": output_dir / "reviewed_discomfort_alternative_map_v2_0_2.jsonl",
        "reviewed_csv": output_dir / "reviewed_discomfort_alternative_map_v2_0_2.csv",
        "removed_jsonl": output_dir / "removed_discomfort_alternative_map_v2_0_2.jsonl",
        "removed_csv": output_dir / "removed_discomfort_alternative_map_v2_0_2.csv",
        "target_sets": output_dir / "reviewed_discomfort_alternative_target_sets_v2_0_2.json",
        "integrity_report": output_dir / "discomfort_alternative_map_review_report_v2_0_2.json",
    }
    write_jsonl(paths["reviewed_jsonl"], kept_rows)
    write_csv(paths["reviewed_csv"], REVIEW_FIELDS, kept_rows)
    write_jsonl(paths["removed_jsonl"], removed_rows)
    write_csv(paths["removed_csv"], REVIEW_FIELDS, removed_rows)
    write_json(
        paths["target_sets"],
        {
            "schema_version": "reviewed-discomfort-alternative-target-sets-v2.0.2-v1",
            "policy_version": POLICY_VERSION,
            "status": "DRAFT_REVIEW_REQUIRED",
            "production_eligible": PRODUCTION_ELIGIBLE,
            "sets": target_sets(kept_rows),
        },
    )
    write_json(paths["integrity_report"], report)
    manifest_path = output_dir / "discomfort_alternative_map_review_manifest_v2_0_2.json"
    write_json(
        manifest_path,
        {
            "schema_version": "discomfort-alternative-map-review-manifest-v2.0.2-v1",
            "policy_version": POLICY_VERSION,
            "reviewed_at": REVIEWED_AT,
            "status": "DRAFT_REVIEW_REQUIRED",
            "production_eligible": PRODUCTION_ELIGIBLE,
            "review_mode": "DETERMINISTIC_REMOVE_AMBIGUOUS",
            "source": {
                "candidate_map": str(candidate_map_path.relative_to(ROOT.parent)),
                "catalog": str(catalog_path.relative_to(ROOT.parent)),
                "policy": str(policy_path.relative_to(ROOT.parent)),
            },
            "counts": report["counts"],
            "artifacts": {
                name: {
                    "path": path.name,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for name, path in paths.items()
            },
        },
    )
    return {
        "candidate_map_count": len(candidate_rows),
        "reviewed_keep_count": len(kept_rows),
        "removed_count": len(removed_rows),
        "removal_reason_counts": report["counts"]["removal_reason_counts"],
        "integrity_metrics": report["integrity_metrics"],
        "manifest": str(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-map", type=Path, default=DEFAULT_CANDIDATE_MAP)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.candidate_map, args.catalog, args.policy, args.output_dir),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
