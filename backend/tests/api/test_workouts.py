from datetime import UTC, date, datetime, timedelta
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
from backend.app.modules.workouts.ports import (
    SessionState,
    WorkoutLogCursor,
    WorkoutLogDetail,
    WorkoutLogFeedback,
    WorkoutLogItem,
    WorkoutLogSummary,
)
from backend.tests.unit.test_workout_service import (
    FakeSession,
    FakeWorkoutRepository,
    _source,
)

NOW = datetime(2026, 8, 14, 1, 0, tzinfo=UTC)


class FakeWorkoutLogRepository(FakeWorkoutRepository):
    def __init__(self, owner_id: UUID, logs: tuple[WorkoutLogSummary, ...]) -> None:
        super().__init__(_source())
        self.owner_id = owner_id
        self.logs = logs
        self.details: dict[UUID, WorkoutLogDetail] = {}

    def list_workout_logs(
        self,
        session: object,
        user_id: UUID,
        *,
        from_local_date: date | None,
        to_local_date: date | None,
        status_code: str | None,
        cursor: WorkoutLogCursor | None,
        limit: int,
    ) -> tuple[WorkoutLogSummary, ...]:
        if user_id != self.owner_id:
            return ()
        rows = [
            row
            for row in self.logs
            if (from_local_date is None or row.local_date >= from_local_date)
            and (to_local_date is None or row.local_date <= to_local_date)
            and (status_code is None or row.status_code == status_code)
            and (
                cursor is None
                or (row.local_date, row.session_id) < (cursor.local_date, cursor.session_id)
            )
        ]
        return tuple(
            sorted(rows, key=lambda row: (row.local_date, row.session_id), reverse=True)[:limit]
        )

    def get_workout_log_detail(
        self, session: object, user_id: UUID, session_id: UUID
    ) -> WorkoutLogDetail | None:
        if user_id != self.owner_id:
            return None
        return self.details.get(session_id)


def _log(index: int, *, status_code: str = "COMPLETED") -> WorkoutLogSummary:
    local_date = date(2026, 8, 14) - timedelta(days=index // 2)
    return WorkoutLogSummary(
        session_id=UUID(int=index + 1),
        local_date=local_date,
        status_code=status_code,
        completed_item_count=1 if status_code == "COMPLETED" else 0,
        total_item_count=1,
        requested_duration_minutes=30,
        training_type_code="STRENGTH",
        not_completed_reason_code="TIME_SHORTAGE" if status_code == "NOT_COMPLETED" else None,
        started_at=NOW,
        finished_at=NOW + timedelta(minutes=30),
    )


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


def test_workout_log_list_requires_authentication() -> None:
    user_id = uuid4()
    repository = FakeWorkoutLogRepository(user_id, ())
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_workout_repository] = lambda: repository
    with TestClient(app) as client:
        response = client.get("/api/v1/workout-sessions")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_workout_log_list_filters_and_uses_default_limit() -> None:
    user_id = uuid4()
    logs = tuple(
        _log(index, status_code="NOT_COMPLETED" if index % 3 == 0 else "COMPLETED")
        for index in range(25)
    )
    repository = FakeWorkoutLogRepository(user_id, logs)
    with _client(repository, user_id) as client:
        first_page = client.get("/api/v1/workout-sessions")
        filtered = client.get(
            "/api/v1/workout-sessions",
            params={
                "from_local_date": "2026-08-10",
                "to_local_date": "2026-08-12",
                "status_code": "COMPLETED",
            },
        )
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 20
    assert first_page.json()["next_cursor"] is not None
    assert filtered.status_code == 200
    assert all(item["status_code"] == "COMPLETED" for item in filtered.json()["items"])
    assert all(
        "2026-08-10" <= item["local_date"] <= "2026-08-12" for item in filtered.json()["items"]
    )


def test_workout_log_list_cursor_is_stable_and_limit_is_validated() -> None:
    user_id = uuid4()
    repository = FakeWorkoutLogRepository(user_id, tuple(_log(index) for index in range(25)))
    with _client(repository, user_id) as client:
        first = client.get("/api/v1/workout-sessions", params={"limit": 10})
        second = client.get(
            "/api/v1/workout-sessions",
            params={"limit": 10, "cursor": first.json()["next_cursor"]},
        )
        maximum = client.get("/api/v1/workout-sessions", params={"limit": 100})
        over_maximum = client.get("/api/v1/workout-sessions", params={"limit": 101})
        bad_cursor = client.get("/api/v1/workout-sessions", params={"cursor": "not-a-cursor"})
    first_ids = {item["session_id"] for item in first.json()["items"]}
    second_ids = {item["session_id"] for item in second.json()["items"]}
    assert first.status_code == second.status_code == maximum.status_code == 200
    assert first_ids.isdisjoint(second_ids)
    assert over_maximum.status_code == 400
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"]["code"] == "INVALID_REQUEST"


