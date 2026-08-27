from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.identity import User
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAttentionArea,
    UserAvailableLocation,
    UserConsent,
    UserConsentEvent,
    UserPreferredExerciseType,
    UserProfile,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.profiles.codes import (
    PROFILE_CODE_SET_VERSION,
    ConsentEventCode,
    ConsentTypeCode,
    MutationEndpointCode,
)
from backend.app.modules.profiles.ports import (
    ConsentRecord,
    IdempotencyRecord,
    MeProfileRecord,
    MeRecord,
    OnboardingProfileValues,
    OnboardingRecord,
    ProfileSettingsChanges,
    ProfileSettingsRecord,
)


class ProfileRepository:
    def get_me(self, session: Session, user_id: UUID) -> MeRecord | None:
        user = session.get(User, user_id)
        if user is None:
            return None
        profile = session.get(UserProfile, user_id)
        profile_record = None
        if profile is not None:
            profile_record = MeProfileRecord(
                nickname=profile.nickname,
                protected_birthdate=profile.protected_birthdate,
                primary_goal_code=profile.primary_goal_code,
                experience_level_code=profile.experience_level_code,
                timezone=profile.timezone,
                preferred_location_code=profile.preferred_location_code,
                available_location_codes=tuple(
                    session.scalars(
                        select(UserAvailableLocation.location_code)
                        .where(UserAvailableLocation.user_id == user_id)
                        .order_by(UserAvailableLocation.location_code)
                    )
                ),
                default_requested_duration_minutes=profile.default_requested_duration_minutes,
                desired_weekly_workout_count=profile.desired_weekly_workout_count,
                coaching_style_code=profile.coaching_style_code,
                attention_area_codes=tuple(
                    session.scalars(
                        select(UserAttentionArea.body_area_code)
                        .where(
                            UserAttentionArea.user_id == user_id,
                            UserAttentionArea.is_active.is_(True),
                        )
                        .order_by(UserAttentionArea.body_area_code)
                    )
                ),
                preferred_exercise_type_codes=tuple(
                    session.scalars(
                        select(UserPreferredExerciseType.exercise_type_code)
                        .where(UserPreferredExerciseType.user_id == user_id)
                        .order_by(UserPreferredExerciseType.exercise_type_code)
                    )
                ),
                profile_version=profile.profile_version,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
        return MeRecord(
            user_id=user_id,
            status_code=user.status_code,
            premium_status_code=user.premium_status_code,
            ai_trial_started_at=user.ai_trial_started_at,
            ai_trial_ends_at=user.ai_trial_ends_at,
            profile=profile_record,
        )

    def acquire_idempotency_lock(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
    ) -> None:
        lock_input = f"{user_id}:{endpoint_code}:{idempotency_key}".encode()
        lock_key = int.from_bytes(sha256(lock_input).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def get_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
    ) -> IdempotencyRecord | None:
        row = session.scalar(
            select(MutationIdempotencyRecord).where(
                MutationIdempotencyRecord.user_id == user_id,
                MutationIdempotencyRecord.endpoint_code == endpoint_code,
                MutationIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        return IdempotencyRecord(
            request_hash=row.request_hash,
            response_payload=row.response_payload,
        )

    def save_idempotency_record(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, object],
        response_schema_version: str,
        now: datetime,
    ) -> None:
        session.add(
            MutationIdempotencyRecord(
                id=uuid4(),
                user_id=user_id,
                endpoint_code=endpoint_code,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_schema_version=response_schema_version,
                created_at=now,
            )
        )

    def upsert_profile(
        self,
        session: Session,
        user_id: UUID,
        protected_birthdate: str,
        values: OnboardingProfileValues,
        now: datetime,
    ) -> OnboardingRecord:
        profile = session.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                protected_birthdate=protected_birthdate,
                nickname=values.nickname,
                primary_goal_code=values.primary_goal_code,
                experience_level_code=values.experience_level_code,
                timezone=values.timezone,
                preferred_location_code=values.preferred_location_code,
                default_requested_duration_minutes=values.default_requested_duration_minutes,
                desired_weekly_workout_count=values.desired_weekly_workout_count,
                coaching_style_code=values.coaching_style_code,
                height_cm=values.height_cm,
                weight_kg=values.weight_kg,
                sex_code=values.sex_code,
                code_set_version=PROFILE_CODE_SET_VERSION,
                profile_version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
        else:
            profile.protected_birthdate = protected_birthdate
            profile.nickname = values.nickname
            profile.primary_goal_code = values.primary_goal_code
            profile.experience_level_code = values.experience_level_code
            profile.timezone = values.timezone
            profile.preferred_location_code = values.preferred_location_code
            profile.default_requested_duration_minutes = values.default_requested_duration_minutes
            profile.desired_weekly_workout_count = values.desired_weekly_workout_count
            profile.coaching_style_code = values.coaching_style_code
            profile.height_cm = values.height_cm
            profile.weight_kg = values.weight_kg
            profile.sex_code = values.sex_code
            profile.profile_version += 1
            profile.updated_at = now

        session.execute(
            delete(UserAvailableLocation).where(UserAvailableLocation.user_id == user_id)
        )
        session.execute(delete(UserAttentionArea).where(UserAttentionArea.user_id == user_id))
        session.execute(
            delete(UserPreferredExerciseType).where(UserPreferredExerciseType.user_id == user_id)
        )
        session.add_all(
            [
                UserAvailableLocation(user_id=user_id, location_code=code, created_at=now)
                for code in values.available_location_codes
            ]
            + [
                UserAttentionArea(
                    id=uuid4(),
                    user_id=user_id,
                    body_area_code=code,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                for code in values.attention_area_codes
            ]
            + [
                UserPreferredExerciseType(
                    user_id=user_id,
                    exercise_type_code=code,
                    created_at=now,
                )
                for code in values.preferred_exercise_type_codes
            ]
        )
        session.flush()

        user = session.get(User, user_id)
        if user is None:
            raise RuntimeError("onboarding user does not exist")
        return OnboardingRecord(
            user_id=user_id,
            profile_version=profile.profile_version,
            coaching_style_code=profile.coaching_style_code,
            ai_trial_started_at=user.ai_trial_started_at,
            ai_trial_ends_at=user.ai_trial_ends_at,
            premium_status_code=user.premium_status_code,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def get_profile_for_update(
        self, session: Session, user_id: UUID
    ) -> ProfileSettingsRecord | None:
        profile = session.scalar(
            select(UserProfile).where(UserProfile.user_id == user_id).with_for_update()
        )
        if profile is None:
            return None
        return ProfileSettingsRecord(
            protected_birthdate=profile.protected_birthdate,
            nickname=profile.nickname,
            primary_goal_code=profile.primary_goal_code,
            experience_level_code=profile.experience_level_code,
            timezone=profile.timezone,
            preferred_location_code=profile.preferred_location_code,
            available_location_codes=tuple(
                session.scalars(
                    select(UserAvailableLocation.location_code)
                    .where(UserAvailableLocation.user_id == user_id)
                    .order_by(UserAvailableLocation.location_code)
                )
            ),
            default_requested_duration_minutes=profile.default_requested_duration_minutes,
            desired_weekly_workout_count=profile.desired_weekly_workout_count,
            coaching_style_code=profile.coaching_style_code,
            height_cm=profile.height_cm,
            weight_kg=profile.weight_kg,
            sex_code=profile.sex_code,
            attention_area_codes=tuple(
                session.scalars(
                    select(UserAttentionArea.body_area_code)
                    .where(
                        UserAttentionArea.user_id == user_id,
                        UserAttentionArea.is_active.is_(True),
                    )
                    .order_by(UserAttentionArea.body_area_code)
                )
            ),
            preferred_exercise_type_codes=tuple(
                session.scalars(
                    select(UserPreferredExerciseType.exercise_type_code)
                    .where(UserPreferredExerciseType.user_id == user_id)
                    .order_by(UserPreferredExerciseType.exercise_type_code)
                )
            ),
            profile_version=profile.profile_version,
        )

    def update_profile_settings(
        self,
        session: Session,
        user_id: UUID,
        changes: ProfileSettingsChanges,
        now: datetime,
    ) -> tuple[int, datetime]:
        profile = session.get(UserProfile, user_id)
        if profile is None:
            raise RuntimeError("locked profile does not exist")

        if changes.protected_birthdate is not None:
            profile.protected_birthdate = changes.protected_birthdate
        for field_name, value in changes.scalar_values.items():
            setattr(profile, field_name, value)

        if changes.available_location_codes is not None:
            session.execute(
                delete(UserAvailableLocation).where(UserAvailableLocation.user_id == user_id)
            )
            session.add_all(
                UserAvailableLocation(user_id=user_id, location_code=code, created_at=now)
                for code in changes.available_location_codes
            )
        if changes.attention_area_codes is not None:
            session.execute(delete(UserAttentionArea).where(UserAttentionArea.user_id == user_id))
            session.add_all(
                UserAttentionArea(
                    id=uuid4(),
                    user_id=user_id,
                    body_area_code=code,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                for code in changes.attention_area_codes
            )
        if changes.preferred_exercise_type_codes is not None:
            session.execute(
                delete(UserPreferredExerciseType).where(
                    UserPreferredExerciseType.user_id == user_id
                )
            )
            session.add_all(
                UserPreferredExerciseType(
                    user_id=user_id,
                    exercise_type_code=code,
                    created_at=now,
                )
                for code in changes.preferred_exercise_type_codes
            )

        profile.profile_version += 1
        profile.updated_at = now
        session.flush()
        return profile.profile_version, profile.updated_at

    def get_consents(self, session: Session, user_id: UUID) -> tuple[ConsentRecord, ...]:
        rows = session.scalars(
            select(UserConsent)
            .where(UserConsent.user_id == user_id)
            .order_by(UserConsent.consent_type_code)
        )
        return tuple(
            ConsentRecord(
                consent_type_code=ConsentTypeCode(row.consent_type_code),
                granted=row.granted,
                policy_version=row.policy_version,
                updated_at=row.updated_at,
            )
            for row in rows
        )

    def replace_consents(
        self,
        session: Session,
        user_id: UUID,
        values: dict[ConsentTypeCode, bool],
        policy_version: str,
        now: datetime,
    ) -> tuple[ConsentRecord, ...]:
        existing = {
            ConsentTypeCode(row.consent_type_code): row
            for row in session.scalars(select(UserConsent).where(UserConsent.user_id == user_id))
        }
        records: list[ConsentRecord] = []
        for consent_type in ConsentTypeCode:
            granted = values[consent_type]
            row = existing.get(consent_type)
            changed = row is None or row.granted != granted or row.policy_version != policy_version
            if row is None:
                row = UserConsent(
                    id=uuid4(),
                    user_id=user_id,
                    consent_type_code=consent_type,
                    granted=granted,
                    policy_version=policy_version,
                    granted_at=now if granted else None,
                    revoked_at=None if granted else now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            elif changed:
                row.granted = granted
                row.policy_version = policy_version
                row.granted_at = now if granted else row.granted_at
                row.revoked_at = None if granted else now
                row.updated_at = now

            if changed:
                session.add(
                    UserConsentEvent(
                        id=uuid4(),
                        user_id=user_id,
                        consent_type_code=consent_type,
                        event_code=(
                            ConsentEventCode.GRANTED if granted else ConsentEventCode.REVOKED
                        ),
                        policy_version=policy_version,
                        occurred_at=now,
                        created_at=now,
                    )
                )
            records.append(
                ConsentRecord(
                    consent_type_code=consent_type,
                    granted=granted,
                    policy_version=policy_version,
                    updated_at=row.updated_at,
                )
            )
        session.flush()
        return tuple(records)

    def disable_user_for_age(self, session: Session, user_id: UUID, now: datetime) -> None:
        user = session.get(User, user_id)
        if user is None:
            raise RuntimeError("onboarding user does not exist")
        user.status_code = UserStatusCode.DISABLED
        user.updated_at = now


__all__ = ["ProfileRepository"]
