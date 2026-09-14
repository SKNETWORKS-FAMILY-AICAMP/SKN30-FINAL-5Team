import inspect
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.app.api.dependencies import get_v3_regeneration_service
from backend.app.api.v1.decisions import regenerate_decision
from backend.app.core.config import Settings
from backend.app.db.repositories.decision import DecisionRepository
from backend.app.domain.agents.v3_orchestration import RegenerationDifferenceCode
from backend.app.modules.decisions.v3_regeneration import (
    V3DecisionEngineCode,
    V3DecisionNotFoundError,
    V3IdempotencyKeyReusedError,
    V3NoAlternativeAvailableError,
    V3RegenerationCommand,
    V3RegenerationCompositionUnavailableError,
    V3RegenerationContextStaleError,
    V3RegenerationDecisionFailedError,
    V3RegenerationError,
    V3RegenerationLimitReachedError,
    V3RegenerationNotAllowedError,
    V3RegenerationResult,
    V3StaleRegenerationError,
)
from backend.tests.api.test_decisions import _client
from backend.tests.unit.test_decision_service import FakeRepository, _context


class StubRegenerationService:
    def __init__(
        self,
        *,
        result: V3RegenerationResult | None = None,
        error: V3RegenerationError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.commands: list[V3RegenerationCommand] = []

    async def regenerate(self, command: V3RegenerationCommand) -> V3RegenerationResult:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class LineageFakeRepository(FakeRepository):
    def __init__(self, *args: object, lineage: dict[str, object], **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.lineage = lineage

    def get_response(self, *args: object, **kwargs: object) -> dict[str, object] | None:
        response = super().get_response(*args, **kwargs)
        if response is not None:
            response.update(self.lineage)
        return response


def test_composition_unavailable_has_stable_sanitized_error() -> None:
    client, _, decision_id, plan_id = _create_stored_decision()
    client.app.dependency_overrides[get_v3_regeneration_service] = lambda: StubRegenerationService(
        error=V3RegenerationCompositionUnavailableError()
    )

    with client:
        response = client.post(
            f"/api/v1/decisions/{decision_id}/regenerations",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_plan_id": str(plan_id),
                "expected_regeneration_sequence": 0,
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "V3_COMPOSITION_UNAVAILABLE"


def _create_stored_decision() -> tuple[object, UUID, UUID, UUID]:
    context = _context()
    user_id = uuid4()
    client = _client(FakeRepository(context), user_id)
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
    return (
        client,
        user_id,
        UUID(response.json()["decision_id"]),
        UUID(response.json()["final_plan"]["plan_id"]),
    )


def test_regeneration_returns_stored_decision_with_mapped_v3_metadata() -> None:
    client, user_id, stored_decision_id, plan_id = _create_stored_decision()
    root_id = uuid4()
    idempotency_key = uuid4()
    service = StubRegenerationService(
        result=V3RegenerationResult(
            decision_id=stored_decision_id,
            root_decision_id=root_id,
            parent_decision_id=root_id,
            regeneration_sequence=1,
            decision_engine_code=V3DecisionEngineCode.DETERMINISTIC_FALLBACK,
            meaningful_difference_codes=(
                RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
                RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED,
                RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
                RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED,
            ),
        )
    )
    client.app.dependency_overrides[get_v3_regeneration_service] = lambda: service

    with client:
        response = client.post(
            f"/api/v1/decisions/{root_id}/regenerations",
            headers={"Idempotency-Key": str(idempotency_key)},
            json={
                "expected_plan_id": str(plan_id),
                "expected_regeneration_sequence": 0,
            },
        )

    assert response.status_code == 201
    assert response.json()["decision_id"] == str(stored_decision_id)
    assert response.json()["generation_mode_code"] == "REGENERATED"
    assert response.json()["decision_engine_code"] == "DETERMINISTIC_FALLBACK"
    assert response.json()["root_decision_id"] == str(root_id)
    assert response.json()["parent_decision_id"] == str(root_id)
    assert response.json()["regeneration_sequence"] == 1
    assert response.json()["meaningful_difference_codes"] == [
        "CORE_EXERCISE_CHANGED",
        "SET_REP_STRUCTURE_CHANGED",
        "EXERCISE_ORDER_CHANGED",
        "ROUTINE_STRUCTURE_CHANGED",
    ]
    assert service.commands == [
        V3RegenerationCommand(
            user_id=user_id,
            decision_id=root_id,
            idempotency_key=idempotency_key,
            expected_plan_id=plan_id,
            expected_regeneration_sequence=0,
        )
    ]


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (V3DecisionNotFoundError(), 404, "DECISION_NOT_FOUND"),
        (V3IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (V3StaleRegenerationError(), 409, "STALE_REGENERATION"),
        (V3RegenerationContextStaleError(), 409, "REGENERATION_CONTEXT_STALE"),
        (V3RegenerationLimitReachedError(), 409, "REGENERATION_LIMIT_REACHED"),
        (V3RegenerationNotAllowedError(), 409, "REGENERATION_NOT_ALLOWED"),
        (V3NoAlternativeAvailableError(), 422, "NO_ALTERNATIVE_AVAILABLE"),
        (V3RegenerationDecisionFailedError(), 503, "DECISION_FAILED"),
    ],
)
def test_regeneration_maps_application_errors(
    error: V3RegenerationError, status_code: int, code: str
) -> None:
    context = _context()
    client = _client(FakeRepository(context), uuid4())
    service = StubRegenerationService(error=error)
    client.app.dependency_overrides[get_v3_regeneration_service] = lambda: service

    with client:
        response = client.post(
            f"/api/v1/decisions/{uuid4()}/regenerations",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_plan_id": str(uuid4()),
                "expected_regeneration_sequence": 0,
            },
        )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert len(service.commands) == 1


@pytest.mark.parametrize(
    ("headers", "payload"),
    [
        ({}, {"expected_plan_id": str(uuid4()), "expected_regeneration_sequence": 0}),
        (
            {"Idempotency-Key": "not-a-uuid"},
            {"expected_plan_id": str(uuid4()), "expected_regeneration_sequence": 0},
        ),
        (
            {"Idempotency-Key": str(uuid4())},
            {"expected_plan_id": "not-a-uuid", "expected_regeneration_sequence": 0},
        ),
        (
            {"Idempotency-Key": str(uuid4())},
            {"expected_plan_id": str(uuid4()), "expected_regeneration_sequence": -1},
        ),
        (
            {"Idempotency-Key": str(uuid4())},
            {"expected_plan_id": str(uuid4()), "expected_regeneration_sequence": 2},
        ),
        (
            {"Idempotency-Key": str(uuid4())},
            {
                "expected_plan_id": str(uuid4()),
                "expected_regeneration_sequence": 0,
                "different": "다르게 만들어 주세요",
            },
        ),
    ],
)
def test_regeneration_rejects_invalid_transport_input(
    headers: dict[str, str], payload: dict[str, object]
) -> None:
    context = _context()
    client = _client(FakeRepository(context), uuid4())
    service = StubRegenerationService(error=V3RegenerationDecisionFailedError())
    client.app.dependency_overrides[get_v3_regeneration_service] = lambda: service

    with client:
        response = client.post(
            f"/api/v1/decisions/{uuid4()}/regenerations",
            headers=headers,
            json=payload,
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert service.commands == []


def test_regeneration_is_disabled_by_default() -> None:
    context = _context()
    client = _client(FakeRepository(context), uuid4())

    with client:
        response = client.post(
            f"/api/v1/decisions/{uuid4()}/regenerations",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_plan_id": str(uuid4()),
                "expected_regeneration_sequence": 0,
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "V3_ENGINE_DISABLED"


def test_regeneration_dependency_uses_the_dedicated_activation_gate() -> None:
    service = StubRegenerationService(error=V3RegenerationDecisionFailedError())
    disabled_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=Settings(
                    app_env="test",
                    database_url="postgresql+psycopg://test:test@localhost/test",
                    v3_langgraph_enabled=True,
                    v3_shadow_evaluation_enabled=True,
                    v3_regeneration_enabled=False,
                ),
                v3_regeneration_service=service,
            )
        )
    )
    enabled_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=disabled_request.app.state.settings.model_copy(
                    update={"v3_regeneration_enabled": True}
                ),
                v3_regeneration_service=service,
            )
        )
    )

    assert get_v3_regeneration_service(disabled_request) is not service
    assert get_v3_regeneration_service(enabled_request) is service


