from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from backend.app.modules.catalog.service import load_integrated_catalog_bundle

SCRIPT = Path(__file__).resolve().parents[1] / "build_integrated_catalog_v2_0_8_final.py"
spec = importlib.util.spec_from_file_location("integrated_v208_final", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_builds_loadable_v208_candidate_with_reviewed_catalog_corrections(tmp_path: Path) -> None:
    target = tmp_path / "bundle"
    report = builder.build(target, tmp_path / "reports")
    loaded = load_integrated_catalog_bundle(
        target, expected_catalog_version=builder.CATALOG_VERSION
    )
    rows = {row.stable_code: row for row in loaded.catalog.records}

    assert report["status"] == "PASS_WITH_APPROVAL"
    assert len(rows) == 237
    assert rows["barbell_straight_leg_deadlift_hip_dominant_barbell"].family_code == (
        "ROMANIAN_DEADLIFT"
    )
    assert rows[
        "barbell_straight_leg_deadlift_hip_dominant_barbell"
    ].representative_stable_code == ("barbell_romanian_deadlift")
    assert rows["smith_close_grip_bench_press"].family_code == "CHEST_PRESS"
    assert rows["cardio_gait_machine"].default_work_seconds == 600
    assert rows["cardio_gait_machine"].default_rest_seconds == 0
    assert rows["mountain_climber"].default_work_seconds == 30
    assert rows["mountain_climber"].default_rest_seconds == 30
    assert rows["quick_feet"].training_type_code.value == "CARDIO"
    assert all(row.recovery_eligible is not None for row in rows.values())
    manifest = json.loads((target / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["promotion"]["status_interpretation_code"] == "PRODUCTION_APPROVED"
    source_fitt = (target / "sources/catalog_enrichment_v3_fitt.csv").read_text(encoding="utf-8")
    assert ",12," in source_fitt
    assert ",15," in source_fitt
