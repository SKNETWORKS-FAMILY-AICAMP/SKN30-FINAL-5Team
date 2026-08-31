import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.dependencies import (
    get_current_user,
    get_db_session,
    get_v3_regeneration_service,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.decisions.execution_profile import (
    ProfiledDecisionCreationService,
    StaticV3ProductionPromotionGate,
    V3ExecutionProfile,
)
from backend.app.modules.decisions.schemas import (
    DecisionCreateRequest,
    DecisionOptionResponse,
    DecisionResponse,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser


class StubCreationService:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0

    async def create(self, session, user_id, request, idempotency_key):
        del session, user_id, request, idempotency_key
        self.calls += 1
        return self.label


def request() -> DecisionCreateRequest:
    return DecisionCreateRequest(
        local_date=date(2026, 8, 26),
        daily_context_id=uuid4(),
        expected_context_version=1,
    )


def test_default_profile_preserves_legacy() -> None:
    settings = Settings(
        app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
    )
    assert settings.v3_execution_profile == "LEGACY"


def test_staging_demo_selects_v3_creation_service() -> None:
    settings = Settings(
        app_env="staging",
        database_url="postgresql+psycopg://test:test@localhost/test",
        v3_execution_profile="DEMO",
    )
    legacy = StubCreationService("legacy")
    v3 = StubCreationService("v3")
    service = ProfiledDecisionCreationService(
        profile=V3ExecutionProfile(settings.v3_execution_profile),
        legacy=legacy,
        v3=v3,
        promotion_gate=StaticV3ProductionPromotionGate(False),
    )
    assert asyncio.run(service.create(object(), uuid4(), request(), uuid4())) == "v3"
    assert (legacy.calls, v3.calls) == (0, 1)


def test_demo_is_rejected_outside_staging_including_production() -> None:
    for app_env in ("local", "test", "production"):
        with pytest.raises(ValidationError, match="allowed only"):
            Settings(
                app_env=app_env,
                database_url="postgresql+psycopg://test:test@localhost/test",
                v3_execution_profile="DEMO",
            )


def test_production_profile_fails_closed_without_promotion_gate() -> None:
    legacy = StubCreationService("legacy")
    v3 = StubCreationService("v3")
    blocked = ProfiledDecisionCreationService(
        profile=V3ExecutionProfile.PRODUCTION,
        legacy=legacy,
        v3=v3,
        promotion_gate=StaticV3ProductionPromotionGate(False),
    )
    assert asyncio.run(blocked.create(object(), uuid4(), request(), uuid4())) == "legacy"
    assert (legacy.calls, v3.calls) == (1, 0)

    allowed = ProfiledDecisionCreationService(
        profile=V3ExecutionProfile.PRODUCTION,
        legacy=legacy,
        v3=v3,
        promotion_gate=StaticV3ProductionPromotionGate(True),
    )
    assert asyncio.run(allowed.create(object(), uuid4(), request(), uuid4())) == "v3"
    assert v3.calls == 1


def test_shadow_keeps_legacy_response_and_logs_no_request_payload(caplog) -> None:
    class BrokenShadow:
        async def shadow(self, **kwargs):
            del kwargs
            raise RuntimeError("email=person@example.test raw_health=secret")

    service = ProfiledDecisionCreationService(
        profile=V3ExecutionProfile.SHADOW,
        legacy=StubCreationService("legacy"),
        v3=StubCreationService("v3"),
        shadow=BrokenShadow(),
        promotion_gate=StaticV3ProductionPromotionGate(False),
    )
    assert asyncio.run(service.create(object(), uuid4(), request(), uuid4())) == "legacy"
    assert "person@example.test" not in caplog.text
    assert "raw_health" not in caplog.text


def test_main_composes_staging_demo_creation_and_regeneration_services() -> None:
    creation = StubCreationService("v3")

    class Regeneration:
        async def regenerate(self, command):
            del command
            raise AssertionError("not invoked by DI test")

    regeneration = Regeneration()
    app = create_app(
        settings=Settings(
            app_env="staging",
            database_url="postgresql+psycopg://test:test@localhost/test",
            v3_execution_profile="DEMO",
        ),
        readiness_probe=lambda: None,
        v3_creation_service=creation,
        v3_regeneration_service=regeneration,
    )
    composed = app.state.decision_creation_service_factory(object())
    assert asyncio.run(composed.create(object(), uuid4(), request(), uuid4())) == "v3"
    fake_request = type("Request", (), {"app": app})()
    assert get_v3_regeneration_service(fake_request) is regeneration


def test_direct_v3_service_injection_skips_runtime_factory(monkeypatch) -> None:
    creation = StubCreationService("v3")

    def unexpected_runtime_factory(settings):
        del settings
        raise AssertionError("runtime factory must not run for direct service injection")

    monkeypatch.setattr(
        "backend.app.main.build_optional_v3_demo_runtime", unexpected_runtime_factory
    )
    app = create_app(
        settings=Settings(
            app_env="staging",
            database_url="postgresql+psycopg://test:test@localhost/test",
            v3_execution_profile="DEMO",
        ),
        readiness_probe=lambda: None,
        v3_creation_service=creation,
    )

    composed = app.state.decision_creation_service_factory(object())
    assert asyncio.run(composed.create(object(), uuid4(), request(), uuid4())) == "v3"
    assert app.state.v3_demo_runtime is None


def test_staging_demo_composer_reuses_one_runtime_for_both_services(monkeypatch) -> None:
    runtime = object()
    creation = StubCreationService("automatic-v3")

    class Regeneration:
        async def regenerate(self, command):
            del command
            raise AssertionError("not invoked by composition test")

    regeneration = Regeneration()
    calls: list[tuple[Settings, object, object]] = []
    monkeypatch.setattr(
        "backend.app.main.build_optional_v3_demo_runtime",
        lambda settings, **kwargs: runtime,
    )

    def compose(settings, database_manager, received_runtime):
        calls.append((settings, database_manager, received_runtime))
        return creation, regeneration

    app = create_app(
        settings=Settings(
            app_env="staging",
            database_url="postgresql+psycopg://test:test@localhost/test",
            v3_execution_profile="DEMO",
        ),
        readiness_probe=lambda: None,
        v3_service_composer=compose,
    )

    service = app.state.decision_creation_service_factory(object())
    assert asyncio.run(service.create(object(), uuid4(), request(), uuid4())) == "automatic-v3"
    fake_request = type("Request", (), {"app": app})()
    assert get_v3_regeneration_service(fake_request) is regeneration
    assert app.state.v3_demo_runtime is runtime
    assert len(calls) == 1
    assert calls[0][2] is runtime


def test_injected_production_gate_enables_automatic_composition(monkeypatch) -> None:
    runtime = object()
    creation = StubCreationService("automatic-v3")

    class Regeneration:
        async def regenerate(self, command):
            del command
            raise AssertionError("not invoked by composition test")

    regeneration = Regeneration()
    composition_settings: list[Settings] = []
    monkeypatch.setattr(
        "backend.app.main.build_optional_v3_demo_runtime",
        lambda settings, **kwargs: runtime,
    )

    def compose(settings, database_manager, received_runtime):
        del database_manager
        assert received_runtime is runtime
        composition_settings.append(settings)
        return creation, regeneration

    app = create_app(
        settings=Settings(
            app_env="production",
            database_url="postgresql+psycopg://test:test@localhost/test",
            v3_execution_profile="PRODUCTION",
            v3_production_promotion_approved=False,
        ),
        readiness_probe=lambda: None,
        v3_promotion_gate=StaticV3ProductionPromotionGate(True),
        v3_service_composer=compose,
    )

    assert composition_settings[0].v3_production_promotion_approved is True
    fake_request = type("Request", (), {"app": app})()
    assert get_v3_regeneration_service(fake_request) is regeneration


def test_staging_demo_v3_success_keeps_public_api_contract() -> None:
    decision_id = uuid4()
    option_id = uuid4()

    class ApiV3Creation:
        async def create(self, session, user_id, request, idempotency_key):
            del session, user_id, idempotency_key
            return DecisionResponse(
                decision_id=decision_id,
                local_date=request.local_date,
                status_code="COMPLETED",
                safety_status_code="PASS",
                action_code="KEEP",
                requested_duration_minutes=10,
                duration_adjustment_source_code="USER_CHECKIN",
                final_plan=None,
                options=[
                    DecisionOptionResponse(
                        option_id=option_id,
                        option_code="FINAL_ROUTINE",
                        action_code="KEEP",
                    )
                ],
                reason_codes=["V3_COMPLETED"],
                summary="결정된 루틴입니다.",
                generation_mode_code="ORIGINAL",
                decision_engine_code="LLM_MULTI_AGENT",
                root_decision_id=decision_id,
                regeneration_sequence=0,
                created_at=datetime(2026, 8, 26, tzinfo=UTC),
            )

    app = create_app(
        settings=Settings(
            app_env="staging",
            database_url="postgresql+psycopg://test:test@localhost/test",
            v3_execution_profile="DEMO",
        ),
        readiness_probe=lambda: None,
        v3_creation_service=ApiV3Creation(),
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid4(), status_code=UserStatusCode.ACTIVE
    )

    def session_override():
        yield object()

    app.dependency_overrides[get_db_session] = session_override
    with TestClient(app) as client:
        api_response = client.post(
            "/api/v1/decisions",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "local_date": "2026-08-26",
                "daily_context_id": str(uuid4()),
                "expected_context_version": 1,
            },
        )
    assert api_response.status_code == 201
    body = api_response.json()
    assert DecisionResponse.model_validate(body).decision_id == decision_id
    assert body["options"] == [
        {
            "option_id": str(option_id),
            "option_code": "FINAL_ROUTINE",
            "action_code": "KEEP",
            "plan_id": None,
            "selectable": True,
            "blocked_reason_code": None,
        }
    ]
