"""Deterministic, provider-neutral calendar context policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.domain.rules.workout_execution import WorkoutSessionStatusCode

EXTERNAL_CONTEXT_POLICY_VERSION = "external-context-policy-v1"
CALENDAR_AVAILABILITY_SCHEMA_VERSION = "calendar-availability-v1"
CALENDAR_PERFORMANCE_SCHEMA_VERSION = "calendar-performance-v1"

CALENDAR_RATE_LIMIT_WINDOW = timedelta(hours=1)
CALENDAR_AVAILABILITY_RATE_LIMIT = 30
CALENDAR_TOTAL_RATE_LIMIT = 60
CALENDAR_PERFORMANCE_RECHECK_INTERVAL = timedelta(minutes=10)
CALENDAR_BUSY_BUFFER = timedelta(minutes=15)
CALENDAR_MAX_AVAILABILITY_SLOTS = 8
CALENDAR_PERFORMANCE_UNAVAILABLE_MESSAGE_KO = (
    "캘린더에서는 실제 운동 수행 여부를 확인할 수 없습니다. "
    "앱에서 완료한 운동 블록만 공식 기록에 반영됩니다."
)


class CalendarProviderCode(StrEnum):
    GOOGLE_CALENDAR = "GOOGLE_CALENDAR"


class CalendarConnectionStatusCode(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class CalendarEndpointCode(StrEnum):
    CONNECTION_AUTHORIZE_INIT = "CONNECTION_AUTHORIZE_INIT"
    CONNECTION_CREATE = "CONNECTION_CREATE"
    CONNECTION_DELETE = "CONNECTION_DELETE"
    AVAILABILITY = "AVAILABILITY"
    EVENT_CREATE = "EVENT_CREATE"
    PERFORMANCE = "PERFORMANCE"


class CalendarPublicFailureCode(StrEnum):
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CALENDAR_NOT_CONNECTED = "CALENDAR_NOT_CONNECTED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"


class CalendarProviderFailureKindCode(StrEnum):
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNAVAILABLE = "UNAVAILABLE"


class CalendarFallbackReasonCode(StrEnum):
    CONSENT_MISSING = "CONSENT_MISSING"
    NOT_CONNECTED = "NOT_CONNECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class CalendarAvailabilitySourceCode(StrEnum):
    MANUAL = "MANUAL"
    CALENDAR = "CALENDAR"
    ROUTINE_DEFAULT = "ROUTINE_DEFAULT"


class CalendarPerformanceCheckReasonCode(StrEnum):
    READY = "READY"
    SCHEDULED_WORKOUT_NOT_FINAL = "SCHEDULED_WORKOUT_NOT_FINAL"
    RECHECK_TOO_SOON = "RECHECK_TOO_SOON"


class CalendarPerformanceGuidanceCode(StrEnum):
    ADVISORY_ONLY = "ADVISORY_ONLY"
    PROVIDER_DOES_NOT_REPORT_PERFORMANCE = "PROVIDER_DOES_NOT_REPORT_PERFORMANCE"


class ScheduledWorkoutStatusCode(StrEnum):
    SCHEDULED = "SCHEDULED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NOT_COMPLETED = "NOT_COMPLETED"
    REST_SELECTED = "REST_SELECTED"


FINAL_SCHEDULED_WORKOUT_STATUSES = frozenset(
    {
        ScheduledWorkoutStatusCode.COMPLETED,
        ScheduledWorkoutStatusCode.PARTIAL,
        ScheduledWorkoutStatusCode.NOT_COMPLETED,
        ScheduledWorkoutStatusCode.REST_SELECTED,
    }
)


class ExternalContextPolicyError(ValueError):
    """Base error for structurally invalid external-context policy input."""


class InvalidCalendarContextError(ExternalContextPolicyError):
    """Raised when normalized calendar input violates the provider-neutral contract."""


class UnsafeCalendarObservabilityFieldError(ExternalContextPolicyError):
    """Raised when an event attempts to expose forbidden calendar material."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidCalendarContextError(f"{field_name} must include timezone information")


