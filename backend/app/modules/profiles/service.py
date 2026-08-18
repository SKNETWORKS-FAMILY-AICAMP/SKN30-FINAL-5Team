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
    calculate_age,
    evaluate_age_eligibility,
)
from backend.app.modules.profiles.codes import (
    CONSENT_RESPONSE_SCHEMA_VERSION,
    ONBOARDING_RESPONSE_SCHEMA_VERSION,
    PROFILE_SETTINGS_RESPONSE_SCHEMA_VERSION,
    CoachingStyleCode,
    MutationEndpointCode,
)
from backend.app.modules.profiles.ports import (
    BirthdateCipher,
    BirthdateDecryptionError,
    BirthdateEncryptionError,
    MeProfileRecord,
    OnboardingProfileValues,
    ProfileRepositoryPort,
    ProfileSettingsChanges,
    ProfileSettingsRecord,
)
from backend.app.modules.profiles.schemas import (
    ConsentResponse,
    ConsentState,
    ConsentValues,
    MeProfile,
    MeResponse,
    OnboardingResponse,
    OnboardingUpsertRequest,
    ProfileSettingsUpdateRequest,
    ProfileSettingsUpdateResponse,
)


class ProfileConfigurationError(Exception):
    """Approved onboarding configuration or encryption is unavailable."""


class InvalidOnboardingCodeError(Exception):
    """An onboarding code is not in the approved deployment code set."""


class RequiredConsentMissingError(Exception):
    """An onboarding request omitted an approved required consent."""


class IdempotencyKeyReusedError(Exception):
    """An idempotency key was reused with a different request body."""


class UserNotFoundError(Exception):
    """No internal user is linked to the authenticated principal."""


class ProfileNotFoundError(Exception):
    """The authenticated user has not completed onboarding."""


class StaleProfileError(Exception):
    """The expected profile version no longer matches the stored version."""


