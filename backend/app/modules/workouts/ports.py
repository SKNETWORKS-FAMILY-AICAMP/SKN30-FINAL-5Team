from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SelectionSource:
    decision_id: UUID
    option_id: UUID
    option_code: str
    option_action_code: str
    option_selectable: bool
    option_plan_candidate_id: UUID | None
    decision_status_code: str
    decision_safety_status_code: str
    recommended_action_code: str | None
    selected_candidate_id: UUID | None
    selected_candidate_action_code: str | None
    safety_candidate_id: UUID | None
    safety_status_code: str | None
    safety_vetoed: bool | None
    plan_item_ids: tuple[UUID, ...]
    estimated_calories_burned: float | None
    already_selected: bool


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: UUID
    status_code: str
    started_at: datetime | None
    ended_at: datetime | None
    items: tuple[tuple[UUID, str, datetime | None], ...]


class WorkoutRepositoryPort(Protocol):
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

    def get_selection_source(
        self, session: Session, user_id: UUID, decision_id: UUID, option_id: UUID
    ) -> SelectionSource | None: ...

    def create_selection(
        self,
        session: Session,
        *,
        source: SelectionSource,
        user_id: UUID,
        selection_id: UUID,
        workout_session_id: UUID | None,
        idempotency_key: UUID,
        now: datetime,
    ) -> None: ...

    def get_session_state(
        self, session: Session, user_id: UUID, session_id: UUID
    ) -> SessionState | None: ...

    def start_session(
        self, session: Session, session_id: UUID, started_at: datetime
    ) -> SessionState: ...

    def update_session_item(
        self,
        session: Session,
        session_id: UUID,
        plan_item_id: UUID,
        status_code: str,
        now: datetime,
    ) -> SessionState | None: ...

    def create_timer_event(
        self,
        session: Session,
        *,
        event_id: UUID,
        session_id: UUID,
        event_code: str,
        occurred_at: datetime,
        client_recorded_at: datetime,
        now: datetime,
    ) -> None: ...

    def create_additional_activity(
        self,
        session: Session,
        *,
        activity_id: UUID,
        session_id: UUID,
        activity_type_code: str,
        duration_seconds: int,
        intensity_code: str | None,
        note: str | None,
        now: datetime,
    ) -> None: ...


__all__ = ["IdempotencyRecord", "SelectionSource", "SessionState", "WorkoutRepositoryPort"]
