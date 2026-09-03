import logging
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_profile_repository,
    get_routine_repository,
)
from backend.app.core.config import Settings
from backend.app.integrations.birthdate_crypto import LocalAesGcmBirthdateCipher
from backend.app.main import create_app
from backend.app.modules.catalog.codes import (
    BodyAreaCode,
    LocationCode,
    TrainingTypeCode,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.profiles.codes import CoachingStyleCode, MutationEndpointCode
from backend.app.modules.profiles.ports import (
    IdempotencyRecord,
    ProfileSettingsChanges,
    ProfileSettingsRecord,
)

NOW = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
SUPPORTED_PROFILE_UPDATE_FIELDS = {
    "primary_goal_code",
    "desired_weekly_workout_count",
    "default_requested_duration_minutes",
    "preferred_location_code",
    "available_location_codes",
    "attention_area_codes",
    "preferred_exercise_type_codes",
    "coaching_style_code",
    "experience_level_code",
    "nickname",
    "height_cm",
    "weight_kg",
    "sex_code",
    "timezone",
    "date_of_birth",
    "persistent_pains",
}


class FakeSession:
    def begin(self) -> nullcontext[None]:
        return nullcontext()


class FakeProfileSettingsRepository:
    def __init__(self, record: ProfileSettingsRecord | None) -> None:
        self.record = record
        self.idempotency: dict[tuple[UUID, MutationEndpointCode, UUID], IdempotencyRecord] = {}
        self.update_count = 0
        self.disabled = False
        self.persistent_pains: tuple[tuple[str, int], ...] = ()

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
            "attention_area_codes",
            "preferred_exercise_type_codes",
        ):
            value = getattr(changes, field_name)
            if value is not None:
                values[field_name] = value
        if changes.persistent_pains is not None:
            self.persistent_pains = changes.persistent_pains
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
    stale_routines = FakeStaleRoutines()
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
    app.dependency_overrides[get_routine_repository] = lambda: stale_routines
    return TestClient(app), repository


