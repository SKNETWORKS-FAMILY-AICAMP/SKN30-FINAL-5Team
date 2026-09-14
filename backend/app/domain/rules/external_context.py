"""Manual availability windows the user enters by hand.

ADR-0016 retired the external calendar integration. Everything this module used to
hold for that integration -- OAuth connection state, provider freebusy merging, rate
limit counters, event links and the observability field allowlist -- went with it.

What remains is the small contract for manually entered workout windows, which was
never part of the external integration. The module and enum keep their historical
names so `modules/checkins` does not have to change while it is being reworked; the
rename belongs to that rework, not to this removal.
"""

from __future__ import annotations

from enum import StrEnum

MAX_AVAILABILITY_SLOTS = 8


class CalendarAvailabilitySourceCode(StrEnum):
    """Where one availability window came from.

    `CALENDAR` was dropped with the integration. The database CHECK constraint on
    `daily_context_availability_slots.availability_source_code` already allowed only
    these two values, so no stored row referenced it.
    """

    MANUAL = "MANUAL"
    ROUTINE_DEFAULT = "ROUTINE_DEFAULT"
