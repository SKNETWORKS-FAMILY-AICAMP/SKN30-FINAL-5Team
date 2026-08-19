from datetime import date

import pytest

from backend.app.domain.rules.safety import (
    AdverseReactionCode,
    BodyAreaCode,
    Discomfort,
    DiscomfortSeverityCode,
    SafetyContext,
    SafetyRequiredActionCode,
)
from backend.app.domain.rules.workout_execution import (
    DecisionSelectionCode,
    InvalidSessionTransitionError,
    InvalidWorkoutSafetyEventError,
    NotCompletedReasonRequiredError,
    SafetyInstructionCode,
    WorkoutBlockStatusCode,
    WorkoutCompletionEvidence,
    WorkoutNotCompletedReasonCode,
    WorkoutSafetyGuidanceCode,
    WorkoutSafetyReasonCode,
    WorkoutSessionStatusCode,
    WorkoutTimerEventCode,
    classify_workout_safety_event,
    derive_official_session_status,
    finish_session,
    is_terminal_session_status,
    mark_session_not_completed,
    require_block_change_allowed,
    should_send_pressure_notification,
    start_session,
)


def _evidence(
    *statuses: WorkoutBlockStatusCode,
    safety_stopped: bool = False,
    actual_elapsed_seconds: int = 0,
    timer_event_codes: tuple[WorkoutTimerEventCode, ...] = (),
    wearable_workout_detected: bool = False,
    calendar_marked_performed: bool = False,
) -> WorkoutCompletionEvidence:
    return WorkoutCompletionEvidence(
        block_status_codes=statuses,
        safety_stopped=safety_stopped,
        actual_elapsed_seconds=actual_elapsed_seconds,
        timer_event_codes=timer_event_codes,
        wearable_workout_detected=wearable_workout_detected,
        calendar_marked_performed=calendar_marked_performed,
    )


def test_all_completed_blocks_are_officially_completed() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.COMPLETED,
        WorkoutBlockStatusCode.COMPLETED,
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.COMPLETED


def test_some_completed_blocks_are_officially_partial() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.COMPLETED,
        WorkoutBlockStatusCode.PENDING,
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.PARTIAL


def test_no_completed_blocks_are_officially_not_completed() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.PENDING,
        WorkoutBlockStatusCode.PENDING,
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.NOT_COMPLETED


def test_safety_stop_has_priority_over_completed_blocks() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.COMPLETED,
        WorkoutBlockStatusCode.COMPLETED,
        safety_stopped=True,
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY


def test_elapsed_time_and_timer_events_do_not_complete_blocks() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.PENDING,
        actual_elapsed_seconds=7200,
        timer_event_codes=(
            WorkoutTimerEventCode.START,
            WorkoutTimerEventCode.PAUSE,
            WorkoutTimerEventCode.RESUME,
            WorkoutTimerEventCode.END,
        ),
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.NOT_COMPLETED


def test_wearable_detection_does_not_complete_blocks() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.PENDING,
        wearable_workout_detected=True,
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.NOT_COMPLETED


def test_calendar_performance_mark_does_not_complete_blocks() -> None:
    evidence = _evidence(
        WorkoutBlockStatusCode.PENDING,
        calendar_marked_performed=True,
    )

    assert derive_official_session_status(evidence) is WorkoutSessionStatusCode.NOT_COMPLETED


def test_session_start_and_finish_follow_block_state() -> None:
    started = start_session(WorkoutSessionStatusCode.PLANNED)
    result = finish_session(
        started,
        _evidence(WorkoutBlockStatusCode.COMPLETED, WorkoutBlockStatusCode.PENDING),
    )

    assert result is WorkoutSessionStatusCode.PARTIAL


def test_finish_with_zero_blocks_requires_not_completed_reason_path() -> None:
    evidence = _evidence(WorkoutBlockStatusCode.PENDING)

    with pytest.raises(NotCompletedReasonRequiredError):
        finish_session(WorkoutSessionStatusCode.IN_PROGRESS, evidence)

    assert (
        mark_session_not_completed(
            WorkoutSessionStatusCode.IN_PROGRESS,
            evidence,
            WorkoutNotCompletedReasonCode.TIME_SHORTAGE,
        )
        is WorkoutSessionStatusCode.NOT_COMPLETED
    )


@pytest.mark.parametrize(
    "terminal_status",
    [
        WorkoutSessionStatusCode.COMPLETED,
        WorkoutSessionStatusCode.PARTIAL,
        WorkoutSessionStatusCode.NOT_COMPLETED,
        WorkoutSessionStatusCode.STOPPED_FOR_SAFETY,
    ],
)
def test_terminal_sessions_cannot_change_block_status(
    terminal_status: WorkoutSessionStatusCode,
) -> None:
    assert is_terminal_session_status(terminal_status) is True

    with pytest.raises(InvalidSessionTransitionError):
        require_block_change_allowed(terminal_status)


