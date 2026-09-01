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
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
from backend.app.domain.agents.v3_compiler import (
    CompiledPlan,
    DeterministicFallbackPlanSpec,
    compile_plan,
)
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    ExercisePrescription,
    PlanActionCode,
    RecoveryCeiling,
    SpecialistAgentInput,
    SpecialistAgentTypeCode,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationResult,
    IntegrityValidationStatusCode,
    validate_plan_integrity,
)
from backend.app.integrations.langgraph.shadow_runtime import (
    V3ShadowRuntime,
    V3ShadowRuntimeVersions,
    build_v3_shadow_runtime,
)
from backend.app.integrations.llm_agents.canonicalization import canonical_plan_values
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.payload import specialist_payload
from backend.app.integrations.llm_agents.prompts import RolePrompt, messages_for
from backend.app.modules.decisions.v3_shadow import V3ShadowCase, V3ShadowExecutionRequest
from backend.scripts.run_v3_staging_shadow import staging_gate_failure

HARNESS_VERSION = "single-multi-agent-suitability-v2"
SINGLE_PROMPT_VERSION = "single-integrated-agent-prompt-v1"
SINGLE_OUTPUT_SCHEMA_VERSION = "single-integrated-plan-v1"
SCENARIO_SPECS = (
    ("HEALTHY_GENERAL_30", "BASELINE", "GENERAL_FITNESS", 30, False),
    ("HEALTHY_MUSCLE_30", "BASELINE", "MUSCLE_GAIN", 30, False),
    ("LIMITED_TIME_GENERAL_20", "SINGLE_CONSTRAINT", "GENERAL_FITNESS", 20, False),
    ("FATIGUE_GENERAL_30", "SINGLE_CONSTRAINT", "GENERAL_FITNESS", 30, True),
    ("FATIGUE_LIMITED_GENERAL_20", "JOINT_CONSTRAINT", "GENERAL_FITNESS", 20, True),
    ("FATIGUE_MUSCLE_30", "JOINT_CONSTRAINT", "MUSCLE_GAIN", 30, True),
)


@dataclass(frozen=True, slots=True)
class ComparisonScenario:
    code: str
    group_code: Literal["BASELINE", "SINGLE_CONSTRAINT", "JOINT_CONSTRAINT"]
    envelope: ConstraintEnvelope
    pool: ExercisePoolSnapshot


@dataclass(frozen=True, slots=True)
class ArchitectureResult:
    scenario_code: str
    scenario_group_code: Literal["BASELINE", "SINGLE_CONSTRAINT", "JOINT_CONSTRAINT"]
    repeat_index: int
    architecture_code: Literal["SINGLE_INTEGRATED", "MULTI_V3"]
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
    phase_complete: bool
    goal_core_main_count: int
    recovery_eligible_percent: int | None
    action_code: str | None
    expected_action_matched: bool
    exercise_codes: tuple[str, ...]
    prescription_summaries: tuple[dict[str, object], ...]


