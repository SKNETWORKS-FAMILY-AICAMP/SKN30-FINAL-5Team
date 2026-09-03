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
    target_duration_seconds: int = 0


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: UUID
    status_code: str
    started_at: datetime | None
    ended_at: datetime | None
    items: tuple[tuple[UUID, str, datetime | None], ...]
    estimated_calories_burned: float | None = None
    completion_code: str | None = None
    execution_state_code: str | None = None
    target_duration_seconds: int | None = None
    accumulated_progress_seconds: int = 0
    accumulated_rest_seconds: int = 0
    accumulated_paused_seconds: int = 0
    last_state_changed_at: datetime | None = None
    is_resumable: bool = False
    stop_reason_code: str | None = None
    local_date: date | None = None


@dataclass(frozen=True, slots=True)
class ReturnHistory:
    last_completed_local_date: date | None
    not_completed_history_count: int


@dataclass(frozen=True, slots=True)
class WorkoutLogCursor:
    local_date: date
    session_id: UUID


@dataclass(frozen=True, slots=True)
class WorkoutLogSummary:
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


@dataclass(frozen=True, slots=True)
class WorkoutLogItem:
    plan_item_id: UUID
    exercise_id: UUID
    exercise_name: str
    status_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkoutLogFeedback:
    perceived_difficulty_code: str | None
    post_workout_discomfort_reported: bool


@dataclass(frozen=True, slots=True)
class WorkoutLogDetail:
    session_id: UUID
    local_date: date
    status_code: str
    requested_duration_minutes: int
    items: tuple[WorkoutLogItem, ...]
    feedback: WorkoutLogFeedback | None
    not_completed_reason_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


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

    def transition_execution_state(
        self,
        session: Session,
        *,
        session_id: UUID,
        execution_state_code: str,
        occurred_at: datetime,
        is_resumable: bool,
        stop_reason_code: str | None,
        completion_code: str | None = None,
        ended_at: datetime | None = None,
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

    def create_safety_event(
        self,
        session: Session,
        *,
        event_id: UUID,
        session_id: UUID,
        occurred_at: datetime,
        result_code: str,
        completion_code: str,
        rule_version: str,
        now: datetime,
    ) -> None: ...

    def finish_session(
        self,
        session: Session,
        *,
        session_id: UUID,
        status_code: str,
        ended_at: datetime,
        actual_elapsed_seconds: int | None,
        completion_code: str | None = None,
        execution_state_code: str | None = None,
    ) -> None: ...

    def create_skip_feedback(
        self,
        session: Session,
        *,
        session_id: UUID,
        reason_code: str,
        now: datetime,
    ) -> None: ...

    def feedback_exists(self, session: Session, session_id: UUID) -> bool: ...

    def create_feedback(
        self,
        session: Session,
        *,
        session_id: UUID,
        difficulty_code: str,
        fatigue_code: str | None,
        satisfaction_code: str | None,
        pain_occurred: bool,
        discomforts: tuple[tuple[str, str], ...],
        adverse_reaction_codes: tuple[str, ...],
        difficulty_reason_codes: tuple[str, ...],
        now: datetime,
    ) -> None: ...

    def get_return_history(
        self, session: Session, user_id: UUID, before_local_date: date
    ) -> ReturnHistory: ...

    def is_pressure_notification_suppressed(
        self, session: Session, user_id: UUID, local_date: date
    ) -> bool: ...

    def list_workout_logs(
        self,
        session: Session,
        user_id: UUID,
        *,
        from_local_date: date | None,
        to_local_date: date | None,
        status_code: str | None,
        cursor: WorkoutLogCursor | None,
        limit: int,
    ) -> tuple[WorkoutLogSummary, ...]: ...

    def get_workout_log_detail(
        self, session: Session, user_id: UUID, session_id: UUID
    ) -> WorkoutLogDetail | None: ...


__all__ = [
    "IdempotencyRecord",
    "ReturnHistory",
    "SelectionSource",
    "SessionState",
    "WorkoutLogCursor",
    "WorkoutLogDetail",
    "WorkoutLogFeedback",
    "WorkoutLogItem",
    "WorkoutLogSummary",
    "WorkoutRepositoryPort",
]
