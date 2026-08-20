from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml.src import evaluate
from ml.src.evaluate import (
    PREDICTION_COLUMNS,
    ExperimentSpec,
    build_experiment_matrix,
    build_prediction_frame,
    load_train_validation_splits,
)
from ml.src.train import load_experiment_config

CONFIG_PATH = Path(__file__).parents[1] / "config" / "experiments.yaml"


def test_experiment_matrix_matches_documented_38_runs() -> None:
    config = load_experiment_config(CONFIG_PATH)

    matrix = build_experiment_matrix(config)

    assert len(matrix) == 38
    assert sum(spec.ablation_id == "A0" for spec in matrix) == 2
    assert sum(spec.ablation_id == "A2-lag1" for spec in matrix) == 6
    assert {spec.model_id for spec in matrix if spec.ablation_id == "A0"} == {"majority"}


def test_split_loader_never_constructs_or_reads_a_test_path(
    monkeypatch: object, tmp_path: Path
) -> None:
    accessed: list[Path] = []

    def record_validation(path: Path, config_path: Path) -> tuple[int, int]:
        del config_path
        accessed.append(path)
        return 39, 22

    def record_read(path: Path) -> pd.DataFrame:
        accessed.append(path)
        return pd.DataFrame({"workout_completed": [0]})

    monkeypatch.setattr(evaluate, "validate_dataset", record_validation)  # type: ignore[attr-defined]
    monkeypatch.setattr(evaluate.pd, "read_csv", record_read)  # type: ignore[attr-defined]

    load_train_validation_splits(tmp_path, "time", CONFIG_PATH)

    assert accessed
    assert all("test" not in path.name for path in accessed)
    assert {path.name for path in accessed} == {"time_train.csv", "time_val.csv"}


def test_prediction_frame_matches_handoff_schema() -> None:
    validation = pd.DataFrame(
        {
            "user_id": ["u1", "u2"],
            "local_date": ["2024-01-01", "2024-01-02"],
            "workout_completed": [0, 1],
            "history_days": [0, 29],
            "history_bucket": ["0-7", "29+"],
            "experience_level_code": ["BEGINNER", "ADVANCED"],
        }
    )

    predictions = build_prediction_frame(
        validation,
        np.array([0.25, 0.75]),
        ExperimentSpec("time", "A1", "logreg"),
        "workout_completed",
    )

    assert predictions.columns.tolist() == list(PREDICTION_COLUMNS)
    assert predictions["split_part"].astype(str).tolist() == ["val", "val"]
    assert predictions["y_prob"].dtype == np.dtype("float32")
