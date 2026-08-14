from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.modules.routines.schemas import RoutineResponse


class InitialWeeklyPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WeeklyPlanUserEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routine_id: UUID
    location_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


class WeeklyPlanRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: Literal["AI", "USER"]
    expected_revision_sequence: int = Field(ge=1)
    user_edits: WeeklyPlanUserEdits | None = None

    @model_validator(mode="after")
    def validate_source_payload(self) -> Self:
        if self.source_code == "USER" and self.user_edits is None:
            raise ValueError("USER revisions require user_edits")
        if self.source_code == "AI" and self.user_edits is not None:
            raise ValueError("AI revisions cannot contain user_edits")
        return self


class WeeklyPlanRevisionResponse(BaseModel):
    revision_id: UUID
    week_start: date
    week_end: date
    revision_sequence: int
    ai_revision_count: Literal[0, 1, 2]
    source_code: Literal["INITIAL", "AI", "USER"]
    source_weekly_report_id: UUID | None
    safety_status_code: Literal["PASS", "NEEDS_INPUT", "REVISE", "BLOCKED", "FAILED"]
    routine: RoutineResponse | None
    selected_location_code: str | None
    finalized: bool
    finalized_at: datetime | None
    revision_reason_codes: list[str]
    finalization_reason_codes: list[str]
    created_at: datetime


__all__ = [
    "InitialWeeklyPlanRequest",
    "WeeklyPlanRevisionRequest",
    "WeeklyPlanRevisionResponse",
    "WeeklyPlanUserEdits",
]
