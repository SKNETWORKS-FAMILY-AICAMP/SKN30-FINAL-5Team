from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from backend.app.domain.rules.external_context import (
    CALENDAR_AVAILABILITY_RATE_LIMIT,
    CALENDAR_AVAILABILITY_SCHEMA_VERSION,
    CALENDAR_PERFORMANCE_SCHEMA_VERSION,
    CALENDAR_TOTAL_RATE_LIMIT,
    EXTERNAL_CONTEXT_POLICY_VERSION,
    FORBIDDEN_CALENDAR_FIELDS,
    GOOGLE_CALENDAR_APP_CREATED_SCOPE,
    GOOGLE_CALENDAR_FREEBUSY_SCOPE,
    MAX_AVAILABILITY_SLOTS,
    PERFORMANCE_RECHECK_INTERVAL,
    SAFE_CALENDAR_OBSERVABILITY_FIELDS,
    AvailabilitySlot,
    CalendarAvailability,
    CalendarAvailabilitySourceCode,
    CalendarConnectionState,
    CalendarConnectionStatusCode,
    CalendarDisconnectActionCode,
    CalendarFailureCode,
    CalendarOperationCode,
    CalendarOutcomeStatusCode,
    CalendarPerformanceObservation,
    CalendarProviderFailureKindCode,
    ExternalContextContractError,
    FixedWindowCounter,
    ManualAvailabilityOverride,
    OfficialWorkoutState,
    ProviderBusyInterval,
    ScheduledWorkoutState,
    ScheduledWorkoutStatusCode,
    calculate_calendar_availability,
    calendar_performance_guidance,
    classify_calendar_provider_failure,
    commit_calendar_connection_mutation,
    evaluate_calendar_access,
    evaluate_calendar_rate_limit,
    evaluate_performance_recheck,
    google_calendar_performance_observation,
    preserve_official_workout_state,
    request_calendar_disconnect,
    select_availability,
    validate_calendar_observability_fields,
)
from backend.app.domain.rules.workout_execution import WorkoutSessionStatusCode

SEOUL = ZoneInfo("Asia/Seoul")
LOCAL_DATE = date(2026, 8, 14)
NOW = datetime(2026, 8, 14, 9, 0, tzinfo=SEOUL)


def _local(hour: int, minute: int = 0, *, day: int = 14) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=SEOUL)


def _busy(
    start_hour: int,
    end_hour: int,
    *,
    start_minute: int = 0,
    end_minute: int = 0,
) -> ProviderBusyInterval:
    return ProviderBusyInterval(
        _local(start_hour, start_minute),
        _local(end_hour, end_minute),
    )


def test_google_calendar_contract_uses_only_minimal_scopes() -> None:
    assert GOOGLE_CALENDAR_FREEBUSY_SCOPE == ("https://www.googleapis.com/auth/calendar.freebusy")
    assert GOOGLE_CALENDAR_APP_CREATED_SCOPE == (
        "https://www.googleapis.com/auth/calendar.app.created"
    )
    assert EXTERNAL_CONTEXT_POLICY_VERSION == "external-context-policy-v1"
    assert CALENDAR_AVAILABILITY_SCHEMA_VERSION == "calendar-availability-v1"
    assert CALENDAR_PERFORMANCE_SCHEMA_VERSION == "calendar-performance-v1"


def test_freebusy_input_and_availability_output_expose_only_normalized_fields() -> None:
    assert {field.name for field in fields(ProviderBusyInterval)} == {"start_at", "end_at"}
    result = calculate_calendar_availability(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Seoul",
        requested_duration_minutes=30,
        busy_intervals=(),
    )
    assert {field.name for field in fields(result)} == {
        "local_date",
        "timezone",
        "slots",
    }


