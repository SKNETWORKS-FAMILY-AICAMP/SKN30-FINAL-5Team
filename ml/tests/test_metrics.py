from __future__ import annotations

import pandas as pd

from ml.src.metrics import evaluate_binary_classification, evaluate_predictions


def test_evaluate_binary_classification_returns_required_results() -> None:
    result = evaluate_binary_classification(
        [0, 0, 1, 1],
        [0.1, 0.4, 0.7, 0.9],
        threshold=0.5,
        calibration_bins=3,
    )

    assert set(result["metrics"]) == {
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "pr_auc",
        "brier",
    }
    assert result["confusion_matrix"]["values"] == [[2, 0], [0, 2]]
    assert result["calibration_curve"]["n_bins"] == 3
    assert result["unavailable_metrics"] == {}


def test_single_class_segment_does_not_fail_complete_evaluation() -> None:
    predictions = pd.DataFrame(
        {
            "y_true": [0, 0, 1, 1],
            "y_prob": [0.1, 0.2, 0.8, 0.9],
            "history_bucket": ["0-7", "0-7", "29+", "29+"],
            "experience_level_code": [
                "BEGINNER",
                "INTERMEDIATE",
                "BEGINNER",
                "INTERMEDIATE",
            ],
        }
    )

    result = evaluate_predictions(
        predictions,
        threshold=0.5,
        calibration_bins=2,
    )

    cold_start = result["segments"]["history_bucket"]["0-7"]
    assert result["overall"]["metrics"]["roc_auc"] == 1.0
    assert cold_start["metrics"]["roc_auc"] is None
    assert cold_start["metrics"]["pr_auc"] is None
    assert cold_start["unavailable_metrics"] == {
        "roc_auc": "requires both target classes",
        "pr_auc": "requires both target classes",
    }
    assert cold_start["confusion_matrix"]["values"] == [[2, 0], [0, 0]]
