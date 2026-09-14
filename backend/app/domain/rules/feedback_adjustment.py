"""Deterministic downshift ladder for `difficulty_code=HARD` feedback.

`DOMAIN_RULES.md` 6.1 fixes the order: exercise difficulty, then intensity, then time
allocation. This module answers only "which axis does the next routine lower, and why",
so the decision stays reproducible from stored feedback alone. It selects an axis; it
does not build a plan.

Three properties the callers depend on:

- One axis per adjustment. The policy evaluates the effect through the next feedback, so
  changing two levers at once would make that reading meaningless.
- The time axis never shortens the requested duration. It only allows the compiler to
  settle on the shorter side of the tolerance window that `DOMAIN_RULES.md` 5 already
  approved. `AGENTS.md` 7 forbids anything past that without explicit user input.
- Safety outranks it. An adjustment never re-admits an exercise the SafetyPolicyEngine
  excluded, so callers apply this inside the envelope rather than around it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AdjustmentAxisCode",
    "AdjustmentReasonCode",
    "DifficultyReasonCode",
    "FEEDBACK_ADJUSTMENT_POLICY_VERSION",
    "FeedbackAdjustment",
    "InvalidFeedbackAdjustmentInputError",
    "select_feedback_adjustment",
]

FEEDBACK_ADJUSTMENT_POLICY_VERSION = "feedback-adjustment-policy-v1"


class InvalidFeedbackAdjustmentInputError(ValueError):
    """Raised when the caller passes something the ladder cannot evaluate."""


class DifficultyReasonCode(StrEnum):
    """Why the session felt hard. The user may report both."""

    VOLUME_HIGH = "VOLUME_HIGH"
    MOVEMENT_DIFFICULT = "MOVEMENT_DIFFICULT"


class AdjustmentAxisCode(StrEnum):
    """The single lever the next routine lowers."""

    EXERCISE_DIFFICULTY = "EXERCISE_DIFFICULTY"
    INTENSITY = "INTENSITY"
    TIME_ALLOCATION = "TIME_ALLOCATION"
    NONE = "NONE"


class AdjustmentReasonCode(StrEnum):
    """Machine-readable justification, stored with the decision run."""

    NO_HARD_FEEDBACK = "NO_HARD_FEEDBACK"
    DIFFICULTY_REASONS_MISSING = "DIFFICULTY_REASONS_MISSING"
    MOVEMENT_DIFFICULT_REPORTED = "MOVEMENT_DIFFICULT_REPORTED"
    VOLUME_HIGH_REPORTED = "VOLUME_HIGH_REPORTED"
    BOTH_REPORTED_DIFFICULTY_FIRST = "BOTH_REPORTED_DIFFICULTY_FIRST"
    NO_EASIER_VARIANT_AVAILABLE = "NO_EASIER_VARIANT_AVAILABLE"
    INTENSITY_FLOOR_REACHED = "INTENSITY_FLOOR_REACHED"


@dataclass(frozen=True, slots=True)
class FeedbackAdjustment:
    """The axis to lower next, with the codes that explain the choice."""

    axis_code: AdjustmentAxisCode
    reason_codes: tuple[AdjustmentReasonCode, ...]
    policy_version: str = FEEDBACK_ADJUSTMENT_POLICY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.axis_code, AdjustmentAxisCode):
            raise InvalidFeedbackAdjustmentInputError("axis_code is invalid")
        if not self.reason_codes:
            raise InvalidFeedbackAdjustmentInputError("reason_codes must not be empty")


def select_feedback_adjustment(
    *,
    difficulty_code: str | None,
    reason_codes: frozenset[DifficultyReasonCode],
    easier_variant_available: bool,
    intensity_reducible: bool,
) -> FeedbackAdjustment:
    """Pick the one axis the next routine lowers.

    `easier_variant_available` and `intensity_reducible` are answered by the caller from
    the approved pool and the current ceiling, because this module must not reach into
    the catalog or re-derive safety state.

    Only `HARD` triggers an adjustment. `EASY` does not raise the load: the policy has no
    upshift ladder, and inventing one here would change the plan on an input the product
    never approved for that purpose.
    """

    if difficulty_code != "HARD":
        return FeedbackAdjustment(
            axis_code=AdjustmentAxisCode.NONE,
            reason_codes=(AdjustmentReasonCode.NO_HARD_FEEDBACK,),
        )
    if not reason_codes:
        # ADR-0018 requires a reason with HARD, but the field is additive while clients
        # roll over, so rows written before that exist. Absent input cannot pick an axis,
        # and guessing one would move the plan on evidence the user never gave.
        return FeedbackAdjustment(
            axis_code=AdjustmentAxisCode.NONE,
            reason_codes=(AdjustmentReasonCode.DIFFICULTY_REASONS_MISSING,),
        )
    if any(not isinstance(code, DifficultyReasonCode) for code in reason_codes):
        raise InvalidFeedbackAdjustmentInputError("reason_codes contains an unknown code")

    movement = DifficultyReasonCode.MOVEMENT_DIFFICULT in reason_codes
    volume = DifficultyReasonCode.VOLUME_HIGH in reason_codes

    trail: list[AdjustmentReasonCode] = []
    if movement and volume:
        trail.append(AdjustmentReasonCode.BOTH_REPORTED_DIFFICULTY_FIRST)
    elif movement:
        trail.append(AdjustmentReasonCode.MOVEMENT_DIFFICULT_REPORTED)
    else:
        trail.append(AdjustmentReasonCode.VOLUME_HIGH_REPORTED)

    # Rung 1. Only a movement complaint starts on difficulty; a volume-only complaint is
    # about how much work there was, which the difficulty axis does not answer.
    if movement:
        if easier_variant_available:
            return FeedbackAdjustment(
                axis_code=AdjustmentAxisCode.EXERCISE_DIFFICULTY,
                reason_codes=tuple(trail),
            )
        trail.append(AdjustmentReasonCode.NO_EASIER_VARIANT_AVAILABLE)

    # Rung 2. The policy converts to intensity when difficulty cannot move.
    if intensity_reducible:
        return FeedbackAdjustment(
            axis_code=AdjustmentAxisCode.INTENSITY,
            reason_codes=tuple(trail),
        )
    trail.append(AdjustmentReasonCode.INTENSITY_FLOOR_REACHED)

    # Rung 3. Time allocation is last and stays inside the approved tolerance window.
    return FeedbackAdjustment(
        axis_code=AdjustmentAxisCode.TIME_ALLOCATION,
        reason_codes=tuple(trail),
    )
