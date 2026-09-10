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
    # Legacy name from the single-status era. Kept so existing clients keep reading.
    stopped_for_safety: int
    # The same number under the split axes P1-C introduced. Optional so a report
    # generated before this release still deserializes.
    safety_stopped_session_count: int | None = None


class WeeklyPatternSummary(BaseModel):
    high_completion_windows: list[str]
    high_completion_exercise_types: list[str]
    high_completion_intensity_codes: list[str]
    blocker_reason_codes: list[str]


class WeeklyConditionSummary(BaseModel):
    checkin_count: int
    fatigue_level_counts: dict[str, int]
    fatigue_change_code: Literal["IMPROVED", "STABLE", "DECLINED", "INSUFFICIENT_DATA"]
    pain_checkin_count: int
    workout_pain_or_safety_stop_count: int


class WeeklyNextRecommendation(BaseModel):
    intensity: str
    volume: str
    duration: str
    pain_response: str


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
    # Added as optional fields so reports generated before the metrics expansion
    # continue to deserialize and existing clients can ignore them.
    total_workout_seconds: int | None = None
    total_estimated_calories_burned: float | None = None
    average_intensity_code: str | None = None
    most_performed_training_type_code: str | None = None
    most_performed_exercise_name: str | None = None
    completed_count_change: int | None = None
    highlight_codes: list[str] | None = None
    improvement_codes: list[str] | None = None
    routine_difficulty_code: Literal["EASY", "APPROPRIATE", "HARD"] | None = None
    condition_summary: WeeklyConditionSummary | None = None
    outcome_reason_summary: dict[str, dict[str, int]] | None = None
    recommendation_action_counts: dict[str, int] | None = None
    adjustment_summary: str | None = None
    next_week_recommendation: WeeklyNextRecommendation | None = None
    coach_message: str | None = None
    acknowledged_at: datetime | None
    generated_at: datetime


class WeeklyReportAcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged_at: AwareDatetime


__all__ = [
    "WeekResponse",
    "WeeklyPatternSummary",
    "WeeklyConditionSummary",
    "WeeklyNextRecommendation",
    "WeeklyReportAcknowledgementRequest",
    "WeeklyReportCounts",
    "WeeklyReportCreateRequest",
    "WeeklyReportResponse",
]
