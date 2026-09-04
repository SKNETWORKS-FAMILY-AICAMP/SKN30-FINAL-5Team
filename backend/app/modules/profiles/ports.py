from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.profiles.codes import ConsentTypeCode, MutationEndpointCode


class BirthdateEncryptionError(Exception):
    """A birthdate could not be encrypted without exposing sensitive context."""


class BirthdateDecryptionError(Exception):
    """A protected birthdate could not be authenticated or decrypted."""


class BirthdateCipher(Protocol):
    def encrypt(self, user_id: UUID, birthdate: date) -> str: ...

    def decrypt(self, user_id: UUID, protected_value: str) -> date: ...


@dataclass(frozen=True)
class OnboardingProfileValues:
    nickname: str
    primary_goal_code: str
    experience_level_code: str
    timezone: str
    preferred_location_code: str
    available_location_codes: tuple[str, ...]
    default_requested_duration_minutes: int
    desired_weekly_workout_count: int
    coaching_style_code: str
    height_cm: float | None
    weight_kg: float | None
    sex_code: str | None
    attention_area_codes: tuple[str, ...]
    preferred_exercise_type_codes: tuple[str, ...]
    medical_exercise_restriction: bool
    eligibility_result_code: str
    weekly_target_sessions: int


@dataclass(frozen=True)
class OnboardingRecord:
    user_id: UUID
    profile_version: int
    coaching_style_code: str
    ai_trial_started_at: datetime
    ai_trial_ends_at: datetime
    premium_status_code: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MeProfileRecord:
    """Stored profile values needed to describe the authenticated user.

    `protected_birthdate` stays encrypted here; only the derived age leaves the
    service layer and the birthdate itself is never part of a response.
    """

    nickname: str
    protected_birthdate: str
    primary_goal_code: str
    experience_level_code: str
    timezone: str
    preferred_location_code: str
    available_location_codes: tuple[str, ...]
    default_requested_duration_minutes: int
    desired_weekly_workout_count: int
    coaching_style_code: str
    attention_area_codes: tuple[str, ...]
    preferred_exercise_type_codes: tuple[str, ...]
    profile_version: int
    created_at: datetime
    updated_at: datetime
    profile_image_object_key: str | None = None


@dataclass(frozen=True)
class MeRecord:
    user_id: UUID
    status_code: str
    premium_status_code: str
    ai_trial_started_at: datetime
    ai_trial_ends_at: datetime
    profile: MeProfileRecord | None = None
    banana_balance: int = 0


@dataclass(frozen=True)
class ConsentRecord:
    consent_type_code: ConsentTypeCode
    granted: bool
    policy_version: str
    updated_at: datetime


@dataclass(frozen=True)
class IdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


@dataclass(frozen=True)
class ProfileSettingsRecord:
    protected_birthdate: str
    nickname: str
    primary_goal_code: str
    experience_level_code: str
    timezone: str
    preferred_location_code: str
    available_location_codes: tuple[str, ...]
    default_requested_duration_minutes: int
    desired_weekly_workout_count: int
    coaching_style_code: str
    height_cm: float | None
    weight_kg: float | None
    sex_code: str | None
    attention_area_codes: tuple[str, ...]
    preferred_exercise_type_codes: tuple[str, ...]
    profile_version: int


@dataclass(frozen=True)
class ProfileSettingsChanges:
    protected_birthdate: str | None
    scalar_values: dict[str, object]
    available_location_codes: tuple[str, ...] | None
    attention_area_codes: tuple[str, ...] | None
    preferred_exercise_type_codes: tuple[str, ...] | None
    persistent_pains: tuple[tuple[str, int], ...] | None


@dataclass(frozen=True)
class ProfileImageRecord:
    object_key: str | None
    profile_version: int
    updated_at: datetime | None = None


class ProfileImageUrlProvider(Protocol):
    def create_url(self, object_key: str) -> str | None: ...


class StaleRoutinePort(Protocol):
    """Retires routines a profile edit has made unreachable.

    The profile default is the target a base routine is built to. When the user
    changes it, the stored routine keeps the old target and every daily decision
    then rejects it as CANDIDATE_DURATION_MISMATCH, leaving the user in a
    permanent REST loop with no way out from the UI.

    Archiving rather than rebuilding keeps this inside the profile transaction:
    a rebuild depends on catalog availability and can legitimately fail, and a
    profile edit must not fail because today's approved pool cannot fill the new
    duration. The client already offers routine creation when none is active.
    """

    def archive_routines_with_other_duration(
        self,
        session: Session,
        user_id: UUID,
        *,
        requested_duration_minutes: int,
    ) -> int: ...


class ProfileRepositoryPort(Protocol):
    def get_me(self, session: Session, user_id: UUID) -> MeRecord | None: ...

    def get_profile_image_for_update(
        self, session: Session, user_id: UUID
    ) -> ProfileImageRecord | None: ...

    def update_profile_image(
        self,
        session: Session,
        user_id: UUID,
        *,
        object_key: str | None,
        content_type: str | None,
        byte_size: int | None,
        now: datetime,
    ) -> tuple[int, datetime]: ...

    def acquire_idempotency_lock(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
    ) -> None: ...

    def get_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
    ) -> IdempotencyRecord | None: ...

    def save_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        response_schema_version: str,
        now: datetime,
    ) -> None: ...

    def upsert_profile(
        self,
        session: Session,
        user_id: UUID,
        protected_birthdate: str,
        values: OnboardingProfileValues,
        now: datetime,
    ) -> OnboardingRecord: ...

    def get_profile_for_update(
        self, session: Session, user_id: UUID
    ) -> ProfileSettingsRecord | None: ...

    def update_profile_settings(
        self,
        session: Session,
        user_id: UUID,
        changes: ProfileSettingsChanges,
        now: datetime,
    ) -> tuple[int, datetime]: ...

    def get_consents(self, session: Session, user_id: UUID) -> tuple[ConsentRecord, ...]: ...
    def replace_consents(
        self,
        session: Session,
        user_id: UUID,
        values: dict[ConsentTypeCode, bool],
        policy_version: str,
        now: datetime,
    ) -> tuple[ConsentRecord, ...]: ...

    def record_terms_agreement(
        self, session: Session, user_id: UUID, terms_version: str, now: datetime
    ) -> None: ...

    def replace_persistent_pains(
        self,
        session: Session,
        user_id: UUID,
        pains: tuple[tuple[str, int], ...],
        now: datetime,
    ) -> None: ...

    def disable_user_for_age(self, session: Session, user_id: UUID, now: datetime) -> None: ...


__all__ = [
    "BirthdateCipher",
    "BirthdateDecryptionError",
    "BirthdateEncryptionError",
    "ConsentRecord",
    "IdempotencyRecord",
    "MeProfileRecord",
    "MeRecord",
    "OnboardingProfileValues",
    "OnboardingRecord",
    "ProfileSettingsChanges",
    "ProfileSettingsRecord",
    "ProfileRepositoryPort",
]
