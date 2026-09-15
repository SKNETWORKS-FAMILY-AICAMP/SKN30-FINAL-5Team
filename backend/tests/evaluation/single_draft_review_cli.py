"""B-vs-E shared-draft pilot. Defaults to a zero-cost forecast."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.dataset import EvaluationCase, load_dataset
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.runners.fake_chat import Script
from backend.tests.evaluation.runners.openai_provider import (
    ProviderUnavailableError,
    build_provider,
)
from backend.tests.evaluation.runners.single_agent import SingleAgentRunner
from backend.tests.evaluation.runners.single_draft_review import SingleDraftReviewRunner
from backend.tests.evaluation.scenario import build_scenario

DEFAULT_OUTPUT = Path("results/single-draft-review-pilot/summary.json")
# One shared Training call plus two critics and one Coordinator, each allowing one retry.
MAX_PROVIDER_ATTEMPTS_PER_CASE = 8


def _cases(dataset: str | None, case_ids: Sequence[str] | None) -> tuple[EvaluationCase, ...]:
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
    return planning_cases(cases)


async def _execute(*, dataset: str | None, case_ids: Sequence[str] | None) -> dict[str, object]:
    provider = build_provider()
    cases = _cases(dataset, case_ids)
    baseline = SingleAgentRunner(provider=provider)
    reviewer = SingleDraftReviewRunner(provider=provider)
    rows: list[dict[str, object]] = []
    attempts = 0
    for case in cases:
        scenario = build_scenario(case)
        original = await baseline.run_scenario(scenario, Script())
        reviewed = await reviewer.run_scenario(scenario, original_run=original)
        baseline_evaluation = evaluate_case(original)
        reviewed_evaluation = evaluate_case(reviewed.base_run)
        critical = (
            *baseline_evaluation.critical_failures,
            *reviewed_evaluation.critical_failures,
        )
        if critical:
            codes = ",".join(item.check_code for item in critical)
            raise RuntimeError(f"critical evaluation failure for {case.case_id}: {codes}")
        attempts += sum(
            audit.attempt_count for audit in reviewed.base_run.graph_result.invocation_audits
        )
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category.value,
                "baseline": baseline_evaluation.to_json(),
                "reviewed": reviewed_evaluation.to_json(),
                "shared_draft": True,
                "review": {
                    "completed": reviewed.review_completed,
                    "changed": reviewed.changed,
                    "specialist_disagreement": reviewed.specialist_disagreement,
                    "applied_adjustment_count": reviewed.applied_adjustment_count,
                    "original_preserved": reviewed.original_preserved,
                    "preservation_codes": list(reviewed.preservation_codes),
                },
                "invocations": [
                    asdict(audit) for audit in reviewed.base_run.graph_result.invocation_audits
                ],
            }
        )
        print(
            f"{case.case_id}: B plan={original.has_plan} fallback={original.used_fallback}; "
            f"E changed={reviewed.changed} preserved={reviewed.original_preserved} "
            f"calls={reviewed.base_run.llm_call_count}"
        )
    return {
        "experiment": "ADR-0026-single-draft-parallel-critics",
        "model_label": provider.label,
        "dataset": dataset or "smoke",
        "case_count": len(cases),
        "provider_attempts": attempts,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dataset")
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        cases = _cases(args.dataset, args.case_ids)
    except ValueError as error:
        parser.error(str(error))
    forecast = len(cases) * MAX_PROVIDER_ATTEMPTS_PER_CASE
    print(f"{len(cases)} case(s), at most {forecast} provider attempts")
    if forecast > args.max_calls:
        parser.error(f"forecast exceeds --max-calls={args.max_calls}")
    if args.dry_run or not args.confirm_spend:
        print("dry-run: no provider was built and no paid call was made")
        return 0
    try:
        report = asyncio.run(_execute(dataset=args.dataset, case_ids=args.case_ids))
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