def test_only_in_progress_session_can_change_block_status() -> None:
    require_block_change_allowed(WorkoutSessionStatusCode.IN_PROGRESS)

    with pytest.raises(InvalidSessionTransitionError):
        require_block_change_allowed(WorkoutSessionStatusCode.PLANNED)


def test_mild_safety_event_shows_caution_without_rewriting_session() -> None:
    decision = classify_workout_safety_event(
        WorkoutSessionStatusCode.IN_PROGRESS,
        SafetyContext(discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)),
    )

    assert decision.instruction_code is SafetyInstructionCode.SHOW_CAUTION
    assert decision.resulting_action_code is None
    assert decision.session_status_code is WorkoutSessionStatusCode.IN_PROGRESS
    assert decision.reason_code is WorkoutSafetyReasonCode.MILD_DISCOMFORT
    assert decision.guidance_code is WorkoutSafetyGuidanceCode.MILD_DISCOMFORT_CAUTION
    assert decision.veto is False


def test_severe_safety_event_stops_session_with_rest_veto() -> None:
    decision = classify_workout_safety_event(
        WorkoutSessionStatusCode.IN_PROGRESS,
        SafetyContext(discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.SEVERE),)),
    )

    assert decision.instruction_code is SafetyInstructionCode.STOP_SESSION
    assert decision.resulting_action_code is SafetyRequiredActionCode.REST
    assert decision.session_status_code is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
    assert decision.reason_code is WorkoutSafetyReasonCode.SEVERE_DISCOMFORT
    assert decision.guidance_code is WorkoutSafetyGuidanceCode.SEVERE_OR_ACUTE_STOP
    assert decision.veto is True


def test_acute_musculoskeletal_event_stops_session_with_reason_and_guidance() -> None:
    decision = classify_workout_safety_event(
        WorkoutSessionStatusCode.IN_PROGRESS,
        SafetyContext(adverse_reaction_codes=(AdverseReactionCode.SUDDEN_SEVERE_PAIN,)),
    )

    assert decision.instruction_code is SafetyInstructionCode.STOP_SESSION
    assert decision.resulting_action_code is SafetyRequiredActionCode.REST
    assert decision.session_status_code is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
    assert decision.reason_code is WorkoutSafetyReasonCode.ACUTE_MUSCULOSKELETAL_REACTION
    assert decision.guidance_code is WorkoutSafetyGuidanceCode.SEVERE_OR_ACUTE_STOP
    assert decision.veto is True


def test_emergency_safety_event_has_priority_and_cannot_be_bypassed() -> None:
    decision = classify_workout_safety_event(
        WorkoutSessionStatusCode.IN_PROGRESS,
        SafetyContext(
            discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.SEVERE),),
            adverse_reaction_codes=(
                AdverseReactionCode.SUDDEN_SEVERE_PAIN,
                AdverseReactionCode.CHEST_DISCOMFORT,
            ),
        ),
    )

    assert decision.instruction_code is SafetyInstructionCode.STOP_AND_SEEK_HELP
    assert decision.resulting_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert decision.session_status_code is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
    assert decision.reason_code is WorkoutSafetyReasonCode.EMERGENCY_ADVERSE_REACTION
    assert decision.guidance_code is WorkoutSafetyGuidanceCode.SERIOUS_ADVERSE_REACTION_STOP
    assert decision.veto is True


def test_empty_safety_event_is_rejected() -> None:
    with pytest.raises(InvalidWorkoutSafetyEventError):
        classify_workout_safety_event(
            WorkoutSessionStatusCode.IN_PROGRESS,
            SafetyContext(),
        )


def test_safety_event_cannot_change_a_terminal_session() -> None:
    with pytest.raises(InvalidSessionTransitionError):
        classify_workout_safety_event(
            WorkoutSessionStatusCode.COMPLETED,
            SafetyContext(
                discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.MILD),)
            ),
        )


def test_rest_selection_suppresses_same_day_pressure_notification() -> None:
    local_date = date(2026, 8, 14)

    assert (
        should_send_pressure_notification(
            selection_code=DecisionSelectionCode.REST,
            selection_local_date=local_date,
            notification_local_date=local_date,
        )
        is False
    )
    assert (
        should_send_pressure_notification(
            selection_code=DecisionSelectionCode.REST,
            selection_local_date=local_date,
            notification_local_date=date(2026, 8, 15),
        )
        is True
    )
