"""PHASE 9 performance aggregation and controlled failure probes."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.tests.evaluation.comparison import nearest_rank_percentile
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.harness import BUILD_ERROR_CASES, GRAPH_CASES, run_case
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode
from backend.tests.evaluation.scenario import ScenarioBuildError, build_scenario


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def aggregate_paid_performance(payload: Mapping[str, Any]) -> dict[str, object]:
    """Aggregate service metrics from stored real-provider case results.

    Judge calls are excluded because they are evaluation overhead rather than
    part of the routine-generation workflow.
    """

    runs = payload.get("cases")
    if not isinstance(runs, list) or not runs:
        raise ValueError("paid evaluation payload must contain non-empty cases")
    latencies = [int(run["wall_clock_ms"]) for run in runs]
    input_tokens = sum(int(run["input_tokens"]) for run in runs)
    output_tokens = sum(int(run["output_tokens"]) for run in runs)
    graph_calls = sum(int(run["llm_call_count"]) for run in runs)
    completed = sum(1 for run in runs if run["status_code"] == "SUCCEEDED")
    return {
        "source": "stored real-provider evaluation",
        "model_label": payload.get("model_label"),
        "run_count": len(runs),
        "latency_ms": {
            "min": min(latencies),
            "p50": nearest_rank_percentile(latencies, 0.50),
            "p95": nearest_rank_percentile(latencies, 0.95),
            "max": max(latencies),
        },
        "token_usage": {
            "input_total": input_tokens,
            "output_total": output_tokens,
            "total": input_tokens + output_tokens,
            "average_per_run": round((input_tokens + output_tokens) / len(runs), 1),
        },
        "llm_calls": {
            "graph_total": graph_calls,
            "average_per_run": round(graph_calls / len(runs), 4),
            "judge_calls_excluded": int(payload.get("llm_calls_made", graph_calls)) - graph_calls,
        },
        "workflow_completion_rate": _rate(completed, len(runs)),
        "fallback_rate": _rate(sum(bool(run["used_fallback"]) for run in runs), len(runs)),
        "repair_rate": _rate(sum(int(run["repair_attempts"]) > 0 for run in runs), len(runs)),
    }


@dataclass(frozen=True, slots=True)
class GraphProbe:
    name: str
    case_id: str
    script: Script
    expected_signal: Callable[[Any], bool]


def _case(case_id: str) -> Any:
    return next(case for case in GRAPH_CASES if case.case_id == case_id)


def graph_probes() -> tuple[GraphProbe, ...]:
    base = GRAPH_CASES[0].case_id
    return (
        GraphProbe(
            "retriever_no_vector_result",
            "SQ-RAG-002",
            Script(),
            lambda run: run.has_plan and run.status_code == "SUCCEEDED",
        ),
        GraphProbe(
            "llm_timeout",
            base,
            Script(training=ScriptCode.PROVIDER_TIMEOUT),
            lambda run: any("TIMEOUT" in code for code in run.failure_codes),
        ),
        GraphProbe(
            "structured_output_parsing_error",
            base,
            Script(training=ScriptCode.PARSE_ERROR),
            lambda run: "LLM_AGENT_SCHEMA_INVALID" in run.failure_codes,
        ),
        GraphProbe(
            "agent_exception",
            base,
            Script(training=ScriptCode.PROVIDER_EXCEPTION),
            lambda run: bool(run.failure_codes),
        ),
        GraphProbe(
            "external_llm_api_failure",
            base,
            Script(
                training=ScriptCode.PROVIDER_EXCEPTION,
                recovery=ScriptCode.PROVIDER_EXCEPTION,
                feasibility=ScriptCode.PROVIDER_EXCEPTION,
                coordinator=ScriptCode.PROVIDER_EXCEPTION,
            ),
            lambda run: run.used_fallback,
        ),
        GraphProbe(
            "invalid_runtime_input",
            "SQ-INVALID-002",
            Script(),
            lambda run: not run.has_plan and bool(run.failure_codes),
        ),
    )


def _repair_cycle_guard_holds() -> bool:
    """The sole graph cycle can be entered once, then routes to fallback."""

    from backend.app.integrations.langgraph.graph import create_v3_graph
    from backend.app.integrations.langgraph.routing import after_validation

    class _Validation:
        passed = False
        repairable = True
        violation_codes = ("REQUESTED_DURATION_MISMATCH",)

    edges = {(edge.source, edge.target) for edge in create_v3_graph().get_graph().edges}
    required_edges = {
        ("coordinator_repair", "compile_repair"),
        ("compile_repair", "validate_repair"),
    }
    return (
        required_edges.issubset(edges)
        and after_validation(  # type: ignore[arg-type]
            {"integrity_validation": _Validation(), "repair_attempts": 0}
        )
        == "coordinator_repair"
        and after_validation(  # type: ignore[arg-type]
            {"integrity_validation": _Validation(), "repair_attempts": 1}
        )
        == "fallback"
    )


def run_failure_matrix() -> dict[str, object]:
    """Exercise failures and distinguish safe handling from node crashes."""

    rows: list[dict[str, object]] = []
    unhandled_node_errors = 0
    invalid_output_audits = 0
    invocation_audits = 0
    for probe in graph_probes():
        try:
            run = run_case(_case(probe.case_id), probe.script)
        except Exception as error:  # measured outcome: an escaped node error
            unhandled_node_errors += 1
            rows.append(
                {
                    "scenario": probe.name,
                    "case_id": probe.case_id,
                    "safe_termination": False,
                    "unhandled_error_type": type(error).__name__,
                }
            )
            continue

        audits = run.graph_result.invocation_audits
        invocation_audits += len(audits)
        invalid_output_audits += sum(
            audit.failure_code == "LLM_AGENT_SCHEMA_INVALID" for audit in audits
        )
        evaluation = evaluate_case(run)
        safe = not evaluation.critical_failures and probe.expected_signal(run)
        rows.append(
            {
                "scenario": probe.name,
                "case_id": probe.case_id,
                "safe_termination": safe,
                "status_code": run.status_code,
                "has_plan": run.has_plan,
                "used_fallback": run.used_fallback,
                "repair_attempts": run.repair_attempts,
                "failure_codes": list(run.failure_codes),
                "critical_failures": len(evaluation.critical_failures),
            }
        )

    for case in BUILD_ERROR_CASES:
        observed = "ACCEPTED"
        try:
            build_scenario(case)
        except ScenarioBuildError as error:
            observed = error.code
        rows.append(
            {
                "scenario": "missing_or_invalid_input",
                "case_id": case.case_id,
                "safe_termination": observed == case.expected_scenario_build_error,
                "status_code": observed,
                "has_plan": False,
                "used_fallback": False,
                "repair_attempts": 0,
                "failure_codes": [observed],
                "critical_failures": 0,
            }
        )

    loop_guard_holds = _repair_cycle_guard_holds()
    rows.append(
        {
            "scenario": "bounded_graph_repair_cycle",
            "case_id": None,
            "safe_termination": loop_guard_holds,
            "status_code": "BOUNDED_TO_ONE_REPAIR" if loop_guard_holds else "UNBOUNDED",
            "has_plan": False,
            "used_fallback": False,
            "repair_attempts": 1 if loop_guard_holds else None,
            "failure_codes": [],
            "critical_failures": 0 if loop_guard_holds else 1,
        }
    )

    safe = sum(bool(row["safe_termination"]) for row in rows)
    return {
        "execution_mode": "scripted fault injection; no external calls",
        "scenario_count": len(rows),
        "safe_termination_count": safe,
        "safe_termination_rate": _rate(safe, len(rows)),
        "unhandled_node_error_count": unhandled_node_errors,
        "node_error_rate": _rate(unhandled_node_errors, len(graph_probes())),
        "parsing_error_rate": _rate(invalid_output_audits, invocation_audits),
        "parsing_error_numerator": invalid_output_audits,
        "parsing_error_denominator": invocation_audits,
        "parsing_error_note": (
            "Controlled-fault invocation rate, not an estimate of production incidence."
        ),
        "scenarios": rows,
    }


def load_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def build_phase9_report(paid_summary_path: Path) -> dict[str, object]:
    return {
        "phase": "PHASE 9 performance and failure evaluation",
        "performance": aggregate_paid_performance(load_json(paid_summary_path)),
        "failure_evaluation": run_failure_matrix(),
    }


__all__ = [
    "aggregate_paid_performance",
    "build_phase9_report",
    "graph_probes",
    "run_failure_matrix",
]
