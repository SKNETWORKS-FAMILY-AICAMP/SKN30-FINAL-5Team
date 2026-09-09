from __future__ import annotations

from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope
from backend.app.domain.agents.v3_duration import plan_duration_seconds
from backend.app.domain.agents.v3_orchestration import (
    FallbackRequest,
    GraphTerminalStatusCode,
    execute_deterministic_fallback,
)
from backend.app.domain.agents.v3_validation import IntegrityValidationContext
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS
from backend.app.domain.rules.plan_shape import (
    MAX_PHASE_EXERCISE_TYPES,
    MAX_PLAN_EXERCISE_TYPES,
    families_over_budget,
    phase_rank,
)
from backend.app.integrations.langgraph.fallback import (
    DETERMINISTIC_FALLBACK_VERSION,
    DeterministicGraphFallbackProvider,
)
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
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )

    assert outcome.compiled_plan is not None
    assert outcome.terminal_result is None
    assert outcome.compiled_plan.requested_duration_minutes == (
        root.constraint_envelope.requested_duration_minutes
    )


def test_fallback_uses_approved_fitt_defaults_not_recovery_maxima() -> None:
    root = make_bundle().root_snapshot
    provider = DeterministicGraphFallbackProvider()
    spec = provider.generate(
        FallbackRequest.create(
            constraint_envelope=root.constraint_envelope,
            exercise_pool=root.exercise_pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    records = {item.exercise_id: item for item in root.exercise_pool.exercises}
    for prescription in spec.exercise_prescriptions:
        record = records[prescription.exercise_id]
        if record.timing_mode_code != "REPS":
            continue
        assert record.fitt_context is not None
        assert record.fitt_context.volume is not None
        volume = record.fitt_context.volume
        assert prescription.sets == volume.default_sets
        assert prescription.repetitions_per_set == volume.default_reps


def test_safety_veto_cannot_be_overridden_by_default_fallback() -> None:
    root = _blocked_root_snapshot()
    provider = DeterministicGraphFallbackProvider()
    request = FallbackRequest.create(
        constraint_envelope=root.constraint_envelope,
        exercise_pool=root.exercise_pool,
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
    )

    assert provider.generate(request) is None
    outcome = execute_deterministic_fallback(
        provider,
        envelope=root.constraint_envelope,
        pool=root.exercise_pool,
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
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
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
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
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    measured = plan_duration_seconds(
        spec.exercise_prescriptions, {item.exercise_id: item for item in records}
    )
    assert spec.estimated_duration_seconds == measured
    assert abs(measured - 30 * 60) <= DURATION_TOLERANCE_SECONDS


def test_light_recovery_fallback_fills_30_minutes_without_raising_work_caps() -> None:
    """The production default-like LIGHT envelope must retain a safe 30-minute fallback."""

    source = duration_envelope(requested_duration_minutes=30, maximum_sets_per_exercise=2)
    ceiling = source.recovery_ceiling.model_copy(
        update={
            "allowed_intensity_codes": ("LOW",),
            "maximum_repetitions_per_set": 10,
        }
    )
    values = source.model_dump(exclude={"envelope_hash"})
    values["recovery_ceiling"] = ceiling
    envelope = ConstraintEnvelope.create(**values)
    records = (
        reps_record(UUID(int=1), phase_codes=("WARMUP",)),
        *tuple(reps_record(UUID(int=index), phase_codes=("MAIN",)) for index in range(2, 10)),
        reps_record(UUID(int=10), phase_codes=("COOLDOWN",)),
    )
    pool = duration_pool(envelope, records)

    outcome = execute_deterministic_fallback(
        DeterministicGraphFallbackProvider(),
        envelope=envelope,
        pool=pool,
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )

    assert outcome.compiled_plan is not None
    assert outcome.terminal_result is None
    assert outcome.compiled_plan.estimated_duration_seconds == 30 * 60
    assert all(item.prescription.sets <= 2 for item in outcome.compiled_plan.exercises)
    assert all(
        item.prescription.repetitions_per_set is None or item.prescription.repetitions_per_set <= 10
        for item in outcome.compiled_plan.exercises
    )
    assert all(
        item.prescription.intensity_code == "LOW" for item in outcome.compiled_plan.exercises
    )


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
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
    )

    assert provider.generate(request) is None


def test_fallback_builds_a_90_minute_plan_with_nonconsecutive_main_repetitions() -> None:
    envelope = duration_envelope(
        requested_duration_minutes=90,
        maximum_sets_per_exercise=None,
    )
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))
    pool = duration_pool(envelope, records)

    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    assert abs(spec.estimated_duration_seconds - 90 * 60) <= DURATION_TOLERANCE_SECONDS
    assert (
        len({item.exercise_id for item in spec.exercise_prescriptions}) <= MAX_PLAN_EXERCISE_TYPES
    )
    main_ids = [
        item.exercise_id for item in spec.exercise_prescriptions if item.phase_code == "MAIN"
    ]
    assert any(main_ids.count(exercise_id) > 1 for exercise_id in main_ids)
    assert all(
        previous != current for previous, current in zip(main_ids, main_ids[1:], strict=False)
    )
    for phase_code in ("WARMUP", "COOLDOWN"):
        phase_ids = [
            item.exercise_id
            for item in spec.exercise_prescriptions
            if item.phase_code == phase_code
        ]
        assert len(phase_ids) == len(set(phase_ids))


