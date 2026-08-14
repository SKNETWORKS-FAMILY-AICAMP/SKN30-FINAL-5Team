from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class PlanIdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PlanContext:
    week_id: UUID
    week_start: date
    week_end: date
    is_first_user_week: bool
    cold_start_applied: bool
    source_weekly_report_id: UUID | None
    previous_report_status_code: str | None
    requested_duration_minutes: int
    preferred_location_code: str
    allowed_location_codes: tuple[str, ...]
    available_equipment_codes: tuple[str, ...]
    safety_status_code: str
    safety_opinion_codes: tuple[str, ...]
    excluded_exercise_ids: tuple[UUID, ...]
    current_routine_id: UUID | None


@dataclass(frozen=True, slots=True)
class RoutinePlanEvidence:
    routine_id: UUID
    routine_version: int
    requested_duration_minutes: int
    supported_location_codes: tuple[str, ...]
    required_equipment_codes: tuple[str, ...]
    exercise_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class LatestPlanRevision:
    revision_id: UUID
    revision_sequence: int
    successful_ai_revision_count: int
    routine_id: UUID | None


@dataclass(frozen=True, slots=True)
class PlanRevisionValues:
    revision_id: UUID
    target_user_week_id: UUID
    source_weekly_report_id: UUID | None
    revision_sequence: int
    ai_revision_number: int | None
    revision_source_code: str
    routine_id: UUID | None
    selected_location_code: str | None
    safety_status_code: str
    input_schema_version: str
    input_snapshot: dict[str, Any]
    input_hash: str
    weekly_plan_policy_version: str
    revision_reason_codes: list[str]
    finalization_reason_codes: list[str]
    finalized_at: datetime | None
    created_at: datetime


class WeeklyPlanRepositoryPort(Protocol):
    def acquire_week_lock(self, session: Session, user_id: UUID, week_start: date) -> None: ...

    def acquire_idempotency_lock(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> None: ...

    def get_idempotency_record(
        self, session: Session, user_id: UUID, endpoint_code: str, key: UUID
    ) -> PlanIdempotencyRecord | None: ...

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

    def get_plan_context(
        self, session: Session, user_id: UUID, week_id: UUID, week_start: date
    ) -> PlanContext | None: ...

    def get_routine_evidence(
        self, session: Session, user_id: UUID, routine_id: UUID
    ) -> RoutinePlanEvidence | None: ...

    def get_latest_revision(self, session: Session, week_id: UUID) -> LatestPlanRevision | None: ...

    def create_revision(
        self, session: Session, values: PlanRevisionValues
    ) -> PlanRevisionValues: ...


__all__ = [
    "LatestPlanRevision",
    "PlanContext",
    "PlanIdempotencyRecord",
    "PlanRevisionValues",
    "RoutinePlanEvidence",
    "WeeklyPlanRepositoryPort",
]
