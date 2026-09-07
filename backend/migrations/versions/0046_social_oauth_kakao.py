"""Add the additive Kakao OAuth identity boundary.

Raw OAuth state, nonce, verifier, code, tokens, redirect URI and IP address
never enter these tables.  Existing Firebase identity rows keep their original
``identity-mvp-v1`` code-set value.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_social_oauth_kakao"
down_revision: str | None = "0045_v2_0_6_release_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_code_set_version", "users", type_="check")
    op.create_check_constraint(
        "ck_users_code_set_version",
        "users",
        "code_set_version IN ('identity-mvp-v1', 'identity-social-v1')",
    )
    op.drop_constraint("ck_user_identities_provider_code", "user_identities", type_="check")
    op.drop_constraint("ck_user_identities_code_set_version", "user_identities", type_="check")
    op.create_check_constraint(
        "ck_user_identities_provider_code_set",
        "user_identities",
        "(provider_code = 'FIREBASE' AND code_set_version = 'identity-mvp-v1') "
        "OR (provider_code = 'KAKAO' AND code_set_version = 'identity-social-v1')",
    )

    op.create_table(
        "social_oauth_authorization_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=32), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("redirect_uri_hash", sa.String(length=64), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_code IN ('KAKAO')",
            name="ck_social_oauth_authorization_provider",
        ),
        sa.CheckConstraint(
            "code_challenge_method = 'S256'",
            name="ck_social_oauth_authorization_pkce",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_social_oauth_authorization_expiry"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index(
        "ix_social_oauth_authorization_requests_expires_at",
        "social_oauth_authorization_requests",
        ["expires_at"],
    )
    op.create_table(
        "social_oauth_rate_limit_windows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=32), nullable=False),
        sa.Column("dimension_code", sa.String(length=32), nullable=False),
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_code IN ('KAKAO')",
            name="ck_social_oauth_rate_provider",
        ),
        sa.CheckConstraint(
            "dimension_code IN ('CLIENT_IP', 'PROVIDER_REDIRECT')",
            name="ck_social_oauth_rate_dimension",
        ),
        sa.CheckConstraint("request_count >= 0", name="ck_social_oauth_rate_count"),
        sa.CheckConstraint("expires_at > window_started_at", name="ck_social_oauth_rate_expiry"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_code",
            "dimension_code",
            "key_digest",
            "window_started_at",
            name="uq_social_oauth_rate_limit_window",
        ),
    )
    op.create_index(
        "ix_social_oauth_rate_limit_windows_expires_at",
        "social_oauth_rate_limit_windows",
        ["expires_at"],
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM user_identities WHERE provider_code = 'KAKAO')
             OR EXISTS (SELECT 1 FROM users WHERE code_set_version = 'identity-social-v1') THEN
            RAISE EXCEPTION '0046 downgrade requires a forward fix while Kakao identities exist';
          END IF;
        END $$;
        """
    )
    op.drop_index(
        "ix_social_oauth_rate_limit_windows_expires_at",
        table_name="social_oauth_rate_limit_windows",
    )
    op.drop_table("social_oauth_rate_limit_windows")
    op.drop_index(
        "ix_social_oauth_authorization_requests_expires_at",
        table_name="social_oauth_authorization_requests",
    )
    op.drop_table("social_oauth_authorization_requests")
    op.drop_constraint(
        "ck_user_identities_provider_code_set",
        "user_identities",
        type_="check",
    )
    op.create_check_constraint(
        "ck_user_identities_provider_code",
        "user_identities",
        "provider_code IN ('FIREBASE')",
    )
    op.create_check_constraint(
        "ck_user_identities_code_set_version",
        "user_identities",
        "code_set_version = 'identity-mvp-v1'",
    )
    op.drop_constraint("ck_users_code_set_version", "users", type_="check")
    op.create_check_constraint(
        "ck_users_code_set_version",
        "users",
        "code_set_version = 'identity-mvp-v1'",
    )
