from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.app.modules.notifications.codes import (
    MAX_RECENT_NOTIFICATIONS,
    NOTIFICATION_RETENTION_DAYS,
    WEEKLY_REMINDER_FIRST_WEEKDAY,
    NotificationActionType,
    NotificationTypeCode,
)
from backend.app.modules.notifications.ports import NotificationRecord, NotificationRepositoryPort
from backend.app.modules.notifications.schemas import NotificationListResponse, NotificationResponse
from backend.app.modules.workouts.ports import WorkoutRepositoryPort


class NotificationNotFoundError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepositoryPort,
        workout_repository: WorkoutRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._workout_repository = workout_repository
        self._clock = clock
        self._uuid_factory = uuid_factory

    def list_notifications(
        self,
        session: Session,
        user_id: UUID,
        *,
        previous_last_active_at: datetime | None,
    ) -> NotificationListResponse:
        now = self._clock()
        with session.begin():
            self._repository.acquire_user_lock(session, user_id)
            self._repository.purge_expired_and_trim(
                session,
                user_id,
                now - timedelta(days=NOTIFICATION_RETENTION_DAYS),
                MAX_RECENT_NOTIFICATIONS,
            )
            self._create_return_notification(session, user_id, now, previous_last_active_at)
            self._create_daily_reward_notification(session, user_id, now)
            self._create_weekly_goal_reminder(session, user_id, now)
            self._repository.purge_expired_and_trim(
                session,
                user_id,
                now - timedelta(days=NOTIFICATION_RETENTION_DAYS),
                MAX_RECENT_NOTIFICATIONS,
            )
            records = self._repository.list_recent(
                session,
                user_id,
                now - timedelta(days=NOTIFICATION_RETENTION_DAYS),
                MAX_RECENT_NOTIFICATIONS,
            )
        responses = [self._response(record) for record in records]
        return NotificationListResponse(
            items=responses,
            unread_count=sum(item.read_at is None for item in records),
        )

    def record_return_notification(
        self,
        session: Session,
        user_id: UUID,
        *,
        previous_last_active_at: datetime,
    ) -> None:
        """Record a long-absence return before another API call overwrites its source time."""
        now = self._clock()
        if now - previous_last_active_at < timedelta(days=3):
            return
        with session.begin():
            self._repository.acquire_user_lock(session, user_id)
            self._repository.purge_expired_and_trim(
                session,
                user_id,
                now - timedelta(days=NOTIFICATION_RETENTION_DAYS),
                MAX_RECENT_NOTIFICATIONS,
            )
            self._create_return_notification(session, user_id, now, previous_last_active_at)

    def mark_read(
        self, session: Session, user_id: UUID, notification_id: UUID
    ) -> NotificationResponse:
        now = self._clock()
        with session.begin():
            self._repository.purge_expired_and_trim(
                session,
                user_id,
                now - timedelta(days=NOTIFICATION_RETENTION_DAYS),
                MAX_RECENT_NOTIFICATIONS,
            )
            record = self._repository.mark_read(session, user_id, notification_id, now)
            if record is None:
                raise NotificationNotFoundError
        return self._response(record)

    def _create_return_notification(
        self,
        session: Session,
        user_id: UUID,
        now: datetime,
        previous_last_active_at: datetime | None,
    ) -> None:
        if previous_last_active_at is None or now - previous_last_active_at < timedelta(days=3):
            return
        event_key = f"kikki-return:{previous_last_active_at.astimezone(UTC).isoformat()}"
        self._create_if_absent(
            session,
            NotificationRecord(
                notification_id=self._uuid_factory(),
                user_id=user_id,
                type_code=NotificationTypeCode.KIKKI_RETURN,
                title="키키가 기다리고 있어요..",
                message="또 바나나 먹고 싶다... 🐵",
                action_type=NotificationActionType.OPEN_KIKKI_HOME,
                payload={},
                event_key=event_key,
                created_at=now,
                read_at=None,
            ),
        )

    def _create_daily_reward_notification(
        self, session: Session, user_id: UUID, now: datetime
    ) -> None:
        timezone_name = self._repository.get_user_timezone(session, user_id)
        if timezone_name is None:
            return
        local_date = now.astimezone(ZoneInfo(timezone_name)).date()
        event_key = f"daily-reward:{local_date.isoformat()}"
        if self._repository.is_daily_reward_claimed(session, user_id, local_date):
            self._repository.delete_by_event_key(session, user_id, event_key)
            return
        self._create_if_absent(
            session,
            NotificationRecord(
                notification_id=self._uuid_factory(),
                user_id=user_id,
                type_code=NotificationTypeCode.DAILY_REWARD,
                title="오늘의 바나나 선물이 도착했어요.",
                message="바나나 15개를 받아 보세요.",
                action_type=NotificationActionType.CLAIM_DAILY_REWARD,
                payload={"reward_amount": 15, "local_date": local_date.isoformat()},
                event_key=event_key,
                created_at=now,
                read_at=None,
            ),
        )

    def _create_weekly_goal_reminder(self, session: Session, user_id: UUID, now: datetime) -> None:
        # A profile timezone and a persisted current user_week are both required; no profile
        # target is substituted for the canonical UserWeek target.
        timezone_name = self._repository.get_user_timezone(session, user_id)
        if timezone_name is None:
            return
        try:
            local_now = now.astimezone(ZoneInfo(timezone_name))
        except (ZoneInfoNotFoundError, ValueError):
            return
        if local_now.weekday() < WEEKLY_REMINDER_FIRST_WEEKDAY:
            return
        local_date = local_now.date()
        week_start = local_date.fromordinal(local_date.toordinal() - local_date.weekday())
        progress = self._repository.get_weekly_progress(session, user_id, week_start)
        if progress is None or progress.completed_workout_count >= progress.target_workout_count:
            return
        if self._workout_repository.is_pressure_notification_suppressed(
            session, user_id, local_date
        ):
            return
        remaining = progress.target_workout_count - progress.completed_workout_count
        self._create_if_absent(
            session,
            NotificationRecord(
                notification_id=self._uuid_factory(),
                user_id=user_id,
                type_code=NotificationTypeCode.WEEKLY_GOAL_REMINDER,
                title=f"이번 주 목표까지 {remaining}회 남았어요!",
                message="이번 주 운동 목표를 확인해 보세요.",
                action_type=None,
                payload={"remaining_workout_count": remaining},
                event_key=(f"weekly-goal:{week_start.isoformat()}:remaining-{remaining}"),
                created_at=now,
                read_at=None,
            ),
        )

    def _create_if_absent(self, session: Session, record: NotificationRecord) -> None:
        self._repository.create_if_absent(session, record)

    @staticmethod
    def _response(record: NotificationRecord) -> NotificationResponse:
        return NotificationResponse(
            notification_id=record.notification_id,
            type=cast(
                Literal["DAILY_REWARD", "WEEKLY_GOAL_REMINDER", "KIKKI_RETURN"],
                record.type_code,
            ),
            title=record.title,
            message=record.message,
            created_at=record.created_at,
            read_at=record.read_at,
            is_read=record.read_at is not None,
            action_type=record.action_type,
            payload=record.payload,
        )


__all__ = ["NotificationNotFoundError", "NotificationService"]
