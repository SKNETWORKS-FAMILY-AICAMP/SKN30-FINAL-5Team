"""PHASE 7: judge the architectures head to head, blind, in both orders.

    # no cost: scripted plans, deterministic judge
    uv run python -m backend.tests.evaluation.pairwise_cli --offline

    # the real thing
    export OPENAI_API_KEY=...        # see docs/test/PAID_EVALUATION.md
    uv run python -m backend.tests.evaluation.pairwise_cli --confirm-spend

The run is split in two so the expensive half is paid for once:

* **collect** runs each architecture over the dataset and writes the blind judge
  payload for every plan to `results/pairwise/payloads.json`.
* **judge** reads that file and does nothing but compare.

Re-judging -- a different model, a changed rubric, more orders -- then costs only
the judge calls. `--judge-only` skips collection when the payloads already exist,
which is the normal way to run this a second time.

Every pair is judged twice, with the plans swapped, because a pairwise win rate
is meaningless without knowing whether the judge was reading content or position.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from itertools import combinations
from pathlib import Path
from typing import Any

from backend.tests.evaluation.architectures import ARCHITECTURE_LABELS, COMPARED_ARCHITECTURES
from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.judge.judge import build_judge_payload
from backend.tests.evaluation.judge.pairwise import (
    PairResult,
    PairwiseJudgeModel,
    compare_pair,
)
from backend.tests.evaluation.runners.openai_provider import (
    ProviderContext,
    ProviderUnavailableError,
    build_provider,
)
from backend.tests.evaluation.tracing import langsmith_configured

DEFAULT_OUTPUT_DIR = Path("results/pairwise")
PAYLOAD_FILE = "payloads.json"

# Judge calls per case per pair: the same two plans, presented both ways round.
ORDERS_PER_PAIR = 2


async def _collect(*, provider: ProviderContext | None, output_dir: Path) -> dict[str, Any]:
    """Run every architecture once and store the blind payload for each plan."""

    from backend.tests.evaluation.comparison_cli import _register_baseline_prompts, _run_one

    _register_baseline_prompts()
    cases = planning_cases(GRAPH_CASES)
    collected: dict[str, Any] = {
        "model_label": provider.label if provider else "eval-scripted-model-v1",
        "blind": True,
        "cases": {},
    }
    for case in cases:
        entry: dict[str, Any] = {"category": case.category.value, "architectures": {}}
        for architecture_code in COMPARED_ARCHITECTURES:
            run = await _run_one(architecture_code, case, provider=provider)
            payload = (
                build_judge_payload(run, blind=True) if run.compiled_plan is not None else None
            )
            entry["architectures"][architecture_code] = payload
            print(
                f"  {case.case_id:<18} {architecture_code:<17} "
                f"{'plan' if payload else 'NO PLAN':<8} calls={run.llm_call_count}"
            )
        collected["cases"][case.case_id] = entry

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / PAYLOAD_FILE).write_text(
        json.dumps(collected, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return collected


def _judge(
    collected: dict[str, Any], model: PairwiseJudgeModel, *, max_calls: int
) -> tuple[list[PairResult], int]:
    results: list[PairResult] = []
    calls = 0
    for left, right in combinations(COMPARED_ARCHITECTURES, 2):
        result = PairResult(left=left, right=right)
        for case_id, entry in collected["cases"].items():
            payloads = entry["architectures"]
            missing = [name for name in (left, right) if payloads.get(name) is None]
            if missing:
                # A pair needs two plans. Recording why keeps a missing plan from
                # quietly reading as a tie.
                result.unjudgeable.append({"case_id": case_id, "no_plan_from": ",".join(missing)})
                continue
            if calls + ORDERS_PER_PAIR > max_calls:
                print(f"  stopping: --max-calls {max_calls} reached")
                results.append(result)
                return results, calls
            try:
                outcome = compare_pair(
                    model,
                    case_id=case_id,
                    category=entry["category"],
                    left=left,
                    right=right,
                    payloads={name: payloads[name] for name in (left, right)},
                )
            except Exception as error:  # noqa: BLE001 -- a lost verdict, not a lost run
                calls += ORDERS_PER_PAIR
                print(
                    f"  {case_id:<18} {left} vs {right}: judge failed "
                    f"({type(error).__name__}: {error})"
                )
                continue
            calls += ORDERS_PER_PAIR
            result.outcomes.append(outcome)
            verdict = outcome.consensus_winner or ("TIE" if outcome.agreed else "DISAGREED")
            print(f"  {case_id:<18} {left} vs {right}: {verdict}")
        results.append(result)
    return results, calls


def _print_summary(results: list[PairResult]) -> None:
    for result in results:
        tally = result.tally()
        left_label = ARCHITECTURE_LABELS.get(result.left, result.left)
        right_label = ARCHITECTURE_LABELS.get(result.right, result.right)
        print(f"\n{left_label}  vs  {right_label}")
        print(f"  판정 {result.judged}건 (계획 부재로 제외 {len(result.unjudgeable)}건)")
        print(
            f"  {left_label} 승 {tally[result.left]} / 무 {tally['TIE']} / "
            f"{right_label} 승 {tally[result.right]}  · 두 순서 불일치 {tally['DISAGREED']}"
        )
        print(f"  순서 일치율 {result.agreement_rate}  · Position Bias {result.position_bias_rate}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offline", action="store_true", help="scripted plans, mock judge; free")
    parser.add_argument(
        "--judge-only", action="store_true", help="reuse the stored payloads; judge calls only"
    )
    parser.add_argument("--max-calls", type=int, default=120)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    cases = planning_cases(GRAPH_CASES)
    pairs = len(list(combinations(COMPARED_ARCHITECTURES, 2)))
    collect_calls = 0 if arguments.judge_only else len(cases) * 6
    print(
        f"{len(cases)} cases x {pairs} pairs x {ORDERS_PER_PAIR} orders = "
        f"up to {len(cases) * pairs * ORDERS_PER_PAIR} judge calls"
        + (f", plus {collect_calls} graph calls to collect plans" if collect_calls else "")
    )
    print(f"hard stop at --max-calls {arguments.max_calls} (judge calls)")
    print("LangSmith: " + ("configured" if langsmith_configured() else "not configured"))

    if not arguments.offline and (not arguments.confirm_spend or arguments.dry_run):
        print("\nDry run. No provider call was made. Pass --confirm-spend to run for real.")
        return 0

    provider = None
    if not arguments.offline:
        try:
            provider = build_provider()
        except ProviderUnavailableError as error:
            print(f"\nProvider unavailable: {error}")
            return 2

    payload_path = arguments.output_dir / PAYLOAD_FILE
    if arguments.judge_only:
        if not payload_path.exists():
            print(f"\nNo stored payloads at {payload_path}; run without --judge-only first.")
            return 2
        collected = json.loads(payload_path.read_text(encoding="utf-8"))
        print(f"\nreusing payloads from {payload_path}")
    else:
        print("\ncollecting plans")
        collected = asyncio.run(_collect(provider=provider, output_dir=arguments.output_dir))

    if arguments.offline:
        from backend.tests.evaluation.judge.mock_pairwise import LongerPlanPairwiseJudge

        model: PairwiseJudgeModel = LongerPlanPairwiseJudge()
    else:
        from backend.tests.evaluation.judge.openai_pairwise import build_openai_pairwise_judge

        model = build_openai_pairwise_judge(provider)

    print("\njudging")
    results, calls = _judge(collected, model, max_calls=arguments.max_calls)
    _print_summary(results)

    redacted = sum(item.redacted_code_count for result in results for item in result.outcomes)
    report = {
        "phase": "PHASE 7 pairwise",
        "model_label": model.model_label,
        "plans_from": collected["model_label"],
        "judge_calls": calls,
        "orders_per_pair": ORDERS_PER_PAIR,
        "blinding": {
            "advisory_codes_withheld": True,
            "revealing_decision_codes_redacted": redacted,
        },
        "pairs": [item.to_json() for item in results],
    }
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "pairwise.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"\njudge calls: {calls}")
    print(f"artifacts:   {arguments.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
