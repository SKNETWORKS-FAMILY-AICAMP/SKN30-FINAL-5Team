from __future__ import annotations

import pytest

from backend.app.domain.agents.contracts import (
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    CoordinatorCandidate,
    CoordinatorInput,
    CoordinatorStatusCode,
    DownshiftAdjustmentCode,
    coordinate,
)
from backend.app.domain.rules.duration import (
    DURATION_RULE_VERSION,
    DurationAdjustmentSourceCode,
    DurationPlan,
    PlanItemDuration,
)
from backend.app.domain.rules.safety import SafetyStatusCode


def _exact_forty_minute_plan() -> DurationPlan:
    return DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=(
            PlanItemDuration(600, 180, 15),
            PlanItemDuration(600, 180, 15),
            PlanItemDuration(400, 155, 15),
        ),
        cooldown_seconds=90,
    )


def _candidate(
    candidate_id: str,
    action_code: RecommendedActionCode,
    exercise_ids: tuple[str, ...],
    *,
    downshift_adjustment_codes: tuple[DownshiftAdjustmentCode, ...] = (),
) -> CoordinatorCandidate:
    return CoordinatorCandidate(
        candidate_id=candidate_id,
        action_code=action_code,
        exercise_ids=exercise_ids,
        goal_tags=("CORE_STRENGTH",),
        downshift_adjustment_codes=downshift_adjustment_codes,
        catalog_version="approved-catalog-v1",
        duration_plan=_exact_forty_minute_plan(),
    )


def _proposal(
    agent_type: AgentTypeCode,
    *,
    action_code: RecommendedActionCode = RecommendedActionCode.KEEP,
    intensity_delta: int = 0,
    preferred_exercise_ids: tuple[str, ...] = (),
    excluded_exercise_ids: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = ("BASE_CANDIDATE_ACCEPTED",),
    safety_status: SafetyStatusCode = SafetyStatusCode.PASS,
    safety_vetoed: bool = False,
) -> AgentProposal:
    is_safety = agent_type is AgentTypeCode.SAFETY
    return AgentProposal(
        agent_type_code=agent_type,
        proposal_status_code=ProposalStatusCode.READY,
        recommended_action_code=action_code,
        requested_duration_minutes=40,
        estimated_duration_seconds=2400,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        intensity_delta=intensity_delta,
        required_goal_tags=("CORE_STRENGTH",),
        preferred_exercise_ids=preferred_exercise_ids,
        excluded_exercise_ids=excluded_exercise_ids,
        hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
        reason_codes=reason_codes,
        evidence_reference_codes=("INPUT.requested_duration_minutes",),
        policy_version="policy-v1",
        safety_status_code=safety_status if is_safety else None,
        safety_vetoed=safety_vetoed if is_safety else None,
    )


def _proposals(
    replacements: dict[AgentTypeCode, AgentProposal] | None = None,
) -> tuple[AgentProposal, ...]:
    replacements = replacements or {}
    return tuple(
        replacements.get(agent_type, _proposal(agent_type)) for agent_type in REQUIRED_AGENT_TYPES
    )


def _input(
    *,
    proposals: tuple[AgentProposal, ...],
    candidates: tuple[CoordinatorCandidate, ...],
) -> CoordinatorInput:
    return CoordinatorInput(
        proposals=proposals,
        candidates=candidates,
        profile_duration_minutes=40,
        requested_duration_minutes=40,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        policy_version="policy-v1",
        catalog_version="approved-catalog-v1",
        catalog_status_code="ACTIVE",
        catalog_review_status_code="DOMAIN_APPROVED",
        catalog_production_eligible=True,
        catalog_activated=True,
        safety_rule_version="approved-safety-v1",
        duration_rule_version=DURATION_RULE_VERSION,
    )


def test_golden_healthy_condition_keeps_base_routine() -> None:
    base = _candidate(
        "candidate-original",
        RecommendedActionCode.KEEP,
        ("push_up", "supported_row"),
    )

    result = coordinate(_input(proposals=_proposals(), candidates=(base,)))

    assert result.status_code is CoordinatorStatusCode.PASS
    assert result.safety_status_code is SafetyStatusCode.PASS
    assert result.final_action_code is RecommendedActionCode.KEEP
    assert result.selected_candidate_id == "candidate-original"
    assert result.estimated_duration_seconds == 2400