def _require_uuid4(value: UUID, *, field_name: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise InvalidCalendarContextError(f"{field_name} must be an opaque UUIDv4")


@dataclass(frozen=True, slots=True)
class CalendarAccessDecision:
    provider_call_allowed: bool
    manual_fallback_required: bool
    workout_plan_preserved: Literal[True] = True
    official_completion_unchanged: Literal[True] = True
    failure_code: CalendarPublicFailureCode | None = None
    fallback_reason_code: CalendarFallbackReasonCode | None = None
    policy_version: str = EXTERNAL_CONTEXT_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.provider_call_allowed:
            if self.manual_fallback_required or self.failure_code or self.fallback_reason_code:
                raise InvalidCalendarContextError(
                    "an allowed provider call cannot also require a fallback"
                )
            return
        if not self.manual_fallback_required or self.failure_code is None:
            raise InvalidCalendarContextError(
                "a blocked provider call must preserve the plan through manual fallback"
            )


def evaluate_calendar_access(
    *,
    consent_granted: bool,
    connection_status_code: CalendarConnectionStatusCode | None,
) -> CalendarAccessDecision:
    """Gate provider calls without blocking the manual daily flow."""

    if not consent_granted:
        return CalendarAccessDecision(
            provider_call_allowed=False,
            manual_fallback_required=True,
            failure_code=CalendarPublicFailureCode.CONSENT_REQUIRED,
            fallback_reason_code=CalendarFallbackReasonCode.CONSENT_MISSING,
        )
    if connection_status_code is not CalendarConnectionStatusCode.ACTIVE:
        return CalendarAccessDecision(
            provider_call_allowed=False,
            manual_fallback_required=True,
            failure_code=CalendarPublicFailureCode.CALENDAR_NOT_CONNECTED,
            fallback_reason_code=CalendarFallbackReasonCode.NOT_CONNECTED,
        )
    return CalendarAccessDecision(
        provider_call_allowed=True,
        manual_fallback_required=False,
    )


def calendar_provider_failure_fallback(
    failure_kind_code: CalendarProviderFailureKindCode,
) -> CalendarAccessDecision:
    """Map provider failures to safe public codes while preserving the workout plan."""

    if failure_kind_code is CalendarProviderFailureKindCode.PERMISSION_DENIED:
        return CalendarAccessDecision(
            provider_call_allowed=False,
            manual_fallback_required=True,
            failure_code=CalendarPublicFailureCode.CALENDAR_NOT_CONNECTED,
            fallback_reason_code=CalendarFallbackReasonCode.PERMISSION_DENIED,
        )
    return CalendarAccessDecision(
        provider_call_allowed=False,
        manual_fallback_required=True,
        failure_code=CalendarPublicFailureCode.PROVIDER_UNAVAILABLE,
        fallback_reason_code=CalendarFallbackReasonCode.PROVIDER_UNAVAILABLE,
    )


@dataclass(frozen=True, slots=True)
class CalendarRateLimitDecision:
    allowed: bool
    availability_count_after_attempt: int
    total_count_after_attempt: int
    retry_after: timedelta | None
    failure_code: CalendarPublicFailureCode | None


def evaluate_calendar_rate_limit(
    *,
    endpoint_code: CalendarEndpointCode,
    availability_count_before_attempt: int,
    total_count_before_attempt: int,
    attempted_at: datetime,
    window_started_at: datetime,
) -> CalendarRateLimitDecision:
    """Apply one deterministic user-scoped fixed window before a provider call."""

    _require_aware(attempted_at, field_name="attempted_at")
    _require_aware(window_started_at, field_name="window_started_at")
    if availability_count_before_attempt < 0 or total_count_before_attempt < 0:
        raise InvalidCalendarContextError("rate-limit counts cannot be negative")
    if availability_count_before_attempt > total_count_before_attempt:
        raise InvalidCalendarContextError(
            "availability count cannot exceed the total calendar endpoint count"
        )

    window_end = window_started_at + CALENDAR_RATE_LIMIT_WINDOW
    if attempted_at >= window_end:
        availability_count_before_attempt = 0
        total_count_before_attempt = 0
        window_started_at = attempted_at
        window_end = attempted_at + CALENDAR_RATE_LIMIT_WINDOW

    availability_count_after_attempt = availability_count_before_attempt
    if endpoint_code is CalendarEndpointCode.AVAILABILITY:
        availability_count_after_attempt += 1
    total_count_after_attempt = total_count_before_attempt + 1
    allowed = (
        availability_count_after_attempt <= CALENDAR_AVAILABILITY_RATE_LIMIT
        and total_count_after_attempt <= CALENDAR_TOTAL_RATE_LIMIT
    )
    return CalendarRateLimitDecision(
        allowed=allowed,
        availability_count_after_attempt=availability_count_after_attempt,
        total_count_after_attempt=total_count_after_attempt,
        retry_after=None if allowed else window_end - attempted_at,
        failure_code=None if allowed else CalendarPublicFailureCode.RATE_LIMITED,
    )


@dataclass(frozen=True, slots=True)
class CalendarDisconnectDecision:
    status_code: CalendarConnectionStatusCode
    destroy_secret: Literal[True]
    call_provider_revoke: Literal[False]
    idempotent_replay: bool
    policy_version: str = EXTERNAL_CONTEXT_POLICY_VERSION


def disconnect_calendar(
    status_code: CalendarConnectionStatusCode,
) -> CalendarDisconnectDecision:
    """Finish local disconnect even when Google OAuth is shared with Firebase login."""

    return CalendarDisconnectDecision(
        status_code=CalendarConnectionStatusCode.REVOKED,
        destroy_secret=True,
        call_provider_revoke=False,
        idempotent_replay=status_code is CalendarConnectionStatusCode.REVOKED,
    )


@dataclass(frozen=True, slots=True)
class AvailabilitySlot:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start_at, field_name="start_at")
        _require_aware(self.end_at, field_name="end_at")
        if self.end_at.astimezone(UTC) <= self.start_at.astimezone(UTC):
            raise InvalidCalendarContextError("availability slot end must be after start")


