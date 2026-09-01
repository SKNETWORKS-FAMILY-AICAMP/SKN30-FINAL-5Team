"""Qdrant implementation of the approved ExerciseRetriever domain port."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from uuid import UUID

from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.integrations.qdrant.client import (
    QdrantCollectionNotReadyError,
    QdrantGateway,
    QdrantProviderError,
    QdrantProviderTimeoutError,
    QdrantProviderUnavailableError,
)
from backend.app.integrations.qdrant.embedding import EmbeddingPort


@dataclass(frozen=True, slots=True)
class VectorIndexContract:
    """Read-only projection of one registry row used for a retrieval request."""

    catalog_version: str
    collection_name: str
    vector_index_version: str
    embedding_model_version: str
    embedding_input_schema_version: str
    vector_dimension: int
    distance_metric_code: str
    status_code: str


def exercise_retrieval_query_hash(request: ExerciseRetrievalRequest) -> str:
    canonical = json.dumps(
        {
            "request_schema_version": request.schema_version,
            "normalized_query_codes": list(request.normalized_query_codes),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _deterministic_fallback_ids(request: ExerciseRetrievalRequest) -> tuple[UUID, ...]:
    mandatory = list(request.mandatory_exercise_ids)
    mandatory_set = set(mandatory)
    previous = set(request.previous_plan_exercise_ids)
    fresh = [
        exercise_id
        for exercise_id in request.eligible_exercise_ids
        if exercise_id not in mandatory_set and exercise_id not in previous
    ]
    repeated = [
        exercise_id
        for exercise_id in request.eligible_exercise_ids
        if exercise_id not in mandatory_set and exercise_id in previous
    ]
    return tuple((mandatory + fresh + repeated)[: request.requested_limit])


def deterministic_retrieval_fallback(
    request: ExerciseRetrievalRequest,
    status: RetrievalStatusCode,
) -> ExerciseRetrievalResult:
    """Return the shared deterministic pool ordering for any vector failure."""

    ranked_ids = _deterministic_fallback_ids(request)
    return ExerciseRetrievalResult(
        ranked_exercise_ids=ranked_ids,
        similarity_scores=tuple(None for _ in ranked_ids),
        collection_name=None,
        vector_index_version=None,
        embedding_model_version=None,
        query_hash=exercise_retrieval_query_hash(request),
        retrieval_status_code=status,
        fallback_used=True,
    )


class QdrantExerciseRetriever:
    """Ranks only PostgreSQL-eligible IDs and falls back deterministically."""

    def __init__(
        self,
        *,
        gateway: QdrantGateway,
        embedding: EmbeddingPort,
        index: VectorIndexContract,
        max_provider_attempts: int = 2,
    ) -> None:
        if max_provider_attempts not in {1, 2}:
            raise ValueError("max_provider_attempts must be 1 or 2")
        self._gateway = gateway
        self._embedding = embedding
        self._index = index
        self._max_provider_attempts = max_provider_attempts

    def _fallback(
        self,
        request: ExerciseRetrievalRequest,
        status: RetrievalStatusCode,
    ) -> ExerciseRetrievalResult:
        return deterministic_retrieval_fallback(request, status)

    def _preflight_status(self, request: ExerciseRetrievalRequest) -> RetrievalStatusCode | None:
        if request.retrieval_mode is RetrievalModeCode.DETERMINISTIC_ONLY:
            return RetrievalStatusCode.VECTOR_INDEX_NOT_READY
        if self._index.status_code != "ACTIVE":
            return RetrievalStatusCode.VECTOR_INDEX_NOT_READY
        embedding_contract = self._embedding.contract
        if (
            request.catalog_version != self._index.catalog_version
            or embedding_contract.model_version != self._index.embedding_model_version
            or embedding_contract.input_schema_version != self._index.embedding_input_schema_version
            or embedding_contract.vector_dimension != self._index.vector_dimension
            or embedding_contract.distance_metric_code != self._index.distance_metric_code
        ):
            return RetrievalStatusCode.VECTOR_INDEX_VERSION_MISMATCH
        return None

    def retrieve(self, request: ExerciseRetrievalRequest) -> ExerciseRetrievalResult:
        preflight = self._preflight_status(request)
        if preflight is not None:
            return self._fallback(request, preflight)

        try:
            query_vector = self._embedding.embed_query(request.normalized_query_codes)
        except Exception:
            return self._fallback(request, RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE)
        if len(query_vector) != self._index.vector_dimension or any(
            not math.isfinite(value) for value in query_vector
        ):
            return self._fallback(request, RetrievalStatusCode.VECTOR_INDEX_VERSION_MISMATCH)

        excluded_ids = tuple(
            exercise_id
            for exercise_id in request.previous_plan_exercise_ids
            if exercise_id in set(request.eligible_exercise_ids)
            and exercise_id not in set(request.mandatory_exercise_ids)
        )
        hits = None
        for attempt in range(self._max_provider_attempts):
            try:
                hits = self._gateway.query_exercises(
                    collection_name=self._index.collection_name,
                    query_vector=query_vector,
                    eligible_exercise_ids=request.eligible_exercise_ids,
                    excluded_exercise_ids=excluded_ids,
                    catalog_version=self._index.catalog_version,
                    vector_index_version=self._index.vector_index_version,
                    embedding_model_version=self._index.embedding_model_version,
                    requested_limit=request.requested_limit,
                )
                break
            except QdrantProviderTimeoutError:
                if attempt + 1 == self._max_provider_attempts:
                    return self._fallback(request, RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT)
            except QdrantCollectionNotReadyError:
                return self._fallback(request, RetrievalStatusCode.VECTOR_INDEX_NOT_READY)
            except QdrantProviderUnavailableError:
                if attempt + 1 == self._max_provider_attempts:
                    return self._fallback(request, RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE)
            except QdrantProviderError:
                return self._fallback(request, RetrievalStatusCode.VECTOR_RESULT_NOT_CANONICAL)

        if not hits:
            return self._fallback(request, RetrievalStatusCode.VECTOR_RESULT_INSUFFICIENT)

        ids = tuple(hit.exercise_id for hit in hits)
        scores = tuple(hit.score for hit in hits)
        if (
            len(ids) != len(set(ids))
            or len(ids) > request.requested_limit
            or not set(ids).issubset(set(request.eligible_exercise_ids))
            or any(not math.isfinite(score) for score in scores)
        ):
            return self._fallback(request, RetrievalStatusCode.VECTOR_RESULT_NOT_CANONICAL)

        result = ExerciseRetrievalResult(
            ranked_exercise_ids=ids,
            similarity_scores=scores,
            collection_name=self._index.collection_name,
            vector_index_version=self._index.vector_index_version,
            embedding_model_version=self._index.embedding_model_version,
            query_hash=exercise_retrieval_query_hash(request),
            retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
            fallback_used=False,
        )
        result.validate_against(request)
        return result


__all__ = [
    "QdrantExerciseRetriever",
    "VectorIndexContract",
    "deterministic_retrieval_fallback",
    "exercise_retrieval_query_hash",
]
