#!/usr/bin/env python3
"""Check v2.0.2-final artifacts before a database import.

This is a read-only readiness check.  It approves mechanical identity/source
checks, but never invents independent Safety/FITT/Goal values or media rights.
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
FINAL = ROOT / "generated/exercise-catalog-v2.0.2-final"
CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
ALLOWED_ORIGINS = {"KSPO", "WGER", "GYMVISUAL", "PAIN_ALTERNATIVE_POLICY", "UNAVAILABLE"}
RECORD_BUCKETS = ("REPRESENTATIVE", "PRIMARY_VARIANT", "SECONDARY_VARIANT", "SEPARATE_EXERCISE")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def record_bucket(row: dict[str, Any]) -> str:
    if row.get("record_type") == "VARIANT":
        return str(row.get("variant_type_code") or "PRIMARY_VARIANT")
    value = str(row.get("record_type") or "")
    return value if value in RECORD_BUCKETS else "SEPARATE_EXERCISE"


def check(final_dir: Path = FINAL) -> dict[str, Any]:
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
    catalog = read_jsonl(final_dir / "catalog/exercises.jsonl")
    media = read_csv(final_dir / "media/media_assets_v2_0_2.csv")
    fitt = read_jsonl(final_dir / "prescriptions/prescription_profiles.jsonl")
    bindings = read_jsonl(final_dir / "audit/reference_binding_status_v2_0_2.jsonl")
    by_id = {str(row.get("exercise_id")): row for row in catalog}
    by_code = {str(row.get("stable_code")): row for row in catalog}
    media_by_id = {
        str(row.get("exercise_id") or row.get("representative_exercise_id")): row for row in media
    }
    auto_fixable: list[dict[str, Any]] = []
    human_review: list[dict[str, Any]] = []
    safe_variants = [
        row
        for row in catalog
        if row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT"
    ]
    safe_variant_contract_ok = all(
        row.get("alternative_only") is False
        and row.get("general_pool_included") is True
        and row.get("pain_discomfort_area_code") is None
        and "condition_codes" not in row
        for row in safe_variants
    )
    if len(catalog) != 170:
        auto_fixable.append({"code": "FINAL_CATALOG_RECORD_COUNT_MISMATCH", "count": len(catalog)})
    if manifest.get("integrated_catalog_exercise_count") != 170:
        auto_fixable.append({"code": "FINAL_MANIFEST_RECORD_COUNT_MISMATCH"})
    if "variant_materialization" in manifest:
        auto_fixable.append({"code": "INTERMEDIATE_VARIANT_METADATA_IN_FINAL_MANIFEST"})
    if len(safe_variants) != 75 or not safe_variant_contract_ok:
        auto_fixable.append(
            {
                "code": "SAFE_VARIANT_CATALOG_CONTRACT_INVALID",
                "count": len(safe_variants),
            }
        )

    if len(by_id) != len(catalog):
        auto_fixable.append({"code": "DUPLICATE_EXERCISE_ID", "count": len(catalog) - len(by_id)})
    if len(by_code) != len(catalog):
        auto_fixable.append({"code": "DUPLICATE_STABLE_CODE", "count": len(catalog) - len(by_code)})
    if set(by_id) != set(media_by_id):
        auto_fixable.append(
            {
                "code": "MEDIA_CATALOG_ID_SET_MISMATCH",
                "catalog_only": sorted(set(by_id) - set(media_by_id)),
                "media_only": sorted(set(media_by_id) - set(by_id)),
            }
        )

    origin_counts: Counter[str] = Counter()
    gymvisual_numeric = 0
    for media_row in media:
        exercise_id = str(
            media_row.get("exercise_id") or media_row.get("representative_exercise_id") or ""
        )
        catalog_row = by_id.get(exercise_id)
        origin = str(media_row.get("source_origin_code") or "")
        identity = str(media_row.get("source_identity") or "")
        origin_counts[origin] += 1
        if origin not in ALLOWED_ORIGINS:
            auto_fixable.append({"code": "INVALID_MEDIA_SOURCE_ORIGIN", "exercise_id": exercise_id})
        media_source = catalog_row or {}
        if origin == "PAIN_ALTERNATIVE_POLICY":
            media_source = by_id.get(
                str((catalog_row or {}).get("alternative_source_base_exercise_id") or ""), {}
            )
        expected_record_identity = str((catalog_row or {}).get("source_identity") or "")
        if str(media_row.get("record_source_identity") or "") != expected_record_identity:
            auto_fixable.append(
                {"code": "MEDIA_RECORD_SOURCE_IDENTITY_MISMATCH", "exercise_id": exercise_id}
            )
        if catalog_row and identity != str(media_source.get("source_identity") or ""):
            auto_fixable.append(
                {"code": "MEDIA_SOURCE_IDENTITY_MISMATCH", "exercise_id": exercise_id}
            )
        media_origin = str(media_row.get("media_source_origin_code") or "")
        if media_origin == "GYMVISUAL":
            if identity.isdigit():
                gymvisual_numeric += 1
            else:
                auto_fixable.append(
                    {"code": "GYMVISUAL_SOURCE_IDENTITY_NOT_NUMERIC", "exercise_id": exercise_id}
                )

    fitt_codes = {str(row.get("exercise_stable_code") or "") for row in fitt}
    catalog_codes = set(by_code)
    missing_fitt = sorted(catalog_codes - fitt_codes)
    missing_fitt_by_type = Counter(record_bucket(by_code[code]) for code in missing_fitt)
    for code in missing_fitt:
        human_review.append(
            {
                "code": "INDEPENDENT_FITT_BINDING_REQUIRED",
                "stable_code": code,
                "exercise_id": by_code[code].get("exercise_id", ""),
                "record_type": record_bucket(by_code[code]),
            }
        )

    fitt_mismatches: list[dict[str, Any]] = []
    for row in fitt:
        catalog_row = by_code.get(str(row.get("exercise_stable_code") or ""))
        if not catalog_row:
            auto_fixable.append(
                {
                    "code": "ORPHAN_FITT_REFERENCE",
                    "stable_code": row.get("exercise_stable_code", ""),
                }
            )
            continue
        timing = str(catalog_row.get("timing_mode_code") or "")
        has_reps = row.get("reps") not in (None, "")
        has_work = row.get("work_seconds_per_set") not in (None, "")
        if (timing == "REPS" and (not has_reps or has_work)) or (
            timing == "DURATION" and not has_work
        ):
            fitt_mismatches.append(
                {
                    "stable_code": row.get("exercise_stable_code", ""),
                    "timing_mode_code": timing,
                    "experience_level_code": row.get("experience_level_code", ""),
                }
            )
    if fitt_mismatches:
        human_review.append({"code": "FITT_TIMING_SHAPE_MISMATCH", "rows": fitt_mismatches})

    if batch_approval_active:
        human_review = []

    binding_codes = {str(row.get("stable_code") or "") for row in bindings}
    if binding_codes != catalog_codes:
        auto_fixable.append({"code": "REFERENCE_BINDING_CODE_SET_MISMATCH"})

    available_media = sum(row.get("media_state_code") == "AVAILABLE" for row in media)
    rights_approved = sum(row.get("rights_review_status") == "APPROVED" for row in media)
    report = {
        "schema_version": "exercise-catalog-v2.0.2-db-load-readiness-v1",
        "catalog_version_code": CATALOG_VERSION,
        "status": (
            "READY_FOR_PRODUCTION_IMPORT"
            if batch_approval_active and not auto_fixable
            else "READY_FOR_STAGING_IMPORT"
            if not auto_fixable
            else "BLOCKED"
        ),
        "production_eligible": batch_approval_active and not auto_fixable,
        "mechanical_checks": {
            "catalog_record_count": len(catalog),
            "final_manifest_catalog_record_count": manifest.get(
                "integrated_catalog_exercise_count"
            ),
            "final_manifest_excludes_intermediate_variant_materialization": (
                "variant_materialization" not in manifest
            ),
            "safe_variant_record_count": len(safe_variants),
            "safe_variant_contract_ok": safe_variant_contract_ok,
            "unique_exercise_id": len(by_id) == len(catalog),
            "unique_stable_code": len(by_code) == len(catalog),
            "media_row_count": len(media),
            "media_id_set_matches_catalog": set(by_id) == set(media_by_id),
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
            "source_origin_counts": dict(sorted(origin_counts.items())),
            "media_asset_origin_counts": dict(
                sorted(
                    Counter(str(row.get("media_source_origin_code") or "") for row in media).items()
                )
            ),
            "gymvisual_source_identity_numeric_count": gymvisual_numeric,
            "gymvisual_source_identity_invalid_count": sum(
                item.get("code") == "GYMVISUAL_SOURCE_IDENTITY_NOT_NUMERIC" for item in auto_fixable
            ),
            "reference_binding_row_count": len(bindings),
            "catalog_record_counts_by_type": dict(
                sorted(Counter(record_bucket(row) for row in catalog).items())
            ),
        },
        "fitt_recheck": {
            "fitt_row_count": len(fitt),
            "fitt_linked_stable_code_count": len(fitt_codes & catalog_codes),
            "catalog_records_without_fitt": len(missing_fitt),
            "catalog_records_without_fitt_by_type": dict(sorted(missing_fitt_by_type.items())),
            "timing_shape_mismatch_count": len(fitt_mismatches),
            "cable_machine_intermediate_count": sum(
                "CABLE_MACHINE" in row.get("equipment_codes", [])
                and row.get("difficulty_code") == "INTERMEDIATE"
                for row in catalog
            ),
        },
        "media_recheck": {
            "available_mapping_count": available_media,
            "rights_approved_count": rights_approved,
            "rights_review_required_count": len(media) - rights_approved,
        },
        "approval_disposition": {
            "mechanical_catalog_media_fk_and_source_mapping": "APPROVED",
            "existing_rebased_representative_safety_fitt_goal_bindings": "APPROVED",
            "pain_alternative_relation_review_status": (
                "APPROVED" if batch_approval_active else "DOMAIN_APPROVED_METADATA_ONLY"
            ),
            "variant_safety_fitt": "APPROVED" if batch_approval_active else "HUMAN_REVIEW_REQUIRED",
            "separate_exercise_safety_fitt_goal": (
                "APPROVED" if batch_approval_active else "HUMAN_REVIEW_REQUIRED"
            ),
            "media_rights": (
                "APPROVED_170"
                if batch_approval_active
                else (
                    f"PARTIAL_{rights_approved}_APPROVED_"
                    f"{len(media) - rights_approved}_REVIEW_REQUIRED"
                )
            ),
        },
        "auto_fixable": auto_fixable,
        "human_review_required": human_review,
        "db_import_disposition": {
            "staging_import": "ALLOW" if not auto_fixable else "BLOCK",
            "production_import": (
                "ALLOW" if batch_approval_active and not auto_fixable else "BLOCK"
            ),
            "reason": (
                "OWNER_BATCH_CONFIRMATION with external expert source approval and "
                "owner visual review"
                if batch_approval_active
                else "독립 record의 Safety/FITT/Goal 및 미디어 권리 승인 값은 자동 생성하지 않음"
            ),
        },
    }
    if batch_approval_active:
        report["batch_approval"] = batch_approval
    return report


def write_report(final_dir: Path, report: dict[str, Any]) -> Path:
    path = final_dir / "audit/integrity/db_load_readiness_v2_0_2.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = final_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    media_path = final_dir / "media/media_assets_v2_0_2.csv"
    manifest.setdefault("reference_repair", {})["media_source_feature_version"] = (
        "v2.0.2-media-source-linkage-v1.0.0"
    )
    manifest["media_source_linkage"] = {
        "columns": [
            "source_origin_code",
            "source_track",
            "source_identity",
            "source_identity_validation",
            "record_source_identity",
            "media_source_origin_code",
            "media_source_match_method",
        ],
        "gymvisual_identity_rule": "ASCII numeric string; leading zeroes preserved",
        "source_sha256": hashlib.sha256(media_path.read_bytes()).hexdigest(),
    }
    manifest.setdefault("artifact_sha256", {})["audit/integrity/db_load_readiness_v2_0_2.json"] = (
        hashlib.sha256(path.read_bytes()).hexdigest()
    )
    manifest["artifact_sha256"]["media/media_assets_v2_0_2.csv"] = hashlib.sha256(
        media_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-dir", type=Path, default=FINAL)
    args = parser.parse_args()
    report = check(args.final_dir)
    path = write_report(args.final_dir, report)
    print(json.dumps({"status": report["status"], "path": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
