from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.integrations.calendar_provider import (
    UnavailableCalendarProvider,
    build_calendar_provider,
)
from backend.app.modules.external_context.ports import (
    CalendarEventCreate,
    CalendarProviderUnavailableError,
)

NOW = datetime(2026, 8, 14, 1, 0, tzinfo=UTC)


def test_factory_returns_null_object_without_google_credentials() -> None:
    assert isinstance(build_calendar_provider(), UnavailableCalendarProvider)


def test_unavailable_provider_fails_every_external_operation_without_payload() -> None:
    provider = UnavailableCalendarProvider()
    request = CalendarEventCreate(uuid4(), NOW, NOW + timedelta(minutes=30))

    operations = (
        lambda: provider.get_busy_intervals(
            local_date=date(2026, 8, 14),
            timezone_name="Asia/Seoul",
        ),
        lambda: provider.create_workout_event(request),
        lambda: provider.get_performance(
            scheduled_workout_id=request.scheduled_workout_id,
            external_event_id="abcde",
            checked_at=NOW,
        ),
        lambda: provider.revoke(token_secret_ref="local-ci-secret-reference"),
    )

    for operation in operations:
        with pytest.raises(CalendarProviderUnavailableError) as captured:
            operation()
        assert str(captured.value) == ""
