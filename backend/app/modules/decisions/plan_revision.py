"""Deterministic rules for a user's own edit of the day's plan.

`DOMAIN_RULES.md` 11.2 allows two edits and bounds both:

- set and repetition counts, which are exempt from the requested-duration check and
  nothing else (ADR-0018 D4). The user's explicit input outranks the time preference;
  the safety exclusions, the approved pool and the catalog timing basis do not move.
- exercise order, but only inside a phase (ADR-0018 D5), and with the whole sequence
  renumbered from 1 afterwards.

Everything here is pure: no session, no repository, no clock. The caller supplies the
current plan and the execution state, and gets back either the revised items or a machine
code saying why the edit is refused. Timing comes from the catalog basis the caller passes
in rather than from arithmetic on the previous numbers, so an edit cannot drift the plan's
measured duration away from what the reviewed data says the work costs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

PLAN_REVISION_POLICY_VERSION = "plan-revision-policy-v1"


class PlanRevisionFailureCode(StrEnum):
    """Stable codes the API returns; each one names a rule, not an implementation."""

    PLAN_ITEM_NOT_FOUND = "PLAN_ITEM_NOT_FOUND"
    PLAN_NOT_EDITABLE = "PLAN_NOT_EDITABLE"
    REPETITIONS_NOT_APPLICABLE = "REPETITIONS_NOT_APPLICABLE"
    REPETITIONS_REQUIRED = "REPETITIONS_REQUIRED"
    TIMING_BASIS_UNAVAILABLE = "TIMING_BASIS_UNAVAILABLE"
    ORDER_ITEMS_MISMATCH = "ORDER_ITEMS_MISMATCH"
    ORDER_CROSSES_PHASE = "ORDER_CROSSES_PHASE"
    COMPLETED_ITEM_NOT_REORDERABLE = "COMPLETED_ITEM_NOT_REORDERABLE"


class PlanRevisionError(Exception):
    """Raised with one stable code so the API never has to interpret a message."""

    def __init__(self, code: PlanRevisionFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class PlanRevisionItem:
    """One plan item as the edit sees it: its effective values plus its timing basis.

    ``seconds_per_rep`` and ``default_work_seconds`` are the reviewed catalog values for
    the exercise. Exactly one of them is set, which is what makes an item repetition-based
    or duration-based; the check constraint on ``exercises`` already guarantees that.
    """

    plan_item_id: UUID
    sequence: int
    phase_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    rest_seconds_per_set: int
    transition_seconds: int
    seconds_per_rep: int | None
    default_work_seconds: int | None

    @property
    def work_seconds(self) -> int:
        per_set = self.work_seconds_per_set
        if per_set is None:
            raise PlanRevisionError(PlanRevisionFailureCode.TIMING_BASIS_UNAVAILABLE)
        return self.sets * per_set

    @property
    def rest_seconds(self) -> int:
        return max(self.sets - 1, 0) * self.rest_seconds_per_set

    @property
    def estimated_item_seconds(self) -> int:
        return self.work_seconds + self.rest_seconds + self.transition_seconds


def plan_estimated_duration_seconds(
    items: Sequence[PlanRevisionItem],
    *,
    setup_seconds: int,
    warmup_seconds: int,
    cooldown_seconds: int,
) -> int:
    """Total the plan exactly the way `domain/rules/duration.py` totals one."""

    return (
        setup_seconds
        + warmup_seconds
        + sum(item.estimated_item_seconds for item in items)
        + cooldown_seconds
    )


def apply_set_repetition_edit(
    items: Sequence[PlanRevisionItem],
    *,
    plan_item_id: UUID,
    sets: int,
    reps: int | None,
) -> tuple[PlanRevisionItem, ...]:
    """Return the plan with one item's volume replaced by the user's own numbers.

    A repetition-based item recomputes its per-set work from the catalog's seconds-per-rep
    basis, so the plan's measured duration still reflects reviewed data rather than a
    number the client sent. A duration-based item has no repetition count to change, and
    the request is refused rather than silently ignored: accepting it would store a plan
    that does not match what was asked for.
    """

    target = _require_item(items, plan_item_id)

    if target.reps is None:
        if reps is not None:
            raise PlanRevisionError(PlanRevisionFailureCode.REPETITIONS_NOT_APPLICABLE)
        if target.work_seconds_per_set is None:
            raise PlanRevisionError(PlanRevisionFailureCode.TIMING_BASIS_UNAVAILABLE)
        edited = replace(target, sets=sets)
    else:
        if reps is None:
            raise PlanRevisionError(PlanRevisionFailureCode.REPETITIONS_REQUIRED)
        if target.seconds_per_rep is None:
            raise PlanRevisionError(PlanRevisionFailureCode.TIMING_BASIS_UNAVAILABLE)
        edited = replace(
            target,
            sets=sets,
            reps=reps,
            work_seconds_per_set=reps * target.seconds_per_rep,
        )

    return tuple(edited if item.plan_item_id == plan_item_id else item for item in items)


def apply_order_edit(
    items: Sequence[PlanRevisionItem],
    *,
    ordered_plan_item_ids: Sequence[UUID],
    completed_plan_item_ids: frozenset[UUID],
) -> tuple[PlanRevisionItem, ...]:
    """Return the plan reordered, then renumbered from 1.

    Before the session starts nothing is completed, so the request carries the whole plan.
    Once the user has finished blocks, those blocks are history: they keep the positions
    they were performed in and the request carries only what is left. Sending a completed
    item is refused rather than ignored, because a client that thinks it moved a finished
    block would render an order the server did not store.

    The phase check is positional. A reorder is legal exactly when the phase at every
    position is unchanged, which is `WARMUP`/`MAIN`/`COOLDOWN` containment (ADR-0018 D5)
    and the phase order itself in one comparison.
    """

    by_id = {item.plan_item_id: item for item in items}
    requested = list(ordered_plan_item_ids)
    if len(set(requested)) != len(requested):
        raise PlanRevisionError(PlanRevisionFailureCode.ORDER_ITEMS_MISMATCH)
    unknown = set(requested) - set(by_id)
    if unknown:
        raise PlanRevisionError(PlanRevisionFailureCode.PLAN_ITEM_NOT_FOUND)
    if set(requested) & completed_plan_item_ids:
        raise PlanRevisionError(PlanRevisionFailureCode.COMPLETED_ITEM_NOT_REORDERABLE)

    current = sorted(items, key=lambda item: item.sequence)
    movable = [item for item in current if item.plan_item_id not in completed_plan_item_ids]
    if {item.plan_item_id for item in movable} != set(requested):
        # Reordering a subset would leave the server guessing where the rest belong.
        raise PlanRevisionError(PlanRevisionFailureCode.ORDER_ITEMS_MISMATCH)

    queue = iter(requested)
    reordered = [
        current[index]
        if current[index].plan_item_id in completed_plan_item_ids
        else by_id[next(queue)]
        for index in range(len(current))
    ]
    if [item.phase_code for item in reordered] != [item.phase_code for item in current]:
        raise PlanRevisionError(PlanRevisionFailureCode.ORDER_CROSSES_PHASE)

    return tuple(
        replace(item, sequence=position) for position, item in enumerate(reordered, start=1)
    )


def _require_item(items: Sequence[PlanRevisionItem], plan_item_id: UUID) -> PlanRevisionItem:
    target = next((item for item in items if item.plan_item_id == plan_item_id), None)
    if target is None:
        raise PlanRevisionError(PlanRevisionFailureCode.PLAN_ITEM_NOT_FOUND)
    return target


__all__ = [
    "PLAN_REVISION_POLICY_VERSION",
    "PlanRevisionError",
    "PlanRevisionFailureCode",
    "PlanRevisionItem",
    "apply_order_edit",
    "apply_set_repetition_edit",
    "plan_estimated_duration_seconds",
]