def test_historical_decision_response_omits_v3_metadata() -> None:
    client, _, decision_id, _ = _create_stored_decision()

    with client:
        response = client.get(f"/api/v1/decisions/{decision_id}")

    assert response.status_code == 200
    assert set(response.json()).isdisjoint(
        {
            "generation_mode_code",
            "decision_engine_code",
            "root_decision_id",
            "parent_decision_id",
            "regeneration_sequence",
            "meaningful_difference_codes",
        }
    )


def test_repository_response_restores_persisted_v3_lineage() -> None:
    root_id = uuid4()
    parent_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        local_date=_context().local_date,
        status_code="COMPLETED",
        safety_status_code="PASS",
        recommended_action_code="KEEP",
        input_snapshot={
            "requested_duration_minutes": 10,
            "duration_adjustment_source_code": "PROFILE",
        },
        candidates=[],
        safety_reviews=[
            SimpleNamespace(
                public_guidance=None,
                safety_status_code="PASS",
                vetoed=False,
                reason_codes=[],
            )
        ],
        explanations=[],
        proposals=[],
        options=[],
        coordinator_result={"reason_codes": []},
        generation_mode_code="REGENERATED",
        decision_engine_code="DETERMINISTIC_FALLBACK",
        root_decision_run_id=root_id,
        parent_decision_run_id=parent_id,
        regeneration_sequence=1,
        created_at=SimpleNamespace(),
    )
    session = SimpleNamespace(scalar=lambda _: run)

    response = DecisionRepository().get_response(session, uuid4(), run.id)

    assert response is not None
    assert response["generation_mode_code"] == "REGENERATED"
    assert response["decision_engine_code"] == "DETERMINISTIC_FALLBACK"
    assert response["root_decision_id"] == root_id
    assert response["parent_decision_id"] == parent_id
    assert response["regeneration_sequence"] == 1


