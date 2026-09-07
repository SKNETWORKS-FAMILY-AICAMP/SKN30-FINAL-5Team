"""Allow Google in the additive social OAuth identity boundary.

Existing Firebase and Kakao identity records remain unchanged. Raw OAuth state,
nonce, verifier, authorization code, redirect URI, tokens, and IP address never
enter this migration or the affected tables.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0047_social_oauth_google"
down_revision: str | None = "0046_social_oauth_kakao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_user_identities_provider_code_set", "user_identities", type_="check")
    op.create_check_constraint(
        "ck_user_identities_provider_code_set",
        "user_identities",
        "(provider_code = 'FIREBASE' AND code_set_version = 'identity-mvp-v1') "
        "OR (provider_code IN ('GOOGLE', 'KAKAO') "
        "AND code_set_version = 'identity-social-v1')",
    )
    op.drop_constraint(
        "ck_social_oauth_authorization_provider",
        "social_oauth_authorization_requests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_social_oauth_authorization_provider",
        "social_oauth_authorization_requests",
        "provider_code IN ('GOOGLE', 'KAKAO')",
    )
    op.drop_constraint(
        "ck_social_oauth_rate_provider",
        "social_oauth_rate_limit_windows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_social_oauth_rate_provider",
        "social_oauth_rate_limit_windows",
        "provider_code IN ('GOOGLE', 'KAKAO')",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM user_identities WHERE provider_code = 'GOOGLE'
          ) OR EXISTS (
            SELECT 1 FROM social_oauth_authorization_requests WHERE provider_code = 'GOOGLE'
          ) OR EXISTS (
            SELECT 1 FROM social_oauth_rate_limit_windows WHERE provider_code = 'GOOGLE'
          ) THEN
            RAISE EXCEPTION
              '0047 downgrade requires a forward fix while Google OAuth records exist';
          END IF;
        END $$;
        """
    )
    op.drop_constraint(
        "ck_social_oauth_rate_provider",
        "social_oauth_rate_limit_windows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_social_oauth_rate_provider",
        "social_oauth_rate_limit_windows",
        "provider_code IN ('KAKAO')",
    )
    op.drop_constraint(
        "ck_social_oauth_authorization_provider",
        "social_oauth_authorization_requests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_social_oauth_authorization_provider",
        "social_oauth_authorization_requests",
        "provider_code IN ('KAKAO')",
    )
    op.drop_constraint("ck_user_identities_provider_code_set", "user_identities", type_="check")
    op.create_check_constraint(
        "ck_user_identities_provider_code_set",
        "user_identities",
        "(provider_code = 'FIREBASE' AND code_set_version = 'identity-mvp-v1') "
        "OR (provider_code = 'KAKAO' AND code_set_version = 'identity-social-v1')",
    )
