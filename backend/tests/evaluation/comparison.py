"""PHASE 6 aggregation: the same numbers, computed the same way, per architecture.

Every rate here is derived from `CaseEvaluation`, `RunMetrics` and `JudgeResult`
-- the objects the earlier phases already produce -- so an architecture cannot be
measured by code written for it.  The aggregation is separated from the CLI so it
can be exercised offline against scripted runs, which is how the comparison is
tested without spending anything.

Two readings of "did it work" are reported side by side, because collapsing them
would hide the question PHASE 6 exists to answer:

* `llm_plan_rate` -- the model produced a plan that passed the integrity gate.
  This is the architecture's own result.
* `plan_delivery_rate` -- the user received a plan at all, counting the
  deterministic fallback. This is the service's result, and the fallback belongs
  to the service rather than to any architecture.

An architecture that never produces a usable plan can still show a high delivery
rate. Reporting only the second number would credit the fallback to the model.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

from backend.tests.evaluation.architectures import ARCHITECTURE_LABELS
from backend.tests.evaluation.evaluators.agent_metrics import AgentMetricsReport
from backend.tests.evaluation.evaluators.findings import CaseEvaluation, Severity
from backend.tests.evaluation.judge.judge import JudgeResult, JudgeVerdict
from backend.tests.evaluation.judge.rubric import JudgeCriterion
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

_RATE_QUANTUM: Final = Decimal("0.0001")

# The categories the master specification asks to be reported separately.
REPORTED_CATEGORIES: Final[tuple[str, ...]] = (
    "simple",
    "moderate",
    "complex",
    "conflict",
    "safety_critical",
    "rag_retrieval",
    "failure_case",
)

# Judge criteria the comparison surfaces by name; the rest are in `judge_mean`.
HEADLINE_CRITERIA: Final[tuple[JudgeCriterion, ...]] = (
    JudgeCriterion.PERSONALIZATION,
    JudgeCriterion.FEASIBILITY,
    JudgeCriterion.OVERALL_QUALITY,
)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float((Decimal(numerator) / Decimal(denominator)).quantize(_RATE_QUANTUM))


def nearest_rank_percentile(values: Sequence[int], fraction: float) -> int | None:
    """Return the repository-standard nearest-rank percentile."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round(fraction * len(ordered)))
    return ordered[rank - 1]


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


@dataclass(frozen=True, slots=True)
class CategoryResult:
    """One category's outcome for one architecture."""

    category: str
    runs: int
    constraint_satisfied: int
    llm_plans: int
    delivered_plans: int
    critical_failures: int

    @property
    def constraint_satisfaction_rate(self) -> float | None:
        return _rate(self.constraint_satisfied, self.runs)

    def to_json(self) -> dict[str, object]:
        return {
            "runs": self.runs,
            "constraint_satisfaction_rate": self.constraint_satisfaction_rate,
            "llm_plan_rate": _rate(self.llm_plans, self.runs),
            "plan_delivery_rate": _rate(self.delivered_plans, self.runs),
            "critical_failures": self.critical_failures,
        }


