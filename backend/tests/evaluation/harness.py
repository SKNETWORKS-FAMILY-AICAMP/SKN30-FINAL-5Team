"""Small synchronous entry points the evaluation tests share."""

from __future__ import annotations

import asyncio

from backend.tests.evaluation.dataset import EvaluationCase, load_smoke_dataset
from backend.tests.evaluation.evaluators import CaseEvaluation, EvaluationReport, evaluate_case
from backend.tests.evaluation.runners.fake_chat import Script
from backend.tests.evaluation.runners.run_multi_agent import (
    ARCHITECTURE_CODE,
    CaseRunResult,
    MultiAgentRunner,
)

SMOKE_DATASET = load_smoke_dataset()

# Cases whose input is refused before the graph. They are asserted separately.
GRAPH_CASES = tuple(case for case in SMOKE_DATASET if case.expected_scenario_build_error is None)
BUILD_ERROR_CASES = tuple(
    case for case in SMOKE_DATASET if case.expected_scenario_build_error is not None
)

# Cases whose envelope excludes at least one exercise. These are where a leak
# could happen at all, so adversarial scripts are pointed at them.
EXCLUSION_CASES = tuple(
    case for case in GRAPH_CASES if case.expected_constraints.excluded_exercise_codes
)


def run_case(case: EvaluationCase, script: Script | None = None) -> CaseRunResult:
    """Run one case through the real graph with a scripted provider."""

    return asyncio.run(MultiAgentRunner().run(case, script or Script()))


def evaluate(case: EvaluationCase, script: Script | None = None) -> CaseEvaluation:
    return evaluate_case(run_case(case, script))


def build_report(run_id: str, evaluations: list[CaseEvaluation]) -> EvaluationReport:
    return EvaluationReport(
        run_id=run_id,
        architecture_code=ARCHITECTURE_CODE,
        cases=evaluations,
    )


__all__ = [
    "BUILD_ERROR_CASES",
    "EXCLUSION_CASES",
    "GRAPH_CASES",
    "SMOKE_DATASET",
    "build_report",
    "evaluate",
    "run_case",
]
