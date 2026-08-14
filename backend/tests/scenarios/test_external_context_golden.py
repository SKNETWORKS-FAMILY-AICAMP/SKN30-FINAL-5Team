from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from backend.app.domain.rules.external_context import (
    CALENDAR_PERFORMANCE_UNAVAILABLE_MESSAGE_KO,
    CalendarBusyInterval,
    CalendarConnectionStatusCode,
    CalendarFallbackReasonCode,
    CalendarPerformanceGuidanceCode,
    CalendarPerformanceObservation,
    CalendarProviderFailureKindCode,
    CalendarPublicFailureCode,
    calculate_calendar_availability,
    calendar_provider_failure_fallback,
    evaluate_calendar_access,
    google_calendar_performance_observation,
    preserve_official_completion_status,
)
from backend.app.domain.rules.safety import (
    AdverseReactionCode,
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyContext,
    SafetyRequiredActionCode,
    evaluate_safety,
)
from backend.app.domain.rules.workout_execution import (
    DecisionSelectionCode,
    WorkoutSessionStatusCode,
    should_send_pressure_notification,
)

NOW = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
WORKOUT_ID = UUID("e6d11237-717b-48f5-bc87-9bb4560c9be2")


def test_golden_calendar_not_connected_keeps_all_core_manual_flows() -> None:
    result = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=None,
    )

    assert result.failure_code is CalendarPublicFailureCode.CALENDAR_NOT_CONNECTED
    assert result.manual_fallback_required is True
    assert result.workout_plan_preserved is True
    assert result.official_completion_unchanged is True


def test_golden_permission_denied_keeps_manual_checkin_and_plan() -> None:
    result = calendar_provider_failure_fallback(CalendarProviderFailureKindCode.PERMISSION_DENIED)

    assert result.fallback_reason_code is CalendarFallbackReasonCode.PERMISSION_DENIED
    assert result.manual_fallback_required is True
    assert result.workout_plan_preserved is True


def test_golden_performed_true_cannot_complete_an_unchecked_workout() -> None:
    observation = CalendarPerformanceObservation(
        scheduled_workout_id=WORKOUT_ID,
        performed=True,
        performance_checked_at=NOW,
    )
    result = preserve_official_completion_status(
        official_session_status_code=WorkoutSessionStatusCode.NOT_COMPLETED,
        observation=observation,
    )

    assert result.official_session_status_code is WorkoutSessionStatusCode.NOT_COMPLETED


def test_golden_google_performed_null_is_supported_fallback_not_an_error() -> None:
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
    assert result.official_session_status_code is WorkoutSessionStatusCode.COMPLETED


def test_golden_provider_outage_returns_safe_503_without_deleting_plan() -> None:
    result = calendar_provider_failure_fallback(CalendarProviderFailureKindCode.UNAVAILABLE)

    assert result.failure_code is CalendarPublicFailureCode.PROVIDER_UNAVAILABLE
    assert result.workout_plan_preserved is True
    assert result.manual_fallback_required is True


def test_golden_full_day_busy_returns_empty_without_shortening_requested_duration() -> None:
    requested_duration_minutes = 40
    availability = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="UTC",
        requested_duration_minutes=requested_duration_minutes,
        busy_intervals=(CalendarBusyInterval(start_at=NOW, end_at=NOW + timedelta(days=1)),),
    )

    assert availability.slots == ()
    assert requested_duration_minutes == 40


def test_golden_external_context_cannot_bypass_emergency_safety_veto() -> None:
    safety = evaluate_safety(
        SafetyContext(adverse_reaction_codes=(AdverseReactionCode.CHEST_DISCOMFORT,)),
        SafetyCandidate(
            items=(
                SafetyCandidateItem(
                    exercise_code="SYNTHETIC_WALK",
                    catalog_version_code="catalog-test-v1",
                    movement_pattern_code="LOCOMOTION",
                ),
            )
        ),
        None,
    )
    calendar = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )

    assert calendar.provider_call_allowed is True
    assert safety.veto is True
    assert safety.required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert safety.plan_allowed is False


def test_golden_calendar_context_cannot_pressure_a_user_who_selected_rest() -> None:
    local_date = date(2026, 8, 14)
    calendar = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )

    assert calendar.provider_call_allowed is True
    assert (
        should_send_pressure_notification(
            selection_code=DecisionSelectionCode.REST,
            selection_local_date=local_date,
            notification_local_date=local_date,
        )
        is False
    )
