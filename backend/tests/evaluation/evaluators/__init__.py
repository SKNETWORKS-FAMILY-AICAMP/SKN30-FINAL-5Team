"""One evaluator set, applied to every runner.

The comparison in PHASE 6 is only meaningful if a single-agent answer and a
multi-agent answer are judged by identical code.  Keeping the aggregation here,
against `CaseRunResult` rather than against any runner's internals, is what
holds that property when the baseline runner is added.
"""

from __future__ import annotations

from backend.tests.evaluation.evaluators import (
    constraint_evaluator,
    failure_evaluator,
    safety_evaluator,
    structure_evaluator,
)
from backend.tests.evaluation.evaluators.findings import (
    CaseEvaluation,
    DefectClass,
    EvaluationReport,
    Finding,
    Severity,
)
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

EVALUATOR_ORDER = (
    safety_evaluator,
    constraint_evaluator,
    structure_evaluator,
    failure_evaluator,
)


def evaluate_case(run: CaseRunResult) -> CaseEvaluation:
    """Apply every evaluator to one run, safety first."""

    findings: list[Finding] = []
    for evaluator in EVALUATOR_ORDER:
        findings.extend(evaluator.evaluate(run))

    input_tokens, output_tokens = run.token_usage
    return CaseEvaluation(
        case_id=run.case.case_id,
        category=run.case.category.value,
        architecture_code=run.architecture_code,
        script_summary=_script_summary(run),
        status_code=run.status_code,
        has_plan=run.has_plan,
        used_fallback=run.used_fallback,
        repair_attempts=run.repair_attempts,
        llm_call_count=run.llm_call_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        wall_clock_ms=run.wall_clock_ms,
        findings=tuple(findings),
        failure_codes=run.failure_codes,
        violation_codes=run.violation_codes,
        decline_reason_codes=run.decline_reason_codes,
    )


def _script_summary(run: CaseRunResult) -> str:
    script = run.script
    return (
        f"T={script.training.value},R={script.recovery.value},"
        f"F={script.feasibility.value},C={script.coordinator.value}"
    )


__all__ = [
    "EVALUATOR_ORDER",
    "CaseEvaluation",
    "DefectClass",
    "EvaluationReport",
    "Finding",
    "Severity",
    "evaluate_case",
]
