"""Deterministic, non-medical MET calorie estimates for completed workout blocks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from uuid import UUID

CALORIE_POLICY_VERSION: Final = "met-completed-blocks-v2"
KCAL_DECIMAL_PLACES: Final = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class CompletedBlockMetInput:
    exercise_id: UUID
    exercise_stable_code: str
    met_value: Decimal | None
    planned_seconds: int
    allocated_progress_seconds: int
    catalog_version_code: str | None = None
    met_source_code: str | None = None
    met_source_activity_code: str | None = None
    met_mapping_method_code: str | None = None
    met_review_status_code: str | None = None
    met_policy_version: str | None = None


@dataclass(frozen=True, slots=True)
class CalorieEstimate:
    estimated_calories_burned: float | None
    source_code: str
    policy_version: str | None
    input_snapshot: dict[str, object] | None


def _has_approved_met_provenance(block: CompletedBlockMetInput) -> bool:
    return bool(
        block.met_value is not None
        and block.met_value > 0
        and block.catalog_version_code
        and block.met_source_code
        and block.met_source_activity_code
        and block.met_mapping_method_code
        and block.met_review_status_code == "DOMAIN_APPROVED"
        and block.met_policy_version
    )


def _block_snapshot(block: CompletedBlockMetInput) -> dict[str, object]:
    return {
        "exercise_id": str(block.exercise_id),
        "exercise_stable_code": block.exercise_stable_code,
        "catalog_version_code": block.catalog_version_code,
        "met_value": None if block.met_value is None else str(block.met_value),
        "met_source_code": block.met_source_code,
        "met_source_activity_code": block.met_source_activity_code,
        "met_mapping_method_code": block.met_mapping_method_code,
        "met_review_status_code": block.met_review_status_code,
        "met_policy_version": block.met_policy_version,
        "planned_seconds": block.planned_seconds,
        "allocated_progress_seconds": block.allocated_progress_seconds,
    }


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
        if _has_approved_met_provenance(block) and block.allocated_progress_seconds > 0
    )
    catalog_versions = {block.catalog_version_code for block in usable}
    met_mapping_source_version = (
        next(iter(catalog_versions)) if len(catalog_versions) == 1 else None
    )
    if weight_kg is None or not usable or met_mapping_source_version is None:
        if weight_kg is None:
            reason_code = "WEIGHT_MISSING"
        elif not usable:
            reason_code = "APPROVED_CATALOG_MET_OR_PROGRESS_MISSING"
        else:
            reason_code = "CATALOG_VERSION_MISMATCH"
        return CalorieEstimate(
            None,
            "UNAVAILABLE",
            CALORIE_POLICY_VERSION,
            {
                "calorie_policy_version": CALORIE_POLICY_VERSION,
                "met_mapping_source_version": met_mapping_source_version,
                "availability": "UNAVAILABLE",
                "reason_code": reason_code,
                "weight_kg": None if weight_kg is None else str(weight_kg),
                "completed_blocks": [_block_snapshot(block) for block in completed],
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
            "met_mapping_source_version": met_mapping_source_version,
            "weight_kg": str(weight_kg),
            "completed_blocks": [_block_snapshot(block) for block in usable],
            "rounding": "HALF_UP_1_DECIMAL_KCAL",
        },
    )


__all__ = [
    "CALORIE_POLICY_VERSION",
    "allocate_completed_progress_seconds",
    "CompletedBlockMetInput",
    "CalorieEstimate",
    "estimate_calories",
]
