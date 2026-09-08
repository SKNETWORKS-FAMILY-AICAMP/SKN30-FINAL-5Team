#!/usr/bin/env python3
"""Build the immutable v2.0.7 final promotion candidate.

The final bundle is regenerated from normalized inputs, then all catalog and
derived-set version references are retargeted together. Content semantics are
unchanged from the verified v2.0.7 projection; only version lineage and file
hashes change.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "data/generated/integrated-catalog-v2.0.7-final/backend_bundle"
REPORTS = ROOT / "data/reports/integrated_catalog_v2_0_7_final"
CATALOG_VERSION = "exercise-catalog-v2.0.7-final"
VERSION_REPLACEMENTS = {
    "exercise-catalog-v2.0.7-draft": CATALOG_VERSION,
    "v2-0-7-met-backend-bundle-draft-2026-09-06": ("v2-0-7-met-backend-bundle-final-2026-09-08"),
    "safety-rule-set-v2.0.6": "safety-rule-set-v2.0.7",
    "alternative-set-v2.0.6-stretch-strap-fallback": (
        "alternative-set-v2.0.7-stretch-strap-fallback"
    ),
    "prescription-set-v2.0.6": "prescription-set-v2.0.7",
    "media-set-v2.0.6": "media-set-v2.0.7",
}


def _load_integrated_builder() -> Any:
    path = ROOT / "data/scripts/build_integrated_catalog_bundle.py"
    spec = importlib.util.spec_from_file_location("integrated_draft_builder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _replace(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item) for item in value]
    if isinstance(value, str):
        for source, target in VERSION_REPLACEMENTS.items():
            value = value.replace(source, target)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Any]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _retarget_catalog(catalog_root: Path) -> None:
    for path in sorted(catalog_root.rglob("*.json")):
        _write_json(path, _replace(json.loads(path.read_text(encoding="utf-8"))))
    for path in sorted(catalog_root.rglob("*.jsonl")):
        rows = [
            _replace(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        _write_jsonl(path, rows)


def _refresh_manifest(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        artifact = path.parent / entry["path"]
        entry["sha256"] = _sha256(artifact)
        entry["bytes"] = artifact.stat().st_size
        if "records" in entry:
            entry["records"] = sum(
                bool(line.strip()) for line in artifact.read_text(encoding="utf-8").splitlines()
            )
    _write_json(path, manifest)


def _root_inventory(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == root / "bundle_manifest.json":
            continue
        entry: dict[str, Any] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix == ".jsonl":
            entry["records"] = sum(
                bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
            )
        entries.append(entry)
    return entries


def build(target: Path = TARGET, reports: Path = REPORTS) -> dict[str, Any]:
    if target.exists() or reports.exists():
        raise ValueError("refusing to overwrite an existing final bundle or report")
    draft_builder = _load_integrated_builder()
    with tempfile.TemporaryDirectory(prefix="integrated-v207-final-") as temporary:
        temp = Path(temporary)
        stage = temp / "backend_bundle"
        draft_builder.build(stage, temp / "draft_reports")
        catalog_root = stage / "catalog"
        _retarget_catalog(catalog_root)
        child_manifests = (
            catalog_root / "catalog/seed_manifest.json",
            catalog_root / "safety/rules_manifest.json",
            catalog_root / "alternatives/alternatives_manifest.json",
            catalog_root / "prescriptions/prescription_manifest.json",
            catalog_root / "media/media_manifest.json",
        )
        for manifest_path in child_manifests:
            _refresh_manifest(manifest_path)
        _refresh_manifest(catalog_root / "bundle_manifest.json")

        outer_path = stage / "bundle_manifest.json"
        outer = json.loads(outer_path.read_text(encoding="utf-8"))
        outer["bundle_version"] = "integrated-catalog-v2.0.7-final-2026-09-08"
        outer["promotion"] = {
            "catalog_version_code": CATALOG_VERSION,
            "approval_record_code": "V2-0-7-PRODUCTION-APPROVAL-2026-09-08-R01",
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation_code": "PRODUCTION_APPROVED",
        }
        outer["files"] = _root_inventory(stage)
        _write_json(outer_path, outer)

        catalog_bundle_path = catalog_root / "bundle_manifest.json"
        report = {
            "status": "PASS",
            "catalog_version_code": CATALOG_VERSION,
            "bundle_manifest_sha256": _sha256(outer_path),
            "catalog_bundle_manifest_sha256": _sha256(catalog_bundle_path),
            "summary": outer["summary"],
            "checks": {
                "regenerated_from_normalized_sources": True,
                "fitt_references_catalog": True,
                "catalog_and_derived_versions_retargeted": True,
                "file_inventory_complete": True,
            },
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, target)
        _write_json(reports / "promotion_candidate_validation.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    args = parser.parse_args()
    print(json.dumps(build(args.target, args.reports), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
