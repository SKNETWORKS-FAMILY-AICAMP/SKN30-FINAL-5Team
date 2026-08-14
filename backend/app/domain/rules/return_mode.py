"""Deterministic 14-day return-mode and approved-cap application rules."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

RETURN_MODE_COMPLETION_GAP_DAYS = 14
RETURN_MODE_RULE_VERSION = "1.0.0"


class ReturnModeStatusCode(StrEnum):
    STANDARD = "STANDARD"
    RETURN_MODE = "RETURN_MODE"


class ReturnModeReasonCode(StrEnum):
    COMPLETION_GAP_14_DAYS = "COMPLETION_GAP_14_DAYS"


class WorkoutLearningSignalCode(StrEnum):
    NOT_COMPLETED_HISTORY = "NOT_COMPLETED_HISTORY"


class ReturnCapReviewStatusCode(StrEnum):
    DRAFT = "DRAFT"
    DOMAIN_APPROVED = "DOMAIN_APPROVED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


class ReturnPlanApplicationStatusCode(StrEnum):
    PLAN_ALLOWED = "PLAN_ALLOWED"
    APPROVED_CAPS_REQUIRED = "APPROVED_CAPS_REQUIRED"
    APPROVED_CAPS_APPLIED = "APPROVED_CAPS_APPLIED"


class ReturnModeRuleError(ValueError):
    """Base exception for invalid return-mode domain input."""


class InvalidReturnModeInputError(ReturnModeRuleError):
    """Raised when return-mode input violates a structural invariant."""


class ReturnDurationViolationError(ReturnModeRuleError):
    """Raised when a return policy shortens or extends the requested duration."""


class ReturnPlanPort(Protocol):
    """Minimum plan shape needed to enforce requested-duration preservation."""

    requested_duration_minutes: int


class ApprovedReturnCapPolicyPort[PlanT: ReturnPlanPort](Protocol):
    """Port implemented by an externally reviewed load and volume cap policy."""

    version_code: str
    review_status_code: ReturnCapReviewStatusCode
    production_eligible: bool
    load_cap_code: str
    volume_cap_code: str

    def apply(self, plan: PlanT) -> PlanT:
        """Apply the policy's approved load and volume caps to a plan."""


@dataclass(frozen=True, slots=True)
class ReturnModeEvaluation:
    status_code: ReturnModeStatusCode
    days_since_last_completed: int | None
    reason_codes: tuple[ReturnModeReasonCode, ...]
    learning_signal_codes: tuple[WorkoutLearningSignalCode, ...]
    penalty_applied: bool = False
    return_mode_rule_version: str = RETURN_MODE_RULE_VERSION

    def __post_init__(self) -> None:
        if self.penalty_applied:
            raise InvalidReturnModeInputError("missed workouts must never apply a penalty")
        if self.days_since_last_completed is not None and (
            isinstance(self.days_since_last_completed, bool)
            or not isinstance(self.days_since_last_completed, int)
            or self.days_since_last_completed < 0
        ):
            raise InvalidReturnModeInputError(
                "days_since_last_completed must be a non-negative integer or null"
            )
        if self.status_code is ReturnModeStatusCode.RETURN_MODE:
            if self.days_since_last_completed is None:
                raise InvalidReturnModeInputError("RETURN_MODE requires days_since_last_completed")
            if self.days_since_last_completed < RETURN_MODE_COMPLETION_GAP_DAYS:
                raise InvalidReturnModeInputError(
                    "RETURN_MODE requires the approved 14-day completion gap"
                )
            if self.reason_codes != (ReturnModeReasonCode.COMPLETION_GAP_14_DAYS,):
                raise InvalidReturnModeInputError("RETURN_MODE requires the completion-gap reason")
        else:
            if self.reason_codes:
                raise InvalidReturnModeInputError("STANDARD state cannot have return reasons")
            if (
                self.days_since_last_completed is not None
                and self.days_since_last_completed >= RETURN_MODE_COMPLETION_GAP_DAYS
            ):
                raise InvalidReturnModeInputError(
                    "a 14-day completion gap cannot remain in STANDARD state"
                )


