"""Versioned golden fixtures for the Wave 6 decision persistence/API boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict

from backend.app.domain.agents.contracts import (
    AGENT_PROPOSAL_SCHEMA_VERSION,
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    COORDINATOR_VERSION,
    CoordinatorCandidate,
    CoordinatorInput,
    CoordinatorStatusCode,
    DownshiftAdjustmentCode,
)
from backend.app.domain.rules.duration import (
    DURATION_RULE_VERSION,
    DurationAdjustmentSourceCode,
    DurationPlan,
    PlanItemDuration,
)
from backend.app.domain.rules.safety import SAFETY_ENGINE_VERSION, SafetyStatusCode
from backend.app.modules.decisions.codes import DECISION_POLICY_VERSION

GOLDEN_CONTRACT_VERSION: Final[str] = "decision-golden-v2"
CATALOG_VERSION: Final[str] = "golden-approved-catalog-v1"
POLICY_VERSION: Final[str] = DECISION_POLICY_VERSION
SAFETY_RULE_VERSION: Final[str] = SAFETY_ENGINE_VERSION
GRAPH_VERSION: Final[str] = "golden-decision-graph-v1"


class ExplanationExecutionMode(StrEnum):
    LLM_DISABLED = "LLM_DISABLED"
    LLM_FAILED = "LLM_FAILED"


class GoldenVersions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    contract_version: str
    catalog_version: str
    policy_version: str
    safety_rule_version: str
    duration_rule_version: str
    graph_version: str
    coordinator_version: str
    proposal_schema_version: str


class GoldenExpectedFinalResult(BaseModel):
    """Decision fields that are stable across persistence and public API mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status_code: CoordinatorStatusCode
    safety_status_code: SafetyStatusCode
    final_action_code: RecommendedActionCode | None
    selected_candidate_id: str | None
    requested_duration_minutes: int
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    estimated_duration_seconds: int | None
    applied_agent_types: tuple[AgentTypeCode, ...]
    reason_codes: tuple[str, ...]
    blocked_reason_codes: tuple[str, ...]


