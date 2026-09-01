"""Evaluate one validation-frozen model configuration on test exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ml-matplotlib"))

import joblib
import matplotlib
import numpy as np
import pandas as pd
import yaml
from sklearn.inspection import permutation_importance

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from ml.src import evaluate as validation_evaluate
from ml.src.evaluate import CATEGORICAL_FEATURES, METRIC_NAMES
from ml.src.metrics import evaluate_predictions
from ml.src.train import build_pipeline, get_ablation_features, load_experiment_config
from ml.src.validate_leakage import load_excluded_columns, validate_columns, validate_dataset

DEFAULT_CONFIG_PATH = Path("ml/config/experiments.yaml")
DEFAULT_FREEZE_PATH = Path("ml/config/final_model.yaml")
DEFAULT_SPLIT_DIR = Path("ml/data/processed/splits")
DEFAULT_VALIDATION_OUTPUT_DIR = Path("ml/outputs")
DEFAULT_FINAL_OUTPUT_DIR = Path("ml/outputs/final")
DEFAULT_MODEL_DIR = Path("ml/models")

FINAL_PREDICTION_COLUMNS = (
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


class FreezeValidationError(ValueError):
    """Raised before test access when the frozen selection evidence is inconsistent."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise FreezeValidationError(f"could not load frozen config: {path}") from exc
    if not isinstance(loaded, dict):
        raise FreezeValidationError("frozen config must be a mapping")
    return loaded


