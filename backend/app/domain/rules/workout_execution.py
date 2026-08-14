"""Deterministic workout execution, safety-event, and notification rules."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backend.app.domain.rules.safety import (
    ACUTE_MUSCULOSKELETAL_REACTION_CODES,
    EMERGENCY_REACTION_CODES,
    DiscomfortSeverityCode,
    SafetyContext,
    SafetyRequiredActionCode,
)

WORKOUT_EXECUTION_RULE_VERSION = "1.0.0"
WORKOUT_SAFETY_EVENT_RULE_VERSION = "1.0.0"


class WorkoutSessionStatusCode(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NOT_COMPLETED = "NOT_COMPLETED"
    STOPPED_FOR_SAFETY = "STOPPED_FOR_SAFETY"


TERMINAL_WORKOUT_SESSION_STATUSES = frozenset(
    {
        WorkoutSessionStatusCode.COMPLETED,
        WorkoutSessionStatusCode.PARTIAL,
        WorkoutSessionStatusCode.NOT_COMPLETED,
        WorkoutSessionStatusCode.STOPPED_FOR_SAFETY,
    }
)


class WorkoutBlockStatusCode(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class WorkoutTimerEventCode(StrEnum):
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    END = "END"


class WorkoutNotCompletedReasonCode(StrEnum):
    TIME_SHORTAGE = "TIME_SHORTAGE"
    FATIGUE = "FATIGUE"
    MUSCLE_SORENESS = "MUSCLE_SORENESS"
    PAIN = "PAIN"
    SCHEDULE_CHANGE = "SCHEDULE_CHANGE"
    LOCATION_EQUIPMENT = "LOCATION_EQUIPMENT"
    WEATHER = "WEATHER"
    DIFFICULTY = "DIFFICULTY"
    LOW_INTEREST = "LOW_INTEREST"
    LOW_MOTIVATION = "LOW_MOTIVATION"


class SafetyInstructionCode(StrEnum):
    SHOW_CAUTION = "SHOW_CAUTION"
    STOP_SESSION = "STOP_SESSION"
    STOP_AND_SEEK_HELP = "STOP_AND_SEEK_HELP"


class WorkoutSafetyReasonCode(StrEnum):
    MILD_DISCOMFORT = "MILD_DISCOMFORT"
    MODERATE_DISCOMFORT = "MODERATE_DISCOMFORT"
    SEVERE_DISCOMFORT = "SEVERE_DISCOMFORT"
    ACUTE_MUSCULOSKELETAL_REACTION = "ACUTE_MUSCULOSKELETAL_REACTION"
    EMERGENCY_ADVERSE_REACTION = "EMERGENCY_ADVERSE_REACTION"


class WorkoutSafetyGuidanceCode(StrEnum):
    MILD_DISCOMFORT_CAUTION = "MILD_DISCOMFORT_CAUTION"
    MODERATE_DISCOMFORT_CAUTION = "MODERATE_DISCOMFORT_CAUTION"
    SEVERE_OR_ACUTE_STOP = "SEVERE_OR_ACUTE_STOP"
    SERIOUS_ADVERSE_REACTION_STOP = "SERIOUS_ADVERSE_REACTION_STOP"


class DecisionSelectionCode(StrEnum):
    FINAL_ROUTINE = "FINAL_ROUTINE"
    REST = "REST"


class WorkoutExecutionRuleError(ValueError):
    """Base exception for invalid workout-execution domain input."""


class InvalidWorkoutExecutionInputError(WorkoutExecutionRuleError):
    """Raised when workout evidence violates a structural invariant."""


class InvalidSessionTransitionError(WorkoutExecutionRuleError):
    """Raised when a session transition is not permitted."""


class NotCompletedReasonRequiredError(InvalidSessionTransitionError):
    """Raised when a zero-completion session is finished without a reason."""


class InvalidWorkoutSafetyEventError(WorkoutExecutionRuleError):
    """Raised when an in-session safety event cannot be classified."""


@dataclass(frozen=True, slots=True)
class WorkoutCompletionEvidence:
    """Normalized evidence; only block checks and a safety stop are authoritative."""

    block_status_codes: tuple[WorkoutBlockStatusCode, ...]
    safety_stopped: bool = False
    actual_elapsed_seconds: int = 0
    timer_event_codes: tuple[WorkoutTimerEventCode, ...] = ()
    wearable_workout_detected: bool = False
    calendar_marked_performed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.block_status_codes, tuple) or not self.block_status_codes:
            raise InvalidWorkoutExecutionInputError(
                "block_status_codes must be a non-empty immutable tuple"
            )
        if any(
            not isinstance(status, WorkoutBlockStatusCode) for status in self.block_status_codes
        ):
            raise InvalidWorkoutExecutionInputError(
                "block_status_codes must contain only WorkoutBlockStatusCode values"
            )
        if not isinstance(self.safety_stopped, bool):
            raise InvalidWorkoutExecutionInputError("safety_stopped must be a boolean")
        if (
            isinstance(self.actual_elapsed_seconds, bool)
            or not isinstance(self.actual_elapsed_seconds, int)
            or self.actual_elapsed_seconds < 0
        ):
            raise InvalidWorkoutExecutionInputError(
                "actual_elapsed_seconds must be a non-negative integer"
            )
        if not isinstance(self.timer_event_codes, tuple) or any(
            not isinstance(event, WorkoutTimerEventCode) for event in self.timer_event_codes
        ):
            raise InvalidWorkoutExecutionInputError(
                "timer_event_codes must contain only WorkoutTimerEventCode values"
            )
        if not isinstance(self.wearable_workout_detected, bool):
            raise InvalidWorkoutExecutionInputError("wearable_workout_detected must be a boolean")
        if not isinstance(self.calendar_marked_performed, bool):
            raise InvalidWorkoutExecutionInputError("calendar_marked_performed must be a boolean")

    @property
    def completed_block_count(self) -> int:
        return sum(status is WorkoutBlockStatusCode.COMPLETED for status in self.block_status_codes)

    @property
    def total_block_count(self) -> int:
        return len(self.block_status_codes)


@dataclass(frozen=True, slots=True)
class WorkoutSafetyEventDecision:
    instruction_code: SafetyInstructionCode
    resulting_action_code: SafetyRequiredActionCode | None
    session_status_code: WorkoutSessionStatusCode
    reason_code: WorkoutSafetyReasonCode
    guidance_code: WorkoutSafetyGuidanceCode
    veto: bool
    safety_event_rule_version: str = WORKOUT_SAFETY_EVENT_RULE_VERSION

    def __post_init__(self) -> None:
        stopped = self.session_status_code is WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
        if self.instruction_code is SafetyInstructionCode.SHOW_CAUTION:
            if stopped or self.resulting_action_code is not None or self.veto:
                raise InvalidWorkoutSafetyEventError(
                    "SHOW_CAUTION must keep the session in progress without a veto"
                )
            return
        if not stopped or self.resulting_action_code is None or not self.veto:
            raise InvalidWorkoutSafetyEventError(
                "stop instructions must veto and stop the session for safety"
            )
        if (
            self.instruction_code is SafetyInstructionCode.STOP_SESSION
            and self.resulting_action_code is not SafetyRequiredActionCode.REST
        ):
            raise InvalidWorkoutSafetyEventError("STOP_SESSION must result in REST")
        if (
            self.instruction_code is SafetyInstructionCode.STOP_AND_SEEK_HELP
            and self.resulting_action_code is not SafetyRequiredActionCode.STOP_AND_SEEK_HELP
        ):
            raise InvalidWorkoutSafetyEventError(
                "STOP_AND_SEEK_HELP must preserve the safety veto action"
            )


def derive_official_session_status(
    evidence: WorkoutCompletionEvidence,
) -> WorkoutSessionStatusCode:
    """Derive the official status without using time, wearable, or calendar signals."""

    if evidence.safety_stopped:
        return WorkoutSessionStatusCode.STOPPED_FOR_SAFETY
    completed_count = evidence.completed_block_count
    if completed_count == evidence.total_block_count:
        return WorkoutSessionStatusCode.COMPLETED
    if completed_count:
        return WorkoutSessionStatusCode.PARTIAL
    return WorkoutSessionStatusCode.NOT_COMPLETED


def is_terminal_session_status(status_code: WorkoutSessionStatusCode) -> bool:
    return status_code in TERMINAL_WORKOUT_SESSION_STATUSES


def require_block_change_allowed(status_code: WorkoutSessionStatusCode) -> None:
    """Permit block mutation only while the session is in progress."""

    if status_code is not WorkoutSessionStatusCode.IN_PROGRESS:
        raise InvalidSessionTransitionError(
            f"block status cannot change while session is {status_code.value}"
        )


def start_session(status_code: WorkoutSessionStatusCode) -> WorkoutSessionStatusCode:
    if status_code is not WorkoutSessionStatusCode.PLANNED:
        raise InvalidSessionTransitionError(
            f"only PLANNED sessions can start, got {status_code.value}"
        )
    return WorkoutSessionStatusCode.IN_PROGRESS


def finish_session(
    status_code: WorkoutSessionStatusCode,
    evidence: WorkoutCompletionEvidence,
) -> WorkoutSessionStatusCode:
    """Finish an in-progress session with at least one checked block or a safety stop."""

    if status_code is not WorkoutSessionStatusCode.IN_PROGRESS:
        raise InvalidSessionTransitionError(
            f"only IN_PROGRESS sessions can finish, got {status_code.value}"
        )
    resulting_status = derive_official_session_status(evidence)
    if resulting_status is WorkoutSessionStatusCode.NOT_COMPLETED:
        raise NotCompletedReasonRequiredError(
            "zero completed blocks require the NOT_COMPLETED transition and one reason"
        )
    return resulting_status


def mark_session_not_completed(
    status_code: WorkoutSessionStatusCode,
    evidence: WorkoutCompletionEvidence,
    reason_code: WorkoutNotCompletedReasonCode,
) -> WorkoutSessionStatusCode:
    """Close a planned or active zero-completion session with one learning reason."""

    if status_code not in {
        WorkoutSessionStatusCode.PLANNED,
        WorkoutSessionStatusCode.IN_PROGRESS,
    }:
        raise InvalidSessionTransitionError(
            f"terminal session {status_code.value} cannot be changed"
        )
    if not isinstance(reason_code, WorkoutNotCompletedReasonCode):
        raise InvalidWorkoutExecutionInputError(
            "reason_code must be an approved WorkoutNotCompletedReasonCode"
        )
    if derive_official_session_status(evidence) is not WorkoutSessionStatusCode.NOT_COMPLETED:
        raise InvalidSessionTransitionError(
            "NOT_COMPLETED requires zero completed blocks and no safety stop"
        )
    return WorkoutSessionStatusCode.NOT_COMPLETED


def classify_workout_safety_event(
    status_code: WorkoutSessionStatusCode,
    context: SafetyContext,
) -> WorkoutSafetyEventDecision:
    """Classify an in-session safety event using the approved deterministic priority."""

    if status_code is not WorkoutSessionStatusCode.IN_PROGRESS:
        raise InvalidSessionTransitionError(
            f"safety events require IN_PROGRESS, got {status_code.value}"
        )
    if not context.discomforts and not context.adverse_reaction_codes:
        raise InvalidWorkoutSafetyEventError(
            "a safety event requires discomfort or an adverse reaction"
        )

    reaction_codes = frozenset(context.adverse_reaction_codes)
    if reaction_codes & EMERGENCY_REACTION_CODES:
        return WorkoutSafetyEventDecision(
            instruction_code=SafetyInstructionCode.STOP_AND_SEEK_HELP,
            resulting_action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
            session_status_code=WorkoutSessionStatusCode.STOPPED_FOR_SAFETY,
            reason_code=WorkoutSafetyReasonCode.EMERGENCY_ADVERSE_REACTION,
            guidance_code=WorkoutSafetyGuidanceCode.SERIOUS_ADVERSE_REACTION_STOP,
            veto=True,
        )

    if reaction_codes & ACUTE_MUSCULOSKELETAL_REACTION_CODES:
        return WorkoutSafetyEventDecision(
            instruction_code=SafetyInstructionCode.STOP_SESSION,
            resulting_action_code=SafetyRequiredActionCode.REST,
            session_status_code=WorkoutSessionStatusCode.STOPPED_FOR_SAFETY,
            reason_code=WorkoutSafetyReasonCode.ACUTE_MUSCULOSKELETAL_REACTION,
            guidance_code=WorkoutSafetyGuidanceCode.SEVERE_OR_ACUTE_STOP,
            veto=True,
        )

    highest_severity = max(
        (discomfort.severity_code for discomfort in context.discomforts),
        default=DiscomfortSeverityCode.NONE,
    )
    if highest_severity is DiscomfortSeverityCode.SEVERE:
        return WorkoutSafetyEventDecision(
            instruction_code=SafetyInstructionCode.STOP_SESSION,
            resulting_action_code=SafetyRequiredActionCode.REST,
            session_status_code=WorkoutSessionStatusCode.STOPPED_FOR_SAFETY,
            reason_code=WorkoutSafetyReasonCode.SEVERE_DISCOMFORT,
            guidance_code=WorkoutSafetyGuidanceCode.SEVERE_OR_ACUTE_STOP,
            veto=True,
        )
    if highest_severity is DiscomfortSeverityCode.MODERATE:
        return WorkoutSafetyEventDecision(
            instruction_code=SafetyInstructionCode.SHOW_CAUTION,
            resulting_action_code=None,
            session_status_code=WorkoutSessionStatusCode.IN_PROGRESS,
            reason_code=WorkoutSafetyReasonCode.MODERATE_DISCOMFORT,
            guidance_code=WorkoutSafetyGuidanceCode.MODERATE_DISCOMFORT_CAUTION,
            veto=False,
        )
    if highest_severity is DiscomfortSeverityCode.MILD:
        return WorkoutSafetyEventDecision(
            instruction_code=SafetyInstructionCode.SHOW_CAUTION,
            resulting_action_code=None,
            session_status_code=WorkoutSessionStatusCode.IN_PROGRESS,
            reason_code=WorkoutSafetyReasonCode.MILD_DISCOMFORT,
            guidance_code=WorkoutSafetyGuidanceCode.MILD_DISCOMFORT_CAUTION,
            veto=False,
        )
    raise InvalidWorkoutSafetyEventError("safety event input could not be classified")


def should_send_pressure_notification(
    *,
    selection_code: DecisionSelectionCode | None,
    selection_local_date: date | None,
    notification_local_date: date,
) -> bool:
    """Suppress pressure notifications on the local date a user selects REST."""

    return not (
        selection_code is DecisionSelectionCode.REST
        and selection_local_date == notification_local_date
    )
