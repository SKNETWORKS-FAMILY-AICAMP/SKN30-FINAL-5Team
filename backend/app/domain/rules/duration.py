"""Deterministic requested-duration calculation and preservation rules."""

from dataclasses import dataclass
from enum import StrEnum

DURATION_RULE_VERSION = "1.0.0"
SECONDS_PER_MINUTE = 60

# The approved window a plan may land within when the eligible pool cannot hit
# the requested duration exactly (project owner approval, 2026-08-27; see
# docs/tasks/TASK-ROUTINE-EQUIPMENT-AND-DURATION.md and AGENTS.md section 7).
# The closest achievable plan wins inside this window; outside it the request
# fails rather than silently shortening the session.
DURATION_TOLERANCE_SECONDS = 300


class DurationAdjustmentSourceCode(StrEnum):
    """The only approved sources for the daily requested duration."""

    PROFILE = "PROFILE"
    USER_OVERRIDE = "USER_OVERRIDE"


class DurationRuleError(ValueError):
    """Base exception for duration contract violations."""


class InvalidDurationInputError(DurationRuleError):
    """Raised when timing data is not valid under the documented contract."""


class RequestedDurationNotPreservedError(DurationRuleError):
    """Raised when PROFILE input changes the user's stored default duration."""


def _require_integer(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidDurationInputError(f"{field_name} must be an integer")
    return value


def _require_positive_integer(value: int, *, field_name: str) -> int:
    checked = _require_integer(value, field_name=field_name)
    if checked <= 0:
        raise InvalidDurationInputError(f"{field_name} must be greater than 0")
    return checked


def _require_inclusive_range(
    value: int,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    checked = _require_integer(value, field_name=field_name)
    if not minimum <= checked <= maximum:
        raise InvalidDurationInputError(
            f"{field_name} must be between {minimum} and {maximum} seconds"
        )
    return checked


def _require_non_negative_integer(value: int, *, field_name: str) -> int:
    checked = _require_integer(value, field_name=field_name)
    if checked < 0:
        raise InvalidDurationInputError(f"{field_name} must be greater than or equal to 0")
    return checked


@dataclass(frozen=True, slots=True)
class DurationRequest:
    """Validated profile/default and daily requested-duration relationship."""

    profile_duration_minutes: int
    requested_duration_minutes: int
    adjustment_source_code: DurationAdjustmentSourceCode

    def __post_init__(self) -> None:
        _require_positive_integer(
            self.profile_duration_minutes,
            field_name="profile_duration_minutes",
        )
        _require_positive_integer(
            self.requested_duration_minutes,
            field_name="requested_duration_minutes",
        )
        if not isinstance(self.adjustment_source_code, DurationAdjustmentSourceCode):
            raise InvalidDurationInputError(
                "adjustment_source_code must be PROFILE or USER_OVERRIDE"
            )
        if (
            self.adjustment_source_code is DurationAdjustmentSourceCode.PROFILE
            and self.requested_duration_minutes != self.profile_duration_minutes
        ):
            raise RequestedDurationNotPreservedError(
                "PROFILE requested duration must match the profile default"
            )

    @property
    def target_duration_seconds(self) -> int:
        return self.requested_duration_minutes * SECONDS_PER_MINUTE


@dataclass(frozen=True, slots=True)
class PlanItemDuration:
    """Total work, rest, and entry-transition timing for one plan item."""

    work_seconds: int
    rest_seconds: int
    transition_seconds: int

    def __post_init__(self) -> None:
        _require_non_negative_integer(self.work_seconds, field_name="work_seconds")
        _require_non_negative_integer(self.rest_seconds, field_name="rest_seconds")
        _require_inclusive_range(
            self.transition_seconds,
            field_name="transition_seconds",
            minimum=10,
            maximum=20,
        )

    @property
    def estimated_item_seconds(self) -> int:
        return self.work_seconds + self.rest_seconds + self.transition_seconds


@dataclass(frozen=True, slots=True)
class DurationPlan:
    """All components that contribute to planned duration."""

    setup_seconds: int
    warmup_seconds: int
    items: tuple[PlanItemDuration, ...]
    cooldown_seconds: int

    def __post_init__(self) -> None:
        _require_inclusive_range(
            self.setup_seconds,
            field_name="setup_seconds",
            minimum=0,
            maximum=60,
        )
        _require_inclusive_range(
            self.warmup_seconds,
            field_name="warmup_seconds",
            minimum=60,
            maximum=180,
        )
        _require_inclusive_range(
            self.cooldown_seconds,
            field_name="cooldown_seconds",
            minimum=45,
            maximum=120,
        )
        if not isinstance(self.items, tuple):
            raise InvalidDurationInputError("items must be an immutable tuple")
        if any(not isinstance(item, PlanItemDuration) for item in self.items):
            raise InvalidDurationInputError("items must contain only PlanItemDuration values")


@dataclass(frozen=True, slots=True)
class DurationAssessment:
    """Reproducible comparison of a validated plan and requested target."""

    requested_duration_minutes: int
    target_duration_seconds: int
    estimated_duration_seconds: int
    delta_seconds: int
    is_exact_match: bool
    duration_rule_version: str = DURATION_RULE_VERSION


class DurationTargetMismatchError(DurationRuleError):
    """Raised when a plan is shorter or longer than the requested target."""

    def __init__(self, assessment: DurationAssessment) -> None:
        self.assessment = assessment
        super().__init__(
            "estimated duration "
            f"{assessment.estimated_duration_seconds}s does not match requested target "
            f"{assessment.target_duration_seconds}s"
        )


def validate_requested_duration(
    *,
    profile_duration_minutes: int,
    requested_duration_minutes: int,
    adjustment_source_code: str | DurationAdjustmentSourceCode,
) -> DurationRequest:
    """Validate source semantics and return the effective requested duration."""

    try:
        source_code = DurationAdjustmentSourceCode(adjustment_source_code)
    except (TypeError, ValueError) as exc:
        raise InvalidDurationInputError(
            "adjustment_source_code must be PROFILE or USER_OVERRIDE"
        ) from exc

    return DurationRequest(
        profile_duration_minutes=profile_duration_minutes,
        requested_duration_minutes=requested_duration_minutes,
        adjustment_source_code=source_code,
    )


def calculate_estimated_duration_seconds(plan: DurationPlan) -> int:
    """Sum every documented component of planned duration without rounding."""

    return (
        plan.setup_seconds
        + plan.warmup_seconds
        + sum(item.estimated_item_seconds for item in plan.items)
        + plan.cooldown_seconds
    )


def assess_duration(request: DurationRequest, plan: DurationPlan) -> DurationAssessment:
    """Compare the complete plan duration with its immutable request target."""

    estimated_duration_seconds = calculate_estimated_duration_seconds(plan)
    target_duration_seconds = request.target_duration_seconds
    delta_seconds = estimated_duration_seconds - target_duration_seconds
    return DurationAssessment(
        requested_duration_minutes=request.requested_duration_minutes,
        target_duration_seconds=target_duration_seconds,
        estimated_duration_seconds=estimated_duration_seconds,
        delta_seconds=delta_seconds,
        is_exact_match=delta_seconds == 0,
    )


def require_exact_duration(
    request: DurationRequest,
    plan: DurationPlan,
    *,
    tolerance_seconds: int = 0,
) -> DurationAssessment:
    """Return an assessment only when the plan preserves the requested time.

    ``tolerance_seconds`` defaults to zero, so every existing caller keeps the
    exact-match rule. Routine creation passes a non-zero allowance under the
    2026-08-27 decision recorded in docs/tasks; the plan may then differ from
    the target by at most that many seconds in either direction.
    """

    if tolerance_seconds < 0:
        raise InvalidDurationInputError("duration tolerance must not be negative")
    assessment = assess_duration(request, plan)
    if not assessment.is_exact_match and abs(assessment.delta_seconds) > tolerance_seconds:
        raise DurationTargetMismatchError(assessment)
    return assessment