def test_workout_log_detail_is_owner_scoped_and_redacts_health_details() -> None:
    owner_id = uuid4()
    session_id = uuid4()
    plan_item_id = uuid4()
    repository = FakeWorkoutLogRepository(owner_id, ())
    repository.details[session_id] = WorkoutLogDetail(
        session_id=session_id,
        local_date=date(2026, 8, 14),
        status_code="COMPLETED",
        requested_duration_minutes=30,
        items=(
            WorkoutLogItem(
                plan_item_id=plan_item_id,
                exercise_id=uuid4(),
                exercise_name="합성 스쿼트",
                status_code="COMPLETED",
                sets=3,
                reps=10,
                work_seconds_per_set=None,
                completed_at=NOW,
            ),
        ),
        feedback=WorkoutLogFeedback(
            perceived_difficulty_code="APPROPRIATE",
            post_workout_discomfort_reported=True,
        ),
        not_completed_reason_code=None,
        started_at=NOW,
        finished_at=NOW + timedelta(minutes=30),
    )
    with _client(repository, owner_id) as owner_client:
        own = owner_client.get(f"/api/v1/workout-sessions/{session_id}")
        missing = owner_client.get(f"/api/v1/workout-sessions/{uuid4()}")
    with _client(repository, uuid4()) as other_client:
        other = other_client.get(f"/api/v1/workout-sessions/{session_id}")
    assert own.status_code == 200
    assert own.json()["completed_item_count"] == 1
    assert own.json()["items"][0]["exercise_name"] == "합성 스쿼트"
    assert own.json()["feedback"] == {
        "perceived_difficulty_code": "APPROPRIATE",
        "post_workout_discomfort_reported": True,
    }
    serialized = own.text
    assert "body_area" not in serialized
    assert "severity" not in serialized
    assert missing.status_code == other.status_code == 404
    assert missing.json()["error"]["code"] == other.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


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
    assert rest.json()["pressure_notifications_allowed"] is False
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


def test_finish_not_completed_safety_and_feedback_contracts() -> None:
    repository = FakeWorkoutRepository(_source())
    user_id = uuid4()
    client = _client(repository, user_id)
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
        client.patch(
            f"/api/v1/workout-sessions/{session_id}/items/{plan_item_id}",
            headers=_key(),
            json={"status_code": "COMPLETED", "client_recorded_at": NOW.isoformat()},
        )
        finished = client.patch(
            f"/api/v1/workout-sessions/{session_id}/finish",
            headers=_key(),
            json={"finished_at": NOW.isoformat(), "actual_elapsed_seconds": 0},
        )
        feedback = client.post(
            f"/api/v1/workout-sessions/{session_id}/feedback",
            headers=_key(),
            json={
                "difficulty_code": "APPROPRIATE",
                "fatigue_code": "MODERATE",
                "satisfaction_code": "SATISFIED",
                "pain_occurred": False,
                "discomforts": [],
                "adverse_reaction_codes": [],
            },
        )

    assert finished.status_code == 200
    assert finished.json()["status_code"] == "PARTIAL"
    assert finished.json()["actual_elapsed_seconds"] == 0
    assert feedback.status_code == 201
    assert feedback.json()["session_status_code"] == "PARTIAL"

    safety_repository = FakeWorkoutRepository(_source())
    with _client(safety_repository, uuid4()) as safety_client:
        selection = safety_client.post(
            f"/api/v1/decisions/{safety_repository.source.decision_id}/selection",
            headers=_key(),
            json={"option_id": str(safety_repository.source.option_id)},
        )
        safety_session_id = selection.json()["workout_session"]["session_id"]
        safety_client.patch(
            f"/api/v1/workout-sessions/{safety_session_id}/start",
            headers=_key(),
            json={"started_at": NOW.isoformat()},
        )
        safety = safety_client.post(
            f"/api/v1/workout-sessions/{safety_session_id}/safety-events",
            headers=_key(),
            json={
                "occurred_at": NOW.isoformat(),
                "symptom_code": "CHEST_DISCOMFORT",
            },
        )
    assert safety.status_code == 201
    assert safety.json()["result_code"] == "STOP_AND_SEEK_HELP"
    assert safety.json()["execution_state_code"] == "STOPPED_SAFETY"


def test_zero_block_finish_requires_explicit_not_completed_reason() -> None:
    repository = FakeWorkoutRepository(_source())
    with _client(repository, uuid4()) as client:
        selected = client.post(
            f"/api/v1/decisions/{repository.source.decision_id}/selection",
            headers=_key(),
            json={"option_id": str(repository.source.option_id)},
        )
        session_id = selected.json()["workout_session"]["session_id"]
        client.patch(
            f"/api/v1/workout-sessions/{session_id}/start",
            headers=_key(),
            json={"started_at": NOW.isoformat()},
        )
        rejected = client.patch(
            f"/api/v1/workout-sessions/{session_id}/finish",
            headers=_key(),
            json={"finished_at": NOW.isoformat(), "actual_elapsed_seconds": 3600},
        )
        not_completed = client.patch(
            f"/api/v1/workout-sessions/{session_id}/not-completed",
            headers=_key(),
            json={"ended_at": NOW.isoformat(), "reason_code": "LOW_MOTIVATION"},
        )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "NOT_COMPLETED_REASON_REQUIRED"
    assert not_completed.status_code == 200
    assert not_completed.json()["penalty_applied"] is False
