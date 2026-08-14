from datetime import date, datetime

from backend.app.domain.rules.safety import SafetyStatusCode
from backend.app.domain.rules.weekly_plan import (
    PlanConstraints,
    PlanFinalizationContext,
    PlanRevisionEndpointCode,
    PlanRevisionPolicyInput,
    PlanRevisionSourceCode,
    PlanRoutineEvidence,
    RoutineDecisionAuthorityCode,
    SafetyDecisionAuthorityCode,
    evaluate_plan_finalization,
    evaluate_plan_revision,
)
from backend.app.domain.rules.weekly_report import (
    WeeklyReportStatusCode,
    acknowledge_weekly_report,
    build_closed_week_aggregate,
    weekly_boundary_for,
)


def _weekly_plan_input() -> PlanRevisionPolicyInput:
    constraints = PlanConstraints(
        requested_duration_minutes=40,
        allowed_location_codes=("HOME",),
        available_equipment_codes=("MAT",),
        required_safety_opinion_codes=("AVOID_KNEE_LOAD",),
    )
    return PlanRevisionPolicyInput(
        endpoint_code=PlanRevisionEndpointCode.PLAN_REVISIONS,
        source_code=PlanRevisionSourceCode.AI,
        safety_status_code=SafetyStatusCode.REVISE,
        successful_ai_revision_count=0,
        constraints=constraints,
        routine=PlanRoutineEvidence(
            routine_reference="weekly-routine-v1",
            requested_duration_minutes=40,
            location_code="HOME",
            required_equipment_codes=("MAT",),
            applied_safety_opinion_codes=("AVOID_KNEE_LOAD",),
            routine_decision_authority_code=RoutineDecisionAuthorityCode.COORDINATOR,
            safety_decision_authority_code=SafetyDecisionAuthorityCode.SAFETY_AGENT,
        ),
    )


def test_golden_closed_report_acknowledgement_unlocks_next_plan() -> None:
    boundary = weekly_boundary_for(local_date=date(2026, 8, 9), timezone_name="Asia/Seoul")
    aggregate = build_closed_week_aggregate(
        boundary=boundary,
        requested_at=datetime.fromisoformat("2026-08-10T09:00:00+09:00"),
        completed_count=2,
        partial_count=1,
        not_completed_count=1,
        stopped_for_safety_count=0,
        primary_miss_reason_code="TIME_SHORTAGE",
    )
    revision = evaluate_plan_revision(_weekly_plan_input())
    report_status = acknowledge_weekly_report(WeeklyReportStatusCode.GENERATED)
    finalization = evaluate_plan_finalization(
        revision_decision=revision,
        safety_status_code=SafetyStatusCode.REVISE,
        routine_present=True,
        context=PlanFinalizationContext(
            is_first_user_week=False,
            cold_start_applied=False,
            previous_report_status_code=report_status,
        ),
    )

    assert aggregate.penalty_applied is False
    assert report_status is WeeklyReportStatusCode.ACKNOWLEDGED
    assert revision.resulting_ai_revision_count == 1
    assert finalization.finalized is True


def test_golden_same_input_and_policy_version_has_identical_result() -> None:
    policy_input = _weekly_plan_input()

    first = evaluate_plan_revision(policy_input)
    second = evaluate_plan_revision(policy_input)

    assert first == second
    assert first.weekly_plan_policy_version == policy_input.weekly_plan_policy_version
