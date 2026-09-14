from __future__ import annotations

import pytest

from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.paid_run_cli import (
    _forecast_line,
    _select_cases,
)

CASES = planning_cases(GRAPH_CASES)


def test_paid_run_case_filter_preserves_dataset_order() -> None:
    requested = [CASES[2].case_id, CASES[0].case_id]

    selected = _select_cases(CASES, requested)

    assert [case.case_id for case in selected] == [CASES[0].case_id, CASES[2].case_id]


def test_paid_run_case_filter_rejects_unknown_case() -> None:
    with pytest.raises(ValueError, match="UNKNOWN-CASE"):
        _select_cases(CASES, ["UNKNOWN-CASE"])


def test_paid_run_forecast_omits_judge_calls_when_disabled() -> None:
    forecast = _forecast_line(1, 3, judge_enabled=False)

    assert "12 graph LLM calls" in forecast
    assert "0 judge calls" in forecast
