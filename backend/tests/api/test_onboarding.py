from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_profile_repository,
)
from backend.app.core.config import Settings
from backend.app.integrations.birthdate_crypto import LocalAesGcmBirthdateCipher
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.profiles.codes import ConsentTypeCode, MutationEndpointCode
from backend.app.modules.profiles.ports import (
    ConsentRecord,
    IdempotencyRecord,
    OnboardingProfileValues,
    OnboardingRecord,
)

NOW = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)


class FakeSession:
    def begin(self) -> nullcontext[None]:
        return nullcontext()


class FakeProfileRepository:
    def __init__(self) -> None:
        self.idempotency: dict[tuple[UUID, MutationEndpointCode, UUID], IdempotencyRecord] = {}
        self.profile_version = 0
        self.disabled = False
        self.consent_events = 0
        self.consent_values: dict[ConsentTypeCode, bool] = {}

    def acquire_idempotency_lock(
        self,
        session: FakeSession,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
    ) -> None:
        del session, user_id, endpoint_code, idempotency_key

    def get_idempotency_record(
        self,
        session: FakeSession,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
    ) -> IdempotencyRecord | None:
        del session
        return self.idempotency.get((user_id, endpoint_code, idempotency_key))

    def save_idempotency_record(
        self,
        session: FakeSession,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
        request_hash: str,
        response_payload: dict[str, Any],
        response_schema_version: str,
        now: datetime,
    ) -> None:
        del session, response_schema_version, now
        self.idempotency[(user_id, endpoint_code, idempotency_key)] = IdempotencyRecord(
            request_hash=request_hash,
            response_payload=response_payload,
        )

    def upsert_profile(
        self,
        session: FakeSession,
        user_id: UUID,
        protected_birthdate: str,
        values: OnboardingProfileValues,
        now: datetime,
    ) -> OnboardingRecord:
        del session, protected_birthdate
        self.profile_version += 1
        return OnboardingRecord(
            user_id=user_id,
            profile_version=self.profile_version,
            coaching_style_code=values.coaching_style_code,
            ai_trial_started_at=NOW,
            ai_trial_ends_at=datetime(2026, 8, 27, 6, 0, tzinfo=UTC),
            premium_status_code="NOT_AVAILABLE",
            created_at=now,
            updated_at=now,
        )

    def replace_consents(
        self,
        session: FakeSession,
        user_id: UUID,
        values: dict[ConsentTypeCode, bool],
        policy_version: str,
        now: datetime,
    ) -> tuple[ConsentRecord, ...]:
        del session, user_id
        for consent_type, granted in values.items():
            if self.consent_values.get(consent_type) != granted:
                self.consent_events += 1
            self.consent_values[consent_type] = granted
        return tuple(
            ConsentRecord(
                consent_type_code=consent_type,
                granted=values[consent_type],
                policy_version=policy_version,
                updated_at=now,
            )
            for consent_type in ConsentTypeCode
        )

    def disable_user_for_age(self, session: FakeSession, user_id: UUID, now: datetime) -> None:
        del session, user_id, now
        self.disabled = True


def _payload() -> dict[str, object]:
    return {
        "nickname": "러너01",
        "date_of_birth": "2000-08-11",
        "primary_goal_code": "GENERAL_FITNESS",
        "experience_level_code": "BEGINNER",
        "timezone": "Asia/Seoul",
        "preferred_location_code": "HOME",
        "default_requested_duration_minutes": 40,
        "desired_weekly_workout_count": 3,
        "equipment_codes": ["BODYWEIGHT"],
        "attention_area_codes": ["KNEE"],
        "preferred_exercise_type_codes": ["STRENGTH"],
        "coaching_style_code": "SUPPORTIVE",
        "height_cm": None,
        "weight_kg": None,
        "sex_code": None,
        "consents": {
            "general_personal_data": True,
            "sensitive_data": True,
            "wearable_integration": False,
            "calendar_integration": False,
            "marketing": False,
        },
    }


def _client(repository: FakeProfileRepository, *, configured: bool = True) -> TestClient:
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        consent_policy_version="privacy-v1" if configured else None,
        onboarding_primary_goal_codes=("GENERAL_FITNESS",) if configured else (),
        onboarding_experience_level_codes=("BEGINNER",) if configured else (),
    )
    user_id = uuid4()
    app = create_app(
        settings=settings,
        readiness_probe=lambda: None,
        birthdate_cipher=LocalAesGcmBirthdateCipher(
            b"t" * 32,
            key_id="test-v1",
            app_env="test",
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id,
        status_code=UserStatusCode.ACTIVE,
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_profile_repository] = lambda: repository
    return TestClient(app)


def test_onboarding_is_atomic_idempotent_and_does_not_expose_birthdate() -> None:
    repository = FakeProfileRepository()
    key = str(uuid4())
    with _client(repository) as client:
        first = client.put(
            "/api/v1/me/onboarding",
            json=_payload(),
            headers={"Idempotency-Key": key},
        )
        second = client.put(
            "/api/v1/me/onboarding",
            json=_payload(),
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert repository.profile_version == 1
    assert repository.consent_events == 5
    assert "date_of_birth" not in first.text
    assert "2000-08-11" not in first.text


def test_reusing_idempotency_key_with_another_payload_returns_conflict() -> None:
    repository = FakeProfileRepository()
    key = str(uuid4())
    with _client(repository) as client:
        first = client.put(
            "/api/v1/me/onboarding",
            json=_payload(),
            headers={"Idempotency-Key": key},
        )
        changed = _payload()
        changed["nickname"] = "다른 닉네임"
        second = client.put(
            "/api/v1/me/onboarding",
            json=changed,
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_underage_onboarding_is_blocked_without_leaking_birthdate() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    secret_birthdate = "2020-01-01"
    payload["date_of_birth"] = secret_birthdate
    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGE_REQUIREMENT_NOT_MET"
    assert repository.disabled is True
    assert secret_birthdate not in response.text


def test_unapproved_deployment_configuration_fails_closed() -> None:
    repository = FakeProfileRepository()
    with _client(repository, configured=False) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=_payload(),
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROFILE_CONFIGURATION_UNAVAILABLE"
    assert repository.profile_version == 0


def test_invalid_calendar_birthdate_uses_specific_safe_error() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload["date_of_birth"] = "2026-02-30"
    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DATE_OF_BIRTH"
    assert "2026-02-30" not in response.text


def test_consent_replacement_is_idempotent_and_versioned() -> None:
    repository = FakeProfileRepository()
    key = str(uuid4())
    payload = {
        "general_personal_data": True,
        "sensitive_data": True,
        "wearable_integration": False,
        "calendar_integration": False,
        "marketing": True,
    }
    with _client(repository) as client:
        first = client.put(
            "/api/v1/me/consents",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        second = client.put(
            "/api/v1/me/consents",
            json=payload,
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert repository.consent_events == 5
    assert {item["policy_version"] for item in first.json()["consents"]} == {"privacy-v1"}
