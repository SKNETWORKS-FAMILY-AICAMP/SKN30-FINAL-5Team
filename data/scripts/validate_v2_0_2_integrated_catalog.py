#!/usr/bin/env python3
"""Validate v2.0.2 integrated exercise references without inventing domain data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "generated/exercise-catalog-v2.0.2-final"
DRAFT = ROOT / "generated/exercise-catalog-v2.0.2-draft"
DEFAULT_OUTPUT = FINAL / "audit/integrity"
CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
GENERATED_AT = "2026-08-28T00:00:00+09:00"
MEDIA_SOURCE_ORIGINS = {"KSPO", "WGER", "GYMVISUAL", "PAIN_ALTERNATIVE_POLICY", "UNAVAILABLE"}

RECORD_TYPES = (
    "REPRESENTATIVE",
    "PRIMARY_VARIANT",
    "SECONDARY_VARIANT",
    "SEPARATE_EXERCISE",
    "GLOBAL",
)
GENERIC_VARIANT_CUES = [
    "원천 수행 단계를 확인하고 안정적인 자세를 잡는다.",
    "통제된 범위에서 Variant의 고유한 수행법을 따른다.",
    "불편하거나 이상 반응이 있으면 즉시 중단한다.",
]
EXECUTION_CHANGE_TERMS = (
    "sumo",
    "wide",
    "narrow",
    "reverse",
    "incline",
    "decline",
    "lying",
    "seated",
    "standing",
    "kneeling",
    "single",
    "one arm",
    "grip",
    "twist",
    "스모",
    "와이드",
    "내로우",
    "리버스",
    "인클라인",
    "디클라인",
    "라잉",
    "시티드",
    "스탠딩",
    "니링",
    "싱글",
    "원암",
    "그립",
    "트위스트",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def record_bucket(row: dict[str, Any]) -> str:
    if row.get("record_type") == "VARIANT":
        return str(row.get("variant_type_code") or "GLOBAL")
    value = str(row.get("record_type") or "GLOBAL")
    return value if value in RECORD_TYPES else "GLOBAL"


def source_origin(source_track: str) -> str:
    return {
        "kspo": "KSPO",
        "wger": "WGER",
        "gymvisual": "GYMVISUAL",
        "pain_alternative_policy": "PAIN_ALTERNATIVE_POLICY",
    }.get(source_track, "UNAVAILABLE")


def issue(
    code: str,
    classification: str,
    scope: str,
    message: str,
    *,
    record: dict[str, Any] | None = None,
    severity: str = "ERROR",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "issue_code": code,
        "classification": classification,
        "scope": scope,
        "severity": severity,
        "record_type": record_bucket(record or {}),
        "exercise_id": (record or {}).get("exercise_id", ""),
        "stable_code": (record or {}).get("stable_code", ""),
        "message_ko": message,
    }
    if details:
        result["details"] = details
    return result


def summarize_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    by_class = Counter(row["classification"] for row in issues)
    by_type = {kind: {"finding_count": 0, "affected_exercise_count": 0} for kind in RECORD_TYPES}
    affected: dict[str, set[str]] = defaultdict(set)
    for row in issues:
        kind = row["record_type"]
        by_type[kind]["finding_count"] += 1
        identity = row.get("exercise_id") or row.get("stable_code")
        if identity:
            affected[kind].add(str(identity))
    for kind in RECORD_TYPES:
        by_type[kind]["affected_exercise_count"] = len(affected[kind])
    return {
        "finding_count": len(issues),
        "classification_counts": dict(sorted(by_class.items())),
        "by_record_type": by_type,
    }


def build_reports(
    *,
    final_dir: Path = FINAL,
    draft_dir: Path = DRAFT,
    media_path: Path | None = None,
) -> dict[str, Any]:
    catalog_path = final_dir / "catalog/exercises.jsonl"
    safety_path = final_dir / "runtime/safety_rules.jsonl"
    fitt_path = final_dir / "prescriptions/prescription_profiles.jsonl"
    goal_path = final_dir / "prescriptions/goal_tag_links.jsonl"
    alternatives_path = final_dir / "alternatives/resolved_discomfort_alternative_map_v2_0_2.jsonl"
    reviewed_alternatives_path = (
        final_dir / "audit/alternatives/reviewed_discomfort_alternative_map_v2_0_2.jsonl"
    )
    concern_removed_path = (
        final_dir / "audit/alternatives/concern_resolution_removed_map_v2_0_2.jsonl"
    )
    safe_variants_path = final_dir / "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl"
    registry_path = final_dir / "audit/stable_code_registry_v2.json"
    deletion_path = final_dir / "audit/canonical_deletions_v2_0_2.jsonl"
    aliases_path = final_dir / "audit/alias_migration_v2_0_2.jsonl"
    variant_map_path = final_dir / "audit/variant_safety_fitt_mapping_v2_0_2.jsonl"
    binding_status_path = final_dir / "audit/reference_binding_status_v2_0_2.jsonl"
    if media_path is None:
        media_path = final_dir / "media/media_assets_v2_0_2.csv"
    manifest = json.loads((final_dir / "manifest.json").read_text(encoding="utf-8"))
    batch_approval = manifest.get("batch_approval") or {}
    batch_approval_active = (
        batch_approval.get("status") == "APPROVED"
        and batch_approval.get("approval_reference") == "USER_DIRECT_REVIEW_2026_08_29"
        and batch_approval.get("scope", {}).get("final_catalog_records") == 170
        and batch_approval.get("scope", {}).get("resolved_alternative_records") == 1104
        and batch_approval.get("scope", {}).get("variant_safety_fitt_records") == 15
        and batch_approval.get("scope", {}).get("alternative_difficulty_delta_records") == 29
        and batch_approval.get("scope", {}).get("media_rights_review_records") == 102
    )

    catalog = read_jsonl(catalog_path)
    safety = read_jsonl(safety_path)
    fitt = read_jsonl(fitt_path)
    goals = read_jsonl(goal_path)
    alternatives = read_jsonl(alternatives_path)
    reviewed_alternatives = read_jsonl(reviewed_alternatives_path)
    concern_removed = read_jsonl(concern_removed_path)
    safe_variants = read_jsonl(safe_variants_path)
    media = read_csv(media_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))["records"]
    deletions = read_jsonl(deletion_path)
    aliases = read_jsonl(aliases_path)
    variant_mappings = read_jsonl(variant_map_path)
    binding_status = read_jsonl(binding_status_path)

    by_id: dict[str, dict[str, Any]] = {
        str(row["exercise_id"]): row for row in catalog if row.get("exercise_id")
    }
    by_code: dict[str, dict[str, Any]] = {
        str(row["stable_code"]): row for row in catalog if row.get("stable_code")
    }
    catalog_ids = set(by_id)
    catalog_codes = set(by_code)
    variants = [row for row in catalog if row.get("record_type") == "VARIANT"]
    binding_by_code = {str(row.get("stable_code") or ""): row for row in binding_status}
    deleted_codes = {row["stable_code_before"] for row in deletions}
    legacy_to_current = {
        row["stable_code_before"]: row["stable_code_after"]
        for row in aliases
        if row.get("field_name") == "stable_code"
        and row.get("stable_code_before")
        and row.get("stable_code_after")
        and row["stable_code_before"] != row["stable_code_after"]
    }

    reference_issues: list[dict[str, Any]] = []
    structural_fields = ("exercise_id", "stable_code", "family_code")
    for row in catalog:
        for field in structural_fields:
            if not row.get(field):
                reference_issues.append(
                    issue(
                        f"MISSING_{field.upper()}",
                        "AUTO_FIXABLE",
                        "CATALOG",
                        f"필수 참조 필드 {field}가 비어 있다.",
                        record=row,
                    )
                )
        bucket = record_bucket(row)
        if row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT":
            if (
                row.get("alternative_only") is not False
                or row.get("general_pool_included") is not True
                or row.get("pain_discomfort_area_code")
                or "condition_codes" in row
            ):
                reference_issues.append(
                    issue(
                        "SAFE_VARIANT_CATALOG_CONTRACT_VIOLATION",
                        "AUTO_FIXABLE",
                        "CATALOG",
                        "safe Variant는 일반 운동 풀에 포함하고 통증 부위·조건은 "
                        "exercise_alternatives 관계에만 둬야 한다.",
                        record=row,
                    )
                )
        rep_id = row.get("representative_exercise_id")
        if bucket in {"PRIMARY_VARIANT", "SECONDARY_VARIANT"}:
            if rep_id not in catalog_ids:
                reference_issues.append(
                    issue(
                        "ORPHAN_REPRESENTATIVE_REFERENCE",
                        "AUTO_FIXABLE",
                        "CATALOG",
                        "Variant의 representative_exercise_id가 통합 카탈로그에 없다.",
                        record=row,
                        details={"representative_exercise_id": rep_id},
                    )
                )
            elif by_id[rep_id].get("record_type") != "REPRESENTATIVE":
                reference_issues.append(
                    issue(
                        "INVALID_REPRESENTATIVE_TARGET_TYPE",
                        "AUTO_FIXABLE",
                        "CATALOG",
                        "Variant의 대표 참조가 REPRESENTATIVE record를 가리키지 않는다.",
                        record=row,
                    )
                )
            elif row.get("family_code") != by_id[rep_id].get("family_code"):
                reference_issues.append(
                    issue(
                        "FAMILY_REPRESENTATIVE_MISMATCH",
                        "AUTO_FIXABLE",
                        "CATALOG",
                        "Variant와 대표운동의 family_code가 다르다.",
                        record=row,
                    )
                )
        elif row.get("variant_type_code"):
            reference_issues.append(
                issue(
                    "VARIANT_TYPE_ON_NON_VARIANT",
                    "AUTO_FIXABLE",
                    "CATALOG",
                    "Variant가 아닌 record에 variant_type_code가 남아 있다.",
                    record=row,
                )
            )

    for field in ("exercise_id", "stable_code"):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in catalog:
            if row.get(field):
                grouped[str(row[field])].append(row)
        for value, rows in grouped.items():
            if len(rows) > 1:
                for row in rows:
                    reference_issues.append(
                        issue(
                            f"DUPLICATE_{field.upper()}",
                            "AUTO_FIXABLE",
                            "CATALOG",
                            f"{field}가 중복된다: {value}",
                            record=row,
                        )
                    )

    active_registry = {
        row["stable_code"]
        for row in registry
        if row.get("status") in {"ACTIVE_CANONICAL", "ACTIVE_CATALOG_RECORD"}
    }
    for code in sorted(catalog_codes - active_registry):
        reference_issues.append(
            issue(
                "STABLE_CODE_MISSING_FROM_REGISTRY",
                "AUTO_FIXABLE",
                "STABLE_CODE_REGISTRY",
                "통합 카탈로그 stable code가 active registry에 없다.",
                record=by_code[code],
            )
        )
    for code in sorted(active_registry - catalog_codes):
        reference_issues.append(
            issue(
                "STALE_ACTIVE_REGISTRY_CODE",
                "AUTO_FIXABLE",
                "STABLE_CODE_REGISTRY",
                "active registry code가 통합 카탈로그에 없거나 삭제/변경 전 코드다.",
                details={"stable_code": code, "is_deleted": code in deleted_codes},
            )
        )

    linked_sets = {
        "SAFETY": (safety, "exercise_stable_code"),
        "FITT": (fitt, "exercise_stable_code"),
        "GOAL": (goals, "exercise_stable_code"),
    }
    for scope, (rows, key) in linked_sets.items():
        references = {str(row.get(key) or "") for row in rows if row.get(key)}
        for code in sorted(references - catalog_codes):
            classification = "AUTO_FIXABLE"
            reference_issues.append(
                issue(
                    f"ORPHAN_{scope}_REFERENCE",
                    classification,
                    scope,
                    f"{scope} 참조 stable code가 통합 카탈로그에 없다.",
                    details={
                        "referenced_stable_code": code,
                        "migration_target": legacy_to_current.get(code, ""),
                        "is_deleted_or_retired": code in deleted_codes
                        or code not in legacy_to_current,
                    },
                )
            )

        for row in catalog:
            if row["stable_code"] in references:
                continue
            classification = "HUMAN_REVIEW_REQUIRED"
            message = f"{scope} 연결이 없으며 운동별 전문 검토 없이 대표값을 복사할 수 없다."
            reference_issues.append(
                issue(
                    f"MISSING_{scope}_BINDING",
                    classification,
                    scope,
                    message,
                    record=row,
                )
            )
        versions = {str(row.get("catalog_version_code") or "") for row in rows}
        if versions != {CATALOG_VERSION}:
            reference_issues.append(
                issue(
                    f"{scope}_CATALOG_VERSION_MISMATCH",
                    "AUTO_FIXABLE",
                    scope,
                    f"{scope} artifact version이 통합 카탈로그 v2.0.2-final과 일치하지 않는다.",
                    details={"found_versions": sorted(versions)},
                )
            )

    missing_binding_state_codes = sorted(catalog_codes - set(binding_by_code))
    extra_binding_state_codes = sorted(set(binding_by_code) - catalog_codes)
    for code in missing_binding_state_codes:
        reference_issues.append(
            issue(
                "MISSING_REFERENCE_BINDING_STATE",
                "AUTO_FIXABLE",
                "REFERENCE_BINDING_STATE",
                "운동별 Safety/FITT/Goal 명시 상태 행이 없다.",
                record=by_code[code],
            )
        )
    for code in extra_binding_state_codes:
        reference_issues.append(
            issue(
                "ORPHAN_REFERENCE_BINDING_STATE",
                "AUTO_FIXABLE",
                "REFERENCE_BINDING_STATE",
                "Safety/FITT/Goal 명시 상태가 카탈로그 밖 stable code를 가리킨다.",
                details={"stable_code": code},
            )
        )

    media_ids = {
        row.get("exercise_id") or row.get("representative_exercise_id", "") for row in media
    }
    for media_row in media:
        media_id = media_row.get("exercise_id") or media_row.get("representative_exercise_id", "")
        if media_id not in catalog_ids:
            reference_issues.append(
                issue(
                    "ORPHAN_MEDIA_REFERENCE",
                    "AUTO_FIXABLE",
                    "MEDIA",
                    "Media exercise ID가 통합 카탈로그에 없다.",
                    details={"exercise_id": media_id},
                )
            )
        catalog_row = by_id.get(str(media_id))
        origin = str(media_row.get("source_origin_code") or "")
        if origin not in MEDIA_SOURCE_ORIGINS:
            reference_issues.append(
                issue(
                    "INVALID_MEDIA_SOURCE_ORIGIN",
                    "AUTO_FIXABLE",
                    "MEDIA",
                    "Media source_origin_code가 허용된 출처 코드가 아니다.",
                    details={"exercise_id": media_id, "source_origin_code": origin},
                )
            )
        if catalog_row:
            expected_origin = source_origin(str(catalog_row.get("source_track") or ""))
            if origin != expected_origin:
                reference_issues.append(
                    issue(
                        "MEDIA_SOURCE_ORIGIN_MISMATCH",
                        "AUTO_FIXABLE",
                        "MEDIA",
                        "Media source 출처가 통합 카탈로그와 일치하지 않는다.",
                        record=catalog_row,
                        details={"expected": expected_origin, "found": origin},
                    )
                )
            record_source_identity = str(media_row.get("record_source_identity") or "")
            expected_record_identity = str(catalog_row.get("source_identity") or "")
            if record_source_identity != expected_record_identity:
                reference_issues.append(
                    issue(
                        "MEDIA_RECORD_SOURCE_IDENTITY_MISMATCH",
                        "AUTO_FIXABLE",
                        "MEDIA",
                        "Media record 원천 식별자가 통합 카탈로그와 일치하지 않는다.",
                        record=catalog_row,
                        details={
                            "expected": expected_record_identity,
                            "found": record_source_identity,
                        },
                    )
                )
            media_source = catalog_row
            if expected_origin == "PAIN_ALTERNATIVE_POLICY":
                media_source = by_id.get(
                    str(catalog_row.get("alternative_source_base_exercise_id") or ""), {}
                )
            expected_media_origin = source_origin(str(media_source.get("source_track") or ""))
            actual_media_origin = str(media_row.get("media_source_origin_code") or "")
            if actual_media_origin != expected_media_origin:
                reference_issues.append(
                    issue(
                        "MEDIA_SOURCE_ORIGIN_MISMATCH",
                        "AUTO_FIXABLE",
                        "MEDIA",
                        "Media source origin이 이름/원천 운동 매핑 결과와 일치하지 않는다.",
                        record=catalog_row,
                        details={"expected": expected_media_origin, "found": actual_media_origin},
                    )
                )
            source_identity = str(media_row.get("source_identity") or "")
            expected_identity = str(media_source.get("source_identity") or "")
            if source_identity != expected_identity:
                reference_issues.append(
                    issue(
                        "MEDIA_SOURCE_IDENTITY_MISMATCH",
                        "AUTO_FIXABLE",
                        "MEDIA",
                        "Media source_identity가 통합 카탈로그와 일치하지 않는다.",
                        record=catalog_row,
                        details={"expected": expected_identity, "found": source_identity},
                    )
                )
            if actual_media_origin == "GYMVISUAL" and not source_identity.isdigit():
                reference_issues.append(
                    issue(
                        "GYMVISUAL_SOURCE_IDENTITY_NOT_NUMERIC",
                        "AUTO_FIXABLE",
                        "MEDIA",
                        "Gymvisual media source_identity는 숫자 코드여야 한다.",
                        record=catalog_row,
                        details={"source_identity": source_identity},
                    )
                )
    for row in catalog:
        if row["exercise_id"] not in media_ids:
            reference_issues.append(
                issue(
                    "MISSING_MEDIA_STATE",
                    "AUTO_FIXABLE",
                    "MEDIA",
                    "운동별 media 존재/미존재 상태가 media registry에 명시되지 않았다.",
                    record=row,
                )
            )
    media_versions = {str(row.get("catalog_version_code") or "") for row in media}
    if media_versions != {CATALOG_VERSION}:
        reference_issues.append(
            issue(
                "MEDIA_CATALOG_VERSION_MISMATCH",
                "AUTO_FIXABLE",
                "MEDIA",
                "Media artifact version이 통합 카탈로그 v2.0.2-final과 일치하지 않는다.",
                details={
                    "media_path": str(media_path.relative_to(ROOT)),
                    "found_versions": sorted(media_versions),
                },
            )
        )

    variant_review: list[dict[str, Any]] = []
    mapping_by_id = {row["exercise_id"]: row for row in variant_mappings}
    for row in variants:
        rep = by_id[row["representative_exercise_id"]]
        safety_reasons = ["INDEPENDENT_VARIANT_SAFETY_REVIEW_REQUIRED"]
        fitt_reasons = ["INDEPENDENT_VARIANT_FITT_REVIEW_REQUIRED"]
        data_reasons: list[str] = []
        if row.get("equipment_codes") != rep.get("equipment_codes"):
            safety_reasons.append("EQUIPMENT_CHANGE_MAY_CHANGE_STABILITY_REQUIREMENT")
        execution_text = " ".join(
            str(row.get(key, "")) for key in ("name_en", "name_ko", "instruction_summary_ko")
        ).lower()
        if any(term in execution_text for term in EXECUTION_CHANGE_TERMS):
            safety_reasons.append("POSTURE_GRIP_STANCE_OR_ROM_DIFFERENCE_REVIEW_REQUIRED")
        taxonomy_fields = (
            "training_type_code",
            "primary_movement_pattern_code",
            "body_focus_code",
            "primary_body_area_codes",
            "secondary_body_area_codes",
        )
        changed_taxonomy = [key for key in taxonomy_fields if row.get(key) != rep.get(key)]
        inherited_taxonomy = [key for key in taxonomy_fields if row.get(key) == rep.get(key)]
        if changed_taxonomy:
            safety_reasons.append("TAXONOMY_CHANGE_MAY_REQUIRE_DISTINCT_SAFETY_RULE")
        if inherited_taxonomy:
            data_reasons.append("REPRESENTATIVE_EQUAL_TAXONOMY_REQUIRES_SOURCE_CONFIRMATION")
        if row.get("difficulty_code") == rep.get("difficulty_code"):
            data_reasons.append("REPRESENTATIVE_EQUAL_DIFFICULTY_REQUIRES_EXECUTION_CONFIRMATION")
        if row.get("location_codes") == rep.get("location_codes"):
            data_reasons.append("REPRESENTATIVE_EQUAL_LOCATION_REQUIRES_FEASIBILITY_CONFIRMATION")
        if row.get("instruction_summary_ko") == rep.get("instruction_summary_ko"):
            data_reasons.append("EXACT_REPRESENTATIVE_INSTRUCTION_COPY")
        if row.get("form_cues_ko") == GENERIC_VARIANT_CUES:
            data_reasons.append("GENERIC_VARIANT_FORM_CUES_REQUIRE_EXERCISE_SPECIFIC_REVIEW")
        timing = row.get("timing_mode_code")
        if timing == "REPS":
            fitt_reasons.append("REPS_BASED_PROFILE_REQUIRED")
            if not row.get("default_seconds_per_rep") or row.get("default_work_seconds") not in (
                None,
                "",
            ):
                fitt_reasons.append("REPS_TIMING_FIELDS_INCONSISTENT")
        elif timing == "DURATION":
            fitt_reasons.append("TIME_BASED_PROFILE_REQUIRED")
            if not row.get("default_work_seconds"):
                fitt_reasons.append("DURATION_TIMING_FIELDS_INCONSISTENT")
        else:
            fitt_reasons.append("UNKNOWN_TIMING_MODE")
        expected_levels = (
            ["BEGINNER", "INTERMEDIATE"]
            if row.get("difficulty_code") == "BEGINNER"
            else ["INTERMEDIATE"]
        )
        mapping = mapping_by_id.get(row["exercise_id"], {})
        assigned_levels = sorted((mapping.get("fitt_template_ids_by_experience") or {}).keys())
        if assigned_levels != expected_levels:
            fitt_reasons.append("EXPERIENCE_LEVEL_PRESCRIPTION_COVERAGE_MISSING")
        variant_review.append(
            {
                "review_classification": "HUMAN_REVIEW_REQUIRED",
                "exercise_id": row["exercise_id"],
                "stable_code": row["stable_code"],
                "variant_type_code": row["variant_type_code"],
                "record_type": record_bucket(row),
                "representative_exercise_id": row["representative_exercise_id"],
                "representative_stable_code": rep["stable_code"],
                "family_code": row["family_code"],
                "difficulty_code": row.get("difficulty_code"),
                "equipment_codes": row.get("equipment_codes"),
                "location_codes": row.get("location_codes"),
                "timing_mode_code": timing,
                "expected_experience_levels": expected_levels,
                "assigned_experience_levels": assigned_levels,
                "changed_taxonomy_fields": changed_taxonomy,
                "representative_equal_taxonomy_fields": inherited_taxonomy,
                "safety_review_reason_codes": sorted(set(safety_reasons)),
                "fitt_review_reason_codes": sorted(set(fitt_reasons)),
                "variant_data_review_reason_codes": sorted(set(data_reasons)),
                "safety_mapping_status_code": mapping.get("safety_mapping_status_code", "MISSING"),
                "fitt_mapping_status_code": mapping.get("fitt_mapping_status_code", "MISSING"),
                "production_eligible": False,
            }
        )

    if batch_approval_active:
        for row in variant_review:
            row.update(
                {
                    "review_classification": "DOMAIN_APPROVED",
                    "production_eligible": True,
                    "review_method_code": "OWNER_BATCH_CONFIRMATION",
                    "reviewer_reference": batch_approval["approval_reference"],
                    "reviewed_at": batch_approval["approved_at"],
                    "evidence_reference": "; ".join(batch_approval["approval_basis"]),
                    "review_note_ko": "일괄 승인: 외부 전문가 원천 승인 및 최종 육안 검수 완료",
                }
            )

    media_goal_issues: list[dict[str, Any]] = [
        row for row in reference_issues if row["scope"] in {"MEDIA", "GOAL"}
    ]
    media_by_id = {
        row.get("exercise_id") or row.get("representative_exercise_id", ""): row for row in media
    }
    for row in catalog:
        matched_media = media_by_id.get(row["exercise_id"])
        if not matched_media:
            media_goal_issues.append(
                issue(
                    "MEDIA_RIGHTS_UNVERIFIED_FOR_CATALOG_RECORD",
                    "HUMAN_REVIEW_REQUIRED",
                    "MEDIA",
                    "통합 record 단위 media rights/license 승인 증적이 없다.",
                    record=row,
                )
            )
        elif matched_media.get("rights_review_status") != "APPROVED":
            media_goal_issues.append(
                issue(
                    "MEDIA_RIGHTS_NOT_APPROVED",
                    "HUMAN_REVIEW_REQUIRED",
                    "MEDIA",
                    "Media rights 상태가 APPROVED가 아니다.",
                    record=row,
                )
            )
    shared_reference_variants = [
        row
        for row in variants
        if row.get("source_media_reference")
        and row.get("source_media_reference")
        == by_id[row["representative_exercise_id"]].get("source_media_reference")
    ]
    for row in shared_reference_variants:
        media_goal_issues.append(
            issue(
                "VARIANT_SHARES_REPRESENTATIVE_SOURCE_MEDIA",
                "HUMAN_REVIEW_REQUIRED",
                "MEDIA",
                "Variant가 대표운동과 동일 source media를 사용해 수행 동일성 확인이 필요하다.",
                record=row,
            )
        )
    goal_codes = {row.get("goal_code") for row in goals}
    if "" in goal_codes or None in goal_codes:
        media_goal_issues.append(
            issue(
                "EMPTY_GOAL_CODE",
                "AUTO_FIXABLE",
                "GOAL",
                "Goal link에 빈 goal_code가 있다.",
            )
        )
    for goal_row in goals:
        goal_stable_code = goal_row.get("exercise_stable_code")
        target = by_code.get(str(goal_stable_code)) if goal_stable_code else None
        if (
            target
            and goal_row.get("role_eligibility_code") == "CORE"
            and "MAIN" not in target.get("phase_codes", [])
        ):
            media_goal_issues.append(
                issue(
                    "GOAL_ROLE_PHASE_SEMANTIC_CONFLICT",
                    "HUMAN_REVIEW_REQUIRED",
                    "GOAL",
                    "CORE Goal role이 MAIN phase를 지원하지 않는 운동에 연결되어 있다.",
                    record=target,
                    details={
                        "goal_code": goal_row.get("goal_code"),
                        "phase_codes": target.get("phase_codes"),
                    },
                )
            )

    alternative_issues: list[dict[str, Any]] = []
    prior_reviewed_by_id = {row["map_relation_id"]: row for row in alternatives + concern_removed}
    current_reviewed_by_id = {row["map_relation_id"]: row for row in reviewed_alternatives}
    added_relation_ids = sorted(current_reviewed_by_id.keys() - prior_reviewed_by_id.keys())
    removed_relation_ids = sorted(prior_reviewed_by_id.keys() - current_reviewed_by_id.keys())
    alternative_difficulty_review = [
        {
            "review_classification": "HUMAN_REVIEW_REQUIRED",
            "change_code": "ADDED_AFTER_DIFFICULTY_POLICY",
            **current_reviewed_by_id[relation_id],
        }
        for relation_id in added_relation_ids
    ] + [
        {
            "review_classification": "HUMAN_REVIEW_REQUIRED",
            "change_code": "REMOVED_AFTER_DIFFICULTY_POLICY",
            **prior_reviewed_by_id[relation_id],
        }
        for relation_id in removed_relation_ids
    ]
    if batch_approval_active:
        for row in alternative_difficulty_review:
            row.update(
                {
                    "review_classification": "DOMAIN_APPROVED",
                    "production_eligible": True,
                    "review_method_code": "OWNER_BATCH_CONFIRMATION",
                    "reviewer_reference": batch_approval["approval_reference"],
                    "reviewed_at": batch_approval["approved_at"],
                    "evidence_reference": "; ".join(batch_approval["approval_basis"]),
                    "review_note_ko": "일괄 승인: 외부 전문가 원천 승인 및 최종 육안 검수 완료",
                }
            )
    safe_by_id = {row["exercise_id"]: row for row in safe_variants}
    all_allowed_ids = catalog_ids | set(safe_by_id)
    all_allowed_codes = catalog_codes | {row["stable_code"] for row in safe_variants}
    natural_keys: Counter[tuple[Any, ...]] = Counter()
    forbidden_reason_rows = 0
    for row in alternatives:
        natural_keys[
            (
                row.get("source_exercise_stable_code"),
                row.get("target_exercise_stable_code"),
                row.get("pain_discomfort_area_code"),
                row.get("condition_code"),
            )
        ] += 1
        if row.get("source_exercise_id") not in all_allowed_ids:
            alternative_issues.append(
                issue(
                    "ORPHAN_ALTERNATIVE_SOURCE",
                    "AUTO_FIXABLE",
                    "ALTERNATIVE",
                    "Alternative source가 운동 registry에 없다.",
                    details={"source_exercise_id": row.get("source_exercise_id")},
                )
            )
        if row.get("target_exercise_id") not in all_allowed_ids:
            alternative_issues.append(
                issue(
                    "ORPHAN_ALTERNATIVE_TARGET",
                    "AUTO_FIXABLE",
                    "ALTERNATIVE",
                    "Alternative target이 운동 registry에 없다.",
                    details={"target_exercise_id": row.get("target_exercise_id")},
                )
            )
        if (
            row.get("source_exercise_stable_code") not in all_allowed_codes
            or row.get("target_exercise_stable_code") not in all_allowed_codes
        ):
            alternative_issues.append(
                issue(
                    "ALTERNATIVE_ID_CODE_MISMATCH",
                    "AUTO_FIXABLE",
                    "ALTERNATIVE",
                    "Alternative stable code와 exercise registry가 일치하지 않는다.",
                    details={"map_relation_id": row.get("map_relation_id")},
                )
            )
        forbidden_values = {
            "EQUIPMENT",
            "LOCATION",
            "DIFFICULTY",
            "PRIMARY_VARIANT",
            "SECONDARY_VARIANT",
        }
        if any(
            row.get(key) in forbidden_values
            for key in ("reason_code", "alternative_reason_code", "review_reason_code")
        ):
            forbidden_reason_rows += 1
        if row.get("review_status_code") != "DOMAIN_APPROVED" or not row.get("production_eligible"):
            continue
    duplicates = [key for key, count in natural_keys.items() if count > 1]
    if duplicates:
        alternative_issues.append(
            issue(
                "DUPLICATE_ALTERNATIVE_NATURAL_KEY",
                "AUTO_FIXABLE",
                "ALTERNATIVE",
                "Alternative natural key가 중복된다.",
                details={"duplicate_count": len(duplicates)},
            )
        )
    if forbidden_reason_rows:
        alternative_issues.append(
            issue(
                "NON_PAIN_ALTERNATIVE_REASON",
                "AUTO_FIXABLE",
                "ALTERNATIVE",
                "확정 Alternative에 장비/장소/난이도/Variant 사유가 남아 있다.",
                details={"row_count": forbidden_reason_rows},
            )
        )
    missing_safe_variant_ids = sorted(set(safe_by_id) - catalog_ids)
    for exercise_id in missing_safe_variant_ids:
        safe = safe_by_id[exercise_id]
        alternative_issues.append(
            issue(
                "SAFE_VARIANT_NOT_IN_INTEGRATED_CATALOG",
                "AUTO_FIXABLE",
                "ALTERNATIVE",
                "Alternative target인 별도 안전 Variant가 통합 exercise catalog에 없다.",
                record={**safe, "record_type": "SEPARATE_EXERCISE"},
                details={
                    "referencing_relation_count": sum(
                        row.get("target_exercise_id") == exercise_id for row in alternatives
                    ),
                },
            )
        )
    alternative_issues.append(
        issue(
            "ALTERNATIVE_DOMAIN_APPROVAL_PENDING",
            "HUMAN_REVIEW_REQUIRED",
            "ALTERNATIVE",
            "통증 Alternative 1,104행은 정책·기계 검수 메타데이터를 갖지만 "
            "production_eligible=false다. 운영 승격을 위한 독립 도메인 승인 registry 증적이 없다.",
            details={
                "relation_count": len(alternatives),
                "review_status_counts": dict(
                    sorted(
                        Counter(
                            str(row.get("review_status_code") or "") for row in alternatives
                        ).items()
                    )
                ),
                "production_eligible_relation_count": sum(
                    bool(row.get("production_eligible")) for row in alternatives
                ),
            },
        )
    )
    if alternative_difficulty_review:
        alternative_issues.append(
            issue(
                "ALTERNATIVE_SET_CHANGED_BY_DIFFICULTY_POLICY",
                "HUMAN_REVIEW_REQUIRED",
                "ALTERNATIVE",
                "난이도 정책 변경으로 기존 검토 Alternative 집합이 달라져 재승인이 필요하다.",
                details={
                    "added_relation_count": len(added_relation_ids),
                    "removed_relation_count": len(removed_relation_ids),
                },
            )
        )

    if batch_approval_active:
        human_review_codes = {
            "VARIANT_SHARES_REPRESENTATIVE_SOURCE_MEDIA",
            "GOAL_ROLE_PHASE_SEMANTIC_CONFLICT",
            "MEDIA_RIGHTS_UNVERIFIED_FOR_CATALOG_RECORD",
            "MEDIA_RIGHTS_NOT_APPROVED",
            "ALTERNATIVE_DOMAIN_APPROVAL_PENDING",
            "ALTERNATIVE_SET_CHANGED_BY_DIFFICULTY_POLICY",
        }
        reference_issues = [
            row for row in reference_issues if row["issue_code"] not in human_review_codes
        ]
        media_goal_issues = [
            row for row in media_goal_issues if row["issue_code"] not in human_review_codes
        ]
        alternative_issues = [
            row for row in alternative_issues if row["issue_code"] not in human_review_codes
        ]

    blockers: list[dict[str, Any]] = []
    batch_approved_blockers = {
        "CATALOG_MANIFEST_NOT_PRODUCTION_ELIGIBLE",
        "VARIANT_SAFETY_FITT_UNAPPROVED",
        "ALTERNATIVE_NOT_DOMAIN_APPROVED",
        "ALTERNATIVE_DIFFICULTY_POLICY_DELTA_REVIEW_REQUIRED",
        "MEDIA_STATE_AND_RIGHTS_INCOMPLETE",
    }

    def blocker(code: str, message: str, evidence: dict[str, Any]) -> None:
        if batch_approval_active and code in batch_approved_blockers:
            return
        blockers.append({"blocker_code": code, "message_ko": message, "evidence": evidence})

    blocker(
        "CATALOG_MANIFEST_NOT_PRODUCTION_ELIGIBLE",
        "통합 manifest가 review-required draft 상태다.",
        {
            "manifest": "manifest.json",
            "status": json.loads((final_dir / "manifest.json").read_text(encoding="utf-8")).get(
                "status"
            ),
        },
    )
    blocker(
        "VARIANT_SAFETY_FITT_UNAPPROVED",
        f"모든 Variant {len(variants)}건의 독립 Safety/FITT 검토가 미완료다.",
        {
            "PRIMARY_VARIANT": sum(
                row["variant_type_code"] == "PRIMARY_VARIANT" for row in variants
            ),
            "SECONDARY_VARIANT": sum(
                row["variant_type_code"] == "SECONDARY_VARIANT" for row in variants
            ),
            "review_classification": dict(
                sorted(
                    Counter(
                        str(row.get("review_classification") or "") for row in variant_review
                    ).items()
                )
            ),
        },
    )
    independent_targets = [
        row
        for row in catalog
        if record_bucket(row) in {"PRIMARY_VARIANT", "SECONDARY_VARIANT", "SEPARATE_EXERCISE"}
    ]
    safety_codes = {str(row.get("exercise_stable_code") or "") for row in safety}
    fitt_codes = {str(row.get("exercise_stable_code") or "") for row in fitt}
    goal_link_codes = {str(row.get("exercise_stable_code") or "") for row in goals}
    missing_independent_bindings = [
        row
        for row in independent_targets
        if (
            row.get("stable_code") not in safety_codes
            or row.get("stable_code") not in fitt_codes
            or row.get("stable_code") not in goal_link_codes
            or binding_by_code.get(str(row.get("stable_code")), {}).get("safety_binding_state_code")
            != "AVAILABLE"
            or binding_by_code.get(str(row.get("stable_code")), {}).get("fitt_binding_state_code")
            != "AVAILABLE"
            or binding_by_code.get(str(row.get("stable_code")), {}).get("goal_binding_state_code")
            != "AVAILABLE"
        )
    ]
    if missing_independent_bindings:
        blocker(
            "MISSING_EXERCISE_BINDINGS",
            "Variant/별도운동의 Safety/FITT/Goal 연결이 없다.",
            {
                "variant_count": len(variants),
                "separate_exercise_count": sum(
                    record_bucket(row) == "SEPARATE_EXERCISE" for row in catalog
                ),
                "missing_record_count": len(missing_independent_bindings),
                "missing_stable_codes": [
                    row.get("stable_code") for row in missing_independent_bindings
                ],
            },
        )
    if missing_safe_variant_ids:
        blocker(
            "ALTERNATIVE_TARGETS_OUTSIDE_INTEGRATED_CATALOG",
            "통증 Alternative target 안전 Variant가 통합 카탈로그 밖에 있다.",
            {
                "safe_variant_count": len(missing_safe_variant_ids),
                "affected_relation_count": sum(
                    row.get("target_exercise_id") in set(missing_safe_variant_ids)
                    for row in alternatives
                ),
            },
        )
    blocker(
        "ALTERNATIVE_NOT_DOMAIN_APPROVED",
        f"통증 Alternative {len(alternatives)}행은 metadata-only 검수 상태이며 "
        "모두 production 비승인 상태다.",
        {
            "relation_count": len(alternatives),
            "review_status_counts": dict(
                sorted(
                    Counter(
                        str(row.get("review_status_code") or "") for row in alternatives
                    ).items()
                )
            ),
            "production_eligible_relation_count": sum(
                bool(row.get("production_eligible")) for row in alternatives
            ),
        },
    )
    if alternative_difficulty_review:
        blocker(
            "ALTERNATIVE_DIFFICULTY_POLICY_DELTA_REVIEW_REQUIRED",
            "난이도 정책 변경으로 추가·제외된 Alternative 관계 재검수가 필요하다.",
            {
                "added_relation_count": len(added_relation_ids),
                "removed_relation_count": len(removed_relation_ids),
                "review_status_counts": dict(
                    sorted(
                        Counter(
                            str(row.get("review_status_code") or "")
                            for row in alternative_difficulty_review
                        ).items()
                    )
                ),
                "user_review_status_counts": dict(
                    sorted(
                        Counter(
                            str(row.get("user_review_status") or "")
                            for row in alternative_difficulty_review
                        ).items()
                    )
                ),
            },
        )
    blocker(
        "MEDIA_STATE_AND_RIGHTS_INCOMPLETE",
        "통합 record 단위 Media 상태/rights 관리가 완결되지 않았다.",
        {
            "catalog_count": len(catalog),
            "valid_media_mapping_count": len(media_ids & catalog_ids),
            "media_state_counts": dict(
                sorted(Counter(str(row.get("media_state_code") or "") for row in media).items())
            ),
            "rights_review_status_counts": dict(
                sorted(Counter(str(row.get("rights_review_status") or "") for row in media).items())
            ),
        },
    )
    if catalog_codes != active_registry:
        blocker(
            "STABLE_CODE_REGISTRY_STALE",
            "stable code registry가 통합 record 집합과 일치하지 않는다.",
            {
                "catalog_not_active_registry_count": len(catalog_codes - active_registry),
                "active_registry_not_catalog_count": len(active_registry - catalog_codes),
            },
        )

    catalog_count_by_type = Counter(record_bucket(row) for row in catalog)
    reference_summary = summarize_issues(reference_issues)
    media_goal_summary = summarize_issues(media_goal_issues)
    alternative_summary = summarize_issues(alternative_issues)
    reference_report = {
        "schema_version": "exercise-catalog-v2.0.2-reference-integrity-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": "APPROVED" if batch_approval_active and not blockers else "BLOCKED",
        "production_eligible": batch_approval_active and not blockers,
        "catalog_counts_by_record_type": dict(catalog_count_by_type),
        "summary": reference_summary,
        "auto_fixable": [
            row for row in reference_issues if row["classification"] == "AUTO_FIXABLE"
        ],
        "human_review_required": [
            row for row in reference_issues if row["classification"] == "HUMAN_REVIEW_REQUIRED"
        ],
        "invariants": {
            "no_orphan_reference": not any(
                "ORPHAN" in row["issue_code"] for row in reference_issues
            ),
            "stable_codes_unique": not any(
                row["issue_code"] == "DUPLICATE_STABLE_CODE" for row in reference_issues
            ),
            "exercise_ids_unique": not any(
                row["issue_code"] == "DUPLICATE_EXERCISE_ID" for row in reference_issues
            ),
            "all_records_have_safety_fitt_media_goal_state": (
                not missing_binding_state_codes
                and not extra_binding_state_codes
                and not (catalog_ids - media_ids)
                and not (media_ids - catalog_ids)
            ),
            "no_legacy_code_residue": not any(
                row["issue_code"].startswith("ORPHAN_")
                and row["scope"] in {"SAFETY", "FITT", "GOAL"}
                for row in reference_issues
            ),
        },
    }
    media_goal_report = {
        "schema_version": "exercise-catalog-v2.0.2-media-goal-integrity-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": "APPROVED" if batch_approval_active and not blockers else "BLOCKED",
        "production_eligible": batch_approval_active and not blockers,
        "summary": media_goal_summary,
        "metrics": {
            "catalog_record_count": len(catalog),
            "media_mapping_row_count": len(media),
            "valid_media_mapping_count": len(media_ids & catalog_ids),
            "media_source_origin_filled_count": sum(
                bool(row.get("source_origin_code")) for row in media
            ),
            "media_source_track_filled_count": sum(bool(row.get("source_track")) for row in media),
            "media_source_identity_filled_count": sum(
                bool(row.get("source_identity")) for row in media
            ),
            "media_source_identity_validation_filled_count": sum(
                bool(row.get("source_identity_validation")) for row in media
            ),
            "media_source_origin_counts": dict(
                sorted(Counter(str(row.get("source_origin_code") or "") for row in media).items())
            ),
            "media_asset_origin_counts": dict(
                sorted(
                    Counter(str(row.get("media_source_origin_code") or "") for row in media).items()
                )
            ),
            "gymvisual_source_identity_numeric_count": sum(
                str(row.get("media_source_origin_code") or "") == "GYMVISUAL"
                and str(row.get("source_identity") or "").isdigit()
                for row in media
            ),
            "gymvisual_source_identity_invalid_count": sum(
                str(row.get("media_source_origin_code") or "") == "GYMVISUAL"
                and not str(row.get("source_identity") or "").isdigit()
                for row in media
            ),
            "missing_explicit_media_state_count": len(catalog_ids - media_ids),
            "orphan_media_id_count": len(media_ids - catalog_ids),
            "variant_shared_representative_source_media_count": len(shared_reference_variants),
            "goal_link_row_count": len(goals),
            "goal_linked_catalog_record_count": len(
                {row["exercise_stable_code"] for row in goals} & catalog_codes
            ),
            "goal_orphan_stable_code_count": len(
                {row["exercise_stable_code"] for row in goals} - catalog_codes
            ),
        },
        "auto_fixable": [
            row for row in media_goal_issues if row["classification"] == "AUTO_FIXABLE"
        ],
        "human_review_required": [
            row for row in media_goal_issues if row["classification"] == "HUMAN_REVIEW_REQUIRED"
        ],
    }
    alternative_report = {
        "schema_version": "exercise-catalog-v2.0.2-integrated-alternative-integrity-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": "APPROVED" if batch_approval_active and not blockers else "BLOCKED",
        "production_eligible": batch_approval_active and not blockers,
        "summary": alternative_summary,
        "metrics": {
            "resolved_relation_count": len(alternatives),
            "pain_condition_relation_count": sum(
                bool(row.get("pain_discomfort_area_code") and row.get("condition_code"))
                for row in alternatives
            ),
            "non_pain_reason_relation_count": forbidden_reason_rows,
            "source_outside_catalog_count": sum(
                row.get("source_exercise_id") not in catalog_ids for row in alternatives
            ),
            "target_outside_catalog_count": sum(
                row.get("target_exercise_id") not in catalog_ids for row in alternatives
            ),
            "target_outside_catalog_unique_exercise_count": len(
                {
                    row.get("target_exercise_id")
                    for row in alternatives
                    if row.get("target_exercise_id") not in catalog_ids
                }
            ),
            # The final catalog is the DB load authority.  Count all 75
            # catalog identities, including safe Variants restored from the
            # prune report, rather than only the auxiliary safe-variant file.
            "safe_variant_registry_count": sum(
                row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT"
                for row in catalog
            ),
            "duplicate_natural_key_count": len(duplicates),
            "review_required_relation_count": sum(
                row.get("review_status_code") != "DOMAIN_APPROVED" for row in alternatives
            ),
            "production_eligible_relation_count": sum(
                bool(row.get("production_eligible")) for row in alternatives
            ),
            "difficulty_policy_added_relation_count": len(added_relation_ids),
            "difficulty_policy_removed_relation_count": len(removed_relation_ids),
        },
        "auto_fixable": [
            row for row in alternative_issues if row["classification"] == "AUTO_FIXABLE"
        ],
        "human_review_required": [
            row for row in alternative_issues if row["classification"] == "HUMAN_REVIEW_REQUIRED"
        ],
        "invariants": {
            "pain_response_relations_only": forbidden_reason_rows == 0,
            "no_equipment_location_difficulty_or_variant_reason": forbidden_reason_rows == 0,
            "all_source_targets_in_integrated_catalog": all(
                row.get("source_exercise_id") in catalog_ids
                and row.get("target_exercise_id") in catalog_ids
                for row in alternatives
            ),
            "no_duplicate_natural_key": not duplicates,
        },
    }
    blocker_report = {
        "schema_version": "exercise-catalog-v2.0.2-production-blockers-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": "APPROVED" if batch_approval_active and not blockers else "BLOCKED",
        "production_eligible": batch_approval_active and not blockers,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "problem_counts_by_record_type": {
            kind: {
                "catalog_record_count": catalog_count_by_type.get(kind, 0),
                "reference_finding_count": reference_summary["by_record_type"][kind][
                    "finding_count"
                ],
                "reference_affected_exercise_count": reference_summary["by_record_type"][kind][
                    "affected_exercise_count"
                ],
                "media_goal_finding_count": media_goal_summary["by_record_type"][kind][
                    "finding_count"
                ],
                "media_goal_affected_exercise_count": media_goal_summary["by_record_type"][kind][
                    "affected_exercise_count"
                ],
                "variant_review_record_count": sum(
                    row["record_type"] == kind for row in variant_review
                ),
                "alternative_finding_count": alternative_summary["by_record_type"][kind][
                    "finding_count"
                ],
                "alternative_affected_exercise_count": alternative_summary["by_record_type"][kind][
                    "affected_exercise_count"
                ],
            }
            for kind in (
                "REPRESENTATIVE",
                "PRIMARY_VARIANT",
                "SECONDARY_VARIANT",
                "SEPARATE_EXERCISE",
            )
        },
    }
    if batch_approval_active:
        for report_name in ("reference", "media_goal", "alternative", "blockers"):
            reports_value = {
                "approval_reference": batch_approval["approval_reference"],
                "approval_method_code": batch_approval["approval_method_code"],
                "approved_at": batch_approval["approved_at"],
                "approval_basis": batch_approval["approval_basis"],
                "row_level_reason_required": False,
            }
            if report_name == "reference":
                reference_report["batch_approval"] = reports_value
            elif report_name == "media_goal":
                media_goal_report["batch_approval"] = reports_value
            elif report_name == "alternative":
                alternative_report["batch_approval"] = reports_value
            else:
                blocker_report["batch_approval"] = reports_value
    return {
        "reference": reference_report,
        "variant_review": variant_review,
        "media_goal": media_goal_report,
        "alternative": alternative_report,
        "alternative_difficulty_review": alternative_difficulty_review,
        "blockers": blocker_report,
        "sources": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (
                catalog_path,
                safety_path,
                fitt_path,
                goal_path,
                alternatives_path,
                reviewed_alternatives_path,
                concern_removed_path,
                safe_variants_path,
                registry_path,
                deletion_path,
                aliases_path,
                variant_map_path,
                binding_status_path,
                media_path,
            )
        },
    }


def write_reports(output: Path, reports: dict[str, Any]) -> None:
    for key in ("reference", "media_goal", "alternative", "blockers"):
        reports[key]["source_sha256"] = reports["sources"]
    write_json(output / "reference_integrity_report_v2_0_2.json", reports["reference"])
    write_jsonl(output / "variant_safety_fitt_review_batch_v2_0_2.jsonl", reports["variant_review"])
    write_csv(output / "variant_safety_fitt_review_batch_v2_0_2.csv", reports["variant_review"])
    write_json(output / "media_goal_integrity_report_v2_0_2.json", reports["media_goal"])
    write_json(output / "alternative_integrity_report_v2_0_2.json", reports["alternative"])
    write_jsonl(
        output / "alternative_difficulty_policy_review_batch_v2_0_2.jsonl",
        reports["alternative_difficulty_review"],
    )
    write_csv(
        output / "alternative_difficulty_policy_review_batch_v2_0_2.csv",
        reports["alternative_difficulty_review"],
    )
    write_json(output / "production_blockers_v2_0_2.json", reports["blockers"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-dir", type=Path, default=FINAL)
    parser.add_argument("--draft-dir", type=Path, default=DRAFT)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    reports = build_reports(
        final_dir=args.final_dir, draft_dir=args.draft_dir, media_path=args.media
    )
    write_reports(args.output_dir, reports)
    print(
        json.dumps(
            {
                "status": reports["blockers"]["status"],
                "blocker_count": reports["blockers"]["blocker_count"],
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
