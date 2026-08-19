from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.modules.catalog.codes import (
    BodyAreaCode,
    EquipmentCode,
    LocationCode,
    TrainingTypeCode,
)
from backend.app.modules.profiles.codes import CoachingStyleCode, ConsentTypeCode


def _exclude_explicit_null_from_patch_schema(schema: dict[str, Any]) -> None:
    """Keep PATCH fields optional while documenting explicit null as invalid."""

    for property_schema in schema.get("properties", {}).values():
        variants = property_schema.get("anyOf")
        if not isinstance(variants, list):
            continue
        non_null_variants = [variant for variant in variants if variant.get("type") != "null"]
        if len(non_null_variants) != 1 or len(non_null_variants) == len(variants):
            continue
        title = property_schema.get("title")
        property_schema.clear()
        property_schema.update(non_null_variants[0])
        if title is not None:
            property_schema["title"] = title


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
    available_location_codes: list[LocationCode] | None = None
    default_requested_duration_minutes: int = Field(gt=0, le=240)
    desired_weekly_workout_count: int = Field(gt=0, le=7)
    equipment_codes: list[EquipmentCode] = Field(min_length=1)
    attention_area_codes: list[BodyAreaCode]
    preferred_exercise_type_codes: list[TrainingTypeCode] = Field(default_factory=list)
    coaching_style_code: CoachingStyleCode = CoachingStyleCode.SUPPORTIVE
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=25, le=300)
    sex_code: Literal["FEMALE", "MALE", "PREFER_NOT_TO_SAY"]
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
        "available_location_codes",
    )
    @classmethod
    def reject_duplicate_codes(cls, value: list[object] | None) -> list[object] | None:
        if value is None:
            return value
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


class ProfileSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_exclude_explicit_null_from_patch_schema,
    )

    primary_goal_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    desired_weekly_workout_count: int | None = Field(default=None, gt=0, le=7)
    default_requested_duration_minutes: int | None = Field(default=None, gt=0, le=240)
    preferred_location_code: LocationCode | None = None
    available_location_codes: list[LocationCode] | None = None
    equipment_codes: list[EquipmentCode] | None = Field(default=None, min_length=1)
    attention_area_codes: list[BodyAreaCode] | None = None
    preferred_exercise_type_codes: list[TrainingTypeCode] | None = None
    coaching_style_code: CoachingStyleCode | None = None
    experience_level_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    height_cm: float | None = Field(default=None, ge=80, le=250)
    weight_kg: float | None = Field(default=None, ge=25, le=300)
    sex_code: Literal["FEMALE", "MALE", "PREFER_NOT_TO_SAY"] | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    date_of_birth: date | None = None

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "equipment_codes",
        "attention_area_codes",
        "preferred_exercise_type_codes",
        "available_location_codes",
    )
    @classmethod
    def reject_duplicate_codes(cls, value: list[object] | None) -> list[object] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("codes must not contain duplicates")
        return value

    @model_validator(mode="after")
    def reject_empty_or_null_patch(self) -> "ProfileSettingsUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one profile setting is required")
        if any(getattr(self, field_name) is None for field_name in self.model_fields_set):
            raise ValueError("profile settings must not be null")
        return self


class ProfileSettingsUpdateResponse(BaseModel):
    profile_version: int
    updated_at: datetime


class MeProfile(BaseModel):
    """Profile view of the authenticated user.

    `age` is derived per request from the protected birthdate and is null when
    the deployment cannot decrypt it. The birthdate itself is never returned.
    """

    nickname: str
    age: int | None = None
    primary_goal_code: str
    experience_level_code: str
    timezone: str
    preferred_location_code: str
    available_location_codes: list[str]
    default_requested_duration_minutes: int
    desired_weekly_workout_count: int
    coaching_style_code: CoachingStyleCode
    equipment_codes: list[str]
    attention_area_codes: list[str]
    preferred_exercise_type_codes: list[str]
    profile_version: int
    created_at: datetime
    updated_at: datetime


class MeResponse(BaseModel):
    user_id: UUID
    status_code: str
    onboarding_completed: bool
    premium_status_code: str
    ai_trial_started_at: datetime
    ai_trial_ends_at: datetime
    profile: MeProfile | None = None


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
    "MeProfile",
    "MeResponse",
    "OnboardingResponse",
    "OnboardingUpsertRequest",
    "ProfileSettingsUpdateRequest",
    "ProfileSettingsUpdateResponse",
]
