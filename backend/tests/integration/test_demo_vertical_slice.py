"""End-to-end vertical slice over real PostgreSQL and the real FastAPI stack.

Unlike `backend/tests/api/*`, nothing here is faked except the Firebase token
verifier: the app talks to a real database through the real repositories, so
this is the test that proves the demo journey actually runs.

The verifier stub stands in for Firebase only. It is a test seam on
`create_app`, not a product auth bypass: the app still requires a bearer token
and still resolves it through the normal identity service.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models.catalog import (
    BodyArea,
    BodyFocus,
    CatalogVersion,
    Equipment,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.db.models.decision import DecisionRun
from backend.app.db.models.identity import User
from backend.app.db.models.profile import UserProfile
from backend.app.db.models.routine import Routine
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.integrations.birthdate_crypto import LocalAesGcmBirthdateCipher
from backend.app.main import create_app
from backend.app.modules.identity.ports import VerifiedFirebaseIdentity
from backend.scripts.demo_seed import (
    DEMO_CATALOG_VERSION_CODE,
    _require_demo_database,
    reset_users,
    seed_catalog,
)

ALEMBIC_CONFIG = Path("backend/alembic.ini")
LOCAL_DATE = date(2026, 8, 17)
DEMO_TIMEZONE = "Asia/Seoul"


class StubFirebaseVerifier:
    """Return a fixed synthetic subject; never a real Firebase credential."""

    def __init__(self, subject: str) -> None:
        self._subject = subject

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        if not token.strip():
            raise ValueError("token must not be blank")
        return VerifiedFirebaseIdentity(firebase_subject=self._subject)


def _database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(database_url).database or "").endswith("_test"):
        pytest.fail("Demo vertical slice tests require a dedicated *_test database")
    return database_url


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    database_url = _database_url()
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    created = create_engine(database_url)
    try:
        yield created
    finally:
        # Sibling integration modules insert the same lookup codes and assume an
        # empty catalog, so this module has to leave the database as it found it.
        try:
            with Session(created) as session, session.begin():
                reset_users(session)
                session.execute(
                    delete(CatalogVersion).where(
                        CatalogVersion.version_code == DEMO_CATALOG_VERSION_CODE
                    )
                )
                for model in (
                    TrainingType,
                    BodyFocus,
                    MovementPattern,
                    Equipment,
                    Location,
                    BodyArea,
                ):
                    session.execute(delete(model))
        finally:
            created.dispose()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    with Session(engine) as session, session.begin():
        # Start from a clean slate: user rows cascade to routines and decisions,
        # which hold RESTRICT references to the catalog.
        reset_users(session)
        seed_catalog(session, datetime.now(UTC))

    settings = Settings(
        app_env="test",
        database_url=engine.url.render_as_string(hide_password=False),
        consent_policy_version="demo-consent-v1",
        onboarding_primary_goal_codes=("GENERAL_FITNESS",),
        onboarding_experience_level_codes=("BEGINNER",),
    )
    application = create_app(
        settings=settings,
        readiness_probe=lambda: None,
        firebase_token_verifier=StubFirebaseVerifier(f"synthetic-subject-{uuid4()}"),
        birthdate_cipher=LocalAesGcmBirthdateCipher(
            base64.b64decode(base64.b64encode(b"0" * 32)),
            key_id="local-v1",
            app_env="test",
        ),
    )
    with TestClient(application) as created:
        created.headers["Authorization"] = "Bearer synthetic-demo-token"
        yield created

    with Session(engine) as session, session.begin():
        reset_users(session)


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _current_week_start() -> date:
    local_today = datetime.now(ZoneInfo(DEMO_TIMEZONE)).date()
    return local_today - timedelta(days=local_today.weekday())


def _onboard(client: TestClient, *, duration_minutes: int = 30) -> dict[str, object]:
    response = client.put(
        "/api/v1/me/onboarding",
        headers=_key(),
        json={
            "nickname": "데모사용자",
            "date_of_birth": "1997-08-11",
            "medical_exercise_restriction": False,
            "terms_version": "terms-v1.0.0",
            "primary_goal_code": "GENERAL_FITNESS",
            "experience_level_code": "BEGINNER",
            "timezone": DEMO_TIMEZONE,
            "preferred_location_code": "HOME",
            "available_location_codes": ["HOME"],
            "default_requested_duration_minutes": duration_minutes,
            "desired_weekly_workout_count": 3,
            "attention_area_codes": [],
            "preferred_exercise_type_codes": ["STRENGTH"],
            "coaching_style_code": "SUPPORTIVE",
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
        },
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _create_routine(
    client: TestClient,
    *,
    effective_from: date = LOCAL_DATE,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/routines",
        headers=_key(),
        json={"effective_from": effective_from.isoformat(), "goal_code": "GENERAL_FITNESS"},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _check_in(
    client: TestClient,
    *,
    local_date: date = LOCAL_DATE,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "fatigue_level_code": "MODERATE",
        "requested_duration_minutes": 30,
        "duration_adjustment_source_code": "PROFILE",
        "location_code": "HOME",
        "discomforts": [],
        "adverse_reaction_codes": [],
    }
    payload.update(overrides)
    response = client.put(
        f"/api/v1/daily-contexts/{local_date.isoformat()}",
        headers=_key(),
        json=payload,
    )
    assert response.status_code in {200, 201}, response.text
    return dict(response.json())


def _decide(
    client: TestClient,
    context: dict[str, object],
    *,
    local_date: date = LOCAL_DATE,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/decisions",
        headers=_key(),
        json={
            "local_date": local_date.isoformat(),
            "daily_context_id": context["id"],
            "expected_context_version": context["context_version"],
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_onboarding_provisions_base_routine_without_creating_a_daily_decision(
    client: TestClient, engine: Engine
) -> None:
    onboarding = _onboard(client)
    assert onboarding["onboarding_completed"] is True

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Routine)) == 1
        assert session.scalar(select(func.count()).select_from(DecisionRun)) == 0
        today = session.scalar(select(Routine.effective_from))
        assert today is not None

    current = client.get("/api/v1/routines/current", params={"local_date": today.isoformat()})
    assert current.status_code == 200, current.text

    context = _check_in(client, local_date=today)
    decision = _decide(client, context, local_date=today)
    assert decision["status_code"] == "COMPLETED"

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(DecisionRun)) == 1


def test_onboarding_rolls_back_when_initial_base_routine_cannot_be_created(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RoutineRepository, "get_creation_context", lambda *args: None)

    response = client.put(
        "/api/v1/me/onboarding",
        headers=_key(),
        json={
            "nickname": "rollback-user",
            "date_of_birth": "1997-08-11",
            "medical_exercise_restriction": False,
            "terms_version": "terms-v1.0.0",
            "primary_goal_code": "GENERAL_FITNESS",
            "experience_level_code": "BEGINNER",
            "timezone": DEMO_TIMEZONE,
            "preferred_location_code": "HOME",
            "available_location_codes": ["HOME"],
            "default_requested_duration_minutes": 30,
            "desired_weekly_workout_count": 3,
            "attention_area_codes": [],
            "preferred_exercise_type_codes": ["STRENGTH"],
            "coaching_style_code": "SUPPORTIVE",
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
        },
    )

    assert response.status_code == 503
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserProfile)) == 0
        assert session.scalar(select(func.count()).select_from(Routine)) == 0


def test_full_vertical_slice_reaches_completed_session(client: TestClient) -> None:
    """Onboarding through explicit block completion, over the real database."""
    onboarding = _onboard(client)
    assert onboarding["onboarding_completed"] is True

    me = client.get("/api/v1/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["onboarding_completed"] is True
    assert body["profile"]["nickname"] == "데모사용자"
    assert body["profile"]["age"] == 29
    assert "equipment_codes" not in body["profile"]
    # The birthdate itself must never travel back to the client.
    assert "date_of_birth" not in body["profile"]
    assert "protected_birthdate" not in body["profile"]

    routine = _create_routine(client)
    day = routine["days"][0]
    assert day["estimated_duration_seconds"] == day["requested_duration_minutes"] * 60

    current = client.get("/api/v1/routines/current", params={"local_date": LOCAL_DATE.isoformat()})
    assert current.status_code == 200, current.text

    context = _check_in(client)
    decision = _decide(client, context)
    assert decision["status_code"] == "COMPLETED"
    assert decision["safety_status_code"] in {"PASS", "REVISE"}
    assert decision["final_plan"] is not None

    plan = decision["final_plan"]
    assert plan["estimated_duration_seconds"] == plan["requested_duration_minutes"] * 60

    routine_option = next(
        option for option in decision["options"] if option["option_code"] == "FINAL_ROUTINE"
    )
    selection = client.post(
        f"/api/v1/decisions/{decision['decision_id']}/selection",
        headers=_key(),
        json={"option_id": routine_option["option_id"]},
    )
    assert selection.status_code in {200, 201}, selection.text
    session_id = selection.json()["workout_session"]["session_id"]

    started = client.patch(
        f"/api/v1/workout-sessions/{session_id}/start",
        headers=_key(),
        json={"started_at": "2026-08-17T10:00:00+09:00"},
    )
    assert started.status_code == 200, started.text
    item_ids = [item["plan_item_id"] for item in started.json()["items"]]
    assert item_ids

    # Elapsed time must not be able to finish a session on its own.
    premature = client.patch(
        f"/api/v1/workout-sessions/{session_id}/finish",
        headers=_key(),
        json={"finished_at": "2026-08-17T10:40:00+09:00", "actual_elapsed_seconds": 2400},
    )
    assert premature.status_code == 409, premature.text

    for index, plan_item_id in enumerate(item_ids, start=1):
        updated = client.patch(
            f"/api/v1/workout-sessions/{session_id}/items/{plan_item_id}",
            headers=_key(),
            json={"status_code": "COMPLETED", "client_recorded_at": "2026-08-17T10:05:00+09:00"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["completed_item_count"] == index

    finished = client.patch(
        f"/api/v1/workout-sessions/{session_id}/finish",
        headers=_key(),
        json={"finished_at": "2026-08-17T10:40:00+09:00", "actual_elapsed_seconds": 2400},
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["status_code"] == "COMPLETED"

    feedback = client.post(
        f"/api/v1/workout-sessions/{session_id}/feedback",
        headers=_key(),
        json={
            "difficulty_code": "APPROPRIATE",
            "pain_occurred": False,
            "discomforts": [],
            "adverse_reaction_codes": [],
        },
    )
    assert feedback.status_code == 201, feedback.text


def test_partial_session_requires_at_least_one_completed_block(client: TestClient) -> None:
    _onboard(client)
    _create_routine(client)
    decision = _decide(client, _check_in(client))
    option = next(
        option for option in decision["options"] if option["option_code"] == "FINAL_ROUTINE"
    )
    selection = client.post(
        f"/api/v1/decisions/{decision['decision_id']}/selection",
        headers=_key(),
        json={"option_id": option["option_id"]},
    )
    session_id = selection.json()["workout_session"]["session_id"]
    started = client.patch(
        f"/api/v1/workout-sessions/{session_id}/start",
        headers=_key(),
        json={"started_at": "2026-08-17T10:00:00+09:00"},
    )
    first_item = started.json()["items"][0]["plan_item_id"]

    client.patch(
        f"/api/v1/workout-sessions/{session_id}/items/{first_item}",
        headers=_key(),
        json={"status_code": "COMPLETED", "client_recorded_at": "2026-08-17T10:05:00+09:00"},
    )
    finished = client.patch(
        f"/api/v1/workout-sessions/{session_id}/finish",
        headers=_key(),
        json={"finished_at": "2026-08-17T10:20:00+09:00", "actual_elapsed_seconds": 1200},
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["status_code"] == "PARTIAL"


def test_severe_discomfort_blocks_plan_and_offers_rest(client: TestClient) -> None:
    """A safety veto must survive into the response with no plan attached."""
    _onboard(client)
    _create_routine(client)
    context = _check_in(
        client,
        discomforts=[{"body_area_code": "KNEE", "severity_code": "SEVERE"}],
    )
    decision = _decide(client, context)

    assert decision["safety_status_code"] == "BLOCKED"
    assert decision["action_code"] in {"REST", "STOP_AND_SEEK_HELP"}
    assert decision["final_plan"] is None
    assert decision["guidance"] is not None
    assert all(option["option_code"] != "FINAL_ROUTINE" for option in decision["options"])


def test_adverse_reaction_returns_serious_stop_guidance(client: TestClient) -> None:
    _onboard(client)
    _create_routine(client)
    context = _check_in(client, adverse_reaction_codes=["CHEST_DISCOMFORT"])
    decision = _decide(client, context)

    assert decision["action_code"] == "STOP_AND_SEEK_HELP"
    assert decision["final_plan"] is None
    assert decision["options"] == []
    assert decision["guidance"]["tone_code"] == "SERIOUS"
    # A serious safety screen must not carry playful mascot animation.
    assert "mascot_animation_asset_key" not in decision["guidance"]


def test_in_session_severe_report_stops_session_and_blocks_pressure(client: TestClient) -> None:
    _onboard(client)
    _create_routine(client)
    decision = _decide(client, _check_in(client))
    option = next(
        option for option in decision["options"] if option["option_code"] == "FINAL_ROUTINE"
    )
    selection = client.post(
        f"/api/v1/decisions/{decision['decision_id']}/selection",
        headers=_key(),
        json={"option_id": option["option_id"]},
    )
    session_id = selection.json()["workout_session"]["session_id"]
    client.patch(
        f"/api/v1/workout-sessions/{session_id}/start",
        headers=_key(),
        json={"started_at": "2026-08-17T10:00:00+09:00"},
    )

    reported = client.post(
        f"/api/v1/workout-sessions/{session_id}/safety-events",
        headers=_key(),
        json={"stop_reason_code": "PAIN_OR_ABNORMAL_RESPONSE"},
    )
    assert reported.status_code in {200, 201}, reported.text
    body = reported.json()
    # The stop reason is the whole input; no symptom detail is collected, so this path
    # always ends in SESSION_STOPPED.
    assert body["result_code"] == "SESSION_STOPPED"
    assert body["execution_state_code"] == "STOPPED_SAFETY"
    assert body["completion_code"] in {"PARTIAL", "NOT_COMPLETED"}
    # The stop is what suppresses same-day pressure: the session is terminal and the app
    # offers no resume, skip-and-continue or alternative for the rest of the day.
    assert body["is_resumable"] is False

    detail = client.get(f"/api/v1/workout-sessions/{session_id}", headers=_key())
    assert detail.status_code == 200, detail.text
    assert detail.json()["status_code"] == "STOPPED_FOR_SAFETY"


def test_rest_selection_suppresses_pressure_and_creates_no_session(client: TestClient) -> None:
    _onboard(client)
    _create_routine(client)
    decision = _decide(client, _check_in(client))
    rest_option = next(
        (option for option in decision["options"] if option["option_code"] == "REST"),
        None,
    )
    if rest_option is None:
        pytest.skip("this decision did not offer a REST opt-out")

    selection = client.post(
        f"/api/v1/decisions/{decision['decision_id']}/selection",
        headers=_key(),
        json={"option_id": rest_option["option_id"]},
    )
    assert selection.status_code in {200, 201}, selection.text
    body = selection.json()
    assert body["selected_action_code"] == "REST"
    assert body["workout_session"] is None
    assert body["pressure_notifications_allowed"] is False


def test_stale_context_version_is_rejected(client: TestClient) -> None:
    _onboard(client)
    _create_routine(client)
    context = _check_in(client)
    refreshed = client.put(
        f"/api/v1/daily-contexts/{LOCAL_DATE.isoformat()}",
        headers={**_key(), "If-Match": f'"{context["context_version"]}"'},
        json={
            "fatigue_level_code": "HIGH",
            "requested_duration_minutes": 30,
            "duration_adjustment_source_code": "PROFILE",
            "location_code": "HOME",
            "discomforts": [],
            "adverse_reaction_codes": [],
        },
    )
    assert refreshed.status_code == 200, refreshed.text

    stale = client.post(
        "/api/v1/decisions",
        headers=_key(),
        json={
            "local_date": LOCAL_DATE.isoformat(),
            "daily_context_id": context["id"],
            "expected_context_version": context["context_version"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_CONTEXT"


def test_exercise_detail_returns_reviewed_instruction_content(client: TestClient) -> None:
    _onboard(client)
    routine = _create_routine(client)
    exercise_id = routine["days"][0]["items"][0]["exercise_id"]

    detail = client.get(f"/api/v1/exercises/{exercise_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["exercise_id"] == exercise_id
    assert body["instruction_summary"]
    assert isinstance(body["form_cues"], list)
    assert body["instruction_content_version"]

    missing = client.get(f"/api/v1/exercises/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_me_reports_pre_onboarding_state(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["onboarding_completed"] is False
    assert body["profile"] is None


def test_unauthenticated_request_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers={"Authorization": ""})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_weekly_report_gate_requires_closed_week(client: TestClient) -> None:
    _onboard(client)
    week_start = _current_week_start().isoformat()
    week = client.get(f"/api/v1/weeks/{week_start}")
    assert week.status_code == 200, week.text
    assert week.json()["week_start"] == week_start

    report = client.post(
        f"/api/v1/weeks/{week_start}/report",
        headers=_key(),
        json={"expected_week_status_code": "CLOSED"},
    )
    assert report.status_code == 409
    assert report.json()["error"]["code"] in {"WEEK_NOT_CLOSED", "WEEK_OUTCOMES_INCOMPLETE"}


def test_release_v1_full_postgresql_vertical_flow(
    client: TestClient,
    engine: Engine,
) -> None:
    """Exercise the release journey only through the stable V1 HTTP contract."""
    assert engine.dialect.name == "postgresql"
    alembic_config = Config(str(ALEMBIC_CONFIG))
    expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == expected_head

    current_week_start = _current_week_start()
    closed_week_start = current_week_start - timedelta(days=7)
    completed_date = closed_week_start
    not_completed_date = closed_week_start + timedelta(days=1)

    unauthenticated = client.get("/api/v1/me", headers={"Authorization": ""})
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    before_onboarding = client.get("/api/v1/me")
    assert before_onboarding.status_code == 200, before_onboarding.text
    assert before_onboarding.json()["onboarding_completed"] is False

    onboarding = _onboard(client)
    assert onboarding["onboarding_completed"] is True
    routine = _create_routine(client, effective_from=closed_week_start)
    assert routine["status_code"] == "ACTIVE"

    completed_context = _check_in(client, local_date=completed_date)
    completed_decision = _decide(
        client,
        completed_context,
        local_date=completed_date,
    )
    assert completed_decision["status_code"] == "COMPLETED"
    assert completed_decision["final_plan"] is not None
    completed_option = next(
        option
        for option in completed_decision["options"]
        if option["option_code"] == "FINAL_ROUTINE"
    )
    completed_selection = client.post(
        f"/api/v1/decisions/{completed_decision['decision_id']}/selection",
        headers=_key(),
        json={"option_id": completed_option["option_id"]},
    )
    assert completed_selection.status_code in {200, 201}, completed_selection.text
    completed_session_id = completed_selection.json()["workout_session"]["session_id"]
    completed_started_at = datetime(
        completed_date.year,
        completed_date.month,
        completed_date.day,
        10,
        tzinfo=ZoneInfo(DEMO_TIMEZONE),
    )
    completed_started = client.patch(
        f"/api/v1/workout-sessions/{completed_session_id}/start",
        headers=_key(),
        json={"started_at": completed_started_at.isoformat()},
    )
    assert completed_started.status_code == 200, completed_started.text
    completed_item_ids = [item["plan_item_id"] for item in completed_started.json()["items"]]
    assert completed_item_ids
    for index, plan_item_id in enumerate(completed_item_ids, start=1):
        item_response = client.patch(
            f"/api/v1/workout-sessions/{completed_session_id}/items/{plan_item_id}",
            headers=_key(),
            json={
                "status_code": "COMPLETED",
                "client_recorded_at": (completed_started_at + timedelta(minutes=index)).isoformat(),
            },
        )
        assert item_response.status_code == 200, item_response.text

    completed_finish = client.patch(
        f"/api/v1/workout-sessions/{completed_session_id}/finish",
        headers=_key(),
        json={
            "finished_at": (completed_started_at + timedelta(minutes=40)).isoformat(),
            "actual_elapsed_seconds": 2400,
        },
    )
    assert completed_finish.status_code == 200, completed_finish.text
    assert completed_finish.json()["status_code"] == "COMPLETED"
    completed_feedback = client.post(
        f"/api/v1/workout-sessions/{completed_session_id}/feedback",
        headers=_key(),
        json={
            "difficulty_code": "APPROPRIATE",
            "pain_occurred": False,
            "discomforts": [],
            "adverse_reaction_codes": [],
        },
    )
    assert completed_feedback.status_code == 201, completed_feedback.text

    missed_context = _check_in(client, local_date=not_completed_date)
    missed_decision = _decide(
        client,
        missed_context,
        local_date=not_completed_date,
    )
    assert missed_decision["status_code"] == "COMPLETED"
    missed_option = next(
        option for option in missed_decision["options"] if option["option_code"] == "FINAL_ROUTINE"
    )
    missed_selection = client.post(
        f"/api/v1/decisions/{missed_decision['decision_id']}/selection",
        headers=_key(),
        json={"option_id": missed_option["option_id"]},
    )
    assert missed_selection.status_code in {200, 201}, missed_selection.text
    missed_session_id = missed_selection.json()["workout_session"]["session_id"]
    missed_ended_at = datetime(
        not_completed_date.year,
        not_completed_date.month,
        not_completed_date.day,
        10,
        5,
        tzinfo=ZoneInfo(DEMO_TIMEZONE),
    )
    not_completed = client.patch(
        f"/api/v1/workout-sessions/{missed_session_id}/not-completed",
        headers=_key(),
        json={"ended_at": missed_ended_at.isoformat(), "reason_code": "TIME_SHORTAGE"},
    )
    assert not_completed.status_code == 200, not_completed.text
    assert not_completed.json()["status_code"] == "NOT_COMPLETED"
    assert not_completed.json()["penalty_applied"] is False

    week = client.get(f"/api/v1/weeks/{closed_week_start.isoformat()}")
    assert week.status_code == 200, week.text
    assert week.json()["status_code"] == "CLOSED"
    report = client.post(
        f"/api/v1/weeks/{closed_week_start.isoformat()}/report",
        headers=_key(),
        json={"expected_week_status_code": "CLOSED"},
    )
    assert report.status_code == 201, report.text
    report_body = report.json()
    assert report_body["status_code"] == "GENERATED"
    assert report_body["counts"]["completed"] == 1
    assert report_body["counts"]["not_completed"] == 1
    assert report_body["primary_miss_reason_code"] == "TIME_SHORTAGE"

    acknowledged_at = datetime.fromisoformat(report_body["generated_at"]) + timedelta(seconds=1)
    acknowledgement = client.post(
        f"/api/v1/weekly-reports/{report_body['report_id']}/acknowledgement",
        headers=_key(),
        json={"acknowledged_at": acknowledged_at.isoformat()},
    )
    assert acknowledgement.status_code == 200, acknowledgement.text
    assert acknowledgement.json()["status_code"] == "ACKNOWLEDGED"

    next_plan = client.post(
        f"/api/v1/weeks/{current_week_start.isoformat()}/plan",
        headers=_key(),
        json={},
    )
    assert next_plan.status_code == 201, next_plan.text
    next_plan_body = next_plan.json()
    assert next_plan_body["source_code"] == "INITIAL"
    assert next_plan_body["source_weekly_report_id"] == report_body["report_id"]
    assert next_plan_body["finalized"] is True
    assert next_plan_body["routine"] is not None


def test_demo_seed_installs_exactly_one_active_catalog(
    engine: Engine,
    client: TestClient,
) -> None:
    """The routine repository requires exactly one qualifying catalog."""
    del client  # the client fixture is what seeds the catalog
    with Session(engine) as session:
        eligible = session.scalars(
            select(CatalogVersion).where(
                CatalogVersion.status_code == "ACTIVE",
                CatalogVersion.review_status_code == "DOMAIN_APPROVED",
                CatalogVersion.review_method_code == "DOMAIN_REVIEWER",
                CatalogVersion.status_interpretation_code == "PRODUCTION_APPROVED",
                CatalogVersion.production_eligible.is_(True),
                CatalogVersion.activated_at.is_not(None),
            )
        ).all()
    assert len(eligible) == 1
    assert eligible[0].version_code == "demo-synthetic-v1"
    # The synthetic origin must stay visible in the row itself.
    assert eligible[0].manifest_metadata["synthetic"] is True


def test_demo_seed_refuses_a_non_demo_database() -> None:
    with pytest.raises(SystemExit):
        _require_demo_database("postgresql+psycopg://user:pw@localhost:5432/exercise_app")


def test_demo_seed_accepts_demo_database_names() -> None:
    assert _require_demo_database("postgresql+psycopg://u:p@localhost:5432/app_test") == "app_test"
    assert _require_demo_database("postgresql+psycopg://u:p@localhost:5432/app_demo") == "app_demo"


# Kept last: it clears every user-owned table, so it must not run before the
# tests above.
def test_reset_users_clears_user_data_and_keeps_the_catalog(
    engine: Engine,
    client: TestClient,
) -> None:
    """An initial weekly plan stores `weekly_plan_revisions.routine_id`, an
    intentional RESTRICT reference to a row that also cascades from `users`.
    A plain `DELETE FROM users` cannot resolve that by cascade order alone."""
    current_week_start = _current_week_start()
    _onboard(client)
    _create_routine(client, effective_from=current_week_start)
    context = _check_in(client, local_date=current_week_start)
    _decide(client, context, local_date=current_week_start)
    plan = client.post(
        f"/api/v1/weeks/{current_week_start.isoformat()}/plan",
        headers=_key(),
        json={},
    )
    assert plan.status_code == 201, plan.text

    user_owned = ("routines", "decision_runs", "scheduled_workouts", "weekly_plan_revisions")
    with Session(engine) as session:
        catalog_exercises = session.scalar(text("select count(*) from exercises"))
        assert session.scalar(select(func.count()).select_from(User)) > 0
        # The reference that makes the plain delete fail must actually be here,
        # otherwise this test would pass against the bug it guards.
        blocking = session.scalar(
            text("select count(*) from weekly_plan_revisions where routine_id is not null")
        )
        assert blocking > 0

    with Session(engine) as session, session.begin():
        removed = reset_users(session)

    assert removed > 0
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0
        for table in user_owned:
            assert session.scalar(text(f"select count(*) from {table}")) == 0, table
        # Truncation must stop at the tables that reference `users`.
        assert session.scalar(text("select count(*) from exercises")) == catalog_exercises
        assert session.scalar(select(func.count()).select_from(CatalogVersion)) >= 1
