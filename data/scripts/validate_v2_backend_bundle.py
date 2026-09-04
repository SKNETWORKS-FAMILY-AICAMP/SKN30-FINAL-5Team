"""Validate V2 backend bundle integrity, stable-code FKs, and DRAFT gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from kspo_fitness100_pipeline import PipelineError  # noqa: E402

try:
    from backend.app.modules.catalog.service import (
        _v2_representative_registry,
        _validate_bundle_exercise_references,
        load_alternative_artifact,
        load_catalog_artifact,
        load_media_artifact,
        load_prescription_artifact,
        load_safety_rule_artifact,
    )
except ImportError as exc:  # pragma: no cover - command-line environment error
    raise RuntimeError(
        "backend catalog schemas are required to validate the importer bundle"
    ) from exc

DEFAULT_BUNDLE = (
    Path(__file__).resolve().parents[1] / "generated/exercise-catalog-v2.0.0-final/backend_bundle"
)
EXCLUDED_AUXILIARY_ARTIFACTS = {
    "data/normalized/home_equipment_substitution_guides_v1.jsonl",
    "data/normalized/dumbbell_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/foam_roller_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/resistance_band_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/stretch_strap_home_suitability_review_v1.jsonl",
    "data/reports/resistance_band_bodyweight_variant_gap_report_v1.json",
    "data/reports/home_equipment_substitution_guides_v1_validation.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_draft(value: Any, label: str) -> None:
    if isinstance(value, dict):
        if value.get("status_code") == "ACTIVE" or value.get("status") == "ACTIVE":
            raise PipelineError(f"{label} must not be ACTIVE")
        if (
            value.get("status_code") == "PRODUCTION_APPROVED"
            or value.get("status") == "PRODUCTION_APPROVED"
        ):
            raise PipelineError(f"{label} must not be PRODUCTION_APPROVED")
        if "production_eligible" in value and value["production_eligible"] is not False:
            raise PipelineError(f"{label} must remain production-ineligible")
        for key, child in value.items():
            _assert_draft(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_draft(child, f"{label}[{index}]")


def validate(bundle: Path = DEFAULT_BUNDLE) -> dict[str, Any]:
    try:
        bundle_manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("V2 bundle manifest is missing or invalid") from exc
    _assert_draft(bundle_manifest, "bundle_manifest")
    if bundle_manifest.get("status_code") != "DRAFT":
        raise PipelineError("V2 bundle status must be DRAFT")
    input_policy = bundle_manifest.get("input_policy")
    if input_policy is not None:
        if (
            not isinstance(input_policy, dict)
            or input_policy.get("canonical_catalog_source")
            != "data/normalized/v2_0_6_exercise_catalog.csv"
            or set(input_policy.get("excluded_auxiliary_artifacts", []))
            != EXCLUDED_AUXILIARY_ARTIFACTS
            or input_policy.get("excluded_reason")
            != (
                "household substitutions, cautions, and replacement exercises are "
                "not stored in equipment descriptions or alternatives"
            )
        ):
            raise PipelineError("V2 auxiliary input exclusion policy is invalid")
    expected_paths = {
        "catalog": "catalog/seed_manifest.json",
        "safety": "safety/rules_manifest.json",
        "alternatives": "alternatives/alternatives_manifest.json",
        "prescriptions": "prescriptions/prescription_manifest.json",
    }
    importer_paths = bundle_manifest.get("importer_paths")
    if (
        not isinstance(importer_paths, dict)
        or {key: importer_paths.get(key) for key in expected_paths} != expected_paths
        or set(importer_paths) - set(expected_paths) - {"media"}
    ):
        raise PipelineError("V2 bundle importer paths do not match the backend contract")
    for entry in bundle_manifest.get("files", []):
        path = bundle / entry["path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or _sha256(path) != entry["sha256"]
        ):
            raise PipelineError(f"V2 bundle file hash or byte count mismatch: {entry['path']}")

    taxonomy_path = bundle / "catalog/input/exercise_taxonomy_codes.json"
    taxonomy_hash = _sha256(taxonomy_path) if taxonomy_path.is_file() else None
    if taxonomy_hash is None:
        catalog_source = json.loads(
            (bundle / "catalog/seed_manifest.json").read_text(encoding="utf-8")
        ).get("source", {})
        taxonomy_hash = catalog_source.get("taxonomy_registry_sha256")
    if not isinstance(taxonomy_hash, str):
        raise PipelineError("V2 catalog taxonomy registry hash is missing")
    catalog = load_catalog_artifact(
        bundle / "catalog", v2_import=True, v2_taxonomy_registry_sha256=taxonomy_hash
    )
    safety = load_safety_rule_artifact(bundle / "safety")
    alternatives = load_alternative_artifact(bundle / "alternatives")
    prescriptions = load_prescription_artifact(bundle / "prescriptions")
    _validate_bundle_exercise_references(
        (catalog,), safety, alternatives, prescriptions, v2_import=True
    )
    stable_codes = {record.stable_code for record in catalog.records}
    if len(stable_codes) != len(catalog.records):
        raise PipelineError("V2 catalog contains duplicate stable codes")
    for safety_record in safety.records:
        if (
            safety_record.exercise_stable_code is not None
            and safety_record.exercise_stable_code not in stable_codes
        ):
            raise PipelineError(f"safety rule FK is missing: {safety_record.exercise_stable_code}")
    relation_keys: set[tuple[str, str, str, str, str, str | None, str | None]] = set()
    for alternative_record in alternatives.records:
        if (
            alternative_record.source_exercise_stable_code not in stable_codes
            or alternative_record.alternative_exercise_stable_code not in stable_codes
        ):
            raise PipelineError("alternative relation FK is missing")
        if (
            alternative_record.source_exercise_stable_code
            == alternative_record.alternative_exercise_stable_code
        ):
            raise PipelineError("alternative relation self-targets")
        key = (
            alternative_record.source_exercise_stable_code,
            alternative_record.alternative_exercise_stable_code,
            alternative_record.reason_code,
            alternative_record.goal_preservation_code,
            alternative_record.rule_version,
            alternative_record.condition_code,
            alternative_record.pain_discomfort_area_code,
        )
        if key in relation_keys:
            raise PipelineError(f"duplicate alternative relation: {key}")
        relation_keys.add(key)
    goal_keys = {
        (record.catalog_version_code, record.exercise_stable_code, record.goal_code)
        for record in prescriptions.goal_tag_records
    }
    if len(goal_keys) != len(prescriptions.goal_tag_records):
        raise PipelineError("V2 goal tag set contains duplicate records")
    for prescription_record in prescriptions.prescription_records:
        if (
            prescription_record.catalog_version_code,
            prescription_record.exercise_stable_code,
            prescription_record.goal_code,
        ) not in goal_keys:
            raise PipelineError("prescription profile is missing its goal tag FK")
    media = None
    if "media" in importer_paths:
        media_manifest_path = bundle / importer_paths["media"]
        media = load_media_artifact(
            media_manifest_path.parent,
            representative_to_stable_code=_v2_representative_registry(
                (bundle / importer_paths["catalog"]).parent,
                catalog,
            ),
        )
        if media.manifest.catalog_version_code != bundle_manifest["catalog_version_code"]:
            raise PipelineError("media catalog version does not match bundle catalog version")
        exact_media_coverage = bundle_manifest.get("projection", {}).get("media_coverage") == (
            "EXACT_ALL_CATALOG_RECORDS"
        )
        if exact_media_coverage and (
            set(media.exercise_stable_codes) != stable_codes
            or len(media.records) != len(stable_codes)
        ):
            raise PipelineError("media must cover every catalog stable code exactly once")
        if not set(media.exercise_stable_codes).issubset(stable_codes):
            raise PipelineError("media references an exercise absent from the catalog")
        if any(
            record.media_status != "AVAILABLE" or record.rights_review_status != "APPROVED"
            for record in media.records
        ):
            raise PipelineError("catalog media must be AVAILABLE and APPROVED")
    counts = {
        "catalog_records": len(catalog.records),
        "safety_rule_records": len(safety.records),
        "alternative_records": len(alternatives.records),
        "goal_tag_records": len(prescriptions.goal_tag_records),
        "prescription_records": len(prescriptions.prescription_records),
        "production_eligible": False,
    }
    if media is not None:
        counts["media_asset_records"] = len(media.records)
    if counts != {**bundle_manifest["summary"], "production_eligible": False}:
        raise PipelineError("V2 bundle summary counts do not match loaded records")
    projection = bundle_manifest.get("projection", {})
    conflict_report_path = projection.get("conflict_report_path")
    # DIRECT means the importer set is the runtime set: nothing is dropped or
    # merged on the way into the bundle. Pinning a literal count here only
    # records what the pipeline happened to emit on one day.
    if (
        projection.get("status") not in {"DIRECT", "DIRECT_EMPTY"}
        or projection.get("runtime_alternative_records") != len(alternatives.records)
        or projection.get("importer_alternative_records") != len(alternatives.records)
        or projection.get("alternative_conflict_count") != 0
    ):
        raise PipelineError("V2 alternative projection blocker metadata is incomplete")
    if projection.get("status") == "DIRECT_EMPTY" and not conflict_report_path:
        raise PipelineError("empty V2 alternative projection must include a conflict report")
    if projection.get("status") == "DIRECT_EMPTY" and alternatives.records:
        raise PipelineError("DIRECT_EMPTY V2 alternative projection must contain zero records")
    if conflict_report_path:
        conflict_report = bundle / conflict_report_path
        if not conflict_report.is_file():
            raise PipelineError("V2 alternative projection conflict report is missing")
        conflict_data = json.loads(conflict_report.read_text(encoding="utf-8"))
        if (
            conflict_data.get("conflict_count") != 0
            or conflict_data.get("projection_status") != "DIRECT"
            or conflict_data.get("production_eligible") is not False
            or conflict_data.get("status") != "DRAFT"
            or conflict_data.get("runtime_record_count") != len(alternatives.records)
            or conflict_data.get("importer_record_count") != len(alternatives.records)
        ):
            raise PipelineError("V2 alternative projection conflict report is invalid")
    return {"status": "valid", **counts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, nargs="?", default=DEFAULT_BUNDLE)
    args = parser.parse_args(argv)
    try:
        report = validate(args.bundle)
    except (OSError, PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
