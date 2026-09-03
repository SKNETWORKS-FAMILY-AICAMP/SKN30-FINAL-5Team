"""The `HARD` feedback downshift ladder from `DOMAIN_RULES.md` 6.1.

These cover the axis choice itself. Whether an easier variant or a lower intensity is
actually reachable is the caller's question, so it is passed in.
"""

import pytest

from backend.app.domain.rules.feedback_adjustment import (
    AdjustmentAxisCode,
    AdjustmentReasonCode,
    DifficultyReasonCode,
    FeedbackAdjustment,
    InvalidFeedbackAdjustmentInputError,
    select_feedback_adjustment,
)

MOVEMENT = DifficultyReasonCode.MOVEMENT_DIFFICULT
VOLUME = DifficultyReasonCode.VOLUME_HIGH


def _select(
    reasons: frozenset[DifficultyReasonCode],
    *,
    difficulty_code: str | None = "HARD",
    easier_variant_available: bool = True,
    intensity_reducible: bool = True,
) -> FeedbackAdjustment:
    return select_feedback_adjustment(
        difficulty_code=difficulty_code,
        reason_codes=reasons,
        easier_variant_available=easier_variant_available,
        intensity_reducible=intensity_reducible,
    )


@pytest.mark.parametrize("difficulty_code", ["EASY", "APPROPRIATE", None])
def test_only_hard_feedback_adjusts_anything(difficulty_code: str | None) -> None:
    """`EASY` must not raise the load; the policy defines no upshift ladder."""

    result = _select(frozenset(), difficulty_code=difficulty_code)

    assert result.axis_code is AdjustmentAxisCode.NONE
    assert result.reason_codes == (AdjustmentReasonCode.NO_HARD_FEEDBACK,)


def test_movement_only_lowers_exercise_difficulty_first() -> None:
    result = _select(frozenset({MOVEMENT}))

    assert result.axis_code is AdjustmentAxisCode.EXERCISE_DIFFICULTY
    assert result.reason_codes == (AdjustmentReasonCode.MOVEMENT_DIFFICULT_REPORTED,)


def test_volume_only_lowers_intensity_without_touching_difficulty() -> None:
    """A volume complaint is about how much work there was, not how hard the movement is."""

    result = _select(frozenset({VOLUME}))

    assert result.axis_code is AdjustmentAxisCode.INTENSITY
    assert result.reason_codes == (AdjustmentReasonCode.VOLUME_HIGH_REPORTED,)
    assert AdjustmentReasonCode.NO_EASIER_VARIANT_AVAILABLE not in result.reason_codes


def test_both_reported_starts_with_difficulty() -> None:
    result = _select(frozenset({MOVEMENT, VOLUME}))

    assert result.axis_code is AdjustmentAxisCode.EXERCISE_DIFFICULTY
    assert result.reason_codes == (AdjustmentReasonCode.BOTH_REPORTED_DIFFICULTY_FIRST,)


def test_falls_through_to_intensity_when_no_easier_variant_exists() -> None:
    result = _select(frozenset({MOVEMENT}), easier_variant_available=False)

    assert result.axis_code is AdjustmentAxisCode.INTENSITY
    assert result.reason_codes == (
        AdjustmentReasonCode.MOVEMENT_DIFFICULT_REPORTED,
        AdjustmentReasonCode.NO_EASIER_VARIANT_AVAILABLE,
    )


def test_time_allocation_is_the_last_resort() -> None:
    result = _select(
        frozenset({MOVEMENT, VOLUME}),
        easier_variant_available=False,
        intensity_reducible=False,
    )

    assert result.axis_code is AdjustmentAxisCode.TIME_ALLOCATION
    assert result.reason_codes == (
        AdjustmentReasonCode.BOTH_REPORTED_DIFFICULTY_FIRST,
        AdjustmentReasonCode.NO_EASIER_VARIANT_AVAILABLE,
        AdjustmentReasonCode.INTENSITY_FLOOR_REACHED,
    )


def test_only_one_axis_moves_per_adjustment() -> None:
    """The policy evaluates each change through the next feedback, so exactly one axis."""

    for reasons in (frozenset({MOVEMENT}), frozenset({VOLUME}), frozenset({MOVEMENT, VOLUME})):
        for easier in (True, False):
            for reducible in (True, False):
                result = _select(
                    reasons,
                    easier_variant_available=easier,
                    intensity_reducible=reducible,
                )
                assert result.axis_code is not AdjustmentAxisCode.NONE
                assert isinstance(result.axis_code, AdjustmentAxisCode)


def test_hard_without_reasons_makes_no_adjustment() -> None:
    """Clients still post `HARD` alone while the field rolls out; absent input picks nothing."""

    result = _select(frozenset())

    assert result.axis_code is AdjustmentAxisCode.NONE
    assert result.reason_codes == (AdjustmentReasonCode.DIFFICULTY_REASONS_MISSING,)


def test_unknown_reason_codes_are_rejected() -> None:
    with pytest.raises(InvalidFeedbackAdjustmentInputError):
        select_feedback_adjustment(
            difficulty_code="HARD",
            reason_codes=frozenset({"SOMETHING_ELSE"}),  # type: ignore[arg-type]
            easier_variant_available=True,
            intensity_reducible=True,
        )


def test_adjustment_carries_a_policy_version_for_replay() -> None:
    result = _select(frozenset({VOLUME}))

    assert result.policy_version == "feedback-adjustment-policy-v1"
