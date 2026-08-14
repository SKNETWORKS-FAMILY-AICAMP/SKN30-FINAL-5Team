import logging
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from backend.app.domain.rules.external_context import (
    CALENDAR_AVAILABILITY_RATE_LIMIT,
    CALENDAR_MAX_AVAILABILITY_SLOTS,
    CALENDAR_PERFORMANCE_UNAVAILABLE_MESSAGE_KO,
    CALENDAR_TOTAL_RATE_LIMIT,
    FORBIDDEN_CALENDAR_FIELDS,
    SAFE_CALENDAR_OBSERVABILITY_FIELDS,
    AvailabilitySlot,
    CalendarAvailability,
    CalendarAvailabilitySourceCode,
    CalendarBusyInterval,
    CalendarConnectionStatusCode,
    CalendarEndpointCode,
    CalendarFallbackReasonCode,
    CalendarPerformanceCheckReasonCode,
    CalendarPerformanceGuidanceCode,
    CalendarPerformanceObservation,
    CalendarProviderFailureKindCode,
    CalendarPublicFailureCode,
    ManualAvailabilityOverride,
    ScheduledWorkoutStatusCode,
    UnsafeCalendarObservabilityFieldError,
    calculate_calendar_availability,
    calendar_provider_failure_fallback,
    disconnect_calendar,
    evaluate_calendar_access,
    evaluate_calendar_rate_limit,
    evaluate_performance_check,
    google_calendar_performance_observation,
    preserve_official_completion_status,
    select_availability,
    validate_calendar_observability_fields,
)
from backend.app.domain.rules.workout_execution import WorkoutSessionStatusCode
from backend.app.integrations.calendar_provider import (
    SyntheticCalendarProvider,
    UnavailableCalendarProvider,
    build_calendar_provider,
)
from backend.app.modules.external_context.ports import (
    CalendarAvailabilityQuery,
    CalendarEventCreateCommand,
    CalendarProviderUnavailableError,
)

NOW = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
WORKOUT_ID = UUID("e6d11237-717b-48f5-bc87-9bb4560c9be2")


def _busy(start_hour: int, end_hour: int) -> CalendarBusyInterval:
    return CalendarBusyInterval(
        start_at=NOW + timedelta(hours=start_hour),
        end_at=NOW + timedelta(hours=end_hour),
    )


def test_consent_and_connection_gate_preserve_manual_flow() -> None:
    without_consent = evaluate_calendar_access(
        consent_granted=False,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )
    disconnected = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=None,
    )
    active = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )

    assert without_consent.failure_code is CalendarPublicFailureCode.CONSENT_REQUIRED
    assert without_consent.fallback_reason_code is CalendarFallbackReasonCode.CONSENT_MISSING
    assert disconnected.failure_code is CalendarPublicFailureCode.CALENDAR_NOT_CONNECTED
    assert disconnected.manual_fallback_required is True
    assert disconnected.workout_plan_preserved is True
    assert active.provider_call_allowed is True


