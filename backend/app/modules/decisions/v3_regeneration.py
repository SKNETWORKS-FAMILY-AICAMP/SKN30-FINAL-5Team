"""Application boundary for manual V3 routine regeneration.

This module intentionally contains contracts only. Implementations own locking,
graph execution, persistence, and response projection; API routes only translate
validated transport input into :class:`V3RegenerationCommand`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, Self, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.agents.v3_compiler import CompiledPlan
from backend.app.domain.agents.v3_contracts import RegenerationContext
from backend.app.domain.agents.v3_orchestration import (
    GraphTerminalStatusCode,
    RegenerationDifferenceCode,
    evaluate_regeneration_difference,
)
from backend.app.domain.agents.v3_persistence import (
    V3DecisionPersistenceBundle,
    V3RootSnapshotPersistence,
)


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
    expected_regeneration_sequence: Literal[0, 1, 2]


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


class V3RegenerationVersionSnapshot(_FrozenContract):
    """Server-owned versions used to reject stale persisted graph input."""

    catalog_version: str
    policy_version: str
    safety_rule_version: str


class V3StoredRegenerationSource(_FrozenContract):
    """Authorized DB projection loaded while the root lineage is locked.

    This object stays in the application layer. Only ``root_snapshot`` and the
    identifier-free ``RegenerationContext`` are passed to the graph runtime.
    """

    decision_id: UUID
    root_decision_id: UUID
    parent_decision_id: UUID | None = None
    plan_id: UUID
    regeneration_sequence: int = Field(ge=0, le=2)
    successful_regeneration_count: int = Field(ge=0, le=2)
    generation_mode_code: Literal["ORIGINAL", "REGENERATED"]
    decision_engine_code: V3DecisionEngineCode
    terminal_status_code: GraphTerminalStatusCode
    root_snapshot: V3RootSnapshotPersistence
    final_plan: CompiledPlan
    snapshot_expires_at: datetime
    versions: V3RegenerationVersionSnapshot

    @model_validator(mode="after")
    def validate_source_lineage(self) -> Self:
        if self.regeneration_sequence == 0 and self.decision_id != self.root_decision_id:
            raise ValueError("sequence zero must be the root decision")
        if self.regeneration_sequence > 0 and self.decision_id == self.root_decision_id:
            raise ValueError("a regenerated source cannot be the root decision")
        if self.snapshot_expires_at.tzinfo is None:
            raise ValueError("snapshot expiry must include timezone information")
        return self


class V3RegenerationIdempotencyRecord(_FrozenContract):
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: V3RegenerationResult


class V3GraphRuntimePort(Protocol):
    """Runs all three specialists from the shared stored root snapshot."""

    async def regenerate(
        self,
        *,
        root_snapshot: V3RootSnapshotPersistence,
        regeneration_context: RegenerationContext,
    ) -> V3DecisionPersistenceBundle: ...


class V3DecisionPersistencePort(Protocol):
    """Persistence operations used inside one caller-owned transaction."""

    def lock_regeneration_source(
        self, *, user_id: UUID, decision_id: UUID
    ) -> V3StoredRegenerationSource | None: ...

    def get_idempotency_result(
        self, *, user_id: UUID, idempotency_key: UUID
    ) -> V3RegenerationIdempotencyRecord | None: ...

    def persist_regeneration(
        self,
        *,
        bundle: V3DecisionPersistenceBundle,
        result: V3RegenerationResult,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
    ) -> None: ...


class V3RegenerationUnitOfWork(Protocol):
    decisions: V3DecisionPersistencePort

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None: ...


class V3DecisionResponseProjector(Protocol):
    """Keeps transport response construction out of the application service."""

    def project(self, result: V3RegenerationResult) -> object: ...


def _command_hash(command: V3RegenerationCommand) -> str:
    payload = {
        "decision_id": str(command.decision_id),
        "expected_plan_id": str(command.expected_plan_id),
        "expected_regeneration_sequence": command.expected_regeneration_sequence,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _regeneration_context(
    source: V3StoredRegenerationSource,
) -> RegenerationContext:
    return RegenerationContext(
        generation_sequence=source.regeneration_sequence + 1,
        previous_plan_hash=source.final_plan.compiled_plan_hash,
        previous_exercise_ids=tuple(
            item.prescription.exercise_id for item in source.final_plan.exercises
        ),
        variation_codes=(
            "CORE_EXERCISE_CHANGED",
            "EXERCISE_ORDER_CHANGED",
            "ROUTINE_STRUCTURE_CHANGED",
            "SET_REP_STRUCTURE_CHANGED",
        ),
    )


class V3RegenerationService:
    """Safety-preserving V3 regeneration orchestration and transaction boundary."""

    def __init__(
        self,
        *,
        unit_of_work: V3RegenerationUnitOfWork,
        graph_runtime: V3GraphRuntimePort,
        current_versions: V3RegenerationVersionSnapshot,
        enabled: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._unit_of_work = unit_of_work
        self._graph_runtime = graph_runtime
        self._current_versions = current_versions
        self._enabled = enabled
        self._clock = clock

    async def regenerate(self, command: V3RegenerationCommand) -> V3RegenerationResult:
        if not self._enabled:
            raise V3EngineDisabledError()
        request_hash = _command_hash(command)
        with self._unit_of_work as work:
            source = work.decisions.lock_regeneration_source(
                user_id=command.user_id, decision_id=command.decision_id
            )
            if source is None:
                # Ownership failures intentionally use the same not-found code.
                raise V3DecisionNotFoundError()
            prior = work.decisions.get_idempotency_result(
                user_id=command.user_id, idempotency_key=command.idempotency_key
            )
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise V3IdempotencyKeyReusedError()
                return prior.result
            self._validate_source(command, source)
            context = _regeneration_context(source)
            bundle = await self._graph_runtime.regenerate(
                root_snapshot=source.root_snapshot,
                regeneration_context=context,
            )
            result = self._validate_execution(source, bundle, context)
            work.decisions.persist_regeneration(
                bundle=bundle,
                result=result,
                user_id=command.user_id,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
            )
            return result

    def _validate_source(
        self, command: V3RegenerationCommand, source: V3StoredRegenerationSource
    ) -> None:
        if (
            command.expected_plan_id != source.plan_id
            or command.expected_regeneration_sequence != source.regeneration_sequence
            or source.successful_regeneration_count != source.regeneration_sequence
        ):
            raise V3StaleRegenerationError()
        if source.successful_regeneration_count >= 2:
            raise V3RegenerationLimitReachedError()
        envelope = source.root_snapshot.constraint_envelope
        if (
            source.terminal_status_code is not GraphTerminalStatusCode.COMPLETED
            or not envelope.plan_generation_allowed
            or envelope.safety_required_action_code is not None
        ):
            raise V3RegenerationNotAllowedError()
        now = self._clock()
        if (
            source.snapshot_expires_at <= now
            or source.versions != self._current_versions
            or envelope.catalog_version != self._current_versions.catalog_version
            or envelope.policy_version != self._current_versions.policy_version
            or envelope.safety_rule_version != self._current_versions.safety_rule_version
        ):
            raise V3RegenerationContextStaleError()

    @staticmethod
    def _validate_execution(
        source: V3StoredRegenerationSource,
        bundle: V3DecisionPersistenceBundle,
        context: RegenerationContext,
    ) -> V3RegenerationResult:
        if (
            bundle.root_decision_execution_id != source.root_decision_id
            or bundle.parent_decision_execution_id != source.decision_id
            or bundle.decision_execution_id in {source.root_decision_id, source.decision_id}
        ):
            raise V3RegenerationDecisionFailedError()
        if (
            bundle.root_snapshot != source.root_snapshot
            or bundle.terminal_status_code is not GraphTerminalStatusCode.COMPLETED
            or bundle.final_plan is None
        ):
            if bundle.final_plan is None:
                raise V3NoAlternativeAvailableError()
            raise V3RegenerationDecisionFailedError()
        difference = evaluate_regeneration_difference(
            source.final_plan,
            bundle.final_plan,
            generation_sequence=context.generation_sequence,
        )
        if not difference.meaningful:
            raise V3NoAlternativeAvailableError()
        engine = (
            V3DecisionEngineCode.DETERMINISTIC_FALLBACK
            if bundle.fallback_used
            else V3DecisionEngineCode.LLM_MULTI_AGENT
        )
        meaningful = tuple(
            code for code in _MEANINGFUL_CODES if code in difference.difference_codes
        )
        sequence = cast(Literal[1, 2], context.generation_sequence)
        return V3RegenerationResult(
            decision_id=bundle.decision_execution_id,
            root_decision_id=source.root_decision_id,
            parent_decision_id=source.decision_id,
            regeneration_sequence=sequence,
            decision_engine_code=engine,
            meaningful_difference_codes=meaningful,
        )


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
    "V3RegenerationService",
    "V3GraphRuntimePort",
    "V3DecisionPersistencePort",
    "V3RegenerationUnitOfWork",
    "V3DecisionResponseProjector",
    "V3StoredRegenerationSource",
    "V3RegenerationVersionSnapshot",
    "V3RegenerationIdempotencyRecord",
    "V3StaleRegenerationError",
]
