from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_plan_revision_repository,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_plan_revision import _Repository, _Session


def _client(repository: _Repository) -> TestClient:
    user_id = uuid4()
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
    app.dependency_overrides[get_plan_revision_repository] = lambda: repository
    return TestClient(app)


def test_set_repetition_endpoint_returns_the_revised_final_plan_and_replays() -> None:
    repository = _Repository()
    key = str(uuid4())
    request = {
        "expected_plan_id": str(repository.plan_id),
        "expected_plan_revision": 0,
        "sets": 3,
        "reps": 12,
    }

    with _client(repository) as client:
        first = client.patch(
            f"/api/v1/decisions/{repository.decision_id}/plan-items/{repository.items[0].plan_item_id}",
            headers={"Idempotency-Key": key},
            json=request,
        )
        replay = client.patch(
            f"/api/v1/decisions/{repository.decision_id}/plan-items/{repository.items[0].plan_item_id}",
            headers={"Idempotency-Key": key},
            json=request,
        )

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert first.json()["final_plan"]["items"][0]["sets"] == 3
    assert repository.save_count == 1


def test_order_endpoint_rejects_empty_and_stale_requests() -> None:
    repository = _Repository()
    with _client(repository) as client:
        empty = client.put(
            f"/api/v1/decisions/{repository.decision_id}/plan-item-order",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_plan_id": str(repository.plan_id),
                "expected_plan_revision": 0,
                "ordered_plan_item_ids": [],
            },
        )
        stale = client.put(
            f"/api/v1/decisions/{repository.decision_id}/plan-item-order",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_plan_id": str(repository.plan_id),
                "expected_plan_revision": 1,
                "ordered_plan_item_ids": [str(item.plan_item_id) for item in repository.items],
            },
        )

    assert empty.status_code == 400
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "PLAN_REVISION_STALE"
