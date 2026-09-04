from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class BananaWallet(Base):
    __tablename__ = "banana_wallets"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_banana_wallets_balance_nonnegative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BananaTransaction(Base):
    __tablename__ = "banana_transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('DAILY_REWARD','WORKOUT_COMPLETED','WORKOUT_PARTIAL',"
            "'WORKOUT_SAFETY_STOPPED','WORKOUT_DAILY_QUEST','HOUSE_FEED','HOUSE_ITEM_PURCHASE')",
            name="ck_banana_transactions_type",
        ),
        CheckConstraint("amount <> 0", name="ck_banana_transactions_amount_nonzero"),
        CheckConstraint("balance_after >= 0", name="ck_banana_transactions_balance_nonnegative"),
        UniqueConstraint("user_id", "event_key", name="uq_banana_transactions_user_event"),
        UniqueConstraint("workout_session_id", name="uq_banana_transactions_workout_session"),
        UniqueConstraint(
            "user_id",
            "transaction_type",
            "reference_code",
            name="uq_banana_transactions_user_type_reference",
        ),
        Index("ix_banana_transactions_user_created", "user_id", "created_at"),
        Index("ix_banana_transactions_daily_reward", "user_id", "source_local_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workout_session_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True
    )
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reference_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["BananaTransaction", "BananaWallet"]
