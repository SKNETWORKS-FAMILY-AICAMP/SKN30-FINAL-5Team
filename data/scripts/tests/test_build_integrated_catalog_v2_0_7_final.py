from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from backend.app.modules.catalog.service import load_integrated_catalog_bundle

SCRIPT = Path(__file__).resolve().parents[1] / "build_integrated_catalog_v2_0_7_final.py"
spec = importlib.util.spec_from_file_location("integrated_final", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_builds_loadable_final_bundle_with_distinct_release_versions(tmp_path: Path) -> None:
    target = tmp_path / "bundle"
    report = builder.build(target, tmp_path / "reports")

    loaded = load_integrated_catalog_bundle(
        target, expected_catalog_version="exercise-catalog-v2.0.7-final"
    )
    nested = json.loads((target / "catalog/bundle_manifest.json").read_text(encoding="utf-8"))

    assert len(loaded.catalog.records) == 237
    assert loaded.gym_guide_record_count == 67
    assert nested["catalog_version_code"] == "exercise-catalog-v2.0.7-final"
    assert nested["derived_set_versions"] == {
        "alternative_set_version_code": "alternative-set-v2.0.7-stretch-strap-fallback",
        "prescription_set_version_code": "prescription-set-v2.0.7",
        "rule_set_version_code": "safety-rule-set-v2.0.7",
    }
    assert report["bundle_manifest_sha256"] == builder._sha256(target / "bundle_manifest.json")
    assert report["catalog_bundle_manifest_sha256"] == builder._sha256(
        target / "catalog/bundle_manifest.json"
    )
