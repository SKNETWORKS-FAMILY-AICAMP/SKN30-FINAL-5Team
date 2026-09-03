"""The latest difficulty feedback has to reach the decision snapshot.

Before ADR-0018 the feedback stopped inside the workouts module, so a decision could not
be replayed against the input that was supposed to shape it. The snapshot is the only
evidence a past decision is reproducible from (`AGENTS.md` 12), so the key is asserted
here rather than left to the repository integration test.
"""

from datetime import date
from uuid import uuid4

from backend.app.modules.decisions.context import DecisionContext

LOCAL_DATE = date(2026, 8, 14)
# Fixed so two contexts differ only by the field under test.
CONTEXT_ID = uuid4()


def _context(
    *,
    difficulty_code: str | None = None,
    reason_codes: tuple[str, ...] = (),
) -> DecisionContext:
    return DecisionContext(
        LOCAL_DATE,
        CONTEXT_ID,
        1,
        "LOW",
        30,
        "PROFILE",
        "HOME",
        None,
        None,
        None,
        (),
        (),
        30,
        "GENERAL_FITNESS",
        "BEGINNER",
        (),
        (),
        latest_difficulty_code=difficulty_code,
        latest_difficulty_reason_codes=reason_codes,
    )


def test_snapshot_always_carries_the_feedback_key() -> None:
    """Present even with no feedback, so a replay never has to guess why it is absent."""

    snapshot = _context().snapshot()

    assert snapshot["latest_difficulty_feedback"] == {
        "difficulty_code": None,
        "reason_codes": [],
    }


def test_snapshot_carries_hard_feedback_with_its_reasons() -> None:
    snapshot = _context(
        difficulty_code="HARD",
        reason_codes=("MOVEMENT_DIFFICULT", "VOLUME_HIGH"),
    ).snapshot()

    assert snapshot["latest_difficulty_feedback"] == {
        "difficulty_code": "HARD",
        "reason_codes": ["MOVEMENT_DIFFICULT", "VOLUME_HIGH"],
    }


def test_reason_codes_are_order_and_duplicate_independent() -> None:
    """Row order must not change the input hash, so the same feedback replays identically."""

    one = _context(difficulty_code="HARD", reason_codes=("VOLUME_HIGH", "MOVEMENT_DIFFICULT"))
    other = _context(
        difficulty_code="HARD",
        reason_codes=("MOVEMENT_DIFFICULT", "VOLUME_HIGH", "VOLUME_HIGH"),
    )

    assert one.latest_difficulty_reason_codes == other.latest_difficulty_reason_codes
    assert one.snapshot() == other.snapshot()


def test_feedback_changes_the_snapshot() -> None:
    """Otherwise the wiring would be inert and the decision would ignore the feedback."""

    without = _context().snapshot()
    with_feedback = _context(difficulty_code="HARD", reason_codes=("VOLUME_HIGH",)).snapshot()

    assert without != with_feedback
