from backend.app.domain.agents.contracts import (
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.runner import ProposalRequest
from backend.app.domain.rules.safety import (
    ACUTE_MUSCULOSKELETAL_REACTION_CODES,
    EMERGENCY_REACTION_CODES,
    SafetyStatusCode,
)
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.app.modules.decisions.context import DecisionContext


class DeterministicProposalAgent:
    policy_version = DECISION_POLICY_VERSION

    def __init__(self, agent_type_code: AgentTypeCode) -> None:
        self.agent_type_code = agent_type_code

    def propose(self, request: ProposalRequest[DecisionContext, object]) -> AgentProposal:
        if self.agent_type_code is AgentTypeCode.SAFETY:
            return self._safety(request)
        reason = {
            AgentTypeCode.TRAINING: "ACTIVE_ROUTINE_AVAILABLE",
            AgentTypeCode.RECOVERY: "MANUAL_CONTEXT_REVIEWED",
            AgentTypeCode.FEASIBILITY: "LOCATION_AND_DURATION_MATCHED",
        }[self.agent_type_code]
        return AgentProposal(
            agent_type_code=self.agent_type_code,
            proposal_status_code=ProposalStatusCode.READY,
            recommended_action_code=RecommendedActionCode.KEEP,
            requested_duration_minutes=request.requested_duration_minutes,
            estimated_duration_seconds=request.requested_duration_minutes * 60,
            duration_adjustment_source_code=request.duration_adjustment_source_code,
            reason_codes=(reason,),
            policy_version=self.policy_version,
        )

    def _safety(self, request: ProposalRequest[DecisionContext, object]) -> AgentProposal:
        reactions = set(request.context.adverse_reaction_codes)
        emergency = {code.value for code in EMERGENCY_REACTION_CODES}
        acute = {code.value for code in ACUTE_MUSCULOSKELETAL_REACTION_CODES}
        severe = any(severity == "SEVERE" for _, severity in request.context.discomforts)
        if reactions & emergency:
            return AgentProposal(
                agent_type_code=AgentTypeCode.SAFETY,
                proposal_status_code=ProposalStatusCode.READY,
                recommended_action_code=RecommendedActionCode.STOP_AND_SEEK_HELP,
                requested_duration_minutes=request.requested_duration_minutes,
                estimated_duration_seconds=request.requested_duration_minutes * 60,
                duration_adjustment_source_code=request.duration_adjustment_source_code,
                reason_codes=("EMERGENCY_REACTION_REPORTED",),
                policy_version=self.policy_version,
                safety_status_code=SafetyStatusCode.BLOCKED,
                safety_vetoed=True,
            )
        if reactions & acute or severe:
            return AgentProposal(
                agent_type_code=AgentTypeCode.SAFETY,
                proposal_status_code=ProposalStatusCode.READY,
                recommended_action_code=RecommendedActionCode.REST,
                requested_duration_minutes=request.requested_duration_minutes,
                estimated_duration_seconds=request.requested_duration_minutes * 60,
                duration_adjustment_source_code=request.duration_adjustment_source_code,
                reason_codes=("ACUTE_OR_SEVERE_INPUT_REPORTED",),
                policy_version=self.policy_version,
                safety_status_code=SafetyStatusCode.BLOCKED,
                safety_vetoed=True,
            )
        if request.context.discomforts:
            return AgentProposal(
                agent_type_code=AgentTypeCode.SAFETY,
                proposal_status_code=ProposalStatusCode.FAILED,
                requested_duration_minutes=request.requested_duration_minutes,
                duration_adjustment_source_code=request.duration_adjustment_source_code,
                reason_codes=("APPROVED_SAFETY_RULESET_UNAVAILABLE",),
                policy_version=self.policy_version,
                safety_status_code=SafetyStatusCode.FAILED,
                safety_vetoed=True,
            )
        return AgentProposal(
            agent_type_code=AgentTypeCode.SAFETY,
            proposal_status_code=ProposalStatusCode.READY,
            recommended_action_code=RecommendedActionCode.KEEP,
            requested_duration_minutes=request.requested_duration_minutes,
            estimated_duration_seconds=request.requested_duration_minutes * 60,
            duration_adjustment_source_code=request.duration_adjustment_source_code,
            reason_codes=("NO_SAFETY_SIGNAL_REPORTED",),
            policy_version=self.policy_version,
            safety_status_code=SafetyStatusCode.PASS,
            safety_vetoed=False,
        )


def default_agents() -> tuple[DeterministicProposalAgent, ...]:
    return tuple(DeterministicProposalAgent(code) for code in AgentTypeCode)
