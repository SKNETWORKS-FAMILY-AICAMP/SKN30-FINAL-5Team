"""Application boundary for manual V3 routine regeneration.

This module intentionally contains contracts only. Implementations own locking,
graph execution, persistence, and response projection; API routes only translate
validated transport input into :class:`V3RegenerationCommand`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.agents.v3_orchestration import RegenerationDifferenceCode


class V3DecisionEngineCode(StrEnum):
    LLM_MULTI_AGENT = "LLM_MULTI_AGENT"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class V3RegenerationFailureCode(StrEnum):
    DECISION_NOT_FOUND = "DECISION_NOT_FOUND"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    STALE_REGENERATION = "STALE_REGENERATION"
    REGENERATION_CONTEXT_STALE = "REGENERATION_CONTEXT_STALE"
    REGENERATION_LIMIT_REACHED = "REGENERATION_LIMIT_REACHED"
    REGENERATION_NOT_ALLOWED = "REGENERATION_NOT_ALLOWED"
    NO_ALTERNATIVE_AVAILABLE = "NO_ALTERNATIVE_AVAILABLE"
    DECISION_FAILED = "DECISION_FAILED"
    V3_ENGINE_DISABLED = "V3_ENGINE_DISABLED"


class V3RegenerationError(RuntimeError):
    """Base application error carrying a stable API-facing machine code."""

    code: V3RegenerationFailureCode

    def __init__(self) -> None:
        super().__init__(self.code.value)


class V3DecisionNotFoundError(V3RegenerationError):
    code = V3RegenerationFailureCode.DECISION_NOT_FOUND


class V3IdempotencyKeyReusedError(V3RegenerationError):
    code = V3RegenerationFailureCode.IDEMPOTENCY_KEY_REUSED


class V3StaleRegenerationError(V3RegenerationError):
    code = V3RegenerationFailureCode.STALE_REGENERATION


class V3RegenerationContextStaleError(V3RegenerationError):
    code = V3RegenerationFailureCode.REGENERATION_CONTEXT_STALE


class V3RegenerationLimitReachedError(V3RegenerationError):
    code = V3RegenerationFailureCode.REGENERATION_LIMIT_REACHED


class V3RegenerationNotAllowedError(V3RegenerationError):
    code = V3RegenerationFailureCode.REGENERATION_NOT_ALLOWED


class V3NoAlternativeAvailableError(V3RegenerationError):
    code = V3RegenerationFailureCode.NO_ALTERNATIVE_AVAILABLE


class V3RegenerationDecisionFailedError(V3RegenerationError):
    code = V3RegenerationFailureCode.DECISION_FAILED


class V3EngineDisabledError(V3RegenerationError):
    code = V3RegenerationFailureCode.V3_ENGINE_DISABLED


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class V3RegenerationCommand(_FrozenContract):
    """Authenticated, optimistic-concurrency input for one regeneration attempt.

    ``user_id`` is an application authorization boundary and must never be
    projected into a LangGraph state, LLM payload, or vector query.
    """

    user_id: UUID
    decision_id: UUID
    idempotency_key: UUID
    expected_plan_id: UUID
    expected_regeneration_sequence: Literal[0, 1]


_MEANINGFUL_CODES = (
    RegenerationDifferenceCode.CORE_EXERCISE_CHANGED,
    RegenerationDifferenceCode.SET_REPETITION_STRUCTURE_CHANGED,
    RegenerationDifferenceCode.EXERCISE_SEQUENCE_CHANGED,
    RegenerationDifferenceCode.ROUTINE_COMPOSITION_CHANGED,
)


class V3RegenerationResult(_FrozenContract):
    """Successful, persisted lineage returned by the application service.

    The API layer uses ``decision_id`` with the existing stored-decision read
    path to build ``DecisionResponse``; this contract does not expose DB rows or
    an unvalidated response dictionary.
    """

    decision_id: UUID
    root_decision_id: UUID
    parent_decision_id: UUID
    regeneration_sequence: Literal[1, 2]
    generation_mode_code: Literal["REGENERATED"] = "REGENERATED"
    decision_engine_code: V3DecisionEngineCode
    meaningful_difference_codes: tuple[RegenerationDifferenceCode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_success_lineage(self) -> Self:
        if self.decision_id in {self.root_decision_id, self.parent_decision_id}:
            raise ValueError("a regeneration must create a new decision")
        if self.regeneration_sequence == 1 and self.parent_decision_id != self.root_decision_id:
            raise ValueError("the first regeneration parent must be the root decision")
        if self.regeneration_sequence == 2 and self.parent_decision_id == self.root_decision_id:
            raise ValueError("the second regeneration parent must be the first regeneration")
        codes = self.meaningful_difference_codes
        expected = tuple(code for code in _MEANINGFUL_CODES if code in codes)
        if codes != expected:
            raise ValueError("meaningful difference codes must be unique and canonical")
        return self


class V3RegenerationServicePort(Protocol):
    """API-independent asynchronous V3 regeneration use case."""

    async def regenerate(self, command: V3RegenerationCommand) -> V3RegenerationResult: ...


__all__ = [
    "V3DecisionEngineCode",
    "V3DecisionNotFoundError",
    "V3EngineDisabledError",
    "V3IdempotencyKeyReusedError",
    "V3NoAlternativeAvailableError",
    "V3RegenerationCommand",
    "V3RegenerationContextStaleError",
    "V3RegenerationDecisionFailedError",
    "V3RegenerationError",
    "V3RegenerationFailureCode",
    "V3RegenerationLimitReachedError",
    "V3RegenerationNotAllowedError",
    "V3RegenerationResult",
    "V3RegenerationServicePort",
    "V3StaleRegenerationError",
]
