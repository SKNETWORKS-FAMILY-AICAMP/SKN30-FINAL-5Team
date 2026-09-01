"""PostgreSQL-authoritative ExercisePoolSnapshot composition with Qdrant ranking."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol
from uuid import UUID

from backend.app.domain.agents.retrieval import (
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    ExerciseRetriever,
    RetrievalFailureCode,
    RetrievalMetadata,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope
from backend.app.domain.agents.v3_persistence import V3RootSnapshotPersistence
from backend.app.integrations.qdrant.exercise_retriever import (
    deterministic_retrieval_fallback,
)
from backend.app.modules.decisions.v3_creation import V3CreationSource


class V3ExercisePoolSnapshotError(RuntimeError):
    """Sanitized fail-closed error raised when no canonical pool can be built."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class EligibleExerciseProjection:
    """PostgreSQL-owned deterministic eligibility projection."""

    catalog_version: str
    exercises: tuple[ExercisePoolExerciseRecord, ...]
    mandatory_exercise_ids: tuple[UUID, ...]
    previous_plan_exercise_ids: tuple[UUID, ...] = ()
    normalized_query_codes: tuple[str, ...] = ()
    retrieval_mode: RetrievalModeCode = RetrievalModeCode.VECTOR_RANKED
    requested_limit: int = 12

    def __post_init__(self) -> None:
        ids = tuple(item.exercise_id for item in self.exercises)
        if not ids or ids != tuple(sorted(set(ids), key=str)):
            raise ValueError("eligible exercises must be non-empty, unique, and canonical")
        if any(item.catalog_version != self.catalog_version for item in self.exercises):
            raise ValueError("eligible exercises must share one catalog version")
        if self.mandatory_exercise_ids != tuple(sorted(set(self.mandatory_exercise_ids), key=str)):
            raise ValueError("mandatory exercise IDs must be unique and canonical")
        if not set(self.mandatory_exercise_ids).issubset(ids):
            raise ValueError("mandatory exercise IDs must be eligible")
        if self.requested_limit <= 0:
            raise ValueError("requested_limit must be positive")


class PostgreSQLExercisePoolSourcePort(Protocol):
    """Canonical catalog boundary; implementations own all PostgreSQL access."""

    def load_eligible(
        self, *, source: V3CreationSource, envelope: ConstraintEnvelope
    ) -> EligibleExerciseProjection: ...

    def revalidate(
        self,
        *,
        catalog_version: str,
        exercise_ids: tuple[UUID, ...],
        envelope: ConstraintEnvelope,
    ) -> tuple[ExercisePoolExerciseRecord, ...]: ...


# Enough of each phase and of goal-driving work that an agent has real choices
# while composing to a requested duration. One of each left it with none.
_MIN_PER_PHASE: Final = 4
_MIN_CORE: Final = 3


