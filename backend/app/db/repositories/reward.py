from datetime import date, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.profile import UserProfile
from backend.app.db.models.reward import BananaTransaction, BananaWallet
from backend.app.db.models.workout import DecisionSelection, WorkoutSession
from backend.app.modules.rewards.codes import BananaTransactionType
from backend.app.modules.rewards.ports import (
    BananaTransactionRecord,
    BananaWalletRecord,
    RewardEligibleWorkout,
)


class RewardRepository:
    def acquire_user_lock(self, session: Session, user_id: UUID) -> None:
        lock_key = int.from_bytes(
            sha256(f"banana-wallet:{user_id}".encode()).digest()[:8], "big", signed=True
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_user_timezone(self, session: Session, user_id: UUID) -> str | None:
        return session.scalar(select(UserProfile.timezone).where(UserProfile.user_id == user_id))

    def get_wallet_for_update(
        self, session: Session, user_id: UUID, now: datetime
    ) -> BananaWalletRecord:
        wallet = session.scalar(
            select(BananaWallet).where(BananaWallet.user_id == user_id).with_for_update()
        )
        if wallet is None:
            wallet = BananaWallet(user_id=user_id, balance=0, created_at=now, updated_at=now)
            session.add(wallet)
            session.flush()
            wallet = session.scalar(
                select(BananaWallet).where(BananaWallet.user_id == user_id).with_for_update()
            )
            if wallet is None:
                raise RuntimeError("created wallet disappeared")
        return BananaWalletRecord(user_id=wallet.user_id, balance=wallet.balance)

    def get_transaction_by_event(
        self, session: Session, user_id: UUID, event_key: str
    ) -> BananaTransactionRecord | None:
        row = session.scalar(
            select(BananaTransaction).where(
                BananaTransaction.user_id == user_id, BananaTransaction.event_key == event_key
            )
        )
        return None if row is None else self._transaction(row)

    def get_transaction_by_type_reference(
        self, session: Session, user_id: UUID, transaction_type: str, reference_code: str
    ) -> BananaTransactionRecord | None:
        row = session.scalar(
            select(BananaTransaction).where(
                BananaTransaction.user_id == user_id,
                BananaTransaction.transaction_type == transaction_type,
                BananaTransaction.reference_code == reference_code,
            )
        )
        return None if row is None else self._transaction(row)

    def create_transaction(
        self, session: Session, record: BananaTransactionRecord
    ) -> BananaTransactionRecord:
        session.add(
            BananaTransaction(
                id=record.transaction_id,
                user_id=record.user_id,
                workout_session_id=record.workout_session_id,
                transaction_type=record.transaction_type,
                amount=record.amount,
                balance_after=record.balance_after,
                event_key=record.event_key,
                reference_code=record.reference_code,
                source_local_date=record.source_local_date,
                created_at=record.created_at,
            )
        )
        session.flush()
        return record

    def update_wallet_balance(
        self, session: Session, user_id: UUID, balance: int, now: datetime
    ) -> None:
        wallet = session.get(BananaWallet, user_id)
        if wallet is None:
            raise RuntimeError("locked wallet disappeared")
        wallet.balance = balance
        wallet.updated_at = now
        session.flush()

    def list_reward_eligible_workouts(
        self, session: Session, user_id: UUID
    ) -> tuple[RewardEligibleWorkout, ...]:
        rows = session.execute(
            select(WorkoutSession.id, WorkoutSession.status_code, DecisionRun.local_date)
            .join(DecisionSelection, DecisionSelection.id == WorkoutSession.decision_selection_id)
            .join(DecisionRun, DecisionRun.id == DecisionSelection.decision_run_id)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status_code.in_(("COMPLETED", "PARTIAL", "STOPPED_FOR_SAFETY")),
            )
            .order_by(DecisionRun.local_date, WorkoutSession.id)
        ).all()
        return tuple(RewardEligibleWorkout(row[0], row[1], row[2]) for row in rows)

    def get_daily_claim(
        self, session: Session, user_id: UUID, local_date: date
    ) -> BananaTransactionRecord | None:
        row = session.scalar(
            select(BananaTransaction).where(
                BananaTransaction.user_id == user_id,
                BananaTransaction.transaction_type == BananaTransactionType.DAILY_REWARD,
                BananaTransaction.source_local_date == local_date,
            )
        )
        return None if row is None else self._transaction(row)

    @staticmethod
    def _transaction(row: BananaTransaction) -> BananaTransactionRecord:
        return BananaTransactionRecord(
            transaction_id=row.id,
            user_id=row.user_id,
            workout_session_id=row.workout_session_id,
            transaction_type=row.transaction_type,
            amount=row.amount,
            balance_after=row.balance_after,
            event_key=row.event_key,
            reference_code=row.reference_code,
            source_local_date=row.source_local_date,
            created_at=row.created_at,
        )
