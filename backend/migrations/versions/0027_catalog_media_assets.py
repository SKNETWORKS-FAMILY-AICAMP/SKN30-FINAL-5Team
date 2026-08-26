"""Add reviewed exercise media assets.

Revision ID: 0027_catalog_media_assets
Revises: 0026_catalog_v2_code_set
Create Date: 2026-08-26

The table is additive and may be safely dropped while no downstream system
depends on stored media references. After production media is loaded, prefer a
forward-fix migration so review evidence is not discarded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_catalog_media_assets"
down_revision: str | None = "0026_catalog_v2_code_set"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercise_media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("s3_key", sa.String(length=500), nullable=False),
        sa.Column("media_status", sa.String(length=32), nullable=False),
        sa.Column("rights_review_status", sa.String(length=32), nullable=False),
        sa.Column("rights_reviewer", sa.String(length=255), nullable=True),
        sa.Column("rights_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rights_evidence_reference", sa.String(length=500), nullable=True),
        sa.Column("media_set_version_code", sa.String(length=120), nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approval_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "media_status IN ('AVAILABLE', 'UNAVAILABLE')",
            name="ck_exercise_media_assets_media_status",
        ),
        sa.CheckConstraint(
            "rights_review_status IN ('APPROVED', 'PENDING', 'REJECTED')",
            name="ck_exercise_media_assets_rights_status",
        ),
        sa.CheckConstraint(
            "rights_review_status <> 'APPROVED' OR "
            "(rights_reviewer IS NOT NULL AND rights_reviewed_at IS NOT NULL "
            "AND rights_evidence_reference IS NOT NULL)",
            name="ck_exercise_media_assets_approved_evidence",
        ),
        sa.CheckConstraint(
            "s3_key ~ '^catalog-media/[a-z0-9][a-z0-9_./-]*\\.(gif|jpe?g|mp4|png|webp)$' "
            "AND position('..' in s3_key) = 0",
            name="ck_exercise_media_assets_s3_key",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"], ["catalog_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_version_id",
            "exercise_id",
            name="uq_exercise_media_assets_catalog_exercise",
        ),
        sa.UniqueConstraint("s3_key", name="uq_exercise_media_assets_s3_key"),
    )
    op.create_index(
        "ix_exercise_media_assets_approved",
        "exercise_media_assets",
        ["catalog_version_id", "exercise_id"],
        unique=False,
        postgresql_where=sa.text(
            "media_status = 'AVAILABLE' AND rights_review_status = 'APPROVED'"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_exercise_media_assets_approved", table_name="exercise_media_assets")
    op.drop_table("exercise_media_assets")
