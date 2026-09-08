from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from backend.app.domain.rules.calories import (
    CompletedBlockMetInput,
    allocate_completed_progress_seconds,
    estimate_calories,
)


def _approved_block(*, met_value: Decimal | None = Decimal("6")) -> CompletedBlockMetInput:
    return CompletedBlockMetInput(
        exercise_id=UUID(int=1),
        exercise_stable_code="deadlift",
        met_value=met_value,
        planned_seconds=600,
        allocated_progress_seconds=600,
        catalog_version_code="integrated-catalog-v2.0.7-final",
        met_source_code="ADULT_COMPENDIUM_PDF_2024",
        met_source_activity_code="02050",
        met_mapping_method_code="DIRECT",
        met_review_status_code="DOMAIN_APPROVED",
        met_policy_version="v2.0.6-met-compendium-direct-similar-1.0.0",
    )


def test_met_calorie_estimate_is_reproducible_from_its_snapshot_inputs() -> None:
    result = estimate_calories(
        weight_kg=Decimal("70"),
        blocks=(_approved_block(),),
    )

    assert result.estimated_calories_burned == 73.5
    assert result.source_code == "MET_ESTIMATE"
    assert result.input_snapshot is not None
    assert result.policy_version == "met-completed-blocks-v2"
    assert result.input_snapshot["met_mapping_source_version"] == "integrated-catalog-v2.0.7-final"
    assert result.input_snapshot["completed_blocks"][0]["allocated_progress_seconds"] == 600
    assert result.input_snapshot["completed_blocks"][0]["met_source_activity_code"] == "02050"


def test_missing_weight_or_met_is_unavailable_without_failing() -> None:
    assert (
        estimate_calories(
            weight_kg=None,
            blocks=(_approved_block(),),
        ).estimated_calories_burned
        is None
    )
    assert (
        estimate_calories(
            weight_kg=Decimal("70"),
            blocks=(_approved_block(met_value=None),),
        ).source_code
        == "UNAVAILABLE"
    )


def test_unapproved_or_incomplete_catalog_met_is_unavailable() -> None:
    unapproved = replace(_approved_block(), met_review_status_code="REVIEW_REQUIRED")

    result = estimate_calories(weight_kg=Decimal("70"), blocks=(unapproved,))

    assert result.source_code == "UNAVAILABLE"
    assert result.input_snapshot is not None
    assert result.input_snapshot["reason_code"] == "APPROVED_CATALOG_MET_OR_PROGRESS_MISSING"


def test_completed_block_progress_allocation_is_repeatable_and_preserves_total() -> None:
    allocation = allocate_completed_progress_seconds(
        total_progress_seconds=101, planned_seconds=(60, 30, 10)
    )

    assert allocation == (61, 30, 10)
    assert sum(allocation) == 101
