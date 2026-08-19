import logging
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
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
from backend.app.modules.profiles.codes import MutationEndpointCode
from backend.app.modules.profiles.ports import (
    IdempotencyRecord,
    ProfileSettingsChanges,
    ProfileSettingsRecord,
)

NOW = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)


class FakeSession:
    def begin(self) -> nullcontext[None]:
        return nullcontext()


class FakeProfileSettingsRepository:
    def __init__(self, record: ProfileSettingsRecord | None) -> None:
        self.record = record
        self.idempotency: dict[tuple[UUID, MutationEndpointCode, UUID], IdempotencyRecord] = {}
        self.update_count = 0
        self.disabled = False

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

    def get_profile_for_update(
        self, session: FakeSession, user_id: UUID
    ) -> ProfileSettingsRecord | None:
        del session, user_id
        return self.record

    def update_profile_settings(
        self,
        session: FakeSession,
        user_id: UUID,
        changes: ProfileSettingsChanges,
        now: datetime,
    ) -> tuple[int, datetime]:
        del session, user_id
        assert self.record is not None
        values: dict[str, object] = dict(changes.scalar_values)
        if changes.protected_birthdate is not None:
            values["protected_birthdate"] = changes.protected_birthdate
        for field_name in (
            "available_location_codes",
            "equipment_codes",
            "attention_area_codes",
            "preferred_exercise_type_codes",
        ):
            value = getattr(changes, field_name)
            if value is not None:
                values[field_name] = value
        values["profile_version"] = self.record.profile_version + 1
        self.record = replace(self.record, **values)
        self.update_count += 1
        return self.record.profile_version, now

    def disable_user_for_age(self, session: FakeSession, user_id: UUID, now: datetime) -> None:
        del session, user_id, now
        self.disabled = True


def _record(protected_birthdate: str) -> ProfileSettingsRecord:
    return ProfileSettingsRecord(
        protected_birthdate=protected_birthdate,
        nickname="러너01",
        primary_goal_code="GENERAL_FITNESS",
        experience_level_code="BEGINNER",
        timezone="Asia/Seoul",
        preferred_location_code="HOME",
        available_location_codes=("GYM", "HOME"),
        default_requested_duration_minutes=40,
        desired_weekly_workout_count=3,
        coaching_style_code="SUPPORTIVE",
        height_cm=172.0,
        weight_kg=68.5,
        sex_code="FEMALE",
        equipment_codes=("BODYWEIGHT",),
        attention_area_codes=("KNEE",),
        preferred_exercise_type_codes=("STRENGTH",),
        profile_version=1,
    )


def _client(
    *,
    has_profile: bool = True,
    configured: bool = True,
    authenticated: bool = True,
) -> tuple[TestClient, FakeProfileSettingsRepository]:
    user_id = uuid4()
    cipher = LocalAesGcmBirthdateCipher(b"s" * 32, key_id="test-v1", app_env="test")
    repository = FakeProfileSettingsRepository(
        _record(cipher.encrypt(user_id, date(2000, 8, 11))) if has_profile else None
    )
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        consent_policy_version="privacy-v1",
        onboarding_primary_goal_codes=("GENERAL_FITNESS", "MUSCLE_GAIN") if configured else (),
        onboarding_experience_level_codes=("BEGINNER", "INTERMEDIATE") if configured else (),
    )
    app = create_app(
        settings=settings,
        readiness_probe=lambda: None,
        birthdate_cipher=cipher,
    )
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=user_id,
            status_code=UserStatusCode.ACTIVE,
        )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_profile_repository] = lambda: repository
    return TestClient(app), repository


def _headers(*, key: str | None = None, version: str = '"1"') -> dict[str, str]:
    return {
        "Idempotency-Key": key or str(uuid4()),
        "If-Match": version,
    }


