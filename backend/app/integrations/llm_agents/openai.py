"""Production-bounded OpenAI chat model factory for private V3 shadow runs."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.app.core.config import Settings


def openai_shadow_gates_ready(settings: Settings, *, allow_provider_calls: bool) -> bool:
    """Require every server-owned gate plus the explicit one-shot CLI opt-in."""

    return all(
        (
            settings.llm_agents_enabled,
            settings.llm_agents_provider_code == "OPENAI",
            settings.llm_agents_model_code in settings.llm_agents_approved_model_codes,
            settings.v3_langgraph_enabled,
            settings.v3_shadow_evaluation_enabled,
            allow_provider_calls,
            settings.openai_api_key is not None,
        )
    )


def build_openai_shadow_chat_model(
    settings: Settings,
    *,
    allow_provider_calls: bool,
) -> BaseChatModel | None:
    """Build no provider object unless all shadow gates are explicitly satisfied."""

    if not openai_shadow_gates_ready(settings, allow_provider_calls=allow_provider_calls):
        return None
    api_key = settings.openai_api_key
    assert api_key is not None
    return ChatOpenAI(
        model=settings.llm_agents_model_code,
        api_key=api_key,
        base_url=settings.llm_api_base_url,
        temperature=0,
        timeout=settings.llm_agents_timeout_seconds,
        max_retries=0,
        max_completion_tokens=settings.llm_agents_max_output_tokens,
        callbacks=[],
        disable_streaming=True,
    )


__all__ = ["build_openai_shadow_chat_model", "openai_shadow_gates_ready"]