def test_consent_and_connection_gate_preserve_manual_fallback() -> None:
    consent_required = evaluate_calendar_access(
        consent_granted=False,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )
    not_connected = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=None,
    )
    allowed = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )

    assert consent_required.failure_code is CalendarFailureCode.CONSENT_REQUIRED
    assert not_connected.failure_code is CalendarFailureCode.CALENDAR_NOT_CONNECTED
    assert allowed.allowed is True and allowed.failure_code is None
    for decision in (consent_required, not_connected, allowed):
        assert decision.manual_fallback.manual_checkin_available is True
        assert decision.manual_fallback.workout_block_check_available is True
        assert decision.manual_fallback.plan_mutation_allowed is False


@pytest.mark.parametrize(
    "kind",
    [
        CalendarProviderFailureKindCode.TIMEOUT,
        CalendarProviderFailureKindCode.HTTP_5XX,
        CalendarProviderFailureKindCode.PROVIDER_RATE_LIMITED,
    ],
)
def test_provider_failures_use_safe_public_error_and_manual_fallback(
    kind: CalendarProviderFailureKindCode,
) -> None:
    decision = classify_calendar_provider_failure(kind)

    assert decision.status_code is CalendarOutcomeStatusCode.PROVIDER_UNAVAILABLE
    assert decision.failure_code is CalendarFailureCode.PROVIDER_UNAVAILABLE
    assert decision.manual_fallback.plan_mutation_allowed is False


def test_permission_denial_is_not_invented_as_a_new_public_error() -> None:
    decision = classify_calendar_provider_failure(CalendarProviderFailureKindCode.PERMISSION_DENIED)

    assert decision.status_code is CalendarOutcomeStatusCode.PERMISSION_DENIED
    assert decision.failure_code is CalendarFailureCode.CALENDAR_NOT_CONNECTED
    assert decision.manual_fallback.manual_checkin_available is True


def test_disconnect_is_local_first_and_repeated_request_is_a_noop() -> None:
    original = CalendarConnectionState(
        connection_id=uuid4(),
        status_code=CalendarConnectionStatusCode.ACTIVE,
    )

    first = request_calendar_disconnect(original, requested_at=NOW)
    repeated = request_calendar_disconnect(
        first.state,
        requested_at=NOW + timedelta(seconds=1),
    )

    assert first.action_code is CalendarDisconnectActionCode.DESTROY_SECRET_LOCALLY
    assert first.state.status_code is CalendarConnectionStatusCode.REVOKED
    assert first.state.revoked_at == NOW
    assert repeated.action_code is CalendarDisconnectActionCode.NOOP_ALREADY_REVOKED
    assert repeated.state is first.state


def test_failed_connection_persistence_does_not_expose_proposed_disconnect() -> None:
    original = CalendarConnectionState(uuid4(), CalendarConnectionStatusCode.ACTIVE)
    proposed = request_calendar_disconnect(original, requested_at=NOW).state

    with pytest.raises(ExternalContextContractError) as captured:
        commit_calendar_connection_mutation(
            proposed=proposed,
            persistence_succeeded=False,
        )

    assert captured.value.code is CalendarFailureCode.DATABASE_UNAVAILABLE
    assert original.status_code is CalendarConnectionStatusCode.ACTIVE


def test_calendar_rate_limits_have_exact_boundaries_and_reset() -> None:
    total = FixedWindowCounter(CALENDAR_TOTAL_RATE_LIMIT - 1, NOW)
    availability = FixedWindowCounter(CALENDAR_AVAILABILITY_RATE_LIMIT - 1, NOW)
    allowed = evaluate_calendar_rate_limit(
        operation_code=CalendarOperationCode.AVAILABILITY,
        total_counter=total,
        availability_counter=availability,
        attempted_at=NOW + timedelta(minutes=59),
    )
    blocked = evaluate_calendar_rate_limit(
        operation_code=CalendarOperationCode.AVAILABILITY,
        total_counter=allowed.total_counter,
        availability_counter=allowed.availability_counter,
        attempted_at=NOW + timedelta(minutes=59),
    )
    reset = evaluate_calendar_rate_limit(
        operation_code=CalendarOperationCode.AVAILABILITY,
        total_counter=blocked.total_counter,
        availability_counter=blocked.availability_counter,
        attempted_at=NOW + timedelta(hours=1),
    )

    assert allowed.allowed is True
    assert allowed.availability_counter is not None
    assert allowed.availability_counter.count == CALENDAR_AVAILABILITY_RATE_LIMIT
    assert blocked.allowed is False
    assert blocked.failure_code is CalendarFailureCode.RATE_LIMITED
    assert blocked.retry_after == timedelta(minutes=1)
    assert reset.allowed is True
    assert reset.total_counter.count == 1
    assert reset.availability_counter is not None
    assert reset.availability_counter.count == 1


