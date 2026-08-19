from __future__ import annotations

import json
from pathlib import Path

import pytest
from build_tranche_3_catalog_seed import build_all, verify_all
from kspo_fitness100_pipeline import PipelineError
from review_tranche_3_candidates import DEFAULT_OUTPUT


def test_builds_two_incremental_seeds(tmp_path: Path) -> None:
    built = build_all(DEFAULT_OUTPUT, tmp_path)

    assert built["records"] == {"kspo": 3, "wger": 3}
    assert verify_all(DEFAULT_OUTPUT, tmp_path) == {
        "status": "valid",
        "records": {"kspo": 3, "wger": 3},
        "production_eligible": False,
    }
    kspo = tmp_path / "exercise-catalog-seed-kspo-tranche3-v0.1.0"
    records = [
        json.loads(line)
        for line in (kspo / "exercises.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {record["stable_code"] for record in records} == {
        "quadruped_scapular_press",
        "standing_band_pulldown",
        "seated_spinal_flexion_extension",
    }
    assert all(record["review_status_code"] == "DOMAIN_APPROVED" for record in records)


def test_rejects_existing_output_directory(tmp_path: Path) -> None:
    build_all(DEFAULT_OUTPUT, tmp_path)

    with pytest.raises(PipelineError, match="already exists"):
        build_all(DEFAULT_OUTPUT, tmp_path)


def test_rejects_tampered_exercise_file(tmp_path: Path) -> None:
    build_all(DEFAULT_OUTPUT, tmp_path)
    path = tmp_path / "exercise-catalog-seed-wger-tranche3-v0.1.0" / "exercises.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

    with pytest.raises(PipelineError, match="hash or size mismatch"):
        verify_all(DEFAULT_OUTPUT, tmp_path)
