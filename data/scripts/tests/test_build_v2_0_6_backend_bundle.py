from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from backend.app.modules.catalog.service import load_alternative_artifact, load_catalog_artifact

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_6_backend_bundle.py"
spec = importlib.util.spec_from_file_location("build_v2_0_6_backend_bundle", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)

VALIDATOR_SCRIPT = Path(__file__).resolve().parents[1] / "validate_v2_backend_bundle.py"
validator_spec = importlib.util.spec_from_file_location(
    "validate_v2_backend_bundle", VALIDATOR_SCRIPT
)
assert validator_spec and validator_spec.loader
validator = importlib.util.module_from_spec(validator_spec)
sys.modules[validator_spec.name] = validator
validator_spec.loader.exec_module(validator)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_builds_complete_237_row_projection_and_fallbacks(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    summary = builder.build(target=output)

    assert summary["catalog_records"] == 237
    assert summary["media_asset_records"] == 237
    assert summary["alternative_records"] == 1
    assert summary["goal_tag_records"] == 711
    assert summary["prescription_records"] > 1000

    catalog = _jsonl(output / "catalog/exercises.jsonl")
    media = _jsonl(output / "media/media_assets.jsonl")
    alternatives = _jsonl(output / "alternatives/alternatives.jsonl")
    assert len({row["stable_code"] for row in catalog}) == 237
    assert len({row["source_identity"] for row in catalog}) == 237
    assert len(media) == 237
    assert {row["reason_code"] for row in alternatives} == {"EQUIPMENT"}
    assert {row["alternative_exercise_stable_code"] for row in alternatives} == {
        "quadruped_quadriceps_stretch_mobility_stretch_bodyweight",
    }
    assert any(row["body_focus_code"] == "ADDUCTORS" for row in catalog)
    assert all(row["rights_review_status"] == "APPROVED" for row in media)
    assert all(row["production_eligible"] is False for row in alternatives)

    artifact = load_catalog_artifact(
        output / "catalog",
        v2_import=True,
        v2_taxonomy_registry_sha256=builder._sha256(builder.TAXONOMY_REGISTRY),
    )
    assert len(artifact.records) == 237
    alternative_artifact = load_alternative_artifact(output / "alternatives", v2_import=True)
    assert len(alternative_artifact.records) == 1
    report = validator.validate(output)
    assert report["status"] == "valid"
    assert report["catalog_records"] == 237
    assert report["media_asset_records"] == 237
    assert report["alternative_records"] == 1


def test_projection_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert builder.build(target=first) == builder.build(target=second)
    assert (first / "bundle_manifest.json").read_bytes() == (
        second / "bundle_manifest.json"
    ).read_bytes()
