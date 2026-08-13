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
    equipment_codes: tuple[str, ...]
    attention_area_codes: tuple[str, ...]
    preferred_exercise_type_codes: tuple[str, ...]


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
class ConsentRecord:
    consent_type_code: ConsentTypeCode
    granted: bool
    policy_version: str
    updated_at: datetime


@dataclass(frozen=True)
class IdempotencyRecord:
    request_hash: str
    response_payload: dict[str, Any]


class ProfileRepositoryPort(Protocol):
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

    def replace_consents(
        self,
        session: Session,
        user_id: UUID,
        values: dict[ConsentTypeCode, bool],
        policy_version: str,
        now: datetime,
    ) -> tuple[ConsentRecord, ...]: ...

    def disable_user_for_age(self, session: Session, user_id: UUID, now: datetime) -> None: ...


__all__ = [
    "BirthdateCipher",
    "BirthdateDecryptionError",
    "BirthdateEncryptionError",
    "ConsentRecord",
    "IdempotencyRecord",
    "OnboardingProfileValues",
    "OnboardingRecord",
    "ProfileRepositoryPort",
]
