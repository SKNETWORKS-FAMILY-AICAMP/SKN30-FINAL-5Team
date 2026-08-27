from dataclasses import replace

import pytest

from backend.app.domain.rules.safety import SafetyStatusCode
from backend.app.domain.rules.weekly_plan import (
    MAX_SUCCESSFUL_AI_REVISIONS,
    WEEKLY_PLAN_POLICY_VERSION,
    InvalidWeeklyPlanInputError,
    PlanConstraints,
    PlanFinalizationContext,
    PlanFinalizationReasonCode,
    PlanRevisionEndpointCode,
    PlanRevisionPolicyInput,
    PlanRevisionReasonCode,
    PlanRevisionSourceCode,
    PlanRoutineEvidence,
    RoutineDecisionAuthorityCode,
    SafetyDecisionAuthorityCode,
    evaluate_plan_finalization,
    evaluate_plan_revision,
)
from backend.app.domain.rules.weekly_report import WeeklyReportStatusCode


@pytest.fixture
def constraints() -> PlanConstraints:
    return PlanConstraints(
        requested_duration_minutes=40,
        allowed_location_codes=("GYM", "HOME"),
        available_equipment_codes=("BAND", "MAT"),
        required_safety_opinion_codes=("EXCLUDE_KNEE_LOAD",),
    )


def _routine(
    *,
    authority: RoutineDecisionAuthorityCode = RoutineDecisionAuthorityCode.COORDINATOR,
) -> PlanRoutineEvidence:
    return PlanRoutineEvidence(
        routine_reference="routine-v2",
        requested_duration_minutes=40,
        location_code="HOME",
        required_equipment_codes=("MAT",),
        applied_safety_opinion_codes=("EXCLUDE_KNEE_LOAD",),
        routine_decision_authority_code=authority,
        safety_decision_authority_code=SafetyDecisionAuthorityCode.SAFETY_AGENT,
    )


def _ai_input(
    constraints: PlanConstraints,
    *,
    successful_ai_revision_count: int,
    safety_status_code: SafetyStatusCode = SafetyStatusCode.REVISE,
    routine: PlanRoutineEvidence | None = None,
) -> PlanRevisionPolicyInput:
    return PlanRevisionPolicyInput(
        endpoint_code=PlanRevisionEndpointCode.PLAN_REVISIONS,
        source_code=PlanRevisionSourceCode.AI,
        safety_status_code=safety_status_code,
        successful_ai_revision_count=successful_ai_revision_count,
        constraints=constraints,
        routine=_routine()
        if routine is None and safety_status_code is SafetyStatusCode.REVISE
        else routine,
    )


@pytest.mark.parametrize(
    ("prior_count", "result_count"),
    [(0, 1), (1, 2)],
)
def test_first_and_second_coordinator_ai_revisions_are_allowed(
    constraints: PlanConstraints,
    prior_count: int,
    result_count: int,
) -> None:
    decision = evaluate_plan_revision(
        _ai_input(constraints, successful_ai_revision_count=prior_count)
    )

    assert MAX_SUCCESSFUL_AI_REVISIONS == 2
    assert decision.revision_allowed is True
    assert decision.resulting_ai_revision_count == result_count
    assert decision.weekly_plan_policy_version == WEEKLY_PLAN_POLICY_VERSION


def test_third_ai_revision_is_blocked(constraints: PlanConstraints) -> None:
    decision = evaluate_plan_revision(_ai_input(constraints, successful_ai_revision_count=2))

    assert decision.revision_allowed is False
    assert decision.resulting_ai_revision_count == 2
    assert PlanRevisionReasonCode.AI_REVISION_LIMIT_REACHED in decision.reason_codes


