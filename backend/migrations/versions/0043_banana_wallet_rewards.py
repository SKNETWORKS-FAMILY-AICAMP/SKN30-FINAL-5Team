"""Persist server-authoritative banana wallets and transaction events.

Revision ID: 0043_banana_wallet_rewards
Revises: 0042_in_app_notifications
Create Date: 2026-09-04

The migration is additive.  Downgrade removes the new wallet and transaction
tables only; no pre-existing user or workout data is modified.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_banana_wallet_rewards"
down_revision: str | None = "0042_in_app_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "banana_wallets",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_banana_wallets_balance_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "banana_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("reference_code", sa.String(length=64), nullable=True),
        sa.Column("source_local_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transaction_type IN ('DAILY_REWARD','WORKOUT_COMPLETED','WORKOUT_PARTIAL',"
            "'WORKOUT_SAFETY_STOPPED','WORKOUT_DAILY_QUEST','HOUSE_FEED','HOUSE_ITEM_PURCHASE')",
            name="ck_banana_transactions_type",
        ),
        sa.CheckConstraint("amount <> 0", name="ck_banana_transactions_amount_nonzero"),
        sa.CheckConstraint("balance_after >= 0", name="ck_banana_transactions_balance_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_key", name="uq_banana_transactions_user_event"),
        sa.UniqueConstraint("workout_session_id", name="uq_banana_transactions_workout_session"),
        sa.UniqueConstraint(
            "user_id",
            "transaction_type",
            "reference_code",
            name="uq_banana_transactions_user_type_reference",
        ),
    )
    op.create_index(
        "ix_banana_transactions_user_created", "banana_transactions", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_banana_transactions_daily_reward",
        "banana_transactions",
        ["user_id", "source_local_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_banana_transactions_daily_reward", table_name="banana_transactions")
    op.drop_index("ix_banana_transactions_user_created", table_name="banana_transactions")
    op.drop_table("banana_transactions")
    op.drop_table("banana_wallets")
