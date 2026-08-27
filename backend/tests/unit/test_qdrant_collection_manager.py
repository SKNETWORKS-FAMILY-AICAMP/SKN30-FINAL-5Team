from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest

from backend.app.integrations.qdrant.client import QdrantPoint, QdrantStoredPoint
from backend.app.integrations.qdrant.collection_manager import (
    QdrantCollectionManager,
    immutable_collection_name,
)

EXERCISE_A = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_B = UUID("00000000-0000-0000-0000-000000000002")
BUILD_HASH = "b" * 64


@dataclass
class MemoryGateway:
    collections: dict[str, dict[UUID, QdrantPoint]] = field(default_factory=dict)
    alias_map: dict[str, str] = field(default_factory=dict)
    upsert_calls: int = 0
    switches: int = 0
    payload_index_calls: int = 0

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, *, collection_name: str, **_: Any) -> None:
        self.collections[collection_name] = {}

    def ensure_filter_payload_indexes(self, collection_name: str) -> None:
        assert collection_name in self.collections
        self.payload_index_calls += 1

    def upsert_points(self, *, collection_name: str, points: tuple[QdrantPoint, ...]) -> None:
        self.upsert_calls += 1
        self.collections[collection_name].update({point.exercise_id: point for point in points})

    def exact_count(self, collection_name: str) -> int:
        return len(self.collections[collection_name])

    def retrieve_points(
        self, *, collection_name: str, exercise_ids: tuple[UUID, ...]
    ) -> tuple[QdrantStoredPoint, ...]:
        points = self.collections[collection_name]
        return tuple(
            QdrantStoredPoint(exercise_id, points[exercise_id].payload)
            for exercise_id in exercise_ids
            if exercise_id in points
        )

    def aliases(self) -> dict[str, str]:
        return dict(self.alias_map)

    def switch_alias(
        self, *, alias_name: str, collection_name: str, previous_collection: str | None
    ) -> None:
        del previous_collection
        self.switches += 1
        self.alias_map[alias_name] = collection_name


def _points() -> tuple[QdrantPoint, ...]:
    return (
        QdrantPoint(EXERCISE_A, (1.0, 0.0), {"build_hash": BUILD_HASH}),
        QdrantPoint(EXERCISE_B, (0.0, 1.0), {"build_hash": BUILD_HASH}),
    )


def test_batch_upsert_rerun_is_idempotent_and_alias_switch_is_atomic() -> None:
    gateway = MemoryGateway()
    manager = QdrantCollectionManager(
        gateway=gateway,  # type: ignore[arg-type]
        alias_name="exercise_catalog_active",
        batch_size=1,
    )
    collection = "exercise_catalog__test__catalog_v1__fake_v1__index_v1"

    manager.build(
        collection_name=collection,
        vector_dimension=2,
        distance_metric_code="COSINE",
        points=_points(),
        expected_build_hash=BUILD_HASH,
    )
    manager.build(
        collection_name=collection,
        vector_dimension=2,
        distance_metric_code="COSINE",
        points=_points(),
        expected_build_hash=BUILD_HASH,
    )

    assert gateway.exact_count(collection) == 2
    assert manager.activate(collection) is True
    assert manager.activate(collection) is False
    assert gateway.switches == 1
    assert gateway.payload_index_calls == 2


def test_validation_rejects_missing_point_and_wrong_build_hash() -> None:
    gateway = MemoryGateway()
    manager = QdrantCollectionManager(
        gateway=gateway,  # type: ignore[arg-type]
        alias_name="exercise_catalog_active",
    )
    gateway.collections["exercise_catalog__test"] = {
        EXERCISE_A: QdrantPoint(EXERCISE_A, (1.0, 0.0), {"build_hash": "c" * 64})
    }

    with pytest.raises(ValueError, match="point count"):
        manager.validate(
            collection_name="exercise_catalog__test",
            expected_ids=(EXERCISE_A, EXERCISE_B),
            expected_build_hash=BUILD_HASH,
        )
    with pytest.raises(ValueError, match="build hash"):
        manager.validate(
            collection_name="exercise_catalog__test",
            expected_ids=(EXERCISE_A,),
            expected_build_hash=BUILD_HASH,
        )


def test_collection_name_is_environment_and_version_allowlisted() -> None:
    name = immutable_collection_name(
        prefix="exercise_catalog",
        environment="test",
        catalog_version="merged-mvp-v0.4.0",
        embedding_model_version="fake/model-v1",
        vector_index_version="index-v1",
    )

    assert name == "exercise_catalog__test__merged_mvp_v0_4_0__fake_model_v1__index_v1"
    with pytest.raises(ValueError, match="environment"):
        immutable_collection_name(
            prefix="exercise_catalog",
            environment="tenant-input",
            catalog_version="catalog-v1",
            embedding_model_version="fake-v1",
            vector_index_version="index-v1",
        )