def test_total_calendar_rate_limit_applies_to_non_availability_operations() -> None:
    allowed = evaluate_calendar_rate_limit(
        operation_code=CalendarOperationCode.EVENT_CREATE,
        total_counter=FixedWindowCounter(CALENDAR_TOTAL_RATE_LIMIT - 1, NOW),
        availability_counter=None,
        attempted_at=NOW,
    )
    blocked = evaluate_calendar_rate_limit(
        operation_code=CalendarOperationCode.PERFORMANCE,
        total_counter=allowed.total_counter,
        availability_counter=None,
        attempted_at=NOW + timedelta(minutes=1),
    )

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert blocked.total_counter.count == CALENDAR_TOTAL_RATE_LIMIT + 1


def test_overlapping_busy_intervals_are_merged_before_slot_calculation() -> None:
    result = calculate_calendar_availability(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Seoul",
        requested_duration_minutes=30,
        busy_intervals=(
            _busy(1, 2),
            _busy(1, 3, start_minute=30),
        ),
    )

    assert result.slots == (
        result.slots[0].__class__(_local(0, 15), _local(0, 45)),
        result.slots[1].__class__(_local(3, 15), _local(23, 45)),
    )


@pytest.mark.parametrize(
    ("gap_minutes", "expected_count"),
    [(60, 1), (59, 0)],
)
def test_buffer_and_minimum_slot_length_boundaries(
    gap_minutes: int,
    expected_count: int,
) -> None:
    gap_start = _local(1)
    gap_end = gap_start + timedelta(minutes=gap_minutes)
    result = calculate_calendar_availability(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Seoul",
        requested_duration_minutes=30,
        busy_intervals=(
            ProviderBusyInterval(_local(0), gap_start),
            ProviderBusyInterval(gap_end, _local(0, day=15)),
        ),
    )

    assert len(result.slots) == expected_count


def test_freebusy_all_day_interval_is_treated_as_busy_under_approved_policy() -> None:
    result = calculate_calendar_availability(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Seoul",
        requested_duration_minutes=30,
        busy_intervals=(ProviderBusyInterval(_local(0), _local(0, day=15)),),
    )

    assert result.slots == ()


def test_slots_are_sorted_and_capped_at_eight() -> None:
    busy_intervals = tuple(
        ProviderBusyInterval(
            _local(hour),
            _local(hour, 15),
        )
        for hour in range(1, 20, 2)
    )
    result = calculate_calendar_availability(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Seoul",
        requested_duration_minutes=30,
        busy_intervals=busy_intervals,
    )

    assert len(result.slots) == MAX_AVAILABILITY_SLOTS
    assert list(result.slots) == sorted(result.slots, key=lambda slot: slot.start_at)


def test_busy_interval_crossing_local_midnight_is_clipped_to_requested_day() -> None:
    result = calculate_calendar_availability(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Seoul",
        requested_duration_minutes=30,
        busy_intervals=(
            ProviderBusyInterval(
                datetime(2026, 8, 13, 14, 30, tzinfo=UTC),
                datetime(2026, 8, 13, 16, 0, tzinfo=UTC),
            ),
        ),
    )

    assert result.slots[0].start_at == _local(1, 15)


