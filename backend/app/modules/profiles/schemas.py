from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.modules.catalog.codes import (
    BodyAreaCode,
    EquipmentCode,
    LocationCode,
    TrainingTypeCode,
)
from backend.app.modules.profiles.codes import CoachingStyleCode, ConsentTypeCode


class ConsentValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    general_personal_data: bool
    sensitive_data: bool
    wearable_integration: bool = False
    calendar_integration: bool = False
    marketing: bool = False

    def by_type(self) -> dict[ConsentTypeCode, bool]:
        return {
            ConsentTypeCode.GENERAL_PERSONAL_DATA: self.general_personal_data,
            ConsentTypeCode.SENSITIVE_DATA: self.sensitive_data,
            ConsentTypeCode.WEARABLE_INTEGRATION: self.wearable_integration,
            ConsentTypeCode.CALENDAR_INTEGRATION: self.calendar_integration,
            ConsentTypeCode.MARKETING: self.marketing,
        }


class OnboardingUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=1, max_length=64)
    date_of_birth: date
    primary_goal_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    experience_level_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    timezone: str = Field(min_length=1, max_length=64)
    preferred_location_code: LocationCode
    default_requested_duration_minutes: int = Field(gt=0, le=240)
    desired_weekly_workout_count: int = Field(gt=0, le=7)
    equipment_codes: list[EquipmentCode] = Field(min_length=1)
    attention_area_codes: list[BodyAreaCode] = Field(default_factory=list)
    preferred_exercise_type_codes: list[TrainingTypeCode] = Field(default_factory=list)
    coaching_style_code: CoachingStyleCode = CoachingStyleCode.SUPPORTIVE
    height_cm: float | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, gt=0)
    sex_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    consents: ConsentValues

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("nickname must not be blank")
        return normalized

    @field_validator(
        "equipment_codes",
        "attention_area_codes",
        "preferred_exercise_type_codes",
    )
    @classmethod
    def reject_duplicate_codes(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("codes must not contain duplicates")
        return value


class OnboardingResponse(BaseModel):
    user_id: UUID
    onboarding_completed: bool
    profile_version: int
    coaching_style_code: CoachingStyleCode
    ai_trial_started_at: datetime
    ai_trial_ends_at: datetime
    premium_status_code: str
    created_at: datetime
    updated_at: datetime


class ConsentState(BaseModel):
    consent_type_code: ConsentTypeCode
    granted: bool
    policy_version: str
    updated_at: datetime


class ConsentResponse(BaseModel):
    user_id: UUID
    consents: list[ConsentState]


__all__ = [
    "ConsentResponse",
    "ConsentState",
    "ConsentValues",
    "OnboardingResponse",
    "OnboardingUpsertRequest",
]
