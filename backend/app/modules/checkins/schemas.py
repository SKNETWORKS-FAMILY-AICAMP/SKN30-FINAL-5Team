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
    DAILY_PAIN_POLICY_VERSION,
    DiscomfortSeverityCode,
    DurationAdjustmentSourceCode,
    FatigueLevelCode,
    SleepSourceCode,
)


class DiscomfortInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_area_code: BodyAreaCode
    severity_code: DiscomfortSeverityCode


class PainInput(BaseModel):
    """NRS 1–10 submitted for one daily body area."""

    model_config = ConfigDict(extra="forbid")

    body_area_code: BodyAreaCode
    intensity_score: int = Field(ge=1, le=10)

    @field_validator("body_area_code")
    @classmethod
    def reject_other(cls, value: BodyAreaCode) -> BodyAreaCode:
        if value is BodyAreaCode.OTHER:
            raise ValueError("OTHER body area must not be stored")
        return value


class DailyPainResponse(PainInput):
    severity_code: DiscomfortSeverityCode
    policy_version: str = DAILY_PAIN_POLICY_VERSION


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
    # Legacy duration fields remain readable by deployed clients during the
    # P1-B rollout. New writes use available_time_minutes as the daily target.
    requested_duration_minutes: int | None = Field(default=None, gt=0, le=240)
    duration_adjustment_source_code: DurationAdjustmentSourceCode = (
        DurationAdjustmentSourceCode.USER_OVERRIDE
    )
    location_code: LocationCode
    sleep_minutes: int | None = Field(default=None, ge=0, le=1440)
    sleep_source_code: SleepSourceCode | None = None
    available_time_minutes: int | None = Field(default=None, ge=10, le=60)
    pain_present: bool | None = None
    red_flag_present: bool = False
    fasting_state_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    hydration_state_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    discomforts: list[DiscomfortInput] = Field(default_factory=list)
    pains: list[PainInput] = Field(default_factory=list)
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

    @field_validator("pains")
    @classmethod
    def reject_duplicate_pain_body_areas(cls, value: list[PainInput]) -> list[PainInput]:
        codes = [item.body_area_code for item in value]
        if len(codes) != len(set(codes)):
            raise ValueError("pain body_area_code must not be duplicated")
        return value

    @field_validator("adverse_reaction_codes")
    @classmethod
    def reject_duplicate_reactions(
        cls, value: list[AdverseReactionCode]
    ) -> list[AdverseReactionCode]:
        if len(value) != len(set(value)):
            raise ValueError("adverse_reaction_codes must not contain duplicates")
        return value

    @model_validator(mode="after")
    def normalize_p1_b_contract(self) -> "DailyContextUpsertRequest":
        if self.available_time_minutes is None:
            if self.requested_duration_minutes is None:
                raise ValueError("available_time_minutes is required")
            if not 10 <= self.requested_duration_minutes <= 60:
                raise ValueError("legacy requested_duration_minutes must be between 10 and 60")
            self.available_time_minutes = self.requested_duration_minutes
        elif (
            self.requested_duration_minutes is not None
            and self.requested_duration_minutes != self.available_time_minutes
        ):
            raise ValueError("available_time_minutes and requested_duration_minutes must agree")
        if self.requested_duration_minutes is None:
            self.requested_duration_minutes = self.available_time_minutes
        if self.sleep_minutes is None and self.sleep_source_code is not None:
            raise ValueError("sleep_source_code requires sleep_minutes")
        if self.pains and self.discomforts:
            raise ValueError("pains and legacy discomforts cannot be combined")
        # Legacy request compatibility only: map the historical three levels to
        # the highest NRS score in each approved band before persistence.
        if self.discomforts:
            representative_scores = {"MILD": 3, "MODERATE": 6, "SEVERE": 10}
            self.pains = [
                PainInput(
                    body_area_code=item.body_area_code,
                    intensity_score=representative_scores[item.severity_code],
                )
                for item in self.discomforts
            ]
        derived_pain_present = bool(self.pains)
        if self.pain_present is not None and self.pain_present != derived_pain_present:
            raise ValueError("pain_present must match pains")
        self.pain_present = derived_pain_present
        return self


class DailyContextResponse(BaseModel):
    id: UUID
    local_date: date
    fatigue_level_code: FatigueLevelCode
    requested_duration_minutes: int
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    location_code: LocationCode
    sleep_minutes: int | None
    sleep_source_code: SleepSourceCode | None = None
    available_time_minutes: int | None = None
    pain_present: bool = False
    red_flag_present: bool = False
    fasting_state_code: str | None
    hydration_state_code: str | None
    discomforts: list[DiscomfortInput]
    pains: list[DailyPainResponse] = Field(default_factory=list)
    adverse_reaction_codes: list[AdverseReactionCode]
    # Defaults keep idempotency payloads written before this field validate unchanged.
    available_slots: list[AvailabilitySlotInput] | None = None
    availability_source_code: CalendarAvailabilitySourceCode = (
        CalendarAvailabilitySourceCode.ROUTINE_DEFAULT
    )
    context_version: int
    created_at: datetime
    updated_at: datetime


class DailyContextDefaultsResponse(BaseModel):
    """Editable daily check-in defaults; they are never Safety input by themselves."""

    local_date: date
    pains: list[PainInput] = Field(default_factory=list)


__all__ = [
    "AvailabilitySlotInput",
    "DailyContextResponse",
    "DailyContextDefaultsResponse",
    "DailyContextUpsertRequest",
    "DiscomfortInput",
    "DailyPainResponse",
    "PainInput",
]
