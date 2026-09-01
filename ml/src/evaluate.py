"""Run the validation-only Track B experiment matrix and persist its evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from ml.src.metrics import evaluate_predictions
from ml.src.train import (
    TrainingResult,
    fit_candidate,
    get_ablation_features,
    load_experiment_config,
    predict_probabilities,
)
from ml.src.validate_leakage import validate_dataset

DEFAULT_CONFIG_PATH = Path("ml/config/experiments.yaml")
DEFAULT_SPLIT_DIR = Path("ml/data/processed/splits")
DEFAULT_OUTPUT_DIR = Path("ml/outputs")
DEFAULT_MODEL_DIR = Path("ml/models")

SPLIT_TYPES = ("time", "user")
MODEL_ABLATIONS = ("A1", "A2", "A3", "A4", "A5", "A2-lag1")
CANDIDATE_MODELS = ("logreg", "rf", "histgb")
CATEGORICAL_FEATURES = frozenset(
    {
        "experience_level_code",
        "resting_hr_trend_code_prev_day",
        "last_workout_type_code_prev_day",
    }
)
PREDICTION_COLUMNS = (
    "user_id",
    "local_date",
    "split_type",
    "split_part",
    "ablation_id",
    "model_id",
    "y_true",
    "y_prob",
    "history_days",
    "history_bucket",
    "experience_level_code",
)
METRIC_NAMES = ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier")


@dataclass(frozen=True)
class ExperimentSpec:
    """One deterministic validation experiment."""

    split_type: str
    ablation_id: str
    model_id: str

    @property
    def experiment_id(self) -> str:
        return f"{self.split_type}_{self.ablation_id}_{self.model_id}"


@dataclass(frozen=True)
class CandidateRecord:
    """A fitted candidate together with the validation data that selected it."""

    spec: ExperimentSpec
    result: TrainingResult
    validation: pd.DataFrame
    probabilities: np.ndarray


def build_experiment_matrix(config: dict[str, Any]) -> list[ExperimentSpec]:
    """Return the documented 38 validation experiments in a stable order."""

    configured_splits = config["splits"]
    configured_ablations = config["ablations"]
    for split_type in SPLIT_TYPES:
        if split_type not in configured_splits:
            raise ValueError(f"config is missing split '{split_type}'")
    for ablation_id in ("A0", *MODEL_ABLATIONS):
        if ablation_id not in configured_ablations:
            raise ValueError(f"config is missing ablation '{ablation_id}'")

    matrix: list[ExperimentSpec] = []
    for split_type in SPLIT_TYPES:
        matrix.append(ExperimentSpec(split_type, "A0", "majority"))
        matrix.extend(
            ExperimentSpec(split_type, ablation_id, model_id)
            for ablation_id in MODEL_ABLATIONS
            for model_id in CANDIDATE_MODELS
        )
    if len(matrix) != 38:
        raise AssertionError(f"validation matrix must contain 38 experiments, got {len(matrix)}")
    return matrix


def load_train_validation_splits(
    split_dir: Path, split_type: str, config_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and leakage-check only train and validation files.

    Test paths are intentionally absent so this stage cannot inspect test labels or
    predictions by accident.
    """

    if split_type not in SPLIT_TYPES:
        raise ValueError(f"unsupported split type '{split_type}'")
    train_path = split_dir / f"{split_type}_train.csv"
    validation_path = split_dir / f"{split_type}_val.csv"
    validate_dataset(train_path, config_path)
    validate_dataset(validation_path, config_path)
    return pd.read_csv(train_path), pd.read_csv(validation_path)


def split_feature_types(feature_columns: list[str]) -> tuple[list[str], list[str]]:
    """Apply the FEATURE_SPEC categorical declarations without dtype inference."""

    categorical = [column for column in feature_columns if column in CATEGORICAL_FEATURES]
    numeric = [column for column in feature_columns if column not in CATEGORICAL_FEATURES]
    return categorical, numeric


def build_prediction_frame(
    validation: pd.DataFrame,
    probabilities: np.ndarray,
    spec: ExperimentSpec,
    target: str,
) -> pd.DataFrame:
    """Build the exact Track B to Track C prediction handoff schema."""

    required = {
        "user_id",
        "local_date",
        target,
        "history_days",
        "history_bucket",
        "experience_level_code",
    }
    missing = sorted(required.difference(validation.columns))
    if missing:
        raise ValueError(f"validation split is missing prediction columns: {', '.join(missing)}")
    if len(validation) != len(probabilities):
        raise ValueError("validation rows and probabilities must have the same length")

    predictions = pd.DataFrame(
        {
            "user_id": validation["user_id"].astype("string"),
            "local_date": pd.to_datetime(validation["local_date"], errors="raise").dt.date,
            "split_type": spec.split_type,
            "split_part": "val",
            "ablation_id": spec.ablation_id,
            "model_id": spec.model_id,
            "y_true": validation[target].astype("int8"),
            "y_prob": np.asarray(probabilities, dtype="float32"),
            "history_days": validation["history_days"].astype("int16"),
            "history_bucket": validation["history_bucket"].astype("category"),
            "experience_level_code": validation["experience_level_code"].astype("category"),
        }
    )
    for column in ("split_type", "split_part", "ablation_id", "model_id"):
        predictions[column] = predictions[column].astype("category")
    return predictions.loc[:, list(PREDICTION_COLUMNS)]


