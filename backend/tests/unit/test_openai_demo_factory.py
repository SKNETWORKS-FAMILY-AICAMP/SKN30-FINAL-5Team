from __future__ import annotations

from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.integrations.llm_agents import openai as openai_integration


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "staging",
        "llm_agents_enabled": True,
        "llm_agents_provider_code": "OPENAI",
        "llm_agents_model_code": "approved-model-v1",
        "llm_agents_approved_model_codes": ("approved-model-v1",),
        "v3_langgraph_enabled": True,
        "v3_shadow_evaluation_enabled": False,
        "openai_api_key": SecretStr("demo-key-sentinel"),
    }
    values.update(overrides)
    return Settings(**values)


def test_demo_factory_builds_only_for_staging_demo(monkeypatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(openai_integration, "ChatOpenAI", constructor)

    model = openai_integration.build_openai_demo_chat_model(_settings(), execution_profile="DEMO")

    assert model is constructor.return_value
    assert constructor.call_count == 1
    kwargs = constructor.call_args.kwargs
    assert kwargs["model"] == "approved-model-v1"
    assert kwargs["max_retries"] == 0
    assert kwargs["callbacks"] == []


@pytest.mark.parametrize(
    ("settings_overrides", "profile"),
    [
        ({"app_env": "production"}, "DEMO"),
        ({"app_env": "local"}, "DEMO"),
        ({}, "SHADOW"),
        ({"llm_agents_enabled": False}, "DEMO"),
        ({"llm_agents_provider_code": "UNCONFIGURED"}, "DEMO"),
        ({"llm_agents_model_code": "not-approved"}, "DEMO"),
        ({"llm_agents_approved_model_codes": ()}, "DEMO"),
        ({"openai_api_key": None}, "DEMO"),
        ({"v3_langgraph_enabled": False}, "DEMO"),
    ],
)
def test_demo_gate_failure_constructs_no_provider(
    monkeypatch, settings_overrides: dict[str, object], profile: str
) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(openai_integration, "ChatOpenAI", constructor)

    model = openai_integration.build_openai_demo_chat_model(
        _settings(**settings_overrides), execution_profile=profile
    )

    assert model is None
    constructor.assert_not_called()


def test_demo_gate_does_not_depend_on_shadow_opt_in() -> None:
    assert openai_integration.openai_demo_gates_ready(
        _settings(v3_shadow_evaluation_enabled=False), execution_profile="DEMO"
    )