def test_changing_the_default_duration_retires_the_stale_routine() -> None:
    # The stored routine was built to the old default. Leaving it active makes
    # every daily decision reject it and the user sees REST with no way out.
    client, _ = _client()
    stale = client.app.dependency_overrides[get_routine_repository]()

    response = client.patch(
        "/api/v1/me/profile",
        json={"default_requested_duration_minutes": 45},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert stale.archived_for == [45]


def test_editing_other_fields_leaves_the_routine_alone() -> None:
    client, _ = _client()
    stale = client.app.dependency_overrides[get_routine_repository]()

    response = client.patch(
        "/api/v1/me/profile",
        json={"desired_weekly_workout_count": 3},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert stale.archived_for == []


class FakeStaleRoutines:
    """Records what the profile edit asked to retire, without a database."""

    def __init__(self) -> None:
        self.archived_for: list[int] = []

    def archive_routines_with_other_duration(
        self, session: Any, user_id: UUID, *, requested_duration_minutes: int
    ) -> int:
        del session, user_id
        self.archived_for.append(requested_duration_minutes)
        return 1


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
    assert isinstance(payload["error"]["details"], list)
    assert all(
        set(detail) == {"field", "type"}
        and isinstance(detail["field"], str)
        and isinstance(detail["type"], str)
        for detail in payload["error"]["details"]
    )
    UUID(payload["error"]["request_id"])
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def _assert_repository_unchanged(
    repository: FakeProfileSettingsRepository,
    before: ProfileSettingsRecord | None,
) -> None:
    assert repository.record == before
    if before is not None:
        assert repository.record is not None
        assert repository.record.profile_version == before.profile_version
    assert repository.update_count == 0


def _schema_allows_null(schema: dict[str, Any]) -> bool:
    if schema.get("type") == "null":
        return True
    return any(
        _schema_allows_null(child)
        for keyword in ("anyOf", "oneOf")
        for child in schema.get(keyword, [])
    )


def _years_ago(local_date: date, years: int) -> date:
    try:
        return local_date.replace(year=local_date.year - years)
    except ValueError:
        return local_date.replace(year=local_date.year - years, day=28)


def test_openapi_exposes_exactly_the_supported_non_null_fields() -> None:
    client, _ = _client()
    schema = client.app.openapi()["components"]["schemas"]["ProfileSettingsUpdateRequest"]

    assert set(schema["properties"]) == SUPPORTED_PROFILE_UPDATE_FIELDS
    assert schema.get("required", []) == []
    assert not any(_schema_allows_null(field) for field in schema["properties"].values())


@pytest.mark.parametrize(
    "payload",
    [
        {"primary_goal_code": "MUSCLE_GAIN"},
        {"desired_weekly_workout_count": 5},
        {"default_requested_duration_minutes": 60},
        {"preferred_location_code": "GYM"},
        {"available_location_codes": ["HOME", "OUTDOOR"]},
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
        {"persistent_pains": [{"body_area_code": "KNEE", "intensity_score": 3}]},
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
    before = repository.record
    assert before is not None
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
    assert repository.record == replace(
        before,
        nickname="변경",
        desired_weekly_workout_count=4,
        profile_version=before.profile_version + 1,
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("desired_weekly_workout_count", 1),
        ("desired_weekly_workout_count", 7),
        ("default_requested_duration_minutes", 1),
        ("default_requested_duration_minutes", 240),
        ("height_cm", 80),
        ("height_cm", 250),
        ("weight_kg", 25),
        ("weight_kg", 300),
    ],
)
def test_numeric_boundaries_are_accepted(field_name: str, value: int) -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={field_name: value},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert repository.record is not None
    assert getattr(repository.record, field_name) == value
    assert repository.record.profile_version == 2


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("desired_weekly_workout_count", 0),
        ("desired_weekly_workout_count", 8),
        ("default_requested_duration_minutes", 0),
        ("default_requested_duration_minutes", 241),
        ("height_cm", 79.9),
        ("height_cm", 250.1),
        ("weight_kg", 24.9),
        ("weight_kg", 300.1),
    ],
)
def test_values_outside_numeric_boundaries_are_rejected(
    field_name: str,
    value: float,
) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={field_name: value},
            headers=_headers(),
        )

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize(
    "payload",
    [
        *(
            {
                "preferred_location_code": code.value,
                "available_location_codes": [code.value],
            }
            for code in LocationCode
        ),
        {"attention_area_codes": [code.value for code in BodyAreaCode]},
        {"preferred_exercise_type_codes": [code.value for code in TrainingTypeCode]},
        *({"coaching_style_code": code.value} for code in CoachingStyleCode),
        *({"sex_code": code} for code in ("FEMALE", "MALE", "PREFER_NOT_TO_SAY")),
    ],
)
def test_all_declared_enum_values_are_accepted(payload: dict[str, object]) -> None:
    client, repository = _client()
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code == 200
    assert repository.update_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"primary_goal_code": "not-valid"},
        {"experience_level_code": "not-valid"},
        {"preferred_location_code": "NOT_A_CODE"},
        {"available_location_codes": ["NOT_A_CODE"]},
        {"attention_area_codes": ["NOT_A_CODE"]},
        {"preferred_exercise_type_codes": ["NOT_A_CODE"]},
        {"coaching_style_code": "NOT_A_CODE"},
        {"sex_code": "NOT_A_CODE"},
    ],
)
def test_invalid_enum_and_code_values_are_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"unknown": "value"},
        {"equipment_codes": ["MAT"]},
    ],
)
def test_invalid_patch_payload_is_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize("field_name", sorted(SUPPORTED_PROFILE_UPDATE_FIELDS))
def test_explicit_null_is_rejected_for_every_supported_field(field_name: str) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={field_name: None},
            headers=_headers(),
        )

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize(
    "payload",
    [
        {"attention_area_codes": ["KNEE", "KNEE"]},
        {"available_location_codes": ["HOME", "HOME"]},
        {"preferred_exercise_type_codes": ["CARDIO", "CARDIO"]},
    ],
)
def test_duplicate_array_codes_are_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize(
    "payload",
    [{"available_location_codes": []}],
)
def test_arrays_that_must_retain_values_reject_empty_lists(
    payload: dict[str, object],
) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


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


def test_empty_preferred_exercise_types_are_allowed() -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"preferred_exercise_type_codes": []},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert repository.record is not None
    assert repository.record.preferred_exercise_type_codes == ()


