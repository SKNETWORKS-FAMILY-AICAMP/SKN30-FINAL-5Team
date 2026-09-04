from contextlib import nullcontext
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from backend.app.modules.rewards.ports import (
    BananaTransactionRecord,
    BananaWalletRecord,
    RewardEligibleWorkout,
)
from backend.app.modules.rewards.schemas import BananaSpendRequest
from backend.app.modules.rewards.service import (
    InsufficientBananaBalanceError,
    InvalidBananaSpendError,
    RewardService,
)


class FakeSession:
    def begin(self):
        return nullcontext()


class FakeRewardRepository:
    def __init__(self) -> None:
        self.wallets: dict[UUID, int] = {}
        self.transactions: list[BananaTransactionRecord] = []
        self.workouts: tuple[RewardEligibleWorkout, ...] = ()
        self.lock_count = 0

    def acquire_user_lock(self, session: FakeSession, user_id: UUID) -> None:
        del session, user_id
        self.lock_count += 1

    def get_user_timezone(self, session: FakeSession, user_id: UUID) -> str | None:
        del session, user_id
        return "Asia/Seoul"

    def get_wallet_for_update(
        self, session: FakeSession, user_id: UUID, now: datetime
    ) -> BananaWalletRecord:
        del session, now
        return BananaWalletRecord(user_id, self.wallets.setdefault(user_id, 0))

    def get_transaction_by_event(
        self, session: FakeSession, user_id: UUID, event_key: str
    ) -> BananaTransactionRecord | None:
        del session
        return next(
            (
                item
                for item in self.transactions
                if item.user_id == user_id and item.event_key == event_key
            ),
            None,
        )

    def get_transaction_by_type_reference(
        self, session: FakeSession, user_id: UUID, transaction_type: str, reference_code: str
    ) -> BananaTransactionRecord | None:
        del session
        return next(
            (
                item
                for item in self.transactions
                if item.user_id == user_id
                and item.transaction_type == transaction_type
                and item.reference_code == reference_code
            ),
            None,
        )

    def create_transaction(
        self, session: FakeSession, record: BananaTransactionRecord
    ) -> BananaTransactionRecord:
        del session
        self.transactions.append(record)
        return record

    def update_wallet_balance(
        self, session: FakeSession, user_id: UUID, balance: int, now: datetime
    ) -> None:
        del session, now
        self.wallets[user_id] = balance

    def list_reward_eligible_workouts(
        self, session: FakeSession, user_id: UUID
    ) -> tuple[RewardEligibleWorkout, ...]:
        del session, user_id
        return self.workouts

    def get_daily_claim(
        self, session: FakeSession, user_id: UUID, local_date: date
    ) -> BananaTransactionRecord | None:
        del session
        return next(
            (
                item
                for item in self.transactions
                if item.user_id == user_id
                and item.transaction_type == "DAILY_REWARD"
                and item.source_local_date == local_date
            ),
            None,
        )


NOW = datetime(2026, 9, 4, 15, 30, tzinfo=UTC)  # 2026-09-05 00:30 Asia/Seoul


def _service(repository: FakeRewardRepository) -> RewardService:
    return RewardService(repository, clock=lambda: NOW)


def test_daily_claim_is_timezone_scoped_and_idempotent() -> None:
    repository = FakeRewardRepository()
    user_id = uuid4()

    first = _service(repository).claim_daily_reward(FakeSession(), user_id)
    repeated = _service(repository).claim_daily_reward(FakeSession(), user_id)

    assert first.daily_reward.local_date == date(2026, 9, 5)
    assert first.balance == 15
    assert repeated.balance == 15
    assert repeated.transaction.transaction_id == first.transaction.transaction_id
    assert len(repository.transactions) == 1
    assert repository.lock_count == 2


def test_canonical_workout_rewards_and_daily_quest_are_server_deduplicated() -> None:
    repository = FakeRewardRepository()
    repository.workouts = (
        RewardEligibleWorkout(uuid4(), "COMPLETED", date(2026, 9, 4)),
        RewardEligibleWorkout(uuid4(), "PARTIAL", date(2026, 9, 4)),
        RewardEligibleWorkout(uuid4(), "STOPPED_FOR_SAFETY", date(2026, 9, 3)),
    )
    user_id = uuid4()

    first = _service(repository).get_wallet(FakeSession(), user_id)
    repeated = _service(repository).get_wallet(FakeSession(), user_id)

    assert first.balance == 70  # 30 completed + 10 daily quest + 15 + 15
    assert repeated.balance == 70
    assert len(repository.transactions) == 4


def test_server_enforces_existing_feed_and_item_costs() -> None:
    repository = FakeRewardRepository()
    user_id = uuid4()
    repository.wallets[user_id] = 30

    fed = _service(repository).spend(
        FakeSession(), user_id, BananaSpendRequest(action_code="FEED_MASCOT"), uuid4()
    )
    purchased = _service(repository).spend(
        FakeSession(),
        user_id,
        BananaSpendRequest(action_code="PURCHASE_HOUSE_ITEM", house_item_code="yoga_mat"),
        uuid4(),
    )

    assert fed.transaction.amount == -10
    assert purchased.transaction.amount == -20
    assert purchased.balance == 0
    with pytest.raises(InsufficientBananaBalanceError):
        _service(repository).spend(
            FakeSession(), user_id, BananaSpendRequest(action_code="FEED_MASCOT"), uuid4()
        )
    with pytest.raises(InvalidBananaSpendError):
        _service(repository).spend(
            FakeSession(),
            user_id,
            BananaSpendRequest(action_code="PURCHASE_HOUSE_ITEM", house_item_code="yoga_mat"),
            uuid4(),
        )
