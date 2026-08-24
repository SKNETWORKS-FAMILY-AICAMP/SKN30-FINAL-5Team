from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest

from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.integrations.qdrant.client import (
    QdrantCollectionNotReadyError,
    QdrantProviderTimeoutError,
    QdrantProviderUnavailableError,
    QdrantSearchHit,
)
from backend.app.integrations.qdrant.embedding import (
    DeterministicFakeEmbeddingAdapter,
    EmbeddingContract,
)
from backend.app.integrations.qdrant.exercise_retriever import (
    QdrantExerciseRetriever,
    VectorIndexContract,
)

EXERCISE_A = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_B = UUID("00000000-0000-0000-0000-000000000002")
EXERCISE_C = UUID("00000000-0000-0000-0000-000000000003")
OUTSIDE = UUID("00000000-0000-0000-0000-000000000099")


def _request(**changes: object) -> ExerciseRetrievalRequest:
    values: dict[str, object] = {
        "catalog_version": "catalog-v1",
        "constraint_envelope_hash": "a" * 64,
        "eligible_exercise_ids": (EXERCISE_A, EXERCISE_B, EXERCISE_C),
        "mandatory_exercise_ids": (EXERCISE_A,),
        "previous_plan_exercise_ids": (EXERCISE_B,),
        "normalized_query_codes": ("BEGINNER", "GENERAL_FITNESS", "HOME"),
        "retrieval_mode": RetrievalModeCode.VECTOR_RANKED,
        "requested_limit": 3,
    }
    values.update(changes)
    return ExerciseRetrievalRequest(**values)


def _index(**changes: object) -> VectorIndexContract:
    values: dict[str, object] = {
        "catalog_version": "catalog-v1",
        "collection_name": "exercise_catalog_active",
        "vector_index_version": "vector-index-v1",
        "embedding_model_version": "fake-model-v1",
        "embedding_input_schema_version": "exercise-embedding-input-v1",
        "vector_dimension": 4,
        "distance_metric_code": "COSINE",
        "status_code": "ACTIVE",
    }
    values.update(changes)
    return VectorIndexContract(**values)


def _embedding() -> DeterministicFakeEmbeddingAdapter:
    return DeterministicFakeEmbeddingAdapter(
        EmbeddingContract(
            provider_code="FAKE",
            model_version="fake-model-v1",
            input_schema_version="exercise-embedding-input-v1",
            vector_dimension=4,
            distance_metric_code="COSINE",
        )
    )


@dataclass
class FakeGateway:
    hits: tuple[QdrantSearchHit, ...] = (
        QdrantSearchHit(EXERCISE_C, 0.9),
        QdrantSearchHit(EXERCISE_A, 0.8),
    )
    errors: list[Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def query_exercises(self, **kwargs: Any) -> tuple[QdrantSearchHit, ...]:
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return self.hits


def _retriever(gateway: FakeGateway, **index_changes: object) -> QdrantExerciseRetriever:
    return QdrantExerciseRetriever(
        gateway=gateway,  # type: ignore[arg-type]
        embedding=_embedding(),
        index=_index(**index_changes),
    )


def test_request_is_translated_to_eligible_and_previous_plan_filters() -> None:
    gateway = FakeGateway()

    result = _retriever(gateway).retrieve(_request())

    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
    assert result.ranked_exercise_ids == (EXERCISE_C, EXERCISE_A)
    assert gateway.calls[0]["eligible_exercise_ids"] == (EXERCISE_A, EXERCISE_B, EXERCISE_C)
    assert gateway.calls[0]["excluded_exercise_ids"] == (EXERCISE_B,)
    assert gateway.calls[0]["requested_limit"] == 3


@pytest.mark.parametrize(
    "hits",
    [
        (QdrantSearchHit(OUTSIDE, 0.9),),
        (QdrantSearchHit(EXERCISE_A, 0.9), QdrantSearchHit(EXERCISE_A, 0.8)),
        (QdrantSearchHit(EXERCISE_A, float("nan")),),
        (QdrantSearchHit(EXERCISE_A, float("inf")),),
    ],
)
def test_noncanonical_provider_results_are_discarded(
    hits: tuple[QdrantSearchHit, ...],
) -> None:
    result = _retriever(FakeGateway(hits=hits)).retrieve(_request())

    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_RESULT_NOT_CANONICAL
    assert result.fallback_used is True
    assert result.ranked_exercise_ids == (EXERCISE_A, EXERCISE_C, EXERCISE_B)
    assert result.similarity_scores == (None, None, None)


def test_timeout_is_retried_once_then_maps_to_canonical_fallback() -> None:
    gateway = FakeGateway(errors=[QdrantProviderTimeoutError(), QdrantProviderTimeoutError()])

    result = _retriever(gateway).retrieve(_request())

    assert len(gateway.calls) == 2
    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_SEARCH_TIMEOUT
    assert result.fallback_used is True


def test_unavailable_is_retried_once_and_provider_text_is_not_exposed() -> None:
    gateway = FakeGateway(
        errors=[
            QdrantProviderUnavailableError("SECRET_API_KEY"),
            QdrantProviderUnavailableError("SECRET_API_KEY"),
        ]
    )

    result = _retriever(gateway).retrieve(_request())

    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE
    assert "SECRET_API_KEY" not in repr(result)


def test_collection_not_ready_maps_without_retry() -> None:
    gateway = FakeGateway(errors=[QdrantCollectionNotReadyError()])

    result = _retriever(gateway).retrieve(_request())

    assert len(gateway.calls) == 1
    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_NOT_READY


def test_deterministic_mode_and_inactive_index_do_not_call_qdrant() -> None:
    deterministic_gateway = FakeGateway()
    deterministic = _retriever(deterministic_gateway).retrieve(
        _request(retrieval_mode=RetrievalModeCode.DETERMINISTIC_ONLY)
    )
    inactive_gateway = FakeGateway()
    inactive = _retriever(inactive_gateway, status_code="READY").retrieve(_request())

    assert deterministic.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_NOT_READY
    assert inactive.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_NOT_READY
    assert deterministic_gateway.calls == []
    assert inactive_gateway.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("catalog_version", "catalog-v2"),
        ("embedding_model_version", "other-model-v1"),
        ("embedding_input_schema_version", "exercise-embedding-input-v2"),
        ("vector_dimension", 8),
        ("distance_metric_code", "DOT"),
    ],
)
def test_version_mismatch_never_calls_qdrant(field: str, value: object) -> None:
    gateway = FakeGateway()

    result = _retriever(gateway, **{field: value}).retrieve(_request())

    assert result.retrieval_status_code is RetrievalStatusCode.VECTOR_INDEX_VERSION_MISMATCH
    assert gateway.calls == []


def test_query_hash_contains_no_identifiers_and_is_stable() -> None:
    gateway = FakeGateway()
    first = _retriever(gateway).retrieve(_request())
    second = _retriever(FakeGateway()).retrieve(_request(previous_plan_exercise_ids=(EXERCISE_C,)))

    assert first.query_hash == second.query_hash
    assert str(EXERCISE_A) not in first.query_hash
