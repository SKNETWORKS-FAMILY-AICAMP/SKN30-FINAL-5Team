import hmac
import math
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import case, delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.db.models.calendar import (
    CalendarConnection,
    CalendarEventLink,
    CalendarOAuthRequest,
    CalendarRateLimitCounter,
)
from backend.app.db.models.workout import WorkoutSession
from backend.app.modules.external_context.ports import (
    CalendarConnectionRecord,
    CalendarEventLinkRecord,
    CalendarOAuthConsumeResult,
    CalendarOAuthRequestRecord,
    CalendarPersistenceConflictError,
    CalendarRateLimitBucketCode,
    CalendarRateLimitResult,
    CalendarSecretReference,
    OAuthConsumeStatusCode,
)

OAUTH_REQUEST_TTL = timedelta(seconds=600)
RATE_LIMIT_WINDOW = timedelta(hours=1)
RATE_LIMITS = {
    CalendarRateLimitBucketCode.TOTAL: 60,
    CalendarRateLimitBucketCode.AVAILABILITY: 30,
}
_SECRET_REFERENCE = re.compile(
    r"calendar-credential://[A-Za-z0-9][A-Za-z0-9._-]{0,62}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


def _connection_record(row: CalendarConnection) -> CalendarConnectionRecord:
    return CalendarConnectionRecord(
        connection_id=row.id,
        user_id=row.user_id,
        provider_code=row.provider_code,
        token_secret_ref=row.token_secret_ref,
        status_code=row.status_code,
        granted_at=row.granted_at,
        revoked_at=row.revoked_at,
    )


def _event_link_record(row: CalendarEventLink) -> CalendarEventLinkRecord:
    return CalendarEventLinkRecord(
        event_link_id=row.id,
        calendar_connection_id=row.calendar_connection_id,
        workout_session_id=row.workout_session_id,
        external_event_id=row.external_event_id,
        start_at=row.start_at,
        end_at=row.end_at,
        performed=row.performed,
        performance_checked_at=row.performance_checked_at,
    )


def _oauth_record(row: CalendarOAuthRequest) -> CalendarOAuthRequestRecord:
    return CalendarOAuthRequestRecord(
        request_id=row.id,
        user_id=row.user_id,
        provider_code=row.provider_code,
        state_digest=row.state_digest,
        redirect_uri_key=row.redirect_uri_key,
        code_challenge_s256=row.code_challenge_s256,
        consent_version=row.consent_version,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


def _advisory_key(*parts: object) -> int:
    material = ":".join(str(part) for part in parts).encode()
    return int.from_bytes(sha256(material).digest()[:8], "big", signed=True)


class CalendarRepository:
    """PostgreSQL persistence for Calendar flows.

    Methods flush writes but never commit. OAuth consumption must be committed before a
    provider exchange, while rate-limit increments must be committed in their own transaction.
    """

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
    ) -> CalendarConnectionRecord:
        _require_aware(granted_at, "granted_at")
        _require_aware(now, "now")
        if provider_code != "GOOGLE_CALENDAR":
            raise ValueError("unsupported calendar provider")
        if _SECRET_REFERENCE.fullmatch(token_secret_ref) is None or token_secret_ref.rsplit("/", 1)[
            -1
        ] != str(connection_id):
            raise ValueError("token_secret_ref must be an opaque reference for the connection")

        statement = (
            insert(CalendarConnection)
            .values(
                id=connection_id,
                user_id=user_id,
                provider_code=provider_code,
                provider_subject=None,
                token_secret_ref=token_secret_ref,
                status_code="ACTIVE",
                granted_at=granted_at,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        session.execute(statement)
        row = session.scalar(
            select(CalendarConnection)
            .where(
                CalendarConnection.user_id == user_id,
                CalendarConnection.provider_code == provider_code,
                CalendarConnection.status_code == "ACTIVE",
            )
            .with_for_update()
        )
        if row is None:
            row = session.get(CalendarConnection, connection_id)
        if row is None or (
            row.id != connection_id
            or row.user_id != user_id
            or row.provider_code != provider_code
            or row.token_secret_ref != token_secret_ref
            or row.status_code != "ACTIVE"
            or row.granted_at != granted_at
        ):
            raise CalendarPersistenceConflictError("calendar connection write conflicts")
        return _connection_record(row)

    def mark_connection_revoke_pending(
        self, session: Session, connection_id: UUID, now: datetime
    ) -> CalendarConnectionRecord | None:
        _require_aware(now, "now")
        row = session.scalar(
            select(CalendarConnection)
            .where(CalendarConnection.id == connection_id)
            .with_for_update()
        )
        if row is None:
            return None
        if row.status_code == "ACTIVE":
            row.status_code = "REVOKE_PENDING"
            row.updated_at = now
            session.flush()
        return _connection_record(row)

    def finalize_connection_revoked(
        self, session: Session, connection_id: UUID, now: datetime
    ) -> CalendarConnectionRecord | None:
        _require_aware(now, "now")
        row = session.scalar(
            select(CalendarConnection)
            .where(CalendarConnection.id == connection_id)
            .with_for_update()
        )
        if row is None:
            return None
        if row.status_code == "REVOKED":
            return _connection_record(row)
        if row.status_code != "REVOKE_PENDING":
            raise CalendarPersistenceConflictError("connection is not pending revocation")
        row.status_code = "REVOKED"
        row.token_secret_ref = None
        row.revoked_at = now
        row.updated_at = now
        session.flush()
        return _connection_record(row)

    def list_user_secret_references(
        self, session: Session, user_id: UUID
    ) -> tuple[CalendarSecretReference, ...]:
        rows = session.execute(
            select(CalendarConnection.id, CalendarConnection.token_secret_ref)
            .where(
                CalendarConnection.user_id == user_id,
                CalendarConnection.token_secret_ref.is_not(None),
            )
            .order_by(CalendarConnection.id)
            .with_for_update()
        )
        return tuple(
            CalendarSecretReference(connection_id=connection_id, token_secret_ref=secret_ref)
            for connection_id, secret_ref in rows
            if secret_ref is not None
        )

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
    ) -> CalendarEventLinkRecord:
        for field_name, value in (("start_at", start_at), ("end_at", end_at), ("now", now)):
            _require_aware(value, field_name)
        if not 5 <= len(external_event_id) <= 1024:
            raise ValueError("external_event_id must be between 5 and 1024 characters")
        if end_at.astimezone(UTC) <= start_at.astimezone(UTC):
            raise ValueError("calendar event end_at must be after start_at")

        connection_exists = session.scalar(
            select(CalendarConnection.id)
            .where(
                CalendarConnection.id == calendar_connection_id,
                CalendarConnection.user_id == user_id,
                CalendarConnection.status_code == "ACTIVE",
            )
            .with_for_update()
        )
        workout_exists = session.scalar(
            select(WorkoutSession.id)
            .where(
                WorkoutSession.id == workout_session_id,
                WorkoutSession.user_id == user_id,
                WorkoutSession.status_code == "PLANNED",
            )
            .with_for_update()
        )
        if connection_exists is None or workout_exists is None:
            raise CalendarPersistenceConflictError("connection or planned workout is unavailable")

        session.execute(
            insert(CalendarEventLink)
            .values(
                id=event_link_id,
                calendar_connection_id=calendar_connection_id,
                workout_session_id=workout_session_id,
                external_event_id=external_event_id,
                start_at=start_at,
                end_at=end_at,
                performed=None,
                performance_checked_at=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        row = session.scalar(
            select(CalendarEventLink)
            .where(CalendarEventLink.workout_session_id == workout_session_id)
            .with_for_update()
        )
        if row is None:
            row = session.scalar(
                select(CalendarEventLink)
                .where(
                    CalendarEventLink.calendar_connection_id == calendar_connection_id,
                    CalendarEventLink.external_event_id == external_event_id,
                )
                .with_for_update()
            )
        if row is None or (
            row.id != event_link_id
            or row.calendar_connection_id != calendar_connection_id
            or row.workout_session_id != workout_session_id
            or row.external_event_id != external_event_id
            or row.start_at != start_at
            or row.end_at != end_at
        ):
            raise CalendarPersistenceConflictError("calendar event link write conflicts")
        return _event_link_record(row)

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
    ) -> CalendarOAuthRequestRecord:
        _require_aware(created_at, "created_at")
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _advisory_key(user_id, provider_code, "calendar-oauth")},
        )
        session.execute(
            delete(CalendarOAuthRequest).where(
                CalendarOAuthRequest.user_id == user_id,
                CalendarOAuthRequest.provider_code == provider_code,
            )
        )
        row = CalendarOAuthRequest(
            id=request_id,
            user_id=user_id,
            provider_code=provider_code,
            state_digest=state_digest,
            redirect_uri_key=redirect_uri_key,
            code_challenge_s256=code_challenge_s256,
            consent_version=consent_version,
            created_at=created_at,
            expires_at=created_at + OAUTH_REQUEST_TTL,
        )
        session.add(row)
        session.flush()
        return _oauth_record(row)

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
    ) -> CalendarOAuthConsumeResult:
        _require_aware(now, "now")
        row = session.scalar(
            select(CalendarOAuthRequest)
            .where(CalendarOAuthRequest.state_digest == state_digest)
            .with_for_update()
        )
        if row is None:
            return CalendarOAuthConsumeResult(OAuthConsumeStatusCode.NOT_FOUND, None)
        if now >= row.expires_at:
            session.delete(row)
            session.flush()
            return CalendarOAuthConsumeResult(OAuthConsumeStatusCode.EXPIRED, None)
        context_matches = all(
            (
                hmac.compare_digest(str(row.user_id), str(user_id)),
                hmac.compare_digest(row.provider_code, provider_code),
                hmac.compare_digest(row.redirect_uri_key, redirect_uri_key),
            )
        )
        if not context_matches:
            return CalendarOAuthConsumeResult(OAuthConsumeStatusCode.INVALID_CONTEXT, None)
        if not hmac.compare_digest(row.code_challenge_s256, computed_code_challenge_s256):
            return CalendarOAuthConsumeResult(OAuthConsumeStatusCode.INVALID_PKCE, None)
        record = _oauth_record(row)
        session.delete(row)
        session.flush()
        return CalendarOAuthConsumeResult(OAuthConsumeStatusCode.CONSUMED, record)

    def increment_rate_limit(
        self,
        session: Session,
        *,
        user_id: UUID,
        bucket_code: CalendarRateLimitBucketCode,
        now: datetime,
    ) -> CalendarRateLimitResult:
        _require_aware(now, "now")
        normalized_now = now.astimezone(UTC)
        window_started_at = normalized_now.replace(minute=0, second=0, microsecond=0)
        window_ends_at = window_started_at + RATE_LIMIT_WINDOW
        expired = CalendarRateLimitCounter.window_ends_at <= normalized_now
        statement = (
            insert(CalendarRateLimitCounter)
            .values(
                user_id=user_id,
                bucket_code=bucket_code,
                count=1,
                window_started_at=window_started_at,
                window_ends_at=window_ends_at,
                updated_at=normalized_now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "bucket_code"],
                set_={
                    "count": case((expired, 1), else_=CalendarRateLimitCounter.count + 1),
                    "window_started_at": case(
                        (expired, window_started_at),
                        else_=CalendarRateLimitCounter.window_started_at,
                    ),
                    "window_ends_at": case(
                        (expired, window_ends_at),
                        else_=CalendarRateLimitCounter.window_ends_at,
                    ),
                    "updated_at": normalized_now,
                },
            )
            .returning(CalendarRateLimitCounter)
        )
        row = session.execute(statement).scalar_one()
        limit = RATE_LIMITS[bucket_code]
        allowed = row.count <= limit
        retry_after = 0
        if not allowed:
            retry_after = max(1, math.ceil((row.window_ends_at - normalized_now).total_seconds()))
        return CalendarRateLimitResult(
            bucket_code=bucket_code,
            count=row.count,
            limit=limit,
            allowed=allowed,
            window_ends_at=row.window_ends_at,
            retry_after_seconds=retry_after,
        )


__all__ = [
    "CalendarRepository",
    "OAUTH_REQUEST_TTL",
    "RATE_LIMITS",
    "RATE_LIMIT_WINDOW",
]
