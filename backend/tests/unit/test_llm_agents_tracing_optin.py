"""ADR-0020: the LangSmith export is opt-in, and both suppression points obey it.

Exporting a provider call means the prompt reaches a second third-party
processor. The approval was for an opt-in, so the property that matters is not
"tracing can be turned on" but "it stays off unless someone turned it on".

Tracing is suppressed in two independent places -- the callback list on the model
and the context manager around the call -- and a change that freed only one would
look like it worked while still leaking, or look broken while still safe. Both
are asserted here, in both states.
"""

from __future__ import annotations

from itertools import cycle
from typing import ClassVar
from unittest.mock import Mock

import langchain_core.tracers.langchain as langchain_tracer_module
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tracers.base import BaseTracer
from pydantic import BaseModel, ConfigDict, SecretStr

from backend.app.core.config import Settings
from backend.app.integrations.llm_agents import openai as openai_integration
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "staging",
        "llm_agents_enabled": True,
        "llm_agents_provider_code": "OPENAI",
        "llm_agents_model_code": "approved-model-v1",
        "llm_agents_approved_model_codes": ("approved-model-v1",),
        "v3_langgraph_enabled": True,
        "openai_api_key": SecretStr("demo-key-sentinel"),
    }
    values.update(overrides)
    return Settings(**values)


# -- the default is off --------------------------------------------------


def test_tracing_is_off_unless_a_deployment_sets_it() -> None:
    """The whole approval rests on this being the default."""

    assert _settings().llm_agents_tracing_enabled is False


def test_an_invoker_built_without_a_decision_suppresses_tracing() -> None:
    """A caller that never heard of ADR-0020 must still be safe."""

    invoker = StructuredChatInvoker(chat_model=None, model_code="approved-model-v1")

    assert invoker.tracing_enabled is False
    assert invoker._invocation_config == {"callbacks": []}


# -- the model factory ---------------------------------------------------


