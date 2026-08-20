from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml.src.train import (
    ExperimentConfigError,
    build_pipeline,
    create_model,
    fit_candidate,
    get_ablation_features,
    load_experiment_config,
    select_best_candidate,
    validate_experiment_config,
)

CONFIG_PATH = Path(__file__).parents[1] / "config" / "experiments.yaml"


@pytest.fixture
def config() -> dict[str, object]:
    return load_experiment_config(CONFIG_PATH)


def test_ablation_features_follow_block_order(config: dict[str, object]) -> None:
    expected = [
        *config["feature_blocks"]["A1"],  # type: ignore[index]
        *config["feature_blocks"]["A2"],  # type: ignore[index]
    ]

    assert get_ablation_features(config, "A2") == expected
    assert get_ablation_features(config, "A2-lag1") == [
        "workout_completed_prev_day",
        "day_of_week",
    ]
    assert "experience_level_code" in get_ablation_features(config, "A1")
    assert get_ablation_features(config, "A0") == []


def test_ablation_features_remove_duplicates_without_reordering(
    config: dict[str, object],
) -> None:
    duplicate_config = deepcopy(config)
    duplicate_config["feature_blocks"]["A2"].insert(0, "day_of_week")  # type: ignore[index]

    features = get_ablation_features(duplicate_config, "A2")

    assert features.count("day_of_week") == 1
    assert features[:3] == ["experience_level_code", "day_of_week", "is_weekend"]


def test_ablation_features_reject_excluded_columns(config: dict[str, object]) -> None:
    invalid_config = deepcopy(config)
    invalid_config["feature_blocks"]["A1"].append("activity_type")  # type: ignore[index]

    with pytest.raises(ExperimentConfigError, match="forbidden columns: activity_type"):
        get_ablation_features(invalid_config, "A1")


def test_config_rejects_unknown_direct_ablation_column(config: dict[str, object]) -> None:
    invalid_config = deepcopy(config)
    invalid_config["ablations"]["A2-lag1"]["columns"].append(  # type: ignore[index]
        "unknown_feature"
    )

    with pytest.raises(ExperimentConfigError, match="references unknown features"):
        validate_experiment_config(invalid_config)


def test_config_loader_reports_missing_required_key(
    config: dict[str, object],
    tmp_path: Path,
) -> None:
    invalid_config_path = tmp_path / "invalid.yaml"
    invalid_config_path.write_text("target: workout_completed\n", encoding="utf-8")

    with pytest.raises(ExperimentConfigError, match="config is missing required key 'seed'"):
        load_experiment_config(invalid_config_path)


@pytest.mark.parametrize(
    ("model_id", "expected_type"),
    [
        ("majority", DummyClassifier),
        ("logreg", LogisticRegression),
        ("rf", RandomForestClassifier),
        ("histgb", HistGradientBoostingClassifier),
    ],
)
def test_model_factory_creates_supported_models(
    config: dict[str, object],
    model_id: str,
    expected_type: type[object],
) -> None:
    model = create_model(model_id, config)

    assert isinstance(model, expected_type)
    if model_id != "majority":
        assert model.get_params()["random_state"] == config["seed"]


def test_pipeline_can_fit_small_in_memory_dataframe(config: dict[str, object]) -> None:
    feature_columns = get_ablation_features(config, "A1")
    pipeline = build_pipeline(
        "logreg",
        config,
        feature_columns,
        categorical_features=["experience_level_code"],
        numeric_features=["day_of_week", "is_weekend"],
    )
    dataframe = pd.DataFrame(
        {
            "experience_level_code": [
                "BEGINNER",
                "INTERMEDIATE",
                "ADVANCED",
                "BEGINNER",
                "INTERMEDIATE",
                "ADVANCED",
            ],
            "day_of_week": [0, 1, 5, 2, 6, 3],
            "is_weekend": [False, False, True, False, True, False],
            "workout_completed": [0, 1, 0, 1, 0, 1],
        }
    )

    pipeline.fit(dataframe[feature_columns], dataframe["workout_completed"])

    assert isinstance(pipeline, Pipeline)
    assert pipeline.predict_proba(dataframe[feature_columns]).shape == (6, 2)


@pytest.mark.parametrize("model_id", ["logreg", "rf", "histgb"])
def test_pipeline_handles_contractual_first_observation_missing_values(
    config: dict[str, object], model_id: str
) -> None:
    feature_columns = get_ablation_features(config, "A3")
    categorical = [
        "experience_level_code",
        "resting_hr_trend_code_prev_day",
        "last_workout_type_code_prev_day",
    ]
    numeric = [column for column in feature_columns if column not in categorical]
    dataframe = pd.DataFrame(
        {
            column: ([None, "STABLE", "UPWARD", "DOWNWARD", "STABLE", "UPWARD"]
            if column == "resting_hr_trend_code_prev_day"
            else [None, "NONE", "RUN", "NONE", "RUN", "NONE"]
            if column == "last_workout_type_code_prev_day"
            else ["BEGINNER", "INTERMEDIATE", "ADVANCED"] * 2)
            for column in categorical
        }
    )
    for index, column in enumerate(numeric):
        dataframe[column] = [float("nan"), 1 + index, 2 + index, 3 + index, 4 + index, 5 + index]
    dataframe["workout_completed"] = [0, 1, 0, 1, 0, 1]
    pipeline = build_pipeline(
        model_id,
        config,
        feature_columns,
        categorical_features=categorical,
        numeric_features=numeric,
    )

    pipeline.fit(dataframe[feature_columns], dataframe["workout_completed"])

    assert pipeline.predict_proba(dataframe[feature_columns]).shape == (6, 2)


def test_fit_candidate_uses_validation_pr_auc(config: dict[str, object]) -> None:
    dataframe = pd.DataFrame(
        {
            "experience_level_code": [
                "BEGINNER",
                "INTERMEDIATE",
                "ADVANCED",
                "BEGINNER",
                "INTERMEDIATE",
                "ADVANCED",
                "BEGINNER",
                "ADVANCED",
            ],
            "day_of_week": [0, 1, 5, 2, 6, 3, 4, 0],
            "is_weekend": [False, False, True, False, True, False, False, False],
            "workout_completed": [0, 1, 0, 1, 0, 1, 1, 0],
        }
    )

    result = fit_candidate(
        dataframe.iloc[:6],
        dataframe.iloc[6:],
        config=config,
        ablation_id="A1",
        model_id="logreg",
        categorical_features=["experience_level_code"],
        numeric_features=["day_of_week", "is_weekend"],
        threshold=0.5,
        calibration_bins=2,
    )

    assert result.selection_metric == "pr_auc"
    assert result.selection_score == result.validation_evaluation["metrics"]["pr_auc"]

    excluded_a5 = replace(result, ablation_id="A5", selection_score=1.0)
    selected = select_best_candidate([excluded_a5, result], config)
    assert selected is result
