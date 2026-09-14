"""PHASE 9 metric definitions and failure safety evidence."""

from __future__ import annotations

from backend.tests.evaluation.comparison import nearest_rank_percentile
from backend.tests.evaluation.performance_failure import (
    aggregate_paid_performance,
    run_failure_matrix,
)


def test_nearest_rank_percentile_is_the_shared_latency_rule() -> None:
    assert nearest_rank_percentile([40, 10, 30, 20], 0.50) == 20
    assert nearest_rank_percentile([40, 10, 30, 20], 0.95) == 40
    assert nearest_rank_percentile([], 0.95) is None


def test_paid_metrics_exclude_judge_calls_from_service_call_count() -> None:
    report = aggregate_paid_performance(
        {
            "model_label": "provider:model",
            "llm_calls_made": 9,
            "cases": [
                {
                    "wall_clock_ms": 10,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "llm_call_count": 4,
                    "status_code": "SUCCEEDED",
                    "used_fallback": False,
                    "repair_attempts": 0,
                },
                {
                    "wall_clock_ms": 20,
                    "input_tokens": 200,
                    "output_tokens": 20,
                    "llm_call_count": 4,
                    "status_code": "FAILED",
                    "used_fallback": True,
                    "repair_attempts": 1,
                },
            ],
        }
    )

    assert report["llm_calls"] == {
        "graph_total": 8,
        "average_per_run": 4.0,
        "judge_calls_excluded": 1,
    }
    assert report["workflow_completion_rate"] == 0.5
    assert report["token_usage"]["average_per_run"] == 165.0  # type: ignore[index]


def test_every_failure_probe_terminates_safely_without_an_unhandled_node_error() -> None:
    report = run_failure_matrix()

    assert report["safe_termination_rate"] == 1.0
    assert report["unhandled_node_error_count"] == 0
    assert report["node_error_rate"] == 0.0
    assert report["parsing_error_numerator"] > 0
    assert all(row["safe_termination"] for row in report["scenarios"])  # type: ignore[union-attr]


def test_the_loop_probe_enters_at_most_one_repair_round() -> None:
    report = run_failure_matrix()
    loop = next(
        row
        for row in report["scenarios"]  # type: ignore[union-attr]
        if row["scenario"] == "bounded_graph_repair_cycle"
    )
    assert loop["repair_attempts"] == 1
