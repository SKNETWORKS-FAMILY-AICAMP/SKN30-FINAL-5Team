"""Versioned, synthetic-only fixtures for the offline V3 evaluation harness."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    RetrievalFailureCode,
    RetrievalMetadata,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    ExercisePrescription,
    RecoveryCeiling,
    RegenerationContext,
)
from backend.app.domain.agents.v3_orchestration import GraphTerminalStatusCode
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowCase,
    V3ShadowExecutionRequest,
    V3ShadowExecutionResult,
    V3ShadowInvocationMetric,
    V3ShadowInvocationPhaseCode,
    V3ShadowInvocationStatusCode,
    V3ShadowPlanProjection,
    V3ShadowRoleCode,
    V3ShadowSafetyMetric,
    V3ShadowStructuredOutputStatusCode,
    V3ShadowUsageMetric,
    V3ShadowUsageStatusCode,
)

SYNTHETIC_FIXTURE_VERSION: Final[str] = "v3-shadow-golden-v2"
SYNTHETIC_FIXTURE_SCHEMA_VERSION: Final[str] = "v3-shadow-fixture-bundle-v1"
STAGING_CATALOG_VERSION: Final[str] = "exercise-catalog-v2.0.1-final"
FIXED_TIME: Final[datetime] = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
EXERCISE_A = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_B = UUID("00000000-0000-0000-0000-000000000002")
EXERCISE_C = UUID("00000000-0000-0000-0000-000000000003")
_FIXTURE_SOURCE_HASH = hashlib.sha256(SYNTHETIC_FIXTURE_VERSION.encode()).hexdigest()


class V3SyntheticShadowFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case: V3ShadowCase
    request: V3ShadowExecutionRequest
    constraint_envelope: ConstraintEnvelope
    exercise_pool: ExercisePoolSnapshot
    regeneration_context: RegenerationContext | None = None
    stored_result: V3ShadowExecutionResult


class V3SyntheticFixtureBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = SYNTHETIC_FIXTURE_SCHEMA_VERSION
    fixture_version: str = SYNTHETIC_FIXTURE_VERSION
    generated_at: datetime = FIXED_TIME
    fixtures: tuple[V3SyntheticShadowFixture, ...]
    fixture_hash: str


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _exercise(exercise_id: UUID) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=exercise_id,
        catalog_version=STAGING_CATALOG_VERSION,
        content_version=f"content-{exercise_id.int}",
        stable_code=f"synthetic-exercise-{exercise_id.int}",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=("PUSH",),
        difficulty_code="BEGINNER",
        timing_mode_code="REPS",
        default_seconds_per_rep=3,
        default_rest_seconds=30,
        default_transition_seconds=15,
        recovery_eligible=True,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=("BODYWEIGHT",),
        location_codes=("HOME",),
        prescription_reference_codes=("synthetic-prescription-v1",),
        source_reference_codes=("synthetic-source-v1",),
        review_reference_codes=("synthetic-review-v1",),
    )


def _envelope(*, generation_allowed: bool = True) -> ConstraintEnvelope:
    return ConstraintEnvelope.create(
        requested_duration_minutes=30,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=("BODYWEIGHT",),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(EXERCISE_A,),
        recovery_ceiling=RecoveryCeiling(
            policy_version="recovery-policy-v1",
            allowed_intensity_codes=("LOW", "MODERATE"),
            allowed_load_codes=("BODYWEIGHT",),
            maximum_sets_per_exercise=3,
            maximum_repetitions_per_set=12,
            maximum_work_seconds_per_set=60,
            minimum_rest_seconds_between_sets=30,
        ),
        plan_generation_allowed=generation_allowed,
        safety_required_action_code=(
            SafetyRequiredActionCode.STOP_AND_SEEK_HELP if not generation_allowed else None
        ),
        policy_version="decision-policy-v3",
        catalog_version=STAGING_CATALOG_VERSION,
        safety_rule_version="safety-rules-v3",
    )


def _pool(
    envelope: ConstraintEnvelope, *, retrieval_code: str = "SUCCEEDED"
) -> ExercisePoolSnapshot:
    failed = retrieval_code != "SUCCEEDED"
    status = (
        RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        if not failed
        else RetrievalStatusCode(retrieval_code)
    )
    metadata = RetrievalMetadata(
        collection_name=None if failed else "exercise-catalog-v3",
        vector_index_version=None if failed else "vector-index-v3",
        embedding_model_version=None if failed else "embedding-v3",
        query_hash=_hash(f"query:{retrieval_code}"),
        retrieval_status_code=status,
        retrieval_failure_codes=() if not failed else (RetrievalFailureCode(status.value),),
        deterministic_fallback_version=None if not failed else "pool-fallback-v1",
        deterministic_pool_fallback_used=failed,
    )
    return ExercisePoolSnapshot.create(
        catalog_version=STAGING_CATALOG_VERSION,
        constraint_envelope_hash=envelope.envelope_hash,
        exercises=tuple(_exercise(item) for item in (EXERCISE_A, EXERCISE_B, EXERCISE_C)),
        mandatory_exercise_ids=(EXERCISE_A,),
        vector_ranked_exercise_ids=() if failed else (EXERCISE_B, EXERCISE_C),
        retrieval_metadata=metadata,
        created_at=FIXED_TIME,
    )


def _phase_for(sequence: int, total: int) -> Literal["WARMUP", "MAIN", "COOLDOWN"]:
    """Open with preparation and close with settling, main work in between."""

    if sequence == 1:
        return "WARMUP"
    if sequence == total:
        return "COOLDOWN"
    return "MAIN"


def _prescription(exercise_id: UUID, sequence: int, total: int) -> ExercisePrescription:
    return ExercisePrescription(
        exercise_id=exercise_id,
        sequence=sequence,
        phase_code=_phase_for(sequence, total),
        sets=3,
        repetitions_per_set=10,
        rest_seconds_between_sets=30,
        transition_seconds=15,
        intensity_code="MODERATE",
        load_code="BODYWEIGHT",
        location_code="HOME",
        equipment_codes=("BODYWEIGHT",),
    )


def _plan(case_code: str, exercise_ids: tuple[UUID, ...]) -> V3ShadowPlanProjection:
    return V3ShadowPlanProjection(
        action_code="KEEP",
        requested_duration_minutes=30,
        estimated_duration_seconds=1800,
        prescriptions=tuple(
            _prescription(exercise_id, index, len(exercise_ids))
            for index, exercise_id in enumerate(exercise_ids, start=1)
        ),
        plan_hash=_hash(f"plan:{case_code}:{','.join(map(str, exercise_ids))}"),
    )


def _invocation(
    role: V3ShadowRoleCode,
    phase: V3ShadowInvocationPhaseCode,
    *,
    status: V3ShadowInvocationStatusCode = V3ShadowInvocationStatusCode.SUCCEEDED,
    latency_ms: int = 40,
) -> V3ShadowInvocationMetric:
    return V3ShadowInvocationMetric(
        role_code=role,
        phase_code=phase,
        status_code=status,
        attempt_count=2 if status is not V3ShadowInvocationStatusCode.SUCCEEDED else 1,
        latency_ms=latency_ms,
        provider_code="FAKE",
        model_version="fake-model-v1",
        prompt_version=f"{role.value.lower()}-prompt-v1",
        output_schema_version="synthetic-output-v1",
        failure_code=None if status is V3ShadowInvocationStatusCode.SUCCEEDED else status.value,
        input_token_count=20 if status is V3ShadowInvocationStatusCode.SUCCEEDED else None,
        output_token_count=10 if status is V3ShadowInvocationStatusCode.SUCCEEDED else None,
    )


def _successful_invocations(
    *, review_role: V3ShadowRoleCode | None = None, repair: bool = False
) -> tuple[V3ShadowInvocationMetric, ...]:
    values: list[V3ShadowInvocationMetric] = []
    for role in (
        V3ShadowRoleCode.TRAINING,
        V3ShadowRoleCode.RECOVERY,
        V3ShadowRoleCode.FEASIBILITY,
    ):
        values.append(_invocation(role, V3ShadowInvocationPhaseCode.PROPOSE))
        if role is review_role:
            values.append(_invocation(role, V3ShadowInvocationPhaseCode.REVIEW, latency_ms=30))
    values.append(_invocation(V3ShadowRoleCode.COORDINATOR, V3ShadowInvocationPhaseCode.COORDINATE))
    if repair:
        values.append(_invocation(V3ShadowRoleCode.COORDINATOR, V3ShadowInvocationPhaseCode.REPAIR))
    return tuple(values)


def _usage(invocations: tuple[V3ShadowInvocationMetric, ...]) -> V3ShadowUsageMetric:
    if not invocations:
        return V3ShadowUsageMetric(
            status_code=V3ShadowUsageStatusCode.NOT_APPLICABLE,
            provider_call_count=0,
        )
    tokens_available = all(item.input_token_count is not None for item in invocations)
    if not tokens_available:
        return V3ShadowUsageMetric(
            status_code=V3ShadowUsageStatusCode.UNAVAILABLE,
            provider_call_count=len(invocations),
        )
    return V3ShadowUsageMetric(
        status_code=V3ShadowUsageStatusCode.COMPLETE,
        provider_call_count=len(invocations),
        input_token_count=sum(item.input_token_count or 0 for item in invocations),
        output_token_count=sum(item.output_token_count or 0 for item in invocations),
    )


def _fixture(
    scenario_code: str,
    *,
    terminal: GraphTerminalStatusCode = GraphTerminalStatusCode.COMPLETED,
    baseline_ids: tuple[UUID, ...] = (EXERCISE_A, EXERCISE_B),
    result_ids: tuple[UUID, ...] = (EXERCISE_A, EXERCISE_B),
    invocations: tuple[V3ShadowInvocationMetric, ...] | None = None,
    review_count: int = 0,
    repair_count: int = 0,
    fallback: bool = False,
    failure_codes: tuple[str, ...] = (),
    retrieval_code: str = "SUCCEEDED",
    structured_success: bool = True,
    regeneration_sequence: int | None = None,
    generation_allowed: bool = True,
) -> V3SyntheticShadowFixture:
    baseline = _plan(f"baseline-{scenario_code}", baseline_ids)
    case = V3ShadowCase.create(
        scenario_code=scenario_code,
        fixture_version=SYNTHETIC_FIXTURE_VERSION,
        fixture_hash=_FIXTURE_SOURCE_HASH,
        baseline_plan=baseline,
    )
    envelope = _envelope(generation_allowed=generation_allowed)
    pool = _pool(envelope, retrieval_code=retrieval_code)
    current_invocations = invocations if invocations is not None else _successful_invocations()
    plan = (
        _plan(scenario_code, result_ids) if terminal is GraphTerminalStatusCode.COMPLETED else None
    )
    result = V3ShadowExecutionResult.create(
        scenario_code=scenario_code,
        case_hash=case.case_hash,
        graph_version="v3-langgraph-v2",
        policy_version=envelope.policy_version,
        catalog_version=envelope.catalog_version,
        prompt_version="v3-prompts-v1",
        provider_code="FAKE",
        model_version="fake-model-v1",
        terminal_status_code=terminal,
        plan=plan,
        safety=V3ShadowSafetyMetric(invariant_passed=True),
        structured_output_status_code=(
            V3ShadowStructuredOutputStatusCode.SUCCEEDED
            if structured_success
            else V3ShadowStructuredOutputStatusCode.FAILED
        ),
        constraint_violation_codes=(),
        invocation_metrics=current_invocations,
        review_attempt_count=review_count,
        repair_attempt_count=repair_count,
        fallback_used=fallback,
        fallback_code="DETERMINISTIC_FALLBACK" if fallback else None,
        fallback_version="fallback-v1" if fallback else None,
        failure_codes=tuple(sorted(failure_codes)),
        total_latency_ms=sum(item.latency_ms for item in current_invocations),
        usage=_usage(current_invocations),
    )
    regeneration_context = (
        None
        if regeneration_sequence is None
        else RegenerationContext(
            generation_sequence=regeneration_sequence,
            previous_plan_hash=baseline.plan_hash,
            previous_exercise_ids=tuple(item.exercise_id for item in baseline.prescriptions),
            variation_codes=("CORE_EXERCISE_CHANGED", "EXERCISE_ORDER_CHANGED"),
        )
    )
    request = V3ShadowExecutionRequest(
        case=case,
        graph_version="v3-langgraph-v2",
        policy_version=envelope.policy_version,
        catalog_version=envelope.catalog_version,
        prompt_version="v3-prompts-v1",
        provider_code="FAKE",
        model_version="fake-model-v1",
        snapshot_is_fresh="STALE" not in scenario_code,
    )
    return V3SyntheticShadowFixture(
        case=case,
        request=request,
        constraint_envelope=envelope,
        exercise_pool=pool,
        regeneration_context=regeneration_context,
        stored_result=result,
    )


def build_synthetic_fixture_bundle() -> V3SyntheticFixtureBundle:
    invalid_invocations = (
        _invocation(
            V3ShadowRoleCode.TRAINING,
            V3ShadowInvocationPhaseCode.PROPOSE,
            status=V3ShadowInvocationStatusCode.INVALID_OUTPUT,
        ),
        _invocation(V3ShadowRoleCode.RECOVERY, V3ShadowInvocationPhaseCode.PROPOSE),
        _invocation(V3ShadowRoleCode.FEASIBILITY, V3ShadowInvocationPhaseCode.PROPOSE),
    )
    timeout_invocations = tuple(
        _invocation(
            role,
            V3ShadowInvocationPhaseCode.PROPOSE,
            status=V3ShadowInvocationStatusCode.TIMEOUT,
        )
        for role in (
            V3ShadowRoleCode.TRAINING,
            V3ShadowRoleCode.RECOVERY,
            V3ShadowRoleCode.FEASIBILITY,
        )
    )
    fixtures = (
        _fixture("HEALTHY_ORIGINAL"),
        _fixture("LIMITED_TIME_DURATION_PRESERVED"),
        _fixture("KNEE_LOAD_EXCLUDED_GOAL_PRESERVED", result_ids=(EXERCISE_A, EXERCISE_C)),
        _fixture("WEARABLE_MISSING_MANUAL_FALLBACK"),
        _fixture("REQUIRED_LLM_FAILURE_FALLBACK", fallback=True),
        _fixture(
            "SAFETY_VETO_PRECEDENCE",
            terminal=GraphTerminalStatusCode.REST,
            invocations=(),
            generation_allowed=False,
        ),
        _fixture("NO_CONFLICT_NO_REVIEW"),
        _fixture(
            "CONFLICT_AFFECTED_REVIEW_ONLY",
            invocations=_successful_invocations(review_role=V3ShadowRoleCode.RECOVERY),
            review_count=1,
        ),
        _fixture(
            "REPAIRABLE_VALIDATION_ONE_REPAIR",
            invocations=_successful_invocations(repair=True),
            repair_count=1,
        ),
        _fixture(
            "REPEATED_ERROR_NO_EXTRA_REPAIR",
            terminal=GraphTerminalStatusCode.FAILED,
            invocations=_successful_invocations(repair=True),
            repair_count=1,
            failure_codes=("VALIDATION_REPEATED",),
        ),
        _fixture(
            "QDRANT_TIMEOUT_POOL_FALLBACK",
            fallback=True,
            retrieval_code="VECTOR_SEARCH_TIMEOUT",
            failure_codes=("VECTOR_SEARCH_TIMEOUT",),
        ),
        _fixture(
            "STALE_CATALOG_INDEX_DISCARDED",
            terminal=GraphTerminalStatusCode.FAILED,
            invocations=(),
            retrieval_code="VECTOR_RESULT_STALE",
            failure_codes=("VECTOR_RESULT_STALE",),
        ),
        _fixture(
            "REGENERATION_EXACT_DUPLICATE_REJECTED",
            terminal=GraphTerminalStatusCode.FAILED,
            regeneration_sequence=1,
            failure_codes=("NO_ALTERNATIVE_AVAILABLE",),
        ),
        _fixture(
            "REGENERATION_MEANINGFUL_DIFFERENCE",
            result_ids=(EXERCISE_A, EXERCISE_C),
            regeneration_sequence=1,
        ),
        _fixture(
            "REGENERATION_MAX_TWO",
            result_ids=(EXERCISE_A, EXERCISE_C),
            regeneration_sequence=2,
        ),
        _fixture(
            "PROVIDER_INVALID_STRUCTURED_OUTPUT",
            invocations=invalid_invocations,
            fallback=True,
            structured_success=False,
            failure_codes=("INVALID_OUTPUT",),
        ),
        _fixture(
            "PROVIDER_TOTAL_TIMEOUT",
            terminal=GraphTerminalStatusCode.FAILED,
            invocations=timeout_invocations,
            structured_success=False,
            failure_codes=("PROVIDER_TIMEOUT",),
        ),
        _fixture(
            "NO_APPROVED_SAFE_EXERCISE",
            terminal=GraphTerminalStatusCode.REST,
            invocations=(),
            failure_codes=("NO_APPROVED_SAFE_EXERCISE",),
            generation_allowed=False,
        ),
        _fixture(
            "STOP_AND_SEEK_HELP",
            terminal=GraphTerminalStatusCode.STOP_AND_SEEK_HELP,
            invocations=(),
            generation_allowed=False,
        ),
        _fixture("PRIVACY_ALLOWLIST"),
    )
    fixture_hash = _hash("|".join(item.case.case_hash for item in fixtures))
    return V3SyntheticFixtureBundle(fixtures=fixtures, fixture_hash=fixture_hash)


__all__ = [
    "FIXED_TIME",
    "SYNTHETIC_FIXTURE_SCHEMA_VERSION",
    "SYNTHETIC_FIXTURE_VERSION",
    "V3SyntheticFixtureBundle",
    "V3SyntheticShadowFixture",
    "build_synthetic_fixture_bundle",
]
