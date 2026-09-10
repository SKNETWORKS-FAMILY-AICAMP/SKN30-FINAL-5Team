"""Deterministic plan composition for the scripted evaluation model.

This is the harness's stand-in for what a Training agent would answer, not a
second implementation of the service's planner.  It exists so a scripted model
can hand the real compiler and the real integrity validator a plan that is
either genuinely compliant or deliberately broken in one named way, and so the
difference between those two is the only thing a test result reflects.

Nothing here is authoritative: every plan it produces is still judged by
`validate_plan_integrity`, which is the service's own gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord, ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, ExercisePrescription
from backend.app.domain.agents.v3_duration import prescription_item_duration
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE
from backend.app.domain.rules.plan_shape import (
    MAX_PHASE_EXERCISE_TYPES,
    MAX_PLAN_EXERCISE_TYPES,
)

_PHASE_ORDER: Final[tuple[str, ...]] = ("WARMUP", "MAIN", "COOLDOWN")
_MAX_MAIN_TYPES: Final = MAX_PLAN_EXERCISE_TYPES - sum(MAX_PHASE_EXERCISE_TYPES.values())


class PlanCompositionError(ValueError):
    """Raised when no plan can be composed from the supplied pool."""


@dataclass(frozen=True, slots=True)
class _Block:
    record: ExercisePoolExerciseRecord
    phase_code: str
    sets: int
    repetitions: int

    @property
    def seconds(self) -> int:
        per_set = self.repetitions * (self.record.default_seconds_per_rep or 0)
        rest = max(self.sets - 1, 0) * self.record.default_rest_seconds
        return self.sets * per_set + rest + self.record.default_transition_seconds


def _eligible(
    pool: ExercisePoolSnapshot,
    envelope: ConstraintEnvelope,
    phase_code: str,
) -> tuple[ExercisePoolExerciseRecord, ...]:
    """Return pool records this phase may use, in canonical order."""

    excluded = set(envelope.excluded_exercise_ids)
    allowed_locations = set(envelope.allowed_location_codes)
    return tuple(
        record
        for record in pool.exercises
        if record.exercise_id not in excluded
        and phase_code in record.phase_codes
        and set(record.location_codes) & allowed_locations
        and record.default_seconds_per_rep is not None
    )


def _volume_bounds(
    record: ExercisePoolExerciseRecord, envelope: ConstraintEnvelope
) -> tuple[int, int, int, int]:
    """Return (min_sets, max_sets, min_reps, max_reps) honouring FITT and Recovery."""

    ceiling = envelope.recovery_ceiling
    volume = record.approved_fitt_volume()
    min_sets, max_sets = (volume.min_sets, volume.max_sets) if volume else (1, 3)
    min_reps, max_reps = (volume.min_reps, volume.max_reps) if volume else (8, 12)
    if ceiling.maximum_sets_per_exercise is not None:
        max_sets = min(max_sets, ceiling.maximum_sets_per_exercise)
    if ceiling.maximum_repetitions_per_set is not None:
        max_reps = min(max_reps, ceiling.maximum_repetitions_per_set)
    per_exercise = next(
        (
            item
            for item in ceiling.per_exercise_volume_ceilings
            if item.exercise_id == record.exercise_id
        ),
        None,
    )
    if per_exercise is not None:
        max_sets = min(max_sets, per_exercise.maximum_sets_per_exercise)
        max_reps = min(max_reps, per_exercise.maximum_repetitions_per_set)
    if max_sets < min_sets or max_reps < min_reps:
        raise PlanCompositionError("recovery ceiling leaves no selectable FITT volume")
    return min_sets, max_sets, min_reps, max_reps


def _rest_seconds(record: ExercisePoolExerciseRecord, envelope: ConstraintEnvelope) -> int:
    minimum = envelope.recovery_ceiling.minimum_rest_seconds_between_sets
    if minimum is None:
        return record.default_rest_seconds
    return max(record.default_rest_seconds, minimum)


def _intensity_code(envelope: ConstraintEnvelope) -> str:
    allowed = envelope.recovery_ceiling.allowed_intensity_codes
    if not allowed:
        return "MODERATE"
    return "LOW" if "LOW" in allowed else allowed[0]


def _load_code(envelope: ConstraintEnvelope, record: ExercisePoolExerciseRecord) -> str | None:
    allowed = envelope.recovery_ceiling.allowed_load_codes
    if not allowed:
        return None
    for candidate in record.equipment_codes:
        if candidate in allowed:
            return candidate
    return allowed[0]


def _location_code(envelope: ConstraintEnvelope, record: ExercisePoolExerciseRecord) -> str:
    shared = [code for code in record.location_codes if code in envelope.allowed_location_codes]
    if not shared:
        raise PlanCompositionError("exercise shares no location with the envelope")
    return sorted(shared)[0]


def _support_blocks(
    records: tuple[ExercisePoolExerciseRecord, ...],
    envelope: ConstraintEnvelope,
    phase_code: str,
    *,
    count: int,
) -> list[_Block]:
    blocks: list[_Block] = []
    for record in records[:count]:
        min_sets, _, min_reps, max_reps = _volume_bounds(record, envelope)
        blocks.append(
            _Block(
                record=record,
                phase_code=phase_code,
                sets=min_sets,
                repetitions=min(max_reps, max(min_reps, 12)),
            )
        )
    return blocks


def _main_blocks(
    records: tuple[ExercisePoolExerciseRecord, ...],
    envelope: ConstraintEnvelope,
    *,
    target_seconds: int,
) -> list[_Block]:
    """Fill the main phase toward `target_seconds` without exceeding the tolerance.

    One family contributes one exercise (`MAX_PLAN_EXERCISES_PER_FAMILY`), an
    exercise's blocks may not sum past the Recovery sets ceiling, and no two
    neighbouring main blocks repeat a movement.
    """

    seen_families: set[str] = set()
    candidates: list[ExercisePoolExerciseRecord] = []
    for record in records:
        if record.family_code and record.family_code in seen_families:
            continue
        if record.family_code:
            seen_families.add(record.family_code)
        candidates.append(record)
        if len(candidates) >= _MAX_MAIN_TYPES:
            break
    if not candidates:
        raise PlanCompositionError("pool offers no main-phase candidate")

    blocks: list[_Block] = []
    total = 0
    sets_used: dict[UUID, int] = {}
    mandatory = [
        record for record in candidates if record.exercise_id in envelope.mandatory_exercise_ids
    ]
    ordered = mandatory + [record for record in candidates if record not in mandatory]

    # Round-robin the candidates so a repeat never lands next to itself and the
    # mandatory movements are placed first.
    index = 0
    while index < len(ordered) * 4:
        record = ordered[index % len(ordered)]
        index += 1
        min_sets, max_sets, min_reps, max_reps = _volume_bounds(record, envelope)
        remaining_sets = max_sets - sets_used.get(record.exercise_id, 0)
        if remaining_sets < min_sets:
            continue
        if blocks and blocks[-1].record.exercise_id == record.exercise_id:
            continue
        chosen: _Block | None = None
        for sets in range(min(max_sets, remaining_sets), min_sets - 1, -1):
            for reps in range(max_reps, min_reps - 1, -1):
                block = _Block(record=record, phase_code="MAIN", sets=sets, repetitions=reps)
                if total + block.seconds <= target_seconds + DURATION_TOLERANCE_SECONDS:
                    chosen = block
                    break
            if chosen is not None:
                break
        if chosen is None:
            continue
        blocks.append(chosen)
        sets_used[record.exercise_id] = sets_used.get(record.exercise_id, 0) + chosen.sets
        total += chosen.seconds
        if total >= target_seconds - DURATION_TOLERANCE_SECONDS:
            break

    if not blocks:
        raise PlanCompositionError("no main block fits inside the requested duration")
    return blocks


def _prescription(
    block: _Block, envelope: ConstraintEnvelope, sequence: int
) -> ExercisePrescription:
    return ExercisePrescription(
        exercise_id=block.record.exercise_id,
        sequence=sequence,
        phase_code=block.phase_code,  # type: ignore[arg-type]
        sets=block.sets,
        repetitions_per_set=block.repetitions,
        work_seconds_per_set=None,
        rest_seconds_between_sets=_rest_seconds(block.record, envelope),
        transition_seconds=block.record.default_transition_seconds,
        intensity_code=_intensity_code(envelope),
        load_code=_load_code(envelope, block.record),
        location_code=_location_code(envelope, block.record),
        equipment_codes=(),
    )


def compose_prescriptions(
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
) -> tuple[ExercisePrescription, ...]:
    """Compose a compliant WARMUP -> MAIN -> COOLDOWN plan for this envelope."""

    warmup_records = _eligible(pool, envelope, "WARMUP")
    main_records = _eligible(pool, envelope, "MAIN")
    cooldown_records = _eligible(pool, envelope, "COOLDOWN")
    if not warmup_records or not main_records or not cooldown_records:
        raise PlanCompositionError("pool cannot cover warmup, main and cooldown")

    target_seconds = envelope.requested_duration_minutes * SECONDS_PER_MINUTE
    support_count = 2 if target_seconds >= 20 * SECONDS_PER_MINUTE else 1
    warmup = _support_blocks(
        warmup_records, envelope, "WARMUP", count=min(support_count, len(warmup_records))
    )
    cooldown = _support_blocks(
        cooldown_records, envelope, "COOLDOWN", count=min(support_count, len(cooldown_records))
    )
    support_seconds = sum(block.seconds for block in warmup + cooldown)
    main = _main_blocks(
        main_records, envelope, target_seconds=max(0, target_seconds - support_seconds)
    )

    blocks = warmup + main + cooldown
    return tuple(
        _prescription(block, envelope, sequence) for sequence, block in enumerate(blocks, start=1)
    )


def prescriptions_duration_seconds(
    prescriptions: tuple[ExercisePrescription, ...],
    pool: ExercisePoolSnapshot,
) -> int:
    """Time a plan the way the compiler does, from the catalog timing basis."""

    records = {record.exercise_id: record for record in pool.exercises}
    return sum(
        prescription_item_duration(item, records[item.exercise_id]).estimated_item_seconds
        for item in prescriptions
    )


def resequence(
    prescriptions: tuple[ExercisePrescription, ...],
) -> tuple[ExercisePrescription, ...]:
    """Renumber prescriptions so the contiguous-sequence contract still holds."""

    return tuple(
        item.model_copy(update={"sequence": index})
        for index, item in enumerate(prescriptions, start=1)
    )


__all__ = [
    "PlanCompositionError",
    "compose_prescriptions",
    "prescriptions_duration_seconds",
    "resequence",
]
