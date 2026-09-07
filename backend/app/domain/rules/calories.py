"""Deterministic, non-medical MET calorie estimates for completed workout blocks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from uuid import UUID

CALORIE_POLICY_VERSION: Final = "met-completed-blocks-v1"
MET_MAPPING_SOURCE_VERSION: Final = "exercise-met-mapping-v0.1.0"
KCAL_DECIMAL_PLACES: Final = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class CompletedBlockMetInput:
    exercise_id: UUID
    exercise_stable_code: str
    met_value: Decimal | None
    planned_seconds: int
    allocated_progress_seconds: int


@dataclass(frozen=True, slots=True)
class CalorieEstimate:
    estimated_calories_burned: float | None
    source_code: str
    policy_version: str | None
    input_snapshot: dict[str, object] | None


def allocate_completed_progress_seconds(
    *, total_progress_seconds: int, planned_seconds: Sequence[int]
) -> tuple[int, ...]:
    """Allocate recorded exercise progress to officially completed blocks.

    The execution record deliberately stores session-level progress, not a timer
    sample for each block.  This deterministic proportional allocation therefore
    uses the prescribed effective block durations and records every input in the
    resulting snapshot.  It never treats elapsed wall-clock time as exercise time.
    """

    if total_progress_seconds <= 0 or not planned_seconds:
        return tuple(0 for _ in planned_seconds)
    weights = tuple(max(0, seconds) for seconds in planned_seconds)
    total_weight = sum(weights)
    if total_weight == 0:
        return tuple(0 for _ in weights)
    shares = tuple(total_progress_seconds * weight for weight in weights)
    allocated = [share // total_weight for share in shares]
    remaining = total_progress_seconds - sum(allocated)
    # Largest-remainder allocation, breaking ties by plan sequence (the input
    # order). This makes the allocation replayable without a clock sample.
    for index in sorted(
        range(len(shares)), key=lambda value: (-(shares[value] % total_weight), value)
    )[:remaining]:
        allocated[index] += 1
    return tuple(allocated)


def estimate_calories(
    *,
    weight_kg: Decimal | None,
    blocks: Iterable[CompletedBlockMetInput],
) -> CalorieEstimate:
    """Estimate kcal from approved MET, weight, and non-paused completed-block time.

    The standard MET conversion uses ``MET × 3.5 × kg / 200 × minutes``. Missing
    weight or a usable approved mapping is represented as unavailable, never as a
    made-up default body weight or a failed session completion.
    """

    completed = tuple(blocks)
    usable = tuple(
        block
        for block in completed
        if block.met_value is not None and block.allocated_progress_seconds > 0
    )
    if weight_kg is None or not usable:
        reason_code = "WEIGHT_MISSING" if weight_kg is None else "MET_MAPPING_OR_PROGRESS_MISSING"
        return CalorieEstimate(
            None,
            "UNAVAILABLE",
            CALORIE_POLICY_VERSION,
            {
                "calorie_policy_version": CALORIE_POLICY_VERSION,
                "met_mapping_source_version": MET_MAPPING_SOURCE_VERSION,
                "availability": "UNAVAILABLE",
                "reason_code": reason_code,
                "weight_kg": None if weight_kg is None else str(weight_kg),
                "completed_blocks": [
                    {
                        "exercise_id": str(block.exercise_id),
                        "exercise_stable_code": block.exercise_stable_code,
                        "met_value": None if block.met_value is None else str(block.met_value),
                        "planned_seconds": block.planned_seconds,
                        "allocated_progress_seconds": block.allocated_progress_seconds,
                    }
                    for block in completed
                ],
                "rounding": "HALF_UP_1_DECIMAL_KCAL",
            },
        )
    assert weight_kg is not None
    raw_kcal = Decimal("0")
    for block in usable:
        assert block.met_value is not None
        raw_kcal += (
            block.met_value
            * Decimal("3.5")
            * weight_kg
            / Decimal("200")
            * Decimal(block.allocated_progress_seconds)
            / Decimal("60")
        )
    rounded = raw_kcal.quantize(KCAL_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    return CalorieEstimate(
        estimated_calories_burned=float(rounded),
        source_code="MET_ESTIMATE",
        policy_version=CALORIE_POLICY_VERSION,
        input_snapshot={
            "calorie_policy_version": CALORIE_POLICY_VERSION,
            "met_mapping_source_version": MET_MAPPING_SOURCE_VERSION,
            "weight_kg": str(weight_kg),
            "completed_blocks": [
                {
                    "exercise_id": str(block.exercise_id),
                    "exercise_stable_code": block.exercise_stable_code,
                    "met_value": str(block.met_value),
                    "planned_seconds": block.planned_seconds,
                    "allocated_progress_seconds": block.allocated_progress_seconds,
                }
                for block in usable
            ],
            "rounding": "HALF_UP_1_DECIMAL_KCAL",
        },
    )


__all__ = [
    "CALORIE_POLICY_VERSION",
    "allocate_completed_progress_seconds",
    "CompletedBlockMetInput",
    "CalorieEstimate",
    "MET_MAPPING_SOURCE_VERSION",
    "estimate_calories",
]
