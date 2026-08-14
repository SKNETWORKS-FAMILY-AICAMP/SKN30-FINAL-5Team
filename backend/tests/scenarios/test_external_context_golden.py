from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from backend.app.domain.rules.external_context import (
    CalendarConnectionStatusCode,
    CalendarFailureCode,
    CalendarPerformanceObservation,
    CalendarProviderFailureKindCode,
    OfficialWorkoutState,
    OfficialWorkoutStatusCode,
    ProviderBusyInterval,
    calculate_calendar_availability,
    classify_calendar_provider_failure,
    evaluate_calendar_access,
    google_calendar_performance_observation,
    preserve_official_workout_state,
)
from backend.app.domain.rules.safety import (
    SafetyEvaluation,
    SafetyRequiredActionCode,
    SafetyRuleAvailabilityCode,
    SafetyStatusCode,
)

WORKOUT_ID = UUID("8d4e0be7-a28f-4e5b-8ee2-83bc17dcc1c9")
NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)
SEOUL = ZoneInfo("Asia/Seoul")


def test_golden_unconnected_calendar_keeps_every_core_manual_path() -> None:
    result = evaluate_calendar_access(
        consent_granted=True,
        connection_status_code=None,
    )

    assert result.failure_code is CalendarFailureCode.CALENDAR_NOT_CONNECTED
    assert result.manual_fallback.manual_checkin_available is True
    assert result.manual_fallback.workout_block_check_available is True
    assert result.manual_fallback.plan_mutation_allowed is False


def test_golden_permission_denial_keeps_plan_and_manual_checkin_unchanged() -> None:
    plan = ("approved-plan-item",)
    result = classify_calendar_provider_failure(CalendarProviderFailureKindCode.PERMISSION_DENIED)

    assert plan == ("approved-plan-item",)
    assert result.failure_code is None
    assert result.manual_fallback.manual_checkin_available is True
    assert result.manual_fallback.plan_mutation_allowed is False


def test_golden_performed_true_cannot_change_official_session_status() -> None:
    official = OfficialWorkoutState(WORKOUT_ID, OfficialWorkoutStatusCode.NOT_COMPLETED)
    provider_observation = CalendarPerformanceObservation(WORKOUT_ID, True, NOW)

    result = preserve_official_workout_state(
        official_workout_state=official,
        observation=provider_observation,
    )

    assert result is official
    assert result.status_code is OfficialWorkoutStatusCode.NOT_COMPLETED


def test_golden_google_performed_null_returns_guidance_not_an_error() -> None:
    result = google_calendar_performance_observation(
        scheduled_workout_id=WORKOUT_ID,
        performance_checked_at=NOW,
    )

    assert result.performed is None
    assert result.guidance is not None
    assert "확인할 수 없습니다" in result.guidance


def test_golden_provider_outage_returns_503_contract_without_plan_mutation() -> None:
    plan = ("approved-plan-item",)
    result = classify_calendar_provider_failure(CalendarProviderFailureKindCode.TIMEOUT)

    assert result.failure_code is CalendarFailureCode.PROVIDER_UNAVAILABLE
    assert result.manual_fallback.plan_mutation_allowed is False
    assert plan == ("approved-plan-item",)


def test_golden_provider_outage_cannot_bypass_safety_veto() -> None:
    safety = SafetyEvaluation(
        status_code=SafetyStatusCode.BLOCKED,
        required_action_code=SafetyRequiredActionCode.REST,
        veto=True,
        plan_allowed=False,
        excluded_exercise_codes=(),
        caution_exercise_codes=(),
        applied_rule_codes=(),
        reason_codes=("SEVERE_DISCOMFORT",),
        emergency_reaction_codes=(),
        acute_reaction_codes=(),
        severe_body_area_codes=(),
        safety_rule_set_version=None,
        rule_availability_code=SafetyRuleAvailabilityCode.NOT_REQUIRED,
    )

    provider_failure = classify_calendar_provider_failure(CalendarProviderFailureKindCode.TIMEOUT)

    assert provider_failure.manual_fallback.plan_mutation_allowed is False
    assert safety.status_code is SafetyStatusCode.BLOCKED
    assert safety.veto is True
    assert safety.plan_allowed is False


def test_golden_fully_busy_day_returns_empty_without_shortening_requested_duration() -> None:
    day_start = datetime(2026, 8, 14, 0, 0, tzinfo=SEOUL)
    day_end = datetime(2026, 8, 15, 0, 0, tzinfo=SEOUL)
    result = calculate_calendar_availability(
        local_date=date(2026, 8, 14),
        timezone_name="Asia/Seoul",
        requested_duration_minutes=40,
        busy_intervals=(ProviderBusyInterval(day_start, day_end),),
    )

    assert result.slots == ()
    assert result.requested_duration_minutes == 40


def test_golden_consent_withdrawal_stops_provider_access_but_not_core_flow() -> None:
    result = evaluate_calendar_access(
        consent_granted=False,
        connection_status_code=CalendarConnectionStatusCode.ACTIVE,
    )

    assert result.failure_code is CalendarFailureCode.CONSENT_REQUIRED
    assert result.manual_fallback.manual_checkin_available is True
    assert result.manual_fallback.workout_block_check_available is True
