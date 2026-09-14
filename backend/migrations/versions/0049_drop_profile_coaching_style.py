"""Drop the retired `user_profiles.coaching_style_code` column.

Revision ID: 0049_drop_profile_coaching_style
Revises: 0048_integrated_catalog_v2_0_7
Create Date: 2026-09-07

BL-1 stage 2. Stage 1 (`cdec29b`) stopped reading the column: onboarding writes the
one fixed style, `decisions.explanations` no longer branches on it, and both
responses report `SUPPORTIVE` from a constant rather than from this row. The column
has therefore been write-only for a full release, which is what AGENTS.md section 10
requires before a drop.

`decision_explanations.coaching_style_code` is a different column and stays: it is
part of an agent decision record, and those keep the values a past decision ran with.

Rollback restores the column, backfills the fixed style, and re-creates the CHECK
constraint. It cannot restore the per-user styles collected before stage 1; they
stopped being read a release ago, so the recovered state is the state stage 1 left.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_drop_profile_coaching_style"
down_revision: str | None = "0048_integrated_catalog_v2_0_7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_NAME = "ck_user_profiles_coaching_style"


def upgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "user_profiles", type_="check")
    op.drop_column("user_profiles", "coaching_style_code")


def downgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "coaching_style_code",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'SUPPORTIVE'"),
        ),
    )
    # The default only exists to backfill existing rows; the column was never
    # defaulted in the schema this rollback restores.
    op.alter_column("user_profiles", "coaching_style_code", server_default=None)
    op.create_check_constraint(
        _CHECK_NAME,
        "user_profiles",
        "coaching_style_code IN ('SUPPORTIVE', 'CONCISE', 'ENERGETIC')",
    )
