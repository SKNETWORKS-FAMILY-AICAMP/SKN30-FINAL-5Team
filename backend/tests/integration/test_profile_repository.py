import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.identity import User
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAttentionArea,
    UserAvailableLocation,
    UserConsent,
    UserConsentEvent,
    UserEquipment,
    UserPreferredExerciseType,
    UserProfile,
)
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.db.repositories.identity import IdentityRepository
from backend.app.db.repositories.profile import ProfileRepository
from backend.app.integrations.birthdate_crypto import LocalAesGcmBirthdateCipher
from backend.app.modules.catalog.service import CatalogImporter
from backend.app.modules.identity.ports import VerifiedFirebaseIdentity
from backend.app.modules.identity.service import CurrentUserService
from backend.app.modules.profiles.schemas import (
    OnboardingUpsertRequest,
    ProfileSettingsUpdateRequest,
)
from backend.app.modules.profiles.service import (
    IdempotencyKeyReusedError,
    ProfileService,
    StaleProfileError,
)

ALEMBIC_CONFIG = Path("backend/alembic.ini")
GENERATED_ARTIFACT = Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0")
NOW = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)


class StaticVerifier:
    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        assert token == "id-token"
        return VerifiedFirebaseIdentity(firebase_subject="profile-test-subject")


class FailingProfileRepository(ProfileRepository):
    def update_profile_settings(self, *args, **kwargs):
        super().update_profile_settings(*args, **kwargs)
        raise RuntimeError("synthetic relationship failure")


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Profile repository tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")

    engine: Engine = create_engine(test_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
        get_settings.cache_clear()


def _request(nickname: str = "러너01") -> OnboardingUpsertRequest:
    return OnboardingUpsertRequest.model_validate(
        {
            "nickname": nickname,
            "date_of_birth": "2000-08-11",
            "primary_goal_code": "GENERAL_FITNESS",
            "experience_level_code": "BEGINNER",
            "timezone": "Asia/Seoul",
            "preferred_location_code": "HOME",
            "default_requested_duration_minutes": 40,
            "desired_weekly_workout_count": 3,
            "attention_area_codes": ["SHOULDER"],
            "preferred_exercise_type_codes": ["STRENGTH"],
            "height_cm": 175.0,
            "weight_kg": 70.0,
            "sex_code": "MALE",
            "consents": {
                "general_personal_data": True,
                "sensitive_data": True,
                "wearable_integration": False,
                "calendar_integration": False,
                "marketing": False,
            },
        }
    )


@pytest.mark.integration
def test_onboarding_persists_atomically_and_retries_idempotently(
    postgres_session: Session,
) -> None:
    CatalogImporter(CatalogRepository(), "test").import_artifact(
        postgres_session, GENERATED_ARTIFACT
    )
    current_user = CurrentUserService(
        StaticVerifier(), IdentityRepository(), clock=lambda: NOW
    ).authenticate(postgres_session, "id-token")
    service = ProfileService(
        ProfileRepository(),
        LocalAesGcmBirthdateCipher(b"p" * 32, key_id="test-v1", app_env="test"),
        primary_goal_codes=("GENERAL_FITNESS",),
        experience_level_codes=("BEGINNER",),
        consent_policy_version="privacy-v1",
        clock=lambda: NOW,
    )
    idempotency_key = uuid4()

    first = service.upsert_onboarding(
        postgres_session, current_user.user_id, _request(), idempotency_key
    )
    second = service.upsert_onboarding(
        postgres_session, current_user.user_id, _request(), idempotency_key
    )
    assert second == first
    profile = postgres_session.get(UserProfile, current_user.user_id)
    assert profile is not None
    assert profile.profile_version == 1
    assert "2000-08-11" not in profile.protected_birthdate
    assert postgres_session.scalar(select(func.count()).select_from(UserEquipment)) == 0
    assert postgres_session.scalar(select(func.count()).select_from(UserAttentionArea)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(UserPreferredExerciseType)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(UserConsent)) == 5
    assert postgres_session.scalar(select(func.count()).select_from(UserConsentEvent)) == 5
    assert postgres_session.scalar(select(func.count()).select_from(MutationIdempotencyRecord)) == 1


@pytest.mark.integration
def test_reonboarding_preserves_existing_user_equipment(
    postgres_session: Session,
) -> None:
    CatalogImporter(CatalogRepository(), "test").import_artifact(
        postgres_session, GENERATED_ARTIFACT
    )
    current_user = CurrentUserService(
        StaticVerifier(), IdentityRepository(), clock=lambda: NOW
    ).authenticate(postgres_session, "id-token")
    service = ProfileService(
        ProfileRepository(),
        LocalAesGcmBirthdateCipher(b"p" * 32, key_id="test-v1", app_env="test"),
        primary_goal_codes=("GENERAL_FITNESS",),
        experience_level_codes=("BEGINNER",),
        consent_policy_version="privacy-v1",
        clock=lambda: NOW,
    )
    service.upsert_onboarding(postgres_session, current_user.user_id, _request(), uuid4())
    postgres_session.add(
        UserEquipment(user_id=current_user.user_id, equipment_code="RESISTANCE_BAND")
    )
    postgres_session.flush()

    response = service.upsert_onboarding(
        postgres_session,
        current_user.user_id,
        _request(nickname="재온보딩 사용자"),
        uuid4(),
    )

    assert response.profile_version == 2
    assert list(
        postgres_session.scalars(
            select(UserEquipment.equipment_code).where(
                UserEquipment.user_id == current_user.user_id
            )
        )
    ) == ["RESISTANCE_BAND"]


@pytest.mark.integration
def test_profile_settings_update_is_partial_atomic_versioned_and_idempotent(
    postgres_session: Session,
) -> None:
    CatalogImporter(CatalogRepository(), "test").import_artifact(
        postgres_session, GENERATED_ARTIFACT
    )
    current_user = CurrentUserService(
        StaticVerifier(), IdentityRepository(), clock=lambda: NOW
    ).authenticate(postgres_session, "id-token")
    cipher = LocalAesGcmBirthdateCipher(b"p" * 32, key_id="test-v1", app_env="test")
    service = ProfileService(
        ProfileRepository(),
        cipher,
        primary_goal_codes=("GENERAL_FITNESS", "MUSCLE_GAIN"),
        experience_level_codes=("BEGINNER", "INTERMEDIATE"),
        consent_policy_version="privacy-v1",
        clock=lambda: NOW,
    )
    onboarding = service.upsert_onboarding(
        postgres_session, current_user.user_id, _request(), uuid4()
    )
    original_created_at = onboarding.created_at
    postgres_session.add(UserEquipment(user_id=current_user.user_id, equipment_code="MAT"))
    postgres_session.flush()

    key = uuid4()
    request = ProfileSettingsUpdateRequest.model_validate(
        {
            "nickname": "수정 사용자",
            "primary_goal_code": "MUSCLE_GAIN",
            "experience_level_code": "INTERMEDIATE",
            "preferred_location_code": "HOME",
            "available_location_codes": ["HOME"],
            "attention_area_codes": [],
            "preferred_exercise_type_codes": ["MOBILITY"],
            "date_of_birth": "1999-01-02",
        }
    )
    first = service.update_profile_settings(postgres_session, current_user.user_id, request, key, 1)
    replay = service.update_profile_settings(
        postgres_session, current_user.user_id, request, key, 1
    )

    assert replay == first
    assert first.profile_version == 2
    profile = postgres_session.get(UserProfile, current_user.user_id)
    assert profile is not None
    assert profile.nickname == "수정 사용자"
    assert profile.default_requested_duration_minutes == 40
    assert profile.desired_weekly_workout_count == 3
    assert profile.created_at == original_created_at
    assert cipher.decrypt(current_user.user_id, profile.protected_birthdate) == date(1999, 1, 2)
    assert set(
        postgres_session.scalars(
            select(UserEquipment.equipment_code).where(
                UserEquipment.user_id == current_user.user_id
            )
        )
    ) == {"MAT"}
    assert (
        list(
            postgres_session.scalars(
                select(UserAttentionArea.body_area_code).where(
                    UserAttentionArea.user_id == current_user.user_id
                )
            )
        )
        == []
    )
    assert list(
        postgres_session.scalars(
            select(UserAvailableLocation.location_code).where(
                UserAvailableLocation.user_id == current_user.user_id
            )
        )
    ) == ["HOME"]
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(MutationIdempotencyRecord)
            .where(MutationIdempotencyRecord.endpoint_code == "PATCH_ME_PROFILE")
        )
        == 1
    )
    postgres_session.commit()

    with pytest.raises(IdempotencyKeyReusedError):
        service.update_profile_settings(
            postgres_session,
            current_user.user_id,
            ProfileSettingsUpdateRequest(nickname="다른 요청"),
            key,
            1,
        )
    before_stale = postgres_session.get(UserProfile, current_user.user_id)
    assert before_stale is not None
    before_stale_nickname = before_stale.nickname
    postgres_session.commit()
    with pytest.raises(StaleProfileError):
        service.update_profile_settings(
            postgres_session,
            current_user.user_id,
            ProfileSettingsUpdateRequest(nickname="stale 변경"),
            uuid4(),
            1,
        )
    after_stale = postgres_session.get(UserProfile, current_user.user_id)
    assert after_stale is not None
    assert after_stale.profile_version == 2
    assert after_stale.nickname == before_stale_nickname