def _assert_common_error(response: Any, *, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "details", "request_id"}
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]
    assert payload["error"]["details"] == []
    UUID(payload["error"]["request_id"])
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "payload",
    [
        {"primary_goal_code": "MUSCLE_GAIN"},
        {"desired_weekly_workout_count": 5},
        {"default_requested_duration_minutes": 60},
        {"preferred_location_code": "GYM"},
        {"available_location_codes": ["HOME", "OUTDOOR"]},
        {"equipment_codes": ["MAT"]},
        {"attention_area_codes": []},
        {"preferred_exercise_type_codes": ["CARDIO"]},
        {"coaching_style_code": "CONCISE"},
        {"experience_level_code": "INTERMEDIATE"},
        {"nickname": "새 닉네임"},
        {"height_cm": 180.5},
        {"weight_kg": 75.0},
        {"sex_code": "PREFER_NOT_TO_SAY"},
        {"timezone": "UTC"},
        {"date_of_birth": "1999-01-02"},
    ],
)
def test_each_supported_field_can_be_updated_independently(
    payload: dict[str, object],
) -> None:
    client, repository = _client()
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code == 200
    assert response.json()["profile_version"] == 2
    assert set(response.json()) == {"profile_version", "updated_at"}
    assert repository.update_count == 1


def test_multiple_fields_update_without_resetting_omitted_values() -> None:
    client, repository = _client()
    original_equipment = repository.record.equipment_codes if repository.record else ()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"nickname": "변경", "desired_weekly_workout_count": 4},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert repository.record is not None
    assert repository.record.nickname == "변경"
    assert repository.record.desired_weekly_workout_count == 4
    assert repository.record.equipment_codes == original_equipment


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"unknown": "value"},
        {"nickname": None},
        {"equipment_codes": []},
        {"equipment_codes": ["MAT", "MAT"]},
        {"attention_area_codes": ["KNEE", "KNEE"]},
    ],
)
def test_invalid_patch_payload_is_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code in {400, 422}
    assert repository.update_count == 0


def test_empty_attention_areas_are_allowed() -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"attention_area_codes": []},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert repository.record is not None
    assert repository.record.attention_area_codes == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"available_location_codes": ["GYM"]},
        {"preferred_location_code": "OUTDOOR"},
    ],
)
def test_invalid_final_location_combination_is_rejected(
    payload: dict[str, object],
) -> None:
    client, repository = _client()
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert repository.update_count == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"primary_goal_code": "UNAPPROVED"},
        {"experience_level_code": "ADVANCED"},
    ],
)
def test_unapproved_configured_codes_are_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ONBOARDING_CODE"
    assert repository.update_count == 0


def test_missing_approved_code_configuration_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, repository = _client(configured=False)
    with caplog.at_level(logging.ERROR, logger="backend.profile"):
        with client:
            response = client.patch(
                "/api/v1/me/profile", json={"nickname": "변경"}, headers=_headers()
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROFILE_CONFIGURATION_UNAVAILABLE"
    assert repository.update_count == 0
    records = [
        record
        for record in caplog.records
        if getattr(record, "event_code", None) == "PROFILE_CONFIGURATION_UNAVAILABLE"
    ]
    assert len(records) == 1
    assert records[0].missing_keys == [
        "ONBOARDING_PRIMARY_GOAL_CODES",
        "ONBOARDING_EXPERIENCE_LEVEL_CODES",
    ]
    assert records[0].request_id == response.headers["X-Request-ID"]


def test_if_match_is_required_and_uses_common_error_schema() -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"nickname": "변경"},
            headers={"Idempotency-Key": str(uuid4())},
        )

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    assert repository.record == before
    assert repository.update_count == 0


@pytest.mark.parametrize("version", ["", "1", 'W/"1"', '"0"', '"-1"', '"abc"'])
def test_if_match_must_be_a_quoted_positive_integer(version: str) -> None:
    client, repository = _client()
    headers = {"Idempotency-Key": str(uuid4()), "If-Match": version}
    with client:
        response = client.patch("/api/v1/me/profile", json={"nickname": "변경"}, headers=headers)

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    assert repository.update_count == 0


