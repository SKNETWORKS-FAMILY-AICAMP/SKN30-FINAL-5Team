"""Deterministic weekly boundaries, report eligibility, and aggregate contracts."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKLY_REPORT_POLICY_VERSION = "1.0.0"
WEEKLY_AGGREGATE_SCHEMA_VERSION = "1.0.0"
_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class UserWeekStatusCode(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class WeeklyReportStatusCode(StrEnum):
    GENERATED = "GENERATED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


class WeeklyReportReasonCode(StrEnum):
    WEEK_NOT_CLOSED = "WEEK_NOT_CLOSED"
    WEEK_CLOSED = "WEEK_CLOSED"


class WeeklyLearningSignalCode(StrEnum):
    NOT_COMPLETED = "NOT_COMPLETED"


class WeeklyReportRuleError(ValueError):
    """Base error for invalid weekly report policy input."""


class InvalidWeeklyBoundaryError(WeeklyReportRuleError):
    """Raised when a timezone, instant, or week boundary is invalid."""


class WeekNotClosedError(WeeklyReportRuleError):
    """Raised when final report generation is attempted for an open week."""


class InvalidWeeklyAggregateError(WeeklyReportRuleError):
    """Raised when a closed-week aggregate violates its immutable contract."""


class InvalidAcknowledgementTransitionError(WeeklyReportRuleError):
    """Raised when a report cannot transition to ACKNOWLEDGED."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidWeeklyBoundaryError(f"{field_name} must include timezone information")


def _timezone(timezone_name: str) -> ZoneInfo:
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise InvalidWeeklyBoundaryError("timezone_name must be a non-empty IANA timezone")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidWeeklyBoundaryError("timezone_name must be a valid IANA timezone") from exc


def _require_machine_reference(value: str, *, field_name: str) -> None:
    if not _MACHINE_REFERENCE_PATTERN.fullmatch(value):
        raise InvalidWeeklyAggregateError(
            f"{field_name} must contain only a structured machine reference"
        )


@dataclass(frozen=True, slots=True)
class WeeklyBoundary:
    timezone_name: str
    week_start_local_date: date
    week_end_local_date: date
    starts_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        zone = _timezone(self.timezone_name)
        if self.week_start_local_date.weekday() != 0:
            raise InvalidWeeklyBoundaryError("week_start_local_date must be Monday")
        if self.week_end_local_date != self.week_start_local_date + timedelta(days=6):
            raise InvalidWeeklyBoundaryError("week_end_local_date must be the following Sunday")
        _require_aware(self.starts_at, field_name="starts_at")
        _require_aware(self.closes_at, field_name="closes_at")
        expected_start = datetime.combine(self.week_start_local_date, time.min, tzinfo=zone)
        expected_close = datetime.combine(
            self.week_end_local_date + timedelta(days=1), time.min, tzinfo=zone
        )
        if self.starts_at != expected_start or self.closes_at != expected_close:
            raise InvalidWeeklyBoundaryError(
                "weekly instants must use local Monday boundaries in the supplied timezone"
            )


@dataclass(frozen=True, slots=True)
class WeeklyReportEligibility:
    week_status_code: UserWeekStatusCode
    report_allowed: bool
    reason_code: WeeklyReportReasonCode
    report_policy_version: str = WEEKLY_REPORT_POLICY_VERSION

    def __post_init__(self) -> None:
        expected = self.week_status_code is UserWeekStatusCode.CLOSED
        if self.report_allowed is not expected:
            raise InvalidWeeklyBoundaryError("only a CLOSED week can allow report generation")
        expected_reason = (
            WeeklyReportReasonCode.WEEK_CLOSED
            if expected
            else WeeklyReportReasonCode.WEEK_NOT_CLOSED
        )
        if self.reason_code is not expected_reason:
            raise InvalidWeeklyBoundaryError("report eligibility reason must match week status")