@dataclass(frozen=True, slots=True)
class ReturnPlanApplication[PlanT: ReturnPlanPort]:
    status_code: ReturnPlanApplicationStatusCode
    requested_duration_minutes: int
    plan: PlanT | None
    cap_policy_version: str | None
    load_cap_code: str | None
    volume_cap_code: str | None

    def __post_init__(self) -> None:
        if self.status_code is ReturnPlanApplicationStatusCode.APPROVED_CAPS_REQUIRED:
            if self.plan is not None or any(
                value is not None
                for value in (
                    self.cap_policy_version,
                    self.load_cap_code,
                    self.volume_cap_code,
                )
            ):
                raise InvalidReturnModeInputError(
                    "missing or unapproved caps must fail closed without a plan"
                )
            return
        if self.plan is None:
            raise InvalidReturnModeInputError("an allowed application requires a plan")
        if self.plan.requested_duration_minutes != self.requested_duration_minutes:
            raise ReturnDurationViolationError(
                "return-mode application must preserve requested duration"
            )
        if self.status_code is ReturnPlanApplicationStatusCode.APPROVED_CAPS_APPLIED:
            if not all(
                isinstance(value, str) and value.strip()
                for value in (
                    self.cap_policy_version,
                    self.load_cap_code,
                    self.volume_cap_code,
                )
            ):
                raise InvalidReturnModeInputError(
                    "applied caps require versioned load and volume cap codes"
                )
        elif any(
            value is not None
            for value in (
                self.cap_policy_version,
                self.load_cap_code,
                self.volume_cap_code,
            )
        ):
            raise InvalidReturnModeInputError(
                "standard plans must not claim return caps were applied"
            )


def evaluate_return_mode(
    *,
    current_local_date: date,
    last_completed_local_date: date | None,
    not_completed_history_count: int = 0,
) -> ReturnModeEvaluation:
    """Activate return mode only after 14 days since an official completion."""

    if (
        isinstance(not_completed_history_count, bool)
        or not isinstance(not_completed_history_count, int)
        or not_completed_history_count < 0
    ):
        raise InvalidReturnModeInputError(
            "not_completed_history_count must be a non-negative integer"
        )
    learning_signals = (
        (WorkoutLearningSignalCode.NOT_COMPLETED_HISTORY,) if not_completed_history_count else ()
    )
    if last_completed_local_date is None:
        return ReturnModeEvaluation(
            status_code=ReturnModeStatusCode.STANDARD,
            days_since_last_completed=None,
            reason_codes=(),
            learning_signal_codes=learning_signals,
        )
    if last_completed_local_date > current_local_date:
        raise InvalidReturnModeInputError(
            "last_completed_local_date cannot be after current_local_date"
        )

    completion_gap_days = (current_local_date - last_completed_local_date).days
    if completion_gap_days >= RETURN_MODE_COMPLETION_GAP_DAYS:
        return ReturnModeEvaluation(
            status_code=ReturnModeStatusCode.RETURN_MODE,
            days_since_last_completed=completion_gap_days,
            reason_codes=(ReturnModeReasonCode.COMPLETION_GAP_14_DAYS,),
            learning_signal_codes=learning_signals,
        )
    return ReturnModeEvaluation(
        status_code=ReturnModeStatusCode.STANDARD,
        days_since_last_completed=completion_gap_days,
        reason_codes=(),
        learning_signal_codes=learning_signals,
    )


def apply_return_plan_policy[PlanT: ReturnPlanPort](
    evaluation: ReturnModeEvaluation,
    plan: PlanT,
    cap_policy: ApprovedReturnCapPolicyPort[PlanT] | None,
) -> ReturnPlanApplication[PlanT]:
    """Apply approved caps in return mode and never invent a fallback cap."""

    requested_duration_minutes = plan.requested_duration_minutes
    if (
        isinstance(requested_duration_minutes, bool)
        or not isinstance(requested_duration_minutes, int)
        or requested_duration_minutes <= 0
    ):
        raise InvalidReturnModeInputError("requested_duration_minutes must be a positive integer")
    if evaluation.status_code is ReturnModeStatusCode.STANDARD:
        return ReturnPlanApplication(
            status_code=ReturnPlanApplicationStatusCode.PLAN_ALLOWED,
            requested_duration_minutes=requested_duration_minutes,
            plan=plan,
            cap_policy_version=None,
            load_cap_code=None,
            volume_cap_code=None,
        )
    if (
        cap_policy is None
        or cap_policy.review_status_code is not ReturnCapReviewStatusCode.DOMAIN_APPROVED
        or not cap_policy.production_eligible
        or not all(
            isinstance(value, str) and value.strip()
            for value in (
                cap_policy.version_code,
                cap_policy.load_cap_code,
                cap_policy.volume_cap_code,
            )
        )
    ):
        return ReturnPlanApplication(
            status_code=ReturnPlanApplicationStatusCode.APPROVED_CAPS_REQUIRED,
            requested_duration_minutes=requested_duration_minutes,
            plan=None,
            cap_policy_version=None,
            load_cap_code=None,
            volume_cap_code=None,
        )

    adjusted_plan = cap_policy.apply(plan)
    if adjusted_plan.requested_duration_minutes != requested_duration_minutes:
        raise ReturnDurationViolationError(
            "approved return caps cannot change requested_duration_minutes"
        )
    return ReturnPlanApplication(
        status_code=ReturnPlanApplicationStatusCode.APPROVED_CAPS_APPLIED,
        requested_duration_minutes=requested_duration_minutes,
        plan=adjusted_plan,
        cap_policy_version=cap_policy.version_code,
        load_cap_code=cap_policy.load_cap_code,
        volume_cap_code=cap_policy.volume_cap_code,
    )
