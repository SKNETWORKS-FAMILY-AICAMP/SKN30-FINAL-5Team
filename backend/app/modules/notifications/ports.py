from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class NotificationRecord:
    notification_id: UUID
    user_id: UUID
    type_code: str
    title: str
    message: str
    action_type: str | None
    payload: dict[str, Any]
    event_key: str
    created_at: datetime
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class WeeklyNotificationProgress:
    timezone: str
    target_workout_count: int
    completed_workout_count: int


class NotificationRepositoryPort(Protocol):
    def acquire_user_lock(self, session: Session, user_id: UUID) -> None: ...

    def get_user_timezone(self, session: Session, user_id: UUID) -> str | None: ...

    def get_weekly_progress(
        self, session: Session, user_id: UUID, week_start: date
    ) -> WeeklyNotificationProgress | None: ...

    def create_if_absent(
        self, session: Session, record: NotificationRecord
    ) -> NotificationRecord: ...

    def purge_expired_and_trim(
        self, session: Session, user_id: UUID, cutoff: datetime, max_count: int
    ) -> None: ...

    def list_recent(
        self, session: Session, user_id: UUID, cutoff: datetime, limit: int
    ) -> tuple[NotificationRecord, ...]: ...

    def mark_read(
        self, session: Session, user_id: UUID, notification_id: UUID, now: datetime
    ) -> NotificationRecord | None: ...


__all__ = ["NotificationRecord", "NotificationRepositoryPort", "WeeklyNotificationProgress"]
