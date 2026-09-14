from datetime import date, datetime
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.modules.catalog.codes import (
    BodyAreaCode,
    LocationCode,
    TrainingTypeCode,
)
from backend.app.modules.profiles.codes import (
    FIXED_COACHING_STYLE_CODE,
    CoachingStyleCode,
    ConsentTypeCode,
)

# Consent request fields for features the service no longer offers. Kept for
# write compatibility, never applied. See ADR-0016 (calendar) and ADR-0019
# (wearable); `ConsentTypeCode` keeps both codes so existing records stay readable.
RETIRED_CONSENT_FIELDS: Final = ("wearable_integration", "calendar_integration")


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
    # Retired features. The fields stay declared because this model forbids extra
    # keys, so removing them would turn a deployed client's request into a 422
    # instead of ignoring a value the service no longer acts on. Whatever arrives
    # is discarded and the consent is stored as not granted: there is nothing to
    # consent to. Calendar was retired by ADR-0016, wearable by ADR-0019.
    wearable_integration: bool = False
    calendar_integration: bool = False
    marketing: bool = False

    @model_validator(mode="after")
    def clear_retired_consents(self) -> "ConsentValues":
        for field_name in RETIRED_CONSENT_FIELDS:
            object.__setattr__(self, field_name, False)
        return self

    def by_type(self) -> dict[ConsentTypeCode, bool]:
        return {
            ConsentTypeCode.GENERAL_PERSONAL_DATA: self.general_personal_data,
            ConsentTypeCode.SENSITIVE_DATA: self.sensitive_data,
            ConsentTypeCode.WEARABLE_INTEGRATION: self.wearable_integration,
            ConsentTypeCode.CALENDAR_INTEGRATION: self.calendar_integration,
            ConsentTypeCode.MARKETING: self.marketing,
        }


class PersistentPainInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_area_code: BodyAreaCode
    intensity_score: int = Field(ge=1, le=10)


class OnboardingUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=1, max_length=64)
    date_of_birth: date
    medical_exercise_restriction: bool
    terms_version: str = Field(min_length=1, max_length=64)
    primary_goal_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    experience_level_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    timezone: str = Field(min_length=1, max_length=64)
    # Location and duration are selected by Daily Check-in after onboarding.
    # These two are accepted and discarded: migration 0050 dropped the columns
    # they used to reach. They stay declared because this model forbids extra
    # keys, so removing them would turn a deployed client's request into a 422.
    preferred_location_code: LocationCode = LocationCode.HOME
    available_location_codes: list[LocationCode] | None = None
    default_requested_duration_minutes: int = Field(default=30, gt=0, le=240)
    # The legacy name remains accepted while clients migrate to the P1-A
    # contract.  Supplying both values with different counts is ambiguous.
    desired_weekly_workout_count: int | None = Field(default=None, gt=0, le=7)
    weekly_target_sessions: int | None = Field(default=None, gt=0, le=7)
    attention_area_codes: list[BodyAreaCode] = Field(default_factory=list)
    preferred_exercise_type_codes: list[TrainingTypeCode] = Field(default_factory=list)
    # Legacy write-compatibility fields, accepted and discarded for the same
    # reason as the two above. `weight_kg` between them is not legacy: it is a
    # required onboarding input and the calorie estimate reads it.
    coaching_style_code: CoachingStyleCode = FIXED_COACHING_STYLE_CODE
    height_cm: float | None = Field(default=None, ge=80, le=250)
    weight_kg: float = Field(ge=25, le=300)
    sex_code: Literal["FEMALE", "MALE", "PREFER_NOT_TO_SAY"] | None = None
    consents: ConsentValues
    persistent_pains: list[PersistentPainInput] = Field(default_factory=list)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("nickname must not be blank")
        return normalized

    @field_validator(
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

    @field_validator("persistent_pains")
    @classmethod
    def reject_duplicate_persistent_pain_areas(
        cls, value: list[PersistentPainInput]
    ) -> list[PersistentPainInput]:
        if len(value) != len({item.body_area_code for item in value}):
            raise ValueError("persistent pain areas must not contain duplicates")
        return value

    @model_validator(mode="after")
    def require_one_weekly_target(self) -> "OnboardingUpsertRequest":
        legacy = self.desired_weekly_workout_count
        current = self.weekly_target_sessions
        if legacy is None and current is None:
            raise ValueError("weekly target sessions is required")
        if legacy is not None and current is not None and legacy != current:
            raise ValueError("weekly target session fields must agree")
        return self


class OnboardingResponse(BaseModel):
    user_id: UUID
    onboarding_completed: bool
    profile_version: int
    # Retained for deployed clients and always FIXED_COACHING_STYLE_CODE; nothing
    # stores a per-user style since migration 0049.
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
    # Accepted and ignored, like the rest of the retired settings; see
    # `_IGNORED_SETTINGS_FIELDS` in the service and OnboardingUpsertRequest.
    preferred_location_code: LocationCode | None = None
    available_location_codes: list[LocationCode] | None = None
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
    persistent_pains: list[PersistentPainInput] | None = None

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "attention_area_codes",
        "preferred_exercise_type_codes",
        "available_location_codes",
    )
    @classmethod
    def reject_duplicate_codes(cls, value: list[object] | None) -> list[object] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("codes must not contain duplicates")
        return value

    @field_validator("persistent_pains")
    @classmethod
    def reject_duplicate_persistent_pain_areas(
        cls, value: list[PersistentPainInput] | None
    ) -> list[PersistentPainInput] | None:
        if value is not None and len(value) != len({item.body_area_code for item in value}):
            raise ValueError("persistent pain areas must not contain duplicates")
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


