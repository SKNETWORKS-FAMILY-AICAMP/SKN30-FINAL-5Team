import json
import logging
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_profile_repository,
    get_routine_repository,
)
from backend.app.core.config import Settings
from backend.app.core.logging import JsonFormatter
from backend.app.integrations.birthdate_crypto import LocalAesGcmBirthdateCipher
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.profiles.codes import ConsentTypeCode, MutationEndpointCode
from backend.app.modules.profiles.ports import (
    ConsentRecord,
    IdempotencyRecord,
    MeProfileRecord,
    MeRecord,
    OnboardingProfileValues,
    OnboardingRecord,
)
from backend.tests.unit.test_routine_service import FakeRoutineRepository

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
        self.terms_versions: list[str] = []
        self.persistent_pains: tuple[tuple[str, int], ...] = ()
        self.onboarding_values: OnboardingProfileValues | None = None
        self.me_record: MeRecord | None = None

    def get_me(self, session: FakeSession, user_id: UUID) -> MeRecord | None:
        del session, user_id
        return self.me_record

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
        del session
        self.onboarding_values = values
        self.profile_version += 1
        self.me_record = MeRecord(
            user_id=user_id,
            status_code="ACTIVE",
            premium_status_code="NOT_AVAILABLE",
            ai_trial_started_at=NOW,
            ai_trial_ends_at=datetime(2026, 8, 27, 6, 0, tzinfo=UTC),
            profile=MeProfileRecord(
                nickname=values.nickname,
                protected_birthdate=protected_birthdate,
                primary_goal_code=values.primary_goal_code,
                experience_level_code=values.experience_level_code,
                timezone=values.timezone,
                preferred_location_code=values.preferred_location_code,
                available_location_codes=values.available_location_codes,
                default_requested_duration_minutes=values.default_requested_duration_minutes,
                desired_weekly_workout_count=values.desired_weekly_workout_count,
                coaching_style_code=values.coaching_style_code,
                attention_area_codes=values.attention_area_codes,
                preferred_exercise_type_codes=values.preferred_exercise_type_codes,
                profile_version=self.profile_version,
                created_at=now,
                updated_at=now,
            ),
        )
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

    def get_consents(self, session: FakeSession, user_id: UUID) -> tuple[ConsentRecord, ...]:
        del session, user_id
        return tuple(
            ConsentRecord(
                consent_type_code=consent_type,
                granted=granted,
                policy_version="consent-policy-test",
                updated_at=NOW,
            )
            for consent_type, granted in sorted(
                self.consent_values.items(), key=lambda item: item[0].value
            )
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

    def record_terms_agreement(
        self, session: FakeSession, user_id: UUID, terms_version: str, now: datetime
    ) -> None:
        del session, user_id, now
        if terms_version not in self.terms_versions:
            self.terms_versions.append(terms_version)

    def replace_persistent_pains(
        self,
        session: FakeSession,
        user_id: UUID,
        pains: tuple[tuple[str, int], ...],
        now: datetime,
    ) -> None:
        del session, user_id, now
        self.persistent_pains = pains


def _payload() -> dict[str, object]:
    return {
        "nickname": "러너01",
        "date_of_birth": "2000-08-11",
        "medical_exercise_restriction": False,
        "terms_version": "terms-v1",
        "primary_goal_code": "GENERAL_FITNESS",
        "experience_level_code": "BEGINNER",
        "timezone": "Asia/Seoul",
        "preferred_location_code": "HOME",
        "default_requested_duration_minutes": 40,
        "desired_weekly_workout_count": 3,
        "attention_area_codes": ["KNEE"],
        "preferred_exercise_type_codes": ["STRENGTH"],
        "coaching_style_code": "SUPPORTIVE",
        "height_cm": 172.0,
        "weight_kg": 68.5,
        "sex_code": "FEMALE",
        "consents": {
            "general_personal_data": True,
            "sensitive_data": True,
            "wearable_integration": False,
            "calendar_integration": False,
            "marketing": False,
        },
        "persistent_pains": [{"body_area_code": "KNEE", "intensity_score": 3}],
    }


def _client(
    repository: FakeProfileRepository,
    *,
    missing_configuration_keys: tuple[str, ...] = (),
    routine_repository: FakeRoutineRepository | None = None,
) -> TestClient:
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        consent_policy_version=(
            None if "CONSENT_POLICY_VERSION" in missing_configuration_keys else "privacy-v1"
        ),
        onboarding_primary_goal_codes=(
            ()
            if "ONBOARDING_PRIMARY_GOAL_CODES" in missing_configuration_keys
            else ("GENERAL_FITNESS",)
        ),
        onboarding_experience_level_codes=(
            ()
            if "ONBOARDING_EXPERIENCE_LEVEL_CODES" in missing_configuration_keys
            else ("BEGINNER",)
        ),
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
    app.dependency_overrides[get_routine_repository] = lambda: (
        routine_repository or FakeRoutineRepository()
    )
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
    assert repository.terms_versions == ["terms-v1"]
    assert repository.persistent_pains == (("KNEE", 3),)
    assert set(first.json()) == {
        "user_id",
        "onboarding_completed",
        "profile_version",
        "coaching_style_code",
        "ai_trial_started_at",
        "ai_trial_ends_at",
        "premium_status_code",
        "created_at",
        "updated_at",
    }
    assert "date_of_birth" not in first.text
    assert "2000-08-11" not in first.text


def test_onboarding_automatically_creates_exactly_one_base_routine() -> None:
    profile_repository = FakeProfileRepository()
    routine_repository = FakeRoutineRepository()
    key = str(uuid4())

    with _client(profile_repository, routine_repository=routine_repository) as client:
        first = client.put(
            "/api/v1/me/onboarding", json=_payload(), headers={"Idempotency-Key": key}
        )
        repeated = client.put(
            "/api/v1/me/onboarding", json=_payload(), headers={"Idempotency-Key": key}
        )
        reonboarding = client.put(
            "/api/v1/me/onboarding", json=_payload(), headers={"Idempotency-Key": str(uuid4())}
        )

    assert first.status_code == 200
    assert repeated.json() == first.json()
    assert reonboarding.status_code == 200
    assert len(routine_repository.versions) == 1
    assert next(iter(routine_repository.versions.values())) == 1
    routine_payload = next(iter(routine_repository.payloads.values()))
    assert {day["requested_duration_minutes"] for day in routine_payload["days"]} == {30}


def test_onboarding_returns_routine_creation_failure_as_a_service_error() -> None:
    routine_repository = FakeRoutineRepository()
    routine_repository.context = None  # type: ignore[assignment]

    with _client(FakeProfileRepository(), routine_repository=routine_repository) as client:
        response = client.put(
            "/api/v1/me/onboarding", json=_payload(), headers={"Idempotency-Key": str(uuid4())}
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "APPROVED_CATALOG_UNAVAILABLE"


def test_openapi_removes_equipment_from_onboarding_and_me_profile() -> None:
    with _client(FakeProfileRepository()) as client:
        schemas = client.app.openapi()["components"]["schemas"]

    assert "equipment_codes" not in schemas["OnboardingUpsertRequest"]["properties"]
    assert "equipment_codes" not in schemas["MeProfile"]["properties"]


def test_get_me_profile_response_omits_equipment_codes() -> None:
    repository = FakeProfileRepository()
    with _client(repository) as client:
        onboarding = client.put(
            "/api/v1/me/onboarding",
            json=_payload(),
            headers={"Idempotency-Key": str(uuid4())},
        )
        response = client.get("/api/v1/me")

    assert onboarding.status_code == 200
    assert response.status_code == 200
    assert response.json()["profile"]["nickname"] == "러너01"
    assert "equipment_codes" not in response.json()["profile"]


def test_onboarding_rejects_removed_equipment_field() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload["equipment_codes"] = ["BODYWEIGHT"]

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert repository.profile_version == 0


@pytest.mark.parametrize("field_name", ["sex_code", "height_cm", "weight_kg"])
@pytest.mark.parametrize("explicit_null", [False, True])
def test_required_body_metrics_reject_missing_and_null_values(
    field_name: str,
    explicit_null: bool,
) -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    if explicit_null:
        payload[field_name] = None
    else:
        payload.pop(field_name)

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 422
    assert repository.profile_version == 0


def test_invalid_sex_code_is_rejected() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload["sex_code"] = "OTHER"

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 422


def test_prefer_not_to_say_sex_code_is_accepted() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload["sex_code"] = "PREFER_NOT_TO_SAY"

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("height_cm", 80),
        ("height_cm", 250),
        ("weight_kg", 25),
        ("weight_kg", 300),
    ],
)
def test_body_metric_boundaries_are_accepted(field_name: str, value: int) -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload[field_name] = value

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("height_cm", 79.9),
        ("height_cm", 250.1),
        ("weight_kg", 24.9),
        ("weight_kg", 300.1),
    ],
)
def test_body_metrics_outside_boundaries_are_rejected(
    field_name: str,
    value: float,
) -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload[field_name] = value

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 422


