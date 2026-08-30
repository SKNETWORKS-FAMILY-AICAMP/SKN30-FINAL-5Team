"""Review and rebuild v2.0.2 Alternative relationships as discomfort-only data.

The v2.0.2 catalog already has independent Variant and HOME/GYM Context
Default artifacts.  This generator therefore treats every legacy relationship
as an input to review, not as an instruction to create a new relation:

* only ``DISCOMFORT`` can be retained as an Alternative;
* ``EQUIPMENT``, ``LOCATION`` and ``DIFFICULTY`` are dispositioned outside the
  Alternative set;
* a retained relation must show that the source loads the reported area, the
  target does not include that area, and the target is not harder;
* a target that retains the reported discomfort area is removed even for
  ``NRS_1_3``; mild pain is not permission to repeat the same local load;
* unresolved or unsafe-looking discomfort candidates stay out of the
  normalized output and are emitted to a review queue.

The generator is deliberately production-ineligible.  It preserves the
legacy relation identity and evidence fields so a domain reviewer can replay
each decision against the v2.0.2-final catalog.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / (
    "generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/"
    "catalog/exercises.jsonl"
)
DEFAULT_LEGACY = ROOT / "generated/exercise-catalog-v2.0.2-draft/alternatives/alternatives.jsonl"
DEFAULT_MAPPING = ROOT / "normalized/v2_discomfort_alternative_mapping.csv"
DEFAULT_STABLE_MIGRATION = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/audit/alias_migration_v2_0_2.csv"
)
DEFAULT_CONSOLIDATION = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/audit/legacy_consolidation_mapping_v2_final.csv"
)
DEFAULT_VARIANTS = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/audit/variant_relationship_review_v2_0_2.csv"
)
DEFAULT_NECK_CANDIDATES = ROOT / "normalized/neck_discomfort_alternative_candidates_v2_0_2.json"
DEFAULT_OUTPUT = ROOT / "generated/exercise-catalog-v2.0.2-final/audit/alternatives"

POLICY_VERSION = "exercise-alternative-policy-v2.0.2-v1.0.0"
REVIEWED_AT = "2026-08-28T00:00:00+09:00"
PRODUCTION_ELIGIBLE = False
REVIEW_STATUS = "REVIEW_REQUIRED"

DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}
SUPPORTED_BANDS = {
    "NRS_1_3": (1, 3, "MILD", "LOAD_REDUCED"),
    "NRS_4_6": (4, 6, "MODERATE", "SKIP_AFFECTED_AREA"),
}
ALTERNATIVE_REASON = "DISCOMFORT"
NECK_UNSAFE_TARGET_PATTERNS = {"CORE_BRACE"}
LOWER_BACK_GUARDS = [
    "NEUTRAL_SPINE_REQUIRED",
    "NO_CORE_OR_HIP_DOMINANT_TARGET_AT_RUNTIME",
    "REDUCED_VOLUME_AND_LOAD",
    "STOP_IF_LOWER_BACK_DISCOMFORT_INCREASES",
]
NECK_GUARDS = [
    "NEUTRAL_HEAD_AND_NECK_REQUIRED",
    "DISTAL_LOW_LOAD_TARGET_ONLY",
    "STOP_IF_NECK_DISCOMFORT_INCREASES",
]

REVIEW_FIELDS = [
    "review_record_id",
    "legacy_record_number",
    "legacy_relation_identity",
    "legacy_reason_code",
    "legacy_goal_preservation_code",
    "legacy_relation_type",
    "source_exercise_stable_code_legacy",
    "source_exercise_stable_code",
    "source_exercise_id",
    "source_record_type",
    "source_exercise_name_ko",
    "source_primary_movement_pattern_code",
    "source_primary_body_area_codes",
    "source_secondary_body_area_codes",
    "source_equipment_codes",
    "source_location_codes",
    "source_difficulty_code",
    "target_exercise_stable_code_legacy",
    "target_exercise_stable_code",
    "target_exercise_id",
    "target_record_type",
    "target_exercise_name_ko",
    "target_primary_movement_pattern_code",
    "target_primary_body_area_codes",
    "target_secondary_body_area_codes",
    "target_equipment_codes",
    "target_location_codes",
    "target_difficulty_code",
    "candidate_origin_code",
    "pain_discomfort_area_code",
    "condition_code",
    "pain_score_min",
    "pain_score_max",
    "severity_code",
    "service_action_code",
    "source_load_to_avoid_code",
    "source_load_to_avoid_detail",
    "source_load_pain_area_overlap",
    "target_load_reduction_basis_code",
    "target_pain_area_overlap",
    "target_difficulty_not_higher",
    "source_target_same_family",
    "source_target_same_movement_pattern",
    "variant_relation_overlap",
    "variant_type_code",
    "direction_code",
    "directionality_check_code",
    "decision",
    "decision_code",
    "reclassification_code",
    "review_reason_code",
    "review_reason_ko",
    "area_specific_safety_review_code",
    "area_specific_safety_guard_codes",
    "evidence_source",
    "evidence_reviewer",
    "evidence_reviewed_at",
    "legacy_review_method_code",
    "legacy_review_status_code",
    "legacy_source_catalog_version_code",
    "legacy_source_manifest_hash",
    "legacy_source_relation_key",
    "legacy_source_metadata",
    "decision_source_code",
    "decision_reviewer_code",
    "review_status_code",
    "production_eligible",
]

NORMALIZED_FIELDS = [
    "alternative_relation_id",
    "source_exercise_stable_code",
    "alternative_exercise_stable_code",
    "source_exercise_id",
    "alternative_exercise_id",
    "source_record_type",
    "alternative_record_type",
    "candidate_origin_code",
    "reason_code",
    "pain_discomfort_area_code",
    "condition_code",
    "pain_score_min",
    "pain_score_max",
    "severity_code",
    "service_action_code",
    "source_load_to_avoid_code",
    "source_load_to_avoid_detail",
    "target_load_reduction_basis_code",
    "source_primary_movement_pattern_code",
    "alternative_primary_movement_pattern_code",
    "source_primary_body_area_codes",
    "source_secondary_body_area_codes",
    "alternative_primary_body_area_codes",
    "alternative_secondary_body_area_codes",
    "source_load_pain_area_overlap",
    "target_pain_area_overlap",
    "target_difficulty_not_higher",
    "source_target_same_family",
    "source_target_same_movement_pattern",
    "variant_relation_overlap",
    "variant_type_code",
    "goal_preservation_code",
    "alternative_strategy_code",
    "allowed_equipment_codes",
    "allowed_location_codes",
    "difficulty_delta",
    "direction_code",
    "directionality_check_code",
    "legacy_relation_identity",
    "legacy_relation_identities",
    "legacy_source_relation_key",
    "legacy_source_relation_keys",
    "evidence_source",
    "evidence_reviewer",
    "evidence_reviewed_at",
    "decision_source_code",
    "decision_reviewer_code",
    "review_decision",
    "area_specific_safety_review_code",
    "area_specific_safety_guard_codes",
    "review_status_code",
    "production_eligible",
]

DISPOSITION_FIELDS = REVIEW_FIELDS


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
            rows.append(value)
    if not rows:
        raise ValueError(f"JSONL input is empty: {path}")
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV input is empty: {path}")
    return rows


def read_json(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not value:
        raise ValueError(f"JSON input is empty: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def parse_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def parse_relation_ids(relation_key: str) -> list[str]:
    return re.findall(r"REX-\d+", relation_key)


def catalog_indexes(
    path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = read_jsonl(path)
    by_stable: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        stable = str(row.get("stable_code", "")).strip()
        exercise_id = str(row.get("exercise_id", "")).strip()
        if not stable or not exercise_id:
            raise ValueError("final catalog rows require stable_code and exercise_id")
        if stable in by_stable or exercise_id in by_id:
            raise ValueError(f"final catalog identity is duplicated: {stable}/{exercise_id}")
        by_stable[stable] = row
        by_id[exercise_id] = row
    return by_stable, by_id


def stable_migrations(path: Path, final_by_stable: dict[str, dict[str, Any]]) -> dict[str, str]:
    migrations: dict[str, str] = {}
    if not path.exists():
        return migrations
    for row in read_csv(path):
        if row.get("field_name") != "stable_code":
            continue
        before = str(row.get("stable_code_before", "")).strip()
        after = str(row.get("stable_code_after", "")).strip()
        if before and after and after in final_by_stable:
            migrations[before] = after
    return migrations


def consolidation_by_source_id(
    path: Path, final_by_id: dict[str, dict[str, Any]]
) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    if not path.exists():
        return {}
    for row in read_csv(path):
        source_id = str(row.get("source_record_id", "")).strip()
        final_id = str(row.get("final_representative_exercise_id", "")).strip()
        if source_id and final_id in final_by_id:
            candidates.setdefault(source_id, set()).add(final_id)
    return {
        source_id: next(iter(final_ids))
        for source_id, final_ids in candidates.items()
        if len(final_ids) == 1
    }


def v1_alias_indexes(
    final_rows: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_v1_id: dict[str, dict[str, Any]] = {}
    for row in final_rows.values():
        for value in row.get("v1_exercise_ids", []):
            by_v1_id[str(value)] = row
    return by_v1_id


def resolve_exercise(
    legacy_row: dict[str, Any],
    side: str,
    final_by_stable: dict[str, dict[str, Any]],
    final_by_id: dict[str, dict[str, Any]],
    migrations: dict[str, str],
    consolidated_ids: dict[str, str],
    by_v1_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    legacy_field = (
        "source_exercise_stable_code" if side == "source" else "alternative_exercise_stable_code"
    )
    legacy_code = str(legacy_row.get(legacy_field, "")).strip()
    if legacy_code in final_by_stable:
        return final_by_stable[legacy_code]
    migrated_code = migrations.get(legacy_code)
    if migrated_code in final_by_stable:
        return final_by_stable[migrated_code]

    metadata = legacy_row.get("source_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    relation_key = str(metadata.get("source_relation_key", ""))
    relation_ids = parse_relation_ids(relation_key)
    index = 0 if side == "source" else 1
    if len(relation_ids) > index:
        source_id = relation_ids[index]
        final_id = consolidated_ids.get(source_id, source_id)
        if final_id in final_by_id:
            return final_by_id[final_id]

    relation_key_value = str(metadata.get("source_relation_key", ""))
    if relation_key_value.startswith("mapping:") and len(relation_ids) > index:
        return final_by_id.get(relation_ids[index])

    # This fallback is only for legacy NEX references.  Direct stable-code
    # matches remain preferred because one legacy stable code can have several
    # promoted separate exercises behind it.
    legacy_relation = str(metadata.get("source_relation_key", ""))
    nex_ids = re.findall(r"NEX-\d+", legacy_relation)
    if len(nex_ids) > index:
        return by_v1_id.get(nex_ids[index])
    return None


def load_variant_pairs(path: Path) -> dict[tuple[str, str], str]:
    pairs: dict[tuple[str, str], str] = {}
    if not path.exists():
        return pairs
    for row in read_csv(path):
        variant = str(row.get("variant_stable_code", "")).strip()
        representative = str(row.get("representative_stable_code", "")).strip()
        variant_type = str(row.get("variant_type_code", "")).strip()
        if not variant or not representative or not variant_type:
            continue
        pairs[(variant, representative)] = variant_type
        pairs[(representative, variant)] = variant_type
    return pairs


def evidence_indexes(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = read_csv(path)
    return {
        str(row.get("source_relation_key", "")).strip(): row
        for row in rows
        if str(row.get("source_relation_key", "")).strip()
    }


def load_neck_candidates(path: Path) -> list[dict[str, Any]]:
    value = read_json(path)
    if not isinstance(value, list):
        raise ValueError(f"neck candidate input must be a JSON array: {path}")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in value:
        if not isinstance(candidate, dict):
            raise ValueError(f"neck candidate rows must be objects: {path}")
        candidate_id = str(candidate.get("candidate_relation_id", "")).strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError(f"neck candidate identity is missing or duplicated: {candidate_id}")
        seen.add(candidate_id)
        candidates.append(candidate)
    return candidates


def exercise_areas(row: dict[str, Any] | None) -> set[str]:
    if row is None:
        return set()
    return {
        str(value)
        for field in ("primary_body_area_codes", "secondary_body_area_codes")
        for value in row.get(field, [])
    }


def excluded_exercise(row: dict[str, Any] | None) -> bool:
    if row is None:
        return True
    record_type = str(row.get("record_type", ""))
    canonical_status = str(row.get("canonical_status", ""))
    return record_type in {"EXCLUDED", "RETIRED"} or canonical_status.startswith("RETIRED")


def legacy_relation_identity(row: dict[str, Any], record_number: int) -> str:
    metadata = row.get("source_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    relation_key = str(metadata.get("source_relation_key", "")).strip()
    if not relation_key:
        relation_key = f"legacy-line:{record_number}"
    source_hash = str(row.get("source_manifest_hash", "")).strip()
    catalog = str(row.get("source_catalog_version_code", "")).strip()
    return "|".join((catalog, source_hash, relation_key))


def condition_fields(
    row: dict[str, Any], evidence: dict[str, str]
) -> tuple[str, str, int | None, int | None, str, str]:
    metadata = row.get("source_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    area = str(metadata.get("body_area_code") or evidence.get("body_area_code") or "").strip()
    band = str(metadata.get("score_band_code") or evidence.get("score_band_code") or "").strip()
    minimum: int | None
    maximum: int | None
    if band in SUPPORTED_BANDS:
        minimum, maximum, severity, action = SUPPORTED_BANDS[band]
    else:
        minimum = parse_int(evidence.get("pain_score_min"))
        maximum = parse_int(evidence.get("pain_score_max"))
        severity = ""
        action = ""
    return area, band, minimum, maximum, severity, action


def decision_for(
    row: dict[str, Any],
    source: dict[str, Any] | None,
    target: dict[str, Any] | None,
    evidence: dict[str, str],
    variant_pairs: dict[tuple[str, str], str],
) -> dict[str, Any]:
    reason = str(row.get("reason_code", "")).strip()
    source_code = str(source.get("stable_code", "")) if source else ""
    target_code = str(target.get("stable_code", "")) if target else ""
    source_areas = exercise_areas(source)
    target_areas = exercise_areas(target)
    area, band, score_min, score_max, severity, action = condition_fields(row, evidence)
    source_overlap = bool(source and area and area in source_areas)
    target_overlap = bool(target and area and area in target_areas)
    same_family = bool(source and target and source.get("family_code") == target.get("family_code"))
    same_pattern = bool(
        source
        and target
        and source.get("primary_movement_pattern_code")
        == target.get("primary_movement_pattern_code")
    )
    variant_type = variant_pairs.get((source_code, target_code), "")
    variant_overlap = bool(variant_type)
    source_rank = DIFFICULTY_RANK.get(str(source.get("difficulty_code", ""))) if source else None
    target_rank = DIFFICULTY_RANK.get(str(target.get("difficulty_code", ""))) if target else None
    target_not_harder = bool(
        source_rank is not None and target_rank is not None and target_rank <= source_rank
    )

    decision = "REVIEW_REQUIRED"
    decision_code = "PENDING_REVIEW"
    reclassification = ""
    reason_code = ""
    reason_ko = ""
    directionality = "NOT_APPLICABLE"
    area_safety_review = ""
    area_safety_guards: list[str] = []

    if reason != ALTERNATIVE_REASON:
        decision = "REMOVE_RECLASSIFY"
        decision_code = "REMOVE_FROM_ALTERNATIVE_SET"
        reclassification = {
            "EQUIPMENT": "RECLASSIFY_VARIANT",
            "LOCATION": "RECLASSIFY_CONTEXT_DEFAULT",
            "DIFFICULTY": "RECLASSIFY_DIFFICULTY_VARIANT",
        }.get(reason, "RECLASSIFY_NON_DISCOMFORT_RELATION")
        reason_code = "NO_DISCOMFORT_CONDITION"
        reason_ko = (
            "통증·불편 조건이 없는 관계이므로 Alternative에서 제거하고 다른 관계 체계로 보낸다."
        )
    elif not area or not band or score_min is None or score_max is None:
        reason_code = "MISSING_PAIN_DISCOMFORT_CONDITION"
        reason_ko = "통증 부위 또는 적용 점수 구간이 없어 Alternative 조건을 재현할 수 없다."
    elif source is None or target is None:
        reason_code = "MISSING_EXERCISE_REFERENCE"
        reason_ko = "v2.0.2-final exercise stable code/id로 해소되지 않아 참조를 확정할 수 없다."
    elif excluded_exercise(source) or excluded_exercise(target):
        reason_code = "EXCLUDED_EXERCISE_REFERENCE"
        reason_ko = (
            "제외 또는 retired exercise 참조가 포함되어 운영 대상 Alternative로 확정할 수 없다."
        )
    elif source_code == target_code:
        decision = "REMOVE_RECLASSIFY"
        decision_code = "REMOVE_SELF_REFERENCE"
        reclassification = "REMOVE_SELF_REFERENCE"
        reason_code = "SELF_REFERENCE_AFTER_STABLE_CODE_MIGRATION"
        reason_ko = "stable code migration 이후 source와 target이 같은 exercise가 되어 제거한다."
    elif not source_overlap:
        reason_code = "SOURCE_DOES_NOT_LOAD_DISCOMFORT_AREA"
        reason_ko = "source가 보고된 불편 부위를 부하하는지 catalog 근거로 확인되지 않는다."
    elif band not in SUPPORTED_BANDS:
        reason_code = "UNSUPPORTED_SEVERITY_NO_ALTERNATIVE"
        reason_ko = "지원하지 않는 심각도 구간은 대체운동을 생성하지 않고 안전 검토로 남긴다."
    elif (variant_overlap or same_family) and target_overlap:
        decision = "REMOVE_RECLASSIFY"
        decision_code = "REMOVE_SIMPLE_VARIANT_DUPLICATE"
        reclassification = "RECLASSIFY_VARIANT_OR_EXERCISE_IDENTITY"
        reason_code = "SIMPLE_VARIANT_RELATION_DUPLICATE"
        reason_ko = (
            "통증 조건에 따른 부담 감소 근거보다 동일 family·"
            "Variant 관계가 우선 확인되어 재분류한다."
        )
    elif (
        area == "NECK"
        and target
        and str(target.get("primary_movement_pattern_code", "")) in NECK_UNSAFE_TARGET_PATTERNS
    ):
        decision = "REMOVE_RECLASSIFY"
        decision_code = "REMOVE_NECK_UNSAFE_TARGET"
        reclassification = "REMOVE_NECK_TARGET_SAFETY_UNCONFIRMED"
        reason_code = "NECK_TARGET_SAFETY_UNCONFIRMED"
        reason_ko = (
            "목 불편 조건에서 target의 목 부담 감소가 확인되지 않는 core/bracing 패턴이므로 "
            "Alternative에서 제거한다."
        )
    elif target_overlap:
        decision = "REMOVE_RECLASSIFY"
        decision_code = "REMOVE_UNSAFE_SAME_AREA_TARGET"
        reclassification = "REMOVE_TARGET_RETAINS_DISCOMFORT_AREA"
        reason_code = "TARGET_RETAINS_DISCOMFORT_AREA"
        reason_ko = (
            "NRS 점수가 1~3인 경미한 조건이어도 target이 보고된 불편 부위를 포함하므로 "
            "동일 부담·위험을 남길 수 있어 Alternative에서 삭제한다."
        )
    elif not target_not_harder:
        reason_code = "TARGET_DIFFICULTY_INCREASES"
        reason_ko = "target 난이도가 source보다 높거나 난이도 비교 근거가 부족하다."
    else:
        decision = "KEEP"
        decision_code = "RETAIN_DISCOMFORT_ALTERNATIVE"
        directionality = "PASS_SOURCE_LOADS_AREA_TARGET_EXCLUDES_AREA"
        if area == "NECK":
            area_safety_review = "NECK_DISTAL_TARGET_CONDITIONALLY_RETAINED"
            area_safety_guards = NECK_GUARDS.copy()
        elif area == "LOWER_BACK":
            area_safety_review = "LOWER_BACK_CONDITIONALLY_RETAINED"
            area_safety_guards = LOWER_BACK_GUARDS.copy()

    if decision == "REVIEW_REQUIRED" and directionality == "NOT_APPLICABLE":
        if source_overlap and not target_overlap and target_not_harder:
            directionality = "PASS_BUT_REVIEW_REASON_REMAINS"
        else:
            directionality = "FAIL_OR_UNCONFIRMED"

    metadata = row.get("source_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    source_detail = {
        "discomfort_area_code": area,
        "source_primary_movement_pattern_code": source.get("primary_movement_pattern_code", "")
        if source
        else "",
        "source_body_area_codes": sorted(source_areas),
        "source_equipment_codes": source.get("equipment_codes", []) if source else [],
    }
    return {
        "pain_discomfort_area_code": area,
        "condition_code": band,
        "pain_score_min": score_min,
        "pain_score_max": score_max,
        "severity_code": severity,
        "service_action_code": action,
        "source_load_to_avoid_code": "PAIN_AREA_INVOLVEMENT_IN_SOURCE_MOVEMENT",
        "source_load_to_avoid_detail": source_detail,
        "source_load_pain_area_overlap": source_overlap,
        "target_load_reduction_basis_code": (
            "TARGET_EXCLUDES_DISCOMFORT_AREA" if not target_overlap else "UNCONFIRMED"
        ),
        "target_pain_area_overlap": target_overlap,
        "target_difficulty_not_higher": target_not_harder,
        "source_target_same_family": same_family,
        "source_target_same_movement_pattern": same_pattern,
        "variant_relation_overlap": variant_overlap,
        "variant_type_code": variant_type,
        "direction_code": "A_TO_B",
        "directionality_check_code": directionality,
        "decision": decision,
        "decision_code": decision_code,
        "reclassification_code": reclassification,
        "review_reason_code": reason_code,
        "review_reason_ko": reason_ko,
        "area_specific_safety_review_code": area_safety_review,
        "area_specific_safety_guard_codes": area_safety_guards,
        "legacy_reason_code": reason,
        "legacy_goal_preservation_code": str(row.get("goal_preservation_code", "")),
        "legacy_relation_type": str(metadata.get("legacy_relationship_type", "")),
        "source_primary_movement_pattern_code": str(
            source.get("primary_movement_pattern_code", "") if source else ""
        ),
        "source_primary_body_area_codes": source.get("primary_body_area_codes", [])
        if source
        else [],
        "source_secondary_body_area_codes": source.get("secondary_body_area_codes", [])
        if source
        else [],
        "source_equipment_codes": source.get("equipment_codes", []) if source else [],
        "source_location_codes": source.get("location_codes", []) if source else [],
        "source_difficulty_code": str(source.get("difficulty_code", "") if source else ""),
        "target_primary_movement_pattern_code": str(
            target.get("primary_movement_pattern_code", "") if target else ""
        ),
        "target_primary_body_area_codes": target.get("primary_body_area_codes", [])
        if target
        else [],
        "target_secondary_body_area_codes": target.get("secondary_body_area_codes", [])
        if target
        else [],
        "target_equipment_codes": target.get("equipment_codes", []) if target else [],
        "target_location_codes": target.get("location_codes", []) if target else [],
        "target_difficulty_code": str(target.get("difficulty_code", "") if target else ""),
    }


def review_row(
    row: dict[str, Any],
    record_number: int,
    source: dict[str, Any] | None,
    target: dict[str, Any] | None,
    evidence: dict[str, str],
    variant_pairs: dict[tuple[str, str], str],
) -> dict[str, Any]:
    metadata = row.get("source_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    result = decision_for(row, source, target, evidence, variant_pairs)
    identity = legacy_relation_identity(row, record_number)
    relation_key = str(metadata.get("source_relation_key", ""))
    evidence_source = str(evidence.get("evidence_source", "") or metadata.get("source_path", ""))
    evidence_reviewer = str(evidence.get("reviewer", "") or row.get("review_method_code", ""))
    evidence_reviewed_at = str(evidence.get("reviewed_at", "") or row.get("created_at", ""))
    candidate_origin = str(metadata.get("candidate_origin_code", "LEGACY_ALTERNATIVE"))
    review_prefix = (
        "ALT-SUPPLEMENTAL-" if candidate_origin != "LEGACY_ALTERNATIVE" else "ALT-LEGACY-"
    )
    review_id = review_prefix + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return {
        **result,
        "review_record_id": review_id,
        "legacy_record_number": record_number,
        "legacy_relation_identity": identity,
        "source_exercise_stable_code_legacy": str(row.get("source_exercise_stable_code", "")),
        "source_exercise_stable_code": str(source.get("stable_code", "")) if source else "",
        "source_exercise_id": str(source.get("exercise_id", "")) if source else "",
        "source_record_type": str(source.get("record_type", "")) if source else "",
        "source_exercise_name_ko": str(source.get("display_name_ko", "")) if source else "",
        "target_exercise_stable_code_legacy": str(row.get("alternative_exercise_stable_code", "")),
        "target_exercise_stable_code": str(target.get("stable_code", "")) if target else "",
        "target_exercise_id": str(target.get("exercise_id", "")) if target else "",
        "target_record_type": str(target.get("record_type", "")) if target else "",
        "target_exercise_name_ko": str(target.get("display_name_ko", "")) if target else "",
        "candidate_origin_code": candidate_origin,
        "legacy_source_catalog_version_code": str(row.get("source_catalog_version_code", "")),
        "legacy_source_manifest_hash": str(row.get("source_manifest_hash", "")),
        "legacy_source_relation_key": relation_key,
        "legacy_source_metadata": metadata,
        "evidence_source": evidence_source,
        "evidence_reviewer": evidence_reviewer,
        "evidence_reviewed_at": evidence_reviewed_at,
        "legacy_review_method_code": str(row.get("review_method_code", "")),
        "legacy_review_status_code": str(row.get("review_status_code", "")),
        "decision_source_code": "DETERMINISTIC_POLICY_V2_0_2",
        "decision_reviewer_code": "DATA_REVIEW_PIPELINE",
        "review_status_code": REVIEW_STATUS,
        "production_eligible": PRODUCTION_ELIGIBLE,
    }


def supplemental_legacy_row(
    candidate: dict[str, Any],
    catalog_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    relation_key = str(candidate["candidate_relation_id"])
    return {
        "source_exercise_stable_code": str(candidate["source_exercise_stable_code"]),
        "alternative_exercise_stable_code": str(candidate["target_exercise_stable_code"]),
        "reason_code": ALTERNATIVE_REASON,
        "goal_preservation_code": str(candidate.get("goal_preservation_code", "ACTIVE_RECOVERY")),
        "source_catalog_version_code": "exercise-catalog-v2.0.2-final",
        "source_manifest_hash": sha256_file(candidate_path),
        "review_method_code": "DETERMINISTIC_POLICY_REVIEW",
        "review_status_code": REVIEW_STATUS,
        "created_at": str(candidate.get("reviewed_at", REVIEWED_AT)),
        "source_metadata": {
            "source_relation_key": relation_key,
            "body_area_code": str(candidate["pain_discomfort_area_code"]),
            "score_band_code": str(candidate["condition_code"]),
            "legacy_relationship_type": "SUPPLEMENTAL_DISCOMFORT_CANDIDATE",
            "candidate_origin_code": "SUPPLEMENTAL_NECK",
            "source_path": str(candidate_path.relative_to(ROOT.parent)),
            "catalog_path": str(catalog_path.relative_to(ROOT.parent)),
        },
    }


def normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    source_detail = row.get("source_load_to_avoid_detail", {})
    return {
        "alternative_relation_id": row["review_record_id"],
        "source_exercise_stable_code": row["source_exercise_stable_code"],
        "alternative_exercise_stable_code": row["target_exercise_stable_code"],
        "source_exercise_id": row["source_exercise_id"],
        "alternative_exercise_id": row["target_exercise_id"],
        "source_record_type": row["source_record_type"],
        "alternative_record_type": row["target_record_type"],
        "candidate_origin_code": row["candidate_origin_code"],
        "reason_code": ALTERNATIVE_REASON,
        "pain_discomfort_area_code": row["pain_discomfort_area_code"],
        "condition_code": row["condition_code"],
        "pain_score_min": row["pain_score_min"],
        "pain_score_max": row["pain_score_max"],
        "severity_code": row["severity_code"],
        "service_action_code": row["service_action_code"],
        "source_load_to_avoid_code": row["source_load_to_avoid_code"],
        "source_load_to_avoid_detail": source_detail,
        "target_load_reduction_basis_code": row["target_load_reduction_basis_code"],
        "source_primary_movement_pattern_code": row["source_primary_movement_pattern_code"],
        "alternative_primary_movement_pattern_code": row["target_primary_movement_pattern_code"],
        "source_primary_body_area_codes": row["source_primary_body_area_codes"],
        "source_secondary_body_area_codes": row["source_secondary_body_area_codes"],
        "alternative_primary_body_area_codes": row["target_primary_body_area_codes"],
        "alternative_secondary_body_area_codes": row["target_secondary_body_area_codes"],
        "source_load_pain_area_overlap": row["source_load_pain_area_overlap"],
        "target_pain_area_overlap": row["target_pain_area_overlap"],
        "target_difficulty_not_higher": row["target_difficulty_not_higher"],
        "source_target_same_family": row["source_target_same_family"],
        "source_target_same_movement_pattern": row["source_target_same_movement_pattern"],
        "variant_relation_overlap": row["variant_relation_overlap"],
        "variant_type_code": row["variant_type_code"],
        "goal_preservation_code": row["legacy_goal_preservation_code"],
        "alternative_strategy_code": (
            "MILD_AREA_EXCLUDED_LOWER_BURDEN"
            if row["condition_code"] == "NRS_1_3"
            else "MODERATE_AFFECTED_AREA_EXCLUDED_ACTIVE_RECOVERY"
        ),
        "allowed_equipment_codes": row["target_equipment_codes"],
        "allowed_location_codes": row["target_location_codes"],
        "difficulty_delta": (
            DIFFICULTY_RANK.get(row["target_difficulty_code"], 0)
            - DIFFICULTY_RANK.get(row["source_difficulty_code"], 0)
            if row["target_difficulty_code"] and row["source_difficulty_code"]
            else ""
        ),
        "direction_code": row["direction_code"],
        "directionality_check_code": row["directionality_check_code"],
        "legacy_relation_identity": row["legacy_relation_identity"],
        "legacy_relation_identities": [row["legacy_relation_identity"]],
        "legacy_source_relation_key": row["legacy_source_relation_key"],
        "legacy_source_relation_keys": [row["legacy_source_relation_key"]],
        "evidence_source": row["evidence_source"],
        "evidence_reviewer": row["evidence_reviewer"],
        "evidence_reviewed_at": row["evidence_reviewed_at"],
        "decision_source_code": row["decision_source_code"],
        "decision_reviewer_code": row["decision_reviewer_code"],
        "review_decision": row["decision"],
        "review_status_code": row["review_status_code"],
        "area_specific_safety_review_code": row["area_specific_safety_review_code"],
        "area_specific_safety_guard_codes": row["area_specific_safety_guard_codes"],
        "production_eligible": row["production_eligible"],
    }


def integrity_report(
    review_rows: list[dict[str, Any]],
    normalized_rows: list[dict[str, Any]],
    normalized_legacy_count: int,
    neck_review_rows: list[dict[str, Any]],
    lower_back_review_rows: list[dict[str, Any]],
    final_by_stable: dict[str, dict[str, Any]],
    variant_pairs: dict[tuple[str, str], str],
    input_paths: dict[str, Path],
) -> dict[str, Any]:
    natural_keys = [
        (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
        for row in normalized_rows
    ]
    pair_keys = [
        (row["source_exercise_stable_code"], row["alternative_exercise_stable_code"])
        for row in normalized_rows
    ]
    natural_counts = Counter(natural_keys)
    pair_counts = Counter(pair_keys)
    condition_pair_keys = {
        (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
        for row in normalized_rows
    }
    reverse_pairs = (
        sum(
            1
            for source, target, area, condition in condition_pair_keys
            if (target, source, area, condition) in condition_pair_keys and source != target
        )
        // 2
    )
    missing_refs = sum(
        not row["source_exercise_stable_code"]
        or row["source_exercise_stable_code"] not in final_by_stable
        or not row["alternative_exercise_stable_code"]
        or row["alternative_exercise_stable_code"] not in final_by_stable
        for row in normalized_rows
    )
    excluded_refs = sum(
        excluded_exercise(final_by_stable.get(row["source_exercise_stable_code"]))
        or excluded_exercise(final_by_stable.get(row["alternative_exercise_stable_code"]))
        for row in normalized_rows
    )
    variant_overlaps = sum(
        (row["source_exercise_stable_code"], row["alternative_exercise_stable_code"])
        in variant_pairs
        for row in normalized_rows
    )
    secondary_variant = sum(
        row["variant_type_code"] == "SECONDARY_VARIANT" for row in normalized_rows
    )
    no_condition = sum(
        not row["pain_discomfort_area_code"] or not row["condition_code"] for row in normalized_rows
    )
    direction_errors = sum(
        row["direction_code"] != "A_TO_B"
        or row["directionality_check_code"] != "PASS_SOURCE_LOADS_AREA_TARGET_EXCLUDES_AREA"
        or row["source_load_pain_area_overlap"] is not True
        or row["target_pain_area_overlap"] is not False
        for row in normalized_rows
    )
    neck_unsafe_targets = sum(
        row["alternative_primary_movement_pattern_code"] in NECK_UNSAFE_TARGET_PATTERNS
        or bool(
            {"NECK", "SHOULDER"}
            & (
                set(row["alternative_primary_body_area_codes"])
                | set(row["alternative_secondary_body_area_codes"])
            )
        )
        for row in normalized_rows
        if row["pain_discomfort_area_code"] == "NECK"
    )
    lower_back_target_overlap = sum(
        bool(
            "LOWER_BACK"
            in set(row["target_primary_body_area_codes"])
            | set(row["target_secondary_body_area_codes"])
        )
        for row in lower_back_review_rows
    )
    counts = Counter(row["decision"] for row in review_rows)
    reason_counts = Counter(row["legacy_reason_code"] for row in review_rows)
    disposition_counts = Counter(
        row["reclassification_code"] or row["review_reason_code"]
        for row in review_rows
        if row["decision"] != "KEEP"
    )
    report = {
        "schema_version": "exercise-alternative-integrity-v2.0.2-v1",
        "policy_version": POLICY_VERSION,
        "reviewed_at": REVIEWED_AT,
        "status": "DRAFT_REVIEW_REQUIRED",
        "production_eligible": PRODUCTION_ELIGIBLE,
        "source": {
            name: {
                "path": str(path.relative_to(ROOT.parent)),
                "sha256": sha256_file(path),
            }
            for name, path in input_paths.items()
        },
        "counts": {
            "existing_alternative_count": len(review_rows),
            "legacy_reason_counts": dict(sorted(reason_counts.items())),
            "maintained_count": counts["KEEP"],
            "removed_or_reclassified_count": counts["REMOVE_RECLASSIFY"],
            "review_required_count": counts["REVIEW_REQUIRED"],
            "normalized_discomfort_alternative_count": len(normalized_rows),
            "normalized_legacy_discomfort_alternative_count": normalized_legacy_count,
            "supplemental_neck_candidate_count": sum(
                row["candidate_origin_code"] == "SUPPLEMENTAL_NECK" for row in neck_review_rows
            ),
            "supplemental_neck_maintained_count": sum(
                row["candidate_origin_code"] == "SUPPLEMENTAL_NECK" and row["decision"] == "KEEP"
                for row in neck_review_rows
            ),
            "collapsed_legacy_identity_count": counts["KEEP"] - normalized_legacy_count,
            "reclassification_or_review_reason_counts": dict(sorted(disposition_counts.items())),
            "neck_review_candidate_count": len(neck_review_rows),
            "neck_review_maintained_count": sum(
                row["decision"] == "KEEP" for row in neck_review_rows
            ),
            "neck_review_removed_or_reclassified_count": sum(
                row["decision"] == "REMOVE_RECLASSIFY" for row in neck_review_rows
            ),
            "lower_back_existing_relation_count": len(lower_back_review_rows),
            "lower_back_conditionally_retained_count": sum(
                row["area_specific_safety_review_code"] == "LOWER_BACK_CONDITIONALLY_RETAINED"
                for row in lower_back_review_rows
            ),
        },
        "natural_key": [
            "source_exercise_stable_code",
            "alternative_exercise_stable_code",
            "pain_discomfort_area_code",
            "condition_code",
        ],
        "invariants": {
            "no_self_reference": sum(source == target for source, target in pair_keys) == 0,
            "no_duplicate_natural_key": sum(
                value - 1 for value in natural_counts.values() if value > 1
            )
            == 0,
            "no_missing_exercise_reference": missing_refs == 0,
            "no_excluded_exercise_reference": excluded_refs == 0,
            "no_simple_variant_relation_in_alternatives": variant_overlaps == 0,
            "no_secondary_variant_as_alternative": secondary_variant == 0,
            "no_discomfort_without_condition": no_condition == 0,
            "no_directionality_error": direction_errors == 0,
            "no_reverse_direction_pair": reverse_pairs == 0,
            "no_unsafe_neck_target_in_normalized": neck_unsafe_targets == 0,
            "lower_back_targets_exclude_lower_back": lower_back_target_overlap == 0,
            "lower_back_safety_review_is_conditionally_retained": all(
                row["area_specific_safety_review_code"] == "LOWER_BACK_CONDITIONALLY_RETAINED"
                for row in lower_back_review_rows
            ),
            "normalized_reason_code_is_discomfort_only": all(
                row["reason_code"] == ALTERNATIVE_REASON for row in normalized_rows
            ),
            "all_normalized_rows_are_kept": all(
                row["review_decision"] == "KEEP" for row in normalized_rows
            ),
        },
        "integrity_metrics": {
            "self_reference_count": sum(source == target for source, target in pair_keys),
            "duplicate_natural_key_count": sum(
                value - 1 for value in natural_counts.values() if value > 1
            ),
            "cross_condition_same_source_target_pair_count": sum(
                value - 1 for value in pair_counts.values() if value > 1
            ),
            "missing_exercise_reference_count": missing_refs,
            "excluded_exercise_reference_count": excluded_refs,
            "variant_relation_overlap_count": variant_overlaps,
            "secondary_variant_alternative_count": secondary_variant,
            "discomfort_without_condition_count": no_condition,
            "directionality_error_count": direction_errors,
            "reverse_direction_pair_count": reverse_pairs,
            "unsafe_neck_normalized_target_count": neck_unsafe_targets,
            "lower_back_target_overlap_count": lower_back_target_overlap,
        },
    }
    return report


def build(
    catalog_path: Path = DEFAULT_CATALOG,
    legacy_path: Path = DEFAULT_LEGACY,
    mapping_path: Path = DEFAULT_MAPPING,
    stable_migration_path: Path = DEFAULT_STABLE_MIGRATION,
    consolidation_path: Path = DEFAULT_CONSOLIDATION,
    variant_path: Path = DEFAULT_VARIANTS,
    neck_candidates_path: Path = DEFAULT_NECK_CANDIDATES,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    final_by_stable, final_by_id = catalog_indexes(catalog_path)
    migrations = stable_migrations(stable_migration_path, final_by_stable)
    consolidated_ids = consolidation_by_source_id(consolidation_path, final_by_id)
    by_v1_id = v1_alias_indexes(final_by_stable)
    legacy_rows = read_jsonl(legacy_path)
    evidence_by_key = evidence_indexes(mapping_path)
    variant_pairs = load_variant_pairs(variant_path)
    neck_candidates = load_neck_candidates(neck_candidates_path)

    review_rows: list[dict[str, Any]] = []
    for record_number, legacy_row in enumerate(legacy_rows, 1):
        source = resolve_exercise(
            legacy_row,
            "source",
            final_by_stable,
            final_by_id,
            migrations,
            consolidated_ids,
            by_v1_id,
        )
        target = resolve_exercise(
            legacy_row,
            "target",
            final_by_stable,
            final_by_id,
            migrations,
            consolidated_ids,
            by_v1_id,
        )
        metadata = legacy_row.get("source_metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        relation_key = str(metadata.get("source_relation_key", "")).strip()
        evidence = evidence_by_key.get(relation_key, {})
        review_rows.append(
            review_row(
                legacy_row,
                record_number,
                source,
                target,
                evidence,
                variant_pairs,
            )
        )

    supplemental_rows: list[dict[str, Any]] = []
    for candidate in neck_candidates:
        source_code = str(candidate["source_exercise_stable_code"])
        target_code = str(candidate["target_exercise_stable_code"])
        source = final_by_stable.get(source_code)
        target = final_by_stable.get(target_code)
        supplemental_rows.append(
            review_row(
                supplemental_legacy_row(candidate, catalog_path, neck_candidates_path),
                1000 + len(supplemental_rows) + 1,
                source,
                target,
                {str(key): json_value(value) for key, value in candidate.items()},
                variant_pairs,
            )
        )

    normalized_rows = [normalized_row(row) for row in review_rows if row["decision"] == "KEEP"]
    normalized_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in review_rows:
        if row["decision"] != "KEEP":
            continue
        key = (
            row["source_exercise_stable_code"],
            row["target_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
        normalized_by_key.setdefault(key, []).append(row)
    normalized_legacy_rows: list[dict[str, Any]] = []
    for key in sorted(normalized_by_key):
        source_rows = normalized_by_key[key]
        normalized = normalized_row(source_rows[0])
        normalized["legacy_relation_identities"] = [
            source_row["legacy_relation_identity"] for source_row in source_rows
        ]
        normalized["legacy_source_relation_keys"] = [
            source_row["legacy_source_relation_key"] for source_row in source_rows
        ]
        normalized_legacy_rows.append(normalized)
    normalized_legacy_rows.sort(
        key=lambda row: (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
    )
    supplemental_normalized_rows = [
        normalized_row(row) for row in supplemental_rows if row["decision"] == "KEEP"
    ]
    normalized_rows = normalized_legacy_rows + supplemental_normalized_rows
    normalized_rows.sort(
        key=lambda row: (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
    )
    review_rows.sort(key=lambda row: int(row["legacy_record_number"]))
    supplemental_rows.sort(key=lambda row: int(row["legacy_record_number"]))
    dispositions = [row for row in review_rows if row["decision"] == "REMOVE_RECLASSIFY"]
    unresolved = [row for row in review_rows if row["decision"] == "REVIEW_REQUIRED"]
    neck_review_rows = [
        row for row in review_rows + supplemental_rows if row["pain_discomfort_area_code"] == "NECK"
    ]
    lower_back_review_rows = [
        row
        for row in review_rows
        if row["pain_discomfort_area_code"] == "LOWER_BACK"
        and row["legacy_reason_code"] == ALTERNATIVE_REASON
    ]
    neck_normalized_rows = [
        normalized_row(row) for row in neck_review_rows if row["decision"] == "KEEP"
    ]
    neck_normalized_rows.sort(
        key=lambda row: (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["pain_discomfort_area_code"],
            row["condition_code"],
        )
    )
    input_paths = {
        "final_catalog": catalog_path,
        "legacy_alternatives": legacy_path,
        "discomfort_evidence": mapping_path,
        "stable_code_migration": stable_migration_path,
        "legacy_consolidation": consolidation_path,
        "variant_relationship_review": variant_path,
        "neck_discomfort_candidates": neck_candidates_path,
    }
    report = integrity_report(
        review_rows,
        normalized_rows,
        len(normalized_legacy_rows),
        neck_review_rows,
        lower_back_review_rows,
        final_by_stable,
        variant_pairs,
        {key: path for key, path in input_paths.items() if path.exists()},
    )
    if not all(report["invariants"].values()):
        failed = [key for key, value in report["invariants"].items() if not value]
        raise ValueError(f"Alternative integrity validation failed: {failed}")

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "review_result_jsonl": output_dir / "pain_alternative_review_result_v2_0_2.jsonl",
        "review_result_csv": output_dir / "pain_alternative_review_result_v2_0_2.csv",
        "normalized_jsonl": output_dir / "normalized_discomfort_alternatives_v2_0_2.jsonl",
        "normalized_csv": output_dir / "normalized_discomfort_alternatives_v2_0_2.csv",
        "disposition_jsonl": output_dir / "legacy_alternative_dispositions_v2_0_2.jsonl",
        "disposition_csv": output_dir / "legacy_alternative_dispositions_v2_0_2.csv",
        "unresolved_jsonl": output_dir / "unresolved_alternatives_review_v2_0_2.jsonl",
        "unresolved_csv": output_dir / "unresolved_alternatives_review_v2_0_2.csv",
        "neck_review_jsonl": output_dir / "neck_alternative_review_v2_0_2.jsonl",
        "neck_review_csv": output_dir / "neck_alternative_review_v2_0_2.csv",
        "neck_normalized_jsonl": output_dir
        / "normalized_neck_discomfort_alternatives_v2_0_2.jsonl",
        "neck_normalized_csv": output_dir / "normalized_neck_discomfort_alternatives_v2_0_2.csv",
        "lower_back_safety_review_jsonl": output_dir
        / "lower_back_alternative_safety_review_v2_0_2.jsonl",
        "lower_back_safety_review_csv": output_dir
        / "lower_back_alternative_safety_review_v2_0_2.csv",
        "integrity_report": output_dir / "alternative_integrity_report_v2_0_2.json",
    }
    write_jsonl(paths["review_result_jsonl"], review_rows)
    write_csv(paths["review_result_csv"], REVIEW_FIELDS, review_rows)
    write_jsonl(paths["normalized_jsonl"], normalized_rows)
    write_csv(paths["normalized_csv"], NORMALIZED_FIELDS, normalized_rows)
    write_jsonl(paths["disposition_jsonl"], dispositions)
    write_csv(paths["disposition_csv"], DISPOSITION_FIELDS, dispositions)
    write_jsonl(paths["unresolved_jsonl"], unresolved)
    write_csv(paths["unresolved_csv"], REVIEW_FIELDS, unresolved)
    write_jsonl(paths["neck_review_jsonl"], neck_review_rows)
    write_csv(paths["neck_review_csv"], REVIEW_FIELDS, neck_review_rows)
    write_jsonl(paths["neck_normalized_jsonl"], neck_normalized_rows)
    write_csv(paths["neck_normalized_csv"], NORMALIZED_FIELDS, neck_normalized_rows)
    write_jsonl(paths["lower_back_safety_review_jsonl"], lower_back_review_rows)
    write_csv(paths["lower_back_safety_review_csv"], REVIEW_FIELDS, lower_back_review_rows)
    write_json(paths["integrity_report"], report)

    manifest = {
        "schema_version": "exercise-alternative-review-manifest-v2.0.2-v1",
        "policy_version": POLICY_VERSION,
        "reviewed_at": REVIEWED_AT,
        "status": "DRAFT_REVIEW_REQUIRED",
        "production_eligible": PRODUCTION_ELIGIBLE,
        "counts": report["counts"],
        "artifacts": {
            name: {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in paths.items()
        },
        "input_artifacts": report["source"],
        "decision_policy": {
            "alternative_reason_code": ALTERNATIVE_REASON,
            "supported_condition_bands": sorted(SUPPORTED_BANDS),
            "severe_condition_policy": "NRS_7_10_HAS_NO_ALTERNATIVE",
            "keep_guard": [
                "SOURCE_LOADS_REPORTED_DISCOMFORT_AREA",
                "TARGET_EXCLUDES_REPORTED_DISCOMFORT_AREA",
                "TARGET_DIFFICULTY_NOT_HIGHER",
                "NOT_SIMPLE_VARIANT_DUPLICATE",
                "DIRECTION_IS_SOURCE_TO_TARGET",
            ],
            "reclassification": {
                "EQUIPMENT": "VARIANT",
                "LOCATION": "CONTEXT_DEFAULT",
                "DIFFICULTY": "VARIANT_DIFFICULTY",
            },
            "same_area_target": "REMOVE_RECLASSIFY_EVEN_FOR_NRS_1_3",
            "neck_safety_policy": "NO_NECK_OR_SHOULDER_OVERLAP_AND_NO_UNPROVEN_CORE_BRACING_TARGET",
            "lower_back_safety_policy": (
                "CONDITIONALLY_RETAIN_WITH_NEUTRAL_SPINE_AND_NO_CORE_OR_HIP_TARGET_GUARDS"
            ),
        },
    }
    manifest_path = output_dir / "alternative_manifest_v2_0_2.json"
    write_json(manifest_path, manifest)
    return {
        "output_dir": str(output_dir),
        "counts": report["counts"],
        "integrity": report["integrity_metrics"],
        "manifest": str(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--legacy", type=Path, default=DEFAULT_LEGACY)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--stable-migration", type=Path, default=DEFAULT_STABLE_MIGRATION)
    parser.add_argument("--consolidation", type=Path, default=DEFAULT_CONSOLIDATION)
    parser.add_argument("--variants", type=Path, default=DEFAULT_VARIANTS)
    parser.add_argument("--neck-candidates", type=Path, default=DEFAULT_NECK_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(
        catalog_path=args.catalog,
        legacy_path=args.legacy,
        mapping_path=args.mapping,
        stable_migration_path=args.stable_migration,
        consolidation_path=args.consolidation,
        variant_path=args.variants,
        neck_candidates_path=args.neck_candidates,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
