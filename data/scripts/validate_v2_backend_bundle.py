"""Validate V2 backend bundle integrity, stable-code FKs, and DRAFT gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from backend.app.modules.catalog.service import (
        _validate_bundle_exercise_references,
        load_alternative_artifact,
        load_catalog_artifact,
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
    expected_paths = {
        "catalog": "catalog/seed_manifest.json",
        "safety": "safety/rules_manifest.json",
        "alternatives": "alternatives/alternatives_manifest.json",
        "prescriptions": "prescriptions/prescription_manifest.json",
    }
    if bundle_manifest.get("importer_paths") != expected_paths:
        raise PipelineError("V2 bundle importer paths do not match the backend contract")
    for entry in bundle_manifest.get("files", []):
        path = bundle / entry["path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or _sha256(path) != entry["sha256"]
        ):
            raise PipelineError(f"V2 bundle file hash or byte count mismatch: {entry['path']}")

    taxonomy_hash = _sha256(bundle / "catalog/input/exercise_taxonomy_codes.json")
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
    if len(stable_codes) != 102:
        raise PipelineError("V2 catalog must contain 102 unique stable codes")
    for safety_record in safety.records:
        if (
            safety_record.exercise_stable_code is not None
            and safety_record.exercise_stable_code not in stable_codes
        ):
            raise PipelineError(f"safety rule FK is missing: {safety_record.exercise_stable_code}")
    relation_keys: set[tuple[str, str, str, str, str]] = set()
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
        )
        if key in relation_keys:
            raise PipelineError(f"duplicate alternative relation: {key}")
        relation_keys.add(key)
    goal_keys = {
        (record.catalog_version_code, record.exercise_stable_code, record.goal_code)
        for record in prescriptions.goal_tag_records
    }
    if len(goal_keys) != 102:
        raise PipelineError("V2 goal tag FK set must contain 102 unique records")
    for prescription_record in prescriptions.prescription_records:
        if (
            prescription_record.catalog_version_code,
            prescription_record.exercise_stable_code,
            prescription_record.goal_code,
        ) not in goal_keys:
            raise PipelineError("prescription profile is missing its goal tag FK")
    counts = {
        "catalog_records": len(catalog.records),
        "safety_rule_records": len(safety.records),
        "alternative_records": len(alternatives.records),
        "goal_tag_records": len(prescriptions.goal_tag_records),
        "prescription_records": len(prescriptions.prescription_records),
        "production_eligible": False,
    }
    if counts != {**bundle_manifest["summary"], "production_eligible": False}:
        raise PipelineError("V2 bundle summary counts do not match loaded records")
    projection = bundle_manifest.get("projection", {})
    conflict_report = bundle / projection.get("conflict_report_path", "")
    if (
        projection.get("status") != "DIRECT"
        or projection.get("runtime_alternative_records") != 285
        or projection.get("importer_alternative_records") != len(alternatives.records)
        or projection.get("alternative_conflict_count") != 0
        or not conflict_report.is_file()
    ):
        raise PipelineError("V2 alternative projection blocker metadata is incomplete")
    conflict_data = json.loads(conflict_report.read_text(encoding="utf-8"))
    if (
        conflict_data.get("conflict_count") != 0
        or conflict_data.get("projection_status") != "DIRECT"
        or conflict_data.get("production_eligible") is not False
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
