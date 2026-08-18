from backend.app.domain.agents.contracts import (
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import CoordinatorCandidate
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

    def propose(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
    ) -> AgentProposal:
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

    def _safety(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
    ) -> AgentProposal:
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
        evaluations = dict(request.candidate_safety_evaluations)
        candidate_evidence = dict(request.candidate_evidence_reference_codes)
        if not evaluations:
            if request.context.discomforts or request.context.attention_area_codes:
                return AgentProposal.failed(
                    agent_type_code=AgentTypeCode.SAFETY,
                    requested_duration_minutes=request.requested_duration_minutes,
                    duration_adjustment_source_code=request.duration_adjustment_source_code,
                    policy_version=self.policy_version,
                    reason_code="APPROVED_SAFETY_RULESET_UNAVAILABLE",
                )
            return self._ready_safety(
                request,
                action=RecommendedActionCode.KEEP,
                status=SafetyStatusCode.PASS,
                vetoed=False,
                reason_codes=("NO_SAFETY_SIGNAL_REPORTED",),
            )

        base_candidate = request.candidates[0]
        base_id = str(base_candidate.candidate_id)
        base = evaluations[base_id]
        if base.status_code is SafetyStatusCode.FAILED:
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
        evidence_codes = tuple(
            sorted(f"SAFETY_RULE/{rule_code}" for rule_code in base.applied_rule_codes)
        )
        excluded_ids = base.excluded_exercise_codes
        if excluded_ids:
            change_candidates = [
                candidate
                for candidate in request.candidates[1:]
                if candidate.action_code is RecommendedActionCode.CHANGE
                and evaluations[str(candidate.candidate_id)].status_code
                in {SafetyStatusCode.PASS, SafetyStatusCode.REVISE}
                and not evaluations[str(candidate.candidate_id)].excluded_exercise_codes
            ]
            if change_candidates:
                selected = min(
                    change_candidates,
                    key=lambda candidate: str(candidate.candidate_id),
                )
                preferred = tuple(
                    sorted(set(selected.exercise_ids) - set(base_candidate.exercise_ids))
                )
                selected_evidence = tuple(
                    sorted(
                        set(evidence_codes) | set(candidate_evidence.get(selected.candidate_id, ()))
                    )
                )
                return self._ready_safety(
                    request,
                    action=RecommendedActionCode.CHANGE,
                    status=SafetyStatusCode.REVISE,
                    vetoed=True,
                    reason_codes=("SAFETY_EXERCISES_REPLACED",),
                    preferred_exercise_ids=preferred,
                    excluded_exercise_ids=excluded_ids,
                    evidence_reference_codes=selected_evidence,
                )
            return self._ready_safety(
                request,
                action=RecommendedActionCode.REST,
                status=SafetyStatusCode.BLOCKED,
                vetoed=True,
                reason_codes=("APPROVED_ALTERNATIVE_UNAVAILABLE",),
                excluded_exercise_ids=excluded_ids,
                evidence_reference_codes=evidence_codes,
            )

        if base.caution_exercise_codes:
            has_downshift = any(
                candidate.action_code is RecommendedActionCode.DOWNSHIFT
                for candidate in request.candidates[1:]
            )
            if not has_downshift:
                return AgentProposal.failed(
                    agent_type_code=AgentTypeCode.SAFETY,
                    requested_duration_minutes=request.requested_duration_minutes,
                    duration_adjustment_source_code=request.duration_adjustment_source_code,
                    policy_version=self.policy_version,
                    reason_code="SAFETY_DOWNSHIFT_UNAVAILABLE",
                )
            chronic_only = bool(request.context.attention_area_codes) and not bool(
                request.context.discomforts
            )
            return self._ready_safety(
                request,
                action=RecommendedActionCode.DOWNSHIFT,
                status=SafetyStatusCode.REVISE,
                vetoed=False,
                reason_codes=(
                    "ATTENTION_AREA_CAUTION_APPLIED" if chronic_only else "SAFETY_CAUTION_APPLIED",
                ),
                evidence_reference_codes=evidence_codes,
            )

        return self._ready_safety(
            request,
            action=RecommendedActionCode.KEEP,
            status=SafetyStatusCode.PASS,
            vetoed=False,
            reason_codes=("NO_APPLICABLE_SAFETY_RESTRICTION",),
            evidence_reference_codes=evidence_codes,
        )

    def _ready_safety(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
        *,
        action: RecommendedActionCode,
        status: SafetyStatusCode,
        vetoed: bool,
        reason_codes: tuple[str, ...],
        preferred_exercise_ids: tuple[str, ...] = (),
        excluded_exercise_ids: tuple[str, ...] = (),
        evidence_reference_codes: tuple[str, ...] = (),
    ) -> AgentProposal:
        return AgentProposal(
            agent_type_code=AgentTypeCode.SAFETY,
            proposal_status_code=ProposalStatusCode.READY,
            recommended_action_code=action,
            requested_duration_minutes=request.requested_duration_minutes,
            estimated_duration_seconds=request.requested_duration_minutes * 60,
            duration_adjustment_source_code=request.duration_adjustment_source_code,
            preferred_exercise_ids=preferred_exercise_ids,
            excluded_exercise_ids=excluded_exercise_ids,
            reason_codes=reason_codes,
            evidence_reference_codes=evidence_reference_codes,
            policy_version=self.policy_version,
            safety_status_code=status,
            safety_vetoed=vetoed,
        )


def default_agents() -> tuple[DeterministicProposalAgent, ...]:
    return tuple(DeterministicProposalAgent(code) for code in AgentTypeCode)
