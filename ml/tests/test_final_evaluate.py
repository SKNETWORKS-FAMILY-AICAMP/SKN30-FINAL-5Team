from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.src.final_evaluate import (
    FINAL_PREDICTION_COLUMNS,
    FreezeValidationError,
    build_test_prediction_frame,
    create_test_attempt_marker,
    validate_freeze_guards,
)


def test_freeze_guards_forbid_test_driven_reselection() -> None:
    freeze = {
        "locked": True,
        "guards": {
            "excluded_ablations": ["A5"],
            "max_test_evaluations": 1,
            "allow_reselection_after_test": False,
        },
    }

    validate_freeze_guards(freeze)

    freeze["guards"]["allow_reselection_after_test"] = True
    with pytest.raises(FreezeValidationError, match="must be false"):
        validate_freeze_guards(freeze)


def test_attempt_marker_blocks_a_second_test_evaluation(tmp_path: Path) -> None:
    freeze_path = tmp_path / "freeze.yaml"
    model_path = tmp_path / "model.joblib"
    marker_path = tmp_path / "test_evaluation_attempt.json"
    freeze_path.write_text("locked: true\n", encoding="utf-8")
    model_path.write_bytes(b"model")

    create_test_attempt_marker(
        marker_path,
        freeze_path=freeze_path,
        model_path=model_path,
        candidate={"experiment_id": "final_time_A3_histgb_test"},
    )

    with pytest.raises(RuntimeError, match="refusing to inspect test again"):
        create_test_attempt_marker(
            marker_path,
            freeze_path=freeze_path,
            model_path=model_path,
            candidate={"experiment_id": "final_time_A3_histgb_test"},
        )


def test_test_prediction_frame_matches_handoff_schema() -> None:
    test = pd.DataFrame(
        {
            "user_id": ["u1", "u2"],
            "local_date": ["2024-01-01", "2024-01-02"],
            "workout_completed": [0, 1],
            "history_days": [40, 50],
            "history_bucket": ["29+", "29+"],
            "experience_level_code": ["BEGINNER", "ADVANCED"],
        }
    )

    predictions = build_test_prediction_frame(
        test,
        np.array([0.25, 0.75]),
        split_type="time",
        ablation_id="A3",
        model_id="histgb",
        target="workout_completed",
    )

    assert predictions.columns.tolist() == list(FINAL_PREDICTION_COLUMNS)
    assert predictions["split_part"].astype(str).tolist() == ["test", "test"]
    assert predictions["y_prob"].dtype == np.dtype("float32")
