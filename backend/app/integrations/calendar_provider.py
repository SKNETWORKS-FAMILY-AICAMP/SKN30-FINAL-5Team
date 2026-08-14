"""Unavailable and synthetic calendar adapters; no live provider calls belong here yet."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from backend.app.domain.rules.external_context import (
    CalendarBusyInterval,
    CalendarPerformanceObservation,
    google_calendar_performance_observation,
)
from backend.app.modules.external_context.ports import (
    CalendarAvailabilityQuery,
    CalendarCreatedEvent,
    CalendarEventCreateCommand,
    CalendarProviderPort,
    CalendarProviderUnavailableError,
)


class UnavailableCalendarProvider:
    def fetch_busy_intervals(
        self,
        query: CalendarAvailabilityQuery,
    ) -> tuple[CalendarBusyInterval, ...]:
        del query
        raise CalendarProviderUnavailableError

    def create_app_event(self, command: CalendarEventCreateCommand) -> CalendarCreatedEvent:
        del command
        raise CalendarProviderUnavailableError

    def check_performance(
        self,
        *,
        scheduled_workout_id: UUID,
        checked_at: datetime,
    ) -> CalendarPerformanceObservation:
        del scheduled_workout_id, checked_at
        raise CalendarProviderUnavailableError


@dataclass(frozen=True, slots=True)
class SyntheticCalendarProvider:
    """Synthetic contract adapter with no credential, event text, or provider payload fields."""

    busy_intervals: tuple[CalendarBusyInterval, ...] = ()
    created_event_id: str = "syntheticevent1"

    def fetch_busy_intervals(
        self,
        query: CalendarAvailabilityQuery,
    ) -> tuple[CalendarBusyInterval, ...]:
        del query
        return self.busy_intervals

    def create_app_event(self, command: CalendarEventCreateCommand) -> CalendarCreatedEvent:
        del command
        return CalendarCreatedEvent(external_event_id=self.created_event_id)

    def check_performance(
        self,
        *,
        scheduled_workout_id: UUID,
        checked_at: datetime,
    ) -> CalendarPerformanceObservation:
        return google_calendar_performance_observation(
            scheduled_workout_id=scheduled_workout_id,
            checked_at=checked_at,
        )


def build_calendar_provider(
    provider: CalendarProviderPort | None = None,
) -> CalendarProviderPort:
    if provider is None:
        return UnavailableCalendarProvider()
    return provider


__all__ = [
    "SyntheticCalendarProvider",
    "UnavailableCalendarProvider",
    "build_calendar_provider",
]
