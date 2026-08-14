from dataclasses import dataclass, replace
from datetime import date

import pytest

from backend.app.domain.rules.return_mode import (
    RETURN_MODE_COMPLETION_GAP_DAYS,
    ApprovedReturnCapPolicyPort,
    InvalidReturnModeInputError,
    ReturnCapReviewStatusCode,
    ReturnDurationViolationError,
    ReturnModeReasonCode,
    ReturnModeStatusCode,
    ReturnPlanApplicationStatusCode,
    WorkoutLearningSignalCode,
    apply_return_plan_policy,
    evaluate_return_mode,
)


@dataclass(frozen=True, slots=True)
class _Plan:
    requested_duration_minutes: int
    load_policy_marker: str
    volume_policy_marker: str


@dataclass(slots=True)
class _CapPolicy(ApprovedReturnCapPolicyPort[_Plan]):
    version_code: str = "approved-return-policy-v1"
    review_status_code: ReturnCapReviewStatusCode = ReturnCapReviewStatusCode.DOMAIN_APPROVED
    production_eligible: bool = True
    load_cap_code: str = "APPROVED_LOAD_CAP"
    volume_cap_code: str = "APPROVED_VOLUME_CAP"
    applied: bool = False
    shorten_duration: bool = False

    def apply(self, plan: _Plan) -> _Plan:
        self.applied = True
        return replace(
            plan,
            requested_duration_minutes=(
                plan.requested_duration_minutes - 1
                if self.shorten_duration
                else plan.requested_duration_minutes
            ),
            load_policy_marker=self.load_cap_code,
            volume_policy_marker=self.volume_cap_code,
        )


def test_return_mode_is_not_active_before_14_day_completion_gap() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 14),
        last_completed_local_date=date(2026, 8, 1),
    )

    assert RETURN_MODE_COMPLETION_GAP_DAYS == 14
    assert evaluation.status_code is ReturnModeStatusCode.STANDARD
    assert evaluation.days_since_last_completed == 13
    assert evaluation.reason_codes == ()


def test_return_mode_activates_at_exactly_14_days_since_completion() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 15),
        last_completed_local_date=date(2026, 8, 1),
    )

    assert evaluation.status_code is ReturnModeStatusCode.RETURN_MODE
    assert evaluation.days_since_last_completed == 14
    assert evaluation.reason_codes == (ReturnModeReasonCode.COMPLETION_GAP_14_DAYS,)


def test_not_completed_history_is_learning_signal_not_return_trigger_or_penalty() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 14),
        last_completed_local_date=date(2026, 8, 13),
        not_completed_history_count=3,
    )

    assert evaluation.status_code is ReturnModeStatusCode.STANDARD
    assert evaluation.learning_signal_codes == (WorkoutLearningSignalCode.NOT_COMPLETED_HISTORY,)
    assert evaluation.penalty_applied is False


def test_cold_start_without_completion_does_not_enter_return_mode() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 14),
        last_completed_local_date=None,
        not_completed_history_count=4,
    )

    assert evaluation.status_code is ReturnModeStatusCode.STANDARD
    assert evaluation.days_since_last_completed is None


def test_future_completion_date_is_rejected() -> None:
    with pytest.raises(InvalidReturnModeInputError):
        evaluate_return_mode(
            current_local_date=date(2026, 8, 14),
            last_completed_local_date=date(2026, 8, 15),
        )


def test_return_mode_fails_closed_when_approved_caps_are_missing() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 15),
        last_completed_local_date=date(2026, 8, 1),
    )
    plan = _Plan(40, "BASE_LOAD", "BASE_VOLUME")

    application = apply_return_plan_policy(evaluation, plan, None)

    assert application.status_code is ReturnPlanApplicationStatusCode.APPROVED_CAPS_REQUIRED
    assert application.requested_duration_minutes == 40
    assert application.plan is None
    assert application.cap_policy_version is None


def test_approved_caps_are_applied_while_requested_duration_is_preserved() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 15),
        last_completed_local_date=date(2026, 8, 1),
    )
    plan = _Plan(40, "BASE_LOAD", "BASE_VOLUME")
    policy = _CapPolicy()

    application = apply_return_plan_policy(evaluation, plan, policy)

    assert policy.applied is True
    assert application.status_code is ReturnPlanApplicationStatusCode.APPROVED_CAPS_APPLIED
    assert application.requested_duration_minutes == 40
    assert application.plan == _Plan(
        40,
        "APPROVED_LOAD_CAP",
        "APPROVED_VOLUME_CAP",
    )
    assert application.cap_policy_version == "approved-return-policy-v1"


def test_unapproved_caps_are_not_applied() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 15),
        last_completed_local_date=date(2026, 8, 1),
    )
    policy = _CapPolicy(review_status_code=ReturnCapReviewStatusCode.DRAFT)

    application = apply_return_plan_policy(
        evaluation,
        _Plan(40, "BASE_LOAD", "BASE_VOLUME"),
        policy,
    )

    assert policy.applied is False
    assert application.status_code is ReturnPlanApplicationStatusCode.APPROVED_CAPS_REQUIRED
    assert application.plan is None


def test_approved_return_policy_cannot_shorten_requested_duration() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 15),
        last_completed_local_date=date(2026, 8, 1),
    )
    policy = _CapPolicy(shorten_duration=True)

    with pytest.raises(ReturnDurationViolationError):
        apply_return_plan_policy(
            evaluation,
            _Plan(40, "BASE_LOAD", "BASE_VOLUME"),
            policy,
        )


def test_standard_mode_does_not_require_or_claim_return_caps() -> None:
    evaluation = evaluate_return_mode(
        current_local_date=date(2026, 8, 14),
        last_completed_local_date=date(2026, 8, 13),
    )
    plan = _Plan(40, "BASE_LOAD", "BASE_VOLUME")

    application = apply_return_plan_policy(evaluation, plan, None)

    assert application.status_code is ReturnPlanApplicationStatusCode.PLAN_ALLOWED
    assert application.plan is plan
    assert application.load_cap_code is None
    assert application.volume_cap_code is None