class InvalidProfileSettingsError(Exception):
    """The merged profile settings violate a cross-field invariant."""


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
        response_type: (
            type[OnboardingResponse] | type[ConsentResponse] | type[ProfileSettingsUpdateResponse]
        ),
    ) -> OnboardingResponse | ConsentResponse | ProfileSettingsUpdateResponse | None:
        existing = self._repository.get_idempotency_record(
            session, user_id, endpoint_code, idempotency_key
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        return response_type.model_validate(existing.response_payload)

    def _require_profile_settings_configuration(self) -> None:
        if not self._primary_goal_codes or not self._experience_level_codes:
            raise ProfileConfigurationError

    def _validate_profile_codes(self, request: ProfileSettingsUpdateRequest) -> None:
        if (
            "primary_goal_code" in request.model_fields_set
            and request.primary_goal_code not in self._primary_goal_codes
        ):
            raise InvalidOnboardingCodeError
        if (
            "experience_level_code" in request.model_fields_set
            and request.experience_level_code not in self._experience_level_codes
        ):
            raise InvalidOnboardingCodeError

    def _protected_birthdate_for_update(
        self,
        user_id: UUID,
        request: ProfileSettingsUpdateRequest,
        current: ProfileSettingsRecord,
        now: datetime,
    ) -> str | None:
        changes_age_inputs = bool(
            {"date_of_birth", "timezone"}.intersection(request.model_fields_set)
        )
        if not changes_age_inputs:
            return None
        if self._birthdate_cipher is None:
            raise ProfileConfigurationError

        if "date_of_birth" in request.model_fields_set:
            birthdate = request.date_of_birth
            assert birthdate is not None
        else:
            try:
                birthdate = self._birthdate_cipher.decrypt(user_id, current.protected_birthdate)
            except BirthdateDecryptionError:
                raise ProfileConfigurationError from None
        timezone_name = (
            request.timezone if "timezone" in request.model_fields_set else current.timezone
        )
        assert timezone_name is not None
        evaluate_age_eligibility(birthdate, timezone_name, at=now)

        if "date_of_birth" not in request.model_fields_set:
            return None
        try:
            return self._birthdate_cipher.encrypt(user_id, birthdate)
        except BirthdateEncryptionError:
            raise ProfileConfigurationError from None

    @staticmethod
    def _profile_settings_changes(
        request: ProfileSettingsUpdateRequest,
        current: ProfileSettingsRecord,
        protected_birthdate: str | None,
    ) -> ProfileSettingsChanges:
        payload = request.model_dump(mode="json", exclude_unset=True)
        preferred_location = str(
            payload.get("preferred_location_code", current.preferred_location_code)
        )
        available_locations = tuple(
            str(code)
            for code in payload.get("available_location_codes", current.available_location_codes)
        )
        if preferred_location not in available_locations:
            raise InvalidProfileSettingsError
        equipment_codes = tuple(
            str(code) for code in payload.get("equipment_codes", current.equipment_codes)
        )
        if not equipment_codes:
            raise InvalidProfileSettingsError

        relationship_fields = {
            "available_location_codes",
            "equipment_codes",
            "attention_area_codes",
            "preferred_exercise_type_codes",
        }
        scalar_values = {
            field_name: value
            for field_name, value in payload.items()
            if field_name not in relationship_fields and field_name != "date_of_birth"
        }
        return ProfileSettingsChanges(
            protected_birthdate=protected_birthdate,
            scalar_values=scalar_values,
            available_location_codes=(
                available_locations
                if "available_location_codes" in request.model_fields_set
                else None
            ),
            equipment_codes=(
                equipment_codes if "equipment_codes" in request.model_fields_set else None
            ),
            attention_area_codes=(
                tuple(str(code) for code in payload["attention_area_codes"])
                if "attention_area_codes" in request.model_fields_set
                else None
            ),
            preferred_exercise_type_codes=(
                tuple(str(code) for code in payload["preferred_exercise_type_codes"])
                if "preferred_exercise_type_codes" in request.model_fields_set
                else None
            ),
        )

    def get_me(self, session: Session, user_id: UUID) -> MeResponse:
        record = self._repository.get_me(session, user_id)
        if record is None:
            raise UserNotFoundError

        profile = None
        if record.profile is not None:
            profile = MeProfile(
                nickname=record.profile.nickname,
                age=self._derive_age(user_id, record.profile),
                primary_goal_code=record.profile.primary_goal_code,
                experience_level_code=record.profile.experience_level_code,
                timezone=record.profile.timezone,
                preferred_location_code=record.profile.preferred_location_code,
                available_location_codes=list(record.profile.available_location_codes),
                default_requested_duration_minutes=(
                    record.profile.default_requested_duration_minutes
                ),
                desired_weekly_workout_count=record.profile.desired_weekly_workout_count,
                coaching_style_code=CoachingStyleCode(record.profile.coaching_style_code),
                equipment_codes=list(record.profile.equipment_codes),
                attention_area_codes=list(record.profile.attention_area_codes),
                preferred_exercise_type_codes=list(record.profile.preferred_exercise_type_codes),
                profile_version=record.profile.profile_version,
                created_at=record.profile.created_at,
                updated_at=record.profile.updated_at,
            )
        return MeResponse(
            user_id=record.user_id,
            status_code=record.status_code,
            onboarding_completed=record.profile is not None,
            premium_status_code=record.premium_status_code,
            ai_trial_started_at=record.ai_trial_started_at,
            ai_trial_ends_at=record.ai_trial_ends_at,
            profile=profile,
        )

    def _derive_age(self, user_id: UUID, profile: MeProfileRecord) -> int | None:
        """Derive the age, returning null rather than failing the read.

        A deployment without a birthdate cipher, or a value this deployment
        cannot authenticate, must still be able to serve the profile.
        """
        if self._birthdate_cipher is None:
            return None
        try:
            birthdate = self._birthdate_cipher.decrypt(user_id, profile.protected_birthdate)
            return calculate_age(birthdate, profile.timezone, at=self._clock())
        except (
            BirthdateDecryptionError,
            InvalidBirthdateError,
            InvalidTimezoneError,
        ):
            return None

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

    def update_profile_settings(
        self,
        session: Session,
        user_id: UUID,
        request: ProfileSettingsUpdateRequest,
        idempotency_key: UUID,
        expected_version: int,
    ) -> ProfileSettingsUpdateResponse:
        request_payload = request.model_dump(mode="json", exclude_unset=True)
        request_hash = _request_hash(
            {"payload": request_payload, "expected_profile_version": expected_version}
        )
        now = self._clock()

        try:
            with session.begin():
                self._repository.acquire_idempotency_lock(
                    session,
                    user_id,
                    MutationEndpointCode.PROFILE_SETTINGS,
                    idempotency_key,
                )
                existing = self._existing_response(
                    session,
                    user_id,
                    MutationEndpointCode.PROFILE_SETTINGS,
                    idempotency_key,
                    request_hash,
                    ProfileSettingsUpdateResponse,
                )
                if existing is not None:
                    assert isinstance(existing, ProfileSettingsUpdateResponse)
                    return existing

                current = self._repository.get_profile_for_update(session, user_id)
                if current is None:
                    raise ProfileNotFoundError
                if current.profile_version != expected_version:
                    raise StaleProfileError

                self._require_profile_settings_configuration()
                self._validate_profile_codes(request)
                protected_birthdate = self._protected_birthdate_for_update(
                    user_id, request, current, now
                )
                changes = self._profile_settings_changes(request, current, protected_birthdate)
                profile_version, updated_at = self._repository.update_profile_settings(
                    session, user_id, changes, now
                )
                response = ProfileSettingsUpdateResponse(
                    profile_version=profile_version,
                    updated_at=updated_at,
                )
                self._repository.save_idempotency_record(
                    session,
                    user_id,
                    MutationEndpointCode.PROFILE_SETTINGS,
                    idempotency_key,
                    request_hash,
                    response.model_dump(mode="json"),
                    PROFILE_SETTINGS_RESPONSE_SCHEMA_VERSION,
                    now,
                )
            return response
        except AgeRequirementNotMetError:
            with session.begin():
                self._repository.disable_user_for_age(session, user_id, now)
            raise


__all__ = [
    "IdempotencyKeyReusedError",
    "InvalidBirthdateError",
    "InvalidOnboardingCodeError",
    "InvalidProfileSettingsError",
    "InvalidTimezoneError",
    "ProfileConfigurationError",
    "ProfileNotFoundError",
    "ProfileService",
    "RequiredConsentMissingError",
    "StaleProfileError",
    "UserNotFoundError",
]
