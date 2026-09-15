"""Paid B-vs-D pilot for the ADR-0025 candidate-review experiment.

The default is a zero-cost forecast. Provider calls require both
``--confirm-spend`` and ``OPENAI_API_KEY``. Each complete case costs at most
five graph calls: one Single-Agent+RAG baseline and four candidate-review calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from backend.tests.evaluation.architectures import ARCHITECTURE_SINGLE_AGENT_RAG
from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.dataset import EvaluationCase, load_dataset
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.runners.candidate_review import CandidateReviewRunner
from backend.tests.evaluation.runners.fake_chat import Script
from backend.tests.evaluation.runners.openai_provider import (
    ProviderUnavailableError,
    build_provider,
)
from backend.tests.evaluation.runners.single_agent import SingleAgentRunner

DEFAULT_OUTPUT = Path("results/candidate-review-pilot/summary.json")
CALLS_PER_CASE = 5


def _cases(
    dataset: str | None, case_ids: Sequence[str] | None, categories: Sequence[str] | None
) -> tuple[EvaluationCase, ...]:
    cases = (
        GRAPH_CASES
        if dataset is None
        else tuple(
            case
            for case in load_dataset(dataset).cases
            if case.expected_scenario_build_error is None
        )
    )
    if case_ids:
        requested = set(case_ids)
        cases = tuple(case for case in cases if case.case_id in requested)
        missing = requested - {case.case_id for case in cases}
        if missing:
            raise ValueError(f"unknown case IDs: {', '.join(sorted(missing))}")
    if categories:
        requested_categories = set(categories)
        cases = tuple(case for case in cases if case.category.value in requested_categories)
    return planning_cases(cases)


async def _execute(
    *, dataset: str | None, case_ids: Sequence[str] | None, categories: Sequence[str] | None
) -> dict[str, object]:
    provider = build_provider()
    cases = _cases(dataset, case_ids, categories)
    baseline = SingleAgentRunner(architecture_code=ARCHITECTURE_SINGLE_AGENT_RAG, provider=provider)
    candidate = CandidateReviewRunner(provider=provider)
    rows: list[dict[str, object]] = []
    provider_calls = 0
    for case in cases:
        baseline_run = await baseline.run(case, Script())
        experimental = await candidate.run(case)
        baseline_eval = evaluate_case(baseline_run)
        candidate_eval = evaluate_case(experimental.base_run)
        provider_calls += baseline_run.llm_call_count + experimental.base_run.llm_call_count
        critical = (*baseline_eval.critical_failures, *candidate_eval.critical_failures)
        if critical:
            codes = ",".join(item.check_code for item in critical)
            raise RuntimeError(f"critical evaluation failure for {case.case_id}: {codes}")
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category.value,
                "baseline": baseline_eval.to_json(),
                "candidate_review": candidate_eval.to_json(),
                "deliberation": {
                    "selection_changed": experimental.selection_changed,
                    "specialist_disagreement": experimental.specialist_disagreement,
                    "applied_adjustment_count": experimental.applied_adjustment_count,
                    "selected_candidate_code": (
                        experimental.outcome.selected_candidate_code
                        if experimental.outcome is not None
                        else None
                    ),
                },
            }
        )
        print(
            f"{case.case_id}: B plan={baseline_run.has_plan} "
            f"fallback={baseline_run.used_fallback}; "
            f"D plan={experimental.base_run.has_plan} "
            f"fallback={experimental.base_run.used_fallback} "
            f"changed={experimental.selection_changed}"
        )
    return {
        "experiment": "ADR-0025-candidate-review-pilot",
        "model_label": provider.label,
        "dataset": dataset or "smoke",
        "case_count": len(cases),
        "provider_calls": provider_calls,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dataset")
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--categories", nargs="+")
    parser.add_argument("--max-calls", type=int, default=25)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    cases = _cases(args.dataset, args.case_ids, args.categories)
    forecast = len(cases) * CALLS_PER_CASE
    print(f"{len(cases)} case(s), at most {forecast} provider calls")
    if forecast > args.max_calls:
        parser.error(f"forecast exceeds --max-calls={args.max_calls}")
    if args.dry_run or not args.confirm_spend:
        print("dry-run: no provider was built and no paid call was made")
        return 0
    try:
        report = asyncio.run(
            _execute(dataset=args.dataset, case_ids=args.case_ids, categories=args.categories)
        )
    except ProviderUnavailableError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