@dataclass(frozen=True, slots=True)
class CalendarBusyInterval:
    """Transient freebusy interval; event text and raw payloads cannot enter this type."""

    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start_at, field_name="start_at")
        _require_aware(self.end_at, field_name="end_at")
        if self.end_at.astimezone(UTC) <= self.start_at.astimezone(UTC):
            raise InvalidCalendarContextError("busy interval end must be after start")


@dataclass(frozen=True, slots=True)
class CalendarAvailability:
    """Public normalized availability contract; do not add provider metadata or event text."""

    local_date: date
    timezone: str
    slots: tuple[AvailabilitySlot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.local_date, date):
            raise InvalidCalendarContextError("local_date must be a date")
        try:
            timezone = ZoneInfo(self.timezone)
        except (TypeError, ZoneInfoNotFoundError) as exc:
            raise InvalidCalendarContextError("timezone must be an IANA timezone") from exc
        if not isinstance(self.slots, tuple):
            raise InvalidCalendarContextError("slots must be an immutable tuple")
        if len(self.slots) > CALENDAR_MAX_AVAILABILITY_SLOTS:
            raise InvalidCalendarContextError("availability cannot expose more than eight slots")
        if any(not isinstance(slot, AvailabilitySlot) for slot in self.slots):
            raise InvalidCalendarContextError("slots must contain only AvailabilitySlot values")
        if tuple(sorted(self.slots, key=lambda slot: slot.start_at.astimezone(UTC))) != self.slots:
            raise InvalidCalendarContextError("availability slots must be ordered by start time")
        for slot in self.slots:
            local_start = slot.start_at.astimezone(timezone)
            local_end = slot.end_at.astimezone(timezone)
            if local_start.date() != self.local_date:
                raise InvalidCalendarContextError("slot start must belong to local_date")
            if local_end.date() not in {self.local_date, self.local_date + timedelta(days=1)}:
                raise InvalidCalendarContextError(
                    "slot end must stay inside the local day boundary"
                )


