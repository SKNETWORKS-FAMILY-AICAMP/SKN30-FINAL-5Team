"""Run PHASE 3-5 against the real provider, with LangSmith tracing.

    # forecast only, no call, no cost
    uv run python -m backend.tests.evaluation.paid_run_cli --dry-run

    # the real thing
    export OPENAI_API_KEY=...        # see docs/test/PAID_EVALUATION.md
    export LANGSMITH_API_KEY=...     # optional; without it the run still works
    uv run python -m backend.tests.evaluation.paid_run_cli --confirm-spend

Nothing here calls a provider without `--confirm-spend`.  The default is a dry
run that prints the measured call and token volume and exits, because the one
mistake this script must not make is spending money nobody approved.

`--max-calls` is a hard stop, checked before each run, so a misconfiguration
cannot walk through the whole dataset at full price.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.evaluators.agent_metrics import build_report as build_agent_report
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.judge.judge import JudgeResult, judge_run
from backend.tests.evaluation.runners.fake_chat import Script
from backend.tests.evaluation.runners.openai_provider import (
    ProviderUnavailableError,
    build_provider,
)
from backend.tests.evaluation.runners.run_multi_agent import (
    ARCHITECTURE_CODE,
    CaseRunResult,
    MultiAgentRunner,
)
from backend.tests.evaluation.tracing import (
    EXPERIMENT_MULTI_AGENT,
    langsmith_configured,
    langsmith_run,
)

DEFAULT_OUTPUT_DIR = Path("results/paid")


@dataclass
class PaidRunOutcome:
    runs: list[CaseRunResult]
    judgements: list[JudgeResult]
    calls_made: int
    tracing_summary: str


def _forecast_line(case_count: int, repeats: int) -> str:
    calls = case_count * 4 * repeats
    return (
        f"{case_count} cases x {repeats} repeat(s) = {calls} graph LLM calls, "
        f"plus up to {case_count * repeats} judge calls"
    )


async def _execute(
    *,
    repeats: int,
    max_calls: int,
    judge_enabled: bool,
) -> PaidRunOutcome:
    provider = build_provider()
    # The graph deadline is the deployment's own bound, not a number chosen
    # here: `V3DemoRuntime` passes `settings.llm_agents_timeout_seconds` through
    # as `node_timeout_seconds`, so taking it from the provider keeps the run
    # matched to what staging actually enforces.
    runner = MultiAgentRunner(
        provider=provider,
        node_timeout_seconds=provider.timeout_seconds,
    )
    cases = planning_cases(GRAPH_CASES)

    runs: list[CaseRunResult] = []
    judgements: list[JudgeResult] = []
    calls = 0

    judge_model = None
    if judge_enabled:
        from backend.tests.evaluation.judge.openai_judge import build_openai_judge

        judge_model = build_openai_judge(provider)

    with langsmith_run(
        EXPERIMENT_MULTI_AGENT,
        metadata={"architecture_code": ARCHITECTURE_CODE, "model_code": provider.model_code},
    ) as tracing:
        print(tracing.summary)
        for repeat in range(repeats):
            for case in cases:
                if calls + 4 > max_calls:
                    print(f"stopping: --max-calls {max_calls} reached")
                    return PaidRunOutcome(runs, judgements, calls, tracing.summary)
                run = await runner.run(case, Script())
                calls += run.llm_call_count
                runs.append(run)
                print(
                    f"  [{repeat + 1}/{repeats}] {case.case_id:<18} "
                    f"{run.status_code:<10} calls={run.llm_call_count} "
                    f"tokens={sum(run.token_usage)}"
                )
                if judge_model is not None and repeat == 0:
                    if calls + 1 > max_calls:
                        continue
                    # A judge that fails is a missing score, not a lost run. The
                    # graph results are the expensive part and must survive it.
                    try:
                        result = judge_run(run, judge_model)
                    except Exception as error:  # noqa: BLE001 -- reported, not raised
                        calls += 1
                        print(f"      judge failed: {type(error).__name__}: {error}")
                        continue
                    if result.output is not None:
                        calls += 1
                    judgements.append(result)
        return PaidRunOutcome(runs, judgements, calls, tracing.summary)


def _write_results(outcome: PaidRunOutcome, output_dir: Path, model_label: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    agent_report = build_agent_report(
        outcome.runs, architecture_code=ARCHITECTURE_CODE, provider_label=model_label
    )
    (output_dir / "agent_metrics.json").write_text(agent_report.dumps(), encoding="utf-8")

    evaluations = [evaluate_case(run) for run in outcome.runs]
    (output_dir / "evaluation_summary.json").write_text(
        json.dumps(
            {
                "architecture_code": ARCHITECTURE_CODE,
                "model_label": model_label,
                "run_count": len(outcome.runs),
                "llm_calls_made": outcome.calls_made,
                "tracing": outcome.tracing_summary,
                "passed_runs": sum(1 for item in evaluations if item.passed),
                "critical_failures": sum(len(item.critical_failures) for item in evaluations),
                "cases": [item.to_json() for item in evaluations],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    latency = sorted(run.wall_clock_ms for run in outcome.runs)
    if latency:

        def percentile(fraction: float) -> int:
            rank = max(1, round(fraction * len(latency)))
            return latency[rank - 1]

        (output_dir / "latency_metrics.json").write_text(
            json.dumps(
                {
                    "model_label": model_label,
                    "sample_count": len(latency),
                    "p50_ms": percentile(0.50),
                    "p95_ms": percentile(0.95),
                    "min_ms": latency[0],
                    "max_ms": latency[-1],
                    "note": (
                        "Wall clock for the whole graph run, measured against the "
                        "real provider. Includes the three parallel specialist "
                        "calls and the coordinator."
                    ),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    if outcome.judgements:
        (output_dir / "judge_scores.json").write_text(
            json.dumps(
                {
                    "case_count": len(outcome.judgements),
                    "scores": [item.to_json() for item in outcome.judgements],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-spend", action="store_true", help="actually call the provider")
    parser.add_argument("--dry-run", action="store_true", help="forecast and exit (default)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    cases = planning_cases(GRAPH_CASES)
    print(_forecast_line(len(cases), arguments.repeats))
    print(f"hard stop at --max-calls {arguments.max_calls}")
    print(
        "LangSmith: "
        + ("configured" if langsmith_configured() else "not configured (run proceeds without it)")
    )

    if not arguments.confirm_spend or arguments.dry_run:
        print("\nDry run. No provider call was made. Pass --confirm-spend to run for real.")
        return 0

    try:
        outcome = asyncio.run(
            _execute(
                repeats=arguments.repeats,
                max_calls=arguments.max_calls,
                judge_enabled=not arguments.no_judge,
            )
        )
    except ProviderUnavailableError as error:
        print(f"\nProvider unavailable: {error}")
        return 2

    provider = build_provider()
    _write_results(outcome, arguments.output_dir, provider.label)
    print(f"\ncalls made: {outcome.calls_made}")
    print(f"artifacts:  {arguments.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
