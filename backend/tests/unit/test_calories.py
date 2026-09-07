from decimal import Decimal
from uuid import UUID

from backend.app.domain.rules.calories import (
    CompletedBlockMetInput,
    allocate_completed_progress_seconds,
    estimate_calories,
)


def test_met_calorie_estimate_is_reproducible_from_its_snapshot_inputs() -> None:
    result = estimate_calories(
        weight_kg=Decimal("70"),
        blocks=(CompletedBlockMetInput(UUID(int=1), "deadlift", Decimal("6"), 600, 600),),
    )

    assert result.estimated_calories_burned == 73.5
    assert result.source_code == "MET_ESTIMATE"
    assert result.input_snapshot is not None
    assert result.input_snapshot["completed_blocks"][0]["allocated_progress_seconds"] == 600


def test_missing_weight_or_met_is_unavailable_without_failing() -> None:
    assert (
        estimate_calories(
            weight_kg=None,
            blocks=(CompletedBlockMetInput(UUID(int=1), "deadlift", Decimal("6"), 600, 600),),
        ).estimated_calories_burned
        is None
    )
    assert (
        estimate_calories(
            weight_kg=Decimal("70"),
            blocks=(CompletedBlockMetInput(UUID(int=1), "unknown", None, 600, 600),),
        ).source_code
        == "UNAVAILABLE"
    )


def test_completed_block_progress_allocation_is_repeatable_and_preserves_total() -> None:
    allocation = allocate_completed_progress_seconds(
        total_progress_seconds=101, planned_seconds=(60, 30, 10)
    )

    assert allocation == (61, 30, 10)
    assert sum(allocation) == 101
