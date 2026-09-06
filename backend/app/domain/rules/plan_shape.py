"""Deterministic session-shape rules shared by the legacy and V3 planners.

A session is a workout, not an inventory. These bounds were already enforced by
the base-routine planner in `backend.app.modules.routines.service`; the V3 path
inherited neither of them, so an authoritative V3 plan could hand the user a
flat twelve-exercise list with no preparation or settling work. Keeping the
numbers here means both planners answer to the same reviewed shape.
"""

from typing import Final, Literal

PLAN_SHAPE_RULE_VERSION: Final = "1.0.0"

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


def phase_rank(phase_code: str) -> int:
    """Sort key placing WARMUP before MAIN before COOLDOWN."""

    return PLAN_PHASE_ORDER.index(phase_code)


__all__ = [
    "MAX_PHASE_EXERCISE_TYPES",
    "MAX_PLAN_EXERCISE_TYPES",
    "PLAN_PHASE_ORDER",
    "PLAN_SHAPE_RULE_VERSION",
    "PhaseCode",
    "phase_rank",
]
