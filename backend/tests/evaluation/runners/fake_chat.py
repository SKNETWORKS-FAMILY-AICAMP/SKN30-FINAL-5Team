"""A scripted, zero-cost chat model that stands in for the LLM provider.

`build_v3_demo_runtime` accepts an injected `chat_model`, so replacing only the
provider leaves the real graph, the real compiler, the real integrity validator
and the real deterministic fallback in the path.  That is the point: the
question this harness answers is not "does the model behave" but "does the
service stay safe when the model does not".

Each script below is one way a model can be wrong.  Feeding them through the
production path is how a safety claim becomes evidence instead of an assertion.

The class deliberately does not subclass `BaseChatModel`.  `StructuredChatInvoker`
casts the model to `Any` and calls exactly one method on it, so a narrow stand-in
keeps the fake honest: it can only use what a real provider is given.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Protocol

from langchain_core.messages import AIMessage, BaseMessage

from backend.app.integrations.llm_agents.models import LlmAgentRoleCode
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS

_ROLE_BY_PROMPT_VERSION: Final[dict[str, LlmAgentRoleCode]] = {
    prompt.version: role for role, prompt in ROLE_PROMPTS.items()
}

# Fixed so token metrics are exercised without pretending to measure a provider.
FAKE_INPUT_TOKENS: Final = 1200
FAKE_OUTPUT_TOKENS: Final = 300


class ProviderTimeoutError(RuntimeError):
    """Named so `_is_provider_timeout` classifies it the way an SDK timeout is."""


class ScriptCode(StrEnum):
    """One named way a model answer can be right or wrong."""

    COMPLIANT = "COMPLIANT"
    """A proposal or plan that respects every constraint."""

    SAFETY_VIOLATING = "SAFETY_VIOLATING"
    """Includes an exercise the safety envelope excluded."""

    POOL_ESCAPE = "POOL_ESCAPE"
    """Prescribes an exercise that is not in the supplied pool."""

    DURATION_VIOLATING = "DURATION_VIOLATING"
    """Claims and prescribes far more work than the requested duration."""

    PHASE_MISSING = "PHASE_MISSING"
    """Returns main work only, with no warmup and no cooldown."""

    ROLE_VIOLATING = "ROLE_VIOLATING"
    """An advisory specialist submits an exercise plan (ADR-0015)."""

    NOT_READY = "NOT_READY"
    """Answers with a non-READY status and no plan."""

    SCHEMA_INVALID = "SCHEMA_INVALID"
    """Returns a payload the output schema rejects."""

    PARSE_ERROR = "PARSE_ERROR"
    """Returns a structured-output envelope carrying a parsing error."""

    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    """Raises the provider's own timeout."""

    PROVIDER_EXCEPTION = "PROVIDER_EXCEPTION"
    """Raises an unclassified provider exception."""

    HANG = "HANG"
    """Never answers, so the graph's own node deadline has to fire."""


@dataclass(frozen=True, slots=True)
class Script:
    """What each role does for one case."""

    training: ScriptCode = ScriptCode.COMPLIANT
    recovery: ScriptCode = ScriptCode.COMPLIANT
    feasibility: ScriptCode = ScriptCode.COMPLIANT
    coordinator: ScriptCode = ScriptCode.COMPLIANT
    coordinator_repair: ScriptCode | None = None
    """Script for the repair call. Defaults to COMPLIANT so repair can succeed."""

    def for_role(self, role_code: LlmAgentRoleCode, *, repair: bool) -> ScriptCode:
        if role_code is LlmAgentRoleCode.COORDINATOR:
            if repair:
                return self.coordinator_repair or ScriptCode.COMPLIANT
            return self.coordinator
        return {
            LlmAgentRoleCode.TRAINING: self.training,
            LlmAgentRoleCode.RECOVERY: self.recovery,
            LlmAgentRoleCode.FEASIBILITY: self.feasibility,
        }[role_code]

    @property
    def is_compliant(self) -> bool:
        """Whether every role answers correctly for this run.

        A case says what a *working* provider should produce for its input. Once
        a fault is injected, "no plan" becomes a correct outcome rather than a
        missed expectation, so evaluators use this to tell the two apart instead
        of reporting fail-closed behaviour as a defect.
        """

        return all(
            code is ScriptCode.COMPLIANT
            for code in (
                self.training,
                self.recovery,
                self.feasibility,
                self.coordinator,
                self.coordinator_repair or ScriptCode.COMPLIANT,
            )
        )


