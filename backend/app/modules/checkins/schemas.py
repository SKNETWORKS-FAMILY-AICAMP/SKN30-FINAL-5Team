from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    context_version: int
    created_at: datetime
    updated_at: datetime


__all__ = ["DailyContextResponse", "DailyContextUpsertRequest", "DiscomfortInput"]