def test_fallback_builds_a_plan_when_the_equipment_allowlist_is_empty() -> None:
    # The production shape. Onboarding stopped collecting equipment on
    # 2026-08-27, so the envelope allowlist is empty and intersecting a
    # record's equipment with it produced nothing -- which made _prescribe
    # decline every record that names any equipment, BODYWEIGHT included.
    # The deterministic fallback then had nothing to build from, and because
    # a fallback that returns no plan routes straight to terminal, the graph
    # ended FAILED with no reason code at all.
    envelope = duration_envelope(requested_duration_minutes=30, allowed_equipment_codes=())
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))
    pool = duration_pool(envelope, records)
    provider = DeterministicGraphFallbackProvider()

    spec = provider.generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    assert spec.exercise_prescriptions
    # The catalog's own equipment is carried through, so the integrity
    # validator can still check the prescription against the reviewed record.
    by_id = {item.exercise_id: item for item in records}
    for prescription in spec.exercise_prescriptions:
        record = by_id[prescription.exercise_id]
        assert set(prescription.equipment_codes) == set(record.equipment_codes)


def test_fallback_opens_with_a_warmup_and_closes_with_a_cooldown() -> None:
    # The fallback never passed phase_code, so every prescription defaulted to
    # MAIN and the deterministic path could only produce a session with no
    # preparation and no settling work.
    envelope = duration_envelope(requested_duration_minutes=30)
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))
    pool = duration_pool(envelope, records)

    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    phases = [item.phase_code for item in spec.exercise_prescriptions]
    assert phases[0] == "WARMUP"
    assert phases[-1] == "COOLDOWN"
    assert set(phases) == {"WARMUP", "MAIN", "COOLDOWN"}
    assert phases == sorted(phases, key=phase_rank)
    assert [item.sequence for item in spec.exercise_prescriptions] == list(
        range(1, len(phases) + 1)
    )


def test_fallback_keeps_the_session_inside_the_exercise_type_budget() -> None:
    # A session is a workout, not an inventory: the base-routine planner has
    # always capped distinct exercises, and the V3 path inherited no such bound.
    envelope = duration_envelope(requested_duration_minutes=120)
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 31))
    pool = duration_pool(envelope, records)

    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    if spec is not None:
        prescriptions = spec.exercise_prescriptions
        assert len({item.exercise_id for item in prescriptions}) <= MAX_PLAN_EXERCISE_TYPES
        for phase_code, cap in MAX_PHASE_EXERCISE_TYPES.items():
            phase_ids = {
                item.exercise_id for item in prescriptions if item.phase_code == phase_code
            }
            assert len(phase_ids) <= cap


def test_fallback_takes_one_exercise_per_movement_family() -> None:
    # The catalog groups near-identical variants under a family code. Three good
    # mornings that differ only by implement spend the session's exercise budget
    # without giving the user anything new to do, so selection takes one of them
    # and moves on to a different movement.
    envelope = duration_envelope(requested_duration_minutes=60)
    family = tuple(
        reps_record(UUID(int=index), family_code="GOOD_MORNING") for index in range(1, 4)
    )
    others = tuple(reps_record(UUID(int=index)) for index in range(4, 21))
    pool = duration_pool(envelope, family + others)

    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    records = {record.exercise_id: record for record in family + others}
    assert (
        families_over_budget(
            (item.exercise_id, records[item.exercise_id].family_code)
            for item in spec.exercise_prescriptions
        )
        == ()
    )


