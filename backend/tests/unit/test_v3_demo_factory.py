from __future__ import annotations

from types import SimpleNamespace

from backend.app.core.config import Settings
from backend.app.integrations.v3_demo_factory import build_optional_v3_demo_runtime


def _settings(**values: object) -> Settings:
    return Settings(
        app_env="staging",
        database_url="postgresql+psycopg://test:test@localhost/test",
        v3_execution_profile="DEMO",
        **values,
    )


def test_demo_factory_uses_the_application_runtime_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Runtime:
        async def create(self, *, root_snapshot):
            del root_snapshot

        async def regenerate(self, *, root_snapshot, regeneration_context):
            del root_snapshot, regeneration_context

    runtime = Runtime()

    def factory(settings, *, execution_profile, **kwargs):
        captured.update(
            settings=settings,
            execution_profile=execution_profile,
            kwargs=kwargs,
        )
        return runtime

    module = SimpleNamespace(build_v3_demo_runtime=factory)
    monkeypatch.setitem(
        __import__("sys").modules,
        "backend.app.integrations.langgraph.demo_runtime",
        module,
    )

    settings = _settings()
    assert build_optional_v3_demo_runtime(settings) is runtime
    assert captured == {
        "settings": settings,
        "execution_profile": "DEMO",
        "kwargs": {},
    }


def test_old_runtime_contract_fails_closed(monkeypatch) -> None:
    class OldRuntime:
        async def execute(self, constraint_envelope):
            del constraint_envelope

        async def regenerate(self, *, root_snapshot, regeneration_context):
            del root_snapshot, regeneration_context

    module = SimpleNamespace(
        build_v3_demo_runtime=lambda settings, *, execution_profile: OldRuntime()
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "backend.app.integrations.langgraph.demo_runtime",
        module,
    )

    assert build_optional_v3_demo_runtime(_settings()) is None


def test_production_without_promotion_does_not_construct_runtime(monkeypatch) -> None:
    module = SimpleNamespace(
        build_v3_demo_runtime=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("factory must not be called")
        )
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "backend.app.integrations.langgraph.demo_runtime",
        module,
    )
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://test:test@localhost/test",
        v3_execution_profile="PRODUCTION",
        v3_production_promotion_approved=False,
    )

    assert build_optional_v3_demo_runtime(settings) is None


def test_explicit_production_gate_result_controls_factory_construction(monkeypatch) -> None:
    class Runtime:
        async def create(self, *, root_snapshot):
            del root_snapshot

        async def regenerate(self, *, root_snapshot, regeneration_context):
            del root_snapshot, regeneration_context

    runtime = Runtime()
    captured: dict[str, object] = {}

    def factory(settings, *, execution_profile, **kwargs):
        captured.update(
            settings=settings,
            execution_profile=execution_profile,
            kwargs=kwargs,
        )
        return runtime

    monkeypatch.setitem(
        __import__("sys").modules,
        "backend.app.integrations.langgraph.demo_runtime",
        SimpleNamespace(build_v3_demo_runtime=factory),
    )
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://test:test@localhost/test",
        v3_execution_profile="PRODUCTION",
        v3_production_promotion_approved=False,
    )

    assert build_optional_v3_demo_runtime(settings, production_promotion_approved=True) is runtime
    assert captured["execution_profile"] == "PRODUCTION"


def test_openai_provider_gate_allows_an_approved_production_profile() -> None:
    from backend.app.integrations.llm_agents.openai import openai_demo_gates_ready

    settings = Settings(
        app_env="staging",
        database_url="postgresql+psycopg://test:test@localhost/test",
        v3_execution_profile="PRODUCTION",
        v3_production_promotion_approved=True,
        v3_langgraph_enabled=True,
        llm_agents_enabled=True,
        llm_agents_provider_code="OPENAI",
        llm_agents_model_code="approved-model-v1",
        llm_agents_approved_model_codes=("approved-model-v1",),
        openai_api_key="redacted-test-only-value",
    )

    assert openai_demo_gates_ready(settings, execution_profile="PRODUCTION") is True
