"""The pairwise judge, on the same provider boundary as everything else.

Mirrors `openai_judge.py`: it goes through `StructuredChatInvoker` rather than
the SDK, so it inherits the bounded retry, the output-token ceiling and
`tracing_context(enabled=False)` -- the pairwise prompts do not reach LangSmith
any more than the agents' do.

The self-preference caveat from PHASE 5 applies here too and is arguably sharper:
a judge comparing two plans, one of which its own family wrote, has a way to
express a preference that a pointwise score does not. `EVAL_JUDGE_MODEL_CODE`
points it at a different model, and `model_label` records which one answered.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.judge.pairwise import (
    PAIRWISE_OUTPUT_SCHEMA_VERSION,
    PAIRWISE_PROMPT_VERSION,
    PairwiseVerdict,
    pairwise_request_text,
)
from backend.tests.evaluation.runners.openai_provider import ProviderContext, build_provider

JUDGE_MODEL_CODE_ENV: Final = "EVAL_JUDGE_MODEL_CODE"


class PairwiseJudgeInvocationError(RuntimeError):
    """Raised when the pairwise judge could not return a valid structured verdict."""


@dataclass(frozen=True, slots=True)
class OpenAIPairwiseJudge:
    invoker: StructuredChatInvoker
    model_label: str

    def compare(self, *, system: str, payload: dict[str, Any]) -> PairwiseVerdict:
        result = self.invoker.invoke(
            # Borrowed only because the invoker needs a role for its failure
            # metadata. Nothing routes on it; the judge is not a service agent.
            role_code=LlmAgentRoleCode.COORDINATOR,
            prompt_version=PAIRWISE_PROMPT_VERSION,
            output_schema_version=PAIRWISE_OUTPUT_SCHEMA_VERSION,
            output_schema=PairwiseVerdict,
            messages=(
                SystemMessage(content=system),
                HumanMessage(content=pairwise_request_text(**payload)),
            ),
            domain_validator=lambda output: output,
        )
        if result.output is None:
            failure = result.failure
            raise PairwiseJudgeInvocationError(
                failure.code.value if failure is not None else "PAIRWISE_JUDGE_FAILED"
            )
        return result.output


def build_openai_pairwise_judge(
    provider: ProviderContext | None = None,
) -> OpenAIPairwiseJudge:
    override = os.environ.get(JUDGE_MODEL_CODE_ENV)
    context = build_provider(model_code=override) if override else (provider or build_provider())
    return OpenAIPairwiseJudge(
        invoker=StructuredChatInvoker(
            chat_model=context.chat_model,
            model_code=context.model_code,
            max_attempts=context.max_attempts,
            use_native_json_schema=True,
        ),
        model_label=context.label,
    )


__all__ = [
    "JUDGE_MODEL_CODE_ENV",
    "OpenAIPairwiseJudge",
    "PairwiseJudgeInvocationError",
    "build_openai_pairwise_judge",
]