def test_attention_area_codes_is_required() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload.pop("attention_area_codes")

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 422
    assert repository.profile_version == 0


@pytest.mark.parametrize(
    "attention_area_codes",
    [[], ["KNEE"], ["KNEE", "SHOULDER"]],
)
def test_valid_attention_area_responses_are_accepted(
    attention_area_codes: list[str],
) -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload["attention_area_codes"] = attention_area_codes

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 200


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
    assert response.json()["error"]["code"] == "OUT_OF_SCOPE_AGE"
    assert repository.disabled is False
    assert secret_birthdate not in response.text


def test_medical_exercise_restriction_blocks_onboarding_without_profile_write() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload["medical_exercise_restriction"] = True

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "OUT_OF_SCOPE_MEDICAL_MANAGEMENT"
    assert repository.profile_version == 0


def test_new_weekly_target_sessions_maps_to_persisted_onboarding_value() -> None:
    repository = FakeProfileRepository()
    payload = _payload()
    payload.pop("desired_weekly_workout_count")
    payload["weekly_target_sessions"] = 4

    with _client(repository) as client:
        response = client.put(
            "/api/v1/me/onboarding", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )

    assert response.status_code == 200
    assert repository.onboarding_values is not None
    assert repository.onboarding_values.weekly_target_sessions == 4
    assert repository.onboarding_values.desired_weekly_workout_count == 4


