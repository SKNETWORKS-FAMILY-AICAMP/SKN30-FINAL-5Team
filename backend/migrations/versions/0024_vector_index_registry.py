"""Add the rebuildable Qdrant vector index registry.

Revision ID: 0024_vector_index_registry
Revises: 0023_v2_deliberation_store
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_vector_index_registry"
down_revision: str | None = "0023_v2_deliberation_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vector_index_registry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("collection_name", sa.String(255), nullable=False),
        sa.Column("vector_index_version", sa.String(128), nullable=False),
        sa.Column("source_manifest_hash", sa.String(64), nullable=False),
        sa.Column("embedding_model_version", sa.String(128), nullable=False),
        sa.Column("embedding_input_schema_version", sa.String(128), nullable=False),
        sa.Column("distance_metric_code", sa.String(16), nullable=False),
        sa.Column("vector_dimension", sa.Integer(), nullable=False),
        sa.Column("build_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status_code IN ('BUILDING','READY','ACTIVE','STALE','FAILED','RETIRED')",
            name="ck_vector_index_registry_status",
        ),
        sa.CheckConstraint("vector_dimension > 0", name="ck_vector_index_registry_dimension"),
        sa.CheckConstraint(
            "distance_metric_code IN ('COSINE','DOT','EUCLID','MANHATTAN')",
            name="ck_vector_index_registry_distance",
        ),
        sa.CheckConstraint(
            "source_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_vector_index_registry_source_hash",
        ),
        sa.CheckConstraint(
            "build_hash ~ '^[0-9a-f]{64}$'",
            name="ck_vector_index_registry_build_hash",
        ),
        sa.CheckConstraint(
            "status_code NOT IN ('READY','ACTIVE') OR built_at IS NOT NULL",
            name="ck_vector_index_registry_built_at",
        ),
        sa.CheckConstraint(
            "status_code <> 'ACTIVE' OR activated_at IS NOT NULL",
            name="ck_vector_index_registry_activated_at",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"], ["catalog_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vector_index_version", name="uq_vector_index_registry_version"),
    )
    op.create_index(
        "ix_vector_index_registry_catalog_status",
        "vector_index_registry",
        ["catalog_version_id", "status_code"],
    )


def downgrade() -> None:
    # Safe rollback: Qdrant collections are derived and intentionally retained;
    # only the additive PostgreSQL registry is removed.
    op.drop_index("ix_vector_index_registry_catalog_status", table_name="vector_index_registry")
    op.drop_table("vector_index_registry")
