"""Add Calendar connection, event, OAuth, and rate-limit persistence.

Revision ID: 0013_calendar_persistence_foundation
Revises: 0012_account_deletion_retention
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_calendar_persistence_foundation"
down_revision: str | None = "0012_account_deletion_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(32), nullable=False),
        sa.Column("provider_subject", sa.String(255), nullable=True),
        sa.Column("token_secret_ref", sa.String(255), nullable=True),
        sa.Column("status_code", sa.String(24), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "provider_code = 'GOOGLE_CALENDAR'",
            name="ck_calendar_connections_provider",
        ),
        sa.CheckConstraint(
            "status_code IN ('ACTIVE','REVOKE_PENDING','REVOKED')",
            name="ck_calendar_connections_status",
        ),
        sa.CheckConstraint(
            "provider_subject IS NULL",
            name="ck_calendar_connections_google_subject",
        ),
        sa.CheckConstraint(
            "token_secret_ref IS NULL OR ("
            "token_secret_ref ~ '^calendar-credential://[A-Za-z0-9][A-Za-z0-9._-]{0,62}/"
            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' "
            "AND split_part(token_secret_ref, '/', 4) = id::text)",
            name="ck_calendar_connections_secret_ref",
        ),
        sa.CheckConstraint(
            "(status_code = 'ACTIVE' AND token_secret_ref IS NOT NULL AND revoked_at IS NULL) OR "
            "(status_code = 'REVOKE_PENDING' AND revoked_at IS NULL) OR "
            "(status_code = 'REVOKED' AND token_secret_ref IS NULL AND revoked_at IS NOT NULL)",
            name="ck_calendar_connections_lifecycle",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_connections_user_id", "calendar_connections", ["user_id"])
    op.create_index(
        "uq_calendar_connections_active_user_provider",
        "calendar_connections",
        ["user_id", "provider_code"],
        unique=True,
        postgresql_where=sa.text("status_code = 'ACTIVE'"),
    )
    op.create_index(
        "uq_calendar_connections_token_secret_ref",
        "calendar_connections",
        ["token_secret_ref"],
        unique=True,
        postgresql_where=sa.text("token_secret_ref IS NOT NULL"),
    )

    op.create_table(
        "calendar_oauth_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(32), nullable=False),
        sa.Column("state_digest", sa.String(64), nullable=False),
        sa.Column("redirect_uri_key", sa.String(64), nullable=False),
        sa.Column("code_challenge_s256", sa.String(43), nullable=False),
        sa.Column("consent_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_code = 'GOOGLE_CALENDAR'",
            name="ck_calendar_oauth_requests_provider",
        ),
        sa.CheckConstraint(
            "state_digest ~ '^[0-9a-f]{64}$'",
            name="ck_calendar_oauth_requests_state_digest",
        ),
        sa.CheckConstraint(
            "redirect_uri_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'",
            name="ck_calendar_oauth_requests_redirect_key",
        ),
        sa.CheckConstraint(
            "code_challenge_s256 ~ '^[A-Za-z0-9_-]{43}$'",
            name="ck_calendar_oauth_requests_pkce_challenge",
        ),
        sa.CheckConstraint(
            "expires_at = created_at + INTERVAL '600 seconds'",
            name="ck_calendar_oauth_requests_expiry",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_digest"),
    )
    op.create_index("ix_calendar_oauth_requests_user_id", "calendar_oauth_requests", ["user_id"])
    op.create_index(
        "uq_calendar_oauth_requests_user_provider",
        "calendar_oauth_requests",
        ["user_id", "provider_code"],
        unique=True,
    )
    op.create_index(
        "ix_calendar_oauth_requests_expires_at", "calendar_oauth_requests", ["expires_at"]
    )

    op.create_table(
        "calendar_rate_limit_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("bucket_code", sa.String(24), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "bucket_code IN ('TOTAL','AVAILABILITY')",
            name="ck_calendar_rate_limit_counters_bucket",
        ),
        sa.CheckConstraint("count >= 0", name="ck_calendar_rate_limit_counters_count"),
        sa.CheckConstraint(
            "window_ends_at = window_started_at + INTERVAL '1 hour'",
            name="ck_calendar_rate_limit_counters_window",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "bucket_code"),
    )

    op.create_table(
        "calendar_event_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("calendar_connection_id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("external_event_id", sa.String(1024), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed", sa.Boolean(), nullable=True),
        sa.Column("performance_checked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "char_length(external_event_id) BETWEEN 5 AND 1024",
            name="ck_calendar_event_links_external_id_length",
        ),
        sa.CheckConstraint("end_at > start_at", name="ck_calendar_event_links_window"),
        sa.CheckConstraint(
            "performed IS NULL",
            name="ck_calendar_event_links_google_performed",
        ),
        sa.ForeignKeyConstraint(
            ["calendar_connection_id"], ["calendar_connections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workout_session_id"),
    )
    op.create_index(
        "ix_calendar_event_links_calendar_connection_id",
        "calendar_event_links",
        ["calendar_connection_id"],
    )
    op.create_index(
        "uq_calendar_event_links_connection_external",
        "calendar_event_links",
        ["calendar_connection_id", "external_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_calendar_event_links_connection_external", table_name="calendar_event_links")
    op.drop_index(
        "ix_calendar_event_links_calendar_connection_id", table_name="calendar_event_links"
    )
    op.drop_table("calendar_event_links")
    op.drop_table("calendar_rate_limit_counters")
    op.drop_index("ix_calendar_oauth_requests_expires_at", table_name="calendar_oauth_requests")
    op.drop_index("uq_calendar_oauth_requests_user_provider", table_name="calendar_oauth_requests")
    op.drop_index("ix_calendar_oauth_requests_user_id", table_name="calendar_oauth_requests")
    op.drop_table("calendar_oauth_requests")
    op.drop_index("uq_calendar_connections_token_secret_ref", table_name="calendar_connections")
    op.drop_index("uq_calendar_connections_active_user_provider", table_name="calendar_connections")
    op.drop_index("ix_calendar_connections_user_id", table_name="calendar_connections")
    op.drop_table("calendar_connections")
