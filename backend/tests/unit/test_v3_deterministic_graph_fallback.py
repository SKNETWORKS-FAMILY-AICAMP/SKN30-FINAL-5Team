from __future__ import annotations

from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import _PHASE_ORDER, PlanPhaseCode
from backend.app.domain.agents.v3_duration import plan_duration_seconds
from backend.app.domain.agents.v3_orchestration import (
    FallbackRequest,
    GraphTerminalStatusCode,
    execute_deterministic_fallback,
)
from backend.app.domain.agents.v3_validation import IntegrityValidationContext
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS
from backend.app.integrations.langgraph.fallback import DeterministicGraphFallbackProvider
from backend.tests.unit.test_v3_demo_runtime import _blocked_root_snapshot
from backend.tests.unit.test_v3_duration import _envelope as duration_envelope
from backend.tests.unit.test_v3_duration import _pool as duration_pool
from backend.tests.unit.test_v3_duration import reps_record
from backend.tests.unit.test_v3_persistence_service import make_bundle


def test_default_fallback_compiles_and_passes_integrity_validation() -> None:
    root = make_bundle().root_snapshot
    provider = DeterministicGraphFallbackProvider()

    outcome = execute_deterministic_fallback(
        provider,
        envelope=root.constraint_envelope,
        pool=root.exercise_pool,
        fallback_version="v3-deterministic-fallback-v1",
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )

    assert outcome.compiled_plan is not None
    assert outcome.terminal_result is None
    assert outcome.compiled_plan.requested_duration_minutes == (
        root.constraint_envelope.requested_duration_minutes
    )


def test_safety_veto_cannot_be_overridden_by_default_fallback() -> None:
    root = _blocked_root_snapshot()
    provider = DeterministicGraphFallbackProvider()
    request = FallbackRequest.create(
        constraint_envelope=root.constraint_envelope,
        exercise_pool=root.exercise_pool,
        fallback_version="v3-deterministic-fallback-v1",
    )

    assert provider.generate(request) is None
    outcome = execute_deterministic_fallback(
        provider,
        envelope=root.constraint_envelope,
        pool=root.exercise_pool,
        fallback_version="v3-deterministic-fallback-v1",
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )
    assert outcome.compiled_plan is None
    assert outcome.terminal_result is not None
    assert outcome.terminal_result.status_code is GraphTerminalStatusCode.STOP_AND_SEEK_HELP


def test_fallback_returns_no_plan_when_mandatory_exercise_has_no_allowed_location() -> None:
    source = make_bundle().root_snapshot
    envelope_values = source.constraint_envelope.model_dump(exclude={"envelope_hash"})
    envelope_values["allowed_location_codes"] = ("GYM",)
    incompatible_envelope = type(source.constraint_envelope).create(**envelope_values)
    source_pool = source.exercise_pool
    incompatible_pool = ExercisePoolSnapshot.create(
        catalog_version=source_pool.catalog_version,
        constraint_envelope_hash=incompatible_envelope.envelope_hash,
        exercises=source_pool.exercises,
        mandatory_exercise_ids=source_pool.mandatory_exercise_ids,
        vector_ranked_exercise_ids=source_pool.vector_ranked_exercise_ids,
        retrieval_metadata=source_pool.retrieval_metadata,
        created_at=source_pool.created_at,
    )
    provider = DeterministicGraphFallbackProvider()
    request = FallbackRequest.create(
        constraint_envelope=incompatible_envelope,
        exercise_pool=incompatible_pool,
        fallback_version="v3-deterministic-fallback-v1",
    )

    assert provider.generate(request) is None


def test_fallback_fills_the_requested_duration_instead_of_declaring_it() -> None:
    # The fallback previously prescribed one set of one repetition per exercise
    # and still reported the full requested duration.
    envelope = duration_envelope(requested_duration_minutes=30)
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))
    pool = duration_pool(envelope, records)
    provider = DeterministicGraphFallbackProvider()

    spec = provider.generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version="v3-deterministic-fallback-v1",
        )
    )

    assert spec is not None
    measured = plan_duration_seconds(
        spec.exercise_prescriptions, {item.exercise_id: item for item in records}
    )
    assert spec.estimated_duration_seconds == measured
    assert abs(measured - 30 * 60) <= DURATION_TOLERANCE_SECONDS


def test_fallback_declines_when_the_pool_cannot_reach_the_requested_duration() -> None:
    # Section 7: the request fails rather than silently handing back a shorter
    # session than the user asked for.
    envelope = duration_envelope(requested_duration_minutes=60)
    records = (reps_record(UUID(int=1)),)
    pool = duration_pool(envelope, records)
    provider = DeterministicGraphFallbackProvider()

    request = FallbackRequest.create(
        constraint_envelope=envelope,
        exercise_pool=pool,
        fallback_version="v3-deterministic-fallback-v1",
    )

    assert provider.generate(request) is None


def test_fallback_orders_its_plan_by_session_phase() -> None:
    """Selection is driven by rank and duration, so the result must be ordered.

    The plan contract rejects a session that runs MAIN before WARMUP, so a
    fallback that appended in retrieval order would fail to build at all.
    """

    envelope = duration_envelope(requested_duration_minutes=30)
    records = tuple(
        reps_record(
            UUID(int=index),
            phase_codes=("COOLDOWN",) if index == 1 else ("MAIN",) if index > 2 else ("WARMUP",),
        )
        for index in range(1, 11)
    )
    pool = duration_pool(envelope, records)
    provider = DeterministicGraphFallbackProvider()

    spec = provider.generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version="v3-deterministic-fallback-v1",
        )
    )

    assert spec is not None
    phases = [item.phase_code for item in spec.exercise_prescriptions]
    assert phases == sorted(phases, key=lambda code: _PHASE_ORDER[code])
    assert PlanPhaseCode.WARMUP in phases
    assert PlanPhaseCode.COOLDOWN in phases
    assert [item.sequence for item in spec.exercise_prescriptions] == list(
        range(1, len(phases) + 1)
    )
