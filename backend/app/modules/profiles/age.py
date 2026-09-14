from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MINIMUM_AGE_YEARS = 18
MAXIMUM_AGE_YEARS = 64


class InvalidBirthdateError(Exception):
    """The birthdate cannot be used for eligibility evaluation."""


class InvalidTimezoneError(Exception):
    """The timezone is not an available IANA timezone."""


class AgeRequirementNotMetError(Exception):
    """The user is outside the approved 18–64 age range."""


@dataclass(frozen=True)
class AgeEligibility:
    local_date: date


def calculate_age(
    birthdate: date,
    timezone_name: str,
    *,
    at: datetime | None = None,
) -> int:
    """Return the completed-year age on the user's local date.

    The value is derived per request and never persisted.
    """
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezoneError from exc

    instant = at or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    local_date = instant.astimezone(timezone).date()
    if birthdate > local_date:
        raise InvalidBirthdateError

    had_birthday = (local_date.month, local_date.day) >= (birthdate.month, birthdate.day)
    return local_date.year - birthdate.year - (0 if had_birthday else 1)


def evaluate_age_eligibility(
    birthdate: date,
    timezone_name: str,
    *,
    at: datetime | None = None,
) -> AgeEligibility:
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezoneError from exc

    instant = at or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    local_date = instant.astimezone(timezone).date()
    if birthdate > local_date:
        raise InvalidBirthdateError

    age = calculate_age(birthdate, timezone_name, at=instant)
    if age < MINIMUM_AGE_YEARS or age > MAXIMUM_AGE_YEARS:
        raise AgeRequirementNotMetError
    return AgeEligibility(local_date=local_date)


__all__ = [
    "MINIMUM_AGE_YEARS",
    "MAXIMUM_AGE_YEARS",
    "AgeEligibility",
    "AgeRequirementNotMetError",
    "InvalidBirthdateError",
    "InvalidTimezoneError",
    "calculate_age",
    "evaluate_age_eligibility",
]
