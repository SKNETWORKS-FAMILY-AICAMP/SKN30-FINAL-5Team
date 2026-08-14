from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

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


class DecisionSelectionResponse(BaseModel):
    selection_id: UUID
    decision_id: UUID
    option_id: UUID
    selected_action_code: Literal["KEEP", "DOWNSHIFT", "CHANGE", "RECOVERY", "REST"]
    workout_session: WorkoutSessionSummary | None
    selected_at: datetime


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


__all__ = [
    "DecisionSelectionRequest",
    "DecisionSelectionResponse",
    "WorkoutAdditionalActivityRequest",
    "WorkoutAdditionalActivityResponse",
    "WorkoutSessionItemUpdateRequest",
    "WorkoutSessionItemUpdateResponse",
    "WorkoutSessionStartRequest",
    "WorkoutSessionStartResponse",
    "WorkoutTimerEventRequest",
    "WorkoutTimerEventResponse",
]
