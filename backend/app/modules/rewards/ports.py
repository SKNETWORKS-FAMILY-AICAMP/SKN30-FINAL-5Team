from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class BananaWalletRecord:
    user_id: UUID
    balance: int


@dataclass(frozen=True, slots=True)
class BananaTransactionRecord:
    transaction_id: UUID
    user_id: UUID
    workout_session_id: UUID | None
    transaction_type: str
    amount: int
    balance_after: int
    event_key: str
    reference_code: str | None
    source_local_date: date | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RewardEligibleWorkout:
    workout_session_id: UUID
    status_code: str
    local_date: date


class RewardRepositoryPort(Protocol):
    def acquire_user_lock(self, session: Session, user_id: UUID) -> None: ...
    def get_user_timezone(self, session: Session, user_id: UUID) -> str | None: ...
    def get_wallet_for_update(
        self, session: Session, user_id: UUID, now: datetime
    ) -> BananaWalletRecord: ...
    def get_transaction_by_event(
        self, session: Session, user_id: UUID, event_key: str
    ) -> BananaTransactionRecord | None: ...
    def get_transaction_by_type_reference(
        self, session: Session, user_id: UUID, transaction_type: str, reference_code: str
    ) -> BananaTransactionRecord | None: ...
    def create_transaction(
        self, session: Session, record: BananaTransactionRecord
    ) -> BananaTransactionRecord: ...
    def update_wallet_balance(
        self, session: Session, user_id: UUID, balance: int, now: datetime
    ) -> None: ...
    def list_reward_eligible_workouts(
        self, session: Session, user_id: UUID
    ) -> tuple[RewardEligibleWorkout, ...]: ...
    def get_daily_claim(
        self, session: Session, user_id: UUID, local_date: date
    ) -> BananaTransactionRecord | None: ...