def test_factory_detaches_the_tracer_by_default(monkeypatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(openai_integration, "ChatOpenAI", constructor)

    openai_integration.build_openai_demo_chat_model(_settings(), execution_profile="DEMO")

    assert constructor.call_args.kwargs["callbacks"] == []


def test_factory_lets_the_tracer_attach_when_approved(monkeypatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(openai_integration, "ChatOpenAI", constructor)

    openai_integration.build_openai_demo_chat_model(
        _settings(llm_agents_tracing_enabled=True), execution_profile="DEMO"
    )

    assert constructor.call_args.kwargs["callbacks"] is None


# -- the invocation boundary ---------------------------------------------


def test_invoker_passes_an_empty_callback_list_by_default() -> None:
    invoker = StructuredChatInvoker(
        chat_model=None, model_code="approved-model-v1", tracing_enabled=False
    )
    assert invoker._invocation_config == {"callbacks": []}


def test_invoker_passes_no_callback_override_when_approved() -> None:
    invoker = StructuredChatInvoker(
        chat_model=None, model_code="approved-model-v1", tracing_enabled=True
    )
    assert invoker._invocation_config is None


def test_the_tracing_scope_only_forces_suppression_when_off() -> None:
    """The context manager is the second point, and it must track the first."""

    from langsmith.run_helpers import get_tracing_context

    off = StructuredChatInvoker(
        chat_model=None, model_code="approved-model-v1", tracing_enabled=False
    )
    with off._tracing_scope():
        assert get_tracing_context()["enabled"] is False

    on = StructuredChatInvoker(
        chat_model=None, model_code="approved-model-v1", tracing_enabled=True
    )
    with on._tracing_scope():
        # Not forced either way: whatever the caller configured stands.
        assert get_tracing_context()["enabled"] is not False


# -- end to end: does LangSmith's own tracer attach? ---------------------
#
# The probe is "was `LangChainTracer` constructed during the call", because
# `langchain_core.callbacks.manager._configure` only builds one when tracing is
# enabled for that call. It is instantiated through a call-time import, so
# replacing the module attribute intercepts it, and nothing reaches the network.
#
# A custom tracer registered through `register_configure_hook` -- which is what
# the evaluation harness's `RunRecorder` is -- is attached unconditionally and
# sees the run either way. It therefore cannot answer this question at all, and
# a test written against it would pass without measuring anything.


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str


class _TraceableStructuredModel(GenericFakeChatModel):
    """A real chat model whose structured binding still goes through the model.

    The scripted stand-in in the evaluation harness is deliberately not a
    Runnable, so no tracer ever sees it and it cannot show this difference.
    """

    def with_structured_output(self, schema: object, **kwargs: object) -> RunnableLambda:
        del schema, kwargs

        def _call(messages: object) -> dict[str, object]:
            raw = self.invoke(messages)  # type: ignore[arg-type]
            return {"raw": raw, "parsed": {"value": "ok"}, "parsing_error": None}

        return RunnableLambda(_call)


class _ProbeTracer(BaseTracer):
    """Stands in for `LangChainTracer` and records only that it was built."""

    constructed: ClassVar[int] = 0

    def __init__(self, **kwargs: object) -> None:
        super().__init__()
        del kwargs
        type(self).constructed += 1

    def _persist_run(self, run: object) -> None:
        return None

    def copy_with_metadata_defaults(self, **kwargs: object) -> _ProbeTracer:
        """`_configure` calls this on the tracer it just built."""

        del kwargs
        return self


def _langsmith_tracer_attached(*, tracing_enabled: bool, monkeypatch) -> int:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "probe-key-never-sent")
    monkeypatch.setattr(langchain_tracer_module, "LangChainTracer", _ProbeTracer)
    _ProbeTracer.constructed = 0

    invoker = StructuredChatInvoker(
        chat_model=_TraceableStructuredModel(messages=cycle([AIMessage(content="ok")])),
        model_code="approved-model-v1",
        max_attempts=1,
        tracing_enabled=tracing_enabled,
    )
    result = invoker.invoke(
        role_code=LlmAgentRoleCode.COORDINATOR,
        prompt_version="test-prompt-v1",
        output_schema_version="test-output-v1",
        output_schema=_Answer,
        messages=(HumanMessage(content="hi"),),
        domain_validator=lambda output: output,
    )
    assert result.output is not None, result.failure
    return _ProbeTracer.constructed


def test_langsmith_never_attaches_by_default(monkeypatch) -> None:
    """The property the privacy boundary rests on, measured against the real tracer.

    Even with `LANGSMITH_TRACING=true` and a key in the environment -- the exact
    situation the suppression exists for -- no tracer is built.
    """

    assert _langsmith_tracer_attached(tracing_enabled=False, monkeypatch=monkeypatch) == 0


def test_langsmith_attaches_once_a_deployment_opts_in(monkeypatch) -> None:
    """ADR-0020, measured. Without this the approval buys nothing."""

    assert _langsmith_tracer_attached(tracing_enabled=True, monkeypatch=monkeypatch) > 0


# -- the setting reaches every construction site -------------------------


def test_build_structured_chat_invoker_carries_the_setting() -> None:
    from backend.app.integrations.llm_agents.provider import build_structured_chat_invoker

    assert build_structured_chat_invoker(_settings()).tracing_enabled is False
    assert (
        build_structured_chat_invoker(_settings(llm_agents_tracing_enabled=True)).tracing_enabled
        is True
    )


def test_paid_provider_context_carries_the_setting(monkeypatch) -> None:
    from backend.tests.evaluation.runners import openai_provider

    monkeypatch.setenv("OPENAI_API_KEY", "demo-key-sentinel")
    settings = openai_provider.build_settings()
    assert settings.llm_agents_tracing_enabled is False

    monkeypatch.setenv("LLM_AGENTS_TRACING_ENABLED", "true")
    settings = openai_provider.build_settings()
    assert settings.llm_agents_tracing_enabled is True
