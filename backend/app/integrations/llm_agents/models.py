"""Provider-neutral result contracts for structured V3 LLM adapters.

Domain proposal and plan contracts deliberately do not live here. They are supplied by
``backend.app.domain.agents`` so integrations cannot drift from the approved V3 schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel


class LlmAgentRoleCode(StrEnum):
    TRAINING = "TRAINING"
    RECOVERY = "RECOVERY"
    FEASIBILITY = "FEASIBILITY"
    COORDINATOR = "COORDINATOR"


class LlmAgentFailureCode(StrEnum):
    """Stable failure codes exposed to the future orchestration layer."""

    PROVIDER_UNAVAILABLE = "LLM_AGENT_PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "LLM_AGENT_PROVIDER_TIMEOUT"
    SCHEMA_INVALID = "LLM_AGENT_SCHEMA_INVALID"
    DOMAIN_INVALID = "LLM_AGENT_DOMAIN_INVALID"


@dataclass(frozen=True, slots=True)
class LlmAgentFailure:
    """Sanitized failure metadata that never carries a provider error message."""

    code: LlmAgentFailureCode
    role_code: LlmAgentRoleCode
    prompt_version: str
    output_schema_version: str
    model_code: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class StructuredAgentResult[OutputT: BaseModel]:
    """All-or-nothing structured invocation result."""

    output: OutputT | None = None
    failure: LlmAgentFailure | None = None

    def __post_init__(self) -> None:
        if (self.output is None) == (self.failure is None):
            raise ValueError("exactly one of output or failure must be present")

    @property
    def succeeded(self) -> bool:
        return self.output is not None

    @classmethod
    def success(cls, output: OutputT) -> StructuredAgentResult[OutputT]:
        return cls(output=output)

    @classmethod
    def failed(
        cls,
        *,
        code: LlmAgentFailureCode,
        role_code: LlmAgentRoleCode,
        prompt_version: str,
        output_schema_version: str,
        model_code: str,
        attempt_count: int,
    ) -> StructuredAgentResult[OutputT]:
        return cls(
            failure=LlmAgentFailure(
                code=code,
                role_code=role_code,
                prompt_version=prompt_version,
                output_schema_version=output_schema_version,
                model_code=model_code,
                attempt_count=attempt_count,
            )
        )


__all__ = [
    "LlmAgentFailure",
    "LlmAgentFailureCode",
    "LlmAgentRoleCode",
    "StructuredAgentResult",
]
