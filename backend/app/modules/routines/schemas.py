from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.modules.routines.codes import (
    RoutinePhaseCode,
    RoutineStatusCode,
    RoutineTierCode,
)


class RoutineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_from: date
    goal_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    # Optional so existing clients keep the profile default. When present the
    # user chose a duration for this routine, which makes the request a
    # USER_OVERRIDE rather than a rewrite of the stored profile default.
    requested_duration_minutes: int | None = Field(default=None, ge=1, le=240)


class RoutineItemResponse(BaseModel):
    id: UUID
    exercise_id: UUID
    exercise_name: str
    sequence: int
    phase_code: RoutinePhaseCode
    tier_code: RoutineTierCode
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    rest_seconds_per_set: int
    instruction_available: bool


class RoutineDayResponse(BaseModel):
    id: UUID
    sequence: int
    title: str
    training_type_code: str
    body_focus_code: str | None
    requested_duration_minutes: int
    estimated_duration_seconds: int
    estimated_calories_burned: float | None
    items: list[RoutineItemResponse]


class RoutineResponse(BaseModel):
    id: UUID
    version: int
    goal_code: str
    status_code: RoutineStatusCode
    effective_from: date
    catalog_version: str
    days: list[RoutineDayResponse]
    created_at: datetime


__all__ = [
    "RoutineCreateRequest",
    "RoutineDayResponse",
    "RoutineItemResponse",
    "RoutineResponse",
]