def _evaluation_settings(config: dict[str, Any]) -> tuple[float, int, int]:
    evaluation = config["evaluation"]
    threshold = evaluation.get("threshold")
    calibration_bins = evaluation.get("calibration_bins")
    permutation_repeats = evaluation.get("permutation_repeats")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError("config.evaluation.threshold must be numeric")
    if not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("config.evaluation.threshold must be between 0 and 1")
    for name, value in (
        ("calibration_bins", calibration_bins),
        ("permutation_repeats", permutation_repeats),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"config.evaluation.{name} must be a positive integer")
    return float(threshold), calibration_bins, permutation_repeats


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _model_hyperparameters(config: dict[str, Any], model_id: str) -> dict[str, Any]:
    parameters = dict(config["models"][model_id]["params"])
    if model_id != "majority":
        parameters["random_state"] = config["seed"]
    return parameters


def _overall_columns(evaluation: dict[str, Any]) -> dict[str, Any]:
    metrics = evaluation["metrics"]
    matrix = evaluation["confusion_matrix"]["values"]
    return {
        **{metric: metrics[metric] for metric in METRIC_NAMES},
        "tn": matrix[0][0],
        "fp": matrix[0][1],
        "fn": matrix[1][0],
        "tp": matrix[1][1],
        "calibration_curve": _json(evaluation["calibration_curve"]),
        "unavailable_metrics": _json(evaluation["unavailable_metrics"]),
    }


