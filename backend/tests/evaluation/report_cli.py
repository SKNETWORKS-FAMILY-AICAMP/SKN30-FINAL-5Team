"""Regenerate the PHASE 2 result artifacts.

    uv run python -m backend.tests.evaluation.report_cli

Costs nothing and calls no provider: the scripted model answers every role.  Run
it whenever the dataset or the evaluators change, and commit the regenerated
files alongside so a reviewer can diff results rather than rerun them.

Latency is deliberately **not** written here.  A scripted provider returns
instantly, so any percentile this run produced would describe the harness rather
than the service, and publishing it as a latency metric would be a false claim.
PHASE 9 measures latency against a real provider.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.evaluators import CaseEvaluation, evaluate_case
from backend.tests.evaluation.harness import BUILD_ERROR_CASES, GRAPH_CASES, SMOKE_DATASET, run_case
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode
from backend.tests.evaluation.runners.run_multi_agent import ARCHITECTURE_CODE
from backend.tests.evaluation.scenario import ScenarioBuildError, build_scenario

RUN_ID = "phase2-deterministic-smoke-v1"
DEFAULT_OUTPUT_DIR = Path("results")

# The adversarial matrix. Each entry names one way the provider misbehaves; the
# result files record what the service did about it.
ADVERSARIAL_SCRIPTS: tuple[tuple[str, Script], ...] = (
    ("compliant", Script()),
    ("training_safety_violating", Script(training=ScriptCode.SAFETY_VIOLATING)),
    ("training_pool_escape", Script(training=ScriptCode.POOL_ESCAPE)),
    ("training_duration_violating", Script(training=ScriptCode.DURATION_VIOLATING)),
    ("training_phase_missing", Script(training=ScriptCode.PHASE_MISSING)),
    (
        "coordinator_safety_violating",
        Script(
            coordinator=ScriptCode.SAFETY_VIOLATING,
            coordinator_repair=ScriptCode.SAFETY_VIOLATING,
        ),
    ),
    (
        "coordinator_duration_violating",
        Script(
            coordinator=ScriptCode.DURATION_VIOLATING,
            coordinator_repair=ScriptCode.DURATION_VIOLATING,
        ),
    ),
    ("recovery_role_violating", Script(recovery=ScriptCode.ROLE_VIOLATING)),
    ("training_schema_invalid", Script(training=ScriptCode.SCHEMA_INVALID)),
    ("training_provider_timeout", Script(training=ScriptCode.PROVIDER_TIMEOUT)),
    ("training_hangs", Script(training=ScriptCode.HANG)),
    (
        "total_provider_failure",
        Script(
            training=ScriptCode.PROVIDER_EXCEPTION,
            recovery=ScriptCode.PROVIDER_EXCEPTION,
            feasibility=ScriptCode.PROVIDER_EXCEPTION,
            coordinator=ScriptCode.PROVIDER_EXCEPTION,
        ),
    ),
)


def _evaluate_all() -> list[tuple[str, CaseEvaluation]]:
    rows: list[tuple[str, CaseEvaluation]] = []
    for script_name, script in ADVERSARIAL_SCRIPTS:
        for case in GRAPH_CASES:
            rows.append((script_name, evaluate_case(run_case(case, script))))
    return rows


def _build_error_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in BUILD_ERROR_CASES:
        observed: str
        try:
            build_scenario(case)
        except ScenarioBuildError as error:
            observed = error.code
        else:
            observed = "ACCEPTED"
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category.value,
                "expected_rejection_code": case.expected_scenario_build_error,
                "observed": observed,
                "passed": observed == case.expected_scenario_build_error,
            }
        )
    return rows


def _fallback_coverage() -> dict[str, object]:
    """Measure how often the deterministic path can still fill the session.

    Recorded because the answer is not uniform: the fallback is bounded by the
    surviving pool and the Recovery ceiling, and those are tightest exactly for
    the constrained users the fallback matters most to. This is a measurement of
    the evaluation catalog, not of production data, so the report reads it as a
    question to confirm against the reviewed catalog rather than as a verdict.
    """

    total_failure = Script(
        training=ScriptCode.PROVIDER_EXCEPTION,
        recovery=ScriptCode.PROVIDER_EXCEPTION,
        feasibility=ScriptCode.PROVIDER_EXCEPTION,
        coordinator=ScriptCode.PROVIDER_EXCEPTION,
    )
    rows: list[dict[str, object]] = []
    for case in GRAPH_CASES:
        if not case.expected_constraints.plan_generation_allowed:
            continue
        run = run_case(case, total_failure)
        rows.append(
            {
                "case_id": case.case_id,
                "requested_duration_minutes": case.expected_constraints.requested_duration_minutes,
                "maximum_sets_per_exercise": case.expected_constraints.maximum_sets_per_exercise,
                "excluded_exercise_count": len(case.expected_constraints.excluded_exercise_codes),
                "pool_size": len(case.pool.exercise_codes),
                "fallback_produced_plan": run.has_plan,
                "status_code": run.status_code,
            }
        )
    covered = sum(1 for row in rows if row["fallback_produced_plan"])
    return {
        "note": (
            "Under total provider failure, whether the deterministic fallback can "
            "still fill the requested duration depends on the surviving pool and "
            "the Recovery sets ceiling. When it cannot, the run fails closed with "
            "no plan rather than silently shortening the session (AGENTS.md 7). "
            "Measured against the evaluation catalog; confirm against the reviewed "
            "production catalog before drawing a product conclusion."
        ),
        "cases_measured": len(rows),
        "fallback_produced_plan": covered,
        "fallback_produced_no_plan": len(rows) - covered,
        "cases": rows,
    }


def _summary(rows: list[tuple[str, CaseEvaluation]]) -> dict[str, object]:
    by_script: dict[str, dict[str, int]] = {}
    by_category: dict[str, dict[str, int]] = {}
    for script_name, evaluation in rows:
        script_bucket = by_script.setdefault(
            script_name, {"total": 0, "passed": 0, "failed": 0, "critical": 0}
        )
        script_bucket["total"] += 1
        script_bucket["passed" if evaluation.passed else "failed"] += 1
        script_bucket["critical"] += len(evaluation.critical_failures)

        category_bucket = by_category.setdefault(
            evaluation.category, {"total": 0, "passed": 0, "failed": 0, "critical": 0}
        )
        category_bucket["total"] += 1
        category_bucket["passed" if evaluation.passed else "failed"] += 1
        category_bucket["critical"] += len(evaluation.critical_failures)

    planned = sum(1 for _, evaluation in rows if evaluation.has_plan)
    fallbacks = sum(1 for _, evaluation in rows if evaluation.used_fallback)
    return {
        "run_id": RUN_ID,
        "architecture_code": ARCHITECTURE_CODE,
        "dataset_id": SMOKE_DATASET.dataset_id,
        "provider": "scripted-offline (no LLM call, no cost)",
        "graph_case_count": len(GRAPH_CASES),
        "script_count": len(ADVERSARIAL_SCRIPTS),
        "total_runs": len(rows),
        "passed_runs": sum(1 for _, evaluation in rows if evaluation.passed),
        "failed_runs": sum(1 for _, evaluation in rows if not evaluation.passed),
        "critical_failures": sum(len(evaluation.critical_failures) for _, evaluation in rows),
        "runs_producing_a_plan": planned,
        "runs_using_deterministic_fallback": fallbacks,
        "by_script": by_script,
        "by_category": by_category,
        "latency_note": (
            "Not measured. The provider is scripted and returns instantly, so any "
            "percentile from this run would describe the harness, not the service. "
            "PHASE 9 measures latency against a real provider."
        ),
    }


def _write_cases_csv(path: Path, rows: list[tuple[str, CaseEvaluation]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "script",
                "case_id",
                "category",
                "status_code",
                "has_plan",
                "used_fallback",
                "repair_attempts",
                "llm_call_count",
                "passed",
                "failure_check_codes",
                "observation_check_codes",
            ]
        )
        for script_name, evaluation in rows:
            writer.writerow(
                [
                    script_name,
                    evaluation.case_id,
                    evaluation.category,
                    evaluation.status_code,
                    int(evaluation.has_plan),
                    int(evaluation.used_fallback),
                    evaluation.repair_attempts,
                    evaluation.llm_call_count,
                    int(evaluation.passed),
                    "|".join(finding.check_code for finding in evaluation.failures),
                    "|".join(finding.check_code for finding in evaluation.observations),
                ]
            )


def _write_failed_cases(path: Path, rows: list[tuple[str, CaseEvaluation]]) -> None:
    failed = [
        {"script": script_name, **evaluation.to_json()}
        for script_name, evaluation in rows
        if not evaluation.passed
    ]
    path.write_text(
        json.dumps({"failed_run_count": len(failed), "runs": failed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _case_index() -> list[dict[str, object]]:
    def row(case: EvaluationCase) -> dict[str, object]:
        body = asdict(case) if not hasattr(case, "model_dump") else case.model_dump(mode="json")
        return {
            "case_id": body["case_id"],
            "category": body["category"],
            "description": body["description"],
            "legacy_scenario_code": body["legacy_scenario_code"],
            "expected_outcome": body["expected_outcome"],
        }

    return [row(case) for case in SMOKE_DATASET]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    output_dir: Path = arguments.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _evaluate_all()
    summary = _summary(rows)
    summary["input_rejection_cases"] = _build_error_rows()
    summary["fallback_coverage"] = _fallback_coverage()
    summary["dataset_cases"] = _case_index()

    (output_dir / "evaluation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_cases_csv(output_dir / "evaluation_cases.csv", rows)
    _write_failed_cases(output_dir / "failed_cases.json", rows)

    print(f"runs: {summary['total_runs']}")
    print(f"passed: {summary['passed_runs']}  failed: {summary['failed_runs']}")
    print(f"critical failures: {summary['critical_failures']}")
    print(f"artifacts written to {output_dir.resolve()}")
    return 0 if summary["failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
