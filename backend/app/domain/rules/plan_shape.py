"""Deterministic session-shape rules shared by the legacy and V3 planners.

A session is a workout, not an inventory. These bounds were already enforced by
the base-routine planner in `backend.app.modules.routines.service`; the V3 path
inherited neither of them, so an authoritative V3 plan could hand the user a
flat twelve-exercise list with no preparation or settling work. Keeping the
numbers here means both planners answer to the same reviewed shape.
"""

from collections.abc import Iterable, Sequence
from typing import Final, Literal

PLAN_SHAPE_RULE_VERSION: Final = "1.2.0"

PhaseCode = Literal["WARMUP", "MAIN", "COOLDOWN"]

# Preparation comes first and settling comes last.
PLAN_PHASE_ORDER: Final[tuple[PhaseCode, ...]] = ("WARMUP", "MAIN", "COOLDOWN")

# Distinct exercises in one session, counted per exercise rather than per block:
# splitting one movement across two blocks is a way to shape a session, not a
# licence to hand the user twelve different movements.
MAX_PLAN_EXERCISE_TYPES: Final = 10

# Warmup and cooldown prepare and settle the body; they do not absorb leftover
# minutes, so each keeps a small reviewed share of the type budget.
MAX_PHASE_EXERCISE_TYPES: Final[dict[PhaseCode, int]] = {
    "WARMUP": 2,
    "COOLDOWN": 2,
}

# MAIN may reuse a movement to fill a longer requested session, but only after
# other MAIN candidates have had a chance to appear. The finite block cap keeps
# a small approved pool from becoming an unbounded loop. WARMUP and COOLDOWN
# remain one block per exercise, and neighbouring MAIN blocks must differ.
MAX_MAIN_BLOCKS_PER_EXERCISE: Final = 10

# Near-identical movements share a family code in the reviewed catalog: the three
# GOOD_MORNING variants differ by the implement they use, not by what they train.
# Listing all three back to back reads as padding rather than variety, and it
# spends the session's exercise budget without broadening it, so one session
# takes at most one exercise from a family.
MAX_PLAN_EXERCISES_PER_FAMILY: Final = 1


def families_over_budget(
    exercises: Iterable[tuple[object, str | None]],
) -> tuple[str, ...]:
    """Return the family codes covering more than one distinct exercise.

    Takes ``(exercise_id, family_code)`` pairs and counts distinct exercises, not
    blocks: MAIN is allowed to repeat one movement to fill a longer session, which
    ``MAX_MAIN_BLOCKS_PER_EXERCISE`` already bounds. A missing family code is not a
    group -- the catalog leaves it unset for exercises that belong to no family,
    so those must never be collapsed together.
    """

    by_family: dict[str, set[object]] = {}
    for exercise_id, family_code in exercises:
        if family_code:
            by_family.setdefault(family_code, set()).add(exercise_id)
    return tuple(
        sorted(
            code
            for code, exercise_ids in by_family.items()
            if len(exercise_ids) > MAX_PLAN_EXERCISES_PER_FAMILY
        )
    )


def has_consecutive_main_repetition(
    blocks: Sequence[tuple[object, PhaseCode]],
) -> bool:
    """Return whether equal exercise IDs occupy neighbouring MAIN blocks."""

    return any(
        previous_id == current_id and previous_phase == current_phase == "MAIN"
        for (previous_id, previous_phase), (current_id, current_phase) in zip(
            blocks, blocks[1:], strict=False
        )
    )


def phase_rank(phase_code: str) -> int:
    """Sort key placing WARMUP before MAIN before COOLDOWN."""

    return PLAN_PHASE_ORDER.index(phase_code)


__all__ = [
    "MAX_PHASE_EXERCISE_TYPES",
    "MAX_PLAN_EXERCISES_PER_FAMILY",
    "MAX_MAIN_BLOCKS_PER_EXERCISE",
    "MAX_PLAN_EXERCISE_TYPES",
    "PLAN_PHASE_ORDER",
    "PLAN_SHAPE_RULE_VERSION",
    "PhaseCode",
    "families_over_budget",
    "has_consecutive_main_repetition",
    "phase_rank",
]
