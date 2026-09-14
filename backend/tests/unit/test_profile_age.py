from datetime import UTC, date, datetime

import pytest

from backend.app.modules.profiles.age import (
    AgeRequirementNotMetError,
    InvalidBirthdateError,
    InvalidTimezoneError,
    evaluate_age_eligibility,
)


@pytest.mark.parametrize(
    ("birthdate", "is_eligible"),
    [
        (date(2008, 8, 13), True),
        (date(2008, 8, 14), False),
        (date(1962, 8, 13), True),
        (date(1961, 8, 13), False),
    ],
)
def test_eligibility_uses_completed_years_at_birthday_boundary(
    birthdate: date, is_eligible: bool
) -> None:
    instant = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)  # 2026-08-13 in Seoul

    if is_eligible:
        result = evaluate_age_eligibility(birthdate, "Asia/Seoul", at=instant)
        assert result.local_date == date(2026, 8, 13)
    else:
        with pytest.raises(AgeRequirementNotMetError):
            evaluate_age_eligibility(birthdate, "Asia/Seoul", at=instant)


def test_timezone_local_date_controls_the_eighteenth_birthday() -> None:
    instant = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)

    seoul = evaluate_age_eligibility(date(2008, 8, 13), "Asia/Seoul", at=instant)
    with pytest.raises(AgeRequirementNotMetError):
        evaluate_age_eligibility(date(2008, 8, 13), "America/Los_Angeles", at=instant)

    assert seoul.local_date == date(2026, 8, 13)


def test_february_29_boundary_uses_the_completed_year_age() -> None:
    result = evaluate_age_eligibility(
        date(2008, 2, 29), "Asia/Seoul", at=datetime(2026, 2, 28, 15, 0, tzinfo=UTC)
    )

    assert result.local_date == date(2026, 3, 1)


def test_future_birthdate_is_rejected_without_value_in_error() -> None:
    future_birthdate = date(2026, 8, 14)

    with pytest.raises(InvalidBirthdateError) as captured:
        evaluate_age_eligibility(
            future_birthdate,
            "Asia/Seoul",
            at=datetime(2026, 8, 13, 3, 0, tzinfo=UTC),
        )

    assert future_birthdate.isoformat() not in str(captured.value)


def test_unknown_timezone_is_rejected_without_echoing_value() -> None:
    timezone_name = "Private/Unknown-Timezone"

    with pytest.raises(InvalidTimezoneError) as captured:
        evaluate_age_eligibility(
            date(2000, 1, 1), timezone_name, at=datetime(2026, 8, 13, tzinfo=UTC)
        )

    assert timezone_name not in str(captured.value)


def test_naive_reference_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_age_eligibility(date(2000, 1, 1), "Asia/Seoul", at=datetime(2026, 8, 13))
