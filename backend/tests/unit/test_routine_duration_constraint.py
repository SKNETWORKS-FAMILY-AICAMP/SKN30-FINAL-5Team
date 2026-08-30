"""The routine day duration CHECK must encode the approved tolerance window.

The routine service composes a plan inside ``DURATION_TOLERANCE_SECONDS`` when
the eligible pool cannot hit the requested duration exactly (AGENTS.md section
7). Migration 0005 required exact equality, so such a plan was built and then
rejected on persist. These tests pin the constraint to the domain tolerance and
check both edges of the window without needing PostgreSQL.
"""

import re
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.app.db.models.routine import RoutineDay
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS

CONSTRAINT_NAME = "ck_routine_days_duration_tolerance"


def _constraint_sqltext() -> str:
    for constraint in RoutineDay.__table__.constraints:
        if constraint.name == CONSTRAINT_NAME:
            return str(constraint.sqltext)
    raise AssertionError(f"{CONSTRAINT_NAME} is missing from the RoutineDay model")


def _insert(connection: Connection, *, requested_minutes: int, estimated_seconds: int) -> None:
    connection.execute(
        text(
            "INSERT INTO routine_day_duration (requested_duration_minutes, "
            "estimated_duration_seconds) VALUES (:requested, :estimated)"
        ),
        {"requested": requested_minutes, "estimated": estimated_seconds},
    )


@pytest.fixture(name="connection")
def _connection() -> Iterator[Connection]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        connection.execute(
            text(
                "CREATE TABLE routine_day_duration ("
                "  requested_duration_minutes INTEGER NOT NULL,"
                "  estimated_duration_seconds INTEGER NOT NULL,"
                f"  CONSTRAINT {CONSTRAINT_NAME} CHECK ({_constraint_sqltext()})"
                ")"
            )
        )
        yield connection
    engine.dispose()


def test_constraint_encodes_the_domain_tolerance() -> None:
    """A literal in the model must not drift from the duration contract."""
    bounds = {int(value) for value in re.findall(r"\d+", _constraint_sqltext())}

    assert DURATION_TOLERANCE_SECONDS in bounds


def test_exact_match_is_still_accepted(connection: Connection) -> None:
    _insert(connection, requested_minutes=30, estimated_seconds=1800)


@pytest.mark.parametrize("delta", [DURATION_TOLERANCE_SECONDS, -DURATION_TOLERANCE_SECONDS, 55])
def test_plan_inside_the_window_is_accepted(connection: Connection, delta: int) -> None:
    """55 is the delta the routine service produces for a 9 minute request."""
    _insert(connection, requested_minutes=30, estimated_seconds=1800 + delta)


@pytest.mark.parametrize(
    "delta", [DURATION_TOLERANCE_SECONDS + 1, -(DURATION_TOLERANCE_SECONDS + 1)]
)
def test_plan_outside_the_window_is_rejected(connection: Connection, delta: int) -> None:
    """The allowance is bounded; it never silently shortens an impossible request."""
    with pytest.raises(IntegrityError):
        _insert(connection, requested_minutes=30, estimated_seconds=1800 + delta)
