"""Add Firebase identity authentication boundary tables.

Revision ID: 0003_identity_auth_boundary
Revises: 0002_catalog_core
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_identity_auth_boundary"
down_revision: str | None = "0002_catalog_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status_code", sa.String(length=32), nullable=False),
        sa.Column("code_set_version", sa.String(length=32), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_trial_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ai_trial_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("premium_status_code", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status_code IN ('ACTIVE', 'DORMANT', 'DELETION_PENDING', 'DISABLED')",
            name="ck_users_status_code",
        ),
        sa.CheckConstraint(
            "code_set_version = 'identity-mvp-v1'",
            name="ck_users_code_set_version",
        ),
        sa.CheckConstraint(
            "premium_status_code = 'NOT_AVAILABLE'",
            name="ck_users_premium_status_code",
        ),
        sa.CheckConstraint(
            "ai_trial_ends_at > ai_trial_started_at",
            name="ck_users_ai_trial_window",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )

    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=32), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("firebase_subject", sa.String(length=255), nullable=False),
        sa.Column("code_set_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "provider_code IN ('FIREBASE')",
            name="ck_user_identities_provider_code",
        ),
        sa.CheckConstraint(
            "code_set_version = 'identity-mvp-v1'",
            name="ck_user_identities_code_set_version",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_identities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_identities"),
    )
    op.create_index(
        "ix_user_identities_user_id",
        "user_identities",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_user_identities_active_provider_subject",
        "user_identities",
        ["provider_code", "provider_subject"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_user_identities_active_firebase_subject",
        "user_identities",
        ["firebase_subject"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_user_identities_active_firebase_subject",
        table_name="user_identities",
    )
    op.drop_index(
        "uq_user_identities_active_provider_subject",
        table_name="user_identities",
    )
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_table("users")
