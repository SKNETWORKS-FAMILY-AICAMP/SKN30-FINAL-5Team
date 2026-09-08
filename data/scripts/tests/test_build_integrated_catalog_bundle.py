from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_integrated_catalog_bundle.py"
spec = importlib.util.spec_from_file_location("integrated", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_builds_complete_additive_bundle(tmp_path: Path) -> None:
    report = builder.build(tmp_path / "bundle", tmp_path / "reports")
    root = tmp_path / "bundle"
    manifest = json.loads((root / "bundle_manifest.json").read_text())
    assert report["status"] == "PASS"
    assert manifest["summary"] == {
        "catalog_records": 237,
        "gym_guide_records": 67,
        "home_guide_records": 34,
        "fitt_reference_records": 208,
        "fitt_stable_code_mapping_records": 89,
        "met_fields_per_catalog_record": 6,
        # The v2.0.6 difficulty re-review left 57 BEGINNER prescription rows on
        # exercises it moved to INTERMEDIATE. The build drops them because the
        # directional rule forbids them; a nonzero count here is expected until
        # the prescription review is re-run against the current difficulties.
        "prescription_rows_removed_for_difficulty": 57,
    }
    catalog = builder._read_jsonl(root / "catalog/catalog/exercises.jsonl")
    codes = {row["stable_code"] for row in catalog}
    assert len(codes) == 237
    assert all(
        all(
            field in row
            for field in builder._load(
                "v207", builder.ROOT / "data/scripts/build_v2_0_7_backend_bundle.py"
            ).MET_FIELDS
        )
        for row in catalog
    )
    for relative in (
        "gym_equipment/starting_guides.jsonl",
        "home_equipment/guides/substitution_guides.jsonl",
    ):
        assert all(
            row["exercise_stable_code"] in codes for row in builder._read_jsonl(root / relative)
        )
    assert len(manifest["files"]) > 10
    assert (root / "sources/catalog_enrichment_v3_fitt.csv").exists()
    assert (root / "sources/v2_0_7_fitt_stable_code_mapping.csv").exists()
    assert manifest["completeness_checks"]["fitt_references_catalog"] is True
