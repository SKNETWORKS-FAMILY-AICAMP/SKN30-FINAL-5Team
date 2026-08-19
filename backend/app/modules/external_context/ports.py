from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.domain.rules.external_context import ProviderBusyInterval


class CalendarProviderUnavailableError(Exception):
    """The optional provider cannot serve the request; no provider payload is exposed."""


class CalendarProviderPermissionDeniedError(Exception):
    """The user denied or revoked the required calendar permission."""


class CalendarPersistenceConflictError(Exception):
    """An idempotent Calendar write conflicts with persisted data."""


class CalendarSecretCleanupPendingError(Exception):
    """A user cannot be hard-deleted while a Calendar secret reference remains."""


class OAuthConsumeStatusCode(StrEnum):
    CONSUMED = "CONSUMED"
    NOT_FOUND = "NOT_FOUND"
    EXPIRED = "EXPIRED"
    INVALID_CONTEXT = "INVALID_CONTEXT"
    INVALID_PKCE = "INVALID_PKCE"


class CalendarRateLimitBucketCode(StrEnum):
    TOTAL = "TOTAL"
    AVAILABILITY = "AVAILABILITY"


@dataclass(frozen=True, slots=True)
class CalendarConnectionRecord:
    connection_id: UUID
    user_id: UUID
    provider_code: str
    token_secret_ref: str | None
    status_code: str
    granted_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class CalendarEventLinkRecord:
    event_link_id: UUID
    calendar_connection_id: UUID
    workout_session_id: UUID
    external_event_id: str
    start_at: datetime
    end_at: datetime
    performed: bool | None
    performance_checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class CalendarOAuthRequestRecord:
    request_id: UUID
    user_id: UUID
    provider_code: str
    state_digest: str
    redirect_uri_key: str
    code_challenge_s256: str
    consent_version: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarOAuthConsumeResult:
    status_code: OAuthConsumeStatusCode
    request: CalendarOAuthRequestRecord | None


@dataclass(frozen=True, slots=True)
class CalendarRateLimitResult:
    bucket_code: CalendarRateLimitBucketCode
    count: int
    limit: int
    allowed: bool
    window_ends_at: datetime
    retry_after_seconds: int


@dataclass(frozen=True, slots=True)
class CalendarSecretReference:
    connection_id: UUID
    token_secret_ref: str


@dataclass(frozen=True, slots=True)
class CalendarEventCreate:
    workout_session_id: UUID
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("start_at", "end_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must include timezone information")
        if self.end_at.astimezone(UTC) <= self.start_at.astimezone(UTC):
            raise ValueError("calendar event end_at must be after start_at")


@dataclass(frozen=True, slots=True)
class CalendarEventReference:
    external_event_id: str

    def __post_init__(self) -> None:
        if not 5 <= len(self.external_event_id) <= 1024:
            raise ValueError("external_event_id must be between 5 and 1024 characters")


class CalendarProviderPort(Protocol):
    def get_busy_intervals(
        self,
        *,
        local_date: date,
        timezone_name: str,
    ) -> tuple[ProviderBusyInterval, ...]: ...

    def create_workout_event(self, request: CalendarEventCreate) -> CalendarEventReference: ...


class CalendarRepositoryPort(Protocol):
    def save_connection(
        self,
        session: Session,
        *,
        connection_id: UUID,
        user_id: UUID,
        provider_code: str,
        token_secret_ref: str,
        granted_at: datetime,
        now: datetime,
    ) -> CalendarConnectionRecord: ...

    def mark_connection_revoke_pending(
        self, session: Session, connection_id: UUID, now: datetime
    ) -> CalendarConnectionRecord | None: ...

    def finalize_connection_revoked(
        self, session: Session, connection_id: UUID, now: datetime
    ) -> CalendarConnectionRecord | None: ...

    def list_user_secret_references(
        self, session: Session, user_id: UUID
    ) -> tuple[CalendarSecretReference, ...]: ...

    def save_event_link(
        self,
        session: Session,
        *,
        event_link_id: UUID,
        user_id: UUID,
        calendar_connection_id: UUID,
        workout_session_id: UUID,
        external_event_id: str,
        start_at: datetime,
        end_at: datetime,
        now: datetime,
    ) -> CalendarEventLinkRecord: ...

    def replace_oauth_request(
        self,
        session: Session,
        *,
        request_id: UUID,
        user_id: UUID,
        provider_code: str,
        state_digest: str,
        redirect_uri_key: str,
        code_challenge_s256: str,
        consent_version: str,
        created_at: datetime,
    ) -> CalendarOAuthRequestRecord: ...

    def consume_oauth_request(
        self,
        session: Session,
        *,
        user_id: UUID,
        provider_code: str,
        state_digest: str,
        redirect_uri_key: str,
        computed_code_challenge_s256: str,
        now: datetime,
    ) -> CalendarOAuthConsumeResult: ...

    def increment_rate_limit(
        self,
        session: Session,
        *,
        user_id: UUID,
        bucket_code: CalendarRateLimitBucketCode,
        now: datetime,
    ) -> CalendarRateLimitResult: ...


__all__ = [
    "CalendarConnectionRecord",
    "CalendarEventCreate",
    "CalendarEventLinkRecord",
    "CalendarEventReference",
    "CalendarOAuthConsumeResult",
    "CalendarOAuthRequestRecord",
    "CalendarPersistenceConflictError",
    "CalendarProviderPermissionDeniedError",
    "CalendarProviderPort",
    "CalendarProviderUnavailableError",
    "CalendarRateLimitBucketCode",
    "CalendarRateLimitResult",
    "CalendarRepositoryPort",
    "CalendarSecretCleanupPendingError",
    "CalendarSecretReference",
    "OAuthConsumeStatusCode",
]
