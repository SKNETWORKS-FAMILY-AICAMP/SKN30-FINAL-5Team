"""Ports for provider adapters that supply normalized calendar context."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from backend.app.domain.rules.external_context import (
    CalendarBusyInterval,
    CalendarPerformanceObservation,
)


class CalendarProviderUnavailableError(Exception):
    """The calendar provider cannot serve the request now."""


class CalendarProviderPermissionDeniedError(Exception):
    """The user did not grant or has revoked the required calendar permission."""


@dataclass(frozen=True, slots=True)
class CalendarAvailabilityQuery:
    local_date: date
    timezone: str


@dataclass(frozen=True, slots=True)
class CalendarEventCreateCommand:
    scheduled_workout_id: UUID
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarCreatedEvent:
    external_event_id: str

    def __post_init__(self) -> None:
        if not 5 <= len(self.external_event_id) <= 1024:
            raise ValueError("external_event_id must contain between 5 and 1024 characters")


class CalendarProviderPort(Protocol):
    def fetch_busy_intervals(
        self,
        query: CalendarAvailabilityQuery,
    ) -> tuple[CalendarBusyInterval, ...]: ...

    def create_app_event(self, command: CalendarEventCreateCommand) -> CalendarCreatedEvent: ...

    def check_performance(
        self,
        *,
        scheduled_workout_id: UUID,
        checked_at: datetime,
    ) -> CalendarPerformanceObservation: ...


__all__ = [
    "CalendarAvailabilityQuery",
    "CalendarCreatedEvent",
    "CalendarEventCreateCommand",
    "CalendarProviderPermissionDeniedError",
    "CalendarProviderPort",
    "CalendarProviderUnavailableError",
]
