from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_current_user, get_db_session, get_decision_repository
from backend.app.core.config import Settings
from backend.app.integrations.llm_provider import UnavailableNarrationProvider
from backend.app.main import create_app
from backend.app.modules.decisions.ports import NarrationCompletion, NarrationPrompt
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser
from backend.tests.unit.test_decision_service import FakeRepository, FakeSession, _context


class BrokenNarrationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def narrate(self, prompt: NarrationPrompt) -> NarrationCompletion:
        self.calls += 1
        raise TimeoutError("provider timeout")


def _client(
    repository: FakeRepository,
    user_id: object,
    narration_provider: object | None = None,
) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
        narration_provider=narration_provider,
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, status_code=UserStatusCode.ACTIVE
    )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_decision_repository] = lambda: repository
    return TestClient(app)


def test_post_and_get_decision_contract() -> None:
    context = _context()
    repository = FakeRepository(context)
    user_id = uuid4()
    client = _client(repository, user_id)
    with client:
        created = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": context.context_version,
            },
        )
        fetched = client.get(f"/api/v1/decisions/{created.json()['decision_id']}")
    assert created.status_code == 201
    assert fetched.status_code == 200
    assert created.json()["final_plan"]["estimated_duration_seconds"] == 600
    assert "date_of_birth" not in created.text
    assert "age" not in created.json()


def test_post_decision_rejects_stale_context() -> None:
    context = _context()
    client = _client(FakeRepository(context), uuid4())
    with client:
        response = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": 1,
            },
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_CONTEXT"


def test_decision_api_runs_without_a_configured_llm_provider() -> None:
    context = _context()
    client = _client(FakeRepository(context), uuid4())

    assert isinstance(client.app.state.narration_provider, UnavailableNarrationProvider)

    with client:
        response = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": context.context_version,
            },
        )

    assert response.status_code == 201
    assert response.json()["final_plan"]["estimated_duration_seconds"] == 600


def test_decision_api_still_succeeds_when_the_provider_fails() -> None:
    context = _context()
    repository = FakeRepository(context)
    provider = BrokenNarrationProvider()
    client = _client(repository, uuid4(), narration_provider=provider)

    with client:
        response = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": context.context_version,
            },
        )

    # 라우트는 provider를 직접 호출하지 않고 서비스에 위임한다.
    assert provider.calls == 1
    assert response.status_code == 201
    explanation = repository.persisted["explanation"]
    assert explanation.source_code.value == "TEMPLATE"
    assert explanation.fallback_reason_code == "LLM_PROVIDER_FAILED"
    # 내부 프롬프트와 추론 과정은 응답에 포함되지 않는다.
    body = response.text
    assert "prompt" not in body.lower()
    assert "slot" not in body.lower()


def test_get_decision_by_date_resumes_the_created_decision() -> None:
    context = _context()
    repository = FakeRepository(context)
    client = _client(repository, uuid4())
    with client:
        created = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": context.local_date.isoformat(),
                "daily_context_id": str(context.daily_context_id),
                "expected_context_version": context.context_version,
            },
        )
        resumed = client.get(
            "/api/v1/decisions", params={"local_date": context.local_date.isoformat()}
        )
        missing = client.get("/api/v1/decisions", params={"local_date": "2020-01-01"})
    assert created.status_code == 201
    assert resumed.status_code == 200
    # 재시작한 클라이언트가 같은 결정을 그대로 복원한다.
    assert resumed.json()["decision_id"] == created.json()["decision_id"]
    assert resumed.json()["action_code"] == created.json()["action_code"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DECISION_NOT_FOUND"
