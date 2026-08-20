from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class DailyContextValues:
    fatigue_level_code: str
    requested_duration_minutes: int
    duration_adjustment_source_code: str
    location_code: str
    sleep_minutes: int | None
    fasting_state_code: str | None
    hydration_state_code: str | None
    discomforts: tuple[tuple[str, str], ...]
    adverse_reaction_codes: tuple[str, ...]
    # ROUTINE_DEFAULT pairs with an empty tuple and means the user did not answer.
    # MANUAL with an empty tuple is an explicit "no time today" choice.
    availability_source_code: str
    available_slots: tuple[tuple[datetime, datetime], ...]


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


class DailyContextRepositoryPort(Protocol):
    def acquire_mutation_lock(self, session: Session, user_id: UUID, local_date: date) -> None: ...

    def get_user_timezone(self, session: Session, user_id: UUID) -> str | None:
        """Return the verified profile IANA timezone used to bound availability slots."""
        ...

    def get_idempotency_record(
        self, session: Session, user_id: UUID, idempotency_key: UUID
    ) -> IdempotencyRecord | None: ...

    def save_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None: ...

    def get_payload(
        self, session: Session, user_id: UUID, local_date: date
    ) -> dict[str, Any] | None: ...

    def replace(
        self,
        session: Session,
        user_id: UUID,
        local_date: date,
        expected_version: int | None,
        values: DailyContextValues,
        now: datetime,
    ) -> dict[str, Any] | None: ...


__all__ = ["DailyContextRepositoryPort", "DailyContextValues", "IdempotencyRecord"]
