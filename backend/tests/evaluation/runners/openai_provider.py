"""Build the real provider, through the service's own gates.

The user asked for a run that matches the deployed service.  That means not
constructing a `ChatOpenAI` by hand here: `openai_demo_gates_ready` is what
staging actually requires before a provider object may exist, so this goes
through `build_openai_demo_chat_model` and inherits every bound the deployment
sets -- temperature 0, the approved model allowlist, the single bounded retry,
streaming off, and the output-token ceiling.

Nothing in this module runs unless a key is present in the environment *and* the
caller opts in explicitly. Fetching the key is the operator's step, not this
module's: see `docs/test/PAID_EVALUATION.md`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.integrations.llm_agents.openai import (
    build_openai_demo_chat_model,
    openai_demo_gates_ready,
)

OPENAI_API_KEY_ENV: Final = "OPENAI_API_KEY"
EVAL_MODEL_CODE_ENV: Final = "EVAL_LLM_AGENTS_MODEL_CODE"

# Everything below mirrors `infra/deployment/compose.staging.v3production.yaml`,
# which is what the deployed service actually runs. Taking the library defaults
# instead is not a smaller version of the same thing: `config.py` warns that they
# "suit a fast completion model" and that a reasoning model needs both raised or
# "every specialist call fails". A 5-second deadline and a 1,200-token ceiling
# starve Training, whose measured output is 2,375-2,893 tokens, so an evaluation
# run on the defaults measures a timeout rather than the service.
DEFAULT_MODEL_CODE: Final = "gpt-5.6-terra"
DEFAULT_TIMEOUT_SECONDS: Final = 60.0
DEFAULT_MAX_OUTPUT_TOKENS: Final = 4000

# The deployed profile is PRODUCTION, promoted; DEMO is the staging-only
# overlay. Mirroring PRODUCTION is what makes this "the same as deployed".
EXECUTION_PROFILE: Final = "PRODUCTION"


class ProviderUnavailableError(RuntimeError):
    """Raised when a paid run was requested and no provider can be built."""


@dataclass(frozen=True, slots=True)
class ProviderContext:
    """A live provider plus the identifiers a stored result must carry."""

    chat_model: BaseChatModel
    model_code: str
    provider_code: str
    max_output_tokens: int
    timeout_seconds: float
    max_attempts: int
    tracing_enabled: bool

    @property
    def label(self) -> str:
        return f"{self.provider_code}:{self.model_code}"


def api_key_present() -> bool:
    return bool(os.environ.get(OPENAI_API_KEY_ENV))


def build_settings(*, model_code: str | None = None) -> Settings:
    """Mirror the staging demo configuration the graph runs under.

    The key is read from the environment by the caller's shell; it is never
    written to a file, a fixture or a result by this harness.
    """

    api_key = os.environ.get(OPENAI_API_KEY_ENV)
    if not api_key:
        raise ProviderUnavailableError(
            f"{OPENAI_API_KEY_ENV} is not set; see docs/test/PAID_EVALUATION.md"
        )
    resolved_model = model_code or os.environ.get(EVAL_MODEL_CODE_ENV, DEFAULT_MODEL_CODE)
    return Settings(
        app_env="staging",
        llm_agents_enabled=True,
        llm_agents_provider_code="OPENAI",
        llm_agents_model_code=resolved_model,
        llm_agents_approved_model_codes=(resolved_model,),
        llm_agents_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        llm_agents_max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        v3_langgraph_enabled=True,
        v3_execution_profile=EXECUTION_PROFILE,
        v3_production_promotion_approved=True,
        openai_api_key=SecretStr(api_key),
    )


def build_provider(*, model_code: str | None = None) -> ProviderContext:
    """Build the provider only if every server-owned gate is satisfied."""

    settings = build_settings(model_code=model_code)
    if not openai_demo_gates_ready(settings, execution_profile=EXECUTION_PROFILE):
        raise ProviderUnavailableError(
            "openai_demo_gates_ready refused the configuration; no provider was built"
        )
    chat_model = build_openai_demo_chat_model(settings, execution_profile=EXECUTION_PROFILE)
    if chat_model is None:
        raise ProviderUnavailableError("the provider factory returned no model")
    return ProviderContext(
        chat_model=chat_model,
        model_code=settings.llm_agents_model_code,
        provider_code=settings.llm_agents_provider_code,
        max_output_tokens=settings.llm_agents_max_output_tokens,
        timeout_seconds=settings.llm_agents_timeout_seconds,
        max_attempts=min(settings.llm_agents_max_attempts, 2),
        tracing_enabled=settings.llm_agents_tracing_enabled,
    )


__all__ = [
    "DEFAULT_MODEL_CODE",
    "EVAL_MODEL_CODE_ENV",
    "EXECUTION_PROFILE",
    "OPENAI_API_KEY_ENV",
    "ProviderContext",
    "ProviderUnavailableError",
    "api_key_present",
    "build_provider",
    "build_settings",
]
