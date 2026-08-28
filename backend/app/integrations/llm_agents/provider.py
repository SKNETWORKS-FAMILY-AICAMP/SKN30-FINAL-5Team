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
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

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


def _provider_output_model(
    output_schema: type[BaseModel], server_owned_fields: tuple[str, ...]
) -> type[BaseModel]:
    """Build a JSON-mode DTO without hashes that only the server can compute."""

    if not server_owned_fields:
        return output_schema
    fields: dict[str, Any] = {
        field_name: (field.annotation, field)
        for field_name, field in output_schema.model_fields.items()
        if field_name not in server_owned_fields
    }
    return create_model(
        output_schema.__name__,
        __config__=ConfigDict(extra="forbid", strict=True),
        **fields,
    )


def _is_provider_timeout(error: BaseException) -> bool:
    """Tell a call that ran out of time apart from a provider that was down.

    The configured bound is handed to the provider client as its own request
    timeout, so exceeding it raises inside the SDK rather than as a Python
    ``TimeoutError``. Provider SDKs give their timeout types no shared base
    class, and this boundary deliberately imports no provider package, so the
    type name is what is left to match on. Misreading a slow call as an outage
    hid a bound that was simply set too low.
    """

    if isinstance(error, TimeoutError):
        return True
    return any("timeout" in type(item).__name__.casefold() for item in _error_chain(error))


def _error_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _canonical_output(
    parsed_payload: object,
    *,
    provider_output_model: type[BaseModel],
    canonical_factory: Callable[[dict[str, object]], BaseModel] | None,
    server_owned_fields: tuple[str, ...],
) -> BaseModel:
    if canonical_factory is not None:
        if not isinstance(parsed_payload, dict):
            raise TypeError("structured provider output must be an object")
        parsed_payload = {
            key: value for key, value in parsed_payload.items() if key not in server_owned_fields
        }
    encoded_output = json.dumps(
        parsed_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    provider_output = provider_output_model.model_validate_json(encoded_output)
    if canonical_factory is None:
        return provider_output
    return canonical_factory(provider_output.model_dump())


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
        canonical_factory: Callable[[dict[str, object]], OutputT] | None = None,
        server_owned_fields: tuple[str, ...] = (),
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
            provider_output_model = _provider_output_model(output_schema, server_owned_fields)
            structured_model = cast(Any, self.chat_model).with_structured_output(
                provider_output_model.model_json_schema(), **binding_options
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
                parsed_output = cast(
                    OutputT,
                    _canonical_output(
                        parsed_payload,
                        provider_output_model=provider_output_model,
                        canonical_factory=canonical_factory,
                        server_owned_fields=server_owned_fields,
                    ),
                )
            except (OutputParserException, ValidationError, TypeError, ValueError):
                failure_code = LlmAgentFailureCode.SCHEMA_INVALID
            except Exception as error:  # provider exceptions have no neutral hierarchy
                failure_code = (
                    LlmAgentFailureCode.PROVIDER_TIMEOUT
                    if _is_provider_timeout(error)
                    else LlmAgentFailureCode.PROVIDER_UNAVAILABLE
                )
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
        canonical_factory: Callable[[dict[str, object]], OutputT] | None = None,
        server_owned_fields: tuple[str, ...] = (),
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
            provider_output_model = _provider_output_model(output_schema, server_owned_fields)
            structured_model = cast(Any, self.chat_model).with_structured_output(
                provider_output_model.model_json_schema(), **binding_options
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
                parsed_output = cast(
                    OutputT,
                    _canonical_output(
                        parsed_payload,
                        provider_output_model=provider_output_model,
                        canonical_factory=canonical_factory,
                        server_owned_fields=server_owned_fields,
                    ),
                )
            except (OutputParserException, ValidationError, TypeError, ValueError):
                failure_code = LlmAgentFailureCode.SCHEMA_INVALID
            except Exception as error:  # provider exceptions have no neutral hierarchy
                failure_code = (
                    LlmAgentFailureCode.PROVIDER_TIMEOUT
                    if _is_provider_timeout(error)
                    else LlmAgentFailureCode.PROVIDER_UNAVAILABLE
                )
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