@pytest.mark.parametrize(
    ("kind", "failure", "reason"),
    [
        (
            CalendarProviderFailureKindCode.PERMISSION_DENIED,
            CalendarPublicFailureCode.CALENDAR_NOT_CONNECTED,
            CalendarFallbackReasonCode.PERMISSION_DENIED,
        ),
        (
            CalendarProviderFailureKindCode.UNAVAILABLE,
            CalendarPublicFailureCode.PROVIDER_UNAVAILABLE,
            CalendarFallbackReasonCode.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_provider_failures_have_deterministic_manual_fallback(
    kind: CalendarProviderFailureKindCode,
    failure: CalendarPublicFailureCode,
    reason: CalendarFallbackReasonCode,
) -> None:
    decision = calendar_provider_failure_fallback(kind)

    assert decision.failure_code is failure
    assert decision.fallback_reason_code is reason
    assert decision.manual_fallback_required is True
    assert decision.official_completion_unchanged is True


def test_rate_limit_boundaries_are_30_availability_and_60_total() -> None:
    thirtieth = evaluate_calendar_rate_limit(
        endpoint_code=CalendarEndpointCode.AVAILABILITY,
        availability_count_before_attempt=CALENDAR_AVAILABILITY_RATE_LIMIT - 1,
        total_count_before_attempt=CALENDAR_AVAILABILITY_RATE_LIMIT - 1,
        attempted_at=NOW + timedelta(minutes=59),
        window_started_at=NOW,
    )
    thirty_first = evaluate_calendar_rate_limit(
        endpoint_code=CalendarEndpointCode.AVAILABILITY,
        availability_count_before_attempt=CALENDAR_AVAILABILITY_RATE_LIMIT,
        total_count_before_attempt=CALENDAR_AVAILABILITY_RATE_LIMIT,
        attempted_at=NOW + timedelta(minutes=59),
        window_started_at=NOW,
    )
    sixtieth = evaluate_calendar_rate_limit(
        endpoint_code=CalendarEndpointCode.PERFORMANCE,
        availability_count_before_attempt=10,
        total_count_before_attempt=CALENDAR_TOTAL_RATE_LIMIT - 1,
        attempted_at=NOW + timedelta(minutes=59),
        window_started_at=NOW,
    )
    sixty_first = evaluate_calendar_rate_limit(
        endpoint_code=CalendarEndpointCode.EVENT_CREATE,
        availability_count_before_attempt=10,
        total_count_before_attempt=CALENDAR_TOTAL_RATE_LIMIT,
        attempted_at=NOW + timedelta(minutes=59),
        window_started_at=NOW,
    )

    assert thirtieth.allowed is True
    assert thirty_first.allowed is False
    assert thirty_first.failure_code is CalendarPublicFailureCode.RATE_LIMITED
    assert sixtieth.allowed is True
    assert sixty_first.allowed is False


def test_rate_limit_resets_at_exactly_one_hour() -> None:
    result = evaluate_calendar_rate_limit(
        endpoint_code=CalendarEndpointCode.AVAILABILITY,
        availability_count_before_attempt=30,
        total_count_before_attempt=60,
        attempted_at=NOW + timedelta(hours=1),
        window_started_at=NOW,
    )

    assert result.allowed is True
    assert result.availability_count_after_attempt == 1
    assert result.total_count_after_attempt == 1


def test_disconnect_is_local_idempotent_and_never_revokes_shared_google_grant() -> None:
    first = disconnect_calendar(CalendarConnectionStatusCode.ACTIVE)
    replay = disconnect_calendar(CalendarConnectionStatusCode.REVOKED)

    assert first.status_code is CalendarConnectionStatusCode.REVOKED
    assert first.destroy_secret is True
    assert first.call_provider_revoke is False
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True


def test_overlapping_busy_intervals_are_merged_before_slot_calculation() -> None:
    availability = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="UTC",
        requested_duration_minutes=30,
        busy_intervals=(
            _busy(6, 8),
            CalendarBusyInterval(
                start_at=NOW + timedelta(hours=7, minutes=30),
                end_at=NOW + timedelta(hours=9),
            ),
        ),
    )

    assert [(slot.start_at.hour, slot.end_at.hour) for slot in availability.slots] == [
        (0, 5),
        (9, 23),
    ]
    assert availability.slots[0].start_at.minute == 15
    assert availability.slots[0].end_at.minute == 45


def test_adjacent_busy_intervals_are_merged_without_creating_a_false_gap() -> None:
    availability = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="UTC",
        requested_duration_minutes=30,
        busy_intervals=(_busy(6, 8), _busy(8, 10)),
    )

    assert [(slot.start_at.hour, slot.end_at.hour) for slot in availability.slots] == [
        (0, 5),
        (10, 23),
    ]


@pytest.mark.parametrize(
    ("free_minutes", "expected_slots"),
    [(59, 0), (60, 1), (61, 1)],
)
def test_buffer_and_minimum_slot_boundary(
    free_minutes: int,
    expected_slots: int,
) -> None:
    availability = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="UTC",
        requested_duration_minutes=30,
        busy_intervals=(
            CalendarBusyInterval(
                start_at=NOW + timedelta(minutes=free_minutes),
                end_at=NOW + timedelta(days=1),
            ),
        ),
    )

    assert len(availability.slots) == expected_slots


