from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.modules.identity.codes import (
    IDENTITY_CODE_SET_VERSION,
    IdentityProviderCode,
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
            f"code_set_version = '{IDENTITY_CODE_SET_VERSION}'",
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
            f"provider_code IN ('{IdentityProviderCode.FIREBASE}')",
            name="ck_user_identities_provider_code",
        ),
        CheckConstraint(
            f"code_set_version = '{IDENTITY_CODE_SET_VERSION}'",
            name="ck_user_identities_code_set_version",
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


__all__ = ["User", "UserIdentity"]
