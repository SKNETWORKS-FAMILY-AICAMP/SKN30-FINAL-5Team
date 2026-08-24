from uuid import UUID

import pytest
from qdrant_client import QdrantClient

from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter, QdrantPoint
from backend.app.integrations.qdrant.collection_manager import QdrantCollectionManager

EXERCISE_A = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_B = UUID("00000000-0000-0000-0000-000000000002")
EXERCISE_C = UUID("00000000-0000-0000-0000-000000000003")
BUILD_HASH = "b" * 64


def _point(exercise_id: UUID, vector: tuple[float, ...]) -> QdrantPoint:
    return QdrantPoint(
        exercise_id=exercise_id,
        vector=vector,
        payload={
            "catalog_version_code": "catalog-v1",
            "vector_index_version": "index-v1",
            "embedding_model_version": "fake-v1",
            "production_eligible": True,
            "build_hash": BUILD_HASH,
        },
    )


@pytest.mark.qdrant_integration
def test_official_client_uuid_upsert_filter_search_and_alias_are_idempotent() -> None:
    raw = QdrantClient(":memory:")
    adapter = OfficialQdrantClientAdapter(raw, timeout_seconds=2)
    manager = QdrantCollectionManager(
        gateway=adapter,
        alias_name="exercise_catalog_active",
        batch_size=2,
    )
    collection = "exercise_catalog__test__catalog_v1__fake_v1__index_v1"
    points = (
        _point(EXERCISE_A, (1.0, 0.0, 0.0)),
        _point(EXERCISE_B, (0.9, 0.1, 0.0)),
        _point(EXERCISE_C, (0.0, 1.0, 0.0)),
    )
    try:
        manager.build(
            collection_name=collection,
            vector_dimension=3,
            distance_metric_code="COSINE",
            points=points,
            expected_build_hash=BUILD_HASH,
        )
        manager.build(
            collection_name=collection,
            vector_dimension=3,
            distance_metric_code="COSINE",
            points=points,
            expected_build_hash=BUILD_HASH,
        )
        assert adapter.exact_count(collection) == 3
        assert manager.activate(collection) is True
        assert manager.activate(collection) is False

        hits = adapter.query_exercises(
            collection_name="exercise_catalog_active",
            query_vector=(1.0, 0.0, 0.0),
            eligible_exercise_ids=(EXERCISE_A, EXERCISE_B),
            excluded_exercise_ids=(EXERCISE_B,),
            catalog_version="catalog-v1",
            vector_index_version="index-v1",
            embedding_model_version="fake-v1",
            requested_limit=3,
        )
        assert tuple(hit.exercise_id for hit in hits) == (EXERCISE_A,)

        version_mismatch = adapter.query_exercises(
            collection_name="exercise_catalog_active",
            query_vector=(1.0, 0.0, 0.0),
            eligible_exercise_ids=(EXERCISE_A, EXERCISE_B, EXERCISE_C),
            excluded_exercise_ids=(),
            catalog_version="catalog-v2",
            vector_index_version="index-v1",
            embedding_model_version="fake-v1",
            requested_limit=3,
        )
        assert version_mismatch == ()

        replacement = "exercise_catalog__test__catalog_v1__fake_v1__index_v2"
        manager.build(
            collection_name=replacement,
            vector_dimension=3,
            distance_metric_code="COSINE",
            points=points,
            expected_build_hash=BUILD_HASH,
        )
        assert manager.activate(replacement) is True
        assert adapter.aliases()["exercise_catalog_active"] == replacement
    finally:
        raw.close()
