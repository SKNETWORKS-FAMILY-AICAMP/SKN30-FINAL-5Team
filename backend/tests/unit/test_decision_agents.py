from dataclasses import replace
from datetime import date
from uuid import UUID

from backend.app.domain.agents.contracts import (
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    CoordinatorCandidate,
    DownshiftAdjustmentCode,
)
from backend.app.domain.agents.runner import ProposalRequest, run_required_agents
from backend.app.domain.rules.duration import (
    DurationAdjustmentSourceCode,
    DurationPlan,
    PlanItemDuration,
)
from backend.app.modules.decisions.agents import default_agents
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.app.modules.decisions.context import DecisionContext


def _context(**changes: object) -> DecisionContext:
    context = DecisionContext(
        local_date=date(2026, 8, 18),
        daily_context_id=UUID("00000000-0000-0000-0000-000000000010"),
        context_version=3,
        fatigue_level_code="LOW",
        requested_duration_minutes=10,
        duration_adjustment_source_code="PROFILE",
        location_code="HOME",
        sleep_minutes=480,
        fasting_state_code=None,
        hydration_state_code=None,
        discomforts=(),
        adverse_reaction_codes=(),
        profile_duration_minutes=10,
        primary_goal_code="GENERAL_FITNESS",
        experience_level_code="BEGINNER",
        equipment_codes=("MAT",),
        attention_area_codes=(),
        recent_workout_status_codes=("COMPLETED", "NOT_COMPLETED"),
        candidate_required_equipment_codes=("MAT",),
        candidate_supported_location_codes=("HOME",),
    )
    return replace(context, **changes)


def _candidate(action: RecommendedActionCode, suffix: str) -> CoordinatorCandidate:
    return CoordinatorCandidate(
        candidate_id=f"candidate-{suffix}",
        action_code=action,
        exercise_ids=("exercise-1",),
        goal_tags=("GENERAL_FITNESS",),
        downshift_adjustment_codes=(
            (DownshiftAdjustmentCode.INTENSITY_REDUCED,)
            if action is RecommendedActionCode.DOWNSHIFT
            else ()
        ),
        catalog_version="catalog-v1",
        duration_plan=DurationPlan(
            setup_seconds=0,
            warmup_seconds=60,
            items=(PlanItemDuration(465, 0, 15),),
            cooldown_seconds=60,
        ),
    )


def _request(context: DecisionContext) -> ProposalRequest[DecisionContext, CoordinatorCandidate]:
    return ProposalRequest(
        context=context,
        candidates=(
            _candidate(RecommendedActionCode.KEEP, "keep"),
            _candidate(RecommendedActionCode.DOWNSHIFT, "downshift"),
        ),
        candidate_exercise_ids=("exercise-1",),
        requested_duration_minutes=10,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        policy_version=DECISION_POLICY_VERSION,
    )


def test_specialists_return_distinct_proposals_from_owned_evidence() -> None:
    batch = run_required_agents(request=_request(_context()), agents=default_agents())

    training = batch.by_agent_type(AgentTypeCode.TRAINING)
    recovery = batch.by_agent_type(AgentTypeCode.RECOVERY)
    feasibility = batch.by_agent_type(AgentTypeCode.FEASIBILITY)

    assert training.required_goal_tags == ("GENERAL_FITNESS",)
    assert training.evidence_reference_codes == (
        "PROFILE/experience_level_code",
        "PROFILE/primary_goal_code",
    )
    assert "HISTORY/recent_workout_status_codes" in recovery.evidence_reference_codes
    assert feasibility.hard_constraint_codes == (
        "AVAILABLE_EQUIPMENT_SUFFICIENT",
        "CURRENT_LOCATION_SUPPORTED",
        "REQUESTED_DURATION_PRESERVED",
    )
    assert len({training.reason_codes, recovery.reason_codes, feasibility.reason_codes}) == 3


def test_moderate_fatigue_proposes_duration_preserving_downshift_deterministically() -> None:
    request = _request(_context(fatigue_level_code="MODERATE"))

    first = run_required_agents(request=request, agents=default_agents())
    second = run_required_agents(request=request, agents=default_agents())
    recovery = first.by_agent_type(AgentTypeCode.RECOVERY)

    assert first == second
    assert recovery.proposal_status_code is ProposalStatusCode.READY
    assert recovery.recommended_action_code is RecommendedActionCode.DOWNSHIFT
    assert recovery.estimated_duration_seconds == 600
    assert recovery.intensity_delta == -1


def test_high_fatigue_fails_closed_until_recovery_content_is_approved() -> None:
    recovery = run_required_agents(
        request=_request(_context(fatigue_level_code="HIGH")),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.RECOVERY)

    assert recovery.proposal_status_code is ProposalStatusCode.NEEDS_INPUT
    assert recovery.recommended_action_code is None
    assert "APPROVED_RECOVERY_CANDIDATE_UNAVAILABLE" in recovery.reason_codes


def test_feasibility_requires_current_location_and_available_equipment() -> None:
    missing_equipment = run_required_agents(
        request=_request(_context(equipment_codes=())),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.FEASIBILITY)
    unsupported_location = run_required_agents(
        request=_request(_context(location_code="GYM")),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.FEASIBILITY)

    assert missing_equipment.proposal_status_code is ProposalStatusCode.NEEDS_INPUT
    assert missing_equipment.reason_codes == ("AVAILABLE_EQUIPMENT_INSUFFICIENT",)
    assert unsupported_location.proposal_status_code is ProposalStatusCode.NEEDS_INPUT
    assert unsupported_location.reason_codes == ("CURRENT_LOCATION_UNSUPPORTED",)
