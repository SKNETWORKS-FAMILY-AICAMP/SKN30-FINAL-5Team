"""The real LLM judge, bound to the same provider the agents use.

Reuses `StructuredChatInvoker` rather than calling the SDK, so the judge
inherits the boundary the service already established: bounded retries, no
streaming, an output-token ceiling, and -- notably -- `tracing_context(enabled=False)`,
so the judge's prompts do not reach LangSmith either.

Judging with the same model that produced the plan is a known bias and is
recorded in the result's `model_label`. `EVAL_JUDGE_MODEL_CODE` points the judge
at a different model when one is approved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.judge.judge import JudgeOutput, judge_request_text
from backend.tests.evaluation.judge.rubric import (
    JUDGE_OUTPUT_SCHEMA_VERSION,
    JUDGE_PROMPT_VERSION,
)
from backend.tests.evaluation.runners.openai_provider import ProviderContext, build_provider

JUDGE_MODEL_CODE_ENV: Final = "EVAL_JUDGE_MODEL_CODE"


class JudgeInvocationError(RuntimeError):
    """Raised when the judge could not return a valid structured verdict."""


@dataclass(frozen=True, slots=True)
class OpenAIJudge:
    invoker: StructuredChatInvoker
    model_label: str

    def score(self, *, system: str, payload: dict[str, Any]) -> JudgeOutput:
        result = self.invoker.invoke(
            # The judge is not one of the service's agents. It borrows the
            # COORDINATOR role code only because the invoker requires one for
            # its failure metadata; nothing routes on it.
            role_code=LlmAgentRoleCode.COORDINATOR,
            prompt_version=JUDGE_PROMPT_VERSION,
            output_schema_version=JUDGE_OUTPUT_SCHEMA_VERSION,
            output_schema=JudgeOutput,
            messages=(
                SystemMessage(content=system),
                HumanMessage(content=judge_request_text(payload)),
            ),
            domain_validator=lambda output: output,
        )
        if result.output is None:
            failure = result.failure
            raise JudgeInvocationError(
                failure.code.value if failure is not None else "JUDGE_INVOCATION_FAILED"
            )
        return result.output


def build_openai_judge(provider: ProviderContext | None = None) -> OpenAIJudge:
    """Build the judge, optionally on a different model than the agents used."""

    override = os.environ.get(JUDGE_MODEL_CODE_ENV)
    context = build_provider(model_code=override) if override else (provider or build_provider())
    return OpenAIJudge(
        invoker=StructuredChatInvoker(
            chat_model=context.chat_model,
            model_code=context.model_code,
            max_attempts=context.max_attempts,
            use_native_json_schema=False,
        ),
        model_label=context.label,
    )


__all__ = ["JUDGE_MODEL_CODE_ENV", "JudgeInvocationError", "OpenAIJudge", "build_openai_judge"]
