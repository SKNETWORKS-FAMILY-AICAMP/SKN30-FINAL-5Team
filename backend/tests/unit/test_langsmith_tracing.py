"""LangSmith stays off unless a composition injects a tracer (ADR-0020)."""

from __future__ import annotations

import inspect
import textwrap

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers import LangChainTracer
from langsmith import tracing_context
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.domain.agents.v3_contracts import (
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.app.integrations.langsmith_tracing import (
    DEFAULT_PROJECT_NAME,
    build_langsmith_tracer,
)
from backend.app.integrations.llm_agents.provider import (
    StructuredChatInvoker,
    build_structured_chat_invoker,
)
from backend.app.integrations.llm_agents.specialists import TrainingAgentAdapter
from backend.tests.unit.llm_agent_test_support import (
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import envelope, pool, proposal

_TRACED_SETTINGS = {
    "langsmith_tracing_enabled": True,
    "langsmith_api_key": "lsv2_test_key",
    "langsmith_project": "helkki-test",
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_tracing_is_off_by_default() -> None:
    settings = _settings()

    assert settings.langsmith_tracing_enabled is False
    assert build_langsmith_tracer(settings) is None


def test_enabling_tracing_without_a_key_fails_startup() -> None:
    """A silent credential gap would drop every trace without saying so."""

    with pytest.raises(ValidationError, match="LANGSMITH_API_KEY"):
        _settings(langsmith_tracing_enabled=True)


def test_tracing_is_refused_in_production() -> None:
    """ADR-0020 limits the export to the staging shadow and demo surfaces."""

    with pytest.raises(ValidationError, match="APP_ENV=production"):
        _settings(app_env="production", **_TRACED_SETTINGS)


def test_plaintext_langsmith_endpoint_is_refused() -> None:
    with pytest.raises(ValidationError, match="must be https"):
        _settings(**_TRACED_SETTINGS | {"langsmith_endpoint": "http://smith.internal"})


def test_configured_tracer_uses_the_named_project() -> None:
    tracer = build_langsmith_tracer(_settings(app_env="staging", **_TRACED_SETTINGS))

    assert isinstance(tracer, LangChainTracer)
    assert tracer.project_name == "helkki-test"


def test_tracer_without_a_named_project_does_not_land_in_langsmith_default() -> None:
    settings = _settings(app_env="staging", **_TRACED_SETTINGS | {"langsmith_project": None})

    tracer = build_langsmith_tracer(settings)

    assert isinstance(tracer, LangChainTracer)
    assert tracer.project_name == DEFAULT_PROJECT_NAME


def test_api_key_is_not_readable_from_the_settings_repr() -> None:
    settings = _settings(app_env="staging", **_TRACED_SETTINGS)

    assert "lsv2_test_key" not in repr(settings)


def test_the_production_invoker_is_never_handed_a_tracer() -> None:
    """The setting alone must not reach the production decision path.

    Only the staging shadow and demo compositions pass handlers. This asserts the
    shared factory stays empty even with tracing fully configured, so enabling the
    flag on a box that also serves the API cannot start exporting its prompts.
    """

    settings = _settings(
        app_env="staging",
        llm_agents_enabled=True,
        llm_agents_provider_code="OPENAI",
        llm_agents_model_code="approved-model-v1",
        **_TRACED_SETTINGS,
    )

    invoker = build_structured_chat_invoker(settings)

    assert invoker.tracing_callbacks == ()


class _RecordingHandler(BaseCallbackHandler):
    """Stands in for LangChainTracer without opening a network client."""

    def __init__(self) -> None:
        self.starts = 0

    def on_llm_start(self, *args: object, **kwargs: object) -> None:
        self.starts += 1

    def on_chat_model_start(self, *args: object, **kwargs: object) -> None:
        self.starts += 1


def test_an_injected_handler_still_records_under_a_disabled_tracing_context() -> None:
    """The whole design rests on this asymmetry, so it is pinned here.

    `provider.py` keeps `tracing_context(enabled=False)` unconditionally so that no
    environment variable can start an export, and relies on `langchain_core` running
    explicitly passed handlers anyway. If that ever stops being true, tracing goes
    silent rather than failing, and this test is the only thing that would say so.
    """

    handler = _RecordingHandler()
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    output = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(responses=[tool_response(SpecialistAgentProposal, output, 1)])
    adapter = TrainingAgentAdapter(
        invoker=StructuredChatInvoker(
            chat_model=model,
            model_code="fake-model-v1",
            tracing_callbacks=(handler,),
        )
    )

    with tracing_context(enabled=False):
        result = adapter.propose(
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )

    assert result.succeeded
    assert handler.starts >= 1


def test_both_call_sites_pin_ambient_tracing_off() -> None:
    """The `enabled=False` argument is the guarantee, so it is read, not assumed.

    Passing the flag through a setting would let `LANGSMITH_TRACING=true` in the
    environment start an export on any path, which is exactly what ADR-0020 rules out.
    Both call sites must therefore stay literal.
    """

    for owner in (StructuredChatInvoker.invoke, V3LangGraphRuntime.ainvoke):
        source = textwrap.dedent(inspect.getsource(owner))
        assert "tracing_context(enabled=False)" in source
        assert "tracing_context(enabled=self" not in source


def test_the_graph_runtime_starts_untraced() -> None:
    runtime = V3LangGraphRuntime(graph=create_v3_graph())

    assert runtime.tracing_callbacks == ()