def test_fallback_still_uses_a_family_member_when_it_is_the_only_candidate() -> None:
    # One-per-family narrows the choice; it must not empty a phase. A pool whose
    # only cooldown candidates share a family still has to yield a plan.
    envelope = duration_envelope(requested_duration_minutes=30)
    records = (
        reps_record(UUID(int=1), phase_codes=("WARMUP",), family_code="CAT_COW"),
        reps_record(UUID(int=2), phase_codes=("COOLDOWN",), family_code="HAMSTRING_STRETCH"),
        reps_record(UUID(int=3), phase_codes=("COOLDOWN",), family_code="HAMSTRING_STRETCH"),
    ) + tuple(reps_record(UUID(int=index), phase_codes=("MAIN",)) for index in range(4, 14))
    pool = duration_pool(envelope, records)

    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    phases = {item.phase_code for item in spec.exercise_prescriptions}
    assert {"WARMUP", "MAIN", "COOLDOWN"} <= phases


def test_fallback_declines_when_the_pool_has_no_cooldown_candidate() -> None:
    # A plan missing a phase cannot pass integrity validation, so there is no
    # safe fallback to hand back; the request fails closed instead.
    envelope = duration_envelope(requested_duration_minutes=30)
    records = tuple(
        reps_record(UUID(int=index), phase_codes=("WARMUP", "MAIN")) for index in range(1, 11)
    )
    pool = duration_pool(envelope, records)

    request = FallbackRequest.create(
        constraint_envelope=envelope,
        exercise_pool=pool,
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
    )

    assert DeterministicGraphFallbackProvider().generate(request) is None


def test_fallback_still_plans_when_no_reviewed_fitt_range_covers_the_pool() -> None:
    """Golden scenario 5 must hold for the catalog actually promoted today.

    No reviewed range covers any promoted `stable_code`, so a fallback that
    declines without one returns nothing at all and the graph terminates. The
    Recovery ceiling is the approved volume in that case, exactly as it was
    before FITT ranges existed.
    """

    root = make_bundle().root_snapshot
    pool = root.exercise_pool
    # Rebuild rather than copy: the snapshot re-derives and re-checks its own
    # pool_hash, which is the point -- an unmapped pool has to be a real one.
    unmapped_pool = ExercisePoolSnapshot.create(
        catalog_version=pool.catalog_version,
        constraint_envelope_hash=pool.constraint_envelope_hash,
        exercises=tuple(
            record.model_copy(update={"fitt_context": None}) for record in pool.exercises
        ),
        mandatory_exercise_ids=pool.mandatory_exercise_ids,
        vector_ranked_exercise_ids=pool.vector_ranked_exercise_ids,
        retrieval_metadata=pool.retrieval_metadata,
        created_at=pool.created_at,
    )
    provider = DeterministicGraphFallbackProvider()

    spec = provider.generate(
        FallbackRequest.create(
            constraint_envelope=root.constraint_envelope,
            exercise_pool=unmapped_pool,
            fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        )
    )

    assert spec is not None
    ceiling = root.constraint_envelope.recovery_ceiling
    records = {item.exercise_id: item for item in unmapped_pool.exercises}
    reps_prescriptions = [
        prescription
        for prescription in spec.exercise_prescriptions
        if records[prescription.exercise_id].timing_mode_code == "REPS"
    ]
    assert reps_prescriptions, "the pool must still contribute its REPS exercises"
    for prescription in reps_prescriptions:
        assert prescription.repetitions_per_set == ceiling.maximum_repetitions_per_set
        if ceiling.maximum_sets_per_exercise is not None:
            assert prescription.sets <= ceiling.maximum_sets_per_exercise


def test_unmapped_pool_fallback_compiles_and_passes_integrity_validation() -> None:
    """Golden scenario 5, end to end, on a pool no reviewed FITT range covers."""

    root = make_bundle().root_snapshot
    pool = root.exercise_pool
    unmapped_pool = ExercisePoolSnapshot.create(
        catalog_version=pool.catalog_version,
        constraint_envelope_hash=pool.constraint_envelope_hash,
        exercises=tuple(
            record.model_copy(update={"fitt_context": None}) for record in pool.exercises
        ),
        mandatory_exercise_ids=pool.mandatory_exercise_ids,
        vector_ranked_exercise_ids=pool.vector_ranked_exercise_ids,
        retrieval_metadata=pool.retrieval_metadata,
        created_at=pool.created_at,
    )

    outcome = execute_deterministic_fallback(
        DeterministicGraphFallbackProvider(),
        envelope=root.constraint_envelope,
        pool=unmapped_pool,
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )

    assert outcome.compiled_plan is not None
    assert outcome.terminal_result is None