@pytest.mark.integration
def test_profile_settings_relationship_failure_rolls_back_every_change(
    postgres_session: Session,
) -> None:
    CatalogImporter(CatalogRepository(), "test").import_artifact(
        postgres_session, GENERATED_ARTIFACT
    )
    current_user = CurrentUserService(
        StaticVerifier(), IdentityRepository(), clock=lambda: NOW
    ).authenticate(postgres_session, "id-token")
    cipher = LocalAesGcmBirthdateCipher(b"p" * 32, key_id="test-v1", app_env="test")
    normal_service = ProfileService(
        ProfileRepository(),
        cipher,
        primary_goal_codes=("GENERAL_FITNESS",),
        experience_level_codes=("BEGINNER",),
        consent_policy_version="privacy-v1",
        clock=lambda: NOW,
    )
    normal_service.upsert_onboarding(postgres_session, current_user.user_id, _request(), uuid4())
    postgres_session.add(UserEquipment(user_id=current_user.user_id, equipment_code="MAT"))
    postgres_session.flush()
    failing_service = ProfileService(
        FailingProfileRepository(),
        cipher,
        primary_goal_codes=("GENERAL_FITNESS",),
        experience_level_codes=("BEGINNER",),
        consent_policy_version="privacy-v1",
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="synthetic relationship failure"):
        failing_service.update_profile_settings(
            postgres_session,
            current_user.user_id,
            ProfileSettingsUpdateRequest(nickname="rollback 대상"),
            uuid4(),
            1,
        )

    profile = postgres_session.get(UserProfile, current_user.user_id)
    assert profile is not None
    assert profile.nickname == "러너01"
    assert profile.profile_version == 1
    assert list(
        postgres_session.scalars(
            select(UserEquipment.equipment_code).where(
                UserEquipment.user_id == current_user.user_id
            )
        )
    ) == ["MAT"]


