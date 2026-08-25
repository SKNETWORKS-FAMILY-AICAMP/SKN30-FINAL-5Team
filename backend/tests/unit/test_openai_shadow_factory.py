from __future__ import annotations

from unittest.mock import Mock

from langchain_core.messages import AIMessage
from pydantic import BaseModel, SecretStr

from backend.app.core.config import Settings
from backend.app.integrations.llm_agents import openai as openai_integration
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker


class _Output(BaseModel):
    value: int


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_agents_enabled": True,
        "llm_agents_provider_code": "OPENAI",
        "llm_agents_model_code": "approved-model-v1",
        "llm_agents_approved_model_codes": ("approved-model-v1",),
        "v3_langgraph_enabled": True,
        "v3_shadow_evaluation_enabled": True,
        "v3_regeneration_enabled": False,
        "openai_api_key": SecretStr("shadow-secret-sentinel"),
    }
    values.update(overrides)
    return Settings(**values)


def test_shadow_gate_defaults_false_and_is_independent_from_public_regeneration() -> None:
    defaults = Settings(_env_file=None)

    assert defaults.v3_shadow_evaluation_enabled is False
    assert defaults.v3_regeneration_enabled is False

    shadow_only = _settings()
    assert shadow_only.v3_shadow_evaluation_enabled is True
    assert shadow_only.v3_regeneration_enabled is False


def test_provider_factory_is_created_only_when_every_gate_and_cli_opt_in_are_present(
    monkeypatch,
) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(openai_integration, "ChatOpenAI", constructor)

    assert (
        openai_integration.build_openai_shadow_chat_model(
            _settings(v3_shadow_evaluation_enabled=False), allow_provider_calls=True
        )
        is None
    )
    assert (
        openai_integration.build_openai_shadow_chat_model(_settings(), allow_provider_calls=False)
        is None
    )
    assert (
        openai_integration.build_openai_shadow_chat_model(
            _settings(llm_agents_approved_model_codes=()), allow_provider_calls=True
        )
        is None
    )
    assert constructor.call_count == 0

    model = openai_integration.build_openai_shadow_chat_model(
        _settings(), allow_provider_calls=True
    )

    assert model is constructor.return_value
    constructor.assert_called_once()
    kwargs = constructor.call_args.kwargs
    assert kwargs["temperature"] == 0
    assert kwargs["max_retries"] == 0
    assert kwargs["callbacks"] == []
    assert kwargs["disable_streaming"] is True
    assert "shadow-secret-sentinel" not in repr(kwargs)


def test_api_key_presence_alone_never_enables_shadow_provider(monkeypatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(openai_integration, "ChatOpenAI", constructor)

    model = openai_integration.build_openai_shadow_chat_model(
        Settings(_env_file=None, openai_api_key=SecretStr("shadow-secret-sentinel")),
        allow_provider_calls=True,
    )

    assert model is None
    constructor.assert_not_called()


def test_openai_invoker_requests_native_strict_json_schema_and_discards_raw_message() -> None:
    structured = Mock()
    structured.invoke.return_value = {
        "raw": AIMessage(
            content="provider-raw-body-sentinel",
            usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        ),
        "parsed": {"value": 7},
        "parsing_error": None,
    }
    model = Mock()
    model.with_structured_output.return_value = structured
    invoker = StructuredChatInvoker(
        chat_model=model,
        model_code="approved-model-v1",
        use_native_json_schema=True,
    )

    result = invoker.invoke(
        role_code=LlmAgentRoleCode.TRAINING,
        prompt_version="prompt-v1",
        output_schema_version="output-v1",
        output_schema=_Output,
        messages=(),
        domain_validator=lambda value: value,
    )

    assert result.output == _Output(value=7)
    assert result.telemetry is not None
    assert result.telemetry.input_token_count == 3
    assert "provider-raw-body-sentinel" not in repr(result)
    model.with_structured_output.assert_called_once()
    kwargs = model.with_structured_output.call_args.kwargs
    assert kwargs == {"include_raw": True, "method": "json_schema", "strict": True}
    assert structured.invoke.call_args.kwargs["config"] == {"callbacks": []}
