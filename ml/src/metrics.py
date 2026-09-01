"""Reusable binary-classification metrics for Track B experiments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

DEFAULT_SEGMENT_COLUMNS = ("history_bucket", "experience_level_code")


def evaluate_binary_classification(
    y_true: Sequence[int] | np.ndarray | pd.Series,
    y_prob: Sequence[float] | np.ndarray | pd.Series,
    *,
    threshold: float,
    calibration_bins: int,
) -> dict[str, Any]:
    """Evaluate binary probabilities without failing on single-class inputs.

    Metrics that are undefined for the supplied labels are returned as ``None``.
    Their error messages are retained in ``unavailable_metrics`` so downstream
    reporting can distinguish an unavailable metric from a computed zero.
    """

    true_values, probability_values = _validate_binary_inputs(y_true, y_prob)
    _validate_evaluation_parameters(threshold, calibration_bins)

    predicted_values = (probability_values >= threshold).astype(np.int8)
    metric_values: dict[str, float | None] = {
        "precision": float(precision_score(true_values, predicted_values, zero_division=0)),
        "recall": float(recall_score(true_values, predicted_values, zero_division=0)),
        "f1": float(f1_score(true_values, predicted_values, zero_division=0)),
        "roc_auc": None,
        "pr_auc": None,
        "brier": float(brier_score_loss(true_values, probability_values)),
    }
    unavailable_metrics: dict[str, str] = {}

    if np.unique(true_values).size < 2:
        reason = "requires both target classes"
        unavailable_metrics["roc_auc"] = reason
        unavailable_metrics["pr_auc"] = reason
    else:
        metric_values["roc_auc"] = _safe_metric(
            "roc_auc",
            lambda: roc_auc_score(true_values, probability_values),
            unavailable_metrics,
        )
        metric_values["pr_auc"] = _safe_metric(
            "pr_auc",
            lambda: average_precision_score(true_values, probability_values),
            unavailable_metrics,
        )

    matrix = confusion_matrix(true_values, predicted_values, labels=[0, 1])
    calibration = _safe_calibration_curve(
        true_values,
        probability_values,
        calibration_bins,
        unavailable_metrics,
    )

    return {
        "n_samples": int(true_values.size),
        "threshold": float(threshold),
        "metrics": metric_values,
        "confusion_matrix": {
            "labels": [0, 1],
            "values": matrix.astype(int).tolist(),
        },
        "calibration_curve": calibration,
        "unavailable_metrics": unavailable_metrics,
    }


def evaluate_predictions(
    predictions: pd.DataFrame,
    *,
    threshold: float,
    calibration_bins: int,
    y_true_column: str = "y_true",
    y_probability_column: str = "y_prob",
    segment_columns: Sequence[str] = DEFAULT_SEGMENT_COLUMNS,
) -> dict[str, Any]:
    """Return overall and segment evaluations with one shared result schema."""

    required_columns = [y_true_column, y_probability_column, *segment_columns]
    missing_columns = [column for column in required_columns if column not in predictions.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"predictions is missing required columns: {missing}")

    overall = evaluate_binary_classification(
        predictions[y_true_column],
        predictions[y_probability_column],
        threshold=threshold,
        calibration_bins=calibration_bins,
    )

    segments: dict[str, dict[str, dict[str, Any]]] = {}
    for segment_column in segment_columns:
        segment_results: dict[str, dict[str, Any]] = {}
        for segment_value in predictions[segment_column].drop_duplicates().tolist():
            if pd.isna(segment_value):
                mask = predictions[segment_column].isna()
                segment_key = "<MISSING>"
            else:
                mask = predictions[segment_column].eq(segment_value)
                segment_key = str(segment_value)

            segment_results[segment_key] = evaluate_binary_classification(
                predictions.loc[mask, y_true_column],
                predictions.loc[mask, y_probability_column],
                threshold=threshold,
                calibration_bins=calibration_bins,
            )
        segments[segment_column] = segment_results

    return {"overall": overall, "segments": segments}


def _validate_binary_inputs(
    y_true: Sequence[int] | np.ndarray | pd.Series,
    y_prob: Sequence[float] | np.ndarray | pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    true_values = np.asarray(y_true)
    probability_values = np.asarray(y_prob, dtype=float)

    if true_values.ndim != 1 or probability_values.ndim != 1:
        raise ValueError("y_true and y_prob must be one-dimensional")
    if true_values.size == 0:
        raise ValueError("y_true and y_prob must not be empty")
    if true_values.size != probability_values.size:
        raise ValueError("y_true and y_prob must have the same length")
    if pd.isna(true_values).any():
        raise ValueError("y_true must not contain missing values")
    if not np.isfinite(probability_values).all():
        raise ValueError("y_prob must contain only finite values")
    if ((probability_values < 0.0) | (probability_values > 1.0)).any():
        raise ValueError("y_prob values must be between 0 and 1")

    unique_targets = set(np.unique(true_values).tolist())
    if not unique_targets.issubset({0, 1}):
        raise ValueError("y_true must contain only binary labels 0 and 1")

    return true_values.astype(np.int8), probability_values


def _validate_evaluation_parameters(threshold: float, calibration_bins: int) -> None:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if isinstance(calibration_bins, bool) or not isinstance(calibration_bins, int):
        raise TypeError("calibration_bins must be an integer")
    if calibration_bins < 1:
        raise ValueError("calibration_bins must be at least 1")


def _safe_metric(
    metric_name: str,
    calculate: Any,
    unavailable_metrics: dict[str, str],
) -> float | None:
    try:
        return float(calculate())
    except (TypeError, ValueError) as exc:
        unavailable_metrics[metric_name] = str(exc)
        return None


def _safe_calibration_curve(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    calibration_bins: int,
    unavailable_metrics: dict[str, str],
) -> dict[str, Any] | None:
    try:
        probability_true, probability_predicted = calibration_curve(
            y_true,
            y_prob,
            n_bins=calibration_bins,
            strategy="uniform",
        )
    except (TypeError, ValueError) as exc:
        unavailable_metrics["calibration_curve"] = str(exc)
        return None

    return {
        "n_bins": calibration_bins,
        "probability_true": probability_true.tolist(),
        "probability_predicted": probability_predicted.tolist(),
    }