def _calendar_day_bounds(
    local_date: date, timezone_name: str
) -> tuple[ZoneInfo, datetime, datetime]:
    try:
        timezone = ZoneInfo(timezone_name)
    except (TypeError, ZoneInfoNotFoundError) as exc:
        raise InvalidCalendarContextError("timezone must be an IANA timezone") from exc
    day_start = datetime.combine(local_date, time.min, timezone).astimezone(UTC)
    day_end = datetime.combine(local_date + timedelta(days=1), time.min, timezone).astimezone(UTC)
    return timezone, day_start, day_end


def calculate_calendar_availability(
    *,
    local_date: date,
    timezone_name: str,
    requested_duration_minutes: int,
    busy_intervals: tuple[CalendarBusyInterval, ...],
) -> CalendarAvailability:
    """Return free windows without caching, shortening duration, or reading event content."""

    if (
        isinstance(requested_duration_minutes, bool)
        or not isinstance(requested_duration_minutes, int)
        or requested_duration_minutes <= 0
    ):
        raise InvalidCalendarContextError("requested_duration_minutes must be a positive integer")
    if not isinstance(busy_intervals, tuple) or any(
        not isinstance(interval, CalendarBusyInterval) for interval in busy_intervals
    ):
        raise InvalidCalendarContextError(
            "busy_intervals must contain only immutable CalendarBusyInterval values"
        )

    timezone, day_start, day_end = _calendar_day_bounds(local_date, timezone_name)
    clipped: list[tuple[datetime, datetime]] = []
    for interval in busy_intervals:
        interval_start = max(interval.start_at.astimezone(UTC), day_start)
        interval_end = min(interval.end_at.astimezone(UTC), day_end)
        if interval_start < interval_end:
            clipped.append((interval_start, interval_end))
    clipped.sort(key=lambda interval: (interval[0], interval[1]))

    merged: list[tuple[datetime, datetime]] = []
    for interval_start, interval_end in clipped:
        if merged and interval_start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, interval_end))
        else:
            merged.append((interval_start, interval_end))

    free_intervals: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            free_intervals.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if cursor < day_end:
        free_intervals.append((cursor, day_end))

    minimum_window = timedelta(minutes=requested_duration_minutes) + 2 * CALENDAR_BUSY_BUFFER
    slots: list[AvailabilitySlot] = []
    for free_start, free_end in free_intervals:
        if free_end - free_start < minimum_window:
            continue
        slots.append(
            AvailabilitySlot(
                start_at=(free_start + CALENDAR_BUSY_BUFFER).astimezone(timezone),
                end_at=(free_end - CALENDAR_BUSY_BUFFER).astimezone(timezone),
            )
        )
        if len(slots) == CALENDAR_MAX_AVAILABILITY_SLOTS:
            break

    return CalendarAvailability(
        local_date=local_date,
        timezone=timezone_name,
        slots=tuple(slots),
    )


@dataclass(frozen=True, slots=True)
class ManualAvailabilityOverride:
    slots: tuple[AvailabilitySlot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.slots, tuple) or any(
            not isinstance(slot, AvailabilitySlot) for slot in self.slots
        ):
            raise InvalidCalendarContextError(
                "manual availability must contain immutable AvailabilitySlot values"
            )


@dataclass(frozen=True, slots=True)
class AvailabilitySelection:
    source_code: CalendarAvailabilitySourceCode
    slots: tuple[AvailabilitySlot, ...]
    manual_choice_preserved: Literal[True] = True


