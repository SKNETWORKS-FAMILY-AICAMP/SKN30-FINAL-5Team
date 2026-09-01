"""Run a staging-only single-agent ablation against the V3 multi-agent graph."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Literal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models.catalog import CatalogVersion
from backend.app.db.repositories.vector_index import IndexableExerciseRecord, VectorIndexRepository
from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    RetrievalFailureCode,
    RetrievalMetadata,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec, compile_plan
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    PlanActionCode,
    RecoveryCeiling,
    V3ProposalStatusCode,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationStatusCode,
    validate_plan_integrity,
)
from backend.app.integrations.langgraph.fallback import DeterministicGraphFallbackProvider
from backend.app.integrations.langgraph.shadow_runtime import (
    V3ShadowRuntime,
    V3ShadowRuntimeVersions,
    build_v3_shadow_runtime,
)
from backend.app.integrations.llm_agents.specialists import TrainingAgentAdapter
from backend.app.modules.decisions.v3_shadow import V3ShadowCase, V3ShadowExecutionRequest
from backend.scripts.run_v3_staging_shadow import staging_gate_failure

HARNESS_VERSION = "single-multi-agent-comparison-v1"
SCENARIO_SPECS = (
    ("HEALTHY_GENERAL_30", "GENERAL_FITNESS", 30, False),
    ("LIMITED_TIME_GENERAL_20", "GENERAL_FITNESS", 20, False),
    ("FATIGUE_GENERAL_30", "GENERAL_FITNESS", 30, True),
    ("HEALTHY_MUSCLE_30", "MUSCLE_GAIN", 30, False),
)


@dataclass(frozen=True, slots=True)
class ComparisonScenario:
    code: str
    envelope: ConstraintEnvelope
    pool: ExercisePoolSnapshot


@dataclass(frozen=True, slots=True)
class ArchitectureResult:
    scenario_code: str
    architecture_code: Literal["SINGLE_TRAINING", "MULTI_V3"]
    completed: bool
    integrity_passed: bool
    terminal_status_code: str
    failure_code: str | None
    violation_codes: tuple[str, ...]
    fallback_used: bool
    provider_call_count: int
    input_token_count: int | None
    output_token_count: int | None
    latency_ms: int
    estimated_duration_seconds: int | None
    duration_delta_seconds: int | None
    exercise_count: int
    phase_codes: tuple[str, ...]


def _pool_record(item: IndexableExerciseRecord) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=item.exercise_id,
        catalog_version=item.catalog_version_code,
        content_version=item.instruction_content_version,
        stable_code=item.stable_code or f"exercise-{item.exercise_id}",
        training_type_code=item.training_type_code,
        body_focus_code=item.body_focus_code,
        movement_pattern_codes=(item.primary_movement_pattern_code,),
        difficulty_code=item.difficulty_code,
        timing_mode_code=item.timing_mode_code,
        default_seconds_per_rep=item.default_seconds_per_rep,
        default_work_seconds=item.default_work_seconds,
        default_rest_seconds=item.default_rest_seconds,
        default_transition_seconds=item.default_transition_seconds,
        recovery_eligible=item.recovery_eligible,
        goal_codes=tuple(sorted(item.goal_codes)),
        phase_codes=tuple(sorted(item.phase_codes)),
        role_eligibility_code=item.role_eligibility_code,
        equipment_codes=tuple(sorted(item.equipment_codes)),
        location_codes=tuple(sorted(item.location_codes)),
        prescription_reference_codes=(f"prescription/{item.stable_code or item.exercise_id}",),
        source_reference_codes=(f"catalog/{item.catalog_version_code}",),
        review_reference_codes=("DOMAIN_APPROVED",),
    )


def _has_phase(item: ExercisePoolExerciseRecord, *, phase: str) -> bool:
    return phase in item.phase_codes


def _select_pool(
    records: tuple[IndexableExerciseRecord, ...], *, goal_code: str, limit: int = 24
) -> tuple[ExercisePoolExerciseRecord, ...]:
    eligible = tuple(
        _pool_record(item)
        for item in records
        if goal_code in item.goal_codes
        and "HOME" in item.location_codes
        and "BEGINNER" in item.prescription_experience_level_codes
    )
    ordered = tuple(sorted(eligible, key=lambda item: (item.stable_code, str(item.exercise_id))))
    selected: list[ExercisePoolExerciseRecord] = []

    def take(predicate: Callable[[ExercisePoolExerciseRecord], bool], count: int) -> None:
        matcher = predicate
        for item in ordered:
            if len([value for value in selected if matcher(value)]) >= count:
                return
            if item not in selected and matcher(item):
                selected.append(item)

    for phase in ("WARMUP", "MAIN", "COOLDOWN"):
        take(partial(_has_phase, phase=phase), 4)
    take(lambda item: item.role_eligibility_code == "CORE", 4)
    for item in ordered:
        if item not in selected:
            selected.append(item)
        if len(selected) >= limit:
            break
    result = tuple(sorted(selected[:limit], key=lambda item: str(item.exercise_id)))
    if len(result) < 12 or any(
        sum(phase in item.phase_codes for item in result) < 2
        for phase in ("WARMUP", "MAIN", "COOLDOWN")
    ):
        raise ValueError(f"approved pool coverage is insufficient for {goal_code}")
    return result


def build_scenarios(
    records: tuple[IndexableExerciseRecord, ...], *, catalog_version: str
) -> tuple[ComparisonScenario, ...]:
    scenarios: list[ComparisonScenario] = []
    for code, goal, minutes, fatigued in SCENARIO_SPECS:
        ceiling = RecoveryCeiling(
            policy_version="agent-comparison-recovery-v1",
            allowed_intensity_codes=(("LOW",) if fatigued else ("LOW", "MODERATE")),
            allowed_load_codes=(),
            maximum_sets_per_exercise=2 if fatigued else 4,
            maximum_repetitions_per_set=10 if fatigued else 15,
            maximum_work_seconds_per_set=40 if fatigued else 60,
            minimum_rest_seconds_between_sets=40 if fatigued else 20,
        )
        envelope = ConstraintEnvelope.create(
            requested_duration_minutes=minutes,
            primary_goal_code=goal,
            allowed_location_codes=("HOME",),
            allowed_equipment_codes=(),
            excluded_exercise_ids=(),
            mandatory_exercise_ids=(),
            recovery_ceiling=ceiling,
            plan_generation_allowed=True,
            policy_version="agent-comparison-policy-v1",
            catalog_version=catalog_version,
            safety_rule_version="agent-comparison-safety-v1",
        )
        exercises = _select_pool(records, goal_code=goal)
        metadata = RetrievalMetadata(
            collection_name=None,
            vector_index_version=None,
            embedding_model_version=None,
            query_hash=hashlib.sha256(code.encode()).hexdigest(),
            retrieval_status_code=RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE,
            retrieval_failure_codes=(RetrievalFailureCode.VECTOR_INDEX_UNAVAILABLE,),
            deterministic_fallback_version="agent-comparison-pool-v1",
            deterministic_pool_fallback_used=True,
        )
        pool = ExercisePoolSnapshot.create(
            catalog_version=catalog_version,
            constraint_envelope_hash=envelope.envelope_hash,
            exercises=exercises,
            mandatory_exercise_ids=(),
            vector_ranked_exercise_ids=(),
            retrieval_metadata=metadata,
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        scenarios.append(ComparisonScenario(code=code, envelope=envelope, pool=pool))
    return tuple(scenarios)


def _failure_result(
    scenario: ComparisonScenario,
    architecture: Literal["SINGLE_TRAINING", "MULTI_V3"],
    *,
    failure_code: str,
    calls: int,
    latency_ms: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    fallback_used: bool = False,
) -> ArchitectureResult:
    return ArchitectureResult(
        scenario.code,
        architecture,
        False,
        False,
        "FAILED",
        failure_code,
        (),
        fallback_used,
        calls,
        input_tokens,
        output_tokens,
        latency_ms,
        None,
        None,
        0,
        (),
    )


async def run_single(
    scenario: ComparisonScenario, *, runtime: V3ShadowRuntime
) -> ArchitectureResult:
    started = time.monotonic_ns()
    outcome = await TrainingAgentAdapter(invoker=runtime.invoker).apropose(
        constraint_envelope=scenario.envelope,
        exercise_pool=scenario.pool,
    )
    telemetry = outcome.telemetry
    calls = (
        telemetry.attempt_count
        if telemetry
        else (outcome.failure.attempt_count if outcome.failure else 0)
    )
    latency = max(0, (time.monotonic_ns() - started) // 1_000_000)
    if outcome.output is None:
        return _failure_result(
            scenario,
            "SINGLE_TRAINING",
            failure_code=outcome.failure.code.value if outcome.failure else "UNKNOWN_FAILURE",
            calls=calls,
            latency_ms=latency,
            input_tokens=telemetry.input_token_count if telemetry else None,
            output_tokens=telemetry.output_token_count if telemetry else None,
        )
    proposal = outcome.output
    if proposal.proposal_status_code is not V3ProposalStatusCode.READY:
        return _failure_result(
            scenario,
            "SINGLE_TRAINING",
            failure_code=proposal.proposal_status_code.value,
            calls=calls,
            latency_ms=latency,
            input_tokens=telemetry.input_token_count if telemetry else None,
            output_tokens=telemetry.output_token_count if telemetry else None,
        )
    try:
        source = DeterministicFallbackPlanSpec.create(
            envelope_hash=scenario.envelope.envelope_hash,
            pool_hash=scenario.pool.pool_hash,
            action_code=PlanActionCode.DOWNSHIFT
            if "FATIGUE" in scenario.code
            else PlanActionCode.KEEP,
            requested_duration_minutes=scenario.envelope.requested_duration_minutes,
            estimated_duration_seconds=scenario.envelope.requested_duration_minutes * 60,
            exercise_prescriptions=proposal.exercise_prescriptions,
            reason_codes=("SINGLE_AGENT_ABLATION",),
            fallback_version="single-agent-ablation-v1",
        )
        compiled = compile_plan(
            source,
            envelope=scenario.envelope,
            pool=scenario.pool,
            compiler_version=runtime.versions.compiler_version,
        )
        validation = validate_plan_integrity(
            compiled,
            envelope=scenario.envelope,
            pool=scenario.pool,
            repair_attempt=0,
            validator_version=runtime.versions.validator_version,
            context=IntegrityValidationContext(),
        )
    except (ValueError, KeyError):
        return _failure_result(
            scenario,
            "SINGLE_TRAINING",
            failure_code="COMPILATION_FAILED",
            calls=calls,
            latency_ms=latency,
            input_tokens=telemetry.input_token_count if telemetry else None,
            output_tokens=telemetry.output_token_count if telemetry else None,
        )
    prescriptions = tuple(item.prescription for item in compiled.exercises)
    delta = abs(
        compiled.estimated_duration_seconds - scenario.envelope.requested_duration_minutes * 60
    )
    return ArchitectureResult(
        scenario.code,
        "SINGLE_TRAINING",
        validation.status_code is IntegrityValidationStatusCode.PASS,
        validation.status_code is IntegrityValidationStatusCode.PASS,
        "COMPLETED" if validation.status_code is IntegrityValidationStatusCode.PASS else "FAILED",
        None
        if validation.status_code is IntegrityValidationStatusCode.PASS
        else "INTEGRITY_FAILED",
        tuple(item.code.value for item in validation.violations),
        False,
        calls,
        telemetry.input_token_count if telemetry else None,
        telemetry.output_token_count if telemetry else None,
        latency,
        compiled.estimated_duration_seconds,
        delta,
        len(prescriptions),
        tuple(sorted({item.phase_code for item in prescriptions})),
    )


async def run_multi(
    scenario: ComparisonScenario, *, runtime: V3ShadowRuntime, settings: Settings
) -> ArchitectureResult:
    versions = V3ShadowRuntimeVersions()
    case = V3ShadowCase.create(
        scenario_code=scenario.code,
        fixture_version=HARNESS_VERSION,
        fixture_hash=hashlib.sha256(HARNESS_VERSION.encode()).hexdigest(),
    )
    request = V3ShadowExecutionRequest(
        case=case,
        graph_version=versions.graph_version,
        policy_version=scenario.envelope.policy_version,
        catalog_version=scenario.envelope.catalog_version,
        prompt_version="agent-comparison-prompts-v1",
        provider_code="OPENAI",
        model_version=settings.llm_agents_model_code,
        snapshot_is_fresh=True,
    )
    try:
        result = await runtime.execute(
            request,
            constraint_envelope=scenario.envelope,
            exercise_pool=scenario.pool,
        )
    except Exception:
        return _failure_result(
            scenario,
            "MULTI_V3",
            failure_code="RUNTIME_FAILED",
            calls=0,
            latency_ms=0,
        )
    plan = result.plan
    completed = result.terminal_status_code.value == "COMPLETED" and plan is not None
    phases = tuple(sorted({item.phase_code for item in plan.prescriptions})) if plan else ()
    target = scenario.envelope.requested_duration_minutes * 60
    return ArchitectureResult(
        scenario.code,
        "MULTI_V3",
        completed,
        result.safety.invariant_passed and not result.constraint_violation_codes,
        result.terminal_status_code.value,
        result.failure_codes[0] if result.failure_codes else None,
        result.constraint_violation_codes,
        result.fallback_used,
        result.usage.provider_call_count,
        result.usage.input_token_count,
        result.usage.output_token_count,
        result.total_latency_ms,
        plan.estimated_duration_seconds if plan else None,
        abs(plan.estimated_duration_seconds - target) if plan else None,
        len(plan.prescriptions) if plan else 0,
        phases,
    )


def summarize(results: tuple[ArchitectureResult, ...]) -> dict[str, dict[str, int | None]]:
    summary: dict[str, dict[str, int | None]] = {}
    for architecture in ("SINGLE_TRAINING", "MULTI_V3"):
        rows = [item for item in results if item.architecture_code == architecture]
        summary[architecture] = {
            "case_count": len(rows),
            "completed_count": sum(item.completed for item in rows),
            "integrity_pass_count": sum(item.integrity_passed for item in rows),
            "fallback_count": sum(item.fallback_used for item in rows),
            "provider_call_count": sum(item.provider_call_count for item in rows),
            "input_token_count": (
                sum(item.input_token_count or 0 for item in rows)
                if all(item.input_token_count is not None for item in rows)
                else None
            ),
            "output_token_count": (
                sum(item.output_token_count or 0 for item in rows)
                if all(item.output_token_count is not None for item in rows)
                else None
            ),
            "mean_latency_ms": round(sum(item.latency_ms for item in rows) / len(rows)),
            "mean_duration_delta_seconds": (
                round(sum(item.duration_delta_seconds or 0 for item in rows) / len(rows))
                if all(item.duration_delta_seconds is not None for item in rows)
                else None
            ),
        }
    return summary


def _write_report(
    output: Path,
    *,
    settings: Settings,
    catalog_version: str,
    results: tuple[ArchitectureResult, ...],
) -> None:
    summary = summarize(results)
    payload = {
        "harness_version": HARNESS_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider_code": "OPENAI",
        "model_code": settings.llm_agents_model_code,
        "catalog_version": catalog_version,
        "cost_status_code": "NOT_AVAILABLE",
        "results": [asdict(item) for item in results],
        "summary": summary,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Single-agent vs multi-agent comparison",
        "",
        f"- Model: `{settings.llm_agents_model_code}`",
        f"- Catalog: `{catalog_version}`",
        "- Cost: `NOT_AVAILABLE` (no approved pricing reference)",
        "",
        "| Architecture | Completed | Integrity | Calls | Input tokens | "
        "Output tokens | Mean latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for code, values in summary.items():
        lines.append(
            f"| {code} | {values['completed_count']}/{values['case_count']} | "
            f"{values['integrity_pass_count']}/{values['case_count']} | "
            f"{values['provider_call_count']} | {values['input_token_count']} | "
            f"{values['output_token_count']} | {values['mean_latency_ms']} |"
        )
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _run(
    settings: Settings, scenarios: tuple[ComparisonScenario, ...]
) -> tuple[ArchitectureResult, ...]:
    runtime = build_v3_shadow_runtime(
        settings,
        allow_provider_calls=True,
        fallback_provider=DeterministicGraphFallbackProvider(),
    )
    values: list[ArchitectureResult] = []
    for index, scenario in enumerate(scenarios):
        if index % 2 == 0:
            values.append(await run_single(scenario, runtime=runtime))
            values.append(await run_multi(scenario, runtime=runtime, settings=settings))
        else:
            values.append(await run_multi(scenario, runtime=runtime, settings=settings))
            values.append(await run_single(scenario, runtime=runtime))
    return tuple(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--maximum-provider-calls", required=True, type=int)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    failure = staging_gate_failure(settings, allow_provider_calls=args.allow_provider_calls)
    if failure is not None:
        print(failure.value, file=sys.stderr)
        return 2
    required_budget = len(SCENARIO_SPECS) * 6 * settings.llm_agents_max_attempts
    if args.maximum_provider_calls < required_budget:
        print("PROVIDER_CALL_BUDGET_TOO_SMALL", file=sys.stderr)
        return 2
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            catalog_version = session.scalar(
                select(CatalogVersion.version_code).where(CatalogVersion.status_code == "ACTIVE")
            )
            if catalog_version is None:
                raise ValueError("ACTIVE_CATALOG_MISSING")
            records = VectorIndexRepository().list_indexable_exercises(session, catalog_version)
        scenarios = build_scenarios(records, catalog_version=catalog_version)
        results = asyncio.run(_run(settings, scenarios))
        root = (Path.cwd() / "outputs" / "agent-comparison").resolve()
        output = (root / args.run_id).resolve()
        if root not in output.parents:
            raise ValueError("OUTPUT_PATH_INVALID")
        _write_report(
            output,
            settings=settings,
            catalog_version=catalog_version,
            results=results,
        )
        print(json.dumps(summarize(results), sort_keys=True))
    except (OSError, ValueError):
        print("COMPARISON_FAILED", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
