from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.modules.notifications.ports import (
    NotificationRecord,
    WeeklyNotificationProgress,
)
from backend.app.modules.notifications.service import NotificationNotFoundError, NotificationService


class FakeSession:
    def begin(self):
        return nullcontext()


class FakeNotificationRepository:
    def __init__(self) -> None:
        self.timezone = "Asia/Seoul"
        self.progress: WeeklyNotificationProgress | None = WeeklyNotificationProgress(
            timezone=self.timezone,
            target_workout_count=3,
            completed_workout_count=2,
        )
        self.records: list[NotificationRecord] = []
        self.locked_user_ids: list[UUID] = []
        self.daily_reward_claimed = False

    def acquire_user_lock(self, session: FakeSession, user_id: UUID) -> None:
        del session
        self.locked_user_ids.append(user_id)

    def get_user_timezone(self, session: FakeSession, user_id: UUID) -> str | None:
        del session, user_id
        return self.timezone

    def is_daily_reward_claimed(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> bool:
        del session, user_id, local_date
        return self.daily_reward_claimed

    def get_weekly_progress(
        self, session: FakeSession, user_id: UUID, week_start: date
    ) -> WeeklyNotificationProgress | None:
        del session, user_id, week_start
        return self.progress

    def create_if_absent(
        self, session: FakeSession, record: NotificationRecord
    ) -> NotificationRecord:
        del session
        existing = next(
            (
                item
                for item in self.records
                if item.user_id == record.user_id and item.event_key == record.event_key
            ),
            None,
        )
        if existing is None:
            self.records.append(record)
            return record
        return existing

    def delete_by_event_key(self, session: FakeSession, user_id: UUID, event_key: str) -> None:
        del session
        self.records = [
            item
            for item in self.records
            if not (item.user_id == user_id and item.event_key == event_key)
        ]

    def purge_expired_and_trim(
        self, session: FakeSession, user_id: UUID, cutoff: datetime, max_count: int
    ) -> None:
        del session
        self.records = [
            item for item in self.records if item.user_id != user_id or item.created_at >= cutoff
        ]
        user_records = sorted(
            (item for item in self.records if item.user_id == user_id),
            key=lambda item: (item.created_at, item.notification_id),
            reverse=True,
        )[:max_count]
        self.records = [item for item in self.records if item.user_id != user_id] + user_records

    def list_recent(
        self, session: FakeSession, user_id: UUID, cutoff: datetime, limit: int
    ) -> tuple[NotificationRecord, ...]:
        del session
        return tuple(
            sorted(
                (
                    item
                    for item in self.records
                    if item.user_id == user_id and item.created_at >= cutoff
                ),
                key=lambda item: (item.created_at, item.notification_id),
                reverse=True,
            )[:limit]
        )

    def mark_read(
        self, session: FakeSession, user_id: UUID, notification_id: UUID, now: datetime
    ) -> NotificationRecord | None:
        del session
        for index, item in enumerate(self.records):
            if item.user_id == user_id and item.notification_id == notification_id:
                updated = replace(item, read_at=item.read_at or now)
                self.records[index] = updated
                return updated
        return None


class FakeWorkoutRepository:
    def __init__(self, *, suppressed: bool = False) -> None:
        self.suppressed = suppressed

    def is_pressure_notification_suppressed(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> bool:
        del session, user_id, local_date
        return self.suppressed


def _service(
    repository: FakeNotificationRepository,
    workout_repository: FakeWorkoutRepository,
    now: datetime,
) -> NotificationService:
    return NotificationService(repository, workout_repository, clock=lambda: now)


def test_weekly_goal_notification_uses_canonical_remaining_count_on_thursday() -> None:
    now = datetime(2026, 9, 3, 1, tzinfo=UTC)  # Thursday morning in Asia/Seoul.
    repository = FakeNotificationRepository()
    response = _service(repository, FakeWorkoutRepository(), now).list_notifications(
        FakeSession(), uuid4(), previous_last_active_at=None
    )

    assert response.unread_count == 2
    weekly = next(item for item in response.items if item.type == "WEEKLY_GOAL_REMINDER")
    daily = next(item for item in response.items if item.type == "DAILY_REWARD")
    assert weekly.payload == {"remaining_workout_count": 1}
    assert weekly.message == "이번 주 운동 목표를 확인해 보세요."
    assert daily.action_type == "CLAIM_DAILY_REWARD"
    assert daily.payload["reward_amount"] == 15


def test_weekly_goal_notification_is_not_created_before_thursday_or_after_goal() -> None:
    repository = FakeNotificationRepository()
    monday = datetime(2026, 8, 31, 1, tzinfo=UTC)
    response = _service(repository, FakeWorkoutRepository(), monday).list_notifications(
        FakeSession(), uuid4(), previous_last_active_at=None
    )
    assert [item.type for item in response.items] == ["DAILY_REWARD"]

    repository.progress = WeeklyNotificationProgress("Asia/Seoul", 3, 3)
    thursday = datetime(2026, 9, 3, 1, tzinfo=UTC)
    response = _service(repository, FakeWorkoutRepository(), thursday).list_notifications(
        FakeSession(), uuid4(), previous_last_active_at=None
    )
    assert [item.type for item in response.items] == ["DAILY_REWARD"]


def test_weekly_goal_notification_respects_existing_rest_pressure_suppression() -> None:
    now = datetime(2026, 9, 3, 1, tzinfo=UTC)
    response = _service(
        FakeNotificationRepository(), FakeWorkoutRepository(suppressed=True), now
    ).list_notifications(FakeSession(), uuid4(), previous_last_active_at=None)
    assert [item.type for item in response.items] == ["DAILY_REWARD"]


def test_return_notification_requires_three_days_and_is_deduplicated_per_return_event() -> None:
    now = datetime(2026, 9, 4, 0, tzinfo=UTC)
    repository = FakeNotificationRepository()
    repository.progress = None
    user_id = uuid4()
    service = _service(repository, FakeWorkoutRepository(), now)

    under_three_days = service.list_notifications(
        FakeSession(),
        user_id,
        previous_last_active_at=now - timedelta(days=3) + timedelta(seconds=1),
    )
    assert [item.type for item in under_three_days.items] == ["DAILY_REWARD"]

    first = service.list_notifications(
        FakeSession(), user_id, previous_last_active_at=now - timedelta(days=3)
    )
    repeated = service.list_notifications(
        FakeSession(), user_id, previous_last_active_at=now - timedelta(days=3)
    )
    assert {item.type for item in first.items} == {"DAILY_REWARD", "KIKKI_RETURN"}
    assert len(repeated.items) == 2
    returned = next(item for item in repeated.items if item.type == "KIKKI_RETURN")
    assert returned.action_type == "OPEN_KIKKI_HOME"


def test_daily_reward_notification_is_not_created_after_the_canonical_claim() -> None:
    repository = FakeNotificationRepository()
    repository.progress = None
    repository.daily_reward_claimed = True

    user_id = uuid4()
    repository.records.append(
        NotificationRecord(
            notification_id=uuid4(),
            user_id=user_id,
            type_code="DAILY_REWARD",
            title="old",
            message="old",
            action_type="CLAIM_DAILY_REWARD",
            payload={},
            event_key="daily-reward:2026-09-04",
            created_at=datetime(2026, 9, 4, tzinfo=UTC),
            read_at=None,
        )
    )
    response = _service(
        repository, FakeWorkoutRepository(), datetime(2026, 9, 4, tzinfo=UTC)
    ).list_notifications(FakeSession(), user_id, previous_last_active_at=None)

    assert response.items == []


def test_read_is_idempotent_and_isolated_by_user() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    repository = FakeNotificationRepository()
    repository.progress = None
    owner_id, other_user_id = uuid4(), uuid4()
    service = _service(repository, FakeWorkoutRepository(), now)
    created = service.list_notifications(
        FakeSession(), owner_id, previous_last_active_at=now - timedelta(days=3)
    ).items[0]

    read_once = service.mark_read(FakeSession(), owner_id, created.notification_id)
    read_twice = service.mark_read(FakeSession(), owner_id, created.notification_id)
    assert read_once.read_at == read_twice.read_at
    with pytest.raises(NotificationNotFoundError):
        service.mark_read(FakeSession(), other_user_id, created.notification_id)


def test_list_keeps_only_14_days_and_20_recent_notifications() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    repository = FakeNotificationRepository()
    user_id = uuid4()
    for offset in range(22):
        repository.records.append(
            NotificationRecord(
                notification_id=uuid4(),
                user_id=user_id,
                type_code="DAILY_REWARD",
                title="t",
                message="m",
                action_type=None,
                payload={},
                event_key=f"reward:{offset}",
                created_at=now - timedelta(minutes=offset),
                read_at=None,
            )
        )
    repository.records.append(
        NotificationRecord(
            notification_id=uuid4(),
            user_id=user_id,
            type_code="DAILY_REWARD",
            title="old",
            message="old",
            action_type=None,
            payload={},
            event_key="reward:old",
            created_at=now - timedelta(days=15),
            read_at=None,
        )
    )
    response = _service(repository, FakeWorkoutRepository(), now).list_notifications(
        FakeSession(), user_id, previous_last_active_at=None
    )
    assert len(response.items) == 20
    assert all(item.created_at >= now - timedelta(days=14) for item in response.items)
