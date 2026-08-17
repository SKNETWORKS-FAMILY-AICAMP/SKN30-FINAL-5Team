from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"
    __table_args__ = (
        CheckConstraint(
            "provider_code = 'GOOGLE_CALENDAR'",
            name="ck_calendar_connections_provider",
        ),
        CheckConstraint(
            "status_code IN ('ACTIVE','REVOKE_PENDING','REVOKED')",
            name="ck_calendar_connections_status",
        ),
        CheckConstraint(
            "provider_subject IS NULL",
            name="ck_calendar_connections_google_subject",
        ),
        CheckConstraint(
            "token_secret_ref IS NULL OR ("
            "token_secret_ref ~ '^calendar-credential://[A-Za-z0-9][A-Za-z0-9._-]{0,62}/"
            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' "
            "AND split_part(token_secret_ref, '/', 4) = id::text)",
            name="ck_calendar_connections_secret_ref",
        ),
        CheckConstraint(
            "(status_code = 'ACTIVE' AND token_secret_ref IS NOT NULL AND revoked_at IS NULL) OR "
            "(status_code = 'REVOKE_PENDING' AND revoked_at IS NULL) OR "
            "(status_code = 'REVOKED' AND token_secret_ref IS NULL AND revoked_at IS NOT NULL)",
            name="ck_calendar_connections_lifecycle",
        ),
        Index(
            "uq_calendar_connections_active_user_provider",
            "user_id",
            "provider_code",
            unique=True,
            postgresql_where=text("status_code = 'ACTIVE'"),
        ),
        Index(
            "uq_calendar_connections_token_secret_ref",
            "token_secret_ref",
            unique=True,
            postgresql_where=text("token_secret_ref IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[str] = mapped_column(String(24), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CalendarEventLink(Base):
    __tablename__ = "calendar_event_links"
    __table_args__ = (
        CheckConstraint(
            "char_length(external_event_id) BETWEEN 5 AND 1024",
            name="ck_calendar_event_links_external_id_length",
        ),
        CheckConstraint("end_at > start_at", name="ck_calendar_event_links_window"),
        CheckConstraint("performed IS NULL", name="ck_calendar_event_links_google_performed"),
        Index(
            "uq_calendar_event_links_connection_external",
            "calendar_connection_id",
            "external_event_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    calendar_connection_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("calendar_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workout_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    external_event_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    performed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    performance_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CalendarOAuthRequest(Base):
    __tablename__ = "calendar_oauth_requests"
    __table_args__ = (
        CheckConstraint(
            "provider_code = 'GOOGLE_CALENDAR'",
            name="ck_calendar_oauth_requests_provider",
        ),
        CheckConstraint(
            "state_digest ~ '^[0-9a-f]{64}$'",
            name="ck_calendar_oauth_requests_state_digest",
        ),
        CheckConstraint(
            "redirect_uri_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'",
            name="ck_calendar_oauth_requests_redirect_key",
        ),
        CheckConstraint(
            "code_challenge_s256 ~ '^[A-Za-z0-9_-]{43}$'",
            name="ck_calendar_oauth_requests_pkce_challenge",
        ),
        CheckConstraint(
            "expires_at = created_at + INTERVAL '600 seconds'",
            name="ck_calendar_oauth_requests_expiry",
        ),
        Index(
            "uq_calendar_oauth_requests_user_provider",
            "user_id",
            "provider_code",
            unique=True,
        ),
        Index("ix_calendar_oauth_requests_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    state_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    redirect_uri_key: Mapped[str] = mapped_column(String(64), nullable=False)
    code_challenge_s256: Mapped[str] = mapped_column(String(43), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CalendarRateLimitCounter(Base):
    __tablename__ = "calendar_rate_limit_counters"
    __table_args__ = (
        CheckConstraint(
            "bucket_code IN ('TOTAL','AVAILABILITY')",
            name="ck_calendar_rate_limit_counters_bucket",
        ),
        CheckConstraint("count >= 0", name="ck_calendar_rate_limit_counters_count"),
        CheckConstraint(
            "window_ends_at = window_started_at + INTERVAL '1 hour'",
            name="ck_calendar_rate_limit_counters_window",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    bucket_code: Mapped[str] = mapped_column(String(24), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "CalendarConnection",
    "CalendarEventLink",
    "CalendarOAuthRequest",
    "CalendarRateLimitCounter",
]
