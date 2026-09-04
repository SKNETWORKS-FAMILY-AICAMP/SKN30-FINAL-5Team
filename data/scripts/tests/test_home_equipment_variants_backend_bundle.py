from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load(name: str, filename: str):
    path = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load(
    "build_home_equipment_variants_backend_bundle",
    "build_home_equipment_variants_backend_bundle.py",
)
validator = _load(
    "validate_home_equipment_variants_backend_bundle",
    "validate_home_equipment_variants_backend_bundle.py",
)


def test_builds_approved_importer_bundle(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    assert builder.build(output) == {
        "substitution_guide_records": 34,
        "variant_candidate_records": 20,
        "stretch_strap_records": 0,
    }
    report = validator.validate(output)
    assert report["status"] == "valid"
    manifest = json.loads((output / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["importer_paths"]) == {"substitution_guides", "variant_candidates"}
    registry = json.loads((output / manifest["approval_registry_path"]).read_text(encoding="utf-8"))
    assert registry["status_code"] == "DOMAIN_APPROVED"
    assert registry["production_eligible"] is True


def test_validator_fails_on_tampered_data(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    builder.build(output)
    data = output / "variants/bodyweight_variant_candidates.jsonl"
    data.write_text(data.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(validator.BundleValidationError, match="hash/count mismatch"):
        validator.validate(output)
