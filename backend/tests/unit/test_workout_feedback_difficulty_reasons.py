"""Request contract for `difficulty_reason_codes` on workout feedback.

ADR-0018 makes the reasons the input that picks the next routine's adjustment axis. They
are additive for now: `DOMAIN_RULES.md` 1.1 requires the API change to land before new
writes are enforced, and clients in the field still post `HARD` alone.
"""

import pytest
from pydantic import ValidationError

from backend.app.modules.workouts.schemas import WorkoutFeedbackRequest


def _request(**overrides: object) -> WorkoutFeedbackRequest:
    payload: dict[str, object] = {
        "difficulty_code": "HARD",
        "pain_occurred": False,
        "discomforts": [],
        "adverse_reaction_codes": [],
    }
    payload.update(overrides)
    return WorkoutFeedbackRequest.model_validate(payload)


def test_hard_accepts_both_reason_codes() -> None:
    request = _request(difficulty_reason_codes=["VOLUME_HIGH", "MOVEMENT_DIFFICULT"])

    assert [code.value for code in request.difficulty_reason_codes] == [
        "VOLUME_HIGH",
        "MOVEMENT_DIFFICULT",
    ]


def test_hard_accepts_a_single_reason_code() -> None:
    request = _request(difficulty_reason_codes=["MOVEMENT_DIFFICULT"])

    assert len(request.difficulty_reason_codes) == 1


def test_hard_without_reasons_is_still_accepted_during_rollout() -> None:
    """Existing clients post `HARD` alone; rejecting them would drop real feedback."""

    request = _request()

    assert request.difficulty_reason_codes == []


@pytest.mark.parametrize("difficulty_code", ["EASY", "APPROPRIATE"])
def test_reasons_are_rejected_outside_hard(difficulty_code: str) -> None:
    """Storing a row that does not match the request would break replay of the decision."""

    with pytest.raises(ValidationError, match="only allowed when difficulty_code is HARD"):
        _request(difficulty_code=difficulty_code, difficulty_reason_codes=["VOLUME_HIGH"])


def test_duplicate_reasons_are_rejected() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        _request(difficulty_reason_codes=["VOLUME_HIGH", "VOLUME_HIGH"])


def test_unknown_reason_codes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(difficulty_reason_codes=["TOO_LONG"])


def test_non_hard_feedback_stays_valid_without_reasons() -> None:
    assert _request(difficulty_code="EASY").difficulty_reason_codes == []