def select_availability(
    *,
    manual_override: ManualAvailabilityOverride | None,
    calendar_availability: CalendarAvailability | None,
) -> AvailabilitySelection:
    """Manual availability, including an explicit empty choice, always wins."""

    if manual_override is not None:
        return AvailabilitySelection(
            source_code=CalendarAvailabilitySourceCode.MANUAL,
            slots=manual_override.slots,
        )
    if calendar_availability is not None:
        return AvailabilitySelection(
            source_code=CalendarAvailabilitySourceCode.CALENDAR,
            slots=calendar_availability.slots,
        )
    return AvailabilitySelection(
        source_code=CalendarAvailabilitySourceCode.ROUTINE_DEFAULT,
        slots=(),
    )


@dataclass(frozen=True, slots=True)
class CalendarPerformanceCheckDecision:
    provider_call_allowed: bool
    reason_code: CalendarPerformanceCheckReasonCode
    retry_after: timedelta | None


def evaluate_performance_check(
    *,
    scheduled_workout_status_code: ScheduledWorkoutStatusCode,
    checked_at: datetime,
    last_performance_checked_at: datetime | None,
) -> CalendarPerformanceCheckDecision:
    """Allow on-demand checks only after finalization and at ten-minute intervals."""

    _require_aware(checked_at, field_name="checked_at")
    if last_performance_checked_at is not None:
        _require_aware(last_performance_checked_at, field_name="last_performance_checked_at")
        if last_performance_checked_at > checked_at:
            raise InvalidCalendarContextError("last performance check cannot be in the future")
    if scheduled_workout_status_code not in FINAL_SCHEDULED_WORKOUT_STATUSES:
        return CalendarPerformanceCheckDecision(
            provider_call_allowed=False,
            reason_code=CalendarPerformanceCheckReasonCode.SCHEDULED_WORKOUT_NOT_FINAL,
            retry_after=None,
        )
    if last_performance_checked_at is not None:
        next_allowed_at = last_performance_checked_at + CALENDAR_PERFORMANCE_RECHECK_INTERVAL
        if checked_at < next_allowed_at:
            return CalendarPerformanceCheckDecision(
                provider_call_allowed=False,
                reason_code=CalendarPerformanceCheckReasonCode.RECHECK_TOO_SOON,
                retry_after=next_allowed_at - checked_at,
            )
    return CalendarPerformanceCheckDecision(
        provider_call_allowed=True,
        reason_code=CalendarPerformanceCheckReasonCode.READY,
        retry_after=None,
    )


@dataclass(frozen=True, slots=True)
class CalendarPerformanceObservation:
    """Normalized advisory evidence; it has no field capable of mutating official completion."""

    scheduled_workout_id: UUID
    performed: bool | None
    performance_checked_at: datetime | None

    def __post_init__(self) -> None:
        _require_uuid4(self.scheduled_workout_id, field_name="scheduled_workout_id")
        if self.performed is not None and not isinstance(self.performed, bool):
            raise InvalidCalendarContextError("performed must be a boolean or null")
        if self.performance_checked_at is not None:
            _require_aware(self.performance_checked_at, field_name="performance_checked_at")


@dataclass(frozen=True, slots=True)
class CalendarPerformanceResolution:
    observation: CalendarPerformanceObservation
    official_session_status_code: WorkoutSessionStatusCode
    guidance_code: CalendarPerformanceGuidanceCode
    guidance_message: str | None
    official_completion_unchanged: Literal[True] = True


def preserve_official_completion_status(
    *,
    official_session_status_code: WorkoutSessionStatusCode,
    observation: CalendarPerformanceObservation,
) -> CalendarPerformanceResolution:
    """Return the official block-derived status unchanged for every calendar value."""

    return CalendarPerformanceResolution(
        observation=observation,
        official_session_status_code=official_session_status_code,
        guidance_code=(
            CalendarPerformanceGuidanceCode.PROVIDER_DOES_NOT_REPORT_PERFORMANCE
            if observation.performed is None
            else CalendarPerformanceGuidanceCode.ADVISORY_ONLY
        ),
        guidance_message=(
            CALENDAR_PERFORMANCE_UNAVAILABLE_MESSAGE_KO if observation.performed is None else None
        ),
    )