def test_slots_are_sorted_and_capped_at_eight() -> None:
    busy_intervals = tuple(
        CalendarBusyInterval(
            start_at=NOW + timedelta(hours=hour),
            end_at=NOW + timedelta(hours=hour, minutes=30),
        )
        for hour in range(1, 20, 2)
    )

    availability = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="UTC",
        requested_duration_minutes=10,
        busy_intervals=busy_intervals,
    )

    assert len(availability.slots) == CALENDAR_MAX_AVAILABILITY_SLOTS
    assert availability.slots == tuple(sorted(availability.slots, key=lambda slot: slot.start_at))


def test_busy_interval_crossing_midnight_is_clipped_to_requested_local_date() -> None:
    availability = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="Asia/Tokyo",
        requested_duration_minutes=30,
        busy_intervals=(
            CalendarBusyInterval(
                start_at=datetime(2026, 8, 13, 23, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
                end_at=datetime(2026, 8, 14, 1, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            ),
        ),
    )

    assert len(availability.slots) == 1
    assert availability.slots[0].start_at == datetime(
        2026, 8, 14, 1, 15, tzinfo=ZoneInfo("Asia/Tokyo")
    )


def test_dst_day_uses_real_iana_midnight_boundaries() -> None:
    availability = calculate_calendar_availability(
        local_date=date(2026, 3, 8),
        timezone_name="America/New_York",
        requested_duration_minutes=30,
        busy_intervals=(),
    )

    slot = availability.slots[0]
    assert slot.start_at.hour == 0 and slot.start_at.minute == 15
    assert slot.end_at.hour == 23 and slot.end_at.minute == 45
    assert slot.end_at.astimezone(UTC) - slot.start_at.astimezone(UTC) == timedelta(
        hours=22, minutes=30
    )


def test_manual_availability_override_wins_even_when_explicitly_empty() -> None:
    calendar = CalendarAvailability(
        local_date=date(2026, 8, 14),
        timezone="UTC",
        slots=(
            AvailabilitySlot(
                start_at=NOW + timedelta(hours=10),
                end_at=NOW + timedelta(hours=11),
            ),
        ),
    )

    result = select_availability(
        manual_override=ManualAvailabilityOverride(slots=()),
        calendar_availability=calendar,
    )

    assert result.source_code is CalendarAvailabilitySourceCode.MANUAL
    assert result.slots == ()
    assert result.manual_choice_preserved is True


def test_performance_check_requires_final_status_and_ten_minute_interval() -> None:
    not_final = evaluate_performance_check(
        scheduled_workout_status_code=ScheduledWorkoutStatusCode.STARTED,
        checked_at=NOW,
        last_performance_checked_at=None,
    )
    before_boundary = evaluate_performance_check(
        scheduled_workout_status_code=ScheduledWorkoutStatusCode.COMPLETED,
        checked_at=NOW + timedelta(minutes=9, seconds=59),
        last_performance_checked_at=NOW,
    )
    at_boundary = evaluate_performance_check(
        scheduled_workout_status_code=ScheduledWorkoutStatusCode.COMPLETED,
        checked_at=NOW + timedelta(minutes=10),
        last_performance_checked_at=NOW,
    )

    assert not_final.reason_code is CalendarPerformanceCheckReasonCode.SCHEDULED_WORKOUT_NOT_FINAL
    assert not_final.provider_call_allowed is False
    assert before_boundary.reason_code is CalendarPerformanceCheckReasonCode.RECHECK_TOO_SOON
    assert before_boundary.retry_after == timedelta(seconds=1)
    assert at_boundary.provider_call_allowed is True


@pytest.mark.parametrize("performed", [True, False, None])
def test_calendar_performance_can_never_change_official_completion(
    performed: bool | None,
) -> None:
    observation = CalendarPerformanceObservation(
        scheduled_workout_id=WORKOUT_ID,
        performed=performed,
        performance_checked_at=NOW,
    )

    result = preserve_official_completion_status(
        official_session_status_code=WorkoutSessionStatusCode.NOT_COMPLETED,
        observation=observation,
    )

    assert result.official_session_status_code is WorkoutSessionStatusCode.NOT_COMPLETED
    assert result.official_completion_unchanged is True


def test_google_calendar_performance_is_always_unknown_with_fallback_guidance() -> None:
    observation = google_calendar_performance_observation(
        scheduled_workout_id=WORKOUT_ID,
        checked_at=NOW,
    )
    result = preserve_official_completion_status(
        official_session_status_code=WorkoutSessionStatusCode.COMPLETED,
        observation=observation,
    )

    assert observation.performed is None
    assert (
        result.guidance_code is CalendarPerformanceGuidanceCode.PROVIDER_DOES_NOT_REPORT_PERFORMANCE
    )
    assert result.guidance_message == CALENDAR_PERFORMANCE_UNAVAILABLE_MESSAGE_KO


def test_unavailable_and_synthetic_adapters_follow_the_same_port_contract() -> None:
    unavailable = build_calendar_provider()
    with pytest.raises(CalendarProviderUnavailableError):
        unavailable.fetch_busy_intervals(
            CalendarAvailabilityQuery(local_date=date(2026, 8, 14), timezone="UTC")
        )

    synthetic = build_calendar_provider(SyntheticCalendarProvider(busy_intervals=(_busy(8, 9),)))
    assert synthetic.fetch_busy_intervals(
        CalendarAvailabilityQuery(local_date=date(2026, 8, 14), timezone="UTC")
    ) == (_busy(8, 9),)
    created = synthetic.create_app_event(
        CalendarEventCreateCommand(
            scheduled_workout_id=WORKOUT_ID,
            start_at=NOW + timedelta(hours=10),
            end_at=NOW + timedelta(hours=11),
        )
    )
    assert 5 <= len(created.external_event_id) <= 1024
    assert isinstance(unavailable, UnavailableCalendarProvider)


def test_normalized_contracts_have_no_raw_calendar_or_completion_mutation_fields() -> None:
    availability_fields = {field.name for field in fields(CalendarAvailability)}
    performance_fields = {field.name for field in fields(CalendarPerformanceObservation)}

    assert availability_fields == {"local_date", "timezone", "slots"}
    assert performance_fields == {
        "scheduled_workout_id",
        "performed",
        "performance_checked_at",
    }
    assert availability_fields.isdisjoint(FORBIDDEN_CALENDAR_FIELDS)
    assert performance_fields.isdisjoint(FORBIDDEN_CALENDAR_FIELDS)


def test_calendar_observability_allowlist_blocks_sensitive_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    validate_calendar_observability_fields(SAFE_CALENDAR_OBSERVABILITY_FIELDS)
    with pytest.raises(UnsafeCalendarObservabilityFieldError):
        validate_calendar_observability_fields(frozenset({"title"}))

    safe_event = {
        "event_id": "7b2adf5f-8318-4be6-98cf-8c1fde688055",
        "request_id": "77a768f7-8814-49d9-bf0d-c0b7826ef74e",
        "provider_code": "GOOGLE_CALENDAR",
        "endpoint_code": "AVAILABILITY",
        "outcome_code": "FALLBACK",
        "failure_code": "PROVIDER_UNAVAILABLE",
        "policy_version": "external-context-policy-v1",
        "occurred_at": "2026-08-14T00:00:00+00:00",
        "latency_bucket": "LT_1S",
    }
    with caplog.at_level(logging.INFO):
        logging.getLogger("calendar-policy-test").info("calendar_event=%s", safe_event)

    assert frozenset(safe_event) == SAFE_CALENDAR_OBSERVABILITY_FIELDS
    assert all(field_name not in caplog.text for field_name in FORBIDDEN_CALENDAR_FIELDS)
