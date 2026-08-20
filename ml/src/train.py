"""Config-driven training primitives for the Track B handoff."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from ml.src.metrics import evaluate_binary_classification

SUPPORTED_ESTIMATORS = {
    "majority": ("sklearn.dummy.DummyClassifier", DummyClassifier),
    "logreg": ("sklearn.linear_model.LogisticRegression", LogisticRegression),
    "rf": ("sklearn.ensemble.RandomForestClassifier", RandomForestClassifier),
    "histgb": (
        "sklearn.ensemble.HistGradientBoostingClassifier",
        HistGradientBoostingClassifier,
    ),
}
REQUIRED_METRICS = {"precision", "recall", "f1", "roc_auc", "pr_auc", "brier"}
REQUIRED_CURVES = {"calibration", "confusion_matrix"}
EXPERIENCE_LEVEL_COLUMN = "experience_level_code"
NON_FEATURE_SEGMENTS = {"history_days", "history_bucket"}
REQUIRED_EVALUATION_SEGMENTS = {"history_bucket", EXPERIENCE_LEVEL_COLUMN}


class ExperimentConfigError(ValueError):
    """Raised when the experiment configuration violates the Track B contract."""


@dataclass(frozen=True)
class TrainingResult:
    """One fitted candidate and its validation-only selection evidence."""

    ablation_id: str
    model_id: str
    feature_columns: tuple[str, ...]
    pipeline: Pipeline
    validation_evaluation: dict[str, Any]
    selection_metric: str
    selection_score: float | None


def load_experiment_config(path: str | Path) -> dict[str, Any]:
    """Load and validate an experiments YAML file."""

    config_path = Path(path)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            loaded = yaml.safe_load(config_file)
    except OSError as exc:
        raise ExperimentConfigError(f"could not read config '{config_path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ExperimentConfigError(f"invalid YAML in config '{config_path}': {exc}") from exc

    if not isinstance(loaded, Mapping):
        raise ExperimentConfigError("config root must be a mapping")

    config = dict(loaded)
    validate_experiment_config(config)
    return config


def validate_experiment_config(config: Mapping[str, Any]) -> None:
    """Fail closed when required training or selection settings are invalid."""

    seed = _required_value(config, "seed", "config")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ExperimentConfigError("config.seed must be an integer")

    target = _required_value(config, "target", "config")
    if not isinstance(target, str) or not target:
        raise ExperimentConfigError("config.target must be a non-empty string")

    identifiers = _string_list(
        _required_value(config, "identifiers", "config"), "config.identifiers"
    )
    segments = _string_list(_required_value(config, "segments", "config"), "config.segments")

    excluded = _mapping(_required_value(config, "excluded", "config"), "config.excluded")
    for group_name, columns in excluded.items():
        _string_list(columns, f"config.excluded.{group_name}")

    feature_blocks = _mapping(
        _required_value(config, "feature_blocks", "config"),
        "config.feature_blocks",
    )
    if not feature_blocks:
        raise ExperimentConfigError("config.feature_blocks must not be empty")
    for block_name, columns in feature_blocks.items():
        _string_list(columns, f"config.feature_blocks.{block_name}")

    if EXPERIENCE_LEVEL_COLUMN not in segments:
        raise ExperimentConfigError(
            f"config.segments must retain {EXPERIENCE_LEVEL_COLUMN} for segment evaluation"
        )
    a1_features = _string_list(feature_blocks.get("A1"), "config.feature_blocks.A1")
    if EXPERIENCE_LEVEL_COLUMN not in a1_features:
        raise ExperimentConfigError(
            f"config.feature_blocks.A1 must include {EXPERIENCE_LEVEL_COLUMN} as a model feature"
        )

    models = _mapping(_required_value(config, "models", "config"), "config.models")
    _validate_models(models)

    ablations = _mapping(_required_value(config, "ablations", "config"), "config.ablations")
    if not ablations:
        raise ExperimentConfigError("config.ablations must not be empty")
    _validate_ablations(ablations, feature_blocks, models)

    evaluation = _mapping(_required_value(config, "evaluation", "config"), "config.evaluation")
    configured_metrics = set(
        _string_list(
            _required_value(evaluation, "metrics", "config.evaluation"), "config.evaluation.metrics"
        )
    )
    missing_metrics = sorted(REQUIRED_METRICS - configured_metrics)
    if missing_metrics:
        raise ExperimentConfigError(
            f"config.evaluation.metrics is missing required metrics: {', '.join(missing_metrics)}"
        )
    configured_curves = set(
        _string_list(
            _required_value(evaluation, "curves", "config.evaluation"), "config.evaluation.curves"
        )
    )
    missing_curves = sorted(REQUIRED_CURVES - configured_curves)
    if missing_curves:
        raise ExperimentConfigError(
            f"config.evaluation.curves is missing required curves: {', '.join(missing_curves)}"
        )
    evaluation_segments = _mapping(
        _required_value(evaluation, "segments", "config.evaluation"),
        "config.evaluation.segments",
    )
    missing_segments = sorted(REQUIRED_EVALUATION_SEGMENTS - set(evaluation_segments))
    if missing_segments:
        raise ExperimentConfigError(
            "config.evaluation.segments is missing configured segments: "
            + ", ".join(missing_segments)
        )

    selection = _mapping(
        _required_value(config, "model_selection", "config"),
        "config.model_selection",
    )
    if selection.get("metric") != "pr_auc":
        raise ExperimentConfigError("config.model_selection.metric must be 'pr_auc'")
    if selection.get("split_part") != "val":
        raise ExperimentConfigError("config.model_selection.split_part must be 'val'")
    excluded_ablations = _string_list(
        _required_value(selection, "exclude_ablations", "config.model_selection"),
        "config.model_selection.exclude_ablations",
    )
    if "A5" not in excluded_ablations:
        raise ExperimentConfigError("config.model_selection.exclude_ablations must include A5")

    forbidden_columns = _forbidden_feature_columns(config, target, identifiers, segments)
    for ablation_id in ablations:
        selected = _feature_columns_unchecked(config, str(ablation_id))
        violations = [column for column in selected if column in forbidden_columns]
        if violations:
            raise ExperimentConfigError(
                f"config.ablations.{ablation_id} selects forbidden columns: "
                + ", ".join(violations)
            )


def get_ablation_features(config: Mapping[str, Any], ablation_id: str) -> list[str]:
    """Build a de-duplicated feature list in YAML block and column order."""

    features = _feature_columns_unchecked(config, ablation_id)
    target = _required_value(config, "target", "config")
    identifiers = _string_list(
        _required_value(config, "identifiers", "config"), "config.identifiers"
    )
    segments = _string_list(_required_value(config, "segments", "config"), "config.segments")
    forbidden_columns = _forbidden_feature_columns(config, target, identifiers, segments)
    violations = [column for column in features if column in forbidden_columns]
    if violations:
        raise ExperimentConfigError(
            f"ablation '{ablation_id}' selects forbidden columns: {', '.join(violations)}"
        )
    return features


def create_model(model_id: str, config: Mapping[str, Any]) -> Any:
    """Create one supported estimator and inject the configured seed."""

    models = _mapping(_required_value(config, "models", "config"), "config.models")
    if model_id not in SUPPORTED_ESTIMATORS:
        supported = ", ".join(SUPPORTED_ESTIMATORS)
        raise ExperimentConfigError(f"unsupported model '{model_id}'; expected one of: {supported}")
    if model_id not in models:
        raise ExperimentConfigError(f"config.models is missing '{model_id}'")

    model_config = _mapping(models[model_id], f"config.models.{model_id}")
    expected_path, estimator_class = SUPPORTED_ESTIMATORS[model_id]
    if model_config.get("estimator") != expected_path:
        raise ExperimentConfigError(f"config.models.{model_id}.estimator must be '{expected_path}'")
    params = dict(_mapping(model_config.get("params"), f"config.models.{model_id}.params"))

    if model_id != "majority":
        seed = _required_value(config, "seed", "config")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ExperimentConfigError("config.seed must be an integer")
        params["random_state"] = seed

    try:
        return estimator_class(**params)
    except TypeError as exc:
        raise ExperimentConfigError(f"invalid parameters for model '{model_id}': {exc}") from exc


def build_pipeline(
    model_id: str,
    config: Mapping[str, Any],
    feature_columns: Sequence[str],
    *,
    categorical_features: Sequence[str] | None = None,
    numeric_features: Sequence[str] | None = None,
) -> Pipeline:
    """Build a fitted-artifact-ready pipeline from an explicit feature type split.

    Track A must supply the categorical/numeric partition after validating the
    delivered DataFrame dtypes. This function deliberately does not infer types.
    HistGradientBoosting receives the selected DataFrame unchanged and uses its
    native categorical support; categorical columns therefore must use compatible
    dtypes when Track A is connected.
    """

    ordered_features = _deduplicate(feature_columns)
    model = create_model(model_id, config)

    if model_id == "majority":
        return Pipeline([("preprocessor", "passthrough"), ("model", model)])
    if not ordered_features:
        raise ValueError(f"model '{model_id}' requires at least one feature")
    if categorical_features is None or numeric_features is None:
        raise ValueError(
            "categorical_features and numeric_features must be supplied explicitly; "
            "dtype inference is deferred until the Track A handoff"
        )

    categorical = _deduplicate(categorical_features)
    numeric = _deduplicate(numeric_features)
    _validate_feature_type_partition(ordered_features, categorical, numeric)

    model_config = _mapping(
        _mapping(config["models"], "config.models")[model_id],
        f"config.models.{model_id}",
    )
    preprocessing = _mapping(
        model_config.get("preprocessing"),
        f"config.models.{model_id}.preprocessing",
    )

    transformers: list[tuple[str, Any, list[str]]] = []
    if categorical:
        categorical_mode = preprocessing.get("categorical")
        if categorical_mode == "onehot":
            categorical_transformer: Any = Pipeline(
                [
                    (
                        "imputer",
                        SimpleImputer(strategy="constant", fill_value="__MISSING__"),
                    ),
                    ("encoder", OneHotEncoder(handle_unknown="ignore")),
                ]
            )
        elif model_id == "histgb" and categorical_mode == "native":
            categorical_transformer = Pipeline(
                [
                    (
                        "imputer",
                        SimpleImputer(strategy="constant", fill_value="__MISSING__"),
                    ),
                    (
                        "encoder",
                        OrdinalEncoder(
                            handle_unknown="use_encoded_value",
                            unknown_value=-1,
                            dtype=np.float64,
                        ),
                    ),
                ]
            )
        else:
            raise ExperimentConfigError(
                f"unsupported categorical preprocessing '{categorical_mode}' "
                f"for model '{model_id}'"
            )
        transformers.append(("categorical", categorical_transformer, categorical))
    if numeric:
        numeric_steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
        numeric_mode = preprocessing.get("numeric")
        if numeric_mode == "standardize":
            numeric_steps.append(("scaler", StandardScaler()))
        elif numeric_mode == "passthrough":
            pass
        else:
            raise ExperimentConfigError(
                f"unsupported numeric preprocessing '{numeric_mode}' for model '{model_id}'"
            )
        transformers.append(("numeric", Pipeline(numeric_steps), numeric))

    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=False,
    )
    if model_id == "histgb":
        # OrdinalEncoder retains one column per categorical feature. HistGB then
        # performs native categorical splits on those leading encoded columns.
        model.set_params(categorical_features=list(range(len(categorical))))
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def fit_candidate(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    *,
    config: Mapping[str, Any],
    ablation_id: str,
    model_id: str | None,
    categorical_features: Sequence[str] | None = None,
    numeric_features: Sequence[str] | None = None,
    threshold: float,
    calibration_bins: int,
) -> TrainingResult:
    """Fit on train only and evaluate on validation only.

    A future test DataFrame is intentionally not accepted here. After selecting a
    candidate with :func:`select_best_candidate`, callers can pass the held-out
    test DataFrame to :func:`predict_probabilities` and the evaluation layer once.
    """

    validate_experiment_config(config)
    resolved_model_id = _resolve_model_id(config, ablation_id, model_id)
    features = get_ablation_features(config, ablation_id)
    target = str(config["target"])

    _require_dataframe_columns(train_df, [target, *features], "train_df")
    _require_dataframe_columns(validation_df, [target, *features], "validation_df")

    pipeline = build_pipeline(
        resolved_model_id,
        config,
        features,
        categorical_features=categorical_features,
        numeric_features=numeric_features,
    )
    x_train = train_df.loc[:, features]
    x_validation = validation_df.loc[:, features]
    pipeline.fit(x_train, train_df[target])

    validation_probabilities = _positive_class_probabilities(pipeline, x_validation)
    validation_evaluation = evaluate_binary_classification(
        validation_df[target],
        validation_probabilities,
        threshold=threshold,
        calibration_bins=calibration_bins,
    )
    selection_metric = str(config["model_selection"]["metric"])
    selection_score = validation_evaluation["metrics"].get(selection_metric)

    return TrainingResult(
        ablation_id=ablation_id,
        model_id=resolved_model_id,
        feature_columns=tuple(features),
        pipeline=pipeline,
        validation_evaluation=validation_evaluation,
        selection_metric=selection_metric,
        selection_score=selection_score,
    )


def predict_probabilities(result: TrainingResult, dataframe: pd.DataFrame) -> np.ndarray:
    """Predict positive-class probabilities for a val or held-out test DataFrame."""

    features = list(result.feature_columns)
    _require_dataframe_columns(dataframe, features, "dataframe")
    return _positive_class_probabilities(result.pipeline, dataframe.loc[:, features])


def select_best_candidate(
    candidates: Sequence[TrainingResult],
    config: Mapping[str, Any],
) -> TrainingResult:
    """Select the highest validation PR-AUC candidate, excluding A5 by config."""

    validate_experiment_config(config)
    selection = config["model_selection"]
    metric = str(selection["metric"])
    excluded_ablations = set(selection["exclude_ablations"])

    eligible: list[TrainingResult] = []
    for candidate in candidates:
        if candidate.ablation_id in excluded_ablations:
            continue
        if candidate.selection_metric != metric or candidate.selection_score is None:
            continue
        if math.isfinite(candidate.selection_score):
            eligible.append(candidate)

    if not eligible:
        raise ValueError(
            f"no eligible candidate has a finite validation {metric} score after exclusions"
        )
    return max(
        eligible,
        key=lambda candidate: (
            candidate.selection_score if candidate.selection_score is not None else -math.inf
        ),
    )


def _validate_models(models: Mapping[str, Any]) -> None:
    for model_id, (expected_path, _) in SUPPORTED_ESTIMATORS.items():
        if model_id not in models:
            raise ExperimentConfigError(f"config.models is missing '{model_id}'")
        model = _mapping(models[model_id], f"config.models.{model_id}")
        if model.get("estimator") != expected_path:
            raise ExperimentConfigError(
                f"config.models.{model_id}.estimator must be '{expected_path}'"
            )
        _mapping(model.get("params"), f"config.models.{model_id}.params")
        if model_id != "majority":
            _mapping(
                model.get("preprocessing"),
                f"config.models.{model_id}.preprocessing",
            )


def _validate_ablations(
    ablations: Mapping[str, Any],
    feature_blocks: Mapping[str, Any],
    models: Mapping[str, Any],
) -> None:
    known_features = {
        column
        for block_name, columns in feature_blocks.items()
        for column in _string_list(columns, f"config.feature_blocks.{block_name}")
    }
    for ablation_id, raw_spec in ablations.items():
        spec = _mapping(raw_spec, f"config.ablations.{ablation_id}")
        has_blocks = "blocks" in spec
        has_columns = "columns" in spec
        if has_blocks == has_columns:
            raise ExperimentConfigError(
                f"config.ablations.{ablation_id} must define exactly one of blocks or columns"
            )
        if has_blocks:
            blocks = _string_list(spec["blocks"], f"config.ablations.{ablation_id}.blocks")
            unknown_blocks = [block for block in blocks if block not in feature_blocks]
            if unknown_blocks:
                raise ExperimentConfigError(
                    f"config.ablations.{ablation_id}.blocks references unknown blocks: "
                    + ", ".join(unknown_blocks)
                )
        else:
            columns = _string_list(
                spec["columns"],
                f"config.ablations.{ablation_id}.columns",
            )
            unknown_columns = [column for column in columns if column not in known_features]
            if unknown_columns:
                raise ExperimentConfigError(
                    f"config.ablations.{ablation_id}.columns references unknown features: "
                    + ", ".join(unknown_columns)
                )

        override = spec.get("model_override")
        if override is not None and override not in models:
            raise ExperimentConfigError(
                f"config.ablations.{ablation_id}.model_override references "
                f"unknown model '{override}'"
            )

    a0 = _mapping(ablations.get("A0"), "config.ablations.A0")
    if a0.get("blocks") != [] or a0.get("model_override") != "majority":
        raise ExperimentConfigError(
            "config.ablations.A0 must use empty blocks and model_override 'majority'"
        )
    if "A5" not in ablations:
        raise ExperimentConfigError("config.ablations must define A5")


def _feature_columns_unchecked(config: Mapping[str, Any], ablation_id: str) -> list[str]:
    ablations = _mapping(_required_value(config, "ablations", "config"), "config.ablations")
    if ablation_id not in ablations:
        raise ExperimentConfigError(f"unknown ablation '{ablation_id}'")

    spec = _mapping(ablations[ablation_id], f"config.ablations.{ablation_id}")
    if "columns" in spec:
        return _deduplicate(
            _string_list(spec["columns"], f"config.ablations.{ablation_id}.columns")
        )

    blocks = _string_list(spec.get("blocks"), f"config.ablations.{ablation_id}.blocks")
    feature_blocks = _mapping(
        _required_value(config, "feature_blocks", "config"),
        "config.feature_blocks",
    )
    selected: list[str] = []
    for block in blocks:
        if block not in feature_blocks:
            raise ExperimentConfigError(
                f"config.ablations.{ablation_id}.blocks references unknown block '{block}'"
            )
        selected.extend(_string_list(feature_blocks[block], f"config.feature_blocks.{block}"))
    return _deduplicate(selected)


def _forbidden_feature_columns(
    config: Mapping[str, Any],
    target: Any,
    identifiers: Sequence[str],
    segments: Sequence[str],
) -> set[str]:
    excluded = _mapping(_required_value(config, "excluded", "config"), "config.excluded")
    forbidden = {
        column
        for group_name, columns in excluded.items()
        for column in _string_list(columns, f"config.excluded.{group_name}")
    }
    forbidden.update(identifiers)
    forbidden.add(str(target))
    forbidden.update(column for column in segments if column != EXPERIENCE_LEVEL_COLUMN)
    forbidden.update(NON_FEATURE_SEGMENTS)
    return forbidden


def _resolve_model_id(
    config: Mapping[str, Any],
    ablation_id: str,
    requested_model_id: str | None,
) -> str:
    ablations = _mapping(config["ablations"], "config.ablations")
    if ablation_id not in ablations:
        raise ExperimentConfigError(f"unknown ablation '{ablation_id}'")
    spec = _mapping(ablations[ablation_id], f"config.ablations.{ablation_id}")
    override = spec.get("model_override")
    if override is not None:
        if requested_model_id is not None and requested_model_id != override:
            raise ExperimentConfigError(
                f"ablation '{ablation_id}' requires model '{override}', not '{requested_model_id}'"
            )
        return str(override)
    if requested_model_id is None:
        raise ExperimentConfigError(f"model_id is required for ablation '{ablation_id}'")
    return requested_model_id


def _positive_class_probabilities(pipeline: Pipeline, features: pd.DataFrame) -> np.ndarray:
    probabilities = np.asarray(pipeline.predict_proba(features), dtype=float)
    classes = np.asarray(pipeline.classes_)
    positive_indices = np.flatnonzero(classes == 1)
    if positive_indices.size == 1:
        return probabilities[:, int(positive_indices[0])]
    if classes.size == 1:
        return np.ones(features.shape[0]) if classes[0] == 1 else np.zeros(features.shape[0])
    raise ValueError("fitted model does not expose a unique positive class labelled 1")


def _validate_feature_type_partition(
    feature_columns: Sequence[str],
    categorical_features: Sequence[str],
    numeric_features: Sequence[str],
) -> None:
    overlap = sorted(set(categorical_features) & set(numeric_features))
    if overlap:
        raise ValueError(f"features cannot be both categorical and numeric: {', '.join(overlap)}")

    declared = set(categorical_features) | set(numeric_features)
    expected = set(feature_columns)
    missing = [column for column in feature_columns if column not in declared]
    unknown = [
        column for column in [*categorical_features, *numeric_features] if column not in expected
    ]
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append("untyped features: " + ", ".join(missing))
        if unknown:
            details.append("unknown typed features: " + ", ".join(unknown))
        raise ValueError("; ".join(details))


def _require_dataframe_columns(
    dataframe: pd.DataFrame,
    required_columns: Sequence[str],
    dataframe_name: str,
) -> None:
    missing = [column for column in required_columns if column not in dataframe.columns]
    if missing:
        raise ValueError(f"{dataframe_name} is missing required columns: {', '.join(missing)}")


def _deduplicate(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _required_value(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise ExperimentConfigError(f"{path} is missing required key '{key}'")
    return mapping[key]


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentConfigError(f"{path} must be a mapping")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ExperimentConfigError(f"{path} must be a list of non-empty strings")
    return value
