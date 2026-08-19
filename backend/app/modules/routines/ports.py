from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class RoutineIdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RoutineCandidate:
    exercise_id: UUID
    exercise_name: str
    training_type_code: str
    body_focus_code: str
    timing_mode_code: str
    seconds_per_rep: int | None
    transition_seconds: int
    phase_code: str
    tier_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    rest_seconds_per_set: int
    intensity_code: str


@dataclass(frozen=True, slots=True)
class RoutineCreationContext:
    profile_duration_minutes: int
    desired_weekly_workout_count: int
    experience_level_code: str
    available_location_codes: tuple[str, ...]
    equipment_codes: tuple[str, ...]
    catalog_version_id: UUID
    catalog_version_code: str
    candidates: tuple[RoutineCandidate, ...]


@dataclass(frozen=True, slots=True)
class RoutineItemValues:
    exercise_id: UUID
    sequence: int
    phase_code: str
    tier_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    rest_seconds_per_set: int
    intensity_code: str


@dataclass(frozen=True, slots=True)
class RoutineDayValues:
    sequence: int
    title: str
    training_type_code: str
    body_focus_code: str | None
    requested_duration_minutes: int
    estimated_duration_seconds: int
    setup_seconds: int
    items: tuple[RoutineItemValues, ...]


class RoutineRepositoryPort(Protocol):
    def acquire_creation_lock(self, session: Session, user_id: UUID) -> None: ...

    def get_idempotency_record(
        self, session: Session, user_id: UUID, idempotency_key: UUID
    ) -> RoutineIdempotencyRecord | None: ...

    def save_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None: ...

    def get_creation_context(
        self, session: Session, user_id: UUID, goal_code: str
    ) -> RoutineCreationContext | None: ...

    def create_routine(
        self,
        session: Session,
        user_id: UUID,
        goal_code: str,
        effective_from: date,
        catalog_version_id: UUID,
        days: tuple[RoutineDayValues, ...],
        now: datetime,
    ) -> UUID: ...

    def get_routine_response_payload(
        self, session: Session, user_id: UUID, routine_id: UUID
    ) -> dict[str, Any] | None: ...

    def get_current_routine_payload(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None: ...


__all__ = [
    "RoutineCandidate",
    "RoutineCreationContext",
    "RoutineDayValues",
    "RoutineIdempotencyRecord",
    "RoutineItemValues",
    "RoutineRepositoryPort",
]