@dataclass(frozen=True, slots=True)
class ClosedWeekAggregateInput:
    """Identifier-free, immutable input snapshot for a closed weekly report."""

    timezone_name: str
    week_start_local_date: date
    week_end_local_date: date
    completed_count: int
    partial_count: int
    not_completed_count: int
    stopped_for_safety_count: int
    week_status_code: UserWeekStatusCode = UserWeekStatusCode.CLOSED
    primary_miss_reason_code: str | None = None
    learning_signal_codes: tuple[WeeklyLearningSignalCode, ...] = ()
    penalty_applied: bool = False
    aggregate_schema_version: str = WEEKLY_AGGREGATE_SCHEMA_VERSION
    report_policy_version: str = WEEKLY_REPORT_POLICY_VERSION

    def __post_init__(self) -> None:
        _timezone(self.timezone_name)
        if self.week_status_code is not UserWeekStatusCode.CLOSED:
            raise InvalidWeeklyAggregateError("weekly report aggregate requires a CLOSED week")
        if self.week_start_local_date.weekday() != 0:
            raise InvalidWeeklyAggregateError("week_start_local_date must be Monday")
        if self.week_end_local_date != self.week_start_local_date + timedelta(days=6):
            raise InvalidWeeklyAggregateError("week_end_local_date must be Sunday")
        for field_name in (
            "completed_count",
            "partial_count",
            "not_completed_count",
            "stopped_for_safety_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidWeeklyAggregateError(f"{field_name} must be a non-negative integer")
        if self.primary_miss_reason_code is not None:
            _require_machine_reference(
                self.primary_miss_reason_code, field_name="primary_miss_reason_code"
            )
            if self.not_completed_count == 0:
                raise InvalidWeeklyAggregateError(
                    "primary_miss_reason_code requires at least one NOT_COMPLETED session"
                )
        expected_signals = (
            (WeeklyLearningSignalCode.NOT_COMPLETED,) if self.not_completed_count else ()
        )
        if self.learning_signal_codes != expected_signals:
            raise InvalidWeeklyAggregateError(
                "NOT_COMPLETED must be represented only as its canonical learning signal"
            )
        if self.penalty_applied:
            raise InvalidWeeklyAggregateError("missed workouts must never apply a penalty")
        for field_name in ("aggregate_schema_version", "report_policy_version"):
            _require_machine_reference(getattr(self, field_name), field_name=field_name)


def weekly_boundary_for(*, local_date: date, timezone_name: str) -> WeeklyBoundary:
    """Return the Monday-starting local week that contains ``local_date``."""

    if not isinstance(local_date, date):
        raise InvalidWeeklyBoundaryError("local_date must be a date")
    zone = _timezone(timezone_name)
    week_start = local_date - timedelta(days=local_date.weekday())
    week_end = week_start + timedelta(days=6)
    return WeeklyBoundary(
        timezone_name=timezone_name,
        week_start_local_date=week_start,
        week_end_local_date=week_end,
        starts_at=datetime.combine(week_start, time.min, tzinfo=zone),
        closes_at=datetime.combine(week_end + timedelta(days=1), time.min, tzinfo=zone),
    )


def evaluate_week_status(*, boundary: WeeklyBoundary, requested_at: datetime) -> UserWeekStatusCode:
    """Logically close a week at the following local Monday without a scheduler."""

    _require_aware(requested_at, field_name="requested_at")
    requested_local_date = requested_at.astimezone(_timezone(boundary.timezone_name)).date()
    if requested_local_date < boundary.week_start_local_date:
        raise InvalidWeeklyBoundaryError("requested_at cannot precede the evaluated week")
    if requested_local_date > boundary.week_end_local_date:
        return UserWeekStatusCode.CLOSED
    return UserWeekStatusCode.OPEN


def evaluate_report_eligibility(
    *, boundary: WeeklyBoundary, requested_at: datetime
) -> WeeklyReportEligibility:
    status = evaluate_week_status(boundary=boundary, requested_at=requested_at)
    if status is UserWeekStatusCode.CLOSED:
        return WeeklyReportEligibility(
            week_status_code=status,
            report_allowed=True,
            reason_code=WeeklyReportReasonCode.WEEK_CLOSED,
        )
    return WeeklyReportEligibility(
        week_status_code=status,
        report_allowed=False,
        reason_code=WeeklyReportReasonCode.WEEK_NOT_CLOSED,
    )


def build_closed_week_aggregate(
    *,
    boundary: WeeklyBoundary,
    requested_at: datetime,
    completed_count: int,
    partial_count: int,
    not_completed_count: int,
    stopped_for_safety_count: int,
    primary_miss_reason_code: str | None = None,
) -> ClosedWeekAggregateInput:
    """Build the minimal aggregate only after logical week closure."""

    eligibility = evaluate_report_eligibility(boundary=boundary, requested_at=requested_at)
    if not eligibility.report_allowed:
        raise WeekNotClosedError(WeeklyReportReasonCode.WEEK_NOT_CLOSED.value)
    return ClosedWeekAggregateInput(
        timezone_name=boundary.timezone_name,
        week_start_local_date=boundary.week_start_local_date,
        week_end_local_date=boundary.week_end_local_date,
        completed_count=completed_count,
        partial_count=partial_count,
        not_completed_count=not_completed_count,
        stopped_for_safety_count=stopped_for_safety_count,
        primary_miss_reason_code=primary_miss_reason_code,
        learning_signal_codes=(
            (WeeklyLearningSignalCode.NOT_COMPLETED,) if not_completed_count else ()
        ),
    )


def acknowledge_weekly_report(
    status_code: WeeklyReportStatusCode,
) -> WeeklyReportStatusCode:
    """Apply the explicit, idempotent acknowledgement state transition."""

    if status_code is WeeklyReportStatusCode.GENERATED:
        return WeeklyReportStatusCode.ACKNOWLEDGED
    if status_code is WeeklyReportStatusCode.ACKNOWLEDGED:
        return status_code
    raise InvalidAcknowledgementTransitionError("FAILED reports cannot be acknowledged")
