"""Persist user-scoped in-app notification state.

Revision ID: 0041_in_app_notifications
Revises: 0040_weekly_safety_and_calorie
Create Date: 2026-09-04

The event key is part of the server-side deduplication contract.  It prevents two
concurrent list requests from publishing the same logical notification for one user.
The data is additive; downgrade removes only this new table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_in_app_notifications"
down_revision: str | None = "0040_weekly_safety_and_calorie"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "in_app_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type_code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type_code IN ('DAILY_REWARD','WEEKLY_GOAL_REMINDER','KIKKI_RETURN')",
            name="ck_in_app_notifications_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_key", name="uq_in_app_notifications_user_event"),
    )
    op.create_index(
        "ix_in_app_notifications_user_created",
        "in_app_notifications",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_in_app_notifications_user_created", table_name="in_app_notifications")
    op.drop_table("in_app_notifications")