@pytest.mark.integration
def test_concurrent_profile_updates_allow_only_one_expected_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Profile repository tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")
    engine = create_engine(test_database_url)
    user_id = uuid4()
    cipher = LocalAesGcmBirthdateCipher(b"c" * 32, key_id="test-v1", app_env="test")
    with Session(engine) as setup:
        CatalogImporter(CatalogRepository(), "test").import_artifact(setup, GENERATED_ARTIFACT)
        setup.add(
            UserProfile(
                user_id=user_id,
                protected_birthdate=cipher.encrypt(user_id, date(2000, 1, 1)),
                nickname="동시성 사용자",
                primary_goal_code="GENERAL_FITNESS",
                experience_level_code="BEGINNER",
                timezone="Asia/Seoul",
                preferred_location_code="HOME",
                default_requested_duration_minutes=30,
                desired_weekly_workout_count=3,
                coaching_style_code="SUPPORTIVE",
                height_cm=170,
                weight_kg=65,
                sex_code="PREFER_NOT_TO_SAY",
                profile_version=1,
            )
        )
        setup.add(
            User(
                id=user_id,
                status_code="ACTIVE",
                code_set_version="identity-mvp-v1",
                last_active_at=NOW,
                ai_trial_started_at=NOW,
                ai_trial_ends_at=NOW + timedelta(days=14),
                premium_status_code="NOT_AVAILABLE",
            )
        )
        setup.add(UserAvailableLocation(user_id=user_id, location_code="HOME"))
        setup.add(UserEquipment(user_id=user_id, equipment_code="MAT"))
        setup.commit()

    barrier = Barrier(2)

    def update(nickname: str) -> str:
        service = ProfileService(
            ProfileRepository(),
            cipher,
            primary_goal_codes=("GENERAL_FITNESS",),
            experience_level_codes=("BEGINNER",),
            consent_policy_version="privacy-v1",
            clock=lambda: NOW,
        )
        with Session(engine) as worker_session:
            barrier.wait()
            try:
                service.update_profile_settings(
                    worker_session,
                    user_id,
                    ProfileSettingsUpdateRequest(nickname=nickname),
                    uuid4(),
                    1,
                )
            except StaleProfileError:
                return "stale"
        return "success"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, ("요청 A", "요청 B")))
        assert sorted(results) == ["stale", "success"]
        with Session(engine) as verify:
            profile = verify.get(UserProfile, user_id)
            assert profile is not None
            assert profile.profile_version == 2
            assert profile.nickname in {"요청 A", "요청 B"}
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.commit()
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_profile_settings_migration_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Profile migration tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_CONFIG))
    command.upgrade(config, "head")
    command.downgrade(config, "0016_approve_safety_data")
    command.upgrade(config, "head")
    get_settings.cache_clear()
