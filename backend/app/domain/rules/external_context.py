"""Deterministic privacy boundary for optional calendar context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EXTERNAL_CONTEXT_POLICY_VERSION = "external-context-policy-v1"
GOOGLE_CALENDAR_FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
GOOGLE_CALENDAR_APP_CREATED_SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
CALENDAR_RATE_LIMIT_WINDOW = timedelta(hours=1)
CALENDAR_AVAILABILITY_RATE_LIMIT = 30
CALENDAR_TOTAL_RATE_LIMIT = 60
PERFORMANCE_RECHECK_INTERVAL = timedelta(minutes=10)
AVAILABILITY_BUFFER = timedelta(minutes=15)
MAX_AVAILABILITY_SLOTS = 8
PERFORMANCE_UNAVAILABLE_GUIDANCE = (
    "Google Calendar에서는 운동 수행 여부를 확인할 수 없습니다. "
    "공식 기록은 앱의 운동 블록 체크를 기준으로 합니다."
)


class CalendarProviderCode(StrEnum):
    GOOGLE_CALENDAR = "GOOGLE_CALENDAR"


class CalendarConnectionStatusCode(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class CalendarOperationCode(StrEnum):
    CONNECTION = "CONNECTION"
    AVAILABILITY = "AVAILABILITY"
    EVENT_CREATE = "EVENT_CREATE"
    PERFORMANCE = "PERFORMANCE"
    DISCONNECTION = "DISCONNECTION"


class CalendarFailureCode(StrEnum):
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    CALENDAR_NOT_CONNECTED = "CALENDAR_NOT_CONNECTED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"


class CalendarProviderFailureKindCode(StrEnum):
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    HTTP_5XX = "HTTP_5XX"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"


class CalendarOutcomeStatusCode(StrEnum):
    AVAILABLE = "AVAILABLE"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    NOT_CONNECTED = "NOT_CONNECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class CalendarDisconnectActionCode(StrEnum):
    REVOKE_PROVIDER = "REVOKE_PROVIDER"
    NOOP_ALREADY_REVOKED = "NOOP_ALREADY_REVOKED"


class ExternalContextContractError(ValueError):
    """A safe external-context failure containing only an approved machine code."""

    def __init__(self, code: CalendarFailureCode) -> None:
        self.code = code
        super().__init__(code)


class ScheduledWorkoutStatusCode(StrEnum):
    SCHEDULED = "SCHEDULED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NOT_COMPLETED = "NOT_COMPLETED"
    REST_SELECTED = "REST_SELECTED"


class OfficialWorkoutStatusCode(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NOT_COMPLETED = "NOT_COMPLETED"
    STOPPED_FOR_SAFETY = "STOPPED_FOR_SAFETY"


FINAL_SCHEDULED_WORKOUT_STATUSES = frozenset(
    {
        ScheduledWorkoutStatusCode.COMPLETED,
        ScheduledWorkoutStatusCode.PARTIAL,
        ScheduledWorkoutStatusCode.NOT_COMPLETED,
        ScheduledWorkoutStatusCode.REST_SELECTED,
    }
)


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


def _timezone(timezone_name: str) -> ZoneInfo:
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("timezone_name must be a non-empty IANA timezone")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc


@dataclass(frozen=True, slots=True)
class ManualFallback:
    manual_checkin_available: bool = True
    workout_block_check_available: bool = True
    plan_mutation_allowed: bool = False


MANUAL_FALLBACK = ManualFallback()


@dataclass(frozen=True, slots=True)
class CalendarAccessDecision:
    allowed: bool
    status_code: CalendarOutcomeStatusCode
    failure_code: CalendarFailureCode | None
    manual_fallback: ManualFallback


def evaluate_calendar_access(
    *,
    consent_granted: bool,
    connection_status_code: CalendarConnectionStatusCode | None,
) -> CalendarAccessDecision:
    if not consent_granted:
        return CalendarAccessDecision(
            allowed=False,
            status_code=CalendarOutcomeStatusCode.CONSENT_REQUIRED,
            failure_code=CalendarFailureCode.CONSENT_REQUIRED,
            manual_fallback=MANUAL_FALLBACK,
        )
    if connection_status_code is not CalendarConnectionStatusCode.ACTIVE:
        return CalendarAccessDecision(
            allowed=False,
            status_code=CalendarOutcomeStatusCode.NOT_CONNECTED,
            failure_code=CalendarFailureCode.CALENDAR_NOT_CONNECTED,
            manual_fallback=MANUAL_FALLBACK,
        )
    return CalendarAccessDecision(
        allowed=True,
        status_code=CalendarOutcomeStatusCode.AVAILABLE,
        failure_code=None,
        manual_fallback=MANUAL_FALLBACK,
    )


@dataclass(frozen=True, slots=True)
class CalendarProviderFailureDecision:
    status_code: CalendarOutcomeStatusCode
    failure_code: CalendarFailureCode | None
    manual_fallback: ManualFallback = MANUAL_FALLBACK


def classify_calendar_provider_failure(
    failure_kind_code: CalendarProviderFailureKindCode,
) -> CalendarProviderFailureDecision:
    if failure_kind_code is CalendarProviderFailureKindCode.PERMISSION_DENIED:
        return CalendarProviderFailureDecision(
            status_code=CalendarOutcomeStatusCode.PERMISSION_DENIED,
            failure_code=None,
        )
    return CalendarProviderFailureDecision(
        status_code=CalendarOutcomeStatusCode.PROVIDER_UNAVAILABLE,
        failure_code=CalendarFailureCode.PROVIDER_UNAVAILABLE,
    )


@dataclass(frozen=True, slots=True)
class CalendarConnectionState:
    connection_id: UUID
    status_code: CalendarConnectionStatusCode
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.revoked_at is not None:
            _require_aware(self.revoked_at, field_name="revoked_at")
        if self.status_code is CalendarConnectionStatusCode.ACTIVE and self.revoked_at is not None:
            raise ValueError("active calendar connection cannot have revoked_at")
        if self.status_code is CalendarConnectionStatusCode.REVOKED and self.revoked_at is None:
            raise ValueError("revoked calendar connection requires revoked_at")


@dataclass(frozen=True, slots=True)
class CalendarDisconnectDecision:
    action_code: CalendarDisconnectActionCode
    state: CalendarConnectionState


def request_calendar_disconnect(
    state: CalendarConnectionState,
    *,
    requested_at: datetime,
) -> CalendarDisconnectDecision:
    _require_aware(requested_at, field_name="requested_at")
    if state.status_code is CalendarConnectionStatusCode.REVOKED:
        return CalendarDisconnectDecision(
            action_code=CalendarDisconnectActionCode.NOOP_ALREADY_REVOKED,
            state=state,
        )
    return CalendarDisconnectDecision(
        action_code=CalendarDisconnectActionCode.REVOKE_PROVIDER,
        state=replace(
            state,
            status_code=CalendarConnectionStatusCode.REVOKED,
            revoked_at=requested_at,
        ),
    )


def commit_calendar_connection_mutation(
    *,
    proposed: CalendarConnectionState,
    persistence_succeeded: bool,
) -> CalendarConnectionState:
    """Expose a local connection state only after its transaction commits."""

    if not persistence_succeeded:
        raise ExternalContextContractError(CalendarFailureCode.DATABASE_UNAVAILABLE)
    return proposed


@dataclass(frozen=True, slots=True)
class FixedWindowCounter:
    count: int
    window_started_at: datetime

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("rate-limit count cannot be negative")
        _require_aware(self.window_started_at, field_name="window_started_at")


@dataclass(frozen=True, slots=True)
class CalendarRateLimitDecision:
    allowed: bool
    total_counter: FixedWindowCounter
    availability_counter: FixedWindowCounter | None
    failure_code: CalendarFailureCode | None
    retry_after: timedelta | None


def _advance_counter(
    counter: FixedWindowCounter,
    *,
    attempted_at: datetime,
) -> tuple[FixedWindowCounter, datetime]:
    attempted_in_utc = attempted_at.astimezone(UTC)
    window_end = counter.window_started_at.astimezone(UTC) + CALENDAR_RATE_LIMIT_WINDOW
    if attempted_in_utc >= window_end:
        return FixedWindowCounter(1, attempted_at), attempted_at + CALENDAR_RATE_LIMIT_WINDOW
    return FixedWindowCounter(counter.count + 1, counter.window_started_at), window_end


def evaluate_calendar_rate_limit(
    *,
    operation_code: CalendarOperationCode,
    total_counter: FixedWindowCounter,
    availability_counter: FixedWindowCounter | None,
    attempted_at: datetime,
) -> CalendarRateLimitDecision:
    _require_aware(attempted_at, field_name="attempted_at")
    next_total, total_window_end = _advance_counter(total_counter, attempted_at=attempted_at)
    total_allowed = next_total.count <= CALENDAR_TOTAL_RATE_LIMIT

    next_availability: FixedWindowCounter | None = availability_counter
    availability_allowed = True
    availability_window_end: datetime | None = None
    if operation_code is CalendarOperationCode.AVAILABILITY:
        if availability_counter is None:
            raise ValueError("availability requests require an availability counter")
        next_availability, availability_window_end = _advance_counter(
            availability_counter,
            attempted_at=attempted_at,
        )
        availability_allowed = next_availability.count <= CALENDAR_AVAILABILITY_RATE_LIMIT

    allowed = total_allowed and availability_allowed
    if allowed:
        retry_after = None
    else:
        blocked_until = [
            window_end
            for is_allowed, window_end in (
                (total_allowed, total_window_end),
                (availability_allowed, availability_window_end),
            )
            if not is_allowed and window_end is not None
        ]
        retry_after = max(blocked_until) - attempted_at
    return CalendarRateLimitDecision(
        allowed=allowed,
        total_counter=next_total,
        availability_counter=next_availability,
        failure_code=None if allowed else CalendarFailureCode.RATE_LIMITED,
        retry_after=retry_after,
    )


@dataclass(frozen=True, slots=True)
class ProviderBusyInterval:
    """A freeBusy-only interval; event text and all-day metadata are intentionally absent."""

    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start_at, field_name="start_at")
        _require_aware(self.end_at, field_name="end_at")
        if self.end_at.astimezone(UTC) <= self.start_at.astimezone(UTC):
            raise ValueError("busy interval end_at must be after start_at")


@dataclass(frozen=True, slots=True)
class AvailabilitySlot:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start_at, field_name="start_at")
        _require_aware(self.end_at, field_name="end_at")
        if self.end_at.astimezone(UTC) <= self.start_at.astimezone(UTC):
            raise ValueError("availability slot end_at must be after start_at")


@dataclass(frozen=True, slots=True)
class CalendarAvailability:
    local_date: date
    timezone: str
    slots: tuple[AvailabilitySlot, ...]
    requested_duration_minutes: int
    policy_version: str = EXTERNAL_CONTEXT_POLICY_VERSION


def _merged_busy_intervals(
    *,
    busy_intervals: tuple[ProviderBusyInterval, ...],
    day_start: datetime,
    day_end: datetime,
) -> tuple[tuple[datetime, datetime], ...]:
    clipped: list[tuple[datetime, datetime]] = []
    for interval in busy_intervals:
        start_at = max(interval.start_at.astimezone(UTC), day_start)
        end_at = min(interval.end_at.astimezone(UTC), day_end)
        if start_at < end_at:
            clipped.append((start_at, end_at))
    clipped.sort(key=lambda value: (value[0], value[1]))

    merged: list[tuple[datetime, datetime]] = []
    for start_at, end_at in clipped:
        if not merged or start_at > merged[-1][1]:
            merged.append((start_at, end_at))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end_at))
    return tuple(merged)


def calculate_calendar_availability(
    *,
    local_date: date,
    timezone_name: str,
    requested_duration_minutes: int,
    busy_intervals: tuple[ProviderBusyInterval, ...],
) -> CalendarAvailability:
    if requested_duration_minutes <= 0:
        raise ValueError("requested_duration_minutes must be positive")
    zone = _timezone(timezone_name)
    day_start_local = datetime.combine(local_date, time.min, tzinfo=zone)
    day_end_local = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
    day_start = day_start_local.astimezone(UTC)
    day_end = day_end_local.astimezone(UTC)
    required_duration = timedelta(minutes=requested_duration_minutes)
    merged_busy = _merged_busy_intervals(
        busy_intervals=busy_intervals,
        day_start=day_start,
        day_end=day_end,
    )

    gaps: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for busy_start, busy_end in merged_busy:
        if cursor < busy_start:
            gaps.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if cursor < day_end:
        gaps.append((cursor, day_end))

    slots: list[AvailabilitySlot] = []
    for gap_start, gap_end in gaps:
        slot_start = gap_start + AVAILABILITY_BUFFER
        slot_end = gap_end - AVAILABILITY_BUFFER
        if slot_end - slot_start < required_duration:
            continue
        slots.append(
            AvailabilitySlot(
                start_at=slot_start.astimezone(zone),
                end_at=slot_end.astimezone(zone),
            )
        )
        if len(slots) == MAX_AVAILABILITY_SLOTS:
            break
    return CalendarAvailability(
        local_date=local_date,
        timezone=timezone_name,
        slots=tuple(slots),
        requested_duration_minutes=requested_duration_minutes,
    )


@dataclass(frozen=True, slots=True)
class OfficialWorkoutState:
    scheduled_workout_id: UUID
    status_code: OfficialWorkoutStatusCode


@dataclass(frozen=True, slots=True)
class ScheduledWorkoutState:
    scheduled_workout_id: UUID
    status_code: ScheduledWorkoutStatusCode


@dataclass(frozen=True, slots=True)
class CalendarPerformanceObservation:
    scheduled_workout_id: UUID
    performed: bool | None
    performance_checked_at: datetime
    guidance: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.performance_checked_at, field_name="performance_checked_at")


def google_calendar_performance_observation(
    *,
    scheduled_workout_id: UUID,
    performance_checked_at: datetime,
) -> CalendarPerformanceObservation:
    return CalendarPerformanceObservation(
        scheduled_workout_id=scheduled_workout_id,
        performed=None,
        performance_checked_at=performance_checked_at,
        guidance=PERFORMANCE_UNAVAILABLE_GUIDANCE,
    )


@dataclass(frozen=True, slots=True)
class PerformanceRecheckDecision:
    allowed: bool
    retry_after: timedelta | None


def evaluate_performance_recheck(
    *,
    scheduled_workout_state: ScheduledWorkoutState,
    performance_checked_at: datetime | None,
    requested_at: datetime,
) -> PerformanceRecheckDecision:
    _require_aware(requested_at, field_name="requested_at")
    if scheduled_workout_state.status_code not in FINAL_SCHEDULED_WORKOUT_STATUSES:
        raise ValueError("performance checks require a finalized official workout status")
    if performance_checked_at is None:
        return PerformanceRecheckDecision(allowed=True, retry_after=None)
    _require_aware(performance_checked_at, field_name="performance_checked_at")
    next_allowed_at = performance_checked_at + PERFORMANCE_RECHECK_INTERVAL
    if requested_at >= next_allowed_at:
        return PerformanceRecheckDecision(allowed=True, retry_after=None)
    return PerformanceRecheckDecision(
        allowed=False,
        retry_after=next_allowed_at - requested_at,
    )


def preserve_official_workout_state(
    *,
    official_workout_state: OfficialWorkoutState,
    observation: CalendarPerformanceObservation,
) -> OfficialWorkoutState:
    """Return the immutable official state unchanged after observing calendar context."""

    if official_workout_state.scheduled_workout_id != observation.scheduled_workout_id:
        raise ValueError("calendar observation must reference the same scheduled workout")
    return official_workout_state


SAFE_CALENDAR_OBSERVABILITY_FIELDS = frozenset(
    {
        "event_id",
        "operation_code",
        "provider_code",
        "outcome_code",
        "failure_code",
        "policy_version",
        "attempt_count",
        "occurred_at",
        "latency_bucket",
    }
)

FORBIDDEN_CALENDAR_FIELDS = frozenset(
    {
        "summary",
        "title",
        "description",
        "attendees",
        "location",
        "organizer",
        "creator",
        "conference_data",
        "hangout_link",
        "calendar_id",
        "external_event_id",
        "provider_subject",
        "access_token",
        "refresh_token",
        "authorization_code",
        "token_secret_ref",
        "raw_payload",
        "raw_response",
        "raw_error",
    }
)


def validate_calendar_observability_fields(field_names: frozenset[str]) -> None:
    if not field_names.issubset(SAFE_CALENDAR_OBSERVABILITY_FIELDS):
        raise ValueError("unsafe calendar observability field")


__all__ = [
    "AVAILABILITY_BUFFER",
    "CALENDAR_AVAILABILITY_RATE_LIMIT",
    "CALENDAR_RATE_LIMIT_WINDOW",
    "CALENDAR_TOTAL_RATE_LIMIT",
    "EXTERNAL_CONTEXT_POLICY_VERSION",
    "FINAL_SCHEDULED_WORKOUT_STATUSES",
    "FORBIDDEN_CALENDAR_FIELDS",
    "GOOGLE_CALENDAR_APP_CREATED_SCOPE",
    "GOOGLE_CALENDAR_FREEBUSY_SCOPE",
    "MANUAL_FALLBACK",
    "MAX_AVAILABILITY_SLOTS",
    "PERFORMANCE_RECHECK_INTERVAL",
    "PERFORMANCE_UNAVAILABLE_GUIDANCE",
    "SAFE_CALENDAR_OBSERVABILITY_FIELDS",
    "AvailabilitySlot",
    "CalendarAccessDecision",
    "CalendarAvailability",
    "CalendarConnectionStatusCode",
    "CalendarConnectionState",
    "CalendarDisconnectActionCode",
    "CalendarDisconnectDecision",
    "CalendarFailureCode",
    "CalendarOperationCode",
    "CalendarOutcomeStatusCode",
    "CalendarPerformanceObservation",
    "CalendarProviderCode",
    "CalendarProviderFailureDecision",
    "CalendarProviderFailureKindCode",
    "CalendarRateLimitDecision",
    "FixedWindowCounter",
    "ExternalContextContractError",
    "ManualFallback",
    "OfficialWorkoutState",
    "OfficialWorkoutStatusCode",
    "PerformanceRecheckDecision",
    "ProviderBusyInterval",
    "ScheduledWorkoutState",
    "ScheduledWorkoutStatusCode",
    "calculate_calendar_availability",
    "classify_calendar_provider_failure",
    "commit_calendar_connection_mutation",
    "evaluate_calendar_access",
    "evaluate_calendar_rate_limit",
    "evaluate_performance_recheck",
    "google_calendar_performance_observation",
    "preserve_official_workout_state",
    "request_calendar_disconnect",
    "validate_calendar_observability_fields",
]