@pytest.mark.parametrize(
    ("endpoint_code", "source_code"),
    [
        (PlanRevisionEndpointCode.INITIAL_PLAN, PlanRevisionSourceCode.AI),
        (PlanRevisionEndpointCode.PLAN_REVISIONS, PlanRevisionSourceCode.INITIAL),
    ],
)
def test_revision_source_must_match_its_endpoint(
    constraints: PlanConstraints,
    endpoint_code: PlanRevisionEndpointCode,
    source_code: PlanRevisionSourceCode,
) -> None:
    decision = evaluate_plan_revision(
        PlanRevisionPolicyInput(
            endpoint_code=endpoint_code,
            source_code=source_code,
            safety_status_code=SafetyStatusCode.PASS,
            successful_ai_revision_count=0,
            constraints=constraints,
            routine=_routine(),
        )
    )

    assert decision.revision_allowed is False
    assert PlanRevisionReasonCode.SOURCE_ENDPOINT_MISMATCH in decision.reason_codes


@pytest.mark.parametrize(
    "status_code",
    [SafetyStatusCode.NEEDS_INPUT, SafetyStatusCode.BLOCKED, SafetyStatusCode.FAILED],
)
def test_non_plan_revision_statuses_have_no_routine_and_cannot_finalize(
    constraints: PlanConstraints,
    status_code: SafetyStatusCode,
) -> None:
    revision = evaluate_plan_revision(
        _ai_input(
            constraints,
            successful_ai_revision_count=1,
            safety_status_code=status_code,
            routine=None,
        )
    )
    finalization = evaluate_plan_finalization(
        revision_decision=revision,
        safety_status_code=status_code,
        routine_present=False,
        context=PlanFinalizationContext(
            is_first_user_week=False,
            cold_start_applied=False,
            previous_report_status_code=WeeklyReportStatusCode.ACKNOWLEDGED,
        ),
    )

    assert revision.revision_allowed is True
    assert revision.routine_allowed is False
    assert revision.resulting_ai_revision_count == 1
    assert finalization.finalized is False
    assert PlanFinalizationReasonCode.REVISION_STATUS_BLOCKS_FINALIZE in finalization.reason_codes


def test_safety_veto_cannot_carry_a_routine(constraints: PlanConstraints) -> None:
    decision = evaluate_plan_revision(
        _ai_input(
            constraints,
            successful_ai_revision_count=0,
            safety_status_code=SafetyStatusCode.BLOCKED,
            routine=_routine(),
        )
    )

    assert decision.revision_allowed is False
    assert decision.routine_allowed is False
    assert PlanRevisionReasonCode.ROUTINE_FORBIDDEN in decision.reason_codes


def test_generated_report_blocks_finalize_until_acknowledged(
    constraints: PlanConstraints,
) -> None:
    revision = evaluate_plan_revision(_ai_input(constraints, successful_ai_revision_count=0))
    generated_context = PlanFinalizationContext(
        is_first_user_week=False,
        cold_start_applied=False,
        previous_report_status_code=WeeklyReportStatusCode.GENERATED,
    )

    blocked = evaluate_plan_finalization(
        revision_decision=revision,
        safety_status_code=SafetyStatusCode.REVISE,
        routine_present=True,
        context=generated_context,
    )
    allowed = evaluate_plan_finalization(
        revision_decision=revision,
        safety_status_code=SafetyStatusCode.REVISE,
        routine_present=True,
        context=replace(
            generated_context,
            previous_report_status_code=WeeklyReportStatusCode.ACKNOWLEDGED,
        ),
    )

    assert blocked.finalized is False
    assert (
        PlanFinalizationReasonCode.PREVIOUS_REPORT_ACKNOWLEDGEMENT_REQUIRED in blocked.reason_codes
    )
    assert allowed.finalized is True


