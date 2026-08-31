from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WeekProfile:
    timezone: str
    target_workout_count: int
    has_prior_week: bool


@dataclass(frozen=True, slots=True)
class WeekRecord:
    week_id: UUID
    user_id: UUID
    week_start: date
    week_end: date
    timezone: str
    target_workout_count: int
    plan_origin_code: str
    cold_start_applied: bool
    status_code: str
    closed_at: datetime | None
    report_id: UUID | None
    report_status_code: str | None


@dataclass(frozen=True, slots=True)
class WeeklySessionEvidence:
    local_date: date
    stored_status_code: str
    block_status_codes: tuple[str, ...]
    safety_stopped: bool
    not_completed_reason_code: str | None
    selected_action_code: str
    feedback_difficulty_code: str | None = None
    pain_occurred: bool | None = None


@dataclass(frozen=True, slots=True)
class StoredReport:
    input_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReportValues:
    report_id: UUID
    input_schema_version: str
    input_snapshot: dict[str, Any]
    input_hash: str
    completed_count: int
    partial_count: int
    not_completed_count: int
    stopped_for_safety: int
    primary_miss_reason_code: str | None
    completion_rate: float
    persistence_rate: float
    negotiation_success_rate: float | None
    weekday_failure_summary: dict[str, Any]
    high_completion_windows: list[Any]
    pattern_summary: dict[str, Any]
    decision_summary: str
    adjustment_direction_code: str
    next_action: str
    agent_summaries: dict[str, Any] | None
    summary: str
    report_policy_version: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class WeeklyReportNarrationInput:
    """Identifier-free, deterministic data that a narration Agent may interpret."""

    input_snapshot: dict[str, Any]
    objective_metrics: dict[str, Any]
    template_summary: str
    template_decision_summary: str
    template_next_action: str


@dataclass(frozen=True, slots=True)
class WeeklyReportNarration:
    """Validated user-facing wording; it has no authority over report metrics."""

    summary: str
    decision_summary: str
    next_action: str
    source_code: str
    model_code: str | None = None
    prompt_version: str | None = None
    fallback_reason_code: str | None = None


class WeeklyReportNarrationAgentPort(Protocol):
    def interpret(self, report: WeeklyReportNarrationInput) -> WeeklyReportNarration: ...


class WeeklyReportRepositoryPort(Protocol):
    def acquire_week_lock(self, session: Session, user_id: UUID, week_start: date) -> None: ...

    def acquire_idempotency_lock(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> None: ...

    def get_idempotency_record(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> IdempotencyRecord | None: ...

    def save_idempotency_record(
        self,
        session: Session,
        *,
        user_id: UUID,
        endpoint_code: str,
        key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None: ...

    def get_week_profile(
        self, session: Session, user_id: UUID, week_start: date
    ) -> WeekProfile | None: ...

    def get_week(self, session: Session, user_id: UUID, week_start: date) -> WeekRecord | None: ...

    def create_week(
        self,
        session: Session,
        *,
        week_id: UUID,
        user_id: UUID,
        week_start: date,
        week_end: date,
        timezone: str,
        target_workout_count: int,
        plan_origin_code: str,
        cold_start_applied: bool,
        status_code: str,
        closed_at: datetime | None,
        now: datetime,
    ) -> WeekRecord: ...

    def close_week(self, session: Session, week_id: UUID, closed_at: datetime) -> WeekRecord: ...

    def get_week_evidence(
        self, session: Session, user_id: UUID, week_start: date, week_end: date
    ) -> tuple[WeeklySessionEvidence, ...]: ...

    def get_report_for_week(self, session: Session, week_id: UUID) -> StoredReport | None: ...

    def get_report_by_id(
        self, session: Session, user_id: UUID, report_id: UUID
    ) -> StoredReport | None: ...

    def create_report(
        self, session: Session, *, week: WeekRecord, values: ReportValues
    ) -> StoredReport: ...

    def acknowledge_report(
        self,
        session: Session,
        *,
        user_id: UUID,
        report_id: UUID,
        acknowledged_at: datetime,
    ) -> StoredReport | None: ...


__all__ = [
    "IdempotencyRecord",
    "ReportValues",
    "StoredReport",
    "WeekProfile",
    "WeekRecord",
    "WeeklyReportNarration",
    "WeeklyReportNarrationAgentPort",
    "WeeklyReportNarrationInput",
    "WeeklyReportRepositoryPort",
    "WeeklySessionEvidence",
]
