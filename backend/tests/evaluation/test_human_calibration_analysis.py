"""Tests for PHASE 10 consensus-label calibration analysis."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from backend.tests.evaluation.human_calibration_analysis import (
    CalibrationInputError,
    analyze_rows,
    load_reference,
    load_rows,
)

ROOT = Path(__file__).resolve().parents[3]
FORM = ROOT / "results/human_calibration/blind_evaluation_form.csv"
REFERENCE = ROOT / "results/human_calibration/sealed_judge_reference.json"


def test_completed_consensus_form_produces_all_24_comparisons() -> None:
    results, summary = analyze_rows(load_rows(FORM), load_reference(REFERENCE))

    assert len(results) == 24
    assert summary["label_type"] == "PM and development-lead consensus"
    assert summary["inter_rater_agreement"] is None
    assert summary["overall"]["sample_count"] == 24  # type: ignore[index]
    assert all(1.0 <= float(row["human_score"]) <= 5.0 for row in results)


def test_missing_or_out_of_range_score_is_rejected() -> None:
    rows = load_rows(FORM)
    reference = load_reference(REFERENCE)
    invalid = deepcopy(rows)
    invalid[0]["overall_quality_score"] = ""
    invalid[1]["feasibility_score"] = "5.1"

    with pytest.raises(CalibrationInputError) as captured:
        analyze_rows(invalid, reference)

    assert any("overall_quality_score must be numeric" in error for error in captured.value.errors)
    assert any(
        "feasibility_score must be between 1 and 5" in error for error in captured.value.errors
    )


def test_sample_identity_cannot_be_changed_after_blind_review() -> None:
    rows = load_rows(FORM)
    invalid = deepcopy(rows)
    invalid[0]["case_id"] = "SQ-TAMPERED-001"

    with pytest.raises(CalibrationInputError, match="case_id does not match"):
        analyze_rows(invalid, load_reference(REFERENCE))