@pytest.mark.parametrize("path", ["/api/v1/decisions", "/api/v1/decisions/{decision_id}"])
def test_get_paths_return_persisted_v3_lineage(path: str) -> None:
    context = _context()
    repository = LineageFakeRepository(context, lineage={})
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
        decision_id = created.json()["decision_id"]
        repository.lineage = {
            "generation_mode_code": "ORIGINAL",
            "decision_engine_code": "LLM_MULTI_AGENT",
            "root_decision_id": UUID(decision_id),
            "parent_decision_id": None,
            "regeneration_sequence": 0,
        }
        target = (
            path.format(decision_id=created.json()["decision_id"])
            if "{decision_id}" in path
            else path
        )
        initial = client.get(target, params={"local_date": context.local_date.isoformat()})
        repository.lineage = {
            "generation_mode_code": "REGENERATED",
            "decision_engine_code": "DETERMINISTIC_FALLBACK",
            "root_decision_id": UUID(decision_id),
            "parent_decision_id": UUID(decision_id),
            "regeneration_sequence": 1,
        }
        client.app.dependency_overrides[get_v3_regeneration_service] = lambda: (
            StubRegenerationService(
                result=V3RegenerationResult(
                    decision_id=uuid4(),
                    root_decision_id=UUID(decision_id),
                    parent_decision_id=UUID(decision_id),
                    regeneration_sequence=1,
                    decision_engine_code=V3DecisionEngineCode.DETERMINISTIC_FALLBACK,
                    meaningful_difference_codes=(RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,),
                )
            )
        )
        rerolled = client.post(
            f"/api/v1/decisions/{decision_id}/regenerations",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_plan_id": created.json()["final_plan"]["plan_id"],
                "expected_regeneration_sequence": 0,
            },
        )
        response = client.get(target, params={"local_date": context.local_date.isoformat()})

    assert initial.status_code == 200
    assert initial.json()["regeneration_sequence"] == 0
    assert rerolled.status_code == 201
    assert rerolled.json()["regeneration_sequence"] == 1
    assert response.status_code == 200
    assert response.json()["generation_mode_code"] == "REGENERATED"
    assert response.json()["decision_engine_code"] == "DETERMINISTIC_FALLBACK"
    assert response.json()["root_decision_id"] == decision_id
    assert response.json()["parent_decision_id"] == decision_id
    assert response.json()["regeneration_sequence"] == 1


def test_regeneration_route_only_delegates_generation_to_application_service() -> None:
    source = inspect.getsource(regenerate_decision).lower()

    assert "await service.regenerate(command)" in source
    for forbidden in ("langgraph", "openai", "qdrant", ".commit(", ".execute(", ".query("):
        assert forbidden not in source
