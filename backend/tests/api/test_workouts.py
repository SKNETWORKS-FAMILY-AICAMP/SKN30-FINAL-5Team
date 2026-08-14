from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_workout_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.workouts.ports import SessionState
from backend.tests.unit.test_workout_service import (
    FakeSession,
    FakeWorkoutRepository,
    _source,
)

NOW = datetime(2026, 8, 14, 1, 0, tzinfo=UTC)


def _client(repository: FakeWorkoutRepository, user_id: UUID) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, status_code=UserStatusCode.ACTIVE
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_workout_repository] = lambda: repository
    return TestClient(app)


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def test_selection_start_blocks_timer_and_additional_activity_contract() -> None:
    repository = FakeWorkoutRepository(_source())
    client = _client(repository, uuid4())
    with client:
        selected = client.post(
            f"/api/v1/decisions/{repository.source.decision_id}/selection",
            headers=_key(),
            json={"option_id": str(repository.source.option_id)},
        )
        session_id = selected.json()["workout_session"]["session_id"]
        started = client.patch(
            f"/api/v1/workout-sessions/{session_id}/start",
            headers=_key(),
            json={"started_at": NOW.isoformat()},
        )
        plan_item_id = started.json()["items"][0]["plan_item_id"]
        timer = client.post(
            f"/api/v1/workout-sessions/{session_id}/timer-events",
            headers=_key(),
            json={
                "event_code": "END",
                "occurred_at": (NOW + timedelta(minutes=20)).isoformat(),
                "client_recorded_at": NOW.isoformat(),
            },
        )
        additional = client.post(
            f"/api/v1/workout-sessions/{session_id}/additional-activities",
            headers=_key(),
            json={
                "activity_type_code": "WALKING",
                "duration_seconds": 1200,
                "intensity_code": "LOW",
                "note": None,
            },
        )
        completed = client.patch(
            f"/api/v1/workout-sessions/{session_id}/items/{plan_item_id}",
            headers=_key(),
            json={"status_code": "COMPLETED", "client_recorded_at": NOW.isoformat()},
        )
        reverted = client.patch(
            f"/api/v1/workout-sessions/{session_id}/items/{plan_item_id}",
            headers=_key(),
            json={"status_code": "PENDING", "client_recorded_at": NOW.isoformat()},
        )

    assert selected.status_code == 201
    assert selected.json()["workout_session"]["status_code"] == "PLANNED"
    assert started.status_code == 200
    assert started.json()["status_code"] == "IN_PROGRESS"
    assert timer.status_code == 201
    assert additional.status_code == 201
    assert timer.json()["session_status_code"] == "IN_PROGRESS"
    assert additional.json()["session_status_code"] == "IN_PROGRESS"
    assert completed.json()["completed_item_count"] == 1
    assert reverted.json()["completed_item_count"] == 0


def test_rest_selection_has_no_session_and_vetoed_final_is_rejected() -> None:
    rest_repository = FakeWorkoutRepository(_source(option_code="REST"))
    veto_repository = FakeWorkoutRepository(_source(vetoed=True))
    with _client(rest_repository, uuid4()) as client:
        rest = client.post(
            f"/api/v1/decisions/{rest_repository.source.decision_id}/selection",
            headers=_key(),
            json={"option_id": str(rest_repository.source.option_id)},
        )
    with _client(veto_repository, uuid4()) as client:
        vetoed = client.post(
            f"/api/v1/decisions/{veto_repository.source.decision_id}/selection",
            headers=_key(),
            json={"option_id": str(veto_repository.source.option_id)},
        )
    assert rest.status_code == 201
    assert rest.json()["selected_action_code"] == "REST"
    assert rest.json()["workout_session"] is None
    assert vetoed.status_code == 409
    assert vetoed.json()["error"]["code"] == "OPTION_NOT_SELECTABLE"


def test_ended_session_and_idempotency_key_reuse_use_contract_errors() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    client = _client(repository, user_id)
    selection_key = str(uuid4())
    with client:
        selected = client.post(
            f"/api/v1/decisions/{repository.source.decision_id}/selection",
            headers={"Idempotency-Key": selection_key},
            json={"option_id": str(repository.source.option_id)},
        )
        conflict = client.post(
            f"/api/v1/decisions/{repository.source.decision_id}/selection",
            headers={"Idempotency-Key": selection_key},
            json={"option_id": str(uuid4())},
        )
        session_id = UUID(selected.json()["workout_session"]["session_id"])
        repository.session_state = SessionState(
            session_id,
            "COMPLETED",
            NOW,
            NOW + timedelta(minutes=10),
            tuple((item_id, "COMPLETED", NOW) for item_id in repository.source.plan_item_ids),
        )
        ended = client.post(
            f"/api/v1/workout-sessions/{session_id}/timer-events",
            headers=_key(),
            json={
                "event_code": "END",
                "occurred_at": NOW.isoformat(),
                "client_recorded_at": NOW.isoformat(),
            },
        )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert ended.status_code == 409
    assert ended.json()["error"]["code"] == "SESSION_ENDED"
