"""Deterministic weekly plan revision and finalization policies."""

import re
from dataclasses import dataclass
from enum import StrEnum

from backend.app.domain.rules.safety import SafetyStatusCode
from backend.app.domain.rules.weekly_report import WeeklyReportStatusCode

WEEKLY_PLAN_POLICY_VERSION = "1.0.0"
MAX_SUCCESSFUL_AI_REVISIONS = 2
_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_ROUTINE_STATUSES = frozenset({SafetyStatusCode.PASS, SafetyStatusCode.REVISE})


class PlanRevisionSourceCode(StrEnum):
    INITIAL = "INITIAL"
    AI = "AI"
    USER = "USER"


class PlanRevisionEndpointCode(StrEnum):
    INITIAL_PLAN = "INITIAL_PLAN"
    PLAN_REVISIONS = "PLAN_REVISIONS"


class RoutineDecisionAuthorityCode(StrEnum):
    COORDINATOR = "COORDINATOR"
    USER = "USER"


class SafetyDecisionAuthorityCode(StrEnum):
    SAFETY_AGENT = "SAFETY_AGENT"


class PlanRevisionReasonCode(StrEnum):
    REVISION_ALLOWED = "REVISION_ALLOWED"
    AI_REVISION_LIMIT_REACHED = "AI_REVISION_LIMIT_REACHED"
    SOURCE_ENDPOINT_MISMATCH = "SOURCE_ENDPOINT_MISMATCH"
    ROUTINE_REQUIRED = "ROUTINE_REQUIRED"
    ROUTINE_FORBIDDEN = "ROUTINE_FORBIDDEN"
    REQUESTED_DURATION_NOT_PRESERVED = "REQUESTED_DURATION_NOT_PRESERVED"
    LOCATION_CONSTRAINT_NOT_SATISFIED = "LOCATION_CONSTRAINT_NOT_SATISFIED"
    EQUIPMENT_CONSTRAINT_NOT_SATISFIED = "EQUIPMENT_CONSTRAINT_NOT_SATISFIED"
    SAFETY_OPINION_NOT_APPLIED = "SAFETY_OPINION_NOT_APPLIED"
    DECISION_AUTHORITY_INVALID = "DECISION_AUTHORITY_INVALID"
    LLM_DECISION_FORBIDDEN = "LLM_DECISION_FORBIDDEN"


class PlanFinalizationReasonCode(StrEnum):
    FINALIZE_ALLOWED = "FINALIZE_ALLOWED"
    REVISION_REJECTED = "REVISION_REJECTED"
    REVISION_STATUS_BLOCKS_FINALIZE = "REVISION_STATUS_BLOCKS_FINALIZE"
    ROUTINE_REQUIRED = "ROUTINE_REQUIRED"
    PREVIOUS_REPORT_ACKNOWLEDGEMENT_REQUIRED = "PREVIOUS_REPORT_ACKNOWLEDGEMENT_REQUIRED"


class WeeklyPlanRuleError(ValueError):
    """Base error for invalid weekly plan policy input."""


class InvalidWeeklyPlanInputError(WeeklyPlanRuleError):
    """Raised when weekly plan policy input is structurally invalid."""


def _valid_count(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidWeeklyPlanInputError(f"{field_name} must be a non-negative integer")


def _canonical_machine_references(values: tuple[str, ...], *, field_name: str) -> None:
    if values != tuple(sorted(set(values))):
        raise InvalidWeeklyPlanInputError(f"{field_name} must be unique and canonically sorted")
    if any(not _MACHINE_REFERENCE_PATTERN.fullmatch(value) for value in values):
        raise InvalidWeeklyPlanInputError(
            f"{field_name} must contain only structured machine references"
        )


@dataclass(frozen=True, slots=True)
class PlanConstraints:
    requested_duration_minutes: int
    allowed_location_codes: tuple[str, ...]
    available_equipment_codes: tuple[str, ...]
    required_safety_opinion_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.requested_duration_minutes, bool)
            or not isinstance(self.requested_duration_minutes, int)
            or self.requested_duration_minutes <= 0
        ):
            raise InvalidWeeklyPlanInputError(
                "requested_duration_minutes must be a positive integer"
            )
        for field_name in (
            "allowed_location_codes",
            "available_equipment_codes",
            "required_safety_opinion_codes",
        ):
            _canonical_machine_references(getattr(self, field_name), field_name=field_name)
        if not self.allowed_location_codes:
            raise InvalidWeeklyPlanInputError("at least one allowed location is required")