def test_golden_time_shortage_downshifts_burden_not_requested_time() -> None:
    feasibility = _proposal(
        AgentTypeCode.FEASIBILITY,
        action_code=RecommendedActionCode.DOWNSHIFT,
        intensity_delta=-1,
        reason_codes=("TIME_SHORTAGE_PATTERN",),
    )
    downshift = _candidate(
        "candidate-goal-preserving-downshift",
        RecommendedActionCode.DOWNSHIFT,
        ("push_up", "supported_row"),
        downshift_adjustment_codes=(DownshiftAdjustmentCode.INTENSITY_REDUCED,),
    )

    result = coordinate(
        _input(
            proposals=_proposals({AgentTypeCode.FEASIBILITY: feasibility}),
            candidates=(downshift,),
        )
    )

    assert feasibility.intensity_delta == -1
    assert downshift.goal_tags == ("CORE_STRENGTH",)
    assert downshift.downshift_adjustment_codes == (DownshiftAdjustmentCode.INTENSITY_REDUCED,)
    assert result.status_code is CoordinatorStatusCode.PASS
    assert result.final_action_code is RecommendedActionCode.DOWNSHIFT
    assert result.requested_duration_minutes == 40
    assert result.estimated_duration_seconds == 2400


@pytest.mark.parametrize("severity_reason", ["KNEE_MILD", "KNEE_MODERATE"])
def test_golden_knee_discomfort_uses_only_approved_replacement(
    severity_reason: str,
) -> None:
    training = _proposal(
        AgentTypeCode.TRAINING,
        preferred_exercise_ids=("squat",),
    )
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=RecommendedActionCode.CHANGE,
        excluded_exercise_ids=("squat",),
        reason_codes=(severity_reason,),
        safety_status=SafetyStatusCode.REVISE,
        safety_vetoed=True,
    )
    unsafe = _candidate(
        "candidate-vetoed",
        RecommendedActionCode.CHANGE,
        ("squat", "supported_row"),
    )
    approved_replacement = _candidate(
        "candidate-approved-knee-replacement",
        RecommendedActionCode.CHANGE,
        ("glute_bridge", "supported_row"),
    )

    result = coordinate(
        _input(
            proposals=_proposals(
                {
                    AgentTypeCode.TRAINING: training,
                    AgentTypeCode.SAFETY: safety,
                }
            ),
            candidates=(unsafe, approved_replacement),
        )
    )

    assert result.status_code is CoordinatorStatusCode.REVISE
    assert result.safety_status_code is SafetyStatusCode.REVISE
    assert result.selected_candidate_id == "candidate-approved-knee-replacement"
    assert result.estimated_duration_seconds == 2400


def test_golden_severe_knee_discomfort_returns_rest_without_plan() -> None:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=RecommendedActionCode.REST,
        reason_codes=("KNEE_SEVERE",),
        safety_status=SafetyStatusCode.BLOCKED,
        safety_vetoed=True,
    )

    result = coordinate(
        _input(
            proposals=_proposals({AgentTypeCode.SAFETY: safety}),
            candidates=(
                _candidate(
                    "candidate-other-agent-keeps",
                    RecommendedActionCode.KEEP,
                    ("push_up", "supported_row"),
                ),
            ),
        )
    )

    assert result.status_code is CoordinatorStatusCode.BLOCKED
    assert result.final_action_code is RecommendedActionCode.REST
    assert result.selected_candidate_id is None
    assert result.estimated_duration_seconds is None


def test_golden_serious_adverse_reaction_stops_without_plan() -> None:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=RecommendedActionCode.STOP_AND_SEEK_HELP,
        reason_codes=("SERIOUS_ADVERSE_REACTION",),
        safety_status=SafetyStatusCode.BLOCKED,
        safety_vetoed=True,
    )

    result = coordinate(
        _input(
            proposals=_proposals({AgentTypeCode.SAFETY: safety}),
            candidates=(
                _candidate(
                    "candidate-must-not-be-returned",
                    RecommendedActionCode.KEEP,
                    ("push_up", "supported_row"),
                ),
            ),
        )
    )

    assert result.status_code is CoordinatorStatusCode.BLOCKED
    assert result.final_action_code is RecommendedActionCode.STOP_AND_SEEK_HELP
    assert result.selected_candidate_id is None
    assert result.estimated_duration_seconds is None


def test_golden_execution_is_deterministic_without_llm() -> None:
    base = _candidate(
        "candidate-no-llm",
        RecommendedActionCode.KEEP,
        ("push_up", "supported_row"),
    )
    coordinator_input = _input(proposals=_proposals(), candidates=(base,))

    results = tuple(coordinate(coordinator_input) for _ in range(3))

    assert results[0] == results[1] == results[2]
    assert results[0].selected_candidate_id == "candidate-no-llm"