class PayloadBuilder(Protocol):
    """Builds the answer body for one request under one script.

    Declared as a Protocol so the scripted model never imports the concrete
    builder: the two modules stay independent and the fake keeps no privileged
    knowledge of how a payload is produced.
    """

    def build(self, request: ModelRequest, script_code: ScriptCode) -> dict[str, object]: ...


@dataclass
class InvocationLog:
    """What the scripted model was asked, for the multi-agent metrics."""

    role_code: str
    mode_code: str
    script_code: str


@dataclass
class ScriptedChatModel:
    """Answer each role from its script, using only what the payload carries."""

    script: Script
    payload_builder: PayloadBuilder
    calls: list[InvocationLog] = field(default_factory=list)

    def with_structured_output(self, schema: Mapping[str, Any], **_: object) -> _ScriptedRunnable:
        del schema
        return _ScriptedRunnable(model=self)

    def _answer(self, messages: Sequence[BaseMessage]) -> dict[str, object]:
        request = _parse_request(messages)
        script_code = self.script.for_role(request.role_code, repair=request.is_repair)
        self.calls.append(
            InvocationLog(
                role_code=request.role_code.value,
                mode_code="REPAIR" if request.is_repair else "INITIAL",
                script_code=script_code.value,
            )
        )
        if script_code is ScriptCode.PROVIDER_TIMEOUT:
            raise ProviderTimeoutError("scripted provider timeout")
        if script_code is ScriptCode.PROVIDER_EXCEPTION:
            raise RuntimeError("scripted provider exception")
        parsed = self.payload_builder.build(request, script_code)
        if script_code is ScriptCode.PARSE_ERROR:
            return {
                "raw": _ai_message(),
                "parsed": None,
                "parsing_error": "scripted structured-output parsing failure",
            }
        return {"raw": _ai_message(), "parsed": parsed, "parsing_error": None}


@dataclass(frozen=True, slots=True)
class _ScriptedRunnable:
    model: ScriptedChatModel

    def invoke(self, messages: Sequence[BaseMessage], **_: object) -> dict[str, object]:
        return self.model._answer(messages)

    async def ainvoke(self, messages: Sequence[BaseMessage], **_: object) -> dict[str, object]:
        request = _parse_request(messages)
        script_code = self.model.script.for_role(request.role_code, repair=request.is_repair)
        if script_code is ScriptCode.HANG:
            self.model.calls.append(
                InvocationLog(
                    role_code=request.role_code.value,
                    mode_code="REPAIR" if request.is_repair else "INITIAL",
                    script_code=script_code.value,
                )
            )
            await asyncio.Event().wait()
        return self.model._answer(messages)


def _ai_message() -> AIMessage:
    return AIMessage(
        content="",
        usage_metadata={
            "input_tokens": FAKE_INPUT_TOKENS,
            "output_tokens": FAKE_OUTPUT_TOKENS,
            "total_tokens": FAKE_INPUT_TOKENS + FAKE_OUTPUT_TOKENS,
        },
    )


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Everything the scripted model is allowed to see: the serialized payload."""

    role_code: LlmAgentRoleCode
    prompt_version: str
    output_schema_version: str
    payload: Mapping[str, Any]

    @property
    def is_repair(self) -> bool:
        return self.payload.get("mode_code") == "REPAIR"


def _parse_request(messages: Sequence[BaseMessage]) -> ModelRequest:
    human = messages[-1]
    content = human.content
    if not isinstance(content, str):
        raise TypeError("scripted model expects one serialized human message")
    body = json.loads(content)
    prompt_version = body["prompt_version"]
    role_code = _ROLE_BY_PROMPT_VERSION.get(prompt_version)
    if role_code is None:
        raise KeyError(f"unmapped prompt version: {prompt_version}")
    return ModelRequest(
        role_code=role_code,
        prompt_version=prompt_version,
        output_schema_version=body["output_schema_version"],
        payload=body["input"],
    )


__all__ = [
    "FAKE_INPUT_TOKENS",
    "FAKE_OUTPUT_TOKENS",
    "InvocationLog",
    "ModelRequest",
    "PayloadBuilder",
    "ProviderTimeoutError",
    "Script",
    "ScriptCode",
    "ScriptedChatModel",
]
