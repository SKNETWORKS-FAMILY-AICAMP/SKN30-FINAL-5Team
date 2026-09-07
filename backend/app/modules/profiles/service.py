import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.catalog.codes import DEFAULT_LOCATION_CODE
from backend.app.modules.profiles.age import (
    AgeRequirementNotMetError,
    InvalidBirthdateError,
    InvalidTimezoneError,
    calculate_age,
    evaluate_age_eligibility,
)
from backend.app.modules.profiles.codes import (
    CONSENT_RESPONSE_SCHEMA_VERSION,
    FIXED_COACHING_STYLE_CODE,
    ONBOARDING_RESPONSE_SCHEMA_VERSION,
    PROFILE_SETTINGS_RESPONSE_SCHEMA_VERSION,
    EligibilityResultCode,
    MutationEndpointCode,
)
from backend.app.modules.profiles.legal import (
    validate_submitted_terms_version,
)
from backend.app.modules.profiles.ports import (
    BirthdateCipher,
    BirthdateDecryptionError,
    BirthdateEncryptionError,
    MeProfileRecord,
    OnboardingProfileValues,
    ProfileImageUrlProvider,
    ProfileRepositoryPort,
    ProfileSettingsChanges,
    ProfileSettingsRecord,
    StaleRoutinePort,
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


class MedicalExerciseRestrictionError(Exception):
    """The user needs individual medical exercise management outside this MVP."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


# Settings fields the API still accepts but no longer applies. A deployed client
# that sends one gets a successful no-op for that field rather than a 422. There is
# no longer a column behind any of them: migrations 0049 and 0050 dropped the
# storage once a full release had gone by without a writer.
#
# `coaching_style_code`: every user shares one narration context.
# The rest: ADR-0017 stopped collecting sex, height and workout location. Location
# is now a Daily Check-in input, so the profile is no longer its source of truth.
_IGNORED_SETTINGS_FIELDS = frozenset(
    {
        "coaching_style_code",
        "preferred_location_code",
        "available_location_codes",
        "height_cm",
        "sex_code",
    }
)


class ProfileService:
    def __init__(
        self,
        repository: ProfileRepositoryPort,
        birthdate_cipher: BirthdateCipher | None,
        *,
        primary_goal_codes: tuple[str, ...],
        experience_level_codes: tuple[str, ...],
        consent_policy_version: str | None,
        terms_version: str | None = None,
        stale_routines: StaleRoutinePort | None = None,
        profile_image_url_provider: ProfileImageUrlProvider | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._stale_routines = stale_routines
        self._birthdate_cipher = birthdate_cipher
        self._primary_goal_codes = frozenset(primary_goal_codes)
        self._experience_level_codes = frozenset(experience_level_codes)
        self._consent_policy_version = consent_policy_version
        self._terms_version = terms_version
        self._clock = clock
        self._profile_image_url_provider = profile_image_url_provider

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
        protected_birthdate: str | None,
    ) -> ProfileSettingsChanges:
        # Ignored fields are dropped before anything reads the payload, so a
        # deployed client that still sends them cannot trip a cross-field rule
        # over values the service is not going to apply.
        payload = {
            field_name: value
            for field_name, value in request.model_dump(mode="json", exclude_unset=True).items()
            if field_name not in _IGNORED_SETTINGS_FIELDS
        }
        relationship_fields = {
            "attention_area_codes",
            "preferred_exercise_type_codes",
            "persistent_pains",
        }
        scalar_values = {
            field_name: value
            for field_name, value in payload.items()
            if field_name not in relationship_fields and field_name != "date_of_birth"
        }
        return ProfileSettingsChanges(
            protected_birthdate=protected_birthdate,
            scalar_values=scalar_values,
            attention_area_codes=(
                tuple(str(code) for code in payload["attention_area_codes"])
                if "attention_area_codes" in payload
                else None
            ),
            preferred_exercise_type_codes=(
                tuple(str(code) for code in payload["preferred_exercise_type_codes"])
                if "preferred_exercise_type_codes" in payload
                else None
            ),
            persistent_pains=(
                tuple(
                    (str(item.body_area_code), item.intensity_score)
                    for item in request.persistent_pains or []
                )
                if "persistent_pains" in payload
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
                profile_image_url=(
                    self._profile_image_url_provider.create_url(
                        record.profile.profile_image_object_key
                    )
                    if self._profile_image_url_provider is not None
                    and record.profile.profile_image_object_key is not None
                    else None
                ),
                age=self._derive_age(user_id, record.profile),
                primary_goal_code=record.profile.primary_goal_code,
                experience_level_code=record.profile.experience_level_code,
                timezone=record.profile.timezone,
                # Retired response fields. Nothing stores a location, a style, a sex
                # or a height any more, but a deployed client still reads the first
                # three off this object, so they report the fixed values the service
                # applies instead of disappearing mid-release. FE-5 and FE-8 remove
                # the last readers; the fields go with the release after that.
                preferred_location_code=DEFAULT_LOCATION_CODE.value,
                available_location_codes=[DEFAULT_LOCATION_CODE.value],
                default_requested_duration_minutes=(
                    record.profile.default_requested_duration_minutes
                ),
                desired_weekly_workout_count=record.profile.desired_weekly_workout_count,
                coaching_style_code=FIXED_COACHING_STYLE_CODE,
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
            banana_balance=record.banana_balance,
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
        self.ensure_age_eligible(session, user_id, request)
        with session.begin():
            return self.upsert_onboarding_in_transaction(session, user_id, request, idempotency_key)

    def ensure_age_eligible(
        self,
        session: Session,
        user_id: UUID,
        request: OnboardingUpsertRequest,
    ) -> None:
        """Validate the new-onboarding age scope without changing account status."""

        evaluate_age_eligibility(request.date_of_birth, request.timezone, at=self._clock())

    def upsert_onboarding_in_transaction(
        self,
        session: Session,
        user_id: UUID,
        request: OnboardingUpsertRequest,
        idempotency_key: UUID,
    ) -> OnboardingResponse:
        """Store onboarding with a transaction owned by an application flow."""

        cipher, consent_policy_version = self._require_onboarding_configuration()
        request_hash = _request_hash(request.model_dump(mode="json"))

        now = self._clock()

        if request.primary_goal_code not in self._primary_goal_codes:
            raise InvalidOnboardingCodeError
        if request.experience_level_code not in self._experience_level_codes:
            raise InvalidOnboardingCodeError
        if not request.consents.general_personal_data or not request.consents.sensitive_data:
            raise RequiredConsentMissingError
        # The deployment decides which revision users accept. Until one is
        # approved this is a no-op, so the setting can ship without a
        # coordinated client release.
        validate_submitted_terms_version(request.terms_version, approved=self._terms_version)
        if request.medical_exercise_restriction:
            raise MedicalExerciseRestrictionError

        try:
            protected_birthdate = cipher.encrypt(user_id, request.date_of_birth)
        except BirthdateEncryptionError:
            raise ProfileConfigurationError from None

        weekly_target_sessions = (
            request.weekly_target_sessions or request.desired_weekly_workout_count
        )
        assert weekly_target_sessions is not None
        profile_values = OnboardingProfileValues(
            nickname=request.nickname,
            primary_goal_code=request.primary_goal_code,
            experience_level_code=request.experience_level_code,
            timezone=request.timezone,
            # The request still carries a location, a coaching style, a sex and a
            # height for write compatibility. None of them is stored: ADR-0017 and
            # the single-style decision removed the columns behind them.
            default_requested_duration_minutes=request.default_requested_duration_minutes,
            desired_weekly_workout_count=weekly_target_sessions,
            weight_kg=request.weight_kg,
            attention_area_codes=tuple(request.attention_area_codes),
            preferred_exercise_type_codes=tuple(request.preferred_exercise_type_codes),
            medical_exercise_restriction=request.medical_exercise_restriction,
            eligibility_result_code=EligibilityResultCode.ELIGIBLE,
            weekly_target_sessions=weekly_target_sessions,
        )

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
        self._repository.record_terms_agreement(session, user_id, request.terms_version, now)
        self._repository.replace_persistent_pains(
            session,
            user_id,
            tuple(
                (str(item.body_area_code), item.intensity_score)
                for item in request.persistent_pains
            ),
            now,
        )
        response = OnboardingResponse(
            user_id=record.user_id,
            onboarding_completed=True,
            profile_version=record.profile_version,
            coaching_style_code=FIXED_COACHING_STYLE_CODE,
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

    def get_consents(self, session: Session, user_id: UUID) -> ConsentResponse:
        """Read the stored consent states; onboarding is the only writer of the
        required pair, so an empty result simply means onboarding has not run."""

        records = self._repository.get_consents(session, user_id)
        return ConsentResponse(
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
                changes = self._profile_settings_changes(request, protected_birthdate)
                profile_version, updated_at = self._repository.update_profile_settings(
                    session, user_id, changes, now
                )
                # A routine is built to the profile default. Leaving one behind
                # that targets the old duration makes every daily decision reject
                # it and the user sees REST forever with no way out.
                new_duration = changes.scalar_values.get("default_requested_duration_minutes")
                if self._stale_routines is not None and isinstance(new_duration, int):
                    self._stale_routines.archive_routines_with_other_duration(
                        session,
                        user_id,
                        requested_duration_minutes=new_duration,
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
            # D3 does not yet define what to do with an existing profile that
            # becomes out of scope, so this endpoint must not disable it.
            raise


__all__ = [
    "IdempotencyKeyReusedError",
    "InvalidBirthdateError",
    "InvalidOnboardingCodeError",
    "MedicalExerciseRestrictionError",
    "InvalidTimezoneError",
    "ProfileConfigurationError",
    "ProfileNotFoundError",
    "ProfileService",
    "RequiredConsentMissingError",
    "StaleProfileError",
    "UserNotFoundError",
]
