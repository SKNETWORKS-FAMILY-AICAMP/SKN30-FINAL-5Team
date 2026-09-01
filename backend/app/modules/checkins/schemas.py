from datetime import date, datetime
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.app.domain.rules.external_context import (
    MAX_AVAILABILITY_SLOTS,
    CalendarAvailabilitySourceCode,
)
from backend.app.domain.rules.safety import AdverseReactionCode, BodyAreaCode
from backend.app.modules.catalog.codes import LocationCode
from backend.app.modules.checkins.codes import (
    DiscomfortSeverityCode,
    DurationAdjustmentSourceCode,
    FatigueLevelCode,
)


class DiscomfortInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_area_code: BodyAreaCode
    severity_code: DiscomfortSeverityCode


class AvailabilitySlotInput(BaseModel):
    """A workout window the user entered by hand. No calendar body text is accepted."""

    model_config = ConfigDict(extra="forbid")

    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def require_positive_range(self) -> "AvailabilitySlotInput":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


def _normalize_slots(value: list[AvailabilitySlotInput]) -> list[AvailabilitySlotInput]:
    """Sort by start time and reject overlapping or touching windows."""

    if len(value) > MAX_AVAILABILITY_SLOTS:
        raise ValueError(f"available_slots cannot exceed {MAX_AVAILABILITY_SLOTS} entries")
    ordered = sorted(value, key=lambda slot: slot.start_at)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.end_at >= current.start_at:
            raise ValueError("available_slots must not overlap or touch")
    return ordered


class DailyContextUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fatigue_level_code: FatigueLevelCode
    requested_duration_minutes: int = Field(gt=0, le=240)
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    location_code: LocationCode
    sleep_minutes: int | None = Field(default=None, ge=0, le=1440)
    fasting_state_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    hydration_state_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    discomforts: list[DiscomfortInput] = Field(default_factory=list)
    adverse_reaction_codes: list[AdverseReactionCode] = Field(default_factory=list)
    # None means the user did not answer; [] is an explicit "no time today" choice.
    # select_availability preserves that difference, so the two must not be merged.
    available_slots: list[AvailabilitySlotInput] | None = None

    @field_validator("available_slots")
    @classmethod
    def normalize_available_slots(
        cls, value: list[AvailabilitySlotInput] | None
    ) -> list[AvailabilitySlotInput] | None:
        return None if value is None else _normalize_slots(value)

    @field_validator("discomforts")
    @classmethod
    def reject_duplicate_body_areas(cls, value: list[DiscomfortInput]) -> list[DiscomfortInput]:
        codes = [item.body_area_code for item in value]
        if len(codes) != len(set(codes)):
            raise ValueError("body_area_code must not be duplicated")
        return value

    @field_validator("adverse_reaction_codes")
    @classmethod
    def reject_duplicate_reactions(
        cls, value: list[AdverseReactionCode]
    ) -> list[AdverseReactionCode]:
        if len(value) != len(set(value)):
            raise ValueError("adverse_reaction_codes must not contain duplicates")
        return value


class DailyContextResponse(BaseModel):
    id: UUID
    local_date: date
    fatigue_level_code: FatigueLevelCode
    requested_duration_minutes: int
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    location_code: LocationCode
    sleep_minutes: int | None
    fasting_state_code: str | None
    hydration_state_code: str | None
    discomforts: list[DiscomfortInput]
    adverse_reaction_codes: list[AdverseReactionCode]
    # Defaults keep idempotency payloads written before this field validate unchanged.
    available_slots: list[AvailabilitySlotInput] | None = None
    availability_source_code: CalendarAvailabilitySourceCode = (
        CalendarAvailabilitySourceCode.ROUTINE_DEFAULT
    )
    context_version: int
    created_at: datetime
    updated_at: datetime


__all__ = [
    "AvailabilitySlotInput",
    "DailyContextResponse",
    "DailyContextUpsertRequest",
    "DiscomfortInput",
]
