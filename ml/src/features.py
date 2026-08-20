"""Causal feature construction for the workout-completion dataset.

Only columns defined in ``ml/docs/FEATURE_SPEC.md`` are emitted.  All values
available on the target date are derived from prior dates of the same user.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import numpy as np
import pandas as pd

USER_ID: Final = "user_id"
LOCAL_DATE: Final = "local_date"
TARGET: Final = "workout_completed"

EXPERIENCE_LEVEL_MAP: Final = {
    "Beginner": "BEGINNER",
    "Intermediate": "INTERMEDIATE",
    "Advanced": "ADVANCED",
    "Elite": "ADVANCED",
}
DAY_OF_WEEK_MAP: Final = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

REQUIRED_RAW_COLUMNS: Final = frozenset(
    {
        "user_id",
        "date",
        "day_of_week",
        "fitness_level",
        "workout_completed",
        "sleep_hours",
        "resting_heart_rate",
        "activity_duration_min",
        "activity_type",
        "activity_calories",
        "avg_heart_rate",
        "hrv",
        "recovery_score",
        "day_strain",
        "calories_burned",
        "sleep_efficiency",
        "light_sleep_hours",
        "rem_sleep_hours",
        "deep_sleep_hours",
        "wake_ups",
        "time_to_fall_asleep_min",
        "respiratory_rate",
        "skin_temp_deviation",
    }
)

# A missing sensor or activity value may only inherit the latest earlier value
# for the same user.  This dataset has no such values, but the policy preserves
# causal behaviour when the pipeline is reused.
CAUSAL_FORWARD_FILL_COLUMNS: Final = (
    "sleep_hours",
    "resting_heart_rate",
    "activity_duration_min",
    "activity_type",
    "activity_calories",
    "avg_heart_rate",
    "hrv",
    "recovery_score",
    "day_strain",
    "calories_burned",
    "sleep_efficiency",
    "light_sleep_hours",
    "rem_sleep_hours",
    "deep_sleep_hours",
    "wake_ups",
    "time_to_fall_asleep_min",
    "respiratory_rate",
    "skin_temp_deviation",
)

OUTPUT_COLUMNS: Final = (
    USER_ID,
    LOCAL_DATE,
    TARGET,
    "experience_level_code",
    "day_of_week",
    "is_weekend",
    "workout_completed_prev_day",
    "workout_count_7d",
    "workout_count_28d",
    "completion_rate_7d",
    "completion_rate_28d",
    "days_since_last_workout",
    "consecutive_workout_days",
    "consecutive_non_workout_days",
    "is_return_mode_candidate",
    "sleep_minutes_prev_day",
    "resting_hr_prev_day",
    "resting_hr_trend_code_prev_day",
    "last_workout_duration_min_prev_day",
    "last_workout_type_code_prev_day",
    "last_workout_calories_prev_day",
    "last_workout_avg_hr_prev_day",
    "sleep_minutes_delta_28d",
    "resting_hr_delta_28d",
    "hrv_prev_day",
    "hrv_delta_28d",
    "recovery_score_prev_day",
    "day_strain_prev_day",
    "calories_burned_prev_day",
    "sleep_efficiency_prev_day",
    "light_sleep_hours_prev_day",
    "rem_sleep_hours_prev_day",
    "deep_sleep_hours_prev_day",
    "wake_ups_prev_day",
    "time_to_fall_asleep_min_prev_day",
    "respiratory_rate_prev_day",
    "skin_temp_deviation_prev_day",
    "history_days",
    "history_bucket",
)


class FeatureValidationError(ValueError):
    """Raised when the raw data cannot produce the contracted feature schema."""


def _require_raw_columns(raw: pd.DataFrame) -> None:
    missing = REQUIRED_RAW_COLUMNS.difference(raw.columns)
    if missing:
        raise FeatureValidationError(
            f"Raw dataset is missing required columns: {', '.join(sorted(missing))}"
        )


def _previous_window_stat(
    frame: pd.DataFrame, column: str, window: str, statistic: str
) -> pd.Series:
    """Return a same-user, previous-calendar-window statistic aligned to each row."""
    values = pd.Series(index=frame.index, dtype="float64")
    for _, user_frame in frame.groupby(USER_ID, sort=False):
        indexed = user_frame.set_index(LOCAL_DATE)[column]
        rolling = indexed.rolling(window, closed="left", min_periods=1)
        if statistic == "sum":
            calculated = rolling.sum()
        elif statistic == "count":
            calculated = rolling.count()
        elif statistic == "mean":
            calculated = rolling.mean()
        else:
            raise ValueError(f"Unsupported rolling statistic: {statistic}")
        values.loc[user_frame.index] = calculated.to_numpy()
    return values


def _previous_day(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame.groupby(USER_ID, sort=False)[column].shift(1)


def _causal_forward_fill(frame: pd.DataFrame) -> None:
    """Fill only from earlier observations of the same user.

    A user's first unavailable value remains missing because no causal source
    exists.  This deliberately avoids zero filling and future user statistics.
    """
    frame.loc[:, CAUSAL_FORWARD_FILL_COLUMNS] = frame.groupby(USER_ID, sort=False)[
        list(CAUSAL_FORWARD_FILL_COLUMNS)
    ].ffill()


def _consecutive_history(values: Iterable[int]) -> tuple[list[int], list[int]]:
    """Count prior consecutive completed and non-completed observations."""
    prior_completed: list[int] = []
    prior_not_completed: list[int] = []
    completed_streak = 0
    not_completed_streak = 0
    for value in values:
        prior_completed.append(completed_streak)
        prior_not_completed.append(not_completed_streak)
        if value == 1:
            completed_streak += 1
            not_completed_streak = 0
        else:
            completed_streak = 0
            not_completed_streak += 1
    return prior_completed, prior_not_completed


def _add_consecutive_history(frame: pd.DataFrame) -> None:
    completed_values = pd.Series(index=frame.index, dtype="int16")
    non_completed_values = pd.Series(index=frame.index, dtype="int16")
    for _, user_frame in frame.groupby(USER_ID, sort=False):
        completed_streak, non_completed_streak = _consecutive_history(
            user_frame[TARGET].astype(int).tolist()
        )
        completed_values.loc[user_frame.index] = completed_streak
        non_completed_values.loc[user_frame.index] = non_completed_streak
    frame["consecutive_workout_days"] = completed_values.astype("int16")
    frame["consecutive_non_workout_days"] = non_completed_values.astype("int16")


def _add_previous_numeric_features(frame: pd.DataFrame) -> None:
    previous_numeric_columns = {
        "sleep_minutes_prev_day": "sleep_minutes",
        "resting_hr_prev_day": "resting_heart_rate",
        "last_workout_duration_min_prev_day": "activity_duration_min",
        "last_workout_calories_prev_day": "activity_calories",
        "last_workout_avg_hr_prev_day": "avg_heart_rate",
        "hrv_prev_day": "hrv",
        "recovery_score_prev_day": "recovery_score",
        "day_strain_prev_day": "day_strain",
        "calories_burned_prev_day": "calories_burned",
        "sleep_efficiency_prev_day": "sleep_efficiency",
        "light_sleep_hours_prev_day": "light_sleep_hours",
        "rem_sleep_hours_prev_day": "rem_sleep_hours",
        "deep_sleep_hours_prev_day": "deep_sleep_hours",
        "time_to_fall_asleep_min_prev_day": "time_to_fall_asleep_min",
        "respiratory_rate_prev_day": "respiratory_rate",
        "skin_temp_deviation_prev_day": "skin_temp_deviation",
    }
    for output_column, raw_column in previous_numeric_columns.items():
        frame[output_column] = _previous_day(frame, raw_column).astype("float32")
    frame["wake_ups_prev_day"] = _previous_day(frame, "wake_ups").astype("Int16")


def _add_baseline_features(frame: pd.DataFrame) -> None:
    # The baseline is the user's preceding 28 calendar days.  The target date
    # and all future dates are excluded by ``closed='left'``.
    sleep_baseline = _previous_window_stat(frame, "sleep_minutes", "28D", "mean")
    resting_hr_baseline = _previous_window_stat(frame, "resting_heart_rate", "28D", "mean")
    hrv_baseline = _previous_window_stat(frame, "hrv", "28D", "mean")

    frame["sleep_minutes_delta_28d"] = (
        frame["sleep_minutes_prev_day"] - sleep_baseline
    ).astype("float32")
    frame["resting_hr_delta_28d"] = (
        frame["resting_hr_prev_day"] - resting_hr_baseline
    ).astype("float32")
    frame["hrv_delta_28d"] = (frame["hrv_prev_day"] - hrv_baseline).astype("float32")

    trend = pd.Series(pd.NA, index=frame.index, dtype="string")
    delta = frame["resting_hr_delta_28d"]
    trend.loc[delta.notna() & (delta >= 2.0)] = "UPWARD"
    trend.loc[delta.notna() & (delta <= -2.0)] = "DOWNWARD"
    trend.loc[delta.notna() & delta.between(-2.0, 2.0, inclusive="neither")] = "STABLE"
    trend.loc[delta.notna() & delta.isin([-2.0, 2.0])] = "STABLE"
    frame["resting_hr_trend_code_prev_day"] = trend.astype("category")


def _validate_output(frame: pd.DataFrame) -> None:
    unexpected = set(frame.columns).difference(OUTPUT_COLUMNS)
    missing = set(OUTPUT_COLUMNS).difference(frame.columns)
    if missing or unexpected:
        raise FeatureValidationError(
            f"Output schema mismatch; missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    if frame[list(OUTPUT_COLUMNS)].columns.tolist() != list(OUTPUT_COLUMNS):
        raise FeatureValidationError("Output columns are not in the contracted order")


def build_feature_dataset(raw: pd.DataFrame) -> pd.DataFrame:
    """Transform raw Whoop rows into the exact FEATURE_SPEC output schema.

    Missing values from first observations and rolling-history windows remain
    missing.  Imputation is intentionally deferred to Track A step 5.
    """
    _require_raw_columns(raw)
    frame = raw.copy()
    if frame[[USER_ID, "date"]].isna().any().any():
        raise FeatureValidationError("user_id and date must not be missing")

    frame[USER_ID] = frame[USER_ID].astype("string")
    frame[LOCAL_DATE] = pd.to_datetime(frame.pop("date"), errors="raise").dt.normalize()
    frame[TARGET] = pd.to_numeric(frame[TARGET], errors="raise").astype("int8")
    if not frame[TARGET].isin([0, 1]).all():
        raise FeatureValidationError("workout_completed must contain only 0 or 1")
    if frame.duplicated([USER_ID, LOCAL_DATE]).any():
        raise FeatureValidationError("user_id and local_date must be unique together")

    frame = frame.sort_values([USER_ID, LOCAL_DATE], kind="stable").reset_index(drop=True)
    _causal_forward_fill(frame)
    experience_level = frame["fitness_level"].map(EXPERIENCE_LEVEL_MAP)
    if experience_level.isna().any():
        unknown = sorted(frame.loc[experience_level.isna(), "fitness_level"].unique())
        raise FeatureValidationError(f"Unknown fitness_level values: {unknown}")
    frame["experience_level_code"] = experience_level.astype("category")

    frame["day_of_week"] = frame["day_of_week"].map(DAY_OF_WEEK_MAP)
    if frame["day_of_week"].isna().any():
        raise FeatureValidationError("day_of_week contains values outside Monday through Sunday")
    frame["day_of_week"] = frame["day_of_week"].astype("int8")
    frame["is_weekend"] = (frame["day_of_week"] >= 5).astype(bool)
    frame["sleep_minutes"] = (pd.to_numeric(frame["sleep_hours"], errors="raise") * 60).astype(
        "float32"
    )

    frame["history_days"] = frame.groupby(USER_ID, sort=False).cumcount().astype("int16")
    frame["history_bucket"] = pd.Categorical(
        np.select(
            [frame["history_days"] <= 7, frame["history_days"] <= 28],
            ["0-7", "8-28"],
            default="29+",
        ),
        categories=["0-7", "8-28", "29+"],
    )

    frame["workout_completed_prev_day"] = _previous_day(frame, TARGET).fillna(0).astype("int8")
    for days in (7, 28):
        count = _previous_window_stat(frame, TARGET, f"{days}D", "sum")
        observed_days = _previous_window_stat(frame, TARGET, f"{days}D", "count")
        frame[f"workout_count_{days}d"] = count.fillna(0).astype("int8")
        frame[f"completion_rate_{days}d"] = (count / observed_days).astype("float32")

    completed_date = frame[LOCAL_DATE].where(frame[TARGET].eq(1))
    last_completed_date = completed_date.groupby(frame[USER_ID], sort=False).ffill()
    prior_completed_date = last_completed_date.groupby(frame[USER_ID], sort=False).shift(1)
    frame["days_since_last_workout"] = (
        (frame[LOCAL_DATE] - prior_completed_date).dt.days.fillna(-1).astype("int16")
    )
    _add_consecutive_history(frame)
    frame["is_return_mode_candidate"] = (frame["days_since_last_workout"] >= 14).astype(bool)

    _add_previous_numeric_features(frame)
    last_workout_type = frame["activity_type"].replace({"Rest Day": "NONE"}).astype("string")
    frame["last_workout_type_code_prev_day"] = (
        last_workout_type.groupby(frame[USER_ID], sort=False).shift(1).astype("category")
    )
    _add_baseline_features(frame)

    output = frame.loc[:, list(OUTPUT_COLUMNS)].copy()
    output[LOCAL_DATE] = output[LOCAL_DATE].dt.date
    _validate_output(output)
    return output