class DecisionGoldenCase(BaseModel):
    """One synthetic input plus separately asserted proposal and final records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_code: str
    versions: GoldenVersions
    context_reference_codes: tuple[str, ...]
    explanation_execution_modes: tuple[ExplanationExecutionMode, ...]
    coordinator_input: CoordinatorInput
    expected_proposals: tuple[AgentProposal, ...]
    expected_final_result: GoldenExpectedFinalResult


VERSIONS = GoldenVersions(
    contract_version=GOLDEN_CONTRACT_VERSION,
    catalog_version=CATALOG_VERSION,
    policy_version=POLICY_VERSION,
    safety_rule_version=SAFETY_RULE_VERSION,
    duration_rule_version=DURATION_RULE_VERSION,
    graph_version=GRAPH_VERSION,
    coordinator_version=COORDINATOR_VERSION,
    proposal_schema_version=AGENT_PROPOSAL_SCHEMA_VERSION,
)


def _duration_plan(minutes: int) -> DurationPlan:
    if minutes == 40:
        items = (
            PlanItemDuration(600, 180, 15),
            PlanItemDuration(600, 180, 15),
            PlanItemDuration(400, 155, 15),
        )
    elif minutes == 30:
        items = (
            PlanItemDuration(600, 165, 15),
            PlanItemDuration(600, 165, 15),
        )
    else:  # pragma: no cover - fixture authors must make supported plans explicit
        raise ValueError("golden duration plan is not defined")
    return DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=items,
        cooldown_seconds=90,
    )


def _candidate(
    candidate_id: str,
    action_code: RecommendedActionCode,
    exercise_ids: tuple[str, ...],
    *,
    minutes: int = 40,
    downshift_adjustment_codes: tuple[DownshiftAdjustmentCode, ...] = (),
) -> CoordinatorCandidate:
    return CoordinatorCandidate(
        candidate_id=candidate_id,
        action_code=action_code,
        exercise_ids=exercise_ids,
        goal_tags=("CORE_STRENGTH",),
        downshift_adjustment_codes=downshift_adjustment_codes,
        catalog_version=CATALOG_VERSION,
        duration_plan=_duration_plan(minutes),
    )


def _proposal(
    agent_type: AgentTypeCode,
    *,
    action_code: RecommendedActionCode = RecommendedActionCode.KEEP,
    status_code: ProposalStatusCode = ProposalStatusCode.READY,
    minutes: int = 40,
    duration_source: DurationAdjustmentSourceCode = DurationAdjustmentSourceCode.PROFILE,
    intensity_delta: int = 0,
    preferred_exercise_ids: tuple[str, ...] = (),
    excluded_exercise_ids: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = ("BASE_CANDIDATE_ACCEPTED",),
    safety_status: SafetyStatusCode = SafetyStatusCode.PASS,
    safety_vetoed: bool = False,
) -> AgentProposal:
    ready = status_code is ProposalStatusCode.READY
    safety_agent = agent_type is AgentTypeCode.SAFETY
    return AgentProposal(
        agent_type_code=agent_type,
        proposal_status_code=status_code,
        recommended_action_code=action_code if ready else None,
        requested_duration_minutes=minutes,
        estimated_duration_seconds=minutes * 60 if ready else None,
        duration_adjustment_source_code=duration_source,
        intensity_delta=intensity_delta,
        required_goal_tags=("CORE_STRENGTH",),
        preferred_exercise_ids=preferred_exercise_ids,
        excluded_exercise_ids=excluded_exercise_ids,
        hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
        reason_codes=reason_codes,
        evidence_reference_codes=("INPUT.requested_duration_minutes",),
        policy_version=POLICY_VERSION,
        safety_status_code=safety_status if safety_agent else None,
        safety_vetoed=safety_vetoed if safety_agent else None,
    )


def _proposals(
    replacements: dict[AgentTypeCode, AgentProposal] | None = None,
    *,
    minutes: int = 40,
    duration_source: DurationAdjustmentSourceCode = DurationAdjustmentSourceCode.PROFILE,
) -> tuple[AgentProposal, ...]:
    replacements = replacements or {}
    return tuple(
        replacements.get(
            agent_type,
            _proposal(agent_type, minutes=minutes, duration_source=duration_source),
        )
        for agent_type in REQUIRED_AGENT_TYPES
    )


def _case(
    case_code: str,
    *,
    proposals: tuple[AgentProposal, ...],
    candidates: tuple[CoordinatorCandidate, ...],
    expected: GoldenExpectedFinalResult,
    context_reference_codes: tuple[str, ...],
    profile_minutes: int = 40,
    requested_minutes: int = 40,
    duration_source: DurationAdjustmentSourceCode = DurationAdjustmentSourceCode.PROFILE,
    execution_modes: tuple[ExplanationExecutionMode, ...] = (
        ExplanationExecutionMode.LLM_DISABLED,
    ),
) -> DecisionGoldenCase:
    coordinator_input = CoordinatorInput(
        proposals=proposals,
        candidates=candidates,
        profile_duration_minutes=profile_minutes,
        requested_duration_minutes=requested_minutes,
        duration_adjustment_source_code=duration_source,
        policy_version=POLICY_VERSION,
        catalog_version=CATALOG_VERSION,
        catalog_status_code="ACTIVE",
        catalog_review_status_code="DOMAIN_APPROVED",
        catalog_production_eligible=True,
        catalog_activated=True,
        safety_rule_version=SAFETY_RULE_VERSION,
        duration_rule_version=DURATION_RULE_VERSION,
    )
    return DecisionGoldenCase(
        case_code=case_code,
        versions=VERSIONS,
        context_reference_codes=context_reference_codes,
        explanation_execution_modes=execution_modes,
        coordinator_input=coordinator_input,
        expected_proposals=proposals,
        expected_final_result=expected,
    )


def _expected(
    *,
    status: CoordinatorStatusCode,
    safety_status: SafetyStatusCode,
    action: RecommendedActionCode | None,
    candidate_id: str | None,
    reason_codes: tuple[str, ...],
    blocked_reason_codes: tuple[str, ...] = (),
    minutes: int = 40,
    duration_source: DurationAdjustmentSourceCode = DurationAdjustmentSourceCode.PROFILE,
    plan: bool = True,
) -> GoldenExpectedFinalResult:
    return GoldenExpectedFinalResult(
        status_code=status,
        safety_status_code=safety_status,
        final_action_code=action,
        selected_candidate_id=candidate_id,
        requested_duration_minutes=minutes,
        duration_adjustment_source_code=duration_source,
        estimated_duration_seconds=minutes * 60 if plan else None,
        applied_agent_types=REQUIRED_AGENT_TYPES,
        reason_codes=reason_codes,
        blocked_reason_codes=blocked_reason_codes,
    )


def _healthy_case(
    case_code: str = "HEALTHY_KEEP",
    *,
    context_codes: tuple[str, ...] = ("CHECK_IN.NORMAL",),
    execution_modes: tuple[ExplanationExecutionMode, ...] = (
        ExplanationExecutionMode.LLM_DISABLED,
    ),
) -> DecisionGoldenCase:
    proposals = _proposals()
    return _case(
        case_code,
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-original",
                RecommendedActionCode.KEEP,
                ("push_up", "supported_row"),
            ),
        ),
        context_reference_codes=context_codes,
        execution_modes=execution_modes,
        expected=_expected(
            status=CoordinatorStatusCode.PASS,
            safety_status=SafetyStatusCode.PASS,
            action=RecommendedActionCode.KEEP,
            candidate_id="candidate-original",
            reason_codes=("BASE_CANDIDATE_ACCEPTED", "COMMON_CANDIDATE_SELECTED"),
        ),
    )


def _downshift_case() -> DecisionGoldenCase:
    feasibility = _proposal(
        AgentTypeCode.FEASIBILITY,
        action_code=RecommendedActionCode.DOWNSHIFT,
        intensity_delta=-1,
        reason_codes=("TIME_SHORTAGE_PATTERN",),
    )
    proposals = _proposals({AgentTypeCode.FEASIBILITY: feasibility})
    return _case(
        "REQUESTED_DURATION_PRESERVING_DOWNSHIFT",
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-goal-preserving-downshift",
                RecommendedActionCode.DOWNSHIFT,
                ("push_up", "supported_row"),
                downshift_adjustment_codes=(DownshiftAdjustmentCode.INTENSITY_REDUCED,),
            ),
        ),
        context_reference_codes=("CHECK_IN.FATIGUE_MODERATE", "HISTORY.TIME_SHORTAGE"),
        expected=_expected(
            status=CoordinatorStatusCode.PASS,
            safety_status=SafetyStatusCode.PASS,
            action=RecommendedActionCode.DOWNSHIFT,
            candidate_id="candidate-goal-preserving-downshift",
            reason_codes=(
                "BASE_CANDIDATE_ACCEPTED",
                "COMMON_CANDIDATE_SELECTED",
                "TIME_SHORTAGE_PATTERN",
            ),
        ),
    )


def _user_override_case() -> DecisionGoldenCase:
    source = DurationAdjustmentSourceCode.USER_OVERRIDE
    proposals = _proposals(minutes=30, duration_source=source)
    return _case(
        "USER_OVERRIDE_DURATION",
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-user-override",
                RecommendedActionCode.KEEP,
                ("push_up", "supported_row"),
                minutes=30,
            ),
        ),
        profile_minutes=40,
        requested_minutes=30,
        duration_source=source,
        context_reference_codes=("DURATION.USER_OVERRIDE",),
        expected=_expected(
            status=CoordinatorStatusCode.PASS,
            safety_status=SafetyStatusCode.PASS,
            action=RecommendedActionCode.KEEP,
            candidate_id="candidate-user-override",
            reason_codes=("BASE_CANDIDATE_ACCEPTED", "COMMON_CANDIDATE_SELECTED"),
            minutes=30,
            duration_source=source,
        ),
    )


def _knee_replacement_case(severity: str) -> DecisionGoldenCase:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=RecommendedActionCode.CHANGE,
        excluded_exercise_ids=("squat",),
        reason_codes=(f"KNEE_{severity}",),
        safety_status=SafetyStatusCode.REVISE,
        safety_vetoed=True,
    )
    training = _proposal(
        AgentTypeCode.TRAINING,
        preferred_exercise_ids=("squat",),
    )
    proposals = _proposals(
        {
            AgentTypeCode.TRAINING: training,
            AgentTypeCode.SAFETY: safety,
        }
    )
    return _case(
        f"KNEE_{severity}_APPROVED_REPLACEMENT",
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-vetoed",
                RecommendedActionCode.CHANGE,
                ("squat", "supported_row"),
            ),
            _candidate(
                "candidate-approved-knee-replacement",
                RecommendedActionCode.CHANGE,
                ("glute_bridge", "supported_row"),
            ),
        ),
        context_reference_codes=(f"CHECK_IN.KNEE_{severity}",),
        expected=_expected(
            status=CoordinatorStatusCode.REVISE,
            safety_status=SafetyStatusCode.REVISE,
            action=RecommendedActionCode.CHANGE,
            candidate_id="candidate-approved-knee-replacement",
            reason_codes=(
                "BASE_CANDIDATE_ACCEPTED",
                "COMMON_CANDIDATE_SELECTED",
                f"KNEE_{severity}",
            ),
        ),
    )


def _blocked_case(
    case_code: str,
    *,
    action: RecommendedActionCode,
    reason_code: str,
    context_code: str,
) -> DecisionGoldenCase:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=action,
        reason_codes=(reason_code,),
        safety_status=SafetyStatusCode.BLOCKED,
        safety_vetoed=True,
    )
    proposals = _proposals({AgentTypeCode.SAFETY: safety})
    reasons = tuple(sorted(("BASE_CANDIDATE_ACCEPTED", reason_code, "SAFETY_BLOCKED")))
    return _case(
        case_code,
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-must-not-be-returned",
                RecommendedActionCode.KEEP,
                ("push_up", "supported_row"),
            ),
        ),
        context_reference_codes=(context_code,),
        expected=_expected(
            status=CoordinatorStatusCode.BLOCKED,
            safety_status=SafetyStatusCode.BLOCKED,
            action=action,
            candidate_id=None,
            reason_codes=reasons,
            blocked_reason_codes=reasons,
            plan=False,
        ),
    )


def _wearable_fallback_case() -> DecisionGoldenCase:
    feasibility = _proposal(
        AgentTypeCode.FEASIBILITY,
        reason_codes=("MANUAL_CHECK_IN_FALLBACK", "WEARABLE_UNAVAILABLE"),
    )
    proposals = _proposals({AgentTypeCode.FEASIBILITY: feasibility})
    return _case(
        "WEARABLE_MISSING_MANUAL_FALLBACK",
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-manual-fallback",
                RecommendedActionCode.KEEP,
                ("push_up", "supported_row"),
            ),
        ),
        context_reference_codes=("CHECK_IN.MANUAL", "WEARABLE.UNAVAILABLE"),
        expected=_expected(
            status=CoordinatorStatusCode.PASS,
            safety_status=SafetyStatusCode.PASS,
            action=RecommendedActionCode.KEEP,
            candidate_id="candidate-manual-fallback",
            reason_codes=(
                "BASE_CANDIDATE_ACCEPTED",
                "COMMON_CANDIDATE_SELECTED",
                "MANUAL_CHECK_IN_FALLBACK",
                "WEARABLE_UNAVAILABLE",
            ),
        ),
    )


def _required_agent_failure_case() -> DecisionGoldenCase:
    recovery = _proposal(
        AgentTypeCode.RECOVERY,
        status_code=ProposalStatusCode.FAILED,
        reason_codes=("AGENT_EXECUTION_FAILED",),
    )
    proposals = _proposals({AgentTypeCode.RECOVERY: recovery})
    return _case(
        "REQUIRED_AGENT_FAILURE",
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-withheld-after-failure",
                RecommendedActionCode.KEEP,
                ("push_up", "supported_row"),
            ),
        ),
        context_reference_codes=("AGENT.RECOVERY_EXECUTION_FAILED",),
        expected=_expected(
            status=CoordinatorStatusCode.FAILED,
            safety_status=SafetyStatusCode.PASS,
            action=None,
            candidate_id=None,
            reason_codes=("REQUIRED_PROPOSAL_FAILED.RECOVERY",),
            blocked_reason_codes=("REQUIRED_PROPOSAL_FAILED.RECOVERY",),
            plan=False,
        ),
    )


def _veto_bypass_case() -> DecisionGoldenCase:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=RecommendedActionCode.REST,
        reason_codes=("KNEE_SEVERE",),
        safety_status=SafetyStatusCode.BLOCKED,
        safety_vetoed=True,
    )
    training = _proposal(
        AgentTypeCode.TRAINING,
        preferred_exercise_ids=("squat",),
        reason_codes=("BASE_CANDIDATE_ACCEPTED",),
    )
    proposals = _proposals(
        {
            AgentTypeCode.TRAINING: training,
            AgentTypeCode.SAFETY: safety,
        }
    )
    reasons = ("BASE_CANDIDATE_ACCEPTED", "KNEE_SEVERE", "SAFETY_BLOCKED")
    return _case(
        "SAFETY_VETO_BYPASS_BLOCKED",
        proposals=proposals,
        candidates=(
            _candidate(
                "candidate-other-agent-preferred",
                RecommendedActionCode.KEEP,
                ("squat", "supported_row"),
            ),
        ),
        context_reference_codes=("CHECK_IN.KNEE_SEVERE", "SAFETY.VETO"),
        expected=_expected(
            status=CoordinatorStatusCode.BLOCKED,
            safety_status=SafetyStatusCode.BLOCKED,
            action=RecommendedActionCode.REST,
            candidate_id=None,
            reason_codes=reasons,
            blocked_reason_codes=reasons,
            plan=False,
        ),
    )


DECISION_GOLDEN_CASES: Final[tuple[DecisionGoldenCase, ...]] = (
    _healthy_case(),
    _downshift_case(),
    _user_override_case(),
    _knee_replacement_case("MILD"),
    _knee_replacement_case("MODERATE"),
    _blocked_case(
        "KNEE_SEVERE_REST",
        action=RecommendedActionCode.REST,
        reason_code="KNEE_SEVERE",
        context_code="CHECK_IN.KNEE_SEVERE",
    ),
    _blocked_case(
        "SERIOUS_ADVERSE_STOP",
        action=RecommendedActionCode.STOP_AND_SEEK_HELP,
        reason_code="SERIOUS_ADVERSE_REACTION",
        context_code="CHECK_IN.SERIOUS_ADVERSE_REACTION",
    ),
    _wearable_fallback_case(),
    _required_agent_failure_case(),
    _veto_bypass_case(),
    _healthy_case(
        "LLM_DISABLED_OR_FAILED_SAME_DECISION",
        context_codes=("CHECK_IN.NORMAL", "EXPLANATION.TEMPLATE_FALLBACK"),
        execution_modes=(
            ExplanationExecutionMode.LLM_DISABLED,
            ExplanationExecutionMode.LLM_FAILED,
        ),
    ),
)
