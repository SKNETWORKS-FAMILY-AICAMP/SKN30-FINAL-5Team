from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.app.domain.rules.safety import AdverseReactionCode, BodyAreaCode
from backend.app.domain.rules.workout_execution import WorkoutNotCompletedReasonCode
from backend.app.modules.checkins.codes import DiscomfortSeverityCode

MachineCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$"),
]


class DecisionSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: UUID


class WorkoutSessionSummary(BaseModel):
    session_id: UUID
    status_code: Literal["PLANNED"]
    completion_code: Literal["COMPLETED", "PARTIAL", "NOT_COMPLETED"] | None = None
    execution_state_code: str | None = None
    target_duration_seconds: int | None = None


class DecisionSelectionResponse(BaseModel):
    selection_id: UUID
    decision_id: UUID
    option_id: UUID
    selected_action_code: Literal["KEEP", "DOWNSHIFT", "CHANGE", "RECOVERY", "REST"]
    workout_session: WorkoutSessionSummary | None
    selected_at: datetime
    pressure_notifications_allowed: bool | None = None


class WorkoutSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    started_at: AwareDatetime


class WorkoutSessionItemResponse(BaseModel):
    plan_item_id: UUID
    status_code: Literal["PENDING", "COMPLETED"]
    completed_at: datetime | None


class WorkoutSessionStartResponse(BaseModel):
    session_id: UUID
    status_code: Literal["IN_PROGRESS"]
    started_at: datetime
    items: list[WorkoutSessionItemResponse]
    current_plan_item_id: UUID | None
    completion_code: None = None
    execution_state_code: Literal["RUNNING"]
    target_duration_seconds: int
    accumulated_progress_seconds: int
    accumulated_rest_seconds: int
    accumulated_paused_seconds: int
    is_resumable: Literal[False]


class WorkoutSessionItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status_code: Literal["PENDING", "COMPLETED"]
    client_recorded_at: AwareDatetime


class WorkoutSessionItemUpdateResponse(BaseModel):
    session_id: UUID
    status_code: Literal["IN_PROGRESS"]
    item: WorkoutSessionItemResponse
    completed_item_count: int
    total_item_count: int
    next_pending_plan_item_id: UUID | None


class WorkoutTimerEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_code: Literal["START", "PAUSE", "RESUME", "END"]
    occurred_at: AwareDatetime
    client_recorded_at: AwareDatetime


class WorkoutTimerEventResponse(BaseModel):
    event_id: UUID
    session_id: UUID
    event_code: Literal["START", "PAUSE", "RESUME", "END"]
    occurred_at: datetime
    client_recorded_at: datetime
    created_at: datetime
    session_status_code: Literal["IN_PROGRESS"]
    execution_state_code: Literal["RUNNING", "PAUSED"]
    accumulated_progress_seconds: int
    accumulated_rest_seconds: int
    accumulated_paused_seconds: int


class WorkoutSessionStopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stopped_at: AwareDatetime
    stop_reason_code: Literal[
        "HIGH_FATIGUE", "TIME_SHORTAGE", "RESUME_LATER", "PAIN_OR_ABNORMAL_RESPONSE"
    ]


class WorkoutSessionStopResponse(BaseModel):
    session_id: UUID
    completion_code: Literal["PARTIAL", "NOT_COMPLETED"] | None
    execution_state_code: Literal["STOPPED_RESUMABLE", "STOPPED_SAFETY"]
    stop_reason_code: Literal[
        "HIGH_FATIGUE", "TIME_SHORTAGE", "RESUME_LATER", "PAIN_OR_ABNORMAL_RESPONSE"
    ]
    is_resumable: bool
    accumulated_progress_seconds: int
    accumulated_rest_seconds: int
    accumulated_paused_seconds: int


class WorkoutAdditionalActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_type_code: MachineCode
    duration_seconds: int = Field(gt=0)
    intensity_code: MachineCode | None = None
    note: str | None = Field(default=None, max_length=500)


class WorkoutAdditionalActivityResponse(BaseModel):
    activity_id: UUID
    session_id: UUID
    activity_type_code: str
    duration_seconds: int
    intensity_code: str | None
    note: str | None
    created_at: datetime
    session_status_code: Literal["IN_PROGRESS"]


class WorkoutDiscomfortInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_area_code: BodyAreaCode
    severity_code: DiscomfortSeverityCode


class WorkoutSafetyEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: AwareDatetime


class WorkoutSafetyEventResponse(BaseModel):
    event_id: UUID
    result_code: Literal["SESSION_STOPPED", "STOP_AND_SEEK_HELP"]
    execution_state_code: Literal["STOPPED_SAFETY"]
    completion_code: Literal["PARTIAL", "NOT_COMPLETED"]
    is_resumable: Literal[False]
    guidance: str


class WorkoutSessionFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finished_at: AwareDatetime
    actual_elapsed_seconds: int = Field(ge=0)


class WorkoutSessionFinishResponse(BaseModel):
    session_id: UUID
    status_code: Literal["COMPLETED", "PARTIAL"]
    ended_at: datetime
    completed_item_count: int
    total_item_count: int
    actual_elapsed_seconds: int
    estimated_calories_burned: float | None
    completion_code: Literal["COMPLETED", "PARTIAL"]
    execution_state_code: Literal["COMPLETED"]


class WorkoutSessionNotCompletedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ended_at: AwareDatetime
    reason_code: WorkoutNotCompletedReasonCode


class WorkoutSessionNotCompletedResponse(BaseModel):
    session_id: UUID
    status_code: Literal["NOT_COMPLETED"]
    ended_at: datetime
    reason_code: WorkoutNotCompletedReasonCode
    completed_item_count: Literal[0]
    total_item_count: int
    penalty_applied: Literal[False]
    completion_code: Literal["NOT_COMPLETED"]
    execution_state_code: Literal["COMPLETED"]


class WorkoutFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    difficulty_code: Literal["EASY", "APPROPRIATE", "HARD"]
    fatigue_code: MachineCode | None = None
    satisfaction_code: MachineCode | None = None
    pain_occurred: bool
    discomforts: list[WorkoutDiscomfortInput] = Field(default_factory=list)
    adverse_reaction_codes: list[AdverseReactionCode] = Field(default_factory=list)

    @field_validator("discomforts")
    @classmethod
    def reject_duplicate_body_areas(
        cls, value: list[WorkoutDiscomfortInput]
    ) -> list[WorkoutDiscomfortInput]:
        if len({item.body_area_code for item in value}) != len(value):
            raise ValueError("body_area_code must not be duplicated")
        return value

    @field_validator("adverse_reaction_codes")
    @classmethod
    def reject_duplicate_reactions(
        cls, value: list[AdverseReactionCode]
    ) -> list[AdverseReactionCode]:
        if len(set(value)) != len(value):
            raise ValueError("adverse_reaction_codes must not contain duplicates")
        return value


class WorkoutFeedbackResponse(BaseModel):
    session_id: UUID
    session_status_code: Literal["COMPLETED", "PARTIAL", "NOT_COMPLETED", "STOPPED_FOR_SAFETY"]
    created_at: datetime
    guidance_code: str | None
    guidance: str | None
    pressure_notifications_allowed: bool


class WorkoutSessionLogSummary(BaseModel):
    session_id: UUID
    local_date: date
    status_code: str
    completed_item_count: int
    total_item_count: int
    requested_duration_minutes: int
    training_type_code: str
    not_completed_reason_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


class WorkoutSessionListResponse(BaseModel):
    items: list[WorkoutSessionLogSummary]
    next_cursor: str | None


class WorkoutSessionItemResult(BaseModel):
    plan_item_id: UUID
    exercise_id: UUID
    exercise_name: str
    status_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    completed_at: datetime | None


class WorkoutFeedbackSummary(BaseModel):
    perceived_difficulty_code: str | None
    post_workout_discomfort_reported: bool


class WorkoutSessionDetailResponse(BaseModel):
    session_id: UUID
    local_date: date
    status_code: str
    completed_item_count: int
    total_item_count: int
    requested_duration_minutes: int
    items: list[WorkoutSessionItemResult]
    feedback: WorkoutFeedbackSummary | None
    not_completed_reason_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


__all__ = [
    "DecisionSelectionRequest",
    "DecisionSelectionResponse",
    "WorkoutAdditionalActivityRequest",
    "WorkoutAdditionalActivityResponse",
    "WorkoutDiscomfortInput",
    "WorkoutFeedbackRequest",
    "WorkoutFeedbackResponse",
    "WorkoutFeedbackSummary",
    "WorkoutSafetyEventRequest",
    "WorkoutSafetyEventResponse",
    "WorkoutSessionFinishRequest",
    "WorkoutSessionFinishResponse",
    "WorkoutSessionDetailResponse",
    "WorkoutSessionItemUpdateRequest",
    "WorkoutSessionItemUpdateResponse",
    "WorkoutSessionStartRequest",
    "WorkoutSessionStartResponse",
    "WorkoutSessionStopRequest",
    "WorkoutSessionStopResponse",
    "WorkoutSessionNotCompletedRequest",
    "WorkoutSessionNotCompletedResponse",
    "WorkoutSessionItemResult",
    "WorkoutSessionListResponse",
    "WorkoutSessionLogSummary",
    "WorkoutTimerEventRequest",
    "WorkoutTimerEventResponse",
]