def test_first_cold_start_week_is_the_only_acknowledgement_exception(
    constraints: PlanConstraints,
) -> None:
    initial_revision = evaluate_plan_revision(
        PlanRevisionPolicyInput(
            endpoint_code=PlanRevisionEndpointCode.INITIAL_PLAN,
            source_code=PlanRevisionSourceCode.INITIAL,
            safety_status_code=SafetyStatusCode.PASS,
            successful_ai_revision_count=0,
            constraints=constraints,
            routine=_routine(),
        )
    )

    decision = evaluate_plan_finalization(
        revision_decision=initial_revision,
        safety_status_code=SafetyStatusCode.PASS,
        routine_present=True,
        context=PlanFinalizationContext(
            is_first_user_week=True,
            cold_start_applied=True,
            previous_report_status_code=None,
        ),
    )

    assert decision.finalized is True
    with pytest.raises(InvalidWeeklyPlanInputError, match="first user week"):
        PlanFinalizationContext(
            is_first_user_week=False,
            cold_start_applied=True,
            previous_report_status_code=None,
        )


@pytest.mark.parametrize(
    ("routine", "reason_code"),
    [
        (
            replace(
                _routine(authority=RoutineDecisionAuthorityCode.USER), requested_duration_minutes=30
            ),
            PlanRevisionReasonCode.REQUESTED_DURATION_NOT_PRESERVED,
        ),
        (
            replace(_routine(authority=RoutineDecisionAuthorityCode.USER), location_code="OUTDOOR"),
            PlanRevisionReasonCode.LOCATION_CONSTRAINT_NOT_SATISFIED,
        ),
        (
            replace(
                _routine(authority=RoutineDecisionAuthorityCode.USER),
                applied_safety_opinion_codes=(),
            ),
            PlanRevisionReasonCode.SAFETY_OPINION_NOT_APPLIED,
        ),
    ],
)
def test_user_edits_must_preserve_all_constraints(
    constraints: PlanConstraints,
    routine: PlanRoutineEvidence,
    reason_code: PlanRevisionReasonCode,
) -> None:
    decision = evaluate_plan_revision(
        PlanRevisionPolicyInput(
            endpoint_code=PlanRevisionEndpointCode.PLAN_REVISIONS,
            source_code=PlanRevisionSourceCode.USER,
            safety_status_code=SafetyStatusCode.REVISE,
            successful_ai_revision_count=2,
            constraints=constraints,
            routine=routine,
        )
    )

    assert decision.revision_allowed is False
    assert reason_code in decision.reason_codes


def test_user_edit_is_allowed_after_two_ai_revisions_when_constraints_hold(
    constraints: PlanConstraints,
) -> None:
    decision = evaluate_plan_revision(
        PlanRevisionPolicyInput(
            endpoint_code=PlanRevisionEndpointCode.PLAN_REVISIONS,
            source_code=PlanRevisionSourceCode.USER,
            safety_status_code=SafetyStatusCode.REVISE,
            successful_ai_revision_count=2,
            constraints=constraints,
            routine=_routine(authority=RoutineDecisionAuthorityCode.USER),
        )
    )

    assert decision.revision_allowed is True
    assert decision.resulting_ai_revision_count == 2


def test_user_edit_is_not_blocked_by_equipment_availability(
    constraints: PlanConstraints,
) -> None:
    decision = evaluate_plan_revision(
        PlanRevisionPolicyInput(
            endpoint_code=PlanRevisionEndpointCode.PLAN_REVISIONS,
            source_code=PlanRevisionSourceCode.USER,
            safety_status_code=SafetyStatusCode.REVISE,
            successful_ai_revision_count=2,
            constraints=constraints,
            routine=replace(
                _routine(authority=RoutineDecisionAuthorityCode.USER),
                required_equipment_codes=("DUMBBELL",),
            ),
        )
    )

    assert decision.revision_allowed is True
    assert PlanRevisionReasonCode.EQUIPMENT_CONSTRAINT_NOT_SATISFIED not in decision.reason_codes


def test_llm_cannot_change_routine_or_safety(constraints: PlanConstraints) -> None:
    decision = evaluate_plan_revision(
        replace(
            _ai_input(constraints, successful_ai_revision_count=0),
            llm_changed_routine_or_safety=True,
        )
    )

    assert decision.revision_allowed is False
    assert PlanRevisionReasonCode.LLM_DECISION_FORBIDDEN in decision.reason_codes
