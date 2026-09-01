"""Fail closed when a processed dataset contains excluded source columns."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

DEFAULT_INPUT_PATH = Path("ml/data/processed/feature_dataset.csv")
DEFAULT_CONFIG_PATH = Path("ml/config/experiments.yaml")


class LeakageValidationError(ValueError):
    """Raised when leakage validation cannot prove that the dataset is safe."""


def load_excluded_columns(config_path: Path) -> frozenset[str]:
    """Load and validate the complete excluded-column contract from YAML."""
    try:
        with config_path.open(encoding="utf-8") as stream:
            config: Any = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as error:
        raise LeakageValidationError(f"Unable to load leakage config: {config_path}") from error

    if not isinstance(config, Mapping):
        raise LeakageValidationError("Leakage config must be a mapping")
    excluded = config.get("excluded")
    if not isinstance(excluded, Mapping) or not excluded:
        raise LeakageValidationError("Leakage config must contain a non-empty excluded mapping")

    columns: set[str] = set()
    for group_name, group_columns in excluded.items():
        if not isinstance(group_name, str) or not group_name:
            raise LeakageValidationError("Leakage config contains an invalid exclusion group name")
        if not isinstance(group_columns, list) or not group_columns:
            raise LeakageValidationError(
                f"Leakage config group {group_name!r} must contain one or more columns"
            )
        if any(not isinstance(column, str) or not column for column in group_columns):
            raise LeakageValidationError(
                f"Leakage config group {group_name!r} contains an invalid column name"
            )
        columns.update(group_columns)

    if not columns:
        raise LeakageValidationError("Leakage config does not exclude any columns")
    return frozenset(columns)


def read_dataset_columns(dataset_path: Path) -> list[str]:
    """Read only the schema needed for leakage validation."""
    if not dataset_path.is_file():
        raise LeakageValidationError(f"Processed dataset does not exist: {dataset_path}")
    suffix = dataset_path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(dataset_path, nrows=0).columns.tolist()
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(dataset_path).columns.tolist()
    except (OSError, ValueError) as error:
        message = f"Unable to read processed dataset schema: {dataset_path}"
        raise LeakageValidationError(message) from error
    raise LeakageValidationError(f"Unsupported processed dataset format: {dataset_path.suffix}")


def validate_columns(columns: Iterable[str], excluded_columns: Iterable[str]) -> None:
    """Raise when any configured excluded source column reaches the final dataset."""
    dataset_columns = set(columns)
    excluded = set(excluded_columns)
    if not dataset_columns:
        raise LeakageValidationError("Processed dataset has no columns")
    if not excluded:
        raise LeakageValidationError("No excluded columns supplied for leakage validation")

    leaked = sorted(dataset_columns.intersection(excluded))
    if leaked:
        raise LeakageValidationError(
            "Leakage validation failed; excluded columns in processed dataset: "
            + ", ".join(leaked)
        )


def validate_dataset(dataset_path: Path, config_path: Path) -> tuple[int, int]:
    """Validate a processed CSV or Parquet dataset against the YAML contract."""
    excluded_columns = load_excluded_columns(config_path)
    dataset_columns = read_dataset_columns(dataset_path)
    validate_columns(dataset_columns, excluded_columns)
    return len(dataset_columns), len(excluded_columns)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Processed CSV or Parquet dataset to validate",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Experiment YAML containing the excluded-column contract",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_column_count, excluded_column_count = validate_dataset(args.input, args.config)
    print(
        "leakage_validation_passed "
        f"input={args.input} dataset_columns={dataset_column_count} "
        f"excluded_columns={excluded_column_count}"
    )


if __name__ == "__main__":
    main()
