from datetime import date, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.notification import InAppNotification
from backend.app.db.models.profile import UserProfile
from backend.app.db.models.reward import BananaTransaction
from backend.app.db.models.weekly_report import UserWeek
from backend.app.db.models.workout import DecisionSelection, WorkoutSession
from backend.app.modules.notifications.ports import (
    NotificationRecord,
    WeeklyNotificationProgress,
)
from backend.app.modules.rewards.codes import BananaTransactionType


class NotificationRepository:
    def acquire_user_lock(self, session: Session, user_id: UUID) -> None:
        lock_key = int.from_bytes(
            sha256(f"in-app-notifications:{user_id}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_user_timezone(self, session: Session, user_id: UUID) -> str | None:
        return session.scalar(select(UserProfile.timezone).where(UserProfile.user_id == user_id))

    def is_daily_reward_claimed(self, session: Session, user_id: UUID, local_date: date) -> bool:
        return (
            session.scalar(
                select(BananaTransaction.id).where(
                    BananaTransaction.user_id == user_id,
                    BananaTransaction.transaction_type == BananaTransactionType.DAILY_REWARD,
                    BananaTransaction.source_local_date == local_date,
                )
            )
            is not None
        )

    def get_weekly_progress(
        self, session: Session, user_id: UUID, week_start: date
    ) -> WeeklyNotificationProgress | None:
        week = session.scalar(
            select(UserWeek).where(
                UserWeek.user_id == user_id,
                UserWeek.week_start_local_date == week_start,
            )
        )
        if week is None:
            return None
        completed_count = session.scalar(
            select(func.count())
            .select_from(WorkoutSession)
            .join(DecisionSelection, DecisionSelection.id == WorkoutSession.decision_selection_id)
            .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status_code == "COMPLETED",
                DecisionRun.local_date >= week.week_start_local_date,
                DecisionRun.local_date <= week.week_end_local_date,
            )
        )
        return WeeklyNotificationProgress(
            timezone=week.timezone,
            target_workout_count=week.target_workout_count,
            completed_workout_count=int(completed_count or 0),
        )

    def create_if_absent(self, session: Session, record: NotificationRecord) -> NotificationRecord:
        existing = session.scalar(
            select(InAppNotification).where(
                InAppNotification.user_id == record.user_id,
                InAppNotification.event_key == record.event_key,
            )
        )
        if existing is not None:
            return self._record(existing)
        session.add(
            InAppNotification(
                id=record.notification_id,
                user_id=record.user_id,
                type_code=record.type_code,
                title=record.title,
                message=record.message,
                action_type=record.action_type,
                payload=record.payload,
                event_key=record.event_key,
                created_at=record.created_at,
                read_at=record.read_at,
            )
        )
        session.flush()
        return record

    def delete_by_event_key(self, session: Session, user_id: UUID, event_key: str) -> None:
        session.execute(
            delete(InAppNotification).where(
                InAppNotification.user_id == user_id,
                InAppNotification.event_key == event_key,
                InAppNotification.type_code == "DAILY_REWARD",
            )
        )

    def purge_expired_and_trim(
        self, session: Session, user_id: UUID, cutoff: datetime, max_count: int
    ) -> None:
        session.execute(
            delete(InAppNotification).where(
                InAppNotification.user_id == user_id,
                InAppNotification.created_at < cutoff,
            )
        )
        retained_ids = (
            select(InAppNotification.id)
            .where(InAppNotification.user_id == user_id)
            .order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc())
            .limit(max_count)
        )
        session.execute(
            delete(InAppNotification).where(
                InAppNotification.user_id == user_id,
                InAppNotification.id.not_in(retained_ids),
            )
        )

    def list_recent(
        self, session: Session, user_id: UUID, cutoff: datetime, limit: int
    ) -> tuple[NotificationRecord, ...]:
        rows = session.scalars(
            select(InAppNotification)
            .where(
                InAppNotification.user_id == user_id,
                InAppNotification.created_at >= cutoff,
            )
            .order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc())
            .limit(limit)
        ).all()
        return tuple(self._record(row) for row in rows)

    def mark_read(
        self, session: Session, user_id: UUID, notification_id: UUID, now: datetime
    ) -> NotificationRecord | None:
        row = session.scalar(
            select(InAppNotification)
            .where(
                InAppNotification.id == notification_id,
                InAppNotification.user_id == user_id,
            )
            .with_for_update()
        )
        if row is None:
            return None
        if row.read_at is None:
            row.read_at = now
            session.flush()
        return self._record(row)

    @staticmethod
    def _record(row: InAppNotification) -> NotificationRecord:
        return NotificationRecord(
            notification_id=row.id,
            user_id=row.user_id,
            type_code=row.type_code,
            title=row.title,
            message=row.message,
            action_type=row.action_type,
            payload=row.payload,
            event_key=row.event_key,
            created_at=row.created_at,
            read_at=row.read_at,
        )


__all__ = ["NotificationRepository"]
