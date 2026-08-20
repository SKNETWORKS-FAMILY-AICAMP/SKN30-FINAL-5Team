import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_merged_catalog_seed as merged  # noqa: E402

GENERATED = Path("data/generated")
CURRENT = GENERATED / "exercise-catalog-seed-merged-mvp-v0.4.0"
INPUTS = (
    GENERATED / "exercise-catalog-seed-kspo-mvp-v0.3.0",
    GENERATED / "exercise-catalog-seed-wger-mvp-v0.2.0",
    GENERATED / "exercise-catalog-seed-kspo-tranche3-v0.1.0",
    GENERATED / "exercise-catalog-seed-wger-tranche3-v0.1.0",
)


def test_current_merged_seed_is_valid_and_preserves_source_tracks() -> None:
    report = merged.verify_seed(CURRENT)
    manifest = json.loads((CURRENT / "seed_manifest.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (CURRENT / "exercises.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert report["status"] == "valid"
    assert manifest["source"]["track"] == "merged"
    assert len(records) == 56
    assert {row["source_track"] for row in records} == {"kspo", "wger"}


def test_merged_seed_rebuild_is_reproducible(tmp_path: Path) -> None:
    output = merged.build_merged_seed(INPUTS, tmp_path, "merged-mvp-v0.4.0")

    assert (output / "exercises.jsonl").read_bytes() == (CURRENT / "exercises.jsonl").read_bytes()


def test_duplicate_input_seed_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(merged.PipelineError, match="supplied twice"):
        merged.build_merged_seed((INPUTS[0], INPUTS[0]), tmp_path, "test-v1")
