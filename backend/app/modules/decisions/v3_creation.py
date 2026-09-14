"""Safety-first V3 initial decision creation application service.

Framework/provider objects are intentionally absent.  A runtime adapter returns
one validated persistence bundle; the repository stores proposals and the final
decision atomically inside the caller-owned unit of work.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from backend.app.domain.agents.v3_contracts import ConstraintEnvelope
from backend.app.domain.agents.v3_persistence import (
    V3DecisionPersistenceBundle,
    V3RootSnapshotPersistence,
)
from backend.app.modules.decisions.explanations import DecisionExplanation
from backend.app.modules.decisions.schemas import DecisionCreateRequest, DecisionResponse
from backend.app.modules.decisions.service import (
    DecisionContextNotFoundError,
    DecisionFailedError,
    IdempotencyKeyReusedError,
    StaleDecisionContextError,
)

_PRIVATE_KEY_FRAGMENTS = (
    "name",
    "email",
    "token",
    "credential",
    "birth",
    "raw",
    "wearable_sample",
    "calendar_text",
    "prompt",
    "reasoning",
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _validate_minimal_payload(value: object, *, path: str = "normalized_values") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in _PRIVATE_KEY_FRAGMENTS):
                raise ValueError(f"{path} contains a forbidden privacy field")
            _validate_minimal_payload(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_minimal_payload(item, path=path)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{path} contains an unsupported value")


class V3CreationSource(_FrozenContract):
    """Authorized repository projection with no direct identifier or raw data."""

    local_date: date
    context_version: int = Field(gt=0)
    normalized_values: dict[str, object]
    application_context: object | None = Field(default=None, exclude=True, repr=False)

    @field_validator("normalized_values")
    @classmethod
    def validate_normalized_values(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_minimal_payload(value)
        return value


class V3CreationIdempotencyRecord(_FrozenContract):
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    response: DecisionResponse


@dataclass(frozen=True, slots=True)
class V3CreationProjection:
    """Public response plus private, auditable narration metadata."""

    response: DecisionResponse
    explanation: DecisionExplanation


class V3ProviderExecutionError(RuntimeError):
    """Sanitized provider failure; raw provider exceptions stay in the adapter."""


class V3StructuredOutputError(RuntimeError):
    """Provider output failed the strict structured contract."""


class V3CreationRepositoryPort(Protocol):
    def acquire_lock(self, *, user_id: UUID, idempotency_key: UUID) -> None: ...
    def get_idempotency(
        self, *, user_id: UUID, idempotency_key: UUID
    ) -> V3CreationIdempotencyRecord | None: ...
    def load_source(self, *, user_id: UUID, daily_context_id: UUID) -> V3CreationSource | None: ...
    def persist_terminal(
        self,
        *,
        user_id: UUID,
        source: V3CreationSource,
        envelope: ConstraintEnvelope,
        response: DecisionResponse,
        explanation: DecisionExplanation,
    ) -> None: ...
    def persist_success(
        self,
        *,
        user_id: UUID,
        source: V3CreationSource,
        bundle: V3DecisionPersistenceBundle,
        response: DecisionResponse,
        explanation: DecisionExplanation,
    ) -> None: ...
    def save_idempotency(
        self,
        *,
        user_id: UUID,
        idempotency_key: UUID,
        request_hash: str,
        response: DecisionResponse,
    ) -> None: ...


class V3CreationUnitOfWork(Protocol):
    decisions: V3CreationRepositoryPort

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None: ...


class V3CreationSafetyPolicyPort(Protocol):
    def evaluate(self, source: V3CreationSource) -> ConstraintEnvelope: ...


class V3ExercisePoolSnapshotLoaderPort(Protocol):
    def load(
        self, *, source: V3CreationSource, envelope: ConstraintEnvelope
    ) -> V3RootSnapshotPersistence: ...


class V3InitialGraphRuntimePort(Protocol):
    async def create(
        self, *, root_snapshot: V3RootSnapshotPersistence
    ) -> V3DecisionPersistenceBundle: ...


class V3DeterministicFallbackPort(Protocol):
    def create(
        self, *, root_snapshot: V3RootSnapshotPersistence, failure_code: str
    ) -> V3DecisionPersistenceBundle: ...


class V3CreationResponseProjectorPort(Protocol):
    def project_terminal(
        self, *, source: V3CreationSource, envelope: ConstraintEnvelope
    ) -> V3CreationProjection: ...
    def project_success(
        self,
        *,
        source: V3CreationSource,
        bundle: V3DecisionPersistenceBundle,
    ) -> V3CreationProjection: ...


def _request_hash(request: DecisionCreateRequest) -> str:
    encoded = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class V3InitialCreationService:
    """Runs Safety before any provider and commits one complete V3 decision."""

    def __init__(
        self,
        *,
        unit_of_work_factory: Callable[[Session], V3CreationUnitOfWork],
        safety_policy: V3CreationSafetyPolicyPort,
        exercise_pool_loader: V3ExercisePoolSnapshotLoaderPort,
        graph_runtime: V3InitialGraphRuntimePort,
        fallback: V3DeterministicFallbackPort,
        projector: V3CreationResponseProjectorPort,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._safety_policy = safety_policy
        self._exercise_pool_loader = exercise_pool_loader
        self._graph_runtime = graph_runtime
        self._fallback = fallback
        self._projector = projector

    async def create(
        self,
        session: Session,
        user_id: UUID,
        request: DecisionCreateRequest,
        idempotency_key: UUID,
    ) -> DecisionResponse:
        request_hash = _request_hash(request)
        with self._unit_of_work_factory(session) as work:
            repository = work.decisions
            repository.acquire_lock(user_id=user_id, idempotency_key=idempotency_key)
            prior = repository.get_idempotency(user_id=user_id, idempotency_key=idempotency_key)
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise IdempotencyKeyReusedError
                return prior.response
            source = repository.load_source(
                user_id=user_id, daily_context_id=request.daily_context_id
            )
            if source is None or source.local_date != request.local_date:
                raise DecisionContextNotFoundError
            if source.context_version != request.expected_context_version:
                raise StaleDecisionContextError

            envelope = self._safety_policy.evaluate(source)
            if not envelope.plan_generation_allowed:
                projection = self._projector.project_terminal(source=source, envelope=envelope)
                response = projection.response
                repository.persist_terminal(
                    user_id=user_id,
                    source=source,
                    envelope=envelope,
                    response=response,
                    explanation=projection.explanation,
                )
            else:
                try:
                    root_snapshot = self._exercise_pool_loader.load(
                        source=source, envelope=envelope
                    )
                except (RuntimeError, ValueError):
                    raise DecisionFailedError from None
                try:
                    bundle = await self._graph_runtime.create(root_snapshot=root_snapshot)
                except TimeoutError:
                    bundle = self._fallback.create(
                        root_snapshot=root_snapshot, failure_code="PROVIDER_TIMEOUT"
                    )
                except (V3StructuredOutputError, ValidationError):
                    bundle = self._fallback.create(
                        root_snapshot=root_snapshot, failure_code="STRUCTURED_OUTPUT_INVALID"
                    )
                except V3ProviderExecutionError:
                    bundle = self._fallback.create(
                        root_snapshot=root_snapshot, failure_code="PROVIDER_UNAVAILABLE"
                    )
                if bundle.root_snapshot != root_snapshot or bundle.final_plan is None:
                    raise DecisionFailedError
                projection = self._projector.project_success(source=source, bundle=bundle)
                response = projection.response
                repository.persist_success(
                    user_id=user_id,
                    source=source,
                    bundle=bundle,
                    response=response,
                    explanation=projection.explanation,
                )
            repository.save_idempotency(
                user_id=user_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
            )
            return response


__all__ = [
    "V3CreationIdempotencyRecord",
    "V3CreationProjection",
    "V3CreationRepositoryPort",
    "V3CreationResponseProjectorPort",
    "V3CreationSafetyPolicyPort",
    "V3CreationSource",
    "V3CreationUnitOfWork",
    "V3DeterministicFallbackPort",
    "V3ExercisePoolSnapshotLoaderPort",
    "V3InitialCreationService",
    "V3InitialGraphRuntimePort",
    "V3ProviderExecutionError",
    "V3StructuredOutputError",
]
