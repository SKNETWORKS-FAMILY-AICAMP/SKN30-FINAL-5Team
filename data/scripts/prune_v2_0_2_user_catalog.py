#!/usr/bin/env python3
"""Materialize the user-reviewed v2.0.2 exercise pool.

Pain-safe records remain Alternatives (``alternative_only``) while also being
available in the general exercise pool (``general_pool_included``). Legacy
Alternative target exercises are restored as ordinary REPRESENTATIVE records.
This script does not restore rejected Alternative relationships or manufacture
new Safety/FITT/Goal values.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from data.scripts.v2_0_2_difficulty_policy import apply_difficulty_policy
except ModuleNotFoundError:
    from v2_0_2_difficulty_policy import apply_difficulty_policy

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "generated/exercise-catalog-v2.0.2-final"
CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
GENERATED_AT = "2026-08-29T00:00:00+09:00"
DECISION_CODE = "USER_DIRECT_REVIEW_2026_08_29"
LEGACY_ALTERNATIVE_TARGETS = (
    ROOT / "generated/exercise-catalog-v2.0.1-final/exercise_alternatives_v2_final.csv"
)
LEGACY_REPRESENTATIVE_CATALOG = (
    ROOT / "generated/exercise-catalog-v2.0.1-final/representative_exercises_v2_final.csv"
)
REPS_TIMING_RESTORES = {
    "bodyweight_crunch_core_brace_bodyweight",
    "bodyweight_reverse_crunch_core_brace_bodyweight",
}

NAME_ONLY_PREFIXES = ("등받이 지지 좌식 ", "누워서 전신 지지 ")
KEEP_NAME_FRAGMENTS = (
    "덤벨 바이셉스 컬",
    "무릎 들기",
    "프론트 레이즈",
    "카프 레이즈",
    "손목 돌리기",
    "손목 당기기",
    "슈러그",
    "스텝밀",
)

SPECIAL_NAME_OVERRIDES = {
    "cardio_gait_machine_rex_000071": "스텝밀 머신(천국의 계단)",
}

# Existing pain-Alternative identities that were removed by the interrupted
# first prune run before its source artifact was regenerated.
RESTORE_ALLOWED_SAFE_IDENTITIES = (
    ("DVAR-03A7A7C6A78247A9", "dumbbell_standing_curl_isolation_dumbbell__knee_no_load_safe_v1", "덤벨 바이셉스 컬"),
    ("DVAR-06892D3AE613BF99", "hip_flexion_isolation_bodyweight__upper_back_no_load_safe_v1", "무릎 들기"),
    ("DVAR-249EF7CC8CED25D3", "dumbbell_shrug_isolation_dumbbell__lower_back_no_load_safe_v1", "슈러그"),
    ("DVAR-35756A39565C0E92", "dumbbell_standing_curl_isolation_dumbbell__abdomen_no_load_safe_v1", "덤벨 바이셉스 컬"),
    ("DVAR-3B2E8D5E61B19928", "barbell_front_raise_isolation_barbell__hip_no_load_safe_v1", "프론트 레이즈"),
    ("DVAR-439BA655BC3B7BC0", "seated_calf_raise_isolation_barbell__shoulder_no_load_safe_v1", "카프 레이즈"),
    ("DVAR-487544E110C93537", "dumbbell_standing_curl_isolation_dumbbell__hip_no_load_safe_v1", "덤벨 바이셉스 컬"),
    ("DVAR-51B939268597C1C2", "barbell_front_raise_isolation_barbell__abdomen_no_load_safe_v1", "프론트 레이즈"),
    ("DVAR-57ADC482D0C91C98", "barbell_front_raise_isolation_barbell__lower_back_no_load_safe_v1", "프론트 레이즈"),
    ("DVAR-5C8E3929479AD7D8", "bodyweight_standing_calf_raise_isolation_bodyweight__lower_back_no_load_safe_v1", "카프 레이즈"),
    ("DVAR-889F35FB54AD157C", "dumbbell_standing_curl_isolation_dumbbell__lower_back_no_load_safe_v1", "덤벨 바이셉스 컬"),
    ("DVAR-9D87E310514D2812", "wrist_circles_mobility_stretch_bodyweight__hip_no_load_safe_v1", "손목 돌리기"),
    ("DVAR-AC2A0EE066A11173", "wrist_circles_mobility_stretch_bodyweight__knee_no_load_safe_v1", "손목 돌리기"),
    ("DVAR-D58F02F81420FBED", "barbell_front_raise_isolation_barbell__knee_no_load_safe_v1", "프론트 레이즈"),
    ("DVAR-EB514FBF13F9433D", "dumbbell_shrug_isolation_dumbbell__hip_no_load_safe_v1", "슈러그"),
    ("DVAR-EC243CDB7A0537D3", "bodyweight_standing_calf_raise_isolation_bodyweight__abdomen_no_load_safe_v1", "카프 레이즈"),
    ("DVAR-FAB7479B08EBDD54", "dumbbell_shrug_isolation_dumbbell__knee_no_load_safe_v1", "슈러그"),
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key, "")) for key in fields})


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def clean_name(value: Any, *, remove_context_prefix: bool = False) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", str(value or "")).strip()
    if remove_context_prefix:
        for prefix in NAME_ONLY_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix) :].strip()
    return name


def equipment_codes_for_name(row: dict[str, Any], field: str) -> list[str]:
    if field.startswith("source_"):
        return list(row.get("source_equipment_codes") or [])
    if field.startswith("target_"):
        return list(row.get("target_equipment_codes") or [])
    return list(row.get("equipment_codes") or [])


def stable_code_for_name(row: dict[str, Any], field: str) -> str:
    if field.startswith("source_"):
        return str(row.get("source_exercise_stable_code") or "")
    if field.startswith("target_"):
        return str(row.get("target_exercise_stable_code") or "")
    return str(row.get("stable_code") or "")


def normalize_equipment_name(value: Any, equipment_codes: list[str], stable_code: str = "") -> str:
    name = clean_name(value, remove_context_prefix=True)
    override = SPECIAL_NAME_OVERRIDES.get(stable_code)
    if override:
        return override
    if "BARBELL" in equipment_codes:
        name = re.sub(r"^(?:덤벨|바벨)\s+", "", name)
        name = f"바벨 {name}".strip()
    elif "DUMBBELL" in equipment_codes:
        name = re.sub(r"^(?:덤벨|바벨)\s+", "", name)
        name = f"덤벨 {name}".strip()
    elif "MACHINE" in equipment_codes or "CABLE_MACHINE" in equipment_codes:
        if not name.endswith(" 머신"):
            name = f"{name} 머신".strip()
    return name


def is_stretch(row: dict[str, Any]) -> bool:
    korean = str(row.get("name_ko") or "")
    english = str(row.get("name_en") or "").lower()
    return "스트레칭" in korean or "stretch" in english


def keep_base(row: dict[str, Any]) -> bool:
    if row.get("general_pool_included") is True:
        return True
    if is_stretch(row):
        return True
    name = str(row.get("name_ko") or "")
    stable = str(row.get("stable_code") or "").lower()
    if any(fragment in name for fragment in KEEP_NAME_FRAGMENTS):
        return True
    return any(
        fragment in stable
        for fragment in (
            "front_raise",
            "calf_raise",
            "wrist_circles",
            "side_wrist_pull",
            "shrug",
            "cardio_gait_machine_rex_000071",
        )
    )


def restore_allowed_base_records(original: list[dict[str, Any]], final: Path) -> list[dict[str, Any]]:
    """Restore explicitly re-requested canonical base records when pruned earlier."""
    existing_ids = {str(row.get("exercise_id") or "") for row in original}
    canonical_path = final / "audit/canonical_exercises_v2_0_2_refined.jsonl"
    if not canonical_path.exists():
        return []
    canonical_rows = read_jsonl(canonical_path)
    restored: list[dict[str, Any]] = []
    for source in canonical_rows:
        if str(source.get("stable_code") or "") != "cardio_gait_machine_rex_000071":
            continue
        exercise_id = str(source.get("representative_exercise_id") or "REX-000071")
        if exercise_id in existing_ids:
            continue
        row = dict(source)
        row.update(
            {
                "exercise_id": exercise_id,
                "legacy_exercise_id": exercise_id,
                "record_type": "REPRESENTATIVE",
                "family_code": "CARDIO_GAIT_MACHINE",
                "is_representative": True,
                "representative_exercise_id": exercise_id,
                "variant_type_code": "",
                "support_equipment_codes": [],
                "difficulty_policy_rule_code": "NO_POLICY_OVERRIDE",
                "recovery_eligible": False,
                "variant_relation_status_code": "NOT_APPLICABLE",
                "variant_materialization_status_code": "NOT_APPLICABLE",
                "safety_mapping_source_representative_exercise_id": exercise_id,
                "safety_mapping_status_code": "REPRESENTATIVE_SAFETY_CONTEXT",
                "safety_rule_binding_status_code": "REVIEW_REQUIRED",
                "review_required": True,
                "review_required_codes": ["SOURCE_LICENSE_REVIEW_REQUIRED"],
                "production_eligible": False,
                "name_ko": SPECIAL_NAME_OVERRIDES["cardio_gait_machine_rex_000071"],
                "display_name_ko": SPECIAL_NAME_OVERRIDES["cardio_gait_machine_rex_000071"],
                "instruction_summary_ko": SPECIAL_NAME_OVERRIDES["cardio_gait_machine_rex_000071"],
                "form_cues_ko": [],
                "setup_condition_ko": "",
                "instruction_identity_status": "USER_REVIEWED_NAME_ONLY",
                "instruction_content_version": "user-name-only-v1",
                "user_review_decision_code": DECISION_CODE,
                "user_review_status": "COMPLETED",
                "catalog_version_code": CATALOG_VERSION,
            }
        )
        restored.append(row)
        existing_ids.add(exercise_id)
    return restored


def restore_legacy_alternative_targets(
    original: list[dict[str, Any]], final: Path
) -> list[dict[str, Any]]:
    """Restore v2.0.1 Alternative targets to the general pool.

    The old Alternative relation file is used only as an auditable allowlist
    of target stable codes. Exercise values come from the v2.0.2 canonical
    source artifact, so rejected relationships themselves are not recreated.
    """
    if not LEGACY_ALTERNATIVE_TARGETS.exists() or not LEGACY_REPRESENTATIVE_CATALOG.exists():
        return []
    canonical_path = final / "audit/canonical_exercises_v2_final.jsonl"
    if not canonical_path.exists():
        return []
    existing_ids = {str(row.get("exercise_id") or "") for row in original}
    existing_codes = {str(row.get("stable_code") or "") for row in original}
    target_codes = {
        str(row.get("alternative_exercise_stable_code") or "")
        for row in read_csv(LEGACY_ALTERNATIVE_TARGETS)
        if row.get("alternative_exercise_stable_code")
    }
    legacy_reps = {
        str(row.get("stable_code") or ""): row
        for row in read_csv(LEGACY_REPRESENTATIVE_CATALOG)
        if row.get("stable_code")
    }
    canonical_by_code = {
        str(row.get("stable_code") or ""): row
        for row in read_jsonl(canonical_path)
        if row.get("stable_code")
    }
    restored: list[dict[str, Any]] = []
    for stable_code in sorted(target_codes):
        if stable_code in existing_codes:
            continue
        source = canonical_by_code.get(stable_code)
        legacy = legacy_reps.get(stable_code, {})
        if source is None:
            raise ValueError(f"legacy Alternative target missing from canonical source: {stable_code}")
        exercise_id = str(source.get("representative_exercise_id") or "")
        if not exercise_id or exercise_id in existing_ids:
            continue
        row = dict(source)
        row.update(
            {
                "exercise_id": exercise_id,
                "legacy_exercise_id": exercise_id,
                "record_type": "REPRESENTATIVE",
                "family_code": str(legacy.get("exercise_family_code") or ""),
                "is_representative": True,
                "representative_exercise_id": exercise_id,
                "variant_type_code": "",
                "support_equipment_codes": [],
                "difficulty_policy_rule_code": "NO_POLICY_OVERRIDE",
                "variant_relation_status_code": "NOT_APPLICABLE",
                "variant_materialization_status_code": "NOT_APPLICABLE",
                "safety_mapping_source_representative_exercise_id": exercise_id,
                "safety_mapping_status_code": "REPRESENTATIVE_SAFETY_CONTEXT",
                "safety_rule_binding_status_code": "REVIEW_REQUIRED",
                "fitt_mapping_source_representative_exercise_id": exercise_id,
                "fitt_mapping_status_code": "RETAINED_FROM_REVIEWED_CATALOG",
                "review_required": True,
                "review_required_codes": ["SOURCE_LICENSE_REVIEW_REQUIRED"],
                "production_eligible": False,
                "source_provenance_status": "RESOLVED_INTEGRATED_SOURCE",
                "canonical_decision_code": "RESTORED_LEGACY_ALTERNATIVE_TARGET",
                "canonical_decision_source": "USER_DIRECT_REVIEW",
                "canonical_decision_note_ko": (
                    "기존 Alternative target 운동을 일반 운동 풀의 대표운동으로 복원한다."
                ),
                "general_pool_included": True,
                "general_pool_inclusion_reason_code": "LEGACY_ALTERNATIVE_TARGET_RESTORED",
                "alternative_only": False,
                "user_review_decision_code": DECISION_CODE,
                "user_review_status": "COMPLETED",
                "catalog_version_code": CATALOG_VERSION,
            }
        )
        if stable_code in REPS_TIMING_RESTORES:
            row["timing_mode_code"] = "REPS"
            row["default_work_seconds"] = None
            row["default_seconds_per_rep"] = 4
        if not row.get("family_code"):
            raise ValueError(f"legacy Alternative target family missing: {stable_code}")
        restored.append(row)
        existing_ids.add(exercise_id)
        existing_codes.add(stable_code)
    return restored


def normalize_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if not result.get("family_code") and str(result.get("stable_code") or "") in SPECIAL_NAME_OVERRIDES:
        result["family_code"] = "CARDIO_GAIT_MACHINE"
    result["name_ko"] = normalize_equipment_name(
        row.get("name_ko"), list(row.get("equipment_codes") or []), str(row.get("stable_code") or "")
    )
    result["difficulty_code"], result["difficulty_policy_rule_code"] = apply_difficulty_policy(
        result, str(row.get("difficulty_code") or "BEGINNER")
    )
    if str(row.get("stable_code") or "") in REPS_TIMING_RESTORES:
        result["timing_mode_code"] = "REPS"
        result["default_work_seconds"] = None
        result["default_seconds_per_rep"] = 4
    result["display_name_ko"] = result["name_ko"]
    result["review_status_code"] = "DOMAIN_APPROVED"
    result["user_review_decision_code"] = DECISION_CODE
    result["user_review_status"] = "COMPLETED"
    result["production_eligible"] = False
    result["instruction_summary_ko"] = result["name_ko"]
    result["form_cues_ko"] = []
    result["setup_condition_ko"] = ""
    result["instruction_identity_status"] = "USER_REVIEWED_NAME_ONLY"
    result["instruction_content_version"] = "user-name-only-v1"
    result["catalog_version_code"] = CATALOG_VERSION
    if row.get("alternative_only") or row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT":
        result["general_pool_included"] = True
        result["general_pool_inclusion_reason_code"] = "PAIN_ALTERNATIVE_TARGET_ALSO_GENERAL_POOL"
        review_codes = [
            code
            for code in result.get("review_required_codes", [])
            if code != "ALTERNATIVE_ONLY_NOT_GENERAL_POOL"
        ]
        if "ALTERNATIVE_TARGET_AND_GENERAL_POOL" not in review_codes:
            review_codes.append("ALTERNATIVE_TARGET_AND_GENERAL_POOL")
        result["review_required_codes"] = review_codes
        result["canonical_decision_note_ko"] = (
            "통증 Alternative target이면서 일반 운동 풀에도 포함한다."
        )
    return result


def exercise_refs(row: dict[str, Any]) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    codes: set[str] = set()
    for key, value in row.items():
        if not value:
            continue
        text = str(value)
        if key.endswith("exercise_id") or key in {"exercise_id", "representative_exercise_id", "variant_exercise_id", "default_exercise_id", "candidate_exercise_id"}:
            ids.add(text)
        if "stable_code" in key or key in {"stable_code", "code"}:
            codes.add(text)
    return ids, codes


def row_survives(row: dict[str, Any], keep_ids: set[str], keep_codes: set[str]) -> bool:
    ids, codes = exercise_refs(row)
    return not (ids - keep_ids) and not (codes - keep_codes)


def normalize_reference_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("source_exercise_name_ko", "target_exercise_name_ko", "name_ko", "display_name_ko"):
        if key in result:
            result[key] = normalize_equipment_name(
                result[key], equipment_codes_for_name(result, key), stable_code_for_name(result, key)
            )
    if "name_ko" in result:
        result["display_name_ko"] = result["name_ko"]
    if "catalog_version_code" in result:
        result["catalog_version_code"] = CATALOG_VERSION
    if "review_status_code" in result:
        result["review_status_code"] = "DOMAIN_APPROVED"
    result["user_review_decision_code"] = DECISION_CODE
    result["user_review_status"] = "COMPLETED"
    return result


def restore_allowed_safe_variants(
    original: list[dict[str, Any]], kept_base: list[dict[str, Any]], final: Path
) -> list[dict[str, Any]]:
    """Restore previously materialized pain Alternatives lost by an earlier prune.

    The prune report retains their stable code and user-visible name.  This is
    an identity-preserving restoration, not a newly inferred Safety rule.
    """
    report_path = final / "audit/integrity/user_catalog_prune_report_v2_0_2.json"
    if not report_path.exists():
        return []
    base_by_code = {str(row["stable_code"]): row for row in kept_base}
    existing_ids = {str(row.get("exercise_id")) for row in original}
    previous = read_json(report_path)
    restored: list[dict[str, Any]] = []
    deleted_rows = list(previous.get("deleted_records", []))
    deleted_rows.extend(
        {"exercise_id": exercise_id, "stable_code": stable, "name_ko": name}
        for exercise_id, stable, name in RESTORE_ALLOWED_SAFE_IDENTITIES
        if not any(row.get("exercise_id") == exercise_id for row in deleted_rows)
    )
    for deleted in deleted_rows:
        stable = str(deleted.get("stable_code") or "")
        exercise_id = str(deleted.get("exercise_id") or "")
        if "__" not in stable or not exercise_id or exercise_id in existing_ids:
            continue
        base_code, suffix = stable.split("__", 1)
        base = base_by_code.get(base_code)
        if base is None or not suffix.endswith("_no_load_safe_v1"):
            continue
        name = clean_name(deleted.get("name_ko"), remove_context_prefix=True)
        restored.append(
            {
                "exercise_id": exercise_id,
                "legacy_exercise_id": "",
                "record_type": "SEPARATE_EXERCISE",
                "catalog_version_code": CATALOG_VERSION,
                "stable_code": stable,
                "name_ko": name,
                "display_name_ko": name,
                "name_en": "",
                "family_code": str(base.get("family_code") or ""),
                "representative_exercise_id": "",
                "variant_type_code": "",
                "is_representative": False,
                "training_type_code": str(base.get("training_type_code") or "STRENGTH"),
                "body_focus_code": str(base.get("body_focus_code") or ""),
                "primary_movement_pattern_code": str(base.get("primary_movement_pattern_code") or ""),
                "primary_body_area_codes": list(base.get("primary_body_area_codes", [])),
                "secondary_body_area_codes": list(base.get("secondary_body_area_codes", [])),
                "equipment_codes": list(base.get("equipment_codes", [])),
                "support_equipment_codes": [],
                "location_codes": list(base.get("location_codes", [])),
                "difficulty_code": str(base.get("difficulty_code") or "BEGINNER"),
                "difficulty_status": "DOMAIN_APPROVED",
                "timing_mode_code": str(base.get("timing_mode_code") or "REPS"),
                "phase_codes": list(base.get("phase_codes", [])),
                "default_seconds_per_rep": None,
                "default_work_seconds": None,
                "default_rest_seconds": None,
                "default_transition_seconds": None,
                "instruction_summary_ko": name,
                "form_cues_ko": [],
                "setup_condition_ko": "",
                "source_track": "pain_alternative_policy",
                "source_identity": exercise_id,
                "source_key": f"pain_alternative_policy:{exercise_id}",
                "source_system": "pain_alternative_policy",
                "source_record_id": exercise_id,
                "source_name": name,
                "source_name_ko": name,
                "source_provenance_status": "RESTORED_POLICY_RECORD",
                "review_status_code": "DOMAIN_APPROVED",
                "review_required": False,
                "review_required_codes": [],
                "production_eligible": False,
                "recovery_eligible": False,
                "canonical_status": "PAIN_ALTERNATIVE_TARGET_REVIEWED",
                "canonical_decision_code": "SEPARATE_EXERCISE_PAIN_SAFE_VARIANT",
                "canonical_decision_source": DECISION_CODE,
                "canonical_decision_note_ko": (
                    "통증 Alternative target이면서 일반 운동 풀에도 포함한다."
                ),
                "variant_relation_status_code": "NOT_APPLICABLE",
                "variant_materialization_status_code": "NOT_APPLICABLE",
                "safety_mapping_status_code": "DOMAIN_APPROVED_ALTERNATIVE_RULE",
                "safety_mapping_source_representative_exercise_id": "",
                "safety_rule_binding_status_code": "ALTERNATIVE_RULE_RETAINED",
                "fitt_mapping_status_code": "REVIEW_REQUIRED",
                "fitt_mapping_source_representative_exercise_id": "",
                "fitt_template_ids_by_experience": {},
                "fitt_allowed_experience_level_codes": [],
                "alternative_only": True,
                "general_pool_included": True,
                "general_pool_inclusion_reason_code": "PAIN_ALTERNATIVE_TARGET_ALSO_GENERAL_POOL",
                "alternative_relation_code": "PAIN_AREA_NO_LOAD_SAFE_VARIANT",
                "alternative_source_base_exercise_id": str(base["exercise_id"]),
                "alternative_source_base_stable_code": base_code,
                "base_exercise_id": str(base["exercise_id"]),
                "base_exercise_stable_code": base_code,
                # Pain area and NRS conditions are stored on the directed
                # exercise_alternatives relation, not on the catalog row.
                "pain_discomfort_area_code": None,
                "pain_area_load_guard_codes": [
                    "NO_PAIN_AREA_WEIGHT_BEARING",
                    "NO_PAIN_AREA_GRIP",
                    "NO_PAIN_AREA_BRACING",
                ],
                "fixed_posture_code": "REVIEWED_NO_LOAD_POSTURE",
                "fixed_support_code": "REVIEWED_NO_LOAD_SUPPORT",
                "stop_guard_code": "STOP_IF_DISCOMFORT_INCREASES",
                "original_posture_instructions_replaced": True,
                "alternative_policy_version": "discomfort-alternative-concern-resolution-v2.0.2-v1.0.0",
                "user_review_decision_code": DECISION_CODE,
                "user_review_status": "COMPLETED",
                "restored_from_prune_report": True,
            }
        )
        existing_ids.add(exercise_id)
    return restored


def filter_jsonl(path: Path, keep_ids: set[str], keep_codes: set[str]) -> int:
    rows = [
        normalize_reference_row(row)
        for row in read_jsonl(path)
        if row.get("materialization_status_code") != "NOT_MATERIALIZED_REVIEW_REQUIRED"
        and row_survives(row, keep_ids, keep_codes)
    ]
    write_jsonl(path, rows)
    return len(rows)


def filter_csv(path: Path, keep_ids: set[str], keep_codes: set[str]) -> int:
    rows = [normalize_reference_row(row) for row in read_csv(path) if row_survives(row, keep_ids, keep_codes)]
    write_csv(path, rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-dir", type=Path, default=FINAL)
    args = parser.parse_args()
    final = args.final_dir
    catalog_path = final / "catalog/exercises.jsonl"
    original = read_jsonl(catalog_path)
    base_rows = [row for row in original if not row.get("alternative_only")]
    safe_rows = [row for row in original if row.get("alternative_only")]
    base_rows.extend(restore_allowed_base_records(original, final))
    base_rows.extend(restore_legacy_alternative_targets(original, final))
    kept_base = [row for row in base_rows if keep_base(row)]
    kept_base_ids = {str(row["exercise_id"]) for row in kept_base}
    restored_safe = restore_allowed_safe_variants(original, kept_base, final)
    safe_rows.extend(restored_safe)
    kept_safe = [
        row
        for row in safe_rows
        if str(
            row.get("base_exercise_id")
            or row.get("alternative_source_base_exercise_id")
            or ""
        )
        in kept_base_ids
        or is_stretch(row)
    ]
    catalog = [normalize_catalog_row(row) for row in kept_base + kept_safe]
    catalog.sort(key=lambda row: str(row["exercise_id"]))
    keep_ids = {str(row["exercise_id"]) for row in catalog}
    keep_codes = {str(row["stable_code"]) for row in catalog}
    write_jsonl(catalog_path, catalog)
    write_csv(final / "audit/catalog/exercises.csv", catalog)
    write_jsonl(final / "audit/runtime/catalog.jsonl", catalog)

    jsonl_names = (
        "runtime/safety_rules.jsonl",
        "prescriptions/prescription_profiles.jsonl",
        "prescriptions/goal_tag_links.jsonl",
        "audit/reference_binding_status_v2_0_2.jsonl",
        "audit/variant_relationship_review_v2_0_2.jsonl",
        "audit/family_representative_mapping_v2_0_2.jsonl",
        "audit/variant_safety_fitt_mapping_v2_0_2.jsonl",
        "audit/integrity/variant_safety_fitt_review_batch_v2_0_2.jsonl",
    )
    for name in jsonl_names:
        path = final / name
        if path.exists():
            filter_jsonl(path, keep_ids, keep_codes)
    safe_variant_path = final / "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl"
    if safe_variant_path.exists():
        safe_source_rows = read_jsonl(safe_variant_path)
        safe_source_ids = {str(row.get("exercise_id") or "") for row in safe_source_rows}
        safe_source_rows.extend(
            row for row in restored_safe if str(row.get("exercise_id") or "") not in safe_source_ids
        )
        safe_kept = [
            normalize_reference_row(row)
            for row in safe_source_rows
            if str(row.get("exercise_id") or "") in keep_ids
        ]
        write_jsonl(safe_variant_path, safe_kept)
    for path in sorted((final / "audit/alternatives").glob("*.jsonl")):
        if path == safe_variant_path:
            continue
        filter_jsonl(path, keep_ids, keep_codes)
    for path in sorted((final / "audit/alternatives").glob("*.csv")):
        filter_csv(path, keep_ids, keep_codes)
    for path in (final / "audit/context").glob("*.jsonl"):
        filter_jsonl(path, keep_ids, keep_codes)
    for path in (final / "audit/context").glob("*.csv"):
        filter_csv(path, keep_ids, keep_codes)

    media_path = final / "media/media_assets_v2_0_2.csv"
    if media_path.exists():
        filter_csv(media_path, keep_ids, keep_codes)
    review_path = final / "audit/integrity/review_result_input_v2_0_2.csv"
    if review_path.exists():
        filter_csv(review_path, keep_ids, keep_codes)
    variant_review_csv = final / "audit/integrity/variant_safety_fitt_review_batch_v2_0_2.csv"
    if variant_review_csv.exists():
        filter_csv(variant_review_csv, keep_ids, keep_codes)

    registry_path = final / "audit/stable_code_registry_v2.json"
    registry = read_json(registry_path)
    registry["records"] = [row for row in registry.get("records", []) if str(row.get("exercise_id")) in keep_ids or str(row.get("stable_code")) in keep_codes]
    registry_codes = {str(row.get("stable_code") or "") for row in registry["records"]}
    for row in catalog:
        stable_code = str(row.get("stable_code") or "")
        if stable_code in registry_codes:
            continue
        registry["records"].append(
            {
                "decision_code": row.get("canonical_decision_code", DECISION_CODE),
                "decision_source": row.get("canonical_decision_source", "USER_DIRECT_REVIEW"),
                "exercise_id": row.get("exercise_id", ""),
                "family_code": row.get("family_code", ""),
                "name_en": row.get("name_en", ""),
                "name_ko": row.get("name_ko", ""),
                "record_type": row.get("record_type", ""),
                "representative_exercise_id": row.get("representative_exercise_id", ""),
                "source_identity": row.get("source_identity", ""),
                "source_keys": [row.get("source_key")] if row.get("source_key") else [],
                "source_track": row.get("source_track", ""),
                "stable_code": stable_code,
                "status": "ACTIVE_CATALOG_RECORD",
            }
        )
        registry_codes.add(stable_code)
    registry["records"] = sorted(registry["records"], key=lambda row: str(row.get("stable_code") or ""))
    registry["active_stable_code_count"] = len(registry["records"])
    registry["stable_code_count"] = len(registry["records"])
    registry["catalog_version_code"] = CATALOG_VERSION
    registry["registry_version"] = DECISION_CODE
    write_json(registry_path, registry)

    manifest_path = final / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["catalog_version_code"] = CATALOG_VERSION
    manifest["integrated_catalog_exercise_count"] = len(catalog)
    manifest["status"] = "USER_REVIEWED_CATALOG_PRUNED"
    manifest["production_eligible"] = False
    manifest["user_review"] = {
        "decision_code": DECISION_CODE,
        "unmentioned_items": "COMPLETED",
        "pain_safety_representation": "ALTERNATIVE_AND_GENERAL_POOL",
        "equipment_or_execution_representation": "VARIANT",
    }
    write_json(manifest_path, manifest)

    variant_report_path = final / "audit/variant_integrity_report_v2_0_2.json"
    if variant_report_path.exists():
        variant_report = read_json(variant_report_path)
        variant_report["status"] = "USER_REVIEWED_CATALOG_PRUNED"
        variant_report["catalog_version_code"] = CATALOG_VERSION
        variant_report["production_eligible"] = False
        variant_report["counts"] = {
            "representative_exercise_count": sum(row["record_type"] == "REPRESENTATIVE" for row in catalog),
            "primary_variant_count": sum(row.get("variant_type_code") == "PRIMARY_VARIANT" for row in catalog),
            "secondary_variant_count": sum(row.get("variant_type_code") == "SECONDARY_VARIANT" for row in catalog),
            "separate_exercise_count": sum(row["record_type"] == "SEPARATE_EXERCISE" for row in catalog),
            "variant_record_count": sum(row["record_type"] == "VARIANT" for row in catalog),
            "integrated_catalog_exercise_count": len(catalog),
        }
        write_json(variant_report_path, variant_report)

    deleted = [row for row in original if str(row.get("exercise_id")) not in keep_ids]
    restored_legacy_targets = [
        row
        for row in catalog
        if row.get("general_pool_inclusion_reason_code")
        == "LEGACY_ALTERNATIVE_TARGET_RESTORED"
    ]
    report = {
        "schema_version": "exercise-catalog-v2.0.2-user-prune-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "decision_code": DECISION_CODE,
        "record_type_counts": dict(sorted(Counter(row["record_type"] for row in catalog).items())),
        "kept_record_count": len(catalog),
        "deleted_record_count": len(deleted),
        "kept_base_record_count": len(kept_base),
        "kept_pain_alternative_record_count": sum(bool(row.get("alternative_only")) for row in catalog),
        "general_pool_included_record_count": sum(
            bool(row.get("general_pool_included")) for row in catalog
        ),
        "restored_legacy_alternative_target_count": len(restored_legacy_targets),
        "restored_legacy_alternative_target_records": [
            {
                "exercise_id": row.get("exercise_id"),
                "stable_code": row.get("stable_code"),
                "name_ko": clean_name(row.get("name_ko")),
            }
            for row in restored_legacy_targets
        ],
        "deleted_records": [
            {"exercise_id": row.get("exercise_id"), "stable_code": row.get("stable_code"), "name_ko": clean_name(row.get("name_ko"))}
            for row in deleted
        ],
        "classification_rule": {
            "pain_safety": "ALTERNATIVE_TARGET_AND_GENERAL_POOL",
            "legacy_alternative_target_restore": "GENERAL_POOL_REPRESENTATIVE",
            "equipment_or_execution_change": "PRIMARY_OR_SECONDARY_VARIANT",
            "unmentioned_review": "COMPLETED",
            "user_visible_name": "PARENTHESES_REMOVED_EXCEPT_EXPLICIT_ALIAS",
        },
    }
    write_json(final / "audit/integrity/user_catalog_prune_report_v2_0_2.json", report)
    auto_report_path = final / "audit/integrity/auto_reference_repair_report_v2_0_2.json"
    if auto_report_path.exists():
        auto_report = read_json(auto_report_path)
        auto_report["catalog"]["integrated_record_count"] = len(catalog)
        auto_report["catalog"]["safe_variant_integrated_count"] = len(kept_safe)
        auto_report["catalog"]["record_type_counts"] = dict(
            sorted(Counter(row["record_type"] for row in catalog).items())
        )
        auto_report["explicit_review_state"]["binding_rows"] = len(catalog)
        auto_report["explicit_review_state"]["review_input_rows"] = len(catalog)
        auto_report["reference_repair_after_user_prune"] = {
            "decision_code": DECISION_CODE,
            "deleted_record_count": len(deleted),
        }
        write_json(auto_report_path, auto_report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
