from backend.app.domain.agents.contracts import (
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import CoordinatorCandidate
from backend.app.domain.agents.runner import ProposalAgent, ProposalRequest
from backend.app.domain.rules.recovery import RecoveryLevelCode, recovery_level
from backend.app.domain.rules.safety import (
    ACUTE_MUSCULOSKELETAL_REACTION_CODES,
    EMERGENCY_REACTION_CODES,
    SafetyStatusCode,
)
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION
from backend.app.modules.decisions.context import DecisionContext


class _ProposalAgent:
    policy_version = DECISION_POLICY_VERSION

    agent_type_code: AgentTypeCode

    def _ready(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
        *,
        action: RecommendedActionCode,
        reason_codes: tuple[str, ...],
        evidence_reference_codes: tuple[str, ...],
        intensity_delta: int = 0,
        required_goal_tags: tuple[str, ...] = (),
        hard_constraint_codes: tuple[str, ...] = (),
    ) -> AgentProposal:
        return AgentProposal(
            agent_type_code=self.agent_type_code,
            proposal_status_code=ProposalStatusCode.READY,
            recommended_action_code=action,
            requested_duration_minutes=request.requested_duration_minutes,
            estimated_duration_seconds=request.requested_duration_minutes * 60,
            duration_adjustment_source_code=request.duration_adjustment_source_code,
            intensity_delta=intensity_delta,
            required_goal_tags=tuple(sorted(set(required_goal_tags))),
            hard_constraint_codes=tuple(sorted(set(hard_constraint_codes))),
            reason_codes=tuple(sorted(set(reason_codes))),
            evidence_reference_codes=tuple(sorted(set(evidence_reference_codes))),
            policy_version=self.policy_version,
        )

    def _needs_input(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
        *,
        reason_codes: tuple[str, ...],
        evidence_reference_codes: tuple[str, ...],
        hard_constraint_codes: tuple[str, ...] = (),
    ) -> AgentProposal:
        return AgentProposal(
            agent_type_code=self.agent_type_code,
            proposal_status_code=ProposalStatusCode.NEEDS_INPUT,
            requested_duration_minutes=request.requested_duration_minutes,
            duration_adjustment_source_code=request.duration_adjustment_source_code,
            hard_constraint_codes=tuple(sorted(set(hard_constraint_codes))),
            reason_codes=tuple(sorted(set(reason_codes))),
            evidence_reference_codes=tuple(sorted(set(evidence_reference_codes))),
            policy_version=self.policy_version,
        )


class TrainingProposalAgent(_ProposalAgent):
    agent_type_code = AgentTypeCode.TRAINING

    def propose(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
    ) -> AgentProposal:
        experience_reason = {
            "BEGINNER": "BEGINNER_GOAL_ROUTINE_SELECTED",
            "INTERMEDIATE": "INTERMEDIATE_GOAL_ROUTINE_SELECTED",
            "ADVANCED": "ADVANCED_GOAL_ROUTINE_SELECTED",
        }.get(request.context.experience_level_code, "EXPERIENCE_LEVEL_REVIEWED")
        return self._ready(
            request,
            action=RecommendedActionCode.KEEP,
            reason_codes=(experience_reason, "PRIMARY_GOAL_PRESERVED"),
            evidence_reference_codes=(
                "PROFILE/experience_level_code",
                "PROFILE/primary_goal_code",
            ),
            required_goal_tags=(request.context.primary_goal_code,),
            hard_constraint_codes=("PRIMARY_GOAL_REQUIRED",),
        )


class RecoveryProposalAgent(_ProposalAgent):
    agent_type_code = AgentTypeCode.RECOVERY

    def propose(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
    ) -> AgentProposal:
        evidence = ["CONTEXT/fatigue_level_code"]
        reasons = ["RECOVERY_CONTEXT_REVIEWED"]
        if request.context.sleep_minutes is not None:
            evidence.append("CONTEXT/sleep_minutes")
            reasons.append("SLEEP_INPUT_RECORDED_WITHOUT_UNAPPROVED_THRESHOLD")
        if request.context.recent_workout_status_codes:
            evidence.append("HISTORY/recent_workout_status_codes")
            reasons.append("RECENT_EXECUTION_HISTORY_REVIEWED")

        level = recovery_level(
            sleep_minutes=request.context.sleep_minutes,
            fatigue_level_code=request.context.fatigue_level_code,
        )
        reasons.append(f"RECOVERY_LEVEL_{level.value}")
        if level is RecoveryLevelCode.VERY_LIGHT:
            return self._ready(
                request,
                action=RecommendedActionCode.DOWNSHIFT,
                reason_codes=tuple(reasons),
                evidence_reference_codes=tuple(evidence),
                intensity_delta=-2,
                hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
            )
        if level is RecoveryLevelCode.LIGHT:
            return self._ready(
                request,
                action=RecommendedActionCode.DOWNSHIFT,
                reason_codes=tuple(reasons),
                evidence_reference_codes=tuple(evidence),
                intensity_delta=-1,
                hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
            )
        return self._ready(
            request,
            action=RecommendedActionCode.KEEP,
            reason_codes=tuple(reasons),
            evidence_reference_codes=tuple(evidence),
            hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
        )


class FeasibilityProposalAgent(_ProposalAgent):
    agent_type_code = AgentTypeCode.FEASIBILITY

    def propose(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
    ) -> AgentProposal:
        supported_locations = request.context.candidate_supported_location_codes
        evidence: tuple[str, ...] = (
            "CANDIDATE/supported_location_codes",
            "CONTEXT/location_code",
            "CONTEXT/requested_duration_minutes",
        )
        if (
            supported_locations is not None
            and request.context.location_code not in supported_locations
        ):
            return self._needs_input(
                request,
                reason_codes=("CURRENT_LOCATION_UNSUPPORTED",),
                evidence_reference_codes=evidence,
                hard_constraint_codes=("CURRENT_LOCATION_REQUIRED",),
            )
        reason_codes = ["TIME_LOCATION_MATCHED"]
        if request.context.recent_adherence_reason_codes:
            evidence += ("HISTORY/recent_adherence_reason_codes",)
            reason_codes.append("RECENT_ADHERENCE_REASONS_REVIEWED")
        return self._ready(
            request,
            action=RecommendedActionCode.KEEP,
            reason_codes=tuple(reason_codes),
            evidence_reference_codes=evidence,
            hard_constraint_codes=(
                "CURRENT_LOCATION_SUPPORTED",
                "REQUESTED_DURATION_PRESERVED",
            ),
        )


class SafetyProposalAgent(_ProposalAgent):
    agent_type_code = AgentTypeCode.SAFETY

    def propose(
        self,
        request: ProposalRequest[DecisionContext, CoordinatorCandidate],
    ) -> AgentProposal:
        if request.context.red_flag_present:
            return AgentProposal(
                agent_type_code=AgentTypeCode.SAFETY,
                proposal_status_code=ProposalStatusCode.READY,
                recommended_action_code=RecommendedActionCode.STOP_AND_SEEK_HELP,
                requested_duration_minutes=request.requested_duration_minutes,
                estimated_duration_seconds=request.requested_duration_minutes * 60,
                duration_adjustment_source_code=request.duration_adjustment_source_code,
                reason_codes=("RED_FLAG_REPORTED",),
                policy_version=self.policy_version,
                safety_status_code=SafetyStatusCode.BLOCKED,
                safety_vetoed=True,
            )
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
        if request.context.discomforts:
            pain_change_candidates = [
                candidate
                for candidate in request.candidates[1:]
                if candidate.action_code is RecommendedActionCode.CHANGE
                and evaluations[str(candidate.candidate_id)].status_code
                in {SafetyStatusCode.PASS, SafetyStatusCode.REVISE}
                and not evaluations[str(candidate.candidate_id)].excluded_exercise_codes
                and any(
                    reference.startswith("PAIN_ALTERNATIVE/")
                    for reference in candidate_evidence.get(candidate.candidate_id, ())
                )
            ]
            if pain_change_candidates:
                selected = min(
                    pain_change_candidates,
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
                    vetoed=bool(excluded_ids),
                    reason_codes=("PAIN_ALTERNATIVE_APPLIED",),
                    preferred_exercise_ids=preferred,
                    excluded_exercise_ids=excluded_ids,
                    evidence_reference_codes=selected_evidence,
                )
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


def default_agents() -> tuple[ProposalAgent[DecisionContext, CoordinatorCandidate], ...]:
    return (
        TrainingProposalAgent(),
        RecoveryProposalAgent(),
        SafetyProposalAgent(),
        FeasibilityProposalAgent(),
    )