def google_calendar_performance_observation(
    *,
    scheduled_workout_id: UUID,
    checked_at: datetime,
) -> CalendarPerformanceObservation:
    """Google Calendar exposes schedule state, not actual workout performance."""

    return CalendarPerformanceObservation(
        scheduled_workout_id=scheduled_workout_id,
        performed=None,
        performance_checked_at=checked_at,
    )


FORBIDDEN_CALENDAR_FIELDS = frozenset(
    {
        "summary",
        "title",
        "description",
        "attendees",
        "location",
        "conference_data",
        "conferenceData",
        "hangout_link",
        "hangoutLink",
        "meeting_link",
        "notes",
        "raw_payload",
        "raw_response",
        "calendar_body",
        "calendar_id",
        "external_event_id",
        "provider_subject",
        "authorization_code",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "token_secret_ref",
    }
)

SAFE_CALENDAR_OBSERVABILITY_FIELDS = frozenset(
    {
        "event_id",
        "request_id",
        "provider_code",
        "endpoint_code",
        "outcome_code",
        "failure_code",
        "policy_version",
        "occurred_at",
        "latency_bucket",
    }
)


def validate_calendar_observability_fields(field_names: frozenset[str]) -> None:
    if not field_names <= SAFE_CALENDAR_OBSERVABILITY_FIELDS:
        raise UnsafeCalendarObservabilityFieldError(
            "calendar observability fields must use the approved allowlist"
        )


__all__ = [
    "CALENDAR_AVAILABILITY_RATE_LIMIT",
    "CALENDAR_AVAILABILITY_SCHEMA_VERSION",
    "CALENDAR_BUSY_BUFFER",
    "CALENDAR_MAX_AVAILABILITY_SLOTS",
    "CALENDAR_PERFORMANCE_RECHECK_INTERVAL",
    "CALENDAR_PERFORMANCE_UNAVAILABLE_MESSAGE_KO",
    "CALENDAR_PERFORMANCE_SCHEMA_VERSION",
    "CALENDAR_RATE_LIMIT_WINDOW",
    "CALENDAR_TOTAL_RATE_LIMIT",
    "EXTERNAL_CONTEXT_POLICY_VERSION",
    "FORBIDDEN_CALENDAR_FIELDS",
    "SAFE_CALENDAR_OBSERVABILITY_FIELDS",
    "AvailabilitySelection",
    "AvailabilitySlot",
    "CalendarAccessDecision",
    "CalendarAvailability",
    "CalendarAvailabilitySourceCode",
    "CalendarBusyInterval",
    "CalendarConnectionStatusCode",
    "CalendarDisconnectDecision",
    "CalendarEndpointCode",
    "CalendarFallbackReasonCode",
    "CalendarPerformanceCheckDecision",
    "CalendarPerformanceCheckReasonCode",
    "CalendarPerformanceGuidanceCode",
    "CalendarPerformanceObservation",
    "CalendarPerformanceResolution",
    "CalendarProviderCode",
    "CalendarProviderFailureKindCode",
    "CalendarPublicFailureCode",
    "CalendarRateLimitDecision",
    "ExternalContextPolicyError",
    "InvalidCalendarContextError",
    "ManualAvailabilityOverride",
    "ScheduledWorkoutStatusCode",
    "UnsafeCalendarObservabilityFieldError",
    "calculate_calendar_availability",
    "calendar_provider_failure_fallback",
    "disconnect_calendar",
    "evaluate_calendar_access",
    "evaluate_calendar_rate_limit",
    "evaluate_performance_check",
    "google_calendar_performance_observation",
    "preserve_official_completion_status",
    "select_availability",
    "validate_calendar_observability_fields",
]
