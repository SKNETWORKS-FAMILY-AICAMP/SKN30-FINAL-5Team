"""Sanitized structured-output invocation boundary for LangChain chat models."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langsmith import tracing_context
from pydantic import BaseModel, ValidationError

from backend.app.core.config import Settings
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    LlmInvocationTelemetry,
    StructuredAgentResult,
)

OutputT = TypeVar("OutputT", bound=BaseModel)


def _validated_usage(raw_message: object) -> tuple[int | None, int | None, bool]:
    if not isinstance(raw_message, AIMessage) or raw_message.usage_metadata is None:
        return None, None, False
    input_tokens = raw_message.usage_metadata.get("input_tokens")
    output_tokens = raw_message.usage_metadata.get("output_tokens")
    if (
        not isinstance(input_tokens, int)
        or isinstance(input_tokens, bool)
        or not isinstance(output_tokens, int)
        or isinstance(output_tokens, bool)
        or input_tokens < 0
        or output_tokens < 0
    ):
        return None, None, False
    return input_tokens, output_tokens, True


def _structured_payload(value: object) -> tuple[object, object]:
    """Return parsed data and the ephemeral message carrying provider usage."""

    if isinstance(value, dict) and {"raw", "parsed", "parsing_error"}.issubset(value):
        if value["parsing_error"] is not None:
            raise ValueError("structured output parsing failed")
        return value["parsed"], value["raw"]
    return value, None


@dataclass(frozen=True, slots=True)
class StructuredChatInvoker:
    """Invoke an injected provider model without selecting or importing a provider SDK."""

    chat_model: BaseChatModel | None
    model_code: str
    max_attempts: int = 2
    use_native_json_schema: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts not in {1, 2}:
            raise ValueError("max_attempts must be one or two")

    def invoke(
        self,
        *,
        role_code: LlmAgentRoleCode,
        prompt_version: str,
        output_schema_version: str,
        output_schema: type[OutputT],
        messages: Sequence[BaseMessage],
        domain_validator: Callable[[OutputT], OutputT],
    ) -> StructuredAgentResult[OutputT]:
        if self.chat_model is None:
            return self.failure(
                code=LlmAgentFailureCode.PROVIDER_UNAVAILABLE,
                role_code=role_code,
                prompt_version=prompt_version,
                output_schema_version=output_schema_version,
                attempt_count=0,
            )

        try:
            # V3 domain contracts are strict Pydantic models. JSON provider values
            # (UUID strings, enum strings, and arrays) must enter Pydantic through
            # JSON mode, so bind the Pydantic-generated schema and validate the
            # returned mapping with model_validate_json below.
            binding_options: dict[str, object] = {"include_raw": True}
            if self.use_native_json_schema:
                binding_options.update(method="json_schema", strict=True)
            structured_model = cast(Any, self.chat_model).with_structured_output(
                output_schema.model_json_schema(), **binding_options
            )
        except Exception:  # provider capabilities are not standardized
            return self.failure(
                code=LlmAgentFailureCode.PROVIDER_UNAVAILABLE,
                role_code=role_code,
                prompt_version=prompt_version,
                output_schema_version=output_schema_version,
                attempt_count=0,
            )

        started_ns = time.monotonic_ns()
        for attempt_count in range(1, self.max_attempts + 1):
            try:
                # LangSmith is a transitive dependency of langchain-core. Disable it
                # explicitly so ambient tracing settings cannot export prompt content.
                with tracing_context(enabled=False):
                    raw_output = structured_model.invoke(
                        list(messages),
                        config={"callbacks": []},
                    )
                parsed_payload, raw_message = _structured_payload(raw_output)
                encoded_output = json.dumps(
                    parsed_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                parsed_output = output_schema.model_validate_json(encoded_output)
            except (OutputParserException, ValidationError, TypeError, ValueError):
                failure_code = LlmAgentFailureCode.SCHEMA_INVALID
            except TimeoutError:
                failure_code = LlmAgentFailureCode.PROVIDER_TIMEOUT
            except Exception:  # external provider exceptions have no neutral hierarchy
                failure_code = LlmAgentFailureCode.PROVIDER_UNAVAILABLE
            else:
                latency_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
                input_tokens, output_tokens, usage_present = _validated_usage(raw_message)
                telemetry = LlmInvocationTelemetry(
                    attempt_count=attempt_count,
                    latency_ms=latency_ms,
                    input_token_count=input_tokens,
                    output_token_count=output_tokens,
                    provider_usage_present=usage_present,
                )
                try:
                    validated_output = domain_validator(parsed_output)
                    validated_output = output_schema.model_validate(validated_output)
                except Exception:  # domain validators may use different error types
                    return self.failure(
                        code=LlmAgentFailureCode.DOMAIN_INVALID,
                        role_code=role_code,
                        prompt_version=prompt_version,
                        output_schema_version=output_schema_version,
                        attempt_count=attempt_count,
                        telemetry=telemetry,
                    )
                return StructuredAgentResult.success(validated_output, telemetry=telemetry)

            if attempt_count == self.max_attempts:
                return self.failure(
                    code=failure_code,
                    role_code=role_code,
                    prompt_version=prompt_version,
                    output_schema_version=output_schema_version,
                    attempt_count=attempt_count,
                    telemetry=LlmInvocationTelemetry(
                        attempt_count=attempt_count,
                        latency_ms=max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
                    ),
                )

        raise AssertionError("bounded invocation loop did not return")

    async def ainvoke(
        self,
        *,
        role_code: LlmAgentRoleCode,
        prompt_version: str,
        output_schema_version: str,
        output_schema: type[OutputT],
        messages: Sequence[BaseMessage],
        domain_validator: Callable[[OutputT], OutputT],
    ) -> StructuredAgentResult[OutputT]:
        """Invoke the provider's native async boundary with bounded attempts.

        Cancellation is deliberately allowed to propagate. The graph owns node
        deadlines and must be able to cancel an in-flight provider coroutine.
        """

        if self.chat_model is None:
            return self.failure(
                code=LlmAgentFailureCode.PROVIDER_UNAVAILABLE,
                role_code=role_code,
                prompt_version=prompt_version,
                output_schema_version=output_schema_version,
                attempt_count=0,
            )

        try:
            binding_options: dict[str, object] = {"include_raw": True}
            if self.use_native_json_schema:
                binding_options.update(method="json_schema", strict=True)
            structured_model = cast(Any, self.chat_model).with_structured_output(
                output_schema.model_json_schema(), **binding_options
            )
        except Exception:
            return self.failure(
                code=LlmAgentFailureCode.PROVIDER_UNAVAILABLE,
                role_code=role_code,
                prompt_version=prompt_version,
                output_schema_version=output_schema_version,
                attempt_count=0,
            )

        started_ns = time.monotonic_ns()
        for attempt_count in range(1, self.max_attempts + 1):
            try:
                with tracing_context(enabled=False):
                    raw_output = await structured_model.ainvoke(
                        list(messages),
                        config={"callbacks": []},
                    )
                parsed_payload, raw_message = _structured_payload(raw_output)
                encoded_output = json.dumps(
                    parsed_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                parsed_output = output_schema.model_validate_json(encoded_output)
            except (OutputParserException, ValidationError, TypeError, ValueError):
                failure_code = LlmAgentFailureCode.SCHEMA_INVALID
            except TimeoutError:
                failure_code = LlmAgentFailureCode.PROVIDER_TIMEOUT
            except Exception:
                failure_code = LlmAgentFailureCode.PROVIDER_UNAVAILABLE
            else:
                latency_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
                input_tokens, output_tokens, usage_present = _validated_usage(raw_message)
                telemetry = LlmInvocationTelemetry(
                    attempt_count=attempt_count,
                    latency_ms=latency_ms,
                    input_token_count=input_tokens,
                    output_token_count=output_tokens,
                    provider_usage_present=usage_present,
                )
                try:
                    validated_output = domain_validator(parsed_output)
                    validated_output = output_schema.model_validate(validated_output)
                except Exception:
                    return self.failure(
                        code=LlmAgentFailureCode.DOMAIN_INVALID,
                        role_code=role_code,
                        prompt_version=prompt_version,
                        output_schema_version=output_schema_version,
                        attempt_count=attempt_count,
                        telemetry=telemetry,
                    )
                return StructuredAgentResult.success(validated_output, telemetry=telemetry)

            if attempt_count == self.max_attempts:
                return self.failure(
                    code=failure_code,
                    role_code=role_code,
                    prompt_version=prompt_version,
                    output_schema_version=output_schema_version,
                    attempt_count=attempt_count,
                    telemetry=LlmInvocationTelemetry(
                        attempt_count=attempt_count,
                        latency_ms=max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
                    ),
                )

        raise AssertionError("bounded async invocation loop did not return")

    def failure(
        self,
        *,
        code: LlmAgentFailureCode,
        role_code: LlmAgentRoleCode,
        prompt_version: str,
        output_schema_version: str,
        attempt_count: int,
        telemetry: LlmInvocationTelemetry | None = None,
    ) -> StructuredAgentResult[OutputT]:
        return StructuredAgentResult.failed(
            code=code,
            role_code=role_code,
            prompt_version=prompt_version,
            output_schema_version=output_schema_version,
            model_code=self.model_code,
            attempt_count=attempt_count,
            telemetry=telemetry,
        )


def build_structured_chat_invoker(
    settings: Settings,
    *,
    chat_model: BaseChatModel | None = None,
) -> StructuredChatInvoker:
    """Build a fail-closed invoker until an approved provider model is injected."""

    configured = (
        settings.llm_agents_enabled
        and settings.llm_agents_provider_code != "UNCONFIGURED"
        and settings.llm_agents_model_code != "unconfigured"
    )
    return StructuredChatInvoker(
        chat_model=chat_model if configured else None,
        model_code=settings.llm_agents_model_code,
        max_attempts=settings.llm_agents_max_attempts,
    )


__all__ = ["StructuredChatInvoker", "build_structured_chat_invoker"]
