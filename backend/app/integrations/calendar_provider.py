from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from backend.app.domain.rules.external_context import (
    CalendarPerformanceObservation,
    ProviderBusyInterval,
    google_calendar_performance_observation,
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


@dataclass(frozen=True, slots=True)
class SyntheticCalendarProvider:
    """Credential-free contract adapter for unit and golden tests."""

    busy_intervals: tuple[ProviderBusyInterval, ...] = ()
    external_event_id: str = "syntheticevent1"

    def get_busy_intervals(
        self,
        *,
        local_date: date,
        timezone_name: str,
    ) -> tuple[ProviderBusyInterval, ...]:
        del local_date, timezone_name
        return self.busy_intervals

    def create_workout_event(self, request: CalendarEventCreate) -> CalendarEventReference:
        del request
        return CalendarEventReference(self.external_event_id)

    def get_performance(
        self,
        *,
        scheduled_workout_id: UUID,
        external_event_id: str,
        checked_at: datetime,
    ) -> CalendarPerformanceObservation:
        del external_event_id
        return google_calendar_performance_observation(
            scheduled_workout_id=scheduled_workout_id,
            performance_checked_at=checked_at,
        )


def build_calendar_provider(
    provider: CalendarProviderPort | None = None,
) -> CalendarProviderPort:
    return provider if provider is not None else UnavailableCalendarProvider()


__all__ = ["SyntheticCalendarProvider", "UnavailableCalendarProvider", "build_calendar_provider"]
