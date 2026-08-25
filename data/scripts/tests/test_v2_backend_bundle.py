from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_v2_backend_bundle as packager  # noqa: E402
import validate_v2_backend_bundle as validator  # noqa: E402


def test_v2_bundle_has_importer_paths_and_draft_projection(tmp_path: Path) -> None:
    output = packager.build(output=tmp_path / "bundle")
    report = validator.validate(output)

    assert report == {
        "status": "valid",
        "catalog_records": 102,
        "safety_rule_records": 394,
        "alternative_records": 285,
        "goal_tag_records": 102,
        "prescription_records": 137,
        "production_eligible": False,
    }
    assert (output / "catalog/seed_manifest.json").is_file()
    assert (output / "safety/rules_manifest.json").is_file()
    assert (output / "alternatives/alternatives_manifest.json").is_file()
    assert (output / "prescriptions/prescription_manifest.json").is_file()
    assert (output / "alternatives/input/alternative_projection_conflicts.json").is_file()
