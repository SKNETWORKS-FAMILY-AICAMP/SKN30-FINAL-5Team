from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.app.db.models.calendar import (
    CalendarConnection,
    CalendarEventLink,
    CalendarOAuthRequest,
    CalendarRateLimitCounter,
)
from backend.app.db.repositories.calendar import OAUTH_REQUEST_TTL, RATE_LIMITS, CalendarRepository
from backend.app.modules.external_context.ports import CalendarRateLimitBucketCode

NOW = datetime(2026, 8, 17, 5, 0, tzinfo=UTC)


def test_persistence_repository_policy_constants_match_accepted_contract() -> None:
    assert OAUTH_REQUEST_TTL == timedelta(seconds=600)
    assert RATE_LIMITS == {
        CalendarRateLimitBucketCode.TOTAL: 60,
        CalendarRateLimitBucketCode.AVAILABILITY: 30,
    }


def test_connection_rejects_non_reference_before_database_access() -> None:
    session = Mock()

    with pytest.raises(ValueError, match="opaque reference"):
        CalendarRepository().save_connection(
            session,
            connection_id=uuid4(),
            user_id=uuid4(),
            provider_code="GOOGLE_CALENDAR",
            token_secret_ref="invalid-reference",
            granted_at=NOW,
            now=NOW,
        )

    session.execute.assert_not_called()


@pytest.mark.parametrize("external_event_id", ["abcd", "x" * 1025])
def test_event_link_rejects_external_id_outside_contract(external_event_id: str) -> None:
    session = Mock()

    with pytest.raises(ValueError, match="between 5 and 1024"):
        CalendarRepository().save_event_link(
            session,
            event_link_id=uuid4(),
            user_id=uuid4(),
            calendar_connection_id=uuid4(),
            workout_session_id=uuid4(),
            external_event_id=external_event_id,
            start_at=NOW,
            end_at=NOW + timedelta(minutes=30),
            now=NOW,
        )

    session.scalar.assert_not_called()


def test_calendar_schema_has_no_raw_secret_state_or_payload_columns() -> None:
    columns = {
        table.name: set(table.columns.keys())
        for table in (
            CalendarConnection.__table__,
            CalendarEventLink.__table__,
            CalendarOAuthRequest.__table__,
            CalendarRateLimitCounter.__table__,
        )
    }

    assert columns["calendar_connections"] == {
        "id",
        "user_id",
        "provider_code",
        "provider_subject",
        "token_secret_ref",
        "status_code",
        "granted_at",
        "revoked_at",
        "created_at",
        "updated_at",
    }
    assert columns["calendar_oauth_requests"] == {
        "id",
        "user_id",
        "provider_code",
        "state_digest",
        "redirect_uri_key",
        "code_challenge_s256",
        "consent_version",
        "created_at",
        "expires_at",
    }
    all_columns = {column for table_columns in columns.values() for column in table_columns}
    forbidden = {
        "access_token",
        "refresh_token",
        "state",
        "verifier",
        "authorization_code",
        "provider_payload",
        "calendar_body",
    }
    assert all_columns.isdisjoint(forbidden)
