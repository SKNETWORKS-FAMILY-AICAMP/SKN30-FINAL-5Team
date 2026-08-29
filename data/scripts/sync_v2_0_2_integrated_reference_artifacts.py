#!/usr/bin/env python3
"""Apply only mechanical v2.0.2-final catalog reference repairs.

This script deliberately does *not* create Safety rules, FITT prescriptions,
Goal roles, medical Alternative approvals, or media-rights approvals.  It
rebases existing approved/draft links to the current stable-code identity and
emits explicit ``REVIEW_REQUIRED`` state rows where an independent record has
no reviewed binding.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.scripts.v2_0_2_difficulty_policy import apply_difficulty_policy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "generated/exercise-catalog-v2.0.2-final"
AUDIT = FINAL / "audit"
DRAFT = ROOT / "generated/exercise-catalog-v2.0.2-draft"
LEGACY_MEDIA = ROOT / "generated/exercise-catalog-v2.0.1-final/media_assets_v2_final.csv"
CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
GENERATED_AT = "2026-08-28T00:00:00+09:00"
REPAIR_VERSION = "v2.0.2-final-mechanical-reference-repair-v1.0.0"
MEDIA_SOURCE_FEATURE_VERSION = "v2.0.2-media-source-linkage-v1.0.0"


class ReferenceRepairError(ValueError):
    """Raised when a mechanical repair would hide an unresolved reference."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceRepairError(f"cannot read JSONL: {path}") from error


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceRepairError(f"cannot read JSON: {path}") from error
    if not isinstance(value, dict):
        raise ReferenceRepairError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [
                {key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)
            ]
    except OSError as error:
        raise ReferenceRepairError(f"cannot read CSV: {path}") from error


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
        writer.writerows({key: csv_value(row.get(key)) for key in fields} for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_code_migrations(aliases: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    mappings: dict[str, str] = {}
    retired: set[str] = set()
    for row in aliases:
        if str(row.get("field_name")) != "stable_code":
            continue
        before = str(row.get("stable_code_before") or "")
        after = str(row.get("stable_code_after") or "")
        if before and after and before != after:
            mappings[before] = after
        elif before and not after:
            retired.add(before)
    return mappings, retired


def safe_variant_record(safe: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Convert the already review-gated alternative target to one catalog row.

    The no-load posture/support instructions come from the existing safe-variant
    artifact.  Defaults and bindable Safety/FITT/Goal values are intentionally
    left absent; assigning them would be a domain decision.
    """
    safe_id = str(safe["exercise_id"])
    difficulty_code, difficulty_policy_rule_code = apply_difficulty_policy(
        {
            "stable_code": str(safe["stable_code"]),
            "equipment_codes": list(safe["equipment_codes"]),
        },
        str(safe["difficulty_code"]),
    )
    return {
        "exercise_id": safe_id,
        "legacy_exercise_id": "",
        "record_type": "SEPARATE_EXERCISE",
        "catalog_version_code": CATALOG_VERSION,
        "stable_code": str(safe["stable_code"]),
        "name_ko": str(safe["name_ko"]),
        "display_name_ko": str(safe["name_ko"]),
        "name_en": "",
        "family_code": str(base["family_code"]),
        "representative_exercise_id": "",
        "variant_type_code": "",
        "is_representative": False,
        "training_type_code": str(safe["training_type_code"]),
        "body_focus_code": str(base.get("body_focus_code") or ""),
        "primary_movement_pattern_code": str(safe["primary_movement_pattern_code"]),
        "primary_body_area_codes": list(safe["primary_body_area_codes"]),
        "secondary_body_area_codes": list(safe["secondary_body_area_codes"]),
        "equipment_codes": list(safe["equipment_codes"]),
        "support_equipment_codes": list(safe.get("support_equipment_codes", [])),
        "location_codes": list(safe["location_codes"]),
        "difficulty_code": difficulty_code,
        "difficulty_policy_rule_code": difficulty_policy_rule_code,
        "difficulty_status": "REVIEW_REQUIRED",
        "timing_mode_code": str(safe["timing_mode_code"]),
        "phase_codes": [],
        "default_seconds_per_rep": None,
        "default_work_seconds": None,
        "default_rest_seconds": None,
        "default_transition_seconds": None,
        "instruction_summary_ko": str(safe["instruction_summary_ko"]),
        "form_cues_ko": list(safe["form_cues_ko"]),
        "setup_condition_ko": "통증 부위 비부하를 위한 지정 지지 장비와 안정적인 공간을 준비한다.",
        "source_track": "pain_alternative_policy",
        "source_identity": safe_id,
        "source_key": f"pain_alternative_policy:{safe_id}",
        "source_system": "pain_alternative_policy",
        "source_record_id": safe_id,
        "source_name": str(safe["name_ko"]),
        "source_name_en": "",
        "source_name_ko": str(safe["name_ko"]),
        "source_url": "",
        "source_author": "",
        "source_license": "",
        "source_media_reference": "",
        "source_media_id": "",
        "source_instruction_en": "",
        "source_instruction_steps_en": "",
        "source_provenance_status": "DERIVED_POLICY_REVIEW_REQUIRED",
        "review_status_code": "REVIEW_REQUIRED",
        "review_required": True,
        "review_required_codes": [
            "ALTERNATIVE_TARGET_AND_GENERAL_POOL",
            "PAIN_ALTERNATIVE_DOMAIN_APPROVAL_REQUIRED",
            "INDEPENDENT_SAFETY_RULE_REVIEW_REQUIRED",
            "INDEPENDENT_FITT_REVIEW_REQUIRED",
            "GOAL_ROLE_REVIEW_REQUIRED",
            "MEDIA_RIGHTS_REVIEW_REQUIRED",
        ],
        "production_eligible": False,
        "recovery_eligible": bool(safe["recovery_eligible"]),
        "canonical_status": "PAIN_ALTERNATIVE_TARGET_REVIEW_REQUIRED",
        "canonical_decision_code": "SEPARATE_EXERCISE_PAIN_SAFE_VARIANT",
        "canonical_decision_source": "CONCERN_RESOLUTION_POLICY_REVIEW",
        "canonical_decision_note_ko": (
            "통증 Alternative target이면서 일반 운동 풀에도 포함한다."
        ),
        "variant_relation_status_code": "NOT_APPLICABLE",
        "variant_materialization_status_code": "NOT_APPLICABLE",
        "safety_mapping_status_code": "REVIEW_REQUIRED",
        "safety_mapping_source_representative_exercise_id": "",
        "safety_rule_binding_status_code": "PENDING_INDEPENDENT_PAIN_VARIANT_SAFETY_REVIEW",
        "fitt_mapping_status_code": "REVIEW_REQUIRED",
        "fitt_mapping_source_representative_exercise_id": "",
        "fitt_template_ids_by_experience": {},
        "fitt_allowed_experience_level_codes": [],
        # A pain-safe variant is an independently executable exercise and may
        # appear in the ordinary pool when no discomfort is reported.  NRS
        # conditions belong only to the directed Alternative relation, not to
        # this catalog identity.
        "alternative_only": False,
        "general_pool_included": True,
        "general_pool_inclusion_reason_code": "INDEPENDENT_SAFE_VARIANT_GENERAL_POOL",
        "alternative_relation_code": str(
            safe.get("variant_relation_code")
            or safe.get("alternative_relation_code")
            or "PAIN_AREA_NO_LOAD_SAFE_VARIANT"
        ),
        "alternative_source_base_exercise_id": str(safe["base_exercise_id"]),
        "alternative_source_base_stable_code": str(safe["base_exercise_stable_code"]),
        # Pain area and NRS conditions belong only to the directed
        # exercise_alternatives relation, never to this exercise row.
        "pain_discomfort_area_code": None,
        "pain_area_load_guard_codes": list(safe["pain_area_load_guard_codes"]),
        "fixed_posture_code": str(safe["fixed_posture_code"]),
        "fixed_support_code": str(safe["fixed_support_code"]),
        "stop_guard_code": str(safe["stop_guard_code"]),
        "original_posture_instructions_replaced": bool(
            safe["original_posture_instructions_replaced"]
        ),
        "alternative_policy_version": str(
            safe.get("policy_version")
            or safe.get("alternative_policy_version")
            or "discomfort-alternative-concern-resolution-v2.0.2-v1.0.0"
        ),
    }


def integrate_safe_variants(
    catalog: list[dict[str, Any]], safe_variants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def normalize_general_pool_safe_variant(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("alternative_relation_code") != "PAIN_AREA_NO_LOAD_SAFE_VARIANT":
            return row
        normalized = deepcopy(row)
        normalized["alternative_only"] = False
        normalized["general_pool_included"] = True
        normalized["general_pool_inclusion_reason_code"] = (
            "INDEPENDENT_SAFE_VARIANT_GENERAL_POOL"
        )
        # NRS applicability is a property of the Alternative edge.  Keeping it
        # on the exercise turns one executable movement into several implicit
        # condition-scoped catalog identities.
        normalized.pop("condition_codes", None)
        normalized["pain_discomfort_area_code"] = None
        return normalized

    ordinary = [
        normalize_general_pool_safe_variant(row)
        for row in catalog
        if not row.get("alternative_only") or row.get("general_pool_included")
    ]
    base_by_id = {str(row["exercise_id"]): row for row in ordinary}
    records: list[dict[str, Any]] = list(ordinary)
    for safe in safe_variants:
        base_id = str(safe["base_exercise_id"])
        base = base_by_id.get(base_id)
        if base is None:
            raise ReferenceRepairError(f"safe Variant base exercise missing: {base_id}")
        if str(safe.get("exercise_id") or "") in {
            str(row.get("exercise_id") or "") for row in records
        }:
            continue
        records.append(safe_variant_record(safe, base))
    ids = [str(row.get("exercise_id") or "") for row in records]
    codes = [str(row.get("stable_code") or "") for row in records]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ReferenceRepairError("integrated catalog has blank or duplicate exercise_id")
    if not all(codes) or len(codes) != len(set(codes)):
        raise ReferenceRepairError("integrated catalog has blank or duplicate stable_code")
    return sorted(records, key=lambda row: str(row["exercise_id"]))


def rebase_reference_rows(
    rows: list[dict[str, Any]],
    catalog_codes: set[str],
    migrations: dict[str, str],
    retired: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for original in rows:
        row = deepcopy(original)
        old = str(row.get("exercise_stable_code") or "")
        current = migrations.get(old, old)
        if old in migrations:
            row["exercise_stable_code"] = current
            counts["remapped_stable_code_reference"] += 1
        if current not in catalog_codes:
            if old in retired or current in retired:
                counts["removed_retired_reference"] += 1
            else:
                counts["removed_orphan_reference"] += 1
            continue
        row["catalog_version_code"] = CATALOG_VERSION
        row.setdefault("reference_rebase_version", REPAIR_VERSION)
        kept.append(row)
    return kept, dict(sorted(counts.items()))


def make_registry(
    catalog: list[dict[str, Any]], prior: dict[str, Any], prior_active_stale_codes: set[str]
) -> dict[str, Any]:
    previous = {str(row.get("stable_code")): row for row in prior.get("records", [])}
    records: list[dict[str, Any]] = []
    for row in catalog:
        old = previous.get(str(row["stable_code"]), {})
        records.append(
            {
                "exercise_id": row["exercise_id"],
                "representative_exercise_id": (
                    row["exercise_id"] if row.get("record_type") == "REPRESENTATIVE" else ""
                ),
                "stable_code": row["stable_code"],
                "status": "ACTIVE_CATALOG_RECORD",
                "record_type": row["record_type"],
                "family_code": row["family_code"],
                "source_track": row.get("source_track", ""),
                "source_identity": row.get("source_identity", ""),
                "source_keys": old.get("source_keys", [row.get("source_key", "")]),
                "name_ko": row.get("name_ko", ""),
                "name_en": row.get("name_en", ""),
                "decision_source": row.get("canonical_decision_source", ""),
                "decision_code": row.get("canonical_decision_code", ""),
            }
        )
    return {
        "schema_version": "1.1",
        "registry_version": REPAIR_VERSION,
        "catalog_version_code": CATALOG_VERSION,
        "active_stable_code_count": len(records),
        "retired_stable_code_count": len(prior_active_stale_codes),
        "stable_code_count": len(records),
        "records": sorted(records, key=lambda row: str(row["stable_code"])),
    }


def explicit_bindings(
    catalog: list[dict[str, Any]],
    safety: list[dict[str, Any]],
    fitt: list[dict[str, Any]],
    goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    safety_codes = {str(row["exercise_stable_code"]) for row in safety}
    fitt_codes = {str(row["exercise_stable_code"]) for row in fitt}
    goal_codes = {str(row["exercise_stable_code"]) for row in goals}
    rows: list[dict[str, Any]] = []
    for row in catalog:
        code = str(row["stable_code"])
        rows.append(
            {
                "exercise_id": row["exercise_id"],
                "stable_code": code,
                "record_type": row["record_type"],
                "safety_binding_state_code": "AVAILABLE"
                if code in safety_codes
                else "REVIEW_REQUIRED",
                "fitt_binding_state_code": "AVAILABLE" if code in fitt_codes else "REVIEW_REQUIRED",
                "goal_binding_state_code": "AVAILABLE" if code in goal_codes else "REVIEW_REQUIRED",
                "binding_state_reason_code": (
                    "EXISTING_REBASED_REFERENCE"
                    if code in safety_codes | fitt_codes | goal_codes
                    else "INDEPENDENT_RECORD_REVIEW_REQUIRED"
                ),
                "production_eligible": False,
            }
        )
    return rows


def media_rows(
    catalog: list[dict[str, Any]], old_rows: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_id = {str(row.get("representative_exercise_id") or ""): row for row in old_rows}
    catalog_by_id = {str(row.get("exercise_id") or ""): row for row in catalog}
    name_matches: dict[str, list[dict[str, Any]]] = {}
    for row in catalog:
        if row.get("source_track") == "pain_alternative_policy":
            continue
        name_matches.setdefault(str(row.get("name_ko") or ""), []).append(row)
    known_ids = {str(row["exercise_id"]) for row in catalog}
    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for exercise in catalog:
        exercise_id = str(exercise["exercise_id"])
        old = by_id.get(exercise_id)
        source_track = str(exercise.get("source_track") or "")
        source_origin_code = {
            "kspo": "KSPO",
            "wger": "WGER",
            "gymvisual": "GYMVISUAL",
            "pain_alternative_policy": "PAIN_ALTERNATIVE_POLICY",
        }.get(source_track, "UNAVAILABLE")
        record_source_identity = str(exercise.get("source_identity") or "")
        media_source = exercise
        media_source_match_method = "SELF_CATALOG_SOURCE"
        if source_track == "pain_alternative_policy":
            # Pain-safe records keep the policy as record provenance, but their
            # media identity comes from the matching integrated exercise.  The
            # explicit base link is the deterministic fallback when display
            # names differ (e.g. shortened Korean pain-safe names).
            candidates = name_matches.get(str(exercise.get("name_ko") or ""), [])
            base = catalog_by_id.get(str(exercise.get("alternative_source_base_exercise_id") or ""))
            media_source = candidates[0] if len(candidates) == 1 else (base or {})
            media_source_match_method = (
                "EXACT_NAME_MATCH"
                if len(candidates) == 1
                else "ALTERNATIVE_BASE_EXERCISE_MATCH"
                if base
                else "NO_MEDIA_SOURCE_MATCH"
            )
        media_source_origin_code = {
            "kspo": "KSPO",
            "wger": "WGER",
            "gymvisual": "GYMVISUAL",
        }.get(str(media_source.get("source_track") or ""), "UNAVAILABLE")
        source_identity = str(media_source.get("source_identity") or "")
        source_identity_validation = (
            "VALID_NUMERIC"
            if media_source_origin_code == "GYMVISUAL" and source_identity.isdigit()
            else "MISSING_NUMERIC"
            if media_source_origin_code == "GYMVISUAL"
            else "VALID_NON_NUMERIC"
            if source_identity
            else "NO_MEDIA_SOURCE_MATCH"
        )
        if old:
            row: dict[str, Any] = dict(old)
            row.update(
                {
                    "exercise_id": exercise_id,
                    "stable_code": exercise["stable_code"],
                    "catalog_version_code": CATALOG_VERSION,
                    "source_origin_code": source_origin_code,
                    "source_track": source_track,
                    "source_identity": source_identity,
                    "source_identity_validation": source_identity_validation,
                    "record_source_identity": record_source_identity,
                    "media_source_origin_code": media_source_origin_code,
                    "media_source_match_method": media_source_match_method,
                    "media_state_code": "AVAILABLE",
                    "media_state_reason_code": "EXISTING_RECORD_SPECIFIC_MEDIA_MAPPING",
                }
            )
            counts["AVAILABLE"] += 1
        else:
            row = {
                "representative_exercise_id": exercise_id,
                "exercise_id": exercise_id,
                "stable_code": exercise["stable_code"],
                "catalog_version_code": CATALOG_VERSION,
                "source_origin_code": source_origin_code,
                "source_track": source_track,
                "source_identity": source_identity,
                "source_identity_validation": source_identity_validation,
                "record_source_identity": record_source_identity,
                "media_source_origin_code": media_source_origin_code,
                "media_source_match_method": media_source_match_method,
                "s3_key": "",
                "media_status": "REVIEW_REQUIRED",
                "media_state_code": "REVIEW_REQUIRED",
                "media_state_reason_code": "NO_RECORD_SPECIFIC_MEDIA_MAPPING",
                "s3_technical_status": "NOT_REQUESTED",
                "verified_at": "",
                "rights_review_status": "REVIEW_REQUIRED",
                "rights_reviewer": "",
                "rights_reviewed_at": "",
                "rights_evidence_reference": "",
                "production_eligibility": "false",
                "backend_visibility": "HIDDEN",
            }
            counts["REVIEW_REQUIRED"] += 1
        output.append(row)
    counts["removed_orphan_media_id"] = sum(
        bool(media_id) and media_id not in known_ids for media_id in by_id
    )
    counts["gymvisual_source_identity_valid_numeric"] = sum(
        row.get("media_source_origin_code") == "GYMVISUAL"
        and row.get("source_identity_validation") == "VALID_NUMERIC"
        for row in output
    )
    counts["gymvisual_source_identity_invalid"] = sum(
        row.get("media_source_origin_code") == "GYMVISUAL"
        and row.get("source_identity_validation") != "VALID_NUMERIC"
        for row in output
    )
    counts["media_source_origin_counts"] = dict(
        sorted(Counter(row.get("media_source_origin_code") for row in output).items())
    )
    counts["source_origin_unavailable"] = sum(
        row.get("source_origin_code") == "UNAVAILABLE" for row in output
    )
    return sorted(output, key=lambda row: str(row["exercise_id"])), dict(sorted(counts.items()))


def review_input(
    catalog: list[dict[str, Any]], bindings: list[dict[str, Any]], media: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    binding_by_code = {str(row["stable_code"]): row for row in bindings}
    media_by_code = {str(row["stable_code"]): row for row in media}
    rows: list[dict[str, Any]] = []
    for exercise in catalog:
        code = str(exercise["stable_code"])
        binding = binding_by_code[code]
        media_row = media_by_code[code]
        rows.append(
            {
                "exercise_id": exercise["exercise_id"],
                "stable_code": code,
                "name_ko": exercise["name_ko"],
                "record_type": exercise["record_type"],
                "variant_type_code": exercise.get("variant_type_code", ""),
                "difficulty_code": exercise["difficulty_code"],
                "safety_current_state": binding["safety_binding_state_code"],
                "fitt_current_state": binding["fitt_binding_state_code"],
                "goal_current_state": binding["goal_binding_state_code"],
                "media_current_state": media_row["media_state_code"],
                "rights_current_state": media_row["rights_review_status"],
                "safety_review_decision": "",
                "fitt_review_decision": "",
                "goal_review_decision": "",
                "media_rights_review_decision": "",
                "reviewer": "",
                "reviewed_at": "",
                "review_note_ko": "",
            }
        )
    return rows


def update_manifest(final: Path, artifact_paths: list[Path], catalog_count: int) -> None:
    path = final / "manifest.json"
    manifest = read_json(path)
    manifest.update(
        {
            "catalog_version_code": CATALOG_VERSION,
            "production_eligible": False,
            "integrated_catalog_exercise_count": catalog_count,
            "reference_repair": {
                "version": REPAIR_VERSION,
                "safe_variant_record_mode": "SEPARATE_EXERCISE_GENERAL_POOL_WITH_CONDITIONED_ALTERNATIVES",
                "safety_fitt_goal_values_generated": False,
                "media_rights_values_generated": False,
            },
        }
    )
    # The 201-record variant pass is review evidence stored under generated/
    # intermediate.  The final bundle is the post-pruning catalog only.
    manifest.pop("variant_materialization", None)
    artifact_hashes = manifest.setdefault("artifact_sha256", {})
    artifact_hashes.pop("../../reports/V2_0_2_VARIANT_CATALOG_INTEGRATION.md", None)
    for artifact in artifact_paths:
        artifact_hashes[str(artifact.relative_to(final))] = sha256(artifact)
    # Refresh hashes for retained evidence artifacts as well.  The final
    # manifest is the hash authority for every listed file, including review
    # evidence regenerated by an earlier v2.0.2 step.
    for relative in list(artifact_hashes):
        artifact = final / relative
        if artifact.is_file():
            artifact_hashes[relative] = sha256(artifact)
    write_json(path, manifest)


def build(
    final: Path = FINAL, draft: Path = DRAFT, legacy_media: Path = LEGACY_MEDIA
) -> dict[str, Any]:
    catalog_path = final / "catalog/exercises.jsonl"
    safe_path = final / "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl"
    aliases_path = final / "audit/alias_migration_v2_0_2.jsonl"
    deletions_path = final / "audit/canonical_deletions_v2_0_2.jsonl"
    prior_canonical_path = final / "audit/canonical_exercises_v2_final.jsonl"
    registry_path = final / "audit/stable_code_registry_v2.json"
    source_safety = draft / "runtime/safety_rules.jsonl"
    source_fitt = draft / "prescriptions/prescription_profiles.jsonl"
    source_goals = draft / "prescriptions/goal_tag_links.jsonl"

    catalog = integrate_safe_variants(read_jsonl(catalog_path), read_jsonl(safe_path))
    migrations, retired = stable_code_migrations(read_jsonl(aliases_path))
    retired.update(
        str(row["stable_code_before"])
        for row in read_jsonl(deletions_path)
        if row.get("stable_code_before")
    )
    catalog_codes = {str(row["stable_code"]) for row in catalog}
    prior_active_stale_codes = {
        str(row["stable_code"])
        for row in read_jsonl(prior_canonical_path)
        if row.get("stable_code") and str(row.get("canonical_status", "")).startswith("ACTIVE_")
    } - catalog_codes
    safety, safety_counts = rebase_reference_rows(
        read_jsonl(source_safety), catalog_codes, migrations, retired
    )
    fitt, fitt_counts = rebase_reference_rows(
        read_jsonl(source_fitt), catalog_codes, migrations, retired
    )
    goals, goal_counts = rebase_reference_rows(
        read_jsonl(source_goals), catalog_codes, migrations, retired
    )
    registry = make_registry(catalog, read_json(registry_path), prior_active_stale_codes)
    bindings = explicit_bindings(catalog, safety, fitt, goals)
    media, media_counts = media_rows(catalog, read_csv(legacy_media))
    review_rows = review_input(catalog, bindings, media)

    write_jsonl(catalog_path, catalog)
    write_csv(final / "audit/catalog/exercises.csv", catalog)
    write_jsonl(final / "audit/runtime/catalog.jsonl", catalog)
    write_json(final / "audit/stable_code_registry_v2.json", registry)
    write_jsonl(final / "runtime/safety_rules.jsonl", safety)
    write_jsonl(final / "prescriptions/prescription_profiles.jsonl", fitt)
    write_jsonl(final / "prescriptions/goal_tag_links.jsonl", goals)
    write_jsonl(final / "audit/reference_binding_status_v2_0_2.jsonl", bindings)
    write_csv(final / "audit/reference_binding_status_v2_0_2.csv", bindings)
    write_csv(final / "media/media_assets_v2_0_2.csv", media)
    write_csv(final / "audit/integrity/review_result_input_v2_0_2.csv", review_rows)

    report = {
        "schema_version": "exercise-catalog-v2.0.2-mechanical-reference-repair-v1",
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "repair_version": REPAIR_VERSION,
        "media_source_feature_version": MEDIA_SOURCE_FEATURE_VERSION,
        "production_eligible": False,
        "catalog": {
            "integrated_record_count": len(catalog),
            "safe_variant_integrated_count": sum(
                row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT"
                for row in catalog
            ),
            "record_type_counts": dict(
                sorted(Counter(row["record_type"] for row in catalog).items())
            ),
        },
        "stable_code_registry": {
            "active_catalog_record_count": registry["active_stable_code_count"],
            "removed_prior_active_code_count": registry["retired_stable_code_count"],
        },
        "reference_rebase": {"safety": safety_counts, "fitt": fitt_counts, "goal": goal_counts},
        "media": media_counts,
        "explicit_review_state": {
            "binding_rows": len(bindings),
            "review_input_rows": len(review_rows),
            "media_state_counts": dict(
                sorted(Counter(row["media_state_code"] for row in media).items())
            ),
        },
        "not_auto_modified": [
            "Safety rule or contraindication values",
            "FITT sets/reps/time/rest values",
            "Goal meaning or CORE/SUPPORT role",
            "pain Alternative domain approval",
            "Media rights approval",
        ],
    }
    report_path = final / "audit/integrity/auto_reference_repair_report_v2_0_2.json"
    write_json(report_path, report)
    update_manifest(
        final,
        [
            catalog_path,
            final / "audit/catalog/exercises.csv",
            final / "audit/runtime/catalog.jsonl",
            final / "audit/stable_code_registry_v2.json",
            final / "runtime/safety_rules.jsonl",
            final / "prescriptions/prescription_profiles.jsonl",
            final / "prescriptions/goal_tag_links.jsonl",
            final / "audit/reference_binding_status_v2_0_2.jsonl",
            final / "audit/reference_binding_status_v2_0_2.csv",
            final / "media/media_assets_v2_0_2.csv",
            final / "audit/integrity/review_result_input_v2_0_2.csv",
            final / "alternatives/resolved_discomfort_alternative_map_v2_0_2.jsonl",
            report_path,
        ],
        len(catalog),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-dir", type=Path, default=FINAL)
    parser.add_argument("--draft-dir", type=Path, default=DRAFT)
    parser.add_argument("--legacy-media", type=Path, default=LEGACY_MEDIA)
    args = parser.parse_args()
    print(json.dumps(build(args.final_dir, args.draft_dir, args.legacy_media), ensure_ascii=False))


if __name__ == "__main__":
    main()