class ProfileImageMutationResponse(BaseModel):
    profile_image_url: str | None
    profile_version: int
    updated_at: datetime


class MeProfile(BaseModel):
    """Profile view of the authenticated user.

    `date_of_birth` and `age` are both derived per request from the protected
    birthdate, and both are null when the deployment cannot decrypt it: a profile
    read must not fail because a birthdate cipher is missing or a stored envelope
    cannot be authenticated.

    The birthdate is returned only here, to the authenticated owner of the
    profile, so the settings editor can show the value the user already stored.
    Every other prohibition in ADR-0005 stands unchanged: the birthdate and the
    derived age stay out of logs, analytics, LLM and agent inputs, and decision
    snapshots, and the encrypted envelope is never returned.

    `weight_kg` is stored for the calorie estimate and returned for the same
    reason as the birthdate: it is a value the user typed and must be able to see
    again. It is optional because a profile written before it was collected has
    none.

    `preferred_location_code`, `available_location_codes` and `coaching_style_code`
    are retired: nothing stores them since migrations 0049 and 0050. They stay in
    the response because deployed clients read them, and they report the fixed
    values the service applies. FE-5 and FE-8 remove the last readers.
    """

    nickname: str
    profile_image_url: str | None = None
    age: int | None = None
    date_of_birth: date | None = None
    weight_kg: float | None = None
    primary_goal_code: str
    experience_level_code: str
    timezone: str
    preferred_location_code: str
    available_location_codes: list[str]
    default_requested_duration_minutes: int
    desired_weekly_workout_count: int
    coaching_style_code: CoachingStyleCode
    attention_area_codes: list[str]
    # `null` identifies a profile that still has only legacy attention-area
    # rows. An empty list is the canonical, explicitly migrated "no pain"
    # value, so clients must not collapse the two states.
    persistent_pains: list[PersistentPainInput] | None = None
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
    banana_balance: int = 0
    profile: MeProfile | None = None


class ConsentState(BaseModel):
    consent_type_code: ConsentTypeCode
    granted: bool
    policy_version: str
    updated_at: datetime


class ConsentResponse(BaseModel):
    user_id: UUID
    consents: list[ConsentState]


class OnboardingRequirementsResponse(BaseModel):
    """What the client must show, and which revision it must submit.

    Retired consent types are absent by construction: the client renders this
    list, so a code that is not here cannot be presented.
    """

    terms_version: str
    consent_policy_version: str
    required_consent_type_codes: list[ConsentTypeCode]
    optional_consent_type_codes: list[ConsentTypeCode]


__all__ = [
    "RETIRED_CONSENT_FIELDS",
    "ConsentResponse",
    "ConsentState",
    "ConsentValues",
    "MeProfile",
    "MeResponse",
    "OnboardingRequirementsResponse",
    "OnboardingResponse",
    "OnboardingUpsertRequest",
    "PersistentPainInput",
    "ProfileSettingsUpdateRequest",
    "ProfileSettingsUpdateResponse",
    "ProfileImageMutationResponse",
]