@dataclass
class ArchitectureResult:
    """Every PHASE 6 metric for one architecture, over one set of runs."""

    architecture_code: str
    model_label: str
    runs: list[CaseRunResult] = field(default_factory=list)
    evaluations: list[CaseEvaluation] = field(default_factory=list)
    judgements: list[JudgeResult] = field(default_factory=list)
    agent_metrics: AgentMetricsReport | None = None

    @property
    def label(self) -> str:
        return ARCHITECTURE_LABELS.get(self.architecture_code, self.architecture_code)

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def constraint_satisfaction_rate(self) -> float | None:
        """Runs that both produced a plan and broke no deterministic constraint.

        A run with no plan counts against this. It satisfied nothing, and calling
        an empty answer constraint-satisfying would rank a silent architecture
        above a productive one.
        """

        satisfied = sum(
            1
            for run, evaluation in zip(self.runs, self.evaluations, strict=True)
            if run.has_plan and evaluation.passed
        )
        return _rate(satisfied, self.run_count)

    @property
    def llm_plan_rate(self) -> float | None:
        produced = sum(1 for run in self.runs if run.has_plan and not run.used_fallback)
        return _rate(produced, self.run_count)

    @property
    def plan_delivery_rate(self) -> float | None:
        return _rate(sum(1 for run in self.runs if run.has_plan), self.run_count)

    @property
    def critical_failure_count(self) -> int:
        return sum(
            1
            for evaluation in self.evaluations
            for finding in evaluation.findings
            if finding.severity is Severity.CRITICAL and finding.fails_case
        )

    @property
    def structured_output_success_rate(self) -> float | None:
        return self.agent_metrics.structured_output_success_rate if self.agent_metrics else None

    @property
    def safety_compliance_rate(self) -> float | None:
        return self.agent_metrics.safety_compliance_rate if self.agent_metrics else None

    @property
    def workflow_completion_rate(self) -> float | None:
        return self.agent_metrics.workflow_completion_rate if self.agent_metrics else None

    @property
    def scored_judgements(self) -> tuple[JudgeResult, ...]:
        return tuple(item for item in self.judgements if item.output is not None)

    def judge_score(self, criterion: JudgeCriterion) -> float | None:
        scores = [
            float(item.output.score_for(criterion))
            for item in self.scored_judgements
            if item.output is not None
        ]
        return _mean(scores)

    @property
    def judge_mean(self) -> float | None:
        return _mean([item.mean_score for item in self.scored_judgements if item.mean_score])

    @property
    def judge_failed_count(self) -> int:
        """Runs the judge was never asked about because a rule already failed."""

        return sum(1 for item in self.judgements if item.verdict is JudgeVerdict.FAIL)

    @property
    def judge_not_judged_count(self) -> int:
        return sum(1 for item in self.judgements if item.verdict is JudgeVerdict.NOT_JUDGED)

    @property
    def p50_latency_ms(self) -> int | None:
        return nearest_rank_percentile([run.wall_clock_ms for run in self.runs], 0.50)

    @property
    def p95_latency_ms(self) -> int | None:
        return nearest_rank_percentile([run.wall_clock_ms for run in self.runs], 0.95)

    @property
    def llm_call_count(self) -> int:
        return sum(run.llm_call_count for run in self.runs)

    @property
    def average_llm_calls(self) -> float | None:
        return _mean([float(run.llm_call_count) for run in self.runs])

    @property
    def token_totals(self) -> tuple[int, int]:
        input_total = sum(run.token_usage[0] for run in self.runs)
        output_total = sum(run.token_usage[1] for run in self.runs)
        return input_total, output_total

    @property
    def average_tokens_per_run(self) -> float | None:
        if self.run_count == 0:
            return None
        input_total, output_total = self.token_totals
        return round((input_total + output_total) / self.run_count, 1)

    def categories(self) -> tuple[CategoryResult, ...]:
        buckets: dict[str, list[tuple[CaseRunResult, CaseEvaluation]]] = {}
        for run, evaluation in zip(self.runs, self.evaluations, strict=True):
            buckets.setdefault(evaluation.category, []).append((run, evaluation))
        results = []
        for category in REPORTED_CATEGORIES:
            rows = buckets.get(category)
            if not rows:
                continue
            results.append(
                CategoryResult(
                    category=category,
                    runs=len(rows),
                    constraint_satisfied=sum(
                        1 for run, evaluation in rows if run.has_plan and evaluation.passed
                    ),
                    llm_plans=sum(1 for run, _ in rows if run.has_plan and not run.used_fallback),
                    delivered_plans=sum(1 for run, _ in rows if run.has_plan),
                    critical_failures=sum(
                        1
                        for _, evaluation in rows
                        for finding in evaluation.findings
                        if finding.severity is Severity.CRITICAL and finding.fails_case
                    ),
                )
            )
        return tuple(results)

    def to_json(self) -> dict[str, object]:
        input_tokens, output_tokens = self.token_totals
        return {
            "architecture_code": self.architecture_code,
            "label": self.label,
            "model_label": self.model_label,
            "run_count": self.run_count,
            "constraint_satisfaction_rate": self.constraint_satisfaction_rate,
            "llm_plan_rate": self.llm_plan_rate,
            "plan_delivery_rate": self.plan_delivery_rate,
            "safety_compliance_rate": self.safety_compliance_rate,
            "workflow_completion_rate": self.workflow_completion_rate,
            "structured_output_success_rate": self.structured_output_success_rate,
            "critical_failures": self.critical_failure_count,
            "judge": {
                "scored_runs": len(self.scored_judgements),
                "deterministic_failures_not_scored": self.judge_failed_count,
                "no_plan_not_scored": self.judge_not_judged_count,
                "mean": self.judge_mean,
                **{
                    criterion.value.lower(): self.judge_score(criterion)
                    for criterion in HEADLINE_CRITERIA
                },
            },
            "latency": {"p50_ms": self.p50_latency_ms, "p95_ms": self.p95_latency_ms},
            "cost_inputs": {
                "llm_calls": self.llm_call_count,
                "average_llm_calls_per_run": self.average_llm_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "average_tokens_per_run": self.average_tokens_per_run,
                "estimated_cost": None,
                "estimated_cost_note": (
                    "Omitted deliberately. docs/runbooks/v3-shadow-evaluation.md "
                    "forbids writing a cost without an approved pricing reference."
                ),
            },
            "by_category": {item.category: item.to_json() for item in self.categories()},
        }


