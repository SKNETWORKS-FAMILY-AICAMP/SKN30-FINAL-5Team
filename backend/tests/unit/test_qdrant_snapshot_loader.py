from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pytest

from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalModeCode,
    RetrievalStatusCode,
)
from backend.app.integrations.qdrant.client import (
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
from backend.app.integrations.qdrant.snapshot_loader import (
    EligibleExerciseProjection,
    QdrantExercisePoolSnapshotLoader,
)
from backend.app.modules.decisions.v3_creation import V3CreationSource
from backend.tests.unit.test_v3_agent_contracts import (
    OUTSIDE,
    A,
    B,
    C,
    D,
    envelope,
    exercise,
)

NOW = datetime(2026, 8, 26, tzinfo=UTC)


@dataclass
class FakeGateway:
    hits: tuple[QdrantSearchHit, ...] = (
        QdrantSearchHit(C, 0.9),
        QdrantSearchHit(B, 0.8),
    )
    errors: list[Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def query_exercises(self, **kwargs: Any) -> tuple[QdrantSearchHit, ...]:
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return self.hits


class FakePostgreSQLCatalog:
    def __init__(self, *, stale_first_read: bool = False) -> None:
        self.records = {value: exercise(value) for value in (A, B, C)}
        self.stale_first_read = stale_first_read
        self.revalidation_calls = 0

    def load_eligible(self, *, source, envelope):
        assert source.normalized_values == {"goal_code": "GENERAL_FITNESS"}
        return EligibleExerciseProjection(
            catalog_version=envelope.catalog_version,
            exercises=tuple(self.records.values()),
            mandatory_exercise_ids=envelope.mandatory_exercise_ids,
            previous_plan_exercise_ids=(B,),
            normalized_query_codes=("BEGINNER", "GENERAL_FITNESS", "HOME"),
            requested_limit=3,
        )

    def revalidate(self, *, catalog_version, exercise_ids, envelope):
        self.revalidation_calls += 1
        assert catalog_version == envelope.catalog_version
        selected = exercise_ids
        if self.stale_first_read and self.revalidation_calls == 1:
            selected = exercise_ids[:-1]
        return tuple(self.records[value] for value in sorted(selected, key=str))


def _source() -> V3CreationSource:
    return V3CreationSource(
        local_date=date(2026, 8, 26),
        context_version=1,
        normalized_values={"goal_code": "GENERAL_FITNESS"},
    )


def _retriever(gateway: FakeGateway) -> QdrantExerciseRetriever:
    embedding = DeterministicFakeEmbeddingAdapter(
        EmbeddingContract(
            provider_code="FAKE",
            model_version="fake-model-v1",
            input_schema_version="exercise-embedding-input-v1",
            vector_dimension=4,
            distance_metric_code="COSINE",
        )
    )
    return QdrantExerciseRetriever(
        gateway=gateway,  # type: ignore[arg-type]
        embedding=embedding,
        index=VectorIndexContract(
            catalog_version="catalog-v3",
            collection_name="exercise_catalog_active",
            vector_index_version="vector-index-v1",
            embedding_model_version="fake-model-v1",
            embedding_input_schema_version="exercise-embedding-input-v1",
            vector_dimension=4,
            distance_metric_code="COSINE",
            status_code="ACTIVE",
        ),
    )


def _load(gateway: FakeGateway, *, stale_first_read: bool = False):
    catalog = FakePostgreSQLCatalog(stale_first_read=stale_first_read)
    loader = QdrantExercisePoolSnapshotLoader(
        catalog=catalog,
        retriever=_retriever(gateway),
        clock=lambda: NOW,
    )
    return loader.load(source=_source(), envelope=envelope()), catalog


def test_qdrant_ranking_is_revalidated_and_preserves_mandatory_hash_lineage() -> None:
    gateway = FakeGateway()

    root, catalog = _load(gateway)

    assert root.retrieval_result.retrieval_status_code is (
        RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED
    )
    assert root.exercise_pool.vector_ranked_exercise_ids == (C, B)
    assert root.exercise_pool.mandatory_exercise_ids == (A,)
    assert tuple(item.exercise_id for item in root.exercise_pool.exercises) == (A, B, C)
    assert root.exercise_pool.constraint_envelope_hash == root.constraint_envelope.envelope_hash
    assert catalog.revalidation_calls == 1
    assert gateway.calls[0]["eligible_exercise_ids"] == (A, B, C)


@pytest.mark.parametrize(
    "errors",
    [
        [QdrantProviderTimeoutError(), QdrantProviderTimeoutError()],
        [QdrantProviderUnavailableError(), QdrantProviderUnavailableError()],
    ],
)
def test_qdrant_failure_uses_deterministic_approved_pool(errors: list[Exception]) -> None:
    root, _ = _load(FakeGateway(errors=errors))

    assert root.retrieval_result.fallback_used
    assert root.exercise_pool.vector_ranked_exercise_ids == ()
    assert root.exercise_pool.mandatory_exercise_ids == (A,)
    assert tuple(item.exercise_id for item in root.exercise_pool.exercises) == (A, B, C)


def test_stale_or_noncanonical_qdrant_result_is_discarded() -> None:
    stale, catalog = _load(FakeGateway(), stale_first_read=True)
    outside, _ = _load(FakeGateway(hits=(QdrantSearchHit(OUTSIDE, 0.9),)))

    assert stale.retrieval_result.retrieval_status_code is RetrievalStatusCode.VECTOR_RESULT_STALE
    assert stale.exercise_pool.vector_ranked_exercise_ids == ()
    assert catalog.revalidation_calls == 2
    assert outside.retrieval_result.retrieval_status_code is (
        RetrievalStatusCode.VECTOR_RESULT_NOT_CANONICAL
    )
    assert outside.exercise_pool.vector_ranked_exercise_ids == ()


def test_vector_payload_contains_only_catalog_codes_and_eligible_ids() -> None:
    gateway = FakeGateway()

    root, _ = _load(gateway)
    serialized_call = repr(gateway.calls[0]).lower()

    assert root.retrieval_request.normalized_query_codes == (
        "BEGINNER",
        "GENERAL_FITNESS",
        "HOME",
    )
    for forbidden in (
        "user_id",
        "email",
        "pain",
        "severity",
        "raw_health",
        "wearable",
    ):
        assert forbidden not in serialized_call


def test_pool_reserves_a_slot_for_each_phase_and_for_goal_driving_work() -> None:
    """Ranking alone can hand the agents a pool no valid session fits into.

    Staging produced 22 ranked exercises with no cooldown and nothing marked as
    goal-driving, so no valid plan existed to propose and creation failed closed.
    """
    records = {
        A: exercise(A).model_copy(
            update={"phase_codes": ("WARMUP",), "role_eligibility_code": "SUPPORT"}
        ),
        B: exercise(B).model_copy(
            update={"phase_codes": ("MAIN",), "role_eligibility_code": "SUPPORT"}
        ),
        C: exercise(C).model_copy(
            update={"phase_codes": ("MAIN",), "role_eligibility_code": "CORE"}
        ),
        D: exercise(D).model_copy(
            update={"phase_codes": ("COOLDOWN",), "role_eligibility_code": "SUPPORT"}
        ),
    }
    request = ExerciseRetrievalRequest(
        catalog_version="catalog-v3",
        constraint_envelope_hash="a" * 64,
        eligible_exercise_ids=tuple(sorted(records, key=str)),
        normalized_query_codes=("GENERAL_FITNESS",),
        retrieval_mode=RetrievalModeCode.VECTOR_RANKED,
        requested_limit=2,
    )
    # Rank puts the two support movements first; on rank alone the pool would
    # carry no cooldown and no goal-driving work.
    result = ExerciseRetrievalResult(
        ranked_exercise_ids=(B, A),
        similarity_scores=(0.9, 0.8),
        collection_name="exercise-catalog-v3",
        vector_index_version="vector-index-v3",
        embedding_model_version="embedding-v3",
        query_hash="b" * 64,
        retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
        fallback_used=False,
    )

    selected = QdrantExercisePoolSnapshotLoader._selected_ids(
        request, result, tuple(records.values())
    )

    phases = {phase for value in selected for phase in records[value].phase_codes}
    assert phases == {"WARMUP", "MAIN", "COOLDOWN"}
    assert any(records[value].role_eligibility_code == "CORE" for value in selected)