@pytest.mark.parametrize("idempotency_key", [None, "not-a-uuid"])
def test_idempotency_key_must_be_a_uuid(idempotency_key: str | None) -> None:
    client, repository = _client()
    headers = {"If-Match": '"1"'}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    with client:
        response = client.patch("/api/v1/me/profile", json={"nickname": "변경"}, headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert repository.update_count == 0


def test_stale_profile_changes_nothing() -> None:
    client, repository = _client()
    before = repository.record
    assert before is not None
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"equipment_codes": ["MAT"]},
            headers=_headers(version='"2"'),
        )

    _assert_common_error(response, status_code=409, code="STALE_PROFILE")
    assert repository.record == before
    assert repository.record.profile_version == before.profile_version
    assert repository.update_count == 0


def test_matching_if_match_increments_profile_version() -> None:
    client, repository = _client()
    assert repository.record is not None
    before_version = repository.record.profile_version
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"nickname": "변경"},
            headers=_headers(version=f'"{before_version}"'),
        )

    assert response.status_code == 200
    assert response.json()["profile_version"] == before_version + 1
    assert repository.record is not None
    assert repository.record.profile_version == before_version + 1
    assert repository.update_count == 1


def test_idempotent_retry_replays_response_without_incrementing_version() -> None:
    client, repository = _client()
    key = str(uuid4())
    with client:
        first = client.patch(
            "/api/v1/me/profile",
            json={"nickname": "변경"},
            headers=_headers(key=key),
        )
        second = client.patch(
            "/api/v1/me/profile",
            json={"nickname": "변경"},
            headers=_headers(key=key),
        )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert repository.update_count == 1
    assert repository.record is not None
    assert repository.record.profile_version == 2


@pytest.mark.parametrize(
    ("second_payload", "second_version"),
    [({"nickname": "다른 값"}, '"1"'), ({"nickname": "변경"}, '"2"')],
)
def test_idempotency_key_reuse_with_different_request_is_rejected(
    second_payload: dict[str, object], second_version: str
) -> None:
    client, repository = _client()
    key = str(uuid4())
    with client:
        first = client.patch(
            "/api/v1/me/profile",
            json={"nickname": "변경"},
            headers=_headers(key=key),
        )
        second = client.patch(
            "/api/v1/me/profile",
            json=second_payload,
            headers=_headers(key=key, version=second_version),
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert repository.update_count == 1


def test_user_without_onboarding_profile_gets_not_found() -> None:
    client, repository = _client(has_profile=False)
    with client:
        response = client.patch("/api/v1/me/profile", json={"nickname": "변경"}, headers=_headers())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert repository.update_count == 0


def test_underage_birthdate_disables_account_without_exposing_value() -> None:
    client, repository = _client()
    secret_birthdate = "2020-01-01"
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"date_of_birth": secret_birthdate},
            headers=_headers(),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGE_REQUIREMENT_NOT_MET"
    assert secret_birthdate not in response.text
    assert repository.disabled is True
    assert repository.update_count == 0


def test_timezone_is_revalidated_with_existing_birthdate() -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"timezone": "Not/A_Zone"},
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TIMEZONE"
    assert repository.update_count == 0


def test_health_values_are_not_reflected_in_error_response() -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"weight_kg": 999.123, "attention_area_codes": ["KNEE"]},
            headers=_headers(),
        )

    assert response.status_code in {400, 422}
    assert "999.123" not in response.text
    assert "KNEE" not in response.text
    assert repository.update_count == 0


def test_unauthenticated_request_is_rejected() -> None:
    client, repository = _client(authenticated=False)
    with client:
        response = client.patch("/api/v1/me/profile", json={"nickname": "변경"}, headers=_headers())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert repository.update_count == 0
