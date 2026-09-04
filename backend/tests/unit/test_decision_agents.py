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
from backend.app.domain.rules.safety import (
    SafetyCandidate,
    SafetyCandidateItem,
    SafetyContext,
    evaluate_safety,
)
from backend.app.modules.decisions.agents import default_agents
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.app.modules.decisions.context import DecisionContext
from backend.app.modules.decisions.ports import (
    AlternativeItemData,
    CandidateItemData,
    DecisionAssembly,
)
from backend.app.modules.decisions.service import _build_adjusted_candidates


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
        "CURRENT_LOCATION_SUPPORTED",
        "REQUESTED_DURATION_PRESERVED",
    )
    assert len({training.reason_codes, recovery.reason_codes, feasibility.reason_codes}) == 3


def test_moderate_fatigue_with_seven_or_more_hours_keeps_normal_recovery() -> None:
    request = _request(_context(fatigue_level_code="MODERATE"))

    first = run_required_agents(request=request, agents=default_agents())
    second = run_required_agents(request=request, agents=default_agents())
    recovery = first.by_agent_type(AgentTypeCode.RECOVERY)

    assert first == second
    assert recovery.proposal_status_code is ProposalStatusCode.READY
    assert recovery.recommended_action_code is RecommendedActionCode.KEEP
    assert recovery.estimated_duration_seconds == 600
    assert recovery.intensity_delta == 0
    assert "RECOVERY_LEVEL_NORMAL" in recovery.reason_codes


def test_high_fatigue_with_seven_or_more_hours_proposes_light_downshift() -> None:
    recovery = run_required_agents(
        request=_request(_context(fatigue_level_code="HIGH")),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.RECOVERY)

    assert recovery.proposal_status_code is ProposalStatusCode.READY
    assert recovery.recommended_action_code is RecommendedActionCode.DOWNSHIFT
    assert recovery.intensity_delta == -1
    assert "RECOVERY_LEVEL_LIGHT" in recovery.reason_codes


def test_feasibility_ignores_equipment_and_requires_current_location() -> None:
    missing_equipment = run_required_agents(
        request=_request(_context(equipment_codes=())),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.FEASIBILITY)
    unsupported_location = run_required_agents(
        request=_request(_context(location_code="GYM")),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.FEASIBILITY)

    assert missing_equipment.proposal_status_code is ProposalStatusCode.READY
    assert missing_equipment.reason_codes == ("TIME_LOCATION_MATCHED",)
    assert "CONTEXT/equipment_codes" not in missing_equipment.evidence_reference_codes
    assert unsupported_location.proposal_status_code is ProposalStatusCode.NEEDS_INPUT
    assert unsupported_location.reason_codes == ("CURRENT_LOCATION_UNSUPPORTED",)


def test_partial_and_not_completed_reason_codes_are_visible_to_feasibility() -> None:
    feasibility = run_required_agents(
        request=_request(
            _context(recent_adherence_reason_codes=("TIME_SHORTAGE", "SCHEDULE_CHANGE"))
        ),
        agents=default_agents(),
    ).by_agent_type(AgentTypeCode.FEASIBILITY)

    assert "HISTORY/recent_adherence_reason_codes" in feasibility.evidence_reference_codes
    assert "RECENT_ADHERENCE_REASONS_REVIEWED" in feasibility.reason_codes


def _equipment_alternative_assembly() -> tuple[DecisionAssembly, UUID]:
    source_id = UUID("00000000-0000-0000-0000-000000000021")
    alternative_id = UUID("00000000-0000-0000-0000-000000000022")
    source_item = CandidateItemData(
        exercise_id=source_id,
        sequence=1,
        phase_code="MAIN",
        tier_code="CORE",
        sets=1,
        reps=10,
        work_seconds_per_set=None,
        rest_seconds_per_set=30,
        transition_seconds=0,
        intensity_code="MODERATE",
        instruction_content_version="v1",
        display_name="source",
        work_seconds=60,
        rest_seconds=30,
    )
    source_safety_item = SafetyCandidateItem(str(source_id), "catalog-v1", "SQUAT")
    alternative_safety_item = SafetyCandidateItem(str(alternative_id), "catalog-v1", "SQUAT")
    assembly = DecisionAssembly(
        context=_context(equipment_codes=()),
        routine_id=UUID("00000000-0000-0000-0000-000000000023"),
        catalog_version_id=UUID("00000000-0000-0000-0000-000000000024"),
        catalog_version="catalog-v1",
        catalog_status_code="ACTIVE",
        catalog_review_status_code="DOMAIN_APPROVED",
        catalog_production_eligible=True,
        catalog_activated=True,
        candidate=_candidate(RecommendedActionCode.KEEP, "equipment"),
        candidate_data={},
        items=(source_item,),
        safety_candidate=SafetyCandidate(items=(source_safety_item,)),
        alternative_items=(
            AlternativeItemData(
                source_exercise_id=source_id,
                item=replace(source_item, exercise_id=alternative_id, display_name="alternative"),
                safety_item=alternative_safety_item,
                evidence_reference_code="ALTERNATIVE/equipment",
                reason_code="EQUIPMENT",
            ),
        ),
    )
    return assembly, alternative_id


def test_pre_filtered_missing_equipment_variant_becomes_an_alternative_candidate() -> None:
    assembly, alternative_id = _equipment_alternative_assembly()
    assert assembly.safety_candidate is not None

    adjusted = _build_adjusted_candidates(
        assembly,
        SafetyContext(),
        assembly.safety_candidate,
        evaluate_safety(SafetyContext(), assembly.safety_candidate, None),
    )

    assert len(adjusted) == 1
    assert adjusted[0].candidate.action_code is RecommendedActionCode.CHANGE
    assert adjusted[0].items[0].exercise_id == alternative_id


def test_blocked_safety_does_not_use_missing_equipment_variant() -> None:
    assembly, _ = _equipment_alternative_assembly()
    assert assembly.safety_candidate is not None
    blocked_context = SafetyContext(red_flag_present=True)

    adjusted = _build_adjusted_candidates(
        assembly,
        blocked_context,
        assembly.safety_candidate,
        evaluate_safety(blocked_context, assembly.safety_candidate, None),
    )

    assert adjusted == ()