def _load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeValidationError(f"could not load validation selection: {path}") from exc
    if not isinstance(loaded, dict):
        raise FreezeValidationError("validation selection must be a mapping")
    return loaded


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_fingerprint(config_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (
        config_path,
        Path(validation_evaluate.__file__),
        Path("ml/src/train.py"),
        Path("ml/src/metrics.py"),
    ):
        digest.update(path.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_freeze_guards(freeze: dict[str, Any]) -> None:
    """Fail closed unless the manifest forbids test-driven reselection and reruns."""

    if freeze.get("locked") is not True:
        raise FreezeValidationError("final model config must be locked before test access")
    guards = freeze.get("guards")
    if not isinstance(guards, dict):
        raise FreezeValidationError("frozen config must contain guards")
    if guards.get("max_test_evaluations") != 1:
        raise FreezeValidationError("max_test_evaluations must equal 1")
    if guards.get("allow_reselection_after_test") is not False:
        raise FreezeValidationError("allow_reselection_after_test must be false")
    excluded = guards.get("excluded_ablations")
    if not isinstance(excluded, list) or "A5" not in excluded:
        raise FreezeValidationError("frozen selection must exclude A5")


def validate_frozen_evidence(
    config: dict[str, Any],
    freeze: dict[str, Any],
    selection: dict[str, Any],
    experiments: pd.DataFrame,
    *,
    config_path: Path,
) -> None:
    """Prove the frozen candidate came from validation before allowing test access."""

    validate_freeze_guards(freeze)
    evidence = freeze.get("validation_evidence")
    if not isinstance(evidence, dict):
        raise FreezeValidationError("frozen config is missing validation evidence")
    candidate = freeze.get("final_candidate")
    if not isinstance(candidate, dict):
        raise FreezeValidationError("frozen config is missing final candidate")
    evaluation = freeze.get("evaluation")
    if not isinstance(evaluation, dict):
        raise FreezeValidationError("frozen config is missing evaluation settings")
    if candidate["ablation_id"] == "A5":
        raise FreezeValidationError("A5 cannot be a final model candidate")
    if candidate.get("refit_on") != "train_plus_validation":
        raise FreezeValidationError("final candidate must refit on train_plus_validation")
    if evaluation.get("split_part") != "test":
        raise FreezeValidationError("final evaluation split_part must be test")
    if selection.get("test_evaluated") is not False:
        raise FreezeValidationError("selection evidence already reports a test evaluation")
    if selection.get("selection_metric") != "pr_auc":
        raise FreezeValidationError("selection evidence must use validation PR-AUC")
    if selection.get("experiment_count") != evidence.get("experiment_count"):
        raise FreezeValidationError("validation experiment count changed after freezing")
    if _sha256(config_path) != evidence.get("config_sha256"):
        raise FreezeValidationError("experiments config changed after validation selection")
    if _source_fingerprint(config_path) != evidence.get("source_fingerprint"):
        raise FreezeValidationError("validation source fingerprint changed after selection")

    global_selection = selection.get("global")
    if not isinstance(global_selection, dict):
        raise FreezeValidationError("selection evidence has no global candidate")
    expected = {
        "experiment_id": evidence.get("experiment_id"),
        "split_type": candidate.get("split_type"),
        "ablation_id": candidate.get("ablation_id"),
        "model_id": candidate.get("model_id"),
    }
    if any(global_selection.get(key) != value for key, value in expected.items()):
        raise FreezeValidationError("frozen candidate does not match validation selection")
    if not np.isclose(
        float(global_selection["validation_pr_auc"]),
        float(evidence["selection_score"]),
        rtol=0.0,
        atol=1e-15,
    ):
        raise FreezeValidationError("frozen validation PR-AUC does not match selection evidence")

    selected_rows = experiments.loc[experiments["experiment_id"].eq(evidence["experiment_id"])]
    if len(selected_rows) != 1 or not bool(selected_rows.iloc[0]["selected"]):
        raise FreezeValidationError("frozen experiment was not the validation-selected row")
    row = selected_rows.iloc[0]
    if not np.isclose(
        float(row["pr_auc"]), float(evidence["selection_score"]), rtol=0.0, atol=1e-6
    ):
        raise FreezeValidationError("frozen score does not match experiments.csv")

    configured_features = get_ablation_features(config, str(candidate["ablation_id"]))
    if configured_features != candidate.get("feature_columns"):
        raise FreezeValidationError("frozen feature columns do not match the ablation config")
    configured_parameters = dict(config["models"][candidate["model_id"]]["params"])
    configured_parameters["random_state"] = config["seed"]
    if configured_parameters != candidate.get("hyperparameters"):
        raise FreezeValidationError("frozen hyperparameters do not match experiments config")
    if candidate.get("seed") != config["seed"]:
        raise FreezeValidationError("frozen seed does not match experiments config")
    if evaluation.get("threshold") != config["evaluation"]["threshold"]:
        raise FreezeValidationError("frozen threshold does not match validation config")
    if evaluation.get("calibration_bins") != config["evaluation"]["calibration_bins"]:
        raise FreezeValidationError("frozen calibration bins do not match validation config")


def _split_feature_types(features: list[str]) -> tuple[list[str], list[str]]:
    categorical = [feature for feature in features if feature in CATEGORICAL_FEATURES]
    numeric = [feature for feature in features if feature not in CATEGORICAL_FEATURES]
    return categorical, numeric


def _atomic_dump(model: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}_", suffix=".joblib.tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        joblib.dump(model, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def create_test_attempt_marker(
    path: Path, *, freeze_path: Path, model_path: Path, candidate: dict[str, Any]
) -> dict[str, Any]:
    """Atomically consume the one permitted test-evaluation attempt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "started",
        "started_at": datetime.now(UTC).isoformat(),
        "freeze_path": freeze_path.as_posix(),
        "freeze_sha256": _sha256(freeze_path),
        "model_path": model_path.as_posix(),
        "model_sha256": _sha256(model_path),
        "experiment_id": candidate["experiment_id"],
        "max_test_evaluations": 1,
    }
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise RuntimeError(
            "test evaluation attempt already exists; refusing to inspect test again"
        ) from exc
    return payload


def _positive_probabilities(model: Any, features: pd.DataFrame) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(features), dtype=float)
    classes = np.asarray(model.classes_)
    positive = np.flatnonzero(classes == 1)
    if positive.size != 1:
        raise ValueError("final model must expose one positive class labelled 1")
    return probabilities[:, int(positive[0])]


def build_test_prediction_frame(
    test: pd.DataFrame,
    probabilities: np.ndarray,
    *,
    split_type: str,
    ablation_id: str,
    model_id: str,
    target: str,
) -> pd.DataFrame:
    """Build the contracted prediction handoff with split_part fixed to test."""

    if len(test) != len(probabilities):
        raise ValueError("test rows and probabilities must have the same length")
    frame = pd.DataFrame(
        {
            "user_id": test["user_id"].astype("string"),
            "local_date": pd.to_datetime(test["local_date"], errors="raise").dt.date,
            "split_type": split_type,
            "split_part": "test",
            "ablation_id": ablation_id,
            "model_id": model_id,
            "y_true": test[target].astype("int8"),
            "y_prob": np.asarray(probabilities, dtype="float32"),
            "history_days": test["history_days"].astype("int16"),
            "history_bucket": test["history_bucket"].astype("category"),
            "experience_level_code": test["experience_level_code"].astype("category"),
        }
    )
    for column in ("split_type", "split_part", "ablation_id", "model_id"):
        frame[column] = frame[column].astype("category")
    return frame.loc[:, list(FINAL_PREDICTION_COLUMNS)]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _segment_rows(evaluation_id: str, segments: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment_name, values in segments.items():
        for segment_value, result in values.items():
            matrix = result["confusion_matrix"]["values"]
            rows.append(
                {
                    "evaluation_id": evaluation_id,
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


def _importance_rows(
    pipeline: Any,
    test: pd.DataFrame,
    features: list[str],
    *,
    model_id: str,
    target: str,
    repeats: int,
    seed: int,
) -> list[dict[str, Any]]:
    if model_id == "logreg":
        names = pipeline.named_steps["preprocessor"].get_feature_names_out()
        coefficients = np.asarray(pipeline.named_steps["model"].coef_)[0]
        return [
            {
                "method": "logistic_coefficient",
                "feature": str(feature),
                "importance_mean": float(coefficient),
                "importance_std": None,
            }
            for feature, coefficient in zip(names, coefficients, strict=True)
        ]

    importance = permutation_importance(
        pipeline,
        test.loc[:, features],
        test[target],
        scoring="average_precision",
        n_repeats=repeats,
        random_state=seed,
        n_jobs=-1,
    )
    return [
        {
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


def _save_calibration_figure(calibration: dict[str, Any], destination: Path) -> None:
    figure, axis = plt.subplots(figsize=(6, 5))
    axis.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect calibration")
    axis.plot(
        calibration["probability_predicted"],
        calibration["probability_true"],
        marker="o",
        color="#2563EB",
        label="Final model",
    )
    axis.set(xlabel="Mean predicted score", ylabel="Observed frequency", xlim=(0, 1), ylim=(0, 1))
    axis.set_title("Holdout Test Calibration (Synthetic Whoop Data)")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(destination, dpi=200)
    plt.close(figure)


def _save_confusion_figure(matrix: list[list[int]], destination: Path) -> None:
    values = np.asarray(matrix, dtype=int)
    figure, axis = plt.subplots(figsize=(5, 4.5))
    image = axis.imshow(values, cmap="Blues")
    for row in range(2):
        for column in range(2):
            axis.text(column, row, f"{values[row, column]:,}", ha="center", va="center")
    axis.set_xticks([0, 1], labels=["Predicted 0", "Predicted 1"])
    axis.set_yticks([0, 1], labels=["Actual 0", "Actual 1"])
    axis.set_title("Holdout Test Confusion Matrix")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    figure.savefig(destination, dpi=200)
    plt.close(figure)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def run_final_test_evaluation(
    *,
    config_path: Path,
    freeze_path: Path,
    split_dir: Path,
    validation_output_dir: Path,
    final_output_dir: Path,
    model_dir: Path,
) -> dict[str, Any]:
    """Refit the frozen candidate and consume the single permitted test evaluation."""

    config = load_experiment_config(config_path)
    freeze = _load_yaml(freeze_path)
    selection = _load_json(validation_output_dir / "selection.json")
    experiments = pd.read_csv(validation_output_dir / "experiments.csv")
    validate_frozen_evidence(config, freeze, selection, experiments, config_path=config_path)

    candidate = freeze["final_candidate"]
    evidence = freeze["validation_evidence"]
    evaluation_config = freeze["evaluation"]
    split_type = str(candidate["split_type"])
    train_path = split_dir / f"{split_type}_train.csv"
    validation_path = split_dir / f"{split_type}_val.csv"
    validate_dataset(train_path, config_path)
    validate_dataset(validation_path, config_path)
    train = pd.read_csv(train_path)
    validation = pd.read_csv(validation_path)
    development = pd.concat([train, validation], ignore_index=True)

    features = list(candidate["feature_columns"])
    categorical, numeric = _split_feature_types(features)
    pipeline = build_pipeline(
        str(candidate["model_id"]),
        config,
        features,
        categorical_features=categorical,
        numeric_features=numeric,
    )
    target = str(config["target"])
    pipeline.fit(development.loc[:, features], development[target])

    final_model_path = model_dir / (
        f"final_model_{candidate['ablation_id']}_{candidate['model_id']}.joblib"
    )
    _atomic_dump(pipeline, final_model_path)
    reloaded_pipeline = joblib.load(final_model_path)

    evaluation_id = f"final_{split_type}_{candidate['ablation_id']}_{candidate['model_id']}_test"
    attempt_path = final_output_dir / "test_evaluation_attempt.json"
    attempt = create_test_attempt_marker(
        attempt_path,
        freeze_path=freeze_path,
        model_path=final_model_path,
        candidate={"experiment_id": evaluation_id},
    )

    # First test access occurs only after the immutable freeze and attempt marker.
    test_path = split_dir / f"{split_type}_test.csv"
    test = pd.read_csv(test_path)
    validate_columns(test.columns, load_excluded_columns(config_path))
    probabilities = _positive_probabilities(pipeline, test.loc[:, features])
    reloaded_probabilities = _positive_probabilities(reloaded_pipeline, test.loc[:, features])
    reload_match = bool(np.array_equal(probabilities, reloaded_probabilities, equal_nan=True))
    max_abs_diff = float(np.max(np.abs(probabilities - reloaded_probabilities)))
    if not reload_match:
        raise RuntimeError(f"reloaded final model predictions differ by up to {max_abs_diff}")

    predictions = build_test_prediction_frame(
        test,
        probabilities,
        split_type=split_type,
        ablation_id=str(candidate["ablation_id"]),
        model_id=str(candidate["model_id"]),
        target=target,
    )
    evaluation = evaluate_predictions(
        predictions,
        threshold=float(evaluation_config["threshold"]),
        calibration_bins=int(evaluation_config["calibration_bins"]),
    )
    overall = evaluation["overall"]
    matrix = overall["confusion_matrix"]["values"]
    calibration = overall["calibration_curve"]
    if calibration is None:
        raise RuntimeError("final calibration curve is unavailable")

    final_output_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = final_output_dir / (
        f"predictions_{split_type}_{candidate['ablation_id']}_{candidate['model_id']}_test.parquet"
    )
    predictions.to_parquet(prediction_path, index=False, engine="pyarrow")
    pd.DataFrame(_segment_rows(evaluation_id, evaluation["segments"])).to_csv(
        final_output_dir / "segment_metrics.csv", index=False
    )
    pd.DataFrame(
        {
            "bin_index": range(len(calibration["probability_true"])),
            "probability_true": calibration["probability_true"],
            "probability_predicted": calibration["probability_predicted"],
        }
    ).to_csv(final_output_dir / "calibration_curve.csv", index=False)
    importance_rows = _importance_rows(
        pipeline,
        test,
        features,
        model_id=str(candidate["model_id"]),
        target=target,
        repeats=int(evaluation_config["permutation_repeats"]),
        seed=int(candidate["seed"]),
    )
    pd.DataFrame(importance_rows).to_csv(final_output_dir / "feature_importance.csv", index=False)
    _save_calibration_figure(calibration, final_output_dir / "calibration_curve.png")
    _save_confusion_figure(matrix, final_output_dir / "confusion_matrix.png")

    metrics_row = {
        "evaluation_id": evaluation_id,
        "split_type": split_type,
        "split_part": "test",
        "ablation_id": candidate["ablation_id"],
        "model_id": candidate["model_id"],
        "n_development": len(development),
        "n_users_development": development["user_id"].nunique(),
        "n_test": len(test),
        "n_users_test": test["user_id"].nunique(),
        "threshold": evaluation_config["threshold"],
        **{metric: overall["metrics"][metric] for metric in METRIC_NAMES},
        "tn": matrix[0][0],
        "fp": matrix[0][1],
        "fn": matrix[1][0],
        "tp": matrix[1][1],
        "validation_pr_auc": evidence["selection_score"],
        "reselection_performed": False,
        "test_evaluation_count": 1,
        "prediction_reload_match": reload_match,
        "prediction_reload_max_abs_diff": max_abs_diff,
        "freeze_sha256": _sha256(freeze_path),
        "model_sha256": _sha256(final_model_path),
        "git_commit": _git_commit(),
        "evaluated_at": datetime.now(UTC).isoformat(),
    }
    pd.DataFrame([metrics_row]).to_csv(final_output_dir / "final_metrics.csv", index=False)
    final_payload = {
        **metrics_row,
        "feature_columns": features,
        "hyperparameters": candidate["hyperparameters"],
        "preprocessing": candidate["preprocessing"],
        "confusion_matrix": overall["confusion_matrix"],
        "calibration_curve": calibration,
        "prediction_path": prediction_path.as_posix(),
        "model_path": final_model_path.as_posix(),
        "selection_source": freeze["selection_source"],
        "validation_results_source": freeze["validation_results_source"],
        "test_driven_reselection_allowed": False,
        "library_versions": {
            package: version(package)
            for package in (
                "joblib",
                "matplotlib",
                "numpy",
                "pandas",
                "pyarrow",
                "PyYAML",
                "scikit-learn",
            )
        },
    }
    (final_output_dir / "final_metrics.json").write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    attempt.update(
        {
            "status": "completed",
            "completed_at": final_payload["evaluated_at"],
            "final_metrics_path": (final_output_dir / "final_metrics.json").as_posix(),
            "reselection_performed": False,
        }
    )
    attempt_path.write_text(
        json.dumps(attempt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "final_test_evaluation_completed "
        f"evaluation_id={evaluation_id} pr_auc={overall['metrics']['pr_auc']:.6f} "
        f"reload_match={str(reload_match).lower()} reselection=false test_evaluation_count=1",
        flush=True,
    )
    return final_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE_PATH)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument(
        "--validation-output-dir", type=Path, default=DEFAULT_VALIDATION_OUTPUT_DIR
    )
    parser.add_argument("--final-output-dir", type=Path, default=DEFAULT_FINAL_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_final_test_evaluation(
        config_path=args.config,
        freeze_path=args.freeze,
        split_dir=args.split_dir,
        validation_output_dir=args.validation_output_dir,
        final_output_dir=args.final_output_dir,
        model_dir=args.model_dir,
    )


if __name__ == "__main__":
    main()
