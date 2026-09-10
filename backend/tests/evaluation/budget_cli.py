"""Forecast the provider work PHASE 3-5 (and 6-7) would do.

    uv run python -m backend.tests.evaluation.budget_cli
    uv run python -m backend.tests.evaluation.budget_cli --pricing-reference pricing.json

Costs nothing: it serializes the prompts that *would* be sent and counts them.
Run it before approving any paid phase.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.tests.evaluation.budget import (
    JUDGE_MAX_OUTPUT_TOKENS,
    BudgetForecast,
    PhaseForecast,
    load_pricing,
    measure_judge_volume,
    measure_prompt_volume,
    planning_cases,
)
from backend.tests.evaluation.harness import GRAPH_CASES

# How many times each phase replays the dataset through the graph. The variance
# pass exists because temperature 0 is not a determinism guarantee, and the
# spread is itself a result worth reporting.
GRAPH_PHASE_REPEATS: dict[str, int] = {
    "phase4_multi_agent_pilot": 1,
    "phase4_multi_agent_variance_3x": 3,
}


def build_forecast(pricing_path: Path | None) -> BudgetForecast:
    cases = planning_cases(GRAPH_CASES)
    roles = measure_prompt_volume(cases)
    phases = [
        PhaseForecast(phase=name, run_count=len(cases), roles=roles, repeats=repeats)
        for name, repeats in GRAPH_PHASE_REPEATS.items()
    ]
    # PHASE 5 scores the plans PHASE 4 already produced; it does not replay the
    # graph, and its request is one plan plus the rubric rather than the pool.
    judge = measure_judge_volume(cases)
    phases.append(
        PhaseForecast(
            phase="phase5_llm_judge",
            run_count=judge.call_count,
            roles=(judge,),
            repeats=1,
            output_tokens_per_call=JUDGE_MAX_OUTPUT_TOKENS,
        )
    )
    return BudgetForecast(
        phases=phases,
        pricing=load_pricing(pricing_path) if pricing_path else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pricing-reference", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="print the full JSON body")
    arguments = parser.parse_args()

    forecast = build_forecast(arguments.pricing_reference)
    body = forecast.to_json()
    if arguments.json:
        print(forecast.dumps())
        return 0

    measured = body["measured"]
    assert isinstance(measured, dict)
    print("Measured provider work (no call made):")
    print(f"  total LLM calls          {measured['total_llm_calls']}")
    print(f"  prompt tokens (headroom) {measured['total_prompt_tokens_with_headroom']:,}")
    print(f"  output tokens (ceiling)  {measured['total_output_tokens_with_headroom']:,}")
    print()
    for phase in measured["phases"]:  # type: ignore[index]
        print(
            f"  {phase['phase']:<34} runs={phase['run_count']:<3} "
            f"x{phase['repeats']}  calls={phase['llm_calls']:<4} "
            f"prompt_tok={phase['prompt_tokens']:,}"
        )
    print()
    cost = body["cost"]
    assert isinstance(cost, dict)
    if cost["available"]:
        print(f"Estimated cost ({cost['currency_code']}): {cost['total']}")
        print(f"  model  {cost['model_code']}")
        print(f"  source {cost['source_reference']}")
    else:
        print("Cost: NOT CALCULATED")
        print(f"  {cost['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
