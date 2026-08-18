import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.profile import (
    MutationIdempotencyRecord,
    UserAttentionArea,
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
from backend.app.modules.profiles.schemas import OnboardingUpsertRequest
from backend.app.modules.profiles.service import ProfileService

ALEMBIC_CONFIG = Path("backend/alembic.ini")
GENERATED_ARTIFACT = Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0")
NOW = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)


class StaticVerifier:
    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        assert token == "id-token"
        return VerifiedFirebaseIdentity(firebase_subject="profile-test-subject")


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
    session = Session(bind=connection)
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
            "equipment_codes": ["MAT"],
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
    assert postgres_session.scalar(select(func.count()).select_from(UserEquipment)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(UserAttentionArea)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(UserPreferredExerciseType)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(UserConsent)) == 5
    assert postgres_session.scalar(select(func.count()).select_from(UserConsentEvent)) == 5
    assert postgres_session.scalar(select(func.count()).select_from(MutationIdempotencyRecord)) == 1
