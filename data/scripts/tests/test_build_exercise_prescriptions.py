import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_exercise_prescriptions as builder  # noqa: E402
import validate_exercise_prescription_review_results as validator  # noqa: E402

SEED = Path("data/generated/exercise-catalog-seed-merged-mvp-v0.4.0")
RESULTS = Path("data/validation/review_results/prescription_results.csv")


def test_current_review_results_cover_all_supported_routines() -> None:
    report = validator.validate_results(SEED, RESULTS)

    assert report["prescription_records"] == 36
    assert report["goal_tag_records"] == 32
    feasibility = report["feasibility"]
    assert isinstance(feasibility, dict)
    assert all(feasibility.values())


def test_builds_and_verifies_artifact(tmp_path: Path) -> None:
    output = builder.build_prescriptions(SEED, RESULTS, tmp_path, "test-v1")

    assert builder.verify_prescriptions(output) == {
        "status": "valid",
        "exercise_records": 32,
        "goal_tag_records": 32,
        "prescription_records": 36,
    }


def test_tampered_artifact_fails_closed(tmp_path: Path) -> None:
    output = builder.build_prescriptions(SEED, RESULTS, tmp_path, "test-v1")
    path = output / "prescription_profiles.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

    with pytest.raises(builder.PipelineError, match="hash or byte count"):
        builder.verify_prescriptions(output)


def test_unknown_exercise_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "results.csv"
    text = RESULTS.read_text(encoding="utf-8").replace(
        "supine_chest_opening_stretch", "missing_exercise", 1
    )
    copied.write_text(text, encoding="utf-8")

    with pytest.raises(validator.PipelineError, match="unknown/non-beginner"):
        validator.validate_results(SEED, copied)
