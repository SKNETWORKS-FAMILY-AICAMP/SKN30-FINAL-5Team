from dataclasses import dataclass, replace
from datetime import date

import pytest

from backend.app.domain.rules.return_mode import (
    ApprovedReturnCapPolicyPort,
    ReturnCapReviewStatusCode,
    ReturnModeStatusCode,
    ReturnPlanApplicationStatusCode,
    apply_return_plan_policy,
    evaluate_return_mode,
)
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
    SafetyInstructionCode,
    WorkoutBlockStatusCode,
    WorkoutCompletionEvidence,
    WorkoutSessionStatusCode,
    WorkoutTimerEventCode,
    classify_workout_safety_event,
    derive_official_session_status,
    should_send_pressure_notification,
)


@pytest.mark.parametrize(
    ("evidence", "expected_status"),
    [
        (
            WorkoutCompletionEvidence(
                block_status_codes=(
                    WorkoutBlockStatusCode.COMPLETED,
                    WorkoutBlockStatusCode.COMPLETED,
                )
            ),
            WorkoutSessionStatusCode.COMPLETED,
        ),
        (
            WorkoutCompletionEvidence(
                block_status_codes=(
                    WorkoutBlockStatusCode.COMPLETED,
                    WorkoutBlockStatusCode.PENDING,
                )
            ),
            WorkoutSessionStatusCode.PARTIAL,
        ),
        (
            WorkoutCompletionEvidence(
                block_status_codes=(WorkoutBlockStatusCode.PENDING,),
                actual_elapsed_seconds=5400,
                timer_event_codes=(
                    WorkoutTimerEventCode.START,
                    WorkoutTimerEventCode.END,
                ),
                wearable_workout_detected=True,
                calendar_marked_performed=True,
            ),
            WorkoutSessionStatusCode.NOT_COMPLETED,
        ),
        (
            WorkoutCompletionEvidence(
                block_status_codes=(WorkoutBlockStatusCode.COMPLETED,),
                safety_stopped=True,
            ),
            WorkoutSessionStatusCode.STOPPED_FOR_SAFETY,
        ),
    ],
)
def test_golden_official_status_uses_only_blocks_and_safety_stop(
    evidence: WorkoutCompletionEvidence,
    expected_status: WorkoutSessionStatusCode,
) -> None:
    assert derive_official_session_status(evidence) is expected_status


def test_golden_severe_event_stops_for_safety_with_rest() -> None:
    decision = classify_workout_safety_event(
        WorkoutSessionStatusCode.IN_PROGRESS,
        SafetyContext(discomforts=(Discomfort(BodyAreaCode.KNEE, DiscomfortSeverityCode.SEVERE),)),
    )

    assert decision.instruction_code is SafetyInstructionCode.STOP_SESSION
    assert decision.resulting_action_code is SafetyRequiredActionCode.REST
    assert decision.session_status_code is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
    assert decision.veto is True


def test_golden_emergency_event_keeps_stop_and_seek_help_veto() -> None:
    decision = classify_workout_safety_event(
        WorkoutSessionStatusCode.IN_PROGRESS,
        SafetyContext(adverse_reaction_codes=(AdverseReactionCode.CHEST_DISCOMFORT,)),
    )

    assert decision.instruction_code is SafetyInstructionCode.STOP_AND_SEEK_HELP
    assert decision.resulting_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP
    assert decision.session_status_code is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
    assert decision.veto is True


@dataclass(frozen=True, slots=True)
class _ReturnPlan:
    requested_duration_minutes: int
    load_cap_applied: bool = False
    volume_cap_applied: bool = False


@dataclass(slots=True)
class _ApprovedGoldenCapPolicy(ApprovedReturnCapPolicyPort[_ReturnPlan]):
    version_code: str = "golden-approved-return-v1"
    review_status_code: ReturnCapReviewStatusCode = ReturnCapReviewStatusCode.DOMAIN_APPROVED
    production_eligible: bool = True
    load_cap_code: str = "GOLDEN_APPROVED_LOAD_CAP"
    volume_cap_code: str = "GOLDEN_APPROVED_VOLUME_CAP"

    def apply(self, plan: _ReturnPlan) -> _ReturnPlan:
        return replace(plan, load_cap_applied=True, volume_cap_applied=True)


def test_golden_14_day_return_preserves_time_and_applies_only_approved_caps() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 15),
        last_completed_local_date=date(2026, 8, 1),
        not_completed_history_count=3,
    )
    application = apply_return_plan_policy(
        evaluation,
        _ReturnPlan(requested_duration_minutes=40),
        _ApprovedGoldenCapPolicy(),
    )

    assert evaluation.status_code is ReturnModeStatusCode.RETURN_MODE
    assert evaluation.penalty_applied is False
    assert application.status_code is ReturnPlanApplicationStatusCode.APPROVED_CAPS_APPLIED
    assert application.requested_duration_minutes == 40
    assert application.plan == _ReturnPlan(
        requested_duration_minutes=40,
        load_cap_applied=True,
        volume_cap_applied=True,
    )


def test_golden_rest_selection_blocks_same_day_pressure() -> None:
    local_date = date(2026, 8, 14)

    assert (
        should_send_pressure_notification(
            selection_code=DecisionSelectionCode.REST,
            selection_local_date=local_date,
            notification_local_date=local_date,
        )
        is False
    )
