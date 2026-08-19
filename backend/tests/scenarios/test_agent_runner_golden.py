from dataclasses import dataclass

from backend.app.domain.agents.contracts import (
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalBatchStatusCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.runner import ProposalRequest, run_required_agents
from backend.app.domain.rules.duration import DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SafetyStatusCode


@dataclass(frozen=True)
class GoldenAgent:
    agent_type_code: AgentTypeCode
    proposal: AgentProposal
    policy_version: str = "policy-v1"

    def propose(self, _request: ProposalRequest[tuple[str, ...], str]) -> AgentProposal:
        return self.proposal


def _request() -> ProposalRequest[tuple[str, ...], str]:
    return ProposalRequest(
        context=("synthetic-no-identifier-context",),
        candidates=("approved-upper-body-candidate",),
        candidate_exercise_ids=("kneeling_push_up", "supported_row"),
        requested_duration_minutes=40,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        policy_version="policy-v1",
    )


def _proposal(agent_type: AgentTypeCode) -> AgentProposal:
    safety = agent_type is AgentTypeCode.SAFETY
    return AgentProposal(
        agent_type_code=agent_type,
        proposal_status_code=ProposalStatusCode.READY,
        recommended_action_code=(
            RecommendedActionCode.CHANGE if safety else RecommendedActionCode.KEEP
        ),
        requested_duration_minutes=40,
        estimated_duration_seconds=2400,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        excluded_exercise_ids=("kneeling_push_up",) if safety else (),
        hard_constraint_codes=("SAFETY_VETO_PRESERVED",) if safety else (),
        reason_codes=("KNEE_LOAD_EXCLUDED",) if safety else ("BASE_CANDIDATE_ACCEPTED",),
        evidence_reference_codes=(
            "RULE.KNEE_KNEELING_PUSH_UP_EXCLUDE" if safety else "INPUT.requested_duration_minutes",
        ),
        policy_version="policy-v1",
        safety_status_code=SafetyStatusCode.REVISE if safety else None,
        safety_vetoed=True if safety else None,
    )


def test_golden_four_proposals_preserve_safety_veto_and_requested_duration() -> None:
    agents = [GoldenAgent(agent_type, _proposal(agent_type)) for agent_type in REQUIRED_AGENT_TYPES]

    batch = run_required_agents(request=_request(), agents=agents)

    safety = batch.by_agent_type(AgentTypeCode.SAFETY)
    assert batch.status_code is ProposalBatchStatusCode.READY
    assert tuple(proposal.agent_type_code for proposal in batch.proposals) == REQUIRED_AGENT_TYPES
    assert all(proposal.requested_duration_minutes == 40 for proposal in batch.proposals)
    assert all(proposal.estimated_duration_seconds == 2400 for proposal in batch.proposals)
    assert safety.safety_status_code is SafetyStatusCode.REVISE
    assert safety.safety_vetoed is True
    assert safety.excluded_exercise_ids == ("kneeling_push_up",)


def test_golden_required_agent_failure_returns_no_plan_success() -> None:
    agents = [GoldenAgent(agent_type, _proposal(agent_type)) for agent_type in REQUIRED_AGENT_TYPES]
    agents = [agent for agent in agents if agent.agent_type_code is not AgentTypeCode.FEASIBILITY]

    batch = run_required_agents(request=_request(), agents=agents)

    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert batch.exercise_plan_success_forbidden is True
    assert batch.by_agent_type(AgentTypeCode.FEASIBILITY).reason_codes == ("AGENT_MISSING",)
