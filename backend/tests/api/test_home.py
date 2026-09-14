from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_decision_repository,
    get_workout_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.workouts.ports import WorkoutLogDetail, WorkoutLogItem

LOCAL_DATE = date(2026, 9, 4)
NOW = datetime(2026, 9, 4, tzinfo=UTC)


class _Session:
    pass


class _Decisions:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_response_for_date(self, session: Any, user_id: UUID, local_date: date):
        del session, user_id
        return self.payload if local_date == LOCAL_DATE else None


class _Workouts:
    def __init__(self, detail: WorkoutLogDetail, plan_id: UUID) -> None:
        self.detail = detail
        self.plan_id = plan_id
        self.requested_plan_ids: list[UUID] = []

    def get_workout_log_detail_for_plan(self, session: Any, user_id: UUID, plan_id: UUID):
        del session, user_id
        self.requested_plan_ids.append(plan_id)
        return self.detail if plan_id == self.plan_id else None

    def get_workout_log_detail(self, session: Any, user_id: UUID, session_id: UUID):
        del session, user_id
        return self.detail if session_id == self.detail.session_id else None


def _decision(plan_id: UUID, item_ids: tuple[UUID, UUID]) -> dict[str, Any]:
    return {
        "decision_id": uuid4(),
        "local_date": LOCAL_DATE,
        "status_code": "COMPLETED",
        "safety_status_code": "PASS",
        "action_code": "KEEP",
        "requested_duration_minutes": 30,
        "duration_adjustment_source_code": "PROFILE",
        "final_plan": {
            "plan_id": plan_id,
            "plan_revision": 0,
            "action_code": "KEEP",
            "training_type_code": "STRENGTH",
            "body_focus_code": None,
            "requested_duration_minutes": 30,
            "estimated_duration_seconds": 120,
            "estimated_calories_burned": None,
            "setup_seconds": 0,
            "warmup_seconds": 0,
            "cooldown_seconds": 0,
            "items": [
                {
                    "plan_item_id": item_id,
                    "exercise_id": uuid4(),
                    "exercise_name": "exercise",
                    "sequence": sequence,
                    "phase_code": "MAIN",
                    "tier_code": "CORE",
                    "sets": 2,
                    "reps": 10,
                    "work_seconds": 40,
                    "rest_seconds": 10,
                    "transition_seconds": 10,
                    "estimated_item_seconds": 60,
                    "instruction_available": True,
                }
                for sequence, item_id in enumerate(item_ids, start=1)
            ],
        },
        "options": [],
        "reason_codes": [],
        "summary": "ready",
        "created_at": NOW,
    }


def test_home_returns_consistent_decision_plan_and_resume_cursor() -> None:
    user_id = uuid4()
    plan_id = uuid4()
    item_ids = (uuid4(), uuid4())
    detail = WorkoutLogDetail(
        session_id=uuid4(),
        local_date=LOCAL_DATE,
        status_code="IN_PROGRESS",
        requested_duration_minutes=30,
        items=(
            WorkoutLogItem(item_ids[0], uuid4(), "first", "COMPLETED", 2, 10, 20, NOW),
            WorkoutLogItem(item_ids[1], uuid4(), "second", "PENDING", 2, 10, 20, None),
        ),
        feedback=None,
        not_completed_reason_code=None,
        started_at=NOW,
        finished_at=None,
    )
    decisions = _Decisions(_decision(plan_id, item_ids))
    workouts = _Workouts(detail, plan_id)
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
        yield _Session()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_decision_repository] = lambda: decisions
    app.dependency_overrides[get_workout_repository] = lambda: workouts

    with TestClient(app) as client:
        response = client.get("/api/v1/home", params={"local_date": LOCAL_DATE.isoformat()})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["decision_id"] == str(decisions.payload["decision_id"])
    assert body["final_plan"] == body["decision"]["final_plan"]
    assert body["workout_session"]["completed_plan_item_ids"] == [str(item_ids[0])]
    assert body["workout_session"]["current_plan_item_id"] == str(item_ids[1])
    assert workouts.requested_plan_ids == [plan_id]
