from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class WeekResponse(BaseModel):
    week_id: UUID
    week_start: date
    week_end: date
    timezone: str
    target_workout_count: int
    plan_origin_code: Literal["COLD_START", "WEEKLY_REPORT"]
    cold_start_applied: bool
    status_code: Literal["OPEN", "CLOSED"]
    closed_at: datetime | None
    report_id: UUID | None
    report_status_code: Literal["GENERATED", "ACKNOWLEDGED", "FAILED"] | None


class WeeklyReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_week_status_code: Literal["CLOSED"]


class WeeklyReportCounts(BaseModel):
    completed: int
    partial: int
    not_completed: int
    stopped_for_safety: int


class WeeklyPatternSummary(BaseModel):
    high_completion_windows: list[str]
    high_completion_exercise_types: list[str]
    high_completion_intensity_codes: list[str]
    blocker_reason_codes: list[str]


class WeeklyReportResponse(BaseModel):
    report_id: UUID
    week_start: date
    week_end: date
    status_code: Literal["GENERATED", "ACKNOWLEDGED"]
    counts: WeeklyReportCounts
    primary_miss_reason_code: str | None
    completion_rate: float
    persistence_rate: float
    negotiation_success_rate: float | None
    weekday_failure_summary: dict[str, Any]
    pattern_summary: WeeklyPatternSummary
    decision_summary: str
    adjustment_direction_code: Literal["MAINTAIN", "REDUCE", "INCREASE", "MIXED"]
    next_action: str
    agent_summaries: dict[str, Any] | None
    summary: str
    acknowledged_at: datetime | None
    generated_at: datetime


class WeeklyReportAcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged_at: AwareDatetime


__all__ = [
    "WeekResponse",
    "WeeklyPatternSummary",
    "WeeklyReportAcknowledgementRequest",
    "WeeklyReportCounts",
    "WeeklyReportCreateRequest",
    "WeeklyReportResponse",
]
