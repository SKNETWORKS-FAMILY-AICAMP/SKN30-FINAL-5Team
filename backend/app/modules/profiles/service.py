import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.profiles.age import (
    AgeRequirementNotMetError,
    InvalidBirthdateError,
    InvalidTimezoneError,
    evaluate_age_eligibility,
)
from backend.app.modules.profiles.codes import (
    CONSENT_RESPONSE_SCHEMA_VERSION,
    ONBOARDING_RESPONSE_SCHEMA_VERSION,
    CoachingStyleCode,
    MutationEndpointCode,
)
from backend.app.modules.profiles.ports import (
    BirthdateCipher,
    BirthdateEncryptionError,
    OnboardingProfileValues,
    ProfileRepositoryPort,
)
from backend.app.modules.profiles.schemas import (
    ConsentResponse,
    ConsentState,
    ConsentValues,
    OnboardingResponse,
    OnboardingUpsertRequest,
)


class ProfileConfigurationError(Exception):
    """Approved onboarding configuration or encryption is unavailable."""


class InvalidOnboardingCodeError(Exception):
    """An onboarding code is not in the approved deployment code set."""


class RequiredConsentMissingError(Exception):
    """An onboarding request omitted an approved required consent."""


class IdempotencyKeyReusedError(Exception):
    """An idempotency key was reused with a different request body."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class ProfileService:
    def __init__(
        self,
        repository: ProfileRepositoryPort,
        birthdate_cipher: BirthdateCipher | None,
        *,
        primary_goal_codes: tuple[str, ...],
        experience_level_codes: tuple[str, ...],
        consent_policy_version: str | None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._birthdate_cipher = birthdate_cipher
        self._primary_goal_codes = frozenset(primary_goal_codes)
        self._experience_level_codes = frozenset(experience_level_codes)
        self._consent_policy_version = consent_policy_version
        self._clock = clock

    def _require_onboarding_configuration(self) -> tuple[BirthdateCipher, str]:
        if (
            self._birthdate_cipher is None
            or not self._primary_goal_codes
            or not self._experience_level_codes
            or self._consent_policy_version is None
        ):
            raise ProfileConfigurationError
        return self._birthdate_cipher, self._consent_policy_version

    def _require_consent_policy_version(self) -> str:
        if self._consent_policy_version is None:
            raise ProfileConfigurationError
        return self._consent_policy_version

    def _existing_response(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
        request_hash: str,
        response_type: type[OnboardingResponse] | type[ConsentResponse],
    ) -> OnboardingResponse | ConsentResponse | None:
        existing = self._repository.get_idempotency_record(
            session, user_id, endpoint_code, idempotency_key
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        return response_type.model_validate(existing.response_payload)

    def upsert_onboarding(
        self,
        session: Session,
        user_id: UUID,
        request: OnboardingUpsertRequest,
        idempotency_key: UUID,
    ) -> OnboardingResponse:
        cipher, consent_policy_version = self._require_onboarding_configuration()
        request_hash = _request_hash(request.model_dump(mode="json"))

        now = self._clock()
        try:
            evaluate_age_eligibility(request.date_of_birth, request.timezone, at=now)
        except AgeRequirementNotMetError:
            with session.begin():
                self._repository.disable_user_for_age(session, user_id, now)
            raise

        if request.primary_goal_code not in self._primary_goal_codes:
            raise InvalidOnboardingCodeError
        if request.experience_level_code not in self._experience_level_codes:
            raise InvalidOnboardingCodeError
        if not request.consents.general_personal_data or not request.consents.sensitive_data:
            raise RequiredConsentMissingError

        try:
            protected_birthdate = cipher.encrypt(user_id, request.date_of_birth)
        except BirthdateEncryptionError:
            raise ProfileConfigurationError from None

        profile_values = OnboardingProfileValues(
            nickname=request.nickname,
            primary_goal_code=request.primary_goal_code,
            experience_level_code=request.experience_level_code,
            timezone=request.timezone,
            preferred_location_code=request.preferred_location_code,
            available_location_codes=tuple(
                request.available_location_codes or (request.preferred_location_code,)
            ),
            default_requested_duration_minutes=request.default_requested_duration_minutes,
            desired_weekly_workout_count=request.desired_weekly_workout_count,
            coaching_style_code=request.coaching_style_code,
            height_cm=request.height_cm,
            weight_kg=request.weight_kg,
            sex_code=request.sex_code,
            equipment_codes=tuple(request.equipment_codes),
            attention_area_codes=tuple(request.attention_area_codes),
            preferred_exercise_type_codes=tuple(request.preferred_exercise_type_codes),
        )

        with session.begin():
            self._repository.acquire_idempotency_lock(
                session,
                user_id,
                MutationEndpointCode.ONBOARDING,
                idempotency_key,
            )
            existing = self._existing_response(
                session,
                user_id,
                MutationEndpointCode.ONBOARDING,
                idempotency_key,
                request_hash,
                OnboardingResponse,
            )
            if existing is not None:
                assert isinstance(existing, OnboardingResponse)
                return existing
            record = self._repository.upsert_profile(
                session,
                user_id,
                protected_birthdate,
                profile_values,
                now,
            )
            self._repository.replace_consents(
                session,
                user_id,
                request.consents.by_type(),
                consent_policy_version,
                now,
            )
            response = OnboardingResponse(
                user_id=record.user_id,
                onboarding_completed=True,
                profile_version=record.profile_version,
                coaching_style_code=CoachingStyleCode(record.coaching_style_code),
                ai_trial_started_at=record.ai_trial_started_at,
                ai_trial_ends_at=record.ai_trial_ends_at,
                premium_status_code=record.premium_status_code,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            self._repository.save_idempotency_record(
                session,
                user_id,
                MutationEndpointCode.ONBOARDING,
                idempotency_key,
                request_hash,
                response.model_dump(mode="json"),
                ONBOARDING_RESPONSE_SCHEMA_VERSION,
                now,
            )
        return response

    def replace_consents(
        self,
        session: Session,
        user_id: UUID,
        request: ConsentValues,
        idempotency_key: UUID,
    ) -> ConsentResponse:
        consent_policy_version = self._require_consent_policy_version()
        request_hash = _request_hash(request.model_dump(mode="json"))
        now = self._clock()

        with session.begin():
            self._repository.acquire_idempotency_lock(
                session,
                user_id,
                MutationEndpointCode.CONSENTS,
                idempotency_key,
            )
            existing = self._existing_response(
                session,
                user_id,
                MutationEndpointCode.CONSENTS,
                idempotency_key,
                request_hash,
                ConsentResponse,
            )
            if existing is not None:
                assert isinstance(existing, ConsentResponse)
                return existing

            records = self._repository.replace_consents(
                session,
                user_id,
                request.by_type(),
                consent_policy_version,
                now,
            )
            response = ConsentResponse(
                user_id=user_id,
                consents=[
                    ConsentState(
                        consent_type_code=record.consent_type_code,
                        granted=record.granted,
                        policy_version=record.policy_version,
                        updated_at=record.updated_at,
                    )
                    for record in records
                ],
            )
            self._repository.save_idempotency_record(
                session,
                user_id,
                MutationEndpointCode.CONSENTS,
                idempotency_key,
                request_hash,
                response.model_dump(mode="json"),
                CONSENT_RESPONSE_SCHEMA_VERSION,
                now,
            )
        return response


__all__ = [
    "IdempotencyKeyReusedError",
    "InvalidBirthdateError",
    "InvalidOnboardingCodeError",
    "InvalidTimezoneError",
    "ProfileConfigurationError",
    "ProfileService",
    "RequiredConsentMissingError",
]
