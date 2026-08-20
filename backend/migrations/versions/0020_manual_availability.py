"""Add user-entered workout availability slots to the daily check-in.

External calendar integration is deferred (ADR-0010 "구현 보류"), so the manual
check-in input is the only availability source. ``availability_source_code``
separates "not provided" from an explicit "no time today" choice, which the
domain preserves in ``select_availability``.

Revision ID: 0020_manual_availability
Revises: 0019_decision_explanations
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_manual_availability"
down_revision: str | None = "0019_decision_explanations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_contexts",
        sa.Column(
            "availability_source_code",
            sa.String(32),
            nullable=False,
            server_default="ROUTINE_DEFAULT",
        ),
    )
    # CALENDAR is reserved for a resumed provider integration and is not written today.
    op.create_check_constraint(
        "ck_daily_contexts_availability_source",
        "daily_contexts",
        "availability_source_code IN ('MANUAL', 'ROUTINE_DEFAULT')",
    )

    op.create_table(
        "daily_context_availability_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("daily_context_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("end_at > start_at", name="ck_daily_context_slot_range"),
        # The upper bound matches the domain MAX_AVAILABILITY_SLOTS of 8.
        sa.CheckConstraint(
            "slot_order >= 0 AND slot_order < 8",
            name="ck_daily_context_slot_order",
        ),
        sa.ForeignKeyConstraint(["daily_context_id"], ["daily_contexts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("daily_context_id", "slot_order", name="uq_daily_context_slot_order"),
    )
    op.create_index(
        "ix_daily_context_availability_slots_context",
        "daily_context_availability_slots",
        ["daily_context_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_context_availability_slots_context",
        table_name="daily_context_availability_slots",
    )
    op.drop_table("daily_context_availability_slots")
    op.drop_constraint("ck_daily_contexts_availability_source", "daily_contexts", type_="check")
    op.drop_column("daily_contexts", "availability_source_code")
