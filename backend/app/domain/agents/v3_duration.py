"""Deterministic V3 plan duration derived from the approved catalog timing basis.

The V1/V2 path already times a plan from reviewed catalog values
(``backend/app/db/repositories/decision.py``). The V3 path asserted its duration
instead of computing it, so a plan could claim the requested time while
prescribing a fraction of it. This module applies the same arithmetic to V3
prescriptions so both paths agree on what a plan actually costs.

Timing inputs come from the catalog record, never from the model: the exercises
table constrains ``default_transition_seconds`` and pairs each timing mode with
its seconds basis, so those values are reviewed data. Sets, repetitions and rest
come from the prescription because they are the choices the plan is making.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord
from backend.app.domain.agents.v3_contracts import ExercisePrescription
from backend.app.domain.rules.duration import SECONDS_PER_MINUTE, PlanItemDuration

# A pool this small stops offering variety even for a short session; a pool this
# large inflates the agent payload and the measured provider latency without
# improving the plan, because a plan repeats sets rather than adding movements.
POOL_SIZE_MINIMUM = 8
POOL_SIZE_MAXIMUM = 40


class TimingBasisUnavailableError(ValueError):
    """Raised when a prescription cannot be timed from its catalog record."""


def work_seconds_per_set(
    prescription: ExercisePrescription,
    exercise: ExercisePoolExerciseRecord,
) -> int:
    """Return one set's work seconds using the prescription's own timing mode."""

    if prescription.work_seconds_per_set is not None:
        return prescription.work_seconds_per_set
    if prescription.repetitions_per_set is None:
        # The prescription contract already requires one of the two, so reaching
        # here means the contract was bypassed rather than that data is missing.
        raise TimingBasisUnavailableError("prescription declares neither repetitions nor seconds")
    if exercise.default_seconds_per_rep is None:
        raise TimingBasisUnavailableError(
            "repetition-based prescription requires a catalog seconds-per-rep basis"
        )
    return prescription.repetitions_per_set * exercise.default_seconds_per_rep


def prescription_item_duration(
    prescription: ExercisePrescription,
    exercise: ExercisePoolExerciseRecord,
) -> PlanItemDuration:
    """Time one prescribed exercise the way the deterministic path times a plan item."""

    per_set = work_seconds_per_set(prescription, exercise)
    return PlanItemDuration(
        work_seconds=prescription.sets * per_set,
        rest_seconds=max(prescription.sets - 1, 0) * prescription.rest_seconds_between_sets,
        transition_seconds=exercise.default_transition_seconds,
    )


def plan_duration_seconds(
    prescriptions: Iterable[ExercisePrescription],
    exercises: Mapping[UUID, ExercisePoolExerciseRecord],
) -> int:
    """Sum every prescribed exercise without rounding."""

    total = 0
    for prescription in prescriptions:
        exercise = exercises.get(prescription.exercise_id)
        if exercise is None:
            raise TimingBasisUnavailableError(
                "prescription references an exercise outside the pool"
            )
        total += prescription_item_duration(prescription, exercise).estimated_item_seconds
    return total


def typical_exercise_seconds(exercise: ExercisePoolExerciseRecord) -> int:
    """Estimate one exercise at its catalog defaults, for sizing an exercise pool.

    This is a planning estimate rather than a plan measurement: it assumes a
    single set so that pool sizing stays conservative and never returns fewer
    candidates than a plan could need.
    """

    work = exercise.default_work_seconds or exercise.default_seconds_per_rep or 0
    return work + exercise.default_rest_seconds + exercise.default_transition_seconds


def pool_size_for_duration(
    *,
    requested_duration_minutes: int,
    exercises: Sequence[ExercisePoolExerciseRecord],
) -> int:
    """Size the candidate pool from the time the plan has to fill.

    A fixed pool size cannot serve both a twenty-minute and a sixty-minute
    request: the short one gets needless candidates and the long one cannot
    reach its target however the agents prescribe. Sizing from the requested
    duration keeps the pool proportional to the work it has to cover.
    """

    if not exercises:
        raise TimingBasisUnavailableError("cannot size a pool without eligible exercises")
    target_seconds = requested_duration_minutes * SECONDS_PER_MINUTE
    typical = [typical_exercise_seconds(item) for item in exercises]
    average_seconds = max(1, sum(typical) // len(typical))
    needed = -(-target_seconds // average_seconds)
    bounded = max(POOL_SIZE_MINIMUM, min(needed, POOL_SIZE_MAXIMUM))
    return min(bounded, len(exercises))


__all__ = [
    "POOL_SIZE_MAXIMUM",
    "POOL_SIZE_MINIMUM",
    "TimingBasisUnavailableError",
    "plan_duration_seconds",
    "pool_size_for_duration",
    "prescription_item_duration",
    "typical_exercise_seconds",
    "work_seconds_per_set",
]
