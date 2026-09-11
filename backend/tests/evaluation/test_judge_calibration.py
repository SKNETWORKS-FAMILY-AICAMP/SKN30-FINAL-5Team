"""The calibration statistics, including the cases where they must say nothing."""

from __future__ import annotations

import pytest

from backend.tests.evaluation.judge_calibration import (
    MINIMUM_PAIRS,
    compare_groups,
    paired_preference,
    pearson,
)


def test_a_group_gap_is_the_difference_of_the_two_means() -> None:
    result = compare_groups(
        label_a="model plan", values_a=[4.0, 4.0, 3.0], label_b="fallback", values_b=[3.0, 3.0]
    )

    assert result.mean_a == pytest.approx(3.6667, abs=1e-4)
    assert result.mean_b == 3.0
    assert result.difference == pytest.approx(0.6667, abs=1e-4)


def test_an_empty_group_has_no_mean_and_no_difference() -> None:
    """An architecture with no fallback must not read as a zero-scoring one."""

    result = compare_groups(label_a="a", values_a=[4.0], label_b="b", values_b=[])

    assert result.mean_b is None
    assert result.difference is None


def test_pairing_is_by_case_not_by_position() -> None:
    left = {"c1": 4.0, "c2": 3.0, "c3": 5.0}
    right = {"c3": 4.0, "c1": 3.0, "c2": 3.0}

    result = paired_preference(left, right)

    assert (result.wins_a, result.wins_b, result.ties) == (2, 0, 1)
    assert result.mean_difference == pytest.approx(0.6667, abs=1e-4)


def test_cases_only_one_side_judged_are_dropped() -> None:
    result = paired_preference({"c1": 4.0, "c2": 5.0}, {"c1": 3.0})

    assert result.decided == 1
    assert result.ties == 0


def test_a_split_too_small_to_mean_anything_reports_no_p_value() -> None:
    result = paired_preference({"c1": 4.0}, {"c1": 3.0})

    assert result.decided < MINIMUM_PAIRS
    assert result.p_value is None


def test_an_even_split_is_not_a_preference() -> None:
    left = {f"c{i}": 4.0 for i in range(10)}
    right = dict(left)
    for i in range(5):
        right[f"c{i}"] = 3.0  # a wins 5
    for i in range(5, 10):
        right[f"c{i}"] = 5.0  # b wins 5

    result = paired_preference(left, right)

    assert (result.wins_a, result.wins_b) == (5, 5)
    assert result.p_value == 1.0


def test_a_clean_sweep_is() -> None:
    left = {f"c{i}": 5.0 for i in range(10)}
    right = {f"c{i}": 3.0 for i in range(10)}

    result = paired_preference(left, right)

    assert (result.wins_a, result.wins_b) == (10, 0)
    assert result.p_value is not None
    assert result.p_value < 0.01


def test_a_constant_series_has_no_correlation_rather_than_a_perfect_one() -> None:
    """Every plan landing on the requested duration is not evidence of tracking."""

    assert pearson([1.0, 1.0, 1.0], [3.0, 4.0, 5.0]) is None


def test_correlation_is_none_when_there_is_nothing_to_correlate() -> None:
    assert pearson([1.0], [2.0]) is None
    assert pearson([1.0, 2.0], [1.0]) is None


def test_correlation_recovers_a_known_relationship() -> None:
    assert pearson([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]) == 1.0
    assert pearson([1.0, 2.0, 3.0, 4.0], [8.0, 6.0, 4.0, 2.0]) == -1.0