@pytest.mark.parametrize(
    "missing_keys",
    [
        ("CONSENT_POLICY_VERSION",),
        ("ONBOARDING_PRIMARY_GOAL_CODES",),
        ("ONBOARDING_EXPERIENCE_LEVEL_CODES",),
        (
            "CONSENT_POLICY_VERSION",
            "ONBOARDING_PRIMARY_GOAL_CODES",
            "ONBOARDING_EXPERIENCE_LEVEL_CODES",
        ),
    ],
)
def test_unapproved_deployment_configuration_fails_closed_and_logs_only_missing_keys(
    caplog: pytest.LogCaptureFixture,
    missing_keys: tuple[str, ...],
) -> None:
    repository = FakeProfileRepository()
    with caplog.at_level(logging.ERROR, logger="backend.profile"):
        with _client(repository, missing_configuration_keys=missing_keys) as client:
            response = client.put(
                "/api/v1/me/onboarding",
                json=_payload(),
                headers={"Idempotency-Key": str(uuid4())},
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROFILE_CONFIGURATION_UNAVAILABLE"
    assert response.json()["error"]["message"] == "온보딩 기능을 일시적으로 사용할 수 없습니다."
    assert repository.profile_version == 0
    records = [
        record
        for record in caplog.records
        if getattr(record, "event_code", None) == "PROFILE_CONFIGURATION_UNAVAILABLE"
    ]
    assert len(records) == 1
    serialized_log = JsonFormatter().format(records[0])
    log_payload = json.loads(serialized_log)
    assert log_payload["missing_keys"] == list(missing_keys)
    assert log_payload["request_id"] == response.headers["X-Request-ID"]
    for sensitive_value in ("privacy-v1", "GENERAL_FITNESS", "BEGINNER", "2000-08-11"):
        assert sensitive_value not in serialized_log


def test_deployed_environment_without_a_kms_key_names_that_key_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 배포 환경에서 BIRTHDATE_KMS_KEY_ID가 비면 cipher가 없어 온보딩이 503으로 닫힌다.
    # 진단 로그가 그 키를 지목하지 않으면 운영자는 원인을 찾지 못한다.
    repository = FakeProfileRepository()
    settings = Settings(
        _env_file=None,
        app_env="staging",
        database_url="postgresql+psycopg://test:test@localhost/test",
        consent_policy_version="privacy-v1",
        onboarding_primary_goal_codes=("GENERAL_FITNESS",),
        onboarding_experience_level_codes=("BEGINNER",),
    )
    app = create_app(settings=settings, readiness_probe=lambda: None)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid4(),
        status_code=UserStatusCode.ACTIVE,
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_profile_repository] = lambda: repository

    with caplog.at_level(logging.ERROR, logger="backend.profile"):
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/me/onboarding",
                json=_payload(),
                headers={"Idempotency-Key": str(uuid4())},
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROFILE_CONFIGURATION_UNAVAILABLE"
    assert repository.profile_version == 0
    records = [
        record
        for record in caplog.records
        if getattr(record, "event_code", None) == "PROFILE_CONFIGURATION_UNAVAILABLE"
    ]
    assert len(records) == 1
    serialized_log = JsonFormatter().format(records[0])
    log_payload = json.loads(serialized_log)
    assert log_payload["missing_keys"] == ["BIRTHDATE_KMS_KEY_ID"]
    # 배포 환경은 로컬 전용 키를 쓰지 않으므로 그 이름을 노출하면 안 된다.
    assert "BIRTHDATE_ENCRYPTION_KEY_BASE64" not in serialized_log
    assert "2000-08-11" not in serialized_log


