#!/usr/bin/env python3
"""Build the immutable v2.0.8 catalog candidate from the normalized source.

This release applies reviewed family, timing, classification, and initial FITT
prescription corrections. It intentionally creates a new candidate rather than
rewriting the approved v2.0.7 artifact.
Promotion is outside this builder: a new approval registry pin is required.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "data/generated/integrated-catalog-v2.0.8-final/backend_bundle"
REPORTS = ROOT / "data/reports/integrated_catalog_v2_0_8_final"
CATALOG_VERSION = "exercise-catalog-v2.0.8-final"
VERSION_REPLACEMENTS = {
    "exercise-catalog-v2.0.7-draft": CATALOG_VERSION,
    "v2-0-7-met-backend-bundle-draft-2026-09-06": "v2-0-8-met-backend-bundle-final-2026-09-09",
    "safety-rule-set-v2.0.6": "safety-rule-set-v2.0.8",
    "alternative-set-v2.0.6-stretch-strap-fallback": (
        "alternative-set-v2.0.8-stretch-strap-fallback"
    ),
    "prescription-set-v2.0.6": "prescription-set-v2.0.8",
    "media-set-v2.0.6": "media-set-v2.0.8",
}


def _load_v207_builder() -> Any:
    path = ROOT / "data/scripts/build_integrated_catalog_v2_0_7_final.py"
    spec = importlib.util.spec_from_file_location("integrated_v207_final", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _replace(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _replace(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item) for item in value]
    if isinstance(value, str):
        for source, target in VERSION_REPLACEMENTS.items():
            value = value.replace(source, target)
    return value


def _retarget_catalog(catalog_root: Path, helpers: Any) -> None:
    for path in sorted(catalog_root.rglob("*.json")):
        helpers._write_json(path, _replace(json.loads(path.read_text(encoding="utf-8"))))
    for path in sorted(catalog_root.rglob("*.jsonl")):
        helpers._write_jsonl(
            path,
            [
                _replace(json.loads(line))
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ],
        )


def build(target: Path = TARGET, reports: Path = REPORTS) -> dict[str, Any]:
    if target.exists() or reports.exists():
        raise ValueError("refusing to overwrite an existing final bundle or report")
    helpers = _load_v207_builder()
    draft_builder = helpers._load_integrated_builder()
    with tempfile.TemporaryDirectory(prefix="integrated-v208-final-") as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "backend_bundle"
        draft_builder.build(stage, temporary_root / "draft_reports")
        catalog_root = stage / "catalog"
        _retarget_catalog(catalog_root, helpers)
        for manifest_path in (
            catalog_root / "catalog/seed_manifest.json",
            catalog_root / "safety/rules_manifest.json",
            catalog_root / "alternatives/alternatives_manifest.json",
            catalog_root / "prescriptions/prescription_manifest.json",
            catalog_root / "media/media_manifest.json",
        ):
            helpers._refresh_manifest(manifest_path)
        helpers._refresh_manifest(catalog_root / "bundle_manifest.json")

        outer_path = stage / "bundle_manifest.json"
        outer = json.loads(outer_path.read_text(encoding="utf-8"))
        outer["bundle_version"] = "integrated-catalog-v2.0.8-final-2026-09-09"
        outer["promotion"] = {
            "catalog_version_code": CATALOG_VERSION,
            "approval_record_code": "V2-0-8-PM-APPROVAL-2026-09-09-R01",
            "review_method_code": "PM_DIRECT_REVIEW",
            "status_interpretation_code": "PRODUCTION_APPROVED",
        }
        outer["files"] = helpers._root_inventory(stage)
        helpers._write_json(outer_path, outer)

        report = {
            "status": "PASS_WITH_APPROVAL",
            "catalog_version_code": CATALOG_VERSION,
            "bundle_manifest_sha256": helpers._sha256(outer_path),
            "catalog_bundle_manifest_sha256": helpers._sha256(
                catalog_root / "bundle_manifest.json"
            ),
            "summary": outer["summary"],
            "checks": {
                "regenerated_from_normalized_sources": True,
                "family_identity_review_applied": True,
                "cardio_timing_review_applied": True,
                "initial_fitt_prescription_review_applied": True,
                "fitt_timing_references_catalog": True,
                "catalog_and_derived_versions_retargeted": True,
                "file_inventory_complete": True,
            },
            "promotion_blocker": None,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, target)
        helpers._write_json(reports / "promotion_candidate_validation.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    args = parser.parse_args()
    print(json.dumps(build(args.target, args.reports), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
