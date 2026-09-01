"""Immutable Qdrant collection build, validation, and alias switching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from backend.app.integrations.qdrant.client import QdrantGateway, QdrantPoint

_COLLECTION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,254}$")
_SUPPORTED_ENVS = frozenset({"local", "test", "staging", "production"})


def _name_part(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not normalized:
        raise ValueError("collection name part is empty after normalization")
    return normalized


def immutable_collection_name(
    *,
    prefix: str,
    environment: str,
    catalog_version: str,
    embedding_model_version: str,
    vector_index_version: str,
) -> str:
    """Build a non-user-controlled allowlisted collection name."""

    if environment not in _SUPPORTED_ENVS:
        raise ValueError("environment is not allowed in a collection name")
    name = "__".join(
        _name_part(value)
        for value in (
            prefix,
            environment,
            catalog_version,
            embedding_model_version,
            vector_index_version,
        )
    )
    if not _COLLECTION_PATTERN.fullmatch(name):
        raise ValueError("generated collection name is not allowlisted")
    return name


@dataclass(frozen=True, slots=True)
class CollectionBuildResult:
    collection_name: str
    point_count: int
    alias_changed: bool


class QdrantCollectionManager:
    def __init__(
        self,
        *,
        gateway: QdrantGateway,
        alias_name: str,
        batch_size: int = 64,
    ) -> None:
        if not _COLLECTION_PATTERN.fullmatch(alias_name):
            raise ValueError("alias_name is not allowlisted")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._gateway = gateway
        self._alias_name = alias_name
        self._batch_size = batch_size

    def build(
        self,
        *,
        collection_name: str,
        vector_dimension: int,
        distance_metric_code: str,
        points: tuple[QdrantPoint, ...],
        expected_build_hash: str,
    ) -> CollectionBuildResult:
        if not _COLLECTION_PATTERN.fullmatch(collection_name):
            raise ValueError("collection_name is not allowlisted")
        if len({point.exercise_id for point in points}) != len(points):
            raise ValueError("build points must have unique UUIDs")
        if not self._gateway.collection_exists(collection_name):
            self._gateway.create_collection(
                collection_name=collection_name,
                vector_dimension=vector_dimension,
                distance_metric_code=distance_metric_code,
            )
        for offset in range(0, len(points), self._batch_size):
            self._gateway.upsert_points(
                collection_name=collection_name,
                points=points[offset : offset + self._batch_size],
            )
        self.validate(
            collection_name=collection_name,
            expected_ids=tuple(point.exercise_id for point in points),
            expected_build_hash=expected_build_hash,
        )
        return CollectionBuildResult(
            collection_name=collection_name,
            point_count=len(points),
            alias_changed=False,
        )

    def validate(
        self,
        *,
        collection_name: str,
        expected_ids: tuple[UUID, ...],
        expected_build_hash: str,
    ) -> None:
        self._gateway.ensure_filter_payload_indexes(collection_name)
        if self._gateway.exact_count(collection_name) != len(expected_ids):
            raise ValueError("Qdrant point count does not match the build input")
        stored = self._gateway.retrieve_points(
            collection_name=collection_name,
            exercise_ids=expected_ids,
        )
        if {point.exercise_id for point in stored} != set(expected_ids):
            raise ValueError("Qdrant point UUID set does not match the build input")
        if any(point.payload.get("build_hash") != expected_build_hash for point in stored):
            raise ValueError("Qdrant point build hash does not match the build input")

    def activate(self, collection_name: str) -> bool:
        if not _COLLECTION_PATTERN.fullmatch(collection_name):
            raise ValueError("collection_name is not allowlisted")
        aliases = self._gateway.aliases()
        current = aliases.get(self._alias_name)
        if current == collection_name:
            return False
        self._gateway.switch_alias(
            alias_name=self._alias_name,
            collection_name=collection_name,
            previous_collection=current,
        )
        return True


__all__ = [
    "CollectionBuildResult",
    "QdrantCollectionManager",
    "immutable_collection_name",
]
