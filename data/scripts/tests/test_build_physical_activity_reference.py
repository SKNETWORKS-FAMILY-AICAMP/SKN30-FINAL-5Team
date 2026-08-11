from __future__ import annotations

import json
from pathlib import Path

import pytest
from build_physical_activity_reference import build_outputs, verify_outputs
from kspo_fitness100_pipeline import PipelineError

DATA_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = DATA_ROOT / "raw" / "physical_activity_guidelines"


def test_builds_normalized_reference_without_exercise_mapping(tmp_path: Path) -> None:
    result = build_outputs(RAW_DIR, tmp_path)

    assert result == {
        "status": "valid",
        "intensity_rule_count": 5,
        "fitt_assertion_count": 10,
        "compendium_activity_count": 20,
    }
    intensity = json.loads((tmp_path / "intensity_reference.json").read_text(encoding="utf-8"))
    assert [rule["reference_code"] for rule in intensity["absolute_met_rules"]] == [
        "BELOW_MODERATE_MET",
        "MODERATE_MET",
        "VIGOROUS_MET",
    ]
    compendium = json.loads(
        (tmp_path / "adult_compendium_reference_subset.json").read_text(encoding="utf-8")
    )
    by_code = {row["activity_code"]: row for row in compendium["activities"]}
    assert by_code["02101"]["absolute_intensity_reference_code"] == "BELOW_MODERATE_MET"
    assert by_code["02056"]["absolute_intensity_reference_code"] == "MODERATE_MET"
    assert by_code["02058"]["absolute_intensity_reference_code"] == "VIGOROUS_MET"
    assert all("normalized_exercise_id" not in row for row in compendium["activities"])


def test_fitt_reference_preserves_source_assertions(tmp_path: Path) -> None:
    build_outputs(RAW_DIR, tmp_path)
    fitt = json.loads((tmp_path / "adult_weekly_fitt_reference.json").read_text(encoding="utf-8"))

    assert fitt["reference_envelope"]["aerobic"] == {
        "moderate_minutes_per_week": {"minimum": 150, "maximum": 300},
        "vigorous_minutes_per_week": {"minimum": 75, "maximum": 150},
        "vigorous_to_moderate_minute_equivalence": {"vigorous": 1, "moderate": 2},
    }
    assert fitt["reference_envelope"]["strength"]["minimum_days_per_week"] == 2
    assert fitt["reference_envelope"]["application_status"] == ("REFERENCE_ONLY_SCHEMA_UNRESOLVED")


def test_rejects_tampered_normalized_output(tmp_path: Path) -> None:
    build_outputs(RAW_DIR, tmp_path)
    path = tmp_path / "intensity_reference.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["absolute_met_rules"][1]["minimum"] = 2.5
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PipelineError, match="does not match"):
        verify_outputs(RAW_DIR, tmp_path)


def test_rejects_tampered_manifest_hash(tmp_path: Path) -> None:
    build_outputs(RAW_DIR, tmp_path)
    path = tmp_path / "reference_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["files"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PipelineError, match="hash mismatch"):
        verify_outputs(RAW_DIR, tmp_path)
