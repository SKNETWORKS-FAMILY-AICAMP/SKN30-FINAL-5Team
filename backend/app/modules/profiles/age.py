from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MINIMUM_AGE_YEARS = 14


class InvalidBirthdateError(Exception):
    """The birthdate cannot be used for eligibility evaluation."""


class InvalidTimezoneError(Exception):
    """The timezone is not an available IANA timezone."""


class AgeRequirementNotMetError(Exception):
    """The user is below the approved minimum age."""


@dataclass(frozen=True)
class AgeEligibility:
    age: int
    local_date: date


def _age_on(birthdate: date, local_date: date) -> int:
    birthday_has_passed = (local_date.month, local_date.day) >= (
        birthdate.month,
        birthdate.day,
    )
    return local_date.year - birthdate.year - (not birthday_has_passed)


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

    age = _age_on(birthdate, local_date)
    if age < MINIMUM_AGE_YEARS:
        raise AgeRequirementNotMetError
    return AgeEligibility(age=age, local_date=local_date)


__all__ = [
    "MINIMUM_AGE_YEARS",
    "AgeEligibility",
    "AgeRequirementNotMetError",
    "InvalidBirthdateError",
    "InvalidTimezoneError",
    "evaluate_age_eligibility",
]