@pytest.mark.parametrize(
    ("local_date", "expected_absolute_hours"),
    [
        (date(2026, 3, 8), 22.5),
        (date(2026, 11, 1), 24.5),
    ],
)
def test_dst_day_boundaries_use_local_midnights(
    local_date: date,
    expected_absolute_hours: float,
) -> None:
    result = calculate_calendar_availability(
        local_date=local_date,
        timezone_name="America/New_York",
        requested_duration_minutes=30,
        busy_intervals=(),
    )

    assert len(result.slots) == 1
    duration = result.slots[0].end_at.astimezone(UTC) - result.slots[0].start_at.astimezone(UTC)
    assert duration == timedelta(hours=expected_absolute_hours)


def test_performance_recheck_requires_final_status_and_ten_minutes() -> None:
    workout_id = uuid4()
    final_state = ScheduledWorkoutState(workout_id, ScheduledWorkoutStatusCode.COMPLETED)
    checked_at = NOW

    before = evaluate_performance_recheck(
        scheduled_workout_state=final_state,
        performance_checked_at=checked_at,
        requested_at=checked_at + PERFORMANCE_RECHECK_INTERVAL - timedelta(microseconds=1),
    )
    boundary = evaluate_performance_recheck(
        scheduled_workout_state=final_state,
        performance_checked_at=checked_at,
        requested_at=checked_at + PERFORMANCE_RECHECK_INTERVAL,
    )

    assert before.allowed is False
    assert before.retry_after == timedelta(microseconds=1)
    assert boundary.allowed is True
    with pytest.raises(ValueError, match="finalized"):
        evaluate_performance_recheck(
            scheduled_workout_state=ScheduledWorkoutState(
                workout_id,
                ScheduledWorkoutStatusCode.STARTED,
            ),
            performance_checked_at=None,
            requested_at=NOW,
        )


@pytest.mark.parametrize("performed", [True, False, None])
def test_calendar_performance_cannot_mutate_official_completion(
    performed: bool | None,
) -> None:
    workout_id = uuid4()
    official = OfficialWorkoutState(workout_id, WorkoutSessionStatusCode.PARTIAL)
    observation = CalendarPerformanceObservation(workout_id, performed, NOW)

    preserved = preserve_official_workout_state(
        official_workout_state=official,
        observation=observation,
    )

    assert preserved is official
    assert preserved.status_code is WorkoutSessionStatusCode.PARTIAL
    assert {field.name for field in fields(observation)} == {
        "scheduled_workout_id",
        "performed",
        "performance_checked_at",
    }


def test_google_performance_is_always_null_with_fallback_guidance() -> None:
    observation = google_calendar_performance_observation(
        scheduled_workout_id=uuid4(),
        performance_checked_at=NOW,
    )

    assert observation.performed is None
    guidance = calendar_performance_guidance(observation)
    assert guidance is not None
    assert "앱의 운동 블록 체크" in guidance


def test_manual_availability_wins_even_when_the_user_explicitly_selects_none() -> None:
    calendar = CalendarAvailability(
        local_date=LOCAL_DATE,
        timezone="Asia/Seoul",
        slots=(AvailabilitySlot(_local(10), _local(11)),),
    )

    selected = select_availability(
        manual_override=ManualAvailabilityOverride(slots=()),
        calendar_availability=calendar,
    )

    assert selected.source_code is CalendarAvailabilitySourceCode.MANUAL
    assert selected.slots == ()
    assert selected.manual_choice_preserved is True


def test_calendar_observability_is_allowlist_only(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="calendar-policy-test")
    validate_calendar_observability_fields(SAFE_CALENDAR_OBSERVABILITY_FIELDS)
    assert SAFE_CALENDAR_OBSERVABILITY_FIELDS.isdisjoint(FORBIDDEN_CALENDAR_FIELDS)
    for field_name in FORBIDDEN_CALENDAR_FIELDS:
        with pytest.raises(ValueError, match="unsafe"):
            validate_calendar_observability_fields(frozenset({field_name}))

    logging.getLogger("calendar-policy-test").info(
        "calendar provider unavailable",
        extra={"operation_code": CalendarOperationCode.AVAILABILITY},
    )
    logged = caplog.text.casefold()
    assert all(field_name.casefold() not in logged for field_name in FORBIDDEN_CALENDAR_FIELDS)
