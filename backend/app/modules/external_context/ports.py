from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID

from backend.app.domain.rules.external_context import (
    CalendarPerformanceObservation,
    ProviderBusyInterval,
)


class CalendarProviderUnavailableError(Exception):
    """The optional provider cannot serve the request; no provider payload is exposed."""


class CalendarProviderPermissionDeniedError(Exception):
    """The user denied or revoked the required calendar permission."""


@dataclass(frozen=True, slots=True)
class CalendarEventCreate:
    scheduled_workout_id: UUID
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

    def get_performance(
        self,
        *,
        scheduled_workout_id: UUID,
        external_event_id: str,
        checked_at: datetime,
    ) -> CalendarPerformanceObservation: ...


__all__ = [
    "CalendarEventCreate",
    "CalendarEventReference",
    "CalendarProviderPermissionDeniedError",
    "CalendarProviderPort",
    "CalendarProviderUnavailableError",
]
