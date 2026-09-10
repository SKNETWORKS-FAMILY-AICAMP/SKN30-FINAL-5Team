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


def _mini_game_client() -> tuple[TestClient, FakeRewardRepository]:
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
    return TestClient(app), repository


def test_mini_game_pays_in_proportion_to_the_score_and_only_once_a_day() -> None:
    client, _ = _mini_game_client()
    with client:
        first = client.post("/api/v1/rewards/mini-game/claim", json={"score": 20})
        replayed = client.post("/api/v1/rewards/mini-game/claim", json={"score": 20})
        different = client.post("/api/v1/rewards/mini-game/claim", json={"score": 30})

    assert first.status_code == 200
    # 20 points / 2 points per banana
    assert first.json()["transaction"]["amount"] == 10
    assert first.json()["balance"] == 10
    # A retry of the same finished round replays rather than paying again.
    assert (
        replayed.json()["transaction"]["transaction_id"]
        == first.json()["transaction"]["transaction_id"]
    )
    assert replayed.json()["balance"] == 10
    # A second, different score on the same day is refused, not paid.
    assert different.status_code == 400
    assert different.json()["error"]["code"] == "INVALID_BANANA_SPEND"


def test_mini_game_caps_the_payout_and_rejects_an_impossible_score() -> None:
    client, _ = _mini_game_client()
    with client:
        capped = client.post("/api/v1/rewards/mini-game/claim", json={"score": 180})
        impossible = client.post("/api/v1/rewards/mini-game/claim", json={"score": 100_000})
        negative = client.post("/api/v1/rewards/mini-game/claim", json={"score": -1})

    # The score is client-reported, so the payout is bounded rather than trusted.
    assert capped.status_code == 200
    assert capped.json()["transaction"]["amount"] == 25
    # Out of the schema's declared range, so it never reaches the service. The
    # repository normalises request-validation failures to 400 INVALID_REQUEST.
    assert impossible.status_code == 400
    assert impossible.json()["error"]["code"] == "INVALID_REQUEST"
    assert negative.status_code == 400
    assert negative.json()["error"]["code"] == "INVALID_REQUEST"


def test_mini_game_pays_nothing_for_a_round_that_caught_nothing() -> None:
    client, _ = _mini_game_client()
    with client:
        scoreless = client.post("/api/v1/rewards/mini-game/claim", json={"score": 1})

    # 1 // 2 == 0: no transaction rather than a zero-amount one, which the
    # ledger's amount <> 0 constraint would reject anyway.
    assert scoreless.status_code == 400
    assert scoreless.json()["error"]["code"] == "INVALID_MINI_GAME_SCORE"