def _segment_rows(
    experiment_id: str, spec: ExperimentSpec, evaluation: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment_name, values in evaluation.items():
        for segment_value, result in values.items():
            matrix = result["confusion_matrix"]["values"]
            rows.append(
                {
                    "experiment_id": experiment_id,
                    "split_type": spec.split_type,
                    "ablation_id": spec.ablation_id,
                    "model_id": spec.model_id,
                    "segment_name": segment_name,
                    "segment_value": segment_value,
                    "n_samples": result["n_samples"],
                    **{metric: result["metrics"][metric] for metric in METRIC_NAMES},
                    "tn": matrix[0][0],
                    "fp": matrix[0][1],
                    "fn": matrix[1][0],
                    "tp": matrix[1][1],
                    "calibration_curve": _json(result["calibration_curve"]),
                    "unavailable_metrics": _json(result["unavailable_metrics"]),
                }
            )
    return rows


def _calibration_rows(
    experiment_id: str, spec: ExperimentSpec, calibration: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if calibration is None:
        return []
    return [
        {
            "experiment_id": experiment_id,
            "split_type": spec.split_type,
            "ablation_id": spec.ablation_id,
            "model_id": spec.model_id,
            "bin_index": index,
            "probability_true": probability_true,
            "probability_predicted": probability_predicted,
        }
        for index, (probability_true, probability_predicted) in enumerate(
            zip(
                calibration["probability_true"],
                calibration["probability_predicted"],
                strict=True,
            )
        )
    ]


def _coefficient_rows(record: CandidateRecord) -> list[dict[str, Any]]:
    if record.spec.model_id != "logreg":
        return []
    preprocessor = record.result.pipeline.named_steps["preprocessor"]
    model = record.result.pipeline.named_steps["model"]
    names = preprocessor.get_feature_names_out()
    coefficients = np.asarray(model.coef_)[0]
    return [
        {
            "experiment_id": record.spec.experiment_id,
            "split_type": record.spec.split_type,
            "ablation_id": record.spec.ablation_id,
            "model_id": record.spec.model_id,
            "method": "logistic_coefficient",
            "feature": str(feature),
            "importance_mean": float(coefficient),
            "importance_std": None,
        }
        for feature, coefficient in zip(names, coefficients, strict=True)
    ]


def _permutation_rows(
    record: CandidateRecord, *, repeats: int, seed: int
) -> list[dict[str, Any]]:
    features = list(record.result.feature_columns)
    if not features:
        return []
    importance = permutation_importance(
        record.result.pipeline,
        record.validation.loc[:, features],
        record.validation["workout_completed"],
        scoring="average_precision",
        n_repeats=repeats,
        random_state=seed,
        n_jobs=-1,
    )
    return [
        {
            "experiment_id": record.spec.experiment_id,
            "split_type": record.spec.split_type,
            "ablation_id": record.spec.ablation_id,
            "model_id": record.spec.model_id,
            "method": "permutation_pr_auc",
            "feature": feature,
            "importance_mean": float(mean),
            "importance_std": float(std),
        }
        for feature, mean, std in zip(
            features,
            importance.importances_mean,
            importance.importances_std,
            strict=True,
        )
    ]


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _source_fingerprint(config_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (config_path, Path(__file__), Path("ml/src/train.py"), Path("ml/src/metrics.py")):
        digest.update(path.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _library_versions() -> dict[str, str]:
    return {
        package: version(package)
        for package in ("joblib", "numpy", "pandas", "pyarrow", "PyYAML", "scikit-learn")
    }


def _atomic_dump(pipeline: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}_", suffix=".joblib.tmp", dir=destination.parent
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        joblib.dump(pipeline, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _best_candidate(
    records: list[CandidateRecord], config: dict[str, Any], split_type: str | None = None
) -> CandidateRecord:
    excluded = set(config["model_selection"]["exclude_ablations"])
    eligible = [
        record
        for record in records
        if record.spec.ablation_id not in excluded
        and record.result.selection_score is not None
        and np.isfinite(record.result.selection_score)
        and (split_type is None or record.spec.split_type == split_type)
    ]
    if not eligible:
        raise ValueError("no eligible validation candidate is available")
    return max(
        eligible,
        key=lambda record: cast(float, record.result.selection_score),
    )


def _prepare_output_paths(
    matrix: list[ExperimentSpec], output_dir: Path, *, overwrite: bool
) -> tuple[Path, Path]:
    prediction_dir = output_dir / "predictions"
    summary_path = output_dir / "experiments.csv"
    expected = [
        prediction_dir
        / f"predictions_{spec.split_type}_{spec.ablation_id}_{spec.model_id}.parquet"
        for spec in matrix
    ]
    conflicts = [path for path in [summary_path, *expected] if path.exists()]
    if conflicts and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing validation output: {conflicts[0]}")
    prediction_dir.mkdir(parents=True, exist_ok=True)
    return prediction_dir, summary_path


def run_validation_experiments(
    *,
    config_path: Path,
    split_dir: Path,
    output_dir: Path,
    model_dir: Path,
    overwrite: bool,
) -> dict[str, Any]:
    """Execute, persist, select, and reload-check the 38 validation experiments."""

    config = load_experiment_config(config_path)
    matrix = build_experiment_matrix(config)
    threshold, calibration_bins, permutation_repeats = _evaluation_settings(config)
    prediction_dir, summary_path = _prepare_output_paths(matrix, output_dir, overwrite=overwrite)
    datasets = {
        split_type: load_train_validation_splits(split_dir, split_type, config_path)
        for split_type in SPLIT_TYPES
    }
    git_commit = _git_commit()
    source_fingerprint = _source_fingerprint(config_path)
    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
    run_at = datetime.now(UTC).isoformat()

    experiment_rows: list[dict[str, Any]] = []
    segment_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    candidates: list[CandidateRecord] = []

    for position, spec in enumerate(matrix, start=1):
        started = time.perf_counter()
        train, validation = datasets[spec.split_type]
        features = get_ablation_features(config, spec.ablation_id)
        categorical, numeric = split_feature_types(features)
        result = fit_candidate(
            train,
            validation,
            config=config,
            ablation_id=spec.ablation_id,
            model_id=spec.model_id,
            categorical_features=categorical,
            numeric_features=numeric,
            threshold=threshold,
            calibration_bins=calibration_bins,
        )
        probabilities = predict_probabilities(result, validation)
        predictions = build_prediction_frame(
            validation, probabilities, spec, str(config["target"])
        )
        evaluation = evaluate_predictions(
            predictions,
            threshold=threshold,
            calibration_bins=calibration_bins,
        )
        prediction_path = (
            prediction_dir
            / f"predictions_{spec.split_type}_{spec.ablation_id}_{spec.model_id}.parquet"
        )
        predictions.to_parquet(prediction_path, index=False, engine="pyarrow")

        record = CandidateRecord(spec, result, validation, probabilities)
        candidates.append(record)
        coefficient_rows.extend(_coefficient_rows(record))
        segment_rows.extend(_segment_rows(spec.experiment_id, spec, evaluation["segments"]))
        calibration_rows.extend(
            _calibration_rows(
                spec.experiment_id,
                spec,
                evaluation["overall"]["calibration_curve"],
            )
        )
        experiment_rows.append(
            {
                "experiment_id": spec.experiment_id,
                "split_type": spec.split_type,
                "split_part": "val",
                "ablation_id": spec.ablation_id,
                "model_id": spec.model_id,
                "n_train": len(train),
                "n_val": len(validation),
                "n_test": None,
                "n_users_train": train["user_id"].nunique(),
                "n_users_val": validation["user_id"].nunique(),
                "n_users_test": None,
                "hyperparams": _json(_model_hyperparameters(config, spec.model_id)),
                "feature_columns": _json(features),
                "seed": config["seed"],
                "git_commit": git_commit,
                "source_fingerprint": source_fingerprint,
                "config_sha256": config_sha256,
                "run_at": run_at,
                "threshold": threshold,
                "calibration_bins": calibration_bins,
                "n_validation_predictions": len(predictions),
                "prediction_path": prediction_path.as_posix(),
                "test_accessed": False,
                "duration_seconds": time.perf_counter() - started,
                **_overall_columns(evaluation["overall"]),
            }
        )
        print(
            f"validation_experiment_completed position={position}/38 "
            f"experiment_id={spec.experiment_id} pr_auc={result.selection_score:.6f}",
            flush=True,
        )

    selected = _best_candidate(candidates, config)
    selected_by_split = {
        split_type: _best_candidate(candidates, config, split_type) for split_type in SPLIT_TYPES
    }
    selected_path = model_dir / (
        f"model_{selected.spec.ablation_id}_{selected.spec.model_id}.joblib"
    )
    if selected_path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite selected model: {selected_path}")
    _atomic_dump(selected.result.pipeline, selected_path)
    reloaded_pipeline = joblib.load(selected_path)
    reloaded_result = replace(selected.result, pipeline=reloaded_pipeline)
    reloaded_probabilities = predict_probabilities(reloaded_result, selected.validation)
    predictions_match = bool(
        np.array_equal(selected.probabilities, reloaded_probabilities, equal_nan=True)
    )
    max_abs_diff = float(np.max(np.abs(selected.probabilities - reloaded_probabilities)))
    if not predictions_match:
        raise RuntimeError(
            f"saved model prediction mismatch; maximum absolute difference={max_abs_diff}"
        )

    selected_ids = {
        selected.spec.experiment_id,
        *(record.spec.experiment_id for record in selected_by_split.values()),
    }
    for row in experiment_rows:
        row["selected"] = row["experiment_id"] == selected.spec.experiment_id
        row["selected_for_split"] = row["experiment_id"] in selected_ids

    importance_rows = [
        *coefficient_rows,
        *_permutation_rows(
            selected,
            repeats=permutation_repeats,
            seed=int(config["seed"]),
        ),
    ]
    pd.DataFrame(experiment_rows).to_csv(summary_path, index=False)
    pd.DataFrame(segment_rows).to_csv(output_dir / "segment_metrics.csv", index=False)
    pd.DataFrame(calibration_rows).to_csv(output_dir / "calibration_curves.csv", index=False)
    pd.DataFrame(importance_rows).to_csv(output_dir / "feature_importance.csv", index=False)

    selection_payload = {
        "selection_metric": config["model_selection"]["metric"],
        "selection_split_part": config["model_selection"]["split_part"],
        "excluded_ablations": config["model_selection"]["exclude_ablations"],
        "global": {
            "experiment_id": selected.spec.experiment_id,
            "split_type": selected.spec.split_type,
            "ablation_id": selected.spec.ablation_id,
            "model_id": selected.spec.model_id,
            "validation_pr_auc": selected.result.selection_score,
            "artifact_path": selected_path.as_posix(),
        },
        "per_split": {
            split_type: {
                "experiment_id": record.spec.experiment_id,
                "ablation_id": record.spec.ablation_id,
                "model_id": record.spec.model_id,
                "validation_pr_auc": record.result.selection_score,
            }
            for split_type, record in selected_by_split.items()
        },
        "prediction_reload_check": {
            "matches": predictions_match,
            "max_absolute_difference": max_abs_diff,
        },
        "test_evaluated": False,
        "experiment_count": len(experiment_rows),
        "seed": config["seed"],
        "git_commit": git_commit,
        "source_fingerprint": source_fingerprint,
        "config_sha256": config_sha256,
        "run_at": run_at,
        "library_versions": _library_versions(),
    }
    selection_path = output_dir / "selection.json"
    selection_path.write_text(
        json.dumps(selection_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "validation_experiments_completed "
        f"count={len(experiment_rows)} selected={selected.spec.experiment_id} "
        f"reload_match={str(predictions_match).lower()} test_evaluated=false",
        flush=True,
    )
    return selection_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_validation_experiments(
        config_path=args.config,
        split_dir=args.split_dir,
        output_dir=args.output_dir,
        model_dir=args.model_dir,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
