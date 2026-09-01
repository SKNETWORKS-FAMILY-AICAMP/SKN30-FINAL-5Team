"""Build the causal feature dataset specified by ``ml/docs/FEATURE_SPEC.md``."""

from __future__ import annotations

import argparse
import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from features import build_feature_dataset

DEFAULT_RAW_PATH = Path("ml/data/Whoop Fitness Dataset/whoop_fitness_dataset_100k.csv")
DEFAULT_OUTPUT_PATH = Path("ml/data/processed/feature_dataset.csv")
DEFAULT_CONFIG_PATH = Path("ml/config/experiments.yaml")
DEFAULT_SPLIT_OUTPUT_DIR = Path("ml/data/processed/splits")
SPLIT_PARTS = ("train", "val", "test")


class SplitConfigurationError(ValueError):
    """Raised when the configured split contract cannot be applied safely."""


@dataclass(frozen=True)
class SplitSettings:
    """Validated, deterministic split settings from experiments.yaml."""

    seed: int
    temporal_ratios: tuple[float, float, float]
    user_ratios: tuple[float, float, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_PATH, help="Input Whoop CSV path")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output feature CSV path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing output file",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Experiment YAML containing the fixed split configuration",
    )
    parser.add_argument(
        "--split-output-dir",
        type=Path,
        help="Write the six configured time/user split CSV files to this directory",
    )
    return parser.parse_args()


def prepare_dataset(raw_path: Path) -> pd.DataFrame:
    """Read the source CSV and return the contracted causal feature dataset."""
    return build_feature_dataset(pd.read_csv(raw_path))


def write_dataset(dataset: pd.DataFrame, output_path: Path, *, overwrite: bool) -> None:
    """Write the prepared dataset without silently replacing a prior artifact."""
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)


def _load_ratios(config: Mapping[str, Any], split_type: str) -> tuple[float, float, float]:
    splits = config.get("splits")
    if not isinstance(splits, Mapping):
        raise SplitConfigurationError("Split config must contain a splits mapping")
    split_config = splits.get(split_type)
    if not isinstance(split_config, Mapping):
        raise SplitConfigurationError(f"Split config must contain {split_type!r}")
    ratios = split_config.get("ratios")
    if not isinstance(ratios, list) or len(ratios) != len(SPLIT_PARTS):
        raise SplitConfigurationError(
            f"Split config {split_type!r} must contain three train/val/test ratios"
        )
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in ratios):
        raise SplitConfigurationError(f"Split config {split_type!r} ratios must be numeric")
    normalized = tuple(float(value) for value in ratios)
    if any(value <= 0 for value in normalized) or not math.isclose(sum(normalized), 1.0):
        raise SplitConfigurationError(
            f"Split config {split_type!r} ratios must be positive and sum to 1"
        )
    return normalized  # type: ignore[return-value]


def load_split_settings(config_path: Path) -> SplitSettings:
    """Load fixed seed and temporal/user split ratios from experiments.yaml."""
    try:
        with config_path.open(encoding="utf-8") as stream:
            config: Any = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as error:
        raise SplitConfigurationError(f"Unable to load split config: {config_path}") from error

    if not isinstance(config, Mapping):
        raise SplitConfigurationError("Split config must be a mapping")
    seed = config.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise SplitConfigurationError("Split config seed must be an integer")
    return SplitSettings(
        seed=seed,
        temporal_ratios=_load_ratios(config, "time"),
        user_ratios=_load_ratios(config, "user"),
    )


