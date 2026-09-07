from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    PremiumStatusCode,
    UserStatusCode,
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('ACTIVE', 'DORMANT', 'DELETION_PENDING', 'DISABLED')",
            name="ck_users_status_code",
        ),
        CheckConstraint(
            "code_set_version IN ('identity-mvp-v1', 'identity-social-v1')",
            name="ck_users_code_set_version",
        ),
        CheckConstraint(
            f"premium_status_code = '{PremiumStatusCode.NOT_AVAILABLE}'",
            name="ck_users_premium_status_code",
        ),
        CheckConstraint(
            "ai_trial_ends_at > ai_trial_started_at",
            name="ck_users_ai_trial_window",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    status_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default=UserStatusCode.ACTIVE
    )
    code_set_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IDENTITY_CODE_SET_VERSION
    )
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_trial_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ai_trial_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    premium_status_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PremiumStatusCode.NOT_AVAILABLE
    )

    identities: Mapped[list["UserIdentity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        CheckConstraint(
            "(provider_code = 'FIREBASE' AND code_set_version = 'identity-mvp-v1') "
            "OR (provider_code = 'KAKAO' AND code_set_version = 'identity-social-v1')",
            name="ck_user_identities_provider_code_set",
        ),
        Index(
            "uq_user_identities_active_provider_subject",
            "provider_code",
            "provider_subject",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_user_identities_active_firebase_subject",
            "firebase_subject",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    firebase_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    code_set_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IDENTITY_CODE_SET_VERSION
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="identities")


class SocialOAuthAuthorizationRequest(Base):
    __tablename__ = "social_oauth_authorization_requests"
    __table_args__ = (
        CheckConstraint(
            "provider_code IN ('KAKAO')",
            name="ck_social_oauth_authorization_provider",
        ),
        CheckConstraint(
            "code_challenge_method = 'S256'",
            name="ck_social_oauth_authorization_pkce",
        ),
        CheckConstraint("expires_at > created_at", name="ck_social_oauth_authorization_expiry"),
        Index("ix_social_oauth_authorization_requests_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    redirect_uri_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SocialOAuthRateLimitWindow(Base):
    __tablename__ = "social_oauth_rate_limit_windows"
    __table_args__ = (
        CheckConstraint("provider_code IN ('KAKAO')", name="ck_social_oauth_rate_provider"),
        CheckConstraint(
            "dimension_code IN ('CLIENT_IP', 'PROVIDER_REDIRECT')",
            name="ck_social_oauth_rate_dimension",
        ),
        CheckConstraint("request_count >= 0", name="ck_social_oauth_rate_count"),
        CheckConstraint("expires_at > window_started_at", name="ck_social_oauth_rate_expiry"),
        Index(
            "uq_social_oauth_rate_limit_window",
            "provider_code",
            "dimension_code",
            "key_digest",
            "window_started_at",
            unique=True,
        ),
        Index("ix_social_oauth_rate_limit_windows_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    dimension_code: Mapped[str] = mapped_column(String(32), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_seconds: Mapped[int] = mapped_column(nullable=False)
    request_count: Mapped[int] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "SocialOAuthAuthorizationRequest",
    "SocialOAuthRateLimitWindow",
    "User",
    "UserIdentity",
]
