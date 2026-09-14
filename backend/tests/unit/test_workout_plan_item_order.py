"""Every read of a plan in running order must honour the user's own reorder.

A reorder writes `user_sequence` and leaves the decision's `sequence` untouched,
so a query that orders by `sequence` alone silently returns the pre-reorder
order. `get_session_state` did exactly that, and because its
`next_pending_plan_item_id` is what moves the client to the next block, the
client landed on a block it did not consider next and then refused to complete
it: after a reorder the moved blocks could not be finished at all.

The expression now lives in one helper. These tests keep it that way, because
the failure is invisible until someone reorders a routine and then tries to run
it -- there is nothing wrong-looking about `.order_by(PlanItem.sequence)` on its
own.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend.app.db.repositories import workout as workout_repository

_SOURCE = Path(inspect.getfile(workout_repository)).read_text(encoding="utf-8")


def _order_by_arguments() -> list[ast.expr]:
    """Every argument passed to an `.order_by(...)` call in the module."""

    tree = ast.parse(_SOURCE)
    arguments: list[ast.expr] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "order_by"
        ):
            arguments.extend(node.args)
    return arguments


def _mentions_plan_item_sequence(node: ast.expr) -> bool:
    return any(
        isinstance(inner, ast.Attribute)
        and inner.attr in {"sequence", "user_sequence"}
        and isinstance(inner.value, ast.Name)
        and inner.value.id == "PlanItem"
        for inner in ast.walk(node)
    )


def test_no_query_orders_plan_items_by_the_raw_decision_sequence() -> None:
    offenders = [
        ast.unparse(argument)
        for argument in _order_by_arguments()
        if _mentions_plan_item_sequence(argument) and ast.unparse(argument) != "_plan_item_order()"
    ]

    assert offenders == [], (
        "order plan items with _plan_item_order() so a user's reorder is honoured; "
        f"found {offenders}"
    )


def test_the_shared_order_coalesces_the_user_sequence_over_the_decision_one() -> None:
    tree = ast.parse(_SOURCE)
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_plan_item_order"
    )
    body = ast.unparse(helper)

    assert "coalesce" in body
    # The user's own order wins; the decision's is only the fallback.
    assert body.index("PlanItem.user_sequence") < body.index("PlanItem.sequence")


def test_every_plan_item_ordering_goes_through_the_helper() -> None:
    # Guards the other direction: the helper must actually be the thing queries
    # use, not merely present alongside hand-written orderings.
    assert _SOURCE.count("_plan_item_order()") >= 4