@dataclass(frozen=True, slots=True)
class PlanRoutineEvidence:
    routine_reference: str
    requested_duration_minutes: int
    location_code: str
    required_equipment_codes: tuple[str, ...]
    applied_safety_opinion_codes: tuple[str, ...]
    routine_decision_authority_code: RoutineDecisionAuthorityCode
    safety_decision_authority_code: SafetyDecisionAuthorityCode

    def __post_init__(self) -> None:
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(self.routine_reference):
            raise InvalidWeeklyPlanInputError("routine_reference must be a machine reference")
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(self.location_code):
            raise InvalidWeeklyPlanInputError("location_code must be a machine reference")
        if (
            isinstance(self.requested_duration_minutes, bool)
            or not isinstance(self.requested_duration_minutes, int)
            or self.requested_duration_minutes <= 0
        ):
            raise InvalidWeeklyPlanInputError(
                "routine requested_duration_minutes must be a positive integer"
            )
        _canonical_machine_references(
            self.required_equipment_codes, field_name="required_equipment_codes"
        )
        _canonical_machine_references(
            self.applied_safety_opinion_codes, field_name="applied_safety_opinion_codes"
        )


@dataclass(frozen=True, slots=True)
class PlanRevisionPolicyInput:
    endpoint_code: PlanRevisionEndpointCode
    source_code: PlanRevisionSourceCode
    safety_status_code: SafetyStatusCode
    successful_ai_revision_count: int
    constraints: PlanConstraints
    routine: PlanRoutineEvidence | None
    llm_changed_routine_or_safety: bool = False
    weekly_plan_policy_version: str = WEEKLY_PLAN_POLICY_VERSION

    def __post_init__(self) -> None:
        _valid_count(self.successful_ai_revision_count, field_name="successful_ai_revision_count")
        if self.successful_ai_revision_count > MAX_SUCCESSFUL_AI_REVISIONS:
            raise InvalidWeeklyPlanInputError("successful_ai_revision_count cannot exceed 2")
        if not isinstance(self.llm_changed_routine_or_safety, bool):
            raise InvalidWeeklyPlanInputError("llm_changed_routine_or_safety must be a boolean")
        if not _MACHINE_REFERENCE_PATTERN.fullmatch(self.weekly_plan_policy_version):
            raise InvalidWeeklyPlanInputError("weekly_plan_policy_version must be versioned")


@dataclass(frozen=True, slots=True)
class PlanRevisionPolicyDecision:
    revision_allowed: bool
    routine_allowed: bool
    resulting_ai_revision_count: int
    reason_codes: tuple[PlanRevisionReasonCode, ...]
    weekly_plan_policy_version: str = WEEKLY_PLAN_POLICY_VERSION

    def __post_init__(self) -> None:
        _valid_count(self.resulting_ai_revision_count, field_name="resulting_ai_revision_count")
        if self.resulting_ai_revision_count > MAX_SUCCESSFUL_AI_REVISIONS:
            raise InvalidWeeklyPlanInputError("resulting_ai_revision_count cannot exceed 2")
        if not self.revision_allowed and self.routine_allowed:
            raise InvalidWeeklyPlanInputError("a rejected revision cannot allow a routine")
        if not self.reason_codes:
            raise InvalidWeeklyPlanInputError("revision decisions require reason codes")
        if self.revision_allowed != (
            self.reason_codes == (PlanRevisionReasonCode.REVISION_ALLOWED,)
        ):
            raise InvalidWeeklyPlanInputError(
                "revision reason codes must match the allow or reject result"
            )


@dataclass(frozen=True, slots=True)
class PlanFinalizationContext:
    is_first_user_week: bool
    cold_start_applied: bool
    previous_report_status_code: WeeklyReportStatusCode | None

    def __post_init__(self) -> None:
        if not isinstance(self.is_first_user_week, bool) or not isinstance(
            self.cold_start_applied, bool
        ):
            raise InvalidWeeklyPlanInputError("cold-start context fields must be booleans")
        if self.cold_start_applied:
            if not self.is_first_user_week or self.previous_report_status_code is not None:
                raise InvalidWeeklyPlanInputError(
                    "cold-start acknowledgement bypass is valid only for the first user week"
                )
        elif self.is_first_user_week and self.previous_report_status_code is None:
            raise InvalidWeeklyPlanInputError(
                "the first user week without a report must explicitly apply cold start"
            )


@dataclass(frozen=True, slots=True)
class PlanFinalizationDecision:
    finalized: bool
    reason_codes: tuple[PlanFinalizationReasonCode, ...]
    weekly_plan_policy_version: str = WEEKLY_PLAN_POLICY_VERSION

    def __post_init__(self) -> None:
        if not self.reason_codes:
            raise InvalidWeeklyPlanInputError("finalization decisions require reason codes")
        if self.finalized != (self.reason_codes == (PlanFinalizationReasonCode.FINALIZE_ALLOWED,)):
            raise InvalidWeeklyPlanInputError(
                "finalization reason codes must match the finalized result"
            )