@dataclass(slots=True)
class QdrantExercisePoolSnapshotLoader:
    """Compose a canonical root snapshot; Qdrant never establishes eligibility."""

    catalog: PostgreSQLExercisePoolSourcePort
    retriever: ExerciseRetriever
    fallback_version: str = "deterministic-pool-v1"
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def load(
        self, *, source: V3CreationSource, envelope: ConstraintEnvelope
    ) -> V3RootSnapshotPersistence:
        projection = self.catalog.load_eligible(source=source, envelope=envelope)
        eligible_ids = tuple(item.exercise_id for item in projection.exercises)
        if (
            projection.catalog_version != envelope.catalog_version
            or projection.mandatory_exercise_ids != envelope.mandatory_exercise_ids
            or set(eligible_ids) & set(envelope.excluded_exercise_ids)
        ):
            raise V3ExercisePoolSnapshotError("ELIGIBLE_POOL_NOT_CANONICAL")
        request = ExerciseRetrievalRequest(
            catalog_version=projection.catalog_version,
            constraint_envelope_hash=envelope.envelope_hash,
            eligible_exercise_ids=eligible_ids,
            mandatory_exercise_ids=projection.mandatory_exercise_ids,
            previous_plan_exercise_ids=projection.previous_plan_exercise_ids,
            normalized_query_codes=projection.normalized_query_codes,
            retrieval_mode=projection.retrieval_mode,
            requested_limit=projection.requested_limit,
        )
        try:
            result = self.retriever.retrieve(request)
            result.validate_against(request)
        except Exception:
            result = deterministic_retrieval_fallback(
                request, RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE
            )

        selected_ids = self._selected_ids(request, result, projection.exercises)
        records = self.catalog.revalidate(
            catalog_version=projection.catalog_version,
            exercise_ids=selected_ids,
            envelope=envelope,
        )
        if self._record_ids(records) != tuple(sorted(set(selected_ids), key=str)):
            result = deterministic_retrieval_fallback(
                request, RetrievalStatusCode.VECTOR_RESULT_STALE
            )
            selected_ids = self._selected_ids(request, result, projection.exercises)
            records = self.catalog.revalidate(
                catalog_version=projection.catalog_version,
                exercise_ids=selected_ids,
                envelope=envelope,
            )
        canonical_ids = tuple(sorted(set(selected_ids), key=str))
        if (
            self._record_ids(records) != canonical_ids
            or not set(projection.mandatory_exercise_ids).issubset(canonical_ids)
            or any(item.catalog_version != projection.catalog_version for item in records)
        ):
            raise V3ExercisePoolSnapshotError("POSTGRESQL_REVALIDATION_FAILED")

        metadata = self._metadata(result)
        pool = ExercisePoolSnapshot.create(
            catalog_version=projection.catalog_version,
            constraint_envelope_hash=envelope.envelope_hash,
            exercises=records,
            mandatory_exercise_ids=projection.mandatory_exercise_ids,
            # Reserving phase and role coverage can push a lower-ranked hit out
            # of the pool, and the snapshot may only name ranked exercises it
            # actually carries. The ranking order it keeps is unchanged.
            vector_ranked_exercise_ids=(
                tuple(item for item in result.ranked_exercise_ids if item in set(canonical_ids))
                if result.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
                else ()
            ),
            retrieval_metadata=metadata,
            created_at=self.clock(),
        )
        return V3RootSnapshotPersistence(
            constraint_envelope=envelope,
            exercise_pool=pool,
            retrieval_request=request,
            retrieval_result=result,
        )

    @staticmethod
    def _selected_ids(
        request: ExerciseRetrievalRequest,
        result: ExerciseRetrievalResult,
        eligible: tuple[ExercisePoolExerciseRecord, ...] = (),
    ) -> tuple[UUID, ...]:
        ordered = (
            *request.mandatory_exercise_ids,
            *result.ranked_exercise_ids,
            *request.eligible_exercise_ids,
        )
        unique = tuple(dict.fromkeys(ordered))
        mandatory_count = len(request.mandatory_exercise_ids)
        limit = max(request.requested_limit, mandatory_count)
        if not eligible:
            return unique[:limit]

        # Ranking alone once handed the agents 22 exercises with no cooldown and
        # no goal-driving work in them at all, so no valid session existed to
        # propose and the training agent answered NEEDS_INPUT. One candidate per
        # phase was still too thin to build a session that hits the requested
        # duration, so reserve a few of each before spending the rest on rank.
        by_id = {record.exercise_id: record for record in eligible}
        reserved: list[UUID] = list(request.mandatory_exercise_ids)

        def take(matches: Callable[[ExercisePoolExerciseRecord], bool]) -> None:
            """Reserve the next highest-ranked candidate that still fits."""

            for item in unique:
                record = by_id.get(item)
                if record is not None and matches(record) and item not in reserved:
                    reserved.append(item)
                    return

        for phase in ("WARMUP", "MAIN", "COOLDOWN"):
            for _ in range(_MIN_PER_PHASE):
                take(lambda record, phase=phase: phase in record.phase_codes)  # type: ignore[misc]
        for _ in range(_MIN_CORE):
            take(lambda record: record.role_eligibility_code == "CORE")

        remaining = [item for item in unique if item not in reserved]
        return tuple(dict.fromkeys((*reserved, *remaining)))[: max(limit, len(reserved))]

    @staticmethod
    def _record_ids(records: tuple[ExercisePoolExerciseRecord, ...]) -> tuple[UUID, ...]:
        return tuple(item.exercise_id for item in records)

    def _metadata(self, result: ExerciseRetrievalResult) -> RetrievalMetadata:
        succeeded = result.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
        return RetrievalMetadata(
            collection_name=result.collection_name,
            vector_index_version=result.vector_index_version,
            embedding_model_version=result.embedding_model_version,
            query_hash=result.query_hash,
            retrieval_status_code=result.retrieval_status_code,
            retrieval_failure_codes=(
                () if succeeded else (RetrievalFailureCode(result.retrieval_status_code.value),)
            ),
            deterministic_fallback_version=(None if succeeded else self.fallback_version),
            deterministic_pool_fallback_used=not succeeded,
        )


__all__ = [
    "EligibleExerciseProjection",
    "PostgreSQLExercisePoolSourcePort",
    "QdrantExercisePoolSnapshotLoader",
    "V3ExercisePoolSnapshotError",
]
