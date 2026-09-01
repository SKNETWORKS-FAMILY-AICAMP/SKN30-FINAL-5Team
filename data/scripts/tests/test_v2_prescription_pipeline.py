from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_v2_prescription_review_input as authoring  # noqa: E402
import build_v2_prescriptions as builder  # noqa: E402
import validate_v2_prescription_review_input as validator  # noqa: E402

CATALOG = Path("data/generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv")
POLICY = Path("data/normalized/v2_prescription_review_policy.json")


def test_v2_review_input_covers_all_102_exercises_and_exact_durations(tmp_path: Path) -> None:
    output = tmp_path / "v2_review.csv"
    rows = authoring.build_rows(CATALOG, POLICY)
    authoring.write_rows(output, rows)

    report = validator.validate_results(CATALOG, output, policy_path=POLICY)

    assert report["catalog_records"] == 102
    assert report["goal_tag_records"] == 102
    assert report["prescription_records"] == 137
    assert all(report["feasibility"].values())
    assert report["production_eligible"] is False


def test_v2_unknown_stable_code_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "v2_review.csv"
    rows = authoring.build_rows(CATALOG, POLICY)
    rows[0]["stable_code"] = "not_a_v2_code"
    authoring.write_rows(output, rows)

    with pytest.raises(validator.PipelineError, match="unknown stable_code"):
        validator.validate_results(CATALOG, output, policy_path=POLICY)


def test_v2_prescription_artifact_is_draft_and_hash_verified(tmp_path: Path) -> None:
    review = tmp_path / "v2_review.csv"
    authoring.write_rows(review, authoring.build_rows(CATALOG, POLICY))
    output = builder.build(CATALOG, review, tmp_path / "prescriptions", policy_path=POLICY)

    assert builder.verify(output)["goal_tag_records"] == 102
    assert builder.verify(output)["prescription_records"] == 137
    manifest = (output / "prescription_manifest.json").read_text(encoding="utf-8")
    assert '"status_code": "DRAFT"' in manifest
    assert '"production_eligible": false' in manifest