def test_persistent_pains_can_be_replaced_or_cleared() -> None:
    client, repository = _client()
    with client:
        first = client.patch(
            "/api/v1/me/profile",
            json={"persistent_pains": [{"body_area_code": "KNEE", "intensity_score": 3}]},
            headers=_headers(),
        )
        assert repository.persistent_pains == (("KNEE", 3),)
        cleared = client.patch(
            "/api/v1/me/profile",
            json={"persistent_pains": []},
            headers=_headers(version='"2"'),
        )

    assert first.status_code == 200
    assert repository.persistent_pains == ()
    assert cleared.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"persistent_pains": [{"body_area_code": "KNEE", "intensity_score": 0}]},
        {"persistent_pains": [{"body_area_code": "KNEE", "intensity_score": 11}]},
        {
            "persistent_pains": [
                {"body_area_code": "KNEE", "intensity_score": 3},
                {"body_area_code": "KNEE", "intensity_score": 4},
            ]
        },
    ],
)
def test_invalid_persistent_pains_are_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


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
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize(
    "payload",
    [
        {"primary_goal_code": "UNAPPROVED"},
        {"experience_level_code": "ADVANCED"},
    ],
)
def test_unapproved_configured_codes_are_rejected(payload: dict[str, object]) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch("/api/v1/me/profile", json=payload, headers=_headers())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ONBOARDING_CODE"
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize("normalized", ["가", "가" * 64])
def test_nickname_is_trimmed_before_the_length_limit_is_applied(normalized: str) -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"nickname": f"  {normalized}  "},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert repository.record is not None
    assert repository.record.nickname == normalized


@pytest.mark.parametrize("nickname", ["", "   ", "가" * 65])
def test_blank_or_too_long_normalized_nickname_is_rejected(nickname: str) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"nickname": nickname},
            headers=_headers(),
        )

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    _assert_repository_unchanged(repository, before)


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
            json={"nickname": "stale 변경"},
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


def test_out_of_scope_birthdate_does_not_change_existing_account_status() -> None:
    client, repository = _client()
    local_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
    secret_birthdate = (_years_ago(local_date, 18) + timedelta(days=1)).isoformat()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"date_of_birth": secret_birthdate},
            headers=_headers(),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "OUT_OF_SCOPE_AGE"
    assert secret_birthdate not in response.text
    assert repository.disabled is False
    _assert_repository_unchanged(repository, before)


def test_exact_minimum_age_birthdate_is_accepted_without_reflecting_it() -> None:
    client, repository = _client()
    local_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
    boundary_birthdate = _years_ago(local_date, 18).isoformat()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"date_of_birth": boundary_birthdate},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert boundary_birthdate not in response.text
    assert repository.record is not None
    assert repository.record.profile_version == 2
    assert repository.disabled is False


@pytest.mark.parametrize(
    "invalid_birthdate",
    [
        "not-a-date",
        (datetime.now(ZoneInfo("Asia/Seoul")).date() + timedelta(days=1)).isoformat(),
    ],
)
def test_invalid_birthdate_is_rejected_without_reflecting_it(
    invalid_birthdate: str,
) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"date_of_birth": invalid_birthdate},
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DATE_OF_BIRTH"
    assert invalid_birthdate not in response.text
    _assert_repository_unchanged(repository, before)


def test_valid_iana_timezone_is_stored() -> None:
    client, repository = _client()
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"timezone": "America/New_York"},
            headers=_headers(),
        )

    assert response.status_code == 200
    assert repository.record is not None
    assert repository.record.timezone == "America/New_York"


def test_timezone_is_revalidated_with_existing_birthdate() -> None:
    client, repository = _client()
    before = repository.record
    invalid_timezone = "Not/A_Zone"
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json={"timezone": invalid_timezone},
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TIMEZONE"
    assert invalid_timezone not in response.text
    _assert_repository_unchanged(repository, before)


@pytest.mark.parametrize(
    ("payload", "sensitive_values"),
    [
        ({"weight_kg": 999.123, "attention_area_codes": ["KNEE"]}, ("999.123", "KNEE")),
        ({"height_cm": 999.456}, ("999.456",)),
    ],
)
def test_health_values_are_not_reflected_in_error_response(
    payload: dict[str, object],
    sensitive_values: tuple[str, ...],
) -> None:
    client, repository = _client()
    before = repository.record
    with client:
        response = client.patch(
            "/api/v1/me/profile",
            json=payload,
            headers=_headers(),
        )

    _assert_common_error(response, status_code=400, code="INVALID_REQUEST")
    assert all(value not in response.text for value in sensitive_values)
    _assert_repository_unchanged(repository, before)


def test_unauthenticated_request_is_rejected() -> None:
    client, repository = _client(authenticated=False)
    with client:
        response = client.patch("/api/v1/me/profile", json={"nickname": "변경"}, headers=_headers())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert repository.update_count == 0
