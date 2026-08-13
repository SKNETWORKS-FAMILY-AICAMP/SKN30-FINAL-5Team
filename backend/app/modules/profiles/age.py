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
    local_date: date


def _latest_eligible_birthdate(local_date: date) -> date:
    eligible_year = local_date.year - MINIMUM_AGE_YEARS
    try:
        return local_date.replace(year=eligible_year)
    except ValueError:
        # A February 29 birthdate reaches the boundary on March 1 in a
        # non-leap year, so February 28 keeps the eligibility check conservative.
        return local_date.replace(year=eligible_year, day=28)


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

    if birthdate > _latest_eligible_birthdate(local_date):
        raise AgeRequirementNotMetError
    return AgeEligibility(local_date=local_date)


__all__ = [
    "MINIMUM_AGE_YEARS",
    "AgeEligibility",
    "AgeRequirementNotMetError",
    "InvalidBirthdateError",
    "InvalidTimezoneError",
    "evaluate_age_eligibility",
]