def evaluate_plan_revision(policy_input: PlanRevisionPolicyInput) -> PlanRevisionPolicyDecision:
    """Validate revision source, deterministic authorities, and user constraints."""

    reasons: list[PlanRevisionReasonCode] = []
    is_initial_endpoint = policy_input.endpoint_code is PlanRevisionEndpointCode.INITIAL_PLAN
    source_is_initial = policy_input.source_code is PlanRevisionSourceCode.INITIAL
    if is_initial_endpoint is not source_is_initial:
        reasons.append(PlanRevisionReasonCode.SOURCE_ENDPOINT_MISMATCH)
    if (
        policy_input.source_code is PlanRevisionSourceCode.AI
        and policy_input.successful_ai_revision_count >= MAX_SUCCESSFUL_AI_REVISIONS
    ):
        reasons.append(PlanRevisionReasonCode.AI_REVISION_LIMIT_REACHED)
    if policy_input.llm_changed_routine_or_safety:
        reasons.append(PlanRevisionReasonCode.LLM_DECISION_FORBIDDEN)

    routine_status = policy_input.safety_status_code in _ROUTINE_STATUSES
    if routine_status and policy_input.routine is None:
        reasons.append(PlanRevisionReasonCode.ROUTINE_REQUIRED)
    if not routine_status and policy_input.routine is not None:
        reasons.append(PlanRevisionReasonCode.ROUTINE_FORBIDDEN)

    routine = policy_input.routine
    if routine is not None:
        expected_authority = (
            RoutineDecisionAuthorityCode.USER
            if policy_input.source_code is PlanRevisionSourceCode.USER
            else RoutineDecisionAuthorityCode.COORDINATOR
        )
        if (
            routine.routine_decision_authority_code is not expected_authority
            or routine.safety_decision_authority_code
            is not SafetyDecisionAuthorityCode.SAFETY_AGENT
        ):
            reasons.append(PlanRevisionReasonCode.DECISION_AUTHORITY_INVALID)
        if (
            routine.requested_duration_minutes
            != policy_input.constraints.requested_duration_minutes
        ):
            reasons.append(PlanRevisionReasonCode.REQUESTED_DURATION_NOT_PRESERVED)
        if routine.location_code not in policy_input.constraints.allowed_location_codes:
            reasons.append(PlanRevisionReasonCode.LOCATION_CONSTRAINT_NOT_SATISFIED)
        if not set(routine.required_equipment_codes).issubset(
            policy_input.constraints.available_equipment_codes
        ):
            reasons.append(PlanRevisionReasonCode.EQUIPMENT_CONSTRAINT_NOT_SATISFIED)
        if not set(policy_input.constraints.required_safety_opinion_codes).issubset(
            routine.applied_safety_opinion_codes
        ):
            reasons.append(PlanRevisionReasonCode.SAFETY_OPINION_NOT_APPLIED)

    if reasons:
        return PlanRevisionPolicyDecision(
            revision_allowed=False,
            routine_allowed=False,
            resulting_ai_revision_count=policy_input.successful_ai_revision_count,
            reason_codes=tuple(sorted(set(reasons))),
        )

    next_ai_count = policy_input.successful_ai_revision_count
    if policy_input.source_code is PlanRevisionSourceCode.AI and routine_status:
        next_ai_count += 1
    return PlanRevisionPolicyDecision(
        revision_allowed=True,
        routine_allowed=routine_status,
        resulting_ai_revision_count=next_ai_count,
        reason_codes=(PlanRevisionReasonCode.REVISION_ALLOWED,),
    )


def evaluate_plan_finalization(
    *,
    revision_decision: PlanRevisionPolicyDecision,
    safety_status_code: SafetyStatusCode,
    routine_present: bool,
    context: PlanFinalizationContext,
) -> PlanFinalizationDecision:
    """Allow finalize only for an eligible routine and acknowledged prior report."""

    if not isinstance(routine_present, bool):
        raise InvalidWeeklyPlanInputError("routine_present must be a boolean")
    reasons: list[PlanFinalizationReasonCode] = []
    if not revision_decision.revision_allowed:
        reasons.append(PlanFinalizationReasonCode.REVISION_REJECTED)
    if safety_status_code not in _ROUTINE_STATUSES:
        reasons.append(PlanFinalizationReasonCode.REVISION_STATUS_BLOCKS_FINALIZE)
    if not routine_present or not revision_decision.routine_allowed:
        reasons.append(PlanFinalizationReasonCode.ROUTINE_REQUIRED)
    cold_start_exception = context.is_first_user_week and context.cold_start_applied
    if (
        not cold_start_exception
        and context.previous_report_status_code is not WeeklyReportStatusCode.ACKNOWLEDGED
    ):
        reasons.append(PlanFinalizationReasonCode.PREVIOUS_REPORT_ACKNOWLEDGEMENT_REQUIRED)
    if reasons:
        return PlanFinalizationDecision(
            finalized=False,
            reason_codes=tuple(sorted(set(reasons))),
        )
    return PlanFinalizationDecision(
        finalized=True,
        reason_codes=(PlanFinalizationReasonCode.FINALIZE_ALLOWED,),
    )
