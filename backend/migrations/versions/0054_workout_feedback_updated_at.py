"""Record when a workout feedback row was last rewritten.

Revision ID: 0054_workout_feedback_updated_at
Revises: 0053_banana_bonding_quest
Create Date: 2026-09-10

Feedback used to be written once and never again, so `created_at` said both when
the row was made and when the answer was given. A session can now be stopped,
resumed and stopped again, and the user is asked how it went each time; the last
answer replaces the earlier one. `created_at` therefore keeps its own meaning --
when the user first answered for this session -- and this column carries the one
that changes.

Existing rows are backfilled from `created_at`, which is exactly right for them:
they were written once and never rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_workout_feedback_updated_at"
down_revision: str | None = "0053_banana_bonding_quest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "workout_feedback"
_COLUMN = "updated_at"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True))
    op.execute(f"UPDATE {_TABLE} SET {_COLUMN} = created_at WHERE {_COLUMN} IS NULL")
    op.alter_column(_TABLE, _COLUMN, nullable=False)


def downgrade() -> None:
    # Safe to drop: `created_at` still holds the first answer, and no row's
    # content depends on this column.
    op.drop_column(_TABLE, _COLUMN)
