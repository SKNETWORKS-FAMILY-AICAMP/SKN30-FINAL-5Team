"""Production-bounded OpenAI chat model factories for V3 runtimes."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.app.core.config import Settings


def _build_openai_chat_model(settings: Settings) -> BaseChatModel:
    """Build the shared bounded provider object after a caller-specific gate."""

    api_key = settings.openai_api_key
    assert api_key is not None
    return ChatOpenAI(
        model=settings.llm_agents_model_code,
        api_key=api_key,
        base_url=settings.llm_api_base_url,
        temperature=0,
        timeout=settings.llm_agents_timeout_seconds,
        # StructuredChatInvoker owns the single bounded retry.
        max_retries=0,
        max_completion_tokens=settings.llm_agents_max_output_tokens,
        callbacks=[],
        disable_streaming=True,
    )


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
    return _build_openai_chat_model(settings)


def openai_demo_gates_ready(settings: Settings, *, execution_profile: str) -> bool:
    """Allow the approved V3 runtime profile to construct its bounded provider.

    ``PRODUCTION`` remains an explicit, server-owned promotion: it requires the
    promotion input in addition to the normal provider gates.  Without that
    input the application must expose V3 composition failure rather than route
    a user back to the legacy decision service.
    """

    profile_allowed = (settings.app_env == "staging" and execution_profile == "DEMO") or (
        settings.app_env in {"staging", "production"}
        and execution_profile == "PRODUCTION"
        and settings.v3_production_promotion_approved
    )

    return all(
        (
            profile_allowed,
            settings.llm_agents_enabled,
            settings.llm_agents_provider_code == "OPENAI",
            settings.llm_agents_model_code in settings.llm_agents_approved_model_codes,
            settings.openai_api_key is not None,
            settings.v3_langgraph_enabled,
        )
    )


def build_openai_demo_chat_model(
    settings: Settings,
    *,
    execution_profile: str,
) -> BaseChatModel | None:
    """Build no provider object unless every staging demo gate is satisfied."""

    if not openai_demo_gates_ready(settings, execution_profile=execution_profile):
        return None
    return _build_openai_chat_model(settings)


__all__ = [
    "build_openai_demo_chat_model",
    "build_openai_shadow_chat_model",
    "openai_demo_gates_ready",
    "openai_shadow_gates_ready",
]