def test_local_environment_missing_birthdate_key_names_the_local_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeProfileRepository()
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        consent_policy_version="privacy-v1",
        onboarding_primary_goal_codes=("GENERAL_FITNESS",),
        onboarding_experience_level_codes=("BEGINNER",),
    )
    app = create_app(settings=settings, readiness_probe=lambda: None)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid4(),
        status_code=UserStatusCode.ACTIVE,
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_profile_repository] = lambda: repository

    with caplog.at_level(logging.ERROR, logger="backend.profile"):
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/me/onboarding",
                json=_payload(),
                headers={"Idempotency-Key": str(uuid4())},
            )

    assert response.status_code == 503
    records = [
        record
        for record in caplog.records
        if getattr(record, "event_code", None) == "PROFILE_CONFIGURATION_UNAVAILABLE"
    ]
    log_payload = json.loads(JsonFormatter().format(records[0]))
    assert log_payload["missing_keys"] == ["BIRTHDATE_ENCRYPTION_KEY_BASE64"]


def test_configured_onboarding_does_not_log_configuration_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeProfileRepository()
    with caplog.at_level(logging.ERROR, logger="backend.profile"):
        with _client(repository) as client:
            response = client.put(
                "/api/v1/me/onboarding",
                json=_payload(),
                headers={"Idempotency-Key": str(uuid4())},
            )

    assert response.status_code == 200
    assert not any(
        getattr(record, "event_code", None) == "PROFILE_CONFIGURATION_UNAVAILABLE"
        for record in caplog.records
    )


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


def test_get_consents_returns_stored_states() -> None:
    repository = FakeProfileRepository()
    client = _client(repository)
    with client:
        onboarded = client.put(
            "/api/v1/me/onboarding",
            headers={"Idempotency-Key": str(uuid4())},
            json=_payload(),
        )
        read = client.get("/api/v1/me/consents")
    assert onboarded.status_code == 200
    assert read.status_code == 200
    states = {item["consent_type_code"]: item["granted"] for item in read.json()["consents"]}
    assert states["GENERAL_PERSONAL_DATA"] is True
    assert states["SENSITIVE_DATA"] is True
    assert states["MARKETING"] is False


def test_get_consents_before_onboarding_is_empty() -> None:
    client = _client(FakeProfileRepository())
    with client:
        read = client.get("/api/v1/me/consents")
    assert read.status_code == 200
    assert read.json()["consents"] == []
