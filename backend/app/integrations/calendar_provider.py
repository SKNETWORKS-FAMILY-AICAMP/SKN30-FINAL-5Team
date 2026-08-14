from datetime import date, datetime
from uuid import UUID

from backend.app.domain.rules.external_context import (
    CalendarPerformanceObservation,
    ProviderBusyInterval,
)
from backend.app.modules.external_context.ports import (
    CalendarEventCreate,
    CalendarEventReference,
    CalendarProviderPort,
    CalendarProviderUnavailableError,
)


class UnavailableCalendarProvider:
    """Local/CI null object used until the approved Google adapter is installed."""

    def get_busy_intervals(
        self,
        *,
        local_date: date,
        timezone_name: str,
    ) -> tuple[ProviderBusyInterval, ...]:
        del local_date, timezone_name
        raise CalendarProviderUnavailableError

    def create_workout_event(self, request: CalendarEventCreate) -> CalendarEventReference:
        del request
        raise CalendarProviderUnavailableError

    def get_performance(
        self,
        *,
        scheduled_workout_id: UUID,
        external_event_id: str,
        checked_at: datetime,
    ) -> CalendarPerformanceObservation:
        del scheduled_workout_id, external_event_id, checked_at
        raise CalendarProviderUnavailableError

    def revoke(self, *, token_secret_ref: str) -> None:
        del token_secret_ref
        raise CalendarProviderUnavailableError


def build_calendar_provider() -> CalendarProviderPort:
    return UnavailableCalendarProvider()


__all__ = ["UnavailableCalendarProvider", "build_calendar_provider"]