@dataclass
class ComparisonReport:
    """A, B and C side by side, with the fairness conditions recorded."""

    results: list[ArchitectureResult] = field(default_factory=list)
    dataset_name: str = "smoke"
    repeats: int = 1
    judge_blind: bool = True
    notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "dataset": self.dataset_name,
            "repeats": self.repeats,
            "judge_blind": self.judge_blind,
            "fairness_conditions": FAIRNESS_CONDITIONS,
            "notes": list(self.notes),
            "architectures": [item.to_json() for item in self.results],
        }

    def dumps(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2, sort_keys=True)

    def markdown(self) -> str:
        """A table a reviewer can read without opening the JSON."""

        header = ("지표", *(item.label for item in self.results))
        rows: list[tuple[str, ...]] = [header]

        def add(name: str, render: Callable[[ArchitectureResult], object]) -> None:
            values = tuple(
                "n/a" if render(item) is None else str(render(item)) for item in self.results
            )
            rows.append((name, *values))

        add("실행 수", lambda item: item.run_count)
        add("Constraint Satisfaction", lambda item: item.constraint_satisfaction_rate)
        add("LLM Plan Rate (fallback 제외)", lambda item: item.llm_plan_rate)
        add("Plan Delivery Rate (fallback 포함)", lambda item: item.plan_delivery_rate)
        add("Safety Compliance", lambda item: item.safety_compliance_rate)
        add("Workflow Success", lambda item: item.workflow_completion_rate)
        add("Structured Output Success", lambda item: item.structured_output_success_rate)
        add("Critical 실패", lambda item: item.critical_failure_count)
        add("Judge 평균", lambda item: item.judge_mean)
        for criterion in HEADLINE_CRITERIA:

            def scorer(item: ArchitectureResult, chosen: JudgeCriterion = criterion) -> object:
                return item.judge_score(chosen)

            add(f"Judge {criterion.value}", scorer)
        add("P50 Latency (ms)", lambda item: item.p50_latency_ms)
        add("P95 Latency (ms)", lambda item: item.p95_latency_ms)
        add("LLM 호출 (합계)", lambda item: item.llm_call_count)
        add("1회 실행당 호출", lambda item: item.average_llm_calls)
        add("1회 실행당 토큰", lambda item: item.average_tokens_per_run)

        lines = ["| " + " | ".join(header) + " |"]
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines)


FAIRNESS_CONDITIONS: Final[dict[str, str]] = {
    "llm_model": "identical: one provider object is built once and shared",
    "temperature": "identical: fixed by build_openai_demo_chat_model",
    "user_input": "identical: the same EvaluationCase list, in the same order",
    "evaluation_dataset": "identical",
    "exercise_data": "identical synthetic catalog",
    "vector_db": "identical ExercisePoolSnapshot per case; PostgreSQL decides eligibility",
    "embedding": "not re-run per architecture; the pool is composed once per case",
    "tool_scope": (
        "A sees only the fields the output schema requires; B and C see the same "
        "full pool projection"
    ),
    "output_schema": (
        "identical up to proposal_references and repair_attempt, which only a "
        "multi-agent run can supply"
    ),
    "downstream_gate": "identical compiler, integrity validator and deterministic fallback",
    "prompt": "the baseline instruction is composed from the four shipped role prompts",
}


__all__ = [
    "FAIRNESS_CONDITIONS",
    "HEADLINE_CRITERIA",
    "REPORTED_CATEGORIES",
    "ArchitectureResult",
    "CategoryResult",
    "ComparisonReport",
]
