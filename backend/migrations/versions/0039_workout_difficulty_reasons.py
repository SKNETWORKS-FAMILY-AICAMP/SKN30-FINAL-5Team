"""Store why a HARD session felt hard, so the next routine can lower one axis.

Revision ID: 0039_workout_difficulty_reasons
Revises: 0038_workout_execution_state
Create Date: 2026-09-03

ADR-0018 (D2) fixed the downshift ladder as exercise difficulty, then intensity, then
time allocation, and made `VOLUME_HIGH` / `MOVEMENT_DIFFICULT` the input that picks the
axis. `workout_feedback.difficulty_code` alone cannot carry that: it says the session was
hard, not which lever to move.

Typed rows rather than a JSONB column because the decision path reads and replays these
values; `AGENTS.md` 10 reserves JSONB for flexible proposal and metadata fields.

Additive only. No existing row or column changes, so the rollback simply drops the new
table. Rows only ever exist for `difficulty_code='HARD'` feedback; that pairing is
enforced in the service rather than by a constraint, because the check would have to
reach across tables.

Numbering note: this revision was authored on top of 0037 while 0038 was held for the
in-flight workout execution work. That work landed first, so it now chains onto 0038.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_workout_difficulty_reasons"
down_revision: str | None = "0038_workout_execution_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_feedback_difficulty_reasons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason_code IN ('VOLUME_HIGH','MOVEMENT_DIFFICULT')",
            name="ck_workout_feedback_difficulty_reason_code",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"],
            ["workout_feedback.workout_session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_session_id",
            "reason_code",
            name="uq_workout_feedback_difficulty_reason",
        ),
    )
    op.create_index(
        "ix_workout_feedback_difficulty_reasons_session",
        "workout_feedback_difficulty_reasons",
        ["workout_session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workout_feedback_difficulty_reasons_session",
        table_name="workout_feedback_difficulty_reasons",
    )
    op.drop_table("workout_feedback_difficulty_reasons")
