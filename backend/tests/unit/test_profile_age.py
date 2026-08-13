from datetime import UTC, date, datetime

import pytest

from backend.app.modules.profiles.age import (
    AgeRequirementNotMetError,
    InvalidBirthdateError,
    InvalidTimezoneError,
    evaluate_age_eligibility,
)


def test_exact_fourteenth_birthday_is_eligible() -> None:
    result = evaluate_age_eligibility(
        date(2012, 8, 13),
        "Asia/Seoul",
        at=datetime(2026, 8, 12, 15, 0, tzinfo=UTC),
    )

    assert result.age == 14
    assert result.local_date == date(2026, 8, 13)


def test_day_before_fourteenth_birthday_is_blocked() -> None:
    with pytest.raises(AgeRequirementNotMetError):
        evaluate_age_eligibility(
            date(2012, 8, 13),
            "Asia/Seoul",
            at=datetime(2026, 8, 12, 14, 59, 59, tzinfo=UTC),
        )


def test_timezone_local_date_controls_boundary() -> None:
    instant = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)

    seoul = evaluate_age_eligibility(date(2012, 8, 13), "Asia/Seoul", at=instant)
    with pytest.raises(AgeRequirementNotMetError):
        evaluate_age_eligibility(date(2012, 8, 13), "America/Los_Angeles", at=instant)

    assert seoul.local_date == date(2026, 8, 13)


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
            date(2000, 1, 1),
            timezone_name,
            at=datetime(2026, 8, 13, tzinfo=UTC),
        )

    assert timezone_name not in str(captured.value)


def test_naive_reference_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_age_eligibility(
            date(2000, 1, 1),
            "Asia/Seoul",
            at=datetime(2026, 8, 13),
        )
