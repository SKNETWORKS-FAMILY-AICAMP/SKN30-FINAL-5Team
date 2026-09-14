"""PHASE 6: run A, B and C over one dataset and report them side by side.

    # forecast only, no call, no cost
    uv run python -m backend.tests.evaluation.comparison_cli --dry-run

    # harness check, still no cost: every architecture against the scripted model
    uv run python -m backend.tests.evaluation.comparison_cli --offline

    # the real thing
    export OPENAI_API_KEY=...        # see docs/test/PAID_EVALUATION.md
    uv run python -m backend.tests.evaluation.comparison_cli --confirm-spend

One provider object is built once and shared by all three architectures, so the
model, temperature, timeout and token ceiling cannot differ between them by
accident.  The case list is built once, in order, for the same reason.

The judge runs blind (`judge_run(..., blind=True)`): the one payload field that
identifies the architecture is withheld, so a score reflects the plan rather than
a recognised pipeline.  That also makes these scores incomparable with the
PHASE 5 numbers, which were taken unblinded; the report records that.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.tests.evaluation.architectures import (
    ARCHITECTURE_MULTI_AGENT,
    ARCHITECTURE_SINGLE_AGENT_RAG,
    ARCHITECTURE_SINGLE_LLM,
    COMPARED_ARCHITECTURES,
    is_multi_agent,
)
from backend.tests.evaluation.budget import planning_cases
from backend.tests.evaluation.comparison import ArchitectureResult, ComparisonReport
from backend.tests.evaluation.dataset import EvaluationCase, load_dataset
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.evaluators.agent_metrics import build_report as build_agent_report
from backend.tests.evaluation.harness import GRAPH_CASES
from backend.tests.evaluation.judge.judge import JudgeModel, build_judge_payload, judge_run
from backend.tests.evaluation.runners.fake_chat import (
    Script,
    ScriptedChatModel,
    register_prompt_role,
)
from backend.tests.evaluation.runners.openai_provider import (
    ProviderContext,
    ProviderUnavailableError,
    build_provider,
)
from backend.tests.evaluation.runners.payloads import SingleAgentPayloadBuilder
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult, MultiAgentRunner
from backend.tests.evaluation.runners.single_agent import (
    SINGLE_AGENT_RAG_PROMPT_VERSION,
    SINGLE_LLM_PROMPT_VERSION,
    SingleAgentRunner,
)
from backend.tests.evaluation.scenario import build_scenario
from backend.tests.evaluation.tracing import (
    EXPERIMENT_BY_ARCHITECTURE,
    langsmith_configured,
    langsmith_run,
)

DEFAULT_OUTPUT_DIR = Path("results/comparison")

# How many provider calls one run of each architecture makes when nothing fails.
CALLS_PER_RUN: dict[str, int] = {
    ARCHITECTURE_SINGLE_LLM: 1,
    ARCHITECTURE_SINGLE_AGENT_RAG: 1,
    ARCHITECTURE_MULTI_AGENT: 4,
}


class CriticalFailureStop(RuntimeError):
    """Raised to abort a paid run the moment an unsafe result appears.

    `ROUND2_IMPROVEMENT_PLAN` section 5 pre-registers this: one unsafe plan,
    critical failure or privacy violation stops the whole run. Spending the rest
    of the budget after that produces numbers nobody should average, and the
    abort is what makes "we checked" different from "we looked afterwards".
    """


def dataset_cases(name: str | None) -> tuple[EvaluationCase, ...]:
    """The cases to run: the tuning smoke set by default, or a named dataset."""

    if name is None:
        return GRAPH_CASES
    loaded = load_dataset(name)
    return tuple(case for case in loaded.cases if case.expected_scenario_build_error is None)


def select_case_ids(
    cases: tuple[EvaluationCase, ...], case_ids: Sequence[str] | None
) -> tuple[EvaluationCase, ...]:
    """Select an explicit paid-run subset while preserving dataset order."""

    if not case_ids:
        return cases
    requested = set(case_ids)
    selected = tuple(case for case in cases if case.case_id in requested)
    missing = sorted(requested - {case.case_id for case in selected})
    if missing:
        raise ValueError(f"unknown case IDs: {', '.join(missing)}")
    return selected


_REPORT_NOTES: tuple[str, ...] = (
    "Judge scores are blind and therefore not comparable with the PHASE 5 numbers.",
    "The baselines get no repair round; the multi-agent path does. Every paid "
    "multi-agent run in PHASE 4 used zero repairs, so the asymmetry had no "
    "measured effect, but it favours C.",
    "A PlanSpec structurally requires three proposal references, so a baseline "
    "plan reaches the shipped compiler through a contract adapter that invents "
    "no advice. See runners/single_agent.py.",
)


def _register_baseline_prompts() -> None:
    """Let the offline stand-in recognise the baseline prompt versions."""

    from backend.app.integrations.llm_agents.models import LlmAgentRoleCode

    for version in (SINGLE_LLM_PROMPT_VERSION, SINGLE_AGENT_RAG_PROMPT_VERSION):
        register_prompt_role(version, LlmAgentRoleCode.COORDINATOR)


@dataclass
class _Budget:
    """A hard stop checked before every provider call."""

    max_calls: int
    used: int = 0

    def allows(self, cost: int) -> bool:
        return self.used + cost <= self.max_calls

    def spend(self, count: int) -> None:
        self.used += count


async def _run_one(
    architecture_code: str,
    case: EvaluationCase,
    *,
    provider: ProviderContext | None,
) -> CaseRunResult:
    if is_multi_agent(architecture_code):
        runner = MultiAgentRunner(
            provider=provider,
            node_timeout_seconds=provider.timeout_seconds if provider else 0.5,
        )
        return await runner.run(case, Script())

    scenario = build_scenario(case)
    chat_model = (
        None
        if provider is not None
        else ScriptedChatModel(
            script=Script(),
            payload_builder=SingleAgentPayloadBuilder(
                envelope=scenario.constraint_envelope, pool=scenario.exercise_pool
            ),
        )
    )
    single = SingleAgentRunner(
        architecture_code=architecture_code, provider=provider, chat_model=chat_model
    )
    return await single.run_scenario(scenario, Script())


async def _run_architecture(
    architecture_code: str,
    cases: Sequence[EvaluationCase],
    *,
    provider: ProviderContext | None,
    repeats: int,
    budget: _Budget,
    judge_model: JudgeModel | None,
    model_label: str,
) -> ArchitectureResult:
    result = ArchitectureResult(architecture_code=architecture_code, model_label=model_label)
    cost = CALLS_PER_RUN[architecture_code]

    with langsmith_run(
        EXPERIMENT_BY_ARCHITECTURE[architecture_code],
        metadata={"architecture_code": architecture_code, "model_code": model_label},
    ) as tracing:
        print(f"  {tracing.summary}")
        for repeat in range(repeats):
            for case in cases:
                if provider is not None and not budget.allows(cost):
                    print(f"  stopping {architecture_code}: --max-calls reached")
                    return _finish(result)
                run = await _run_one(architecture_code, case, provider=provider)
                if provider is not None:
                    budget.spend(run.llm_call_count)
                evaluation = evaluate_case(run)
                result.runs.append(run)
                result.evaluations.append(evaluation)
                if evaluation.critical_failures:
                    codes = ",".join(item.check_code for item in evaluation.critical_failures)
                    raise CriticalFailureStop(f"{architecture_code} {case.case_id}: {codes}")
                print(
                    f"  [{repeat + 1}/{repeats}] {architecture_code:<17} {case.case_id:<18} "
                    f"{run.status_code:<10} plan={'y' if run.has_plan else 'n'} "
                    f"fallback={'y' if run.used_fallback else 'n'} "
                    f"calls={run.llm_call_count} tokens={sum(run.token_usage)}"
                )
                if judge_model is None or repeat != 0:
                    continue
                if provider is not None and not budget.allows(1):
                    continue
                try:
                    # A judge that fails is a missing score, not a lost run.
                    judgement = judge_run(run, judge_model, evaluation=evaluation, blind=True)
                except Exception as error:  # noqa: BLE001 -- reported, not raised
                    if provider is not None:
                        budget.spend(1)
                    print(f"      judge failed: {type(error).__name__}: {error}")
                    continue
                if judgement.output is not None and provider is not None:
                    budget.spend(1)
                result.judgements.append(judgement)
    return _finish(result)


def _finish(result: ArchitectureResult) -> ArchitectureResult:
    result.agent_metrics = build_agent_report(
        result.runs,
        architecture_code=result.architecture_code,
        provider_label=result.model_label,
    )
    return result


async def _execute(
    *,
    architectures: Sequence[str],
    repeats: int,
    max_calls: int,
    offline: bool,
    judge_enabled: bool,
    dataset: str | None = None,
    case_ids: Sequence[str] | None = None,
) -> ComparisonReport:
    _register_baseline_prompts()
    provider = None if offline else build_provider()
    model_label = provider.label if provider is not None else "eval-scripted-model-v1"
    cases = planning_cases(select_case_ids(dataset_cases(dataset), case_ids))
    budget = _Budget(max_calls=max_calls)

    judge_model: JudgeModel | None = None
    if judge_enabled:
        if provider is not None:
            from backend.tests.evaluation.judge.openai_judge import build_openai_judge

            judge_model = build_openai_judge(provider)
        else:
            from backend.tests.evaluation.judge.mock_judge import StructuralMockJudge

            # Offline scores move the pipeline; they are not an opinion.
            judge_model = StructuralMockJudge()

    report = ComparisonReport(
        dataset_name=dataset or "smoke",
        repeats=repeats,
        judge_blind=True,
        notes=_REPORT_NOTES,
    )
    for architecture_code in architectures:
        print(f"\n{architecture_code}")
        report.results.append(
            await _run_architecture(
                architecture_code,
                cases,
                provider=provider,
                repeats=repeats,
                budget=budget,
                judge_model=judge_model,
                model_label=model_label,
            )
        )
    if provider is not None:
        print(f"\ncalls made: {budget.used}")
    return report


def _write(report: ComparisonReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(report.dumps(), encoding="utf-8")
    (output_dir / "comparison.md").write_text(report.markdown() + "\n", encoding="utf-8")
    for result in report.results:
        name = result.architecture_code.lower()
        if result.agent_metrics is not None:
            (output_dir / f"agent_metrics_{name}.json").write_text(
                result.agent_metrics.dumps(), encoding="utf-8"
            )
        (output_dir / f"cases_{name}.json").write_text(
            json.dumps(
                [item.to_json() for item in result.evaluations],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (output_dir / f"judge_{name}.json").write_text(
            json.dumps(
                {
                    "blind": True,
                    "scores": [item.to_json() for item in result.judgements],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    # The blind payloads are what PHASE 7 compares. Writing them here means a
    # pairwise run does not have to pay for the graph a second time: the first
    # version of this did, and re-running 84 provider calls to obtain plans that
    # already existed is not a cost worth repeating.
    _write_pairwise_payloads(report, output_dir)


def _write_pairwise_payloads(report: ComparisonReport, output_dir: Path) -> None:
    """Store one blind judge payload per case per architecture, for PHASE 7.

    Only the first repeat is kept. A pairwise comparison needs one plan per
    architecture per case, and picking among repeats after the fact would be a
    choice the report could not justify.
    """

    cases: dict[str, dict[str, object]] = {}
    for result in report.results:
        seen: set[str] = set()
        for run in result.runs:
            case_id = run.case.case_id
            if case_id in seen:
                continue
            seen.add(case_id)
            entry = cases.setdefault(
                case_id, {"category": run.case.category.value, "architectures": {}}
            )
            architectures = entry["architectures"]
            assert isinstance(architectures, dict)
            architectures[result.architecture_code] = (
                build_judge_payload(run, blind=True) if run.compiled_plan is not None else None
            )
    (output_dir / "pairwise_payloads.json").write_text(
        json.dumps(
            {
                "model_label": report.results[0].model_label if report.results else "unknown",
                "blind": True,
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _forecast(architectures: Sequence[str], case_count: int, repeats: int) -> str:
    graph_calls = sum(CALLS_PER_RUN[code] * case_count * repeats for code in architectures)
    judge_calls = len(architectures) * case_count
    return (
        f"{case_count} cases x {repeats} repeat(s) over {len(architectures)} "
        f"architectures = {graph_calls} graph LLM calls, plus up to "
        f"{judge_calls} judge calls"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-spend", action="store_true", help="actually call the provider")
    parser.add_argument("--dry-run", action="store_true", help="forecast and exit (default)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="run every architecture against the scripted model; costs nothing",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=200)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument(
        "--architectures",
        nargs="+",
        choices=list(COMPARED_ARCHITECTURES),
        default=list(COMPARED_ARCHITECTURES),
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="dataset base name; default is the tuning smoke set",
    )
    parser.add_argument(
        "--case-ids",
        nargs="+",
        default=None,
        help="run only these case IDs from the selected dataset",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    try:
        cases = planning_cases(
            select_case_ids(dataset_cases(arguments.dataset), arguments.case_ids)
        )
    except ValueError as error:
        parser.error(str(error))
    print(_forecast(arguments.architectures, len(cases), arguments.repeats))
    print(f"hard stop at --max-calls {arguments.max_calls}")
    print(
        "LangSmith: "
        + ("configured" if langsmith_configured() else "not configured (run proceeds without it)")
    )

    if not arguments.offline and (not arguments.confirm_spend or arguments.dry_run):
        print("\nDry run. No provider call was made. Pass --confirm-spend to run for real.")
        return 0

    try:
        report = asyncio.run(
            _execute(
                architectures=arguments.architectures,
                repeats=arguments.repeats,
                max_calls=arguments.max_calls,
                offline=arguments.offline,
                judge_enabled=not arguments.no_judge,
                dataset=arguments.dataset,
                case_ids=arguments.case_ids,
            )
        )
    except ProviderUnavailableError as error:
        print(f"\nProvider unavailable: {error}")
        return 2
    except CriticalFailureStop as error:
        # Pre-registered in ROUND2_IMPROVEMENT_PLAN section 5: one unsafe result
        # ends the run rather than being averaged into it.
        print(f"\nSTOPPED: a critical failure appeared and the run was aborted.\n  {error}")
        return 3

    _write(report, arguments.output_dir)
    print()
    print(report.markdown())
    print(f"\nartifacts: {arguments.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
