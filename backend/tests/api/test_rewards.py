from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_current_user, get_db_session, get_reward_repository
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_reward_service import FakeRewardRepository, FakeSession


def test_reward_contract_claims_once_and_spends_with_idempotency() -> None:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    repository, user_id = FakeRewardRepository(), uuid4()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, status_code=UserStatusCode.ACTIVE
    )
    app.dependency_overrides[get_reward_repository] = lambda: repository

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    key = str(uuid4())
    with TestClient(app) as client:
        initial = client.get("/api/v1/rewards")
        claimed = client.post("/api/v1/rewards/daily-reward/claim")
        repeated = client.post("/api/v1/rewards/daily-reward/claim")
        spent = client.post(
            "/api/v1/rewards/spend",
            headers={"Idempotency-Key": key},
            json={"action_code": "FEED_MASCOT"},
        )
        replayed_spend = client.post(
            "/api/v1/rewards/spend",
            headers={"Idempotency-Key": key},
            json={"action_code": "FEED_MASCOT"},
        )

    assert initial.status_code == 200
    assert initial.json()["daily_reward"]["is_claimable"] is True
    assert claimed.status_code == 200
    assert claimed.json()["balance"] == 15
    assert repeated.json()["balance"] == 15
    assert spent.status_code == 200
    assert spent.json()["balance"] == 5
    assert (
        replayed_spend.json()["transaction"]["transaction_id"]
        == spent.json()["transaction"]["transaction_id"]
    )