def _partition_counts(total: int, ratios: tuple[float, float, float]) -> tuple[int, int, int]:
    """Allocate all items with deterministic largest-remainder rounding."""
    if total < len(SPLIT_PARTS):
        raise SplitConfigurationError("Each split requires at least one item")
    raw_counts = [total * ratio for ratio in ratios]
    counts = [math.floor(value) for value in raw_counts]
    remainder = total - sum(counts)
    ranked_parts = sorted(
        range(len(SPLIT_PARTS)),
        key=lambda index: (-(raw_counts[index] - counts[index]), index),
    )
    for index in ranked_parts[:remainder]:
        counts[index] += 1
    if any(count == 0 for count in counts):
        raise SplitConfigurationError("Split configuration produced an empty partition")
    return tuple(counts)  # type: ignore[return-value]


def create_temporal_splits(
    dataset: pd.DataFrame, ratios: tuple[float, float, float]
) -> dict[str, pd.DataFrame]:
    """Split complete dates into past, next, and final chronological partitions."""
    if "local_date" not in dataset.columns:
        raise SplitConfigurationError("Temporal split requires local_date")
    local_dates = pd.to_datetime(dataset["local_date"], errors="raise")
    unique_dates = sorted(local_dates.unique())
    train_count, val_count, _ = _partition_counts(len(unique_dates), ratios)
    boundaries = (train_count, train_count + val_count)
    date_partitions = {
        "train": set(unique_dates[: boundaries[0]]),
        "val": set(unique_dates[boundaries[0] : boundaries[1]]),
        "test": set(unique_dates[boundaries[1] :]),
    }
    return {
        part: dataset.loc[local_dates.isin(dates)].copy()
        for part, dates in date_partitions.items()
    }


def create_user_splits(
    dataset: pd.DataFrame, ratios: tuple[float, float, float], seed: int
) -> dict[str, pd.DataFrame]:
    """Split whole users deterministically without a random row-level split."""
    if "user_id" not in dataset.columns:
        raise SplitConfigurationError("User split requires user_id")
    users = sorted(dataset["user_id"].dropna().astype(str).unique())
    train_count, val_count, _ = _partition_counts(len(users), ratios)
    ranked_users = sorted(
        users,
        key=lambda user_id: hashlib.sha256(f"{seed}:{user_id}".encode()).hexdigest(),
    )
    user_partitions = {
        "train": set(ranked_users[:train_count]),
        "val": set(ranked_users[train_count : train_count + val_count]),
        "test": set(ranked_users[train_count + val_count :]),
    }
    string_user_ids = dataset["user_id"].astype(str)
    return {
        part: dataset.loc[string_user_ids.isin(users_for_part)].copy()
        for part, users_for_part in user_partitions.items()
    }


def create_splits(dataset: pd.DataFrame, settings: SplitSettings) -> dict[str, pd.DataFrame]:
    """Create the six Track A split datasets from one preprocessed dataset."""
    splits: dict[str, pd.DataFrame] = {}
    for part, split in create_temporal_splits(dataset, settings.temporal_ratios).items():
        splits[f"time_{part}"] = split
    for part, split in create_user_splits(dataset, settings.user_ratios, settings.seed).items():
        splits[f"user_{part}"] = split
    return splits


def write_splits(
    splits: Mapping[str, pd.DataFrame], output_dir: Path, *, overwrite: bool
) -> None:
    """Write all six split files without silently replacing prior artifacts."""
    output_paths = {name: output_dir / f"{name}.csv" for name in splits}
    existing = [path for path in output_paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing split output: {existing[0]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, split in splits.items():
        split.to_csv(output_paths[name], index=False)


def main() -> None:
    args = parse_args()
    dataset = prepare_dataset(args.raw)
    write_dataset(dataset, args.output, overwrite=args.overwrite)
    print(
        f"prepared_dataset rows={len(dataset)} columns={len(dataset.columns)} output={args.output}"
    )
    if args.split_output_dir:
        splits = create_splits(dataset, load_split_settings(args.config))
        write_splits(splits, args.split_output_dir, overwrite=args.overwrite)
        for name, split in splits.items():
            print(
                f"prepared_split name={name} rows={len(split)} "
                f"users={split['user_id'].nunique()}"
            )


if __name__ == "__main__":
    main()
