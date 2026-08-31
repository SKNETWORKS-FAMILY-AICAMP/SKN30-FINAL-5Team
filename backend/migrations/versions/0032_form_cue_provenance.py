"""Record where an exercise's form cues came from and whether they are reviewed.

Revision ID: 0032_form_cue_provenance
Revises: 0031_catalog_v2_0_2_identity
Create Date: 2026-08-31

v2.0.2 loaded 75 pain-area safe variants. 54 carry cues written into
``discomfort_safe_variants_v2_0_2.jsonl``; the other 21 were rendered from the
same template afterwards because that file never covered them. Both sets read
identically, so once the rows were in the database there was no way to ask which
cues a reviewer had actually seen - the question you have to answer before
showing coaching text to a beginner.

``form_cues_source`` names the artifact or template a record's cues came from,
and ``form_cues_review_status`` carries ``REVIEW_REQUIRED`` while they are
waiting on a reviewer. Both are nullable: rows imported before this migration,
and catalogs whose cues were always part of the reviewed payload, leave them
unset, and NULL means "not stated" rather than "reviewed".

The columns are additive, so the downgrade simply drops them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_form_cue_provenance"
down_revision: str | None = "0031_catalog_v2_0_2_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column("form_cues_source", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "exercises",
        sa.Column("form_cues_review_status", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_exercises_form_cues_review_status",
        "exercises",
        "form_cues_review_status IS NULL OR "
        "form_cues_review_status IN ('REVIEW_REQUIRED', 'DOMAIN_APPROVED')",
    )
    # The reason the columns exist: find the unreviewed cues without scanning text.
    op.create_index(
        "ix_exercises_form_cues_review",
        "exercises",
        ["catalog_version_id", "form_cues_review_status"],
        postgresql_where=sa.text("form_cues_review_status IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_exercises_form_cues_review", table_name="exercises")
    op.drop_constraint("ck_exercises_form_cues_review_status", "exercises", type_="check")
    op.drop_column("exercises", "form_cues_review_status")
    op.drop_column("exercises", "form_cues_source")
