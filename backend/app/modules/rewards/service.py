from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.modules.rewards.codes import (
    DAILY_REWARD_BANANAS,
    HOUSE_FEED_COST,
    HOUSE_ITEM_COSTS,
    WORKOUT_COMPLETED_BANANAS,
    WORKOUT_DAILY_QUEST_BANANAS,
    WORKOUT_PARTIAL_BANANAS,
    BananaSpendActionCode,
    BananaTransactionType,
)
from backend.app.modules.rewards.ports import (
    BananaTransactionRecord,
    BananaWalletRecord,
    RewardRepositoryPort,
)
from backend.app.modules.rewards.schemas import (
    BananaSpendRequest,
    BananaSpendResponse,
    BananaTransactionResponse,
    BananaWalletResponse,
    DailyRewardClaimResponse,
    DailyRewardStatus,
)


class RewardProfileNotFoundError(Exception):
    pass


class InsufficientBananaBalanceError(Exception):
    pass


class InvalidBananaSpendError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RewardService:
    def __init__(
        self,
        repository: RewardRepositoryPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._uuid_factory = uuid_factory

    def get_wallet(self, session: Session, user_id: UUID) -> BananaWalletResponse:
        now = self._clock()
        with session.begin():
            timezone, wallet, local_now = self._prepare(session, user_id, now)
            del timezone
            self._sync_workout_rewards(session, user_id, wallet, local_now, now)
            wallet = self._repository.get_wallet_for_update(session, user_id, now)
            claim = self._repository.get_daily_claim(session, user_id, local_now.date())
        return self._wallet_response(wallet, local_now.date(), claim)

    def claim_daily_reward(self, session: Session, user_id: UUID) -> DailyRewardClaimResponse:
        now = self._clock()
        with session.begin():
            _, wallet, local_now = self._prepare(session, user_id, now)
            self._sync_workout_rewards(session, user_id, wallet, local_now, now)
            local_date = local_now.date()
            event_key = f"daily-reward:{local_date.isoformat()}"
            transaction = self._apply(
                session,
                user_id=user_id,
                wallet=self._repository.get_wallet_for_update(session, user_id, now),
                transaction_type=BananaTransactionType.DAILY_REWARD,
                amount=DAILY_REWARD_BANANAS,
                event_key=event_key,
                source_local_date=local_date,
                reference_code=None,
                now=now,
            )
            wallet = self._repository.get_wallet_for_update(session, user_id, now)
        return DailyRewardClaimResponse(
            **self._wallet_response(wallet, local_date, transaction).model_dump(),
            transaction=self._transaction_response(transaction),
        )

    def spend(
        self, session: Session, user_id: UUID, request: BananaSpendRequest, idempotency_key: UUID
    ) -> BananaSpendResponse:
        now = self._clock()
        with session.begin():
            _, wallet, local_now = self._prepare(session, user_id, now)
            self._sync_workout_rewards(session, user_id, wallet, local_now, now)
            transaction_type, amount, reference_code = self._spend_values(request)
            if (
                transaction_type is BananaTransactionType.HOUSE_ITEM_PURCHASE
                and reference_code is not None
                and self._repository.get_transaction_by_type_reference(
                    session, user_id, transaction_type, reference_code
                )
                is not None
            ):
                raise InvalidBananaSpendError
            transaction = self._apply(
                session,
                user_id=user_id,
                wallet=self._repository.get_wallet_for_update(session, user_id, now),
                transaction_type=transaction_type,
                amount=-amount,
                event_key=f"banana-spend:{idempotency_key}",
                source_local_date=local_now.date(),
                reference_code=reference_code,
                now=now,
            )
            wallet = self._repository.get_wallet_for_update(session, user_id, now)
            claim = self._repository.get_daily_claim(session, user_id, local_now.date())
        return BananaSpendResponse(
            **self._wallet_response(wallet, local_now.date(), claim).model_dump(),
            transaction=self._transaction_response(transaction),
        )

    def _prepare(
        self, session: Session, user_id: UUID, now: datetime
    ) -> tuple[str, BananaWalletRecord, datetime]:
        self._repository.acquire_user_lock(session, user_id)
        timezone = self._repository.get_user_timezone(session, user_id)
        if timezone is None:
            raise RewardProfileNotFoundError
        wallet = self._repository.get_wallet_for_update(session, user_id, now)
        return timezone, wallet, now.astimezone(ZoneInfo(timezone))

    def _sync_workout_rewards(
        self,
        session: Session,
        user_id: UUID,
        wallet: BananaWalletRecord,
        local_now: datetime,
        now: datetime,
    ) -> None:
        current_wallet = wallet
        for workout in self._repository.list_reward_eligible_workouts(session, user_id):
            reward = {
                "COMPLETED": (BananaTransactionType.WORKOUT_COMPLETED, WORKOUT_COMPLETED_BANANAS),
                "PARTIAL": (BananaTransactionType.WORKOUT_PARTIAL, WORKOUT_PARTIAL_BANANAS),
                "STOPPED_FOR_SAFETY": (
                    BananaTransactionType.WORKOUT_SAFETY_STOPPED,
                    WORKOUT_PARTIAL_BANANAS,
                ),
            }.get(workout.status_code)
            if reward is None:
                continue
            current_wallet = BananaWalletRecord(
                user_id,
                self._apply(
                    session,
                    user_id=user_id,
                    wallet=current_wallet,
                    transaction_type=reward[0],
                    amount=reward[1],
                    event_key=f"workout-reward:{workout.workout_session_id}",
                    source_local_date=workout.local_date,
                    reference_code=None,
                    workout_session_id=workout.workout_session_id,
                    now=now,
                ).balance_after,
            )
            if workout.status_code == "COMPLETED":
                current_wallet = BananaWalletRecord(
                    user_id,
                    self._apply(
                        session,
                        user_id=user_id,
                        wallet=current_wallet,
                        transaction_type=BananaTransactionType.WORKOUT_DAILY_QUEST,
                        amount=WORKOUT_DAILY_QUEST_BANANAS,
                        event_key=f"workout-daily-quest:{workout.local_date.isoformat()}",
                        source_local_date=workout.local_date,
                        reference_code=None,
                        now=now,
                    ).balance_after,
                )

    def _apply(
        self,
        session: Session,
        *,
        user_id: UUID,
        wallet: BananaWalletRecord,
        transaction_type: BananaTransactionType,
        amount: int,
        event_key: str,
        source_local_date: date,
        reference_code: str | None,
        now: datetime,
        workout_session_id: UUID | None = None,
    ) -> BananaTransactionRecord:
        existing = self._repository.get_transaction_by_event(session, user_id, event_key)
        if existing is not None:
            if (
                existing.transaction_type != transaction_type
                or existing.amount != amount
                or existing.reference_code != reference_code
            ):
                raise InvalidBananaSpendError
            return existing
        balance_after = wallet.balance + amount
        if balance_after < 0:
            raise InsufficientBananaBalanceError
        record = BananaTransactionRecord(
            transaction_id=self._uuid_factory(),
            user_id=user_id,
            workout_session_id=workout_session_id,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=balance_after,
            event_key=event_key,
            reference_code=reference_code,
            source_local_date=source_local_date,
            created_at=now,
        )
        created = self._repository.create_transaction(session, record)
        self._repository.update_wallet_balance(session, user_id, balance_after, now)
        return created

    @staticmethod
    def _spend_values(
        request: BananaSpendRequest,
    ) -> tuple[BananaTransactionType, int, str | None]:
        if request.action_code is BananaSpendActionCode.FEED_MASCOT:
            return BananaTransactionType.HOUSE_FEED, HOUSE_FEED_COST, None
        item_code = request.house_item_code
        if item_code is None or item_code not in HOUSE_ITEM_COSTS:
            raise InvalidBananaSpendError
        return BananaTransactionType.HOUSE_ITEM_PURCHASE, HOUSE_ITEM_COSTS[item_code], item_code

    @staticmethod
    def _transaction_response(record: BananaTransactionRecord) -> BananaTransactionResponse:
        return BananaTransactionResponse(
            transaction_id=str(record.transaction_id),
            transaction_type=BananaTransactionType(record.transaction_type),
            amount=record.amount,
            balance_after=record.balance_after,
            created_at=record.created_at,
        )

    @staticmethod
    def _wallet_response(
        wallet: BananaWalletRecord,
        local_date: date,
        claim: BananaTransactionRecord | None,
    ) -> BananaWalletResponse:
        return BananaWalletResponse(
            balance=wallet.balance,
            daily_reward=DailyRewardStatus(
                local_date=local_date,
                reward_amount=DAILY_REWARD_BANANAS,
                is_claimable=claim is None,
                is_claimed=claim is not None,
                claimed_at=None if claim is None else claim.created_at,
            ),
        )