class SingleIntegratedPlan(BaseModel):
    """Evaluation-only final plan returned by one monolithic LLM agent."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_code: PlanActionCode
    exercise_prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)
    decision_codes: tuple[str, ...] = Field(min_length=1)
    public_summary_code: str | None = None

    @field_validator("decision_codes")
    @classmethod
    def validate_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("decision_codes must be canonical")
        return values

    @model_validator(mode="after")
    def validate_session_shape(self) -> SingleIntegratedPlan:
        phases = {item.phase_code for item in self.exercise_prescriptions}
        if phases != {"WARMUP", "MAIN", "COOLDOWN"}:
            raise ValueError("single integrated plan must contain all session phases")
        return self


SINGLE_PROMPT = RolePrompt(
    role_code=LlmAgentRoleCode.COORDINATOR,
    version=SINGLE_PROMPT_VERSION,
    instruction=(
        "Act as one integrated exercise-planning agent. You alone perform the Training, Recovery, "
        "and Feasibility responsibilities and return one final plan without specialist proposals. "
        "Preserve the primary goal, use CORE exercises for MAIN work, and apply the supplied "
        "recovery ceiling, duration, location, mandatory, exclusion, and catalog constraints. "
        "Select only IDs from the supplied pool. Include WARMUP, MAIN, and COOLDOWN in that order, "
        "using each exercise only in an allowed phase. Land as close as possible to the requested "
        "duration and never outside the five-minute tolerance. Equipment is catalog information, "
        "not a user eligibility gate. Return stable machine codes and no hidden reasoning."
    ),
)


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
    for code, group, goal, minutes, fatigued in SCENARIO_SPECS:
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
        scenarios.append(
            ComparisonScenario(
                code=code,
                group_code=cast(
                    Literal["BASELINE", "SINGLE_CONSTRAINT", "JOINT_CONSTRAINT"], group
                ),
                envelope=envelope,
                pool=pool,
            )
        )
    return tuple(scenarios)


def _single_payload(scenario: ComparisonScenario) -> dict[str, object]:
    agent_input = SpecialistAgentInput(
        agent_type_code=SpecialistAgentTypeCode.TRAINING,
        constraint_envelope=scenario.envelope,
        envelope_hash=scenario.envelope.envelope_hash,
        exercise_pool=scenario.pool,
        pool_hash=scenario.pool.pool_hash,
    )
    payload = specialist_payload(agent_input)
    payload["schema_version"] = "single-integrated-agent-input-v1"
    payload["agent_type_code"] = "INTEGRATED"
    return payload


def _compile_single_plan(
    output: SingleIntegratedPlan,
    scenario: ComparisonScenario,
    runtime: V3ShadowRuntime,
) -> tuple[CompiledPlan, IntegrityValidationResult]:
    # DeterministicFallbackPlanSpec is reused only as the compiler's proposal-free
    # transport contract. This candidate is model-generated and is never counted as fallback.
    source = DeterministicFallbackPlanSpec.create(
        envelope_hash=scenario.envelope.envelope_hash,
        pool_hash=scenario.pool.pool_hash,
        action_code=output.action_code,
        requested_duration_minutes=scenario.envelope.requested_duration_minutes,
        estimated_duration_seconds=scenario.envelope.requested_duration_minutes * 60,
        exercise_prescriptions=output.exercise_prescriptions,
        reason_codes=output.decision_codes,
        fallback_version="single-integrated-candidate-v1",
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
    if validation.status_code is not IntegrityValidationStatusCode.PASS:
        raise ValueError("single integrated plan failed deterministic integrity validation")
    return compiled, validation


def _validate_single_output(
    output: SingleIntegratedPlan,
    *,
    scenario: ComparisonScenario,
    runtime: V3ShadowRuntime,
) -> SingleIntegratedPlan:
    _compile_single_plan(output, scenario, runtime)
    return output


def _quality_metrics(
    prescriptions: tuple[ExercisePrescription, ...], scenario: ComparisonScenario
) -> tuple[bool, int, int, tuple[str, ...], tuple[dict[str, object], ...]]:
    records = {item.exercise_id: item for item in scenario.pool.exercises}
    phases = {item.phase_code for item in prescriptions}
    goal = scenario.envelope.primary_goal_code
    goal_core_main_count = sum(
        item.phase_code == "MAIN"
        and records[item.exercise_id].role_eligibility_code == "CORE"
        and goal in records[item.exercise_id].goal_codes
        for item in prescriptions
    )
    recovery_count = sum(records[item.exercise_id].recovery_eligible for item in prescriptions)

    def summary(item: ExercisePrescription) -> dict[str, object]:
        return {
            "stable_code": records[item.exercise_id].stable_code,
            "sequence": item.sequence,
            "phase_code": item.phase_code,
            "sets": item.sets,
            "repetitions_per_set": item.repetitions_per_set,
            "work_seconds_per_set": item.work_seconds_per_set,
            "rest_seconds_between_sets": item.rest_seconds_between_sets,
            "transition_seconds": item.transition_seconds,
            "intensity_code": item.intensity_code,
        }

    summaries = tuple(summary(item) for item in prescriptions)
    return (
        phases == {"WARMUP", "MAIN", "COOLDOWN"},
        goal_core_main_count,
        round(100 * recovery_count / len(prescriptions)),
        tuple(records[item.exercise_id].stable_code for item in prescriptions),
        summaries,
    )


def _failure_result(
    scenario: ComparisonScenario,
    architecture: Literal["SINGLE_INTEGRATED", "MULTI_V3"],
    *,
    repeat_index: int,
    failure_code: str,
    calls: int,
    latency_ms: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    fallback_used: bool = False,
) -> ArchitectureResult:
    return ArchitectureResult(
        scenario.code,
        scenario.group_code,
        repeat_index,
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
        False,
        0,
        None,
        None,
        False,
        (),
        (),
    )


async def run_single(
    scenario: ComparisonScenario, *, runtime: V3ShadowRuntime, repeat_index: int
) -> ArchitectureResult:
    started = time.monotonic_ns()
    outcome = await runtime.invoker.ainvoke(
        role_code=LlmAgentRoleCode.COORDINATOR,
        prompt_version=SINGLE_PROMPT_VERSION,
        output_schema_version=SINGLE_OUTPUT_SCHEMA_VERSION,
        output_schema=SingleIntegratedPlan,
        messages=messages_for(
            SINGLE_PROMPT,
            output_schema_version=SINGLE_OUTPUT_SCHEMA_VERSION,
            payload=_single_payload(scenario),
        ),
        domain_validator=lambda output: _validate_single_output(
            output, scenario=scenario, runtime=runtime
        ),
        canonical_factory=lambda values: SingleIntegratedPlan.model_validate(
            canonical_plan_values(values)
        ),
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
            "SINGLE_INTEGRATED",
            repeat_index=repeat_index,
            failure_code=outcome.failure.code.value if outcome.failure else "UNKNOWN_FAILURE",
            calls=calls,
            latency_ms=latency,
            input_tokens=telemetry.input_token_count if telemetry else None,
            output_tokens=telemetry.output_token_count if telemetry else None,
        )
    try:
        compiled, validation = _compile_single_plan(outcome.output, scenario, runtime)
    except (ValueError, KeyError):
        return _failure_result(
            scenario,
            "SINGLE_INTEGRATED",
            repeat_index=repeat_index,
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
    phase_complete, goal_count, recovery_percent, codes, prescription_summaries = _quality_metrics(
        prescriptions, scenario
    )
    expected_action = (
        PlanActionCode.DOWNSHIFT if "FATIGUE" in scenario.code else PlanActionCode.KEEP
    )
    return ArchitectureResult(
        scenario.code,
        scenario.group_code,
        repeat_index,
        "SINGLE_INTEGRATED",
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
        phase_complete,
        goal_count,
        recovery_percent,
        compiled.action_code.value,
        compiled.action_code is expected_action,
        codes,
        prescription_summaries,
    )


async def run_multi(
    scenario: ComparisonScenario,
    *,
    runtime: V3ShadowRuntime,
    settings: Settings,
    repeat_index: int,
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
            repeat_index=repeat_index,
            failure_code="RUNTIME_FAILED",
            calls=0,
            latency_ms=0,
        )
    plan = result.plan
    completed = result.terminal_status_code.value == "COMPLETED" and plan is not None
    phases = tuple(sorted({item.phase_code for item in plan.prescriptions})) if plan else ()
    target = scenario.envelope.requested_duration_minutes * 60
    quality = _quality_metrics(plan.prescriptions, scenario) if plan else (False, 0, 0, (), ())
    expected_action = (
        PlanActionCode.DOWNSHIFT if "FATIGUE" in scenario.code else PlanActionCode.KEEP
    )
    return ArchitectureResult(
        scenario.code,
        scenario.group_code,
        repeat_index,
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
        quality[0],
        quality[1],
        quality[2] if plan else None,
        plan.action_code if plan else None,
        plan is not None and plan.action_code == expected_action.value,
        quality[3],
        quality[4],
    )


def summarize(results: tuple[ArchitectureResult, ...]) -> dict[str, dict[str, int | None]]:
    summary: dict[str, dict[str, int | None]] = {}
    for architecture in ("SINGLE_INTEGRATED", "MULTI_V3"):
        rows = [item for item in results if item.architecture_code == architecture]
        summary[architecture] = {
            "case_count": len(rows),
            "completed_count": sum(item.completed for item in rows),
            "integrity_pass_count": sum(item.integrity_passed for item in rows),
            "phase_complete_count": sum(item.phase_complete for item in rows),
            "goal_preserved_count": sum(item.goal_core_main_count > 0 for item in rows),
            "action_match_count": sum(item.expected_action_matched for item in rows),
            "joint_constraint_completed_count": sum(
                item.completed and item.scenario_group_code == "JOINT_CONSTRAINT" for item in rows
            ),
            "joint_constraint_case_count": sum(
                item.scenario_group_code == "JOINT_CONSTRAINT" for item in rows
            ),
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


def suitability_assessment(results: tuple[ArchitectureResult, ...]) -> dict[str, object]:
    """Apply preregistered automatic rules without claiming subjective plan quality."""

    def suitable(result: ArchitectureResult) -> bool:
        return (
            result.completed
            and result.integrity_passed
            and result.phase_complete
            and result.goal_core_main_count > 0
            and result.expected_action_matched
        )

    counts: dict[str, dict[str, dict[str, int]]] = {}
    for architecture in ("SINGLE_INTEGRATED", "MULTI_V3"):
        counts[architecture] = {}
        for group in ("BASELINE", "SINGLE_CONSTRAINT", "JOINT_CONSTRAINT"):
            rows = [
                item
                for item in results
                if item.architecture_code == architecture and item.scenario_group_code == group
            ]
            counts[architecture][group] = {
                "case_count": len(rows),
                "suitable_plan_count": sum(suitable(item) for item in rows),
            }

    single_baseline = counts["SINGLE_INTEGRATED"]["BASELINE"]
    multi_baseline = counts["MULTI_V3"]["BASELINE"]
    single_joint = counts["SINGLE_INTEGRATED"]["JOINT_CONSTRAINT"]
    multi_joint = counts["MULTI_V3"]["JOINT_CONSTRAINT"]
    expected_repeats = min(single_baseline["case_count"], multi_baseline["case_count"])
    baseline_non_degradation = (
        expected_repeats > 0
        and multi_baseline["suitable_plan_count"] >= single_baseline["suitable_plan_count"] - 1
    )
    # With two joint scenarios repeated three times, two additional successes are
    # a 33-point advantage. Keep the rule count-based so the report remains exact.
    joint_constraint_advantage = (
        single_joint["case_count"] == multi_joint["case_count"]
        and single_joint["case_count"] >= 6
        and multi_joint["suitable_plan_count"] >= single_joint["suitable_plan_count"] + 2
    )
    return {
        "automatic_counts": counts,
        "decision_rules": {
            "baseline_non_degradation": baseline_non_degradation,
            "joint_constraint_advantage": joint_constraint_advantage,
            "blind_expert_review": "PENDING",
        },
        "automatic_evidence_status": (
            "SUPPORTS_ROLE_SEPARATION"
            if baseline_non_degradation and joint_constraint_advantage
            else "DOES_NOT_YET_SUPPORT_ROLE_SEPARATION"
        ),
        "final_conclusion_status": "PENDING_BLIND_EXPERT_REVIEW",
    }


def blind_review_records(
    results: tuple[ArchitectureResult, ...],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    """Pair successful plans without leaking architecture labels to reviewers."""

    grouped: dict[tuple[str, int], dict[str, ArchitectureResult]] = {}
    for result in results:
        grouped.setdefault((result.scenario_code, result.repeat_index), {})[
            result.architecture_code
        ] = result
    reviews: list[dict[str, object]] = []
    keys: list[dict[str, object]] = []
    for (scenario_code, repeat_index), pair in sorted(grouped.items()):
        single = pair.get("SINGLE_INTEGRATED")
        multi = pair.get("MULTI_V3")
        if single is None or multi is None or not single.completed or not multi.completed:
            continue
        digest = hashlib.sha256(f"{scenario_code}:{repeat_index}".encode()).digest()
        ordered = (single, multi) if digest[0] % 2 == 0 else (multi, single)

        def candidate(value: ArchitectureResult) -> dict[str, object]:
            return {
                "action_code": value.action_code,
                "estimated_duration_seconds": value.estimated_duration_seconds,
                "duration_delta_seconds": value.duration_delta_seconds,
                "prescriptions": value.prescription_summaries,
            }

        reviews.append(
            {
                "scenario_code": scenario_code,
                "scenario_group_code": single.scenario_group_code,
                "repeat_index": repeat_index,
                "candidate_a": candidate(ordered[0]),
                "candidate_b": candidate(ordered[1]),
                "review": {
                    "goal_preservation_winner": "PENDING",
                    "recovery_appropriateness_winner": "PENDING",
                    "feasibility_winner": "PENDING",
                    "overall_winner": "PENDING",
                    "reviewer_code": "PENDING",
                },
            }
        )
        keys.append(
            {
                "scenario_code": scenario_code,
                "repeat_index": repeat_index,
                "candidate_a_architecture": ordered[0].architecture_code,
                "candidate_b_architecture": ordered[1].architecture_code,
            }
        )
    return tuple(reviews), tuple(keys)


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
        "suitability_assessment": suitability_assessment(results),
    }
    reviews, blind_keys = blind_review_records(results)
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output / "expert_review_template.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        for record in reviews:
            stream.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
    (output / "blind_key.json").write_text(
        json.dumps(blind_keys, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Integrated single-agent vs role-separated multi-agent suitability",
        "",
        f"- Model: `{settings.llm_agents_model_code}`",
        f"- Catalog: `{catalog_version}`",
        "- Cost: `NOT_AVAILABLE` (no approved pricing reference)",
        "",
        "- Deterministic fallback: `DISABLED_FOR_BOTH_ARCHITECTURES`",
        "- Safety policy: `SAME_DETERMINISTIC_ENVELOPE_AND_POST_PLAN_VALIDATOR`",
        "",
        "| Architecture | Completed | Integrity | Phase complete | Goal preserved | "
        "Action match | Joint constraints | Calls | Mean latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for code, values in summary.items():
        lines.append(
            f"| {code} | {values['completed_count']}/{values['case_count']} | "
            f"{values['integrity_pass_count']}/{values['case_count']} | "
            f"{values['phase_complete_count']}/{values['case_count']} | "
            f"{values['goal_preserved_count']}/{values['case_count']} | "
            f"{values['action_match_count']}/{values['case_count']} | "
            f"{values['joint_constraint_completed_count']}/"
            f"{values['joint_constraint_case_count']} | "
            f"{values['provider_call_count']} | {values['mean_latency_ms']} |"
        )
    lines.extend(
        [
            "",
            f"- Automatic evidence: "
            f"`{suitability_assessment(results)['automatic_evidence_status']}`",
            "- Final conclusion: `PENDING_BLIND_EXPERT_REVIEW`",
            "",
            "Automatic metrics establish reliability and constraint adherence. The paired "
            "expert-review template must be scored before making a plan-quality claim.",
        ]
    )
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _run(
    settings: Settings,
    scenarios: tuple[ComparisonScenario, ...],
    *,
    repeat_count: int,
) -> tuple[ArchitectureResult, ...]:
    runtime = build_v3_shadow_runtime(settings, allow_provider_calls=True)
    values: list[ArchitectureResult] = []
    for repeat_index in range(1, repeat_count + 1):
        for scenario_index, scenario in enumerate(scenarios):
            if (scenario_index + repeat_index) % 2 == 0:
                values.append(
                    await run_single(scenario, runtime=runtime, repeat_index=repeat_index)
                )
                values.append(
                    await run_multi(
                        scenario,
                        runtime=runtime,
                        settings=settings,
                        repeat_index=repeat_index,
                    )
                )
            else:
                values.append(
                    await run_multi(
                        scenario,
                        runtime=runtime,
                        settings=settings,
                        repeat_index=repeat_index,
                    )
                )
                values.append(
                    await run_single(scenario, runtime=runtime, repeat_index=repeat_index)
                )
    return tuple(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--maximum-provider-calls", required=True, type=int)
    parser.add_argument("--repeat-count", default=3, type=int)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    failure = staging_gate_failure(settings, allow_provider_calls=args.allow_provider_calls)
    if failure is not None:
        print(failure.value, file=sys.stderr)
        return 2
    if args.repeat_count < 1 or args.repeat_count > 5:
        print("REPEAT_COUNT_INVALID", file=sys.stderr)
        return 2
    required_budget = len(SCENARIO_SPECS) * args.repeat_count * 6 * settings.llm_agents_max_attempts
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
        results = asyncio.run(_run(settings, scenarios, repeat_count=args.repeat_count))
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
