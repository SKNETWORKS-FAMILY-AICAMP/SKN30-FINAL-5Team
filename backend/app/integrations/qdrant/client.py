"""Sanitizing wrapper around the official Qdrant Python client.

Provider exceptions are translated at this boundary so URLs, credentials, response bodies,
and provider error text never cross into the domain or application layers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from backend.app.core.config import Settings

VECTOR_NAME = "semantic"


class QdrantProviderError(RuntimeError):
    """Sanitized base error for provider failures."""


class QdrantProviderUnavailableError(QdrantProviderError):
    pass


class QdrantProviderTimeoutError(QdrantProviderError):
    pass


class QdrantCollectionNotReadyError(QdrantProviderError):
    pass


@dataclass(frozen=True, slots=True)
class QdrantSearchHit:
    exercise_id: UUID
    score: float


@dataclass(frozen=True, slots=True)
class QdrantStoredPoint:
    exercise_id: UUID
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QdrantPoint:
    exercise_id: UUID
    vector: tuple[float, ...]
    payload: dict[str, Any]


class QdrantGateway(Protocol):
    def query_exercises(
        self,
        *,
        collection_name: str,
        query_vector: tuple[float, ...],
        eligible_exercise_ids: tuple[UUID, ...],
        excluded_exercise_ids: tuple[UUID, ...],
        catalog_version: str,
        vector_index_version: str,
        embedding_model_version: str,
        requested_limit: int,
    ) -> tuple[QdrantSearchHit, ...]: ...

    def collection_exists(self, collection_name: str) -> bool: ...

    def create_collection(
        self,
        *,
        collection_name: str,
        vector_dimension: int,
        distance_metric_code: str,
    ) -> None: ...

    def upsert_points(self, *, collection_name: str, points: tuple[QdrantPoint, ...]) -> None: ...

    def exact_count(self, collection_name: str) -> int: ...

    def retrieve_points(
        self, *, collection_name: str, exercise_ids: tuple[UUID, ...]
    ) -> tuple[QdrantStoredPoint, ...]: ...

    def aliases(self) -> dict[str, str]: ...

    def switch_alias(
        self, *, alias_name: str, collection_name: str, previous_collection: str | None
    ) -> None: ...


_DISTANCE_BY_CODE = {
    "COSINE": models.Distance.COSINE,
    "DOT": models.Distance.DOT,
    "EUCLID": models.Distance.EUCLID,
    "MANHATTAN": models.Distance.MANHATTAN,
}


class OfficialQdrantClientAdapter:
    """Official-client adapter with a small, testable surface."""

    def __init__(self, client: QdrantClient, *, timeout_seconds: float) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> OfficialQdrantClientAdapter:
        if not settings.qdrant_enabled:
            raise ValueError("Qdrant is disabled")
        api_key = settings.qdrant_api_key
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=api_key.get_secret_value() if api_key is not None else None,
            timeout=math.ceil(settings.qdrant_timeout_seconds),
            check_compatibility=True,
        )
        return cls(client, timeout_seconds=settings.qdrant_timeout_seconds)

    @property
    def _timeout(self) -> int:
        return math.ceil(self._timeout_seconds)

    @staticmethod
    def _translate(exc: Exception) -> QdrantProviderError:
        if isinstance(exc, UnexpectedResponse) and exc.status_code == 404:
            return QdrantCollectionNotReadyError("VECTOR_INDEX_NOT_READY")
        source = exc.source if isinstance(exc, ResponseHandlingException) else exc
        error_type = type(source).__name__.upper()
        if "TIMEOUT" in error_type:
            return QdrantProviderTimeoutError("VECTOR_SEARCH_TIMEOUT")
        return QdrantProviderUnavailableError("VECTOR_INDEX_UNAVAILABLE")

    def query_exercises(
        self,
        *,
        collection_name: str,
        query_vector: tuple[float, ...],
        eligible_exercise_ids: tuple[UUID, ...],
        excluded_exercise_ids: tuple[UUID, ...],
        catalog_version: str,
        vector_index_version: str,
        embedding_model_version: str,
        requested_limit: int,
    ) -> tuple[QdrantSearchHit, ...]:
        must: list[models.Condition] = [
            models.HasIdCondition(has_id=list(eligible_exercise_ids)),
            models.FieldCondition(
                key="catalog_version_code", match=models.MatchValue(value=catalog_version)
            ),
            models.FieldCondition(
                key="vector_index_version",
                match=models.MatchValue(value=vector_index_version),
            ),
            models.FieldCondition(
                key="embedding_model_version",
                match=models.MatchValue(value=embedding_model_version),
            ),
            models.FieldCondition(key="production_eligible", match=models.MatchValue(value=True)),
        ]
        must_not: list[models.Condition] = []
        if excluded_exercise_ids:
            must_not.append(models.HasIdCondition(has_id=list(excluded_exercise_ids)))
        try:
            response = self._client.query_points(
                collection_name=collection_name,
                query=list(query_vector),
                using=VECTOR_NAME,
                query_filter=models.Filter(must=must, must_not=must_not),
                limit=requested_limit,
                with_payload=False,
                with_vectors=False,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise self._translate(exc) from None
        hits: list[QdrantSearchHit] = []
        try:
            for point in response.points:
                hits.append(
                    QdrantSearchHit(exercise_id=UUID(str(point.id)), score=float(point.score))
                )
        except (TypeError, ValueError, AttributeError):
            raise QdrantProviderError("VECTOR_RESULT_NOT_CANONICAL") from None
        return tuple(hits)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            return self._client.collection_exists(collection_name)
        except Exception as exc:
            raise self._translate(exc) from None

    def create_collection(
        self,
        *,
        collection_name: str,
        vector_dimension: int,
        distance_metric_code: str,
    ) -> None:
        try:
            distance = _DISTANCE_BY_CODE[distance_metric_code]
        except KeyError:
            raise ValueError("distance metric is not supported") from None
        try:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    VECTOR_NAME: models.VectorParams(size=vector_dimension, distance=distance)
                },
                timeout=self._timeout,
            )
        except Exception as exc:
            raise self._translate(exc) from None

    def upsert_points(self, *, collection_name: str, points: tuple[QdrantPoint, ...]) -> None:
        provider_points = [
            models.PointStruct(
                id=point.exercise_id,
                vector={VECTOR_NAME: list(point.vector)},
                payload=point.payload,
            )
            for point in points
        ]
        try:
            self._client.upsert(
                collection_name=collection_name,
                points=provider_points,
                wait=True,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise self._translate(exc) from None

    def exact_count(self, collection_name: str) -> int:
        try:
            return self._client.count(
                collection_name=collection_name, exact=True, timeout=self._timeout
            ).count
        except Exception as exc:
            raise self._translate(exc) from None

    def retrieve_points(
        self, *, collection_name: str, exercise_ids: tuple[UUID, ...]
    ) -> tuple[QdrantStoredPoint, ...]:
        try:
            records = self._client.retrieve(
                collection_name=collection_name,
                ids=list(exercise_ids),
                with_payload=True,
                with_vectors=False,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise self._translate(exc) from None
        points: list[QdrantStoredPoint] = []
        try:
            for record in records:
                points.append(
                    QdrantStoredPoint(
                        exercise_id=UUID(str(record.id)), payload=dict(record.payload or {})
                    )
                )
        except (TypeError, ValueError, AttributeError):
            raise QdrantProviderError("VECTOR_RESULT_NOT_CANONICAL") from None
        return tuple(points)

    def aliases(self) -> dict[str, str]:
        try:
            response = self._client.get_aliases()
        except Exception as exc:
            raise self._translate(exc) from None
        return {alias.alias_name: alias.collection_name for alias in response.aliases}

    def switch_alias(
        self, *, alias_name: str, collection_name: str, previous_collection: str | None
    ) -> None:
        operations: list[models.AliasOperations] = []
        if previous_collection is not None:
            operations.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias_name))
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=collection_name,
                    alias_name=alias_name,
                )
            )
        )
        try:
            self._client.update_collection_aliases(
                change_aliases_operations=operations,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise self._translate(exc) from None


__all__ = [
    "OfficialQdrantClientAdapter",
    "QdrantCollectionNotReadyError",
    "QdrantGateway",
    "QdrantPoint",
    "QdrantProviderError",
    "QdrantProviderTimeoutError",
    "QdrantProviderUnavailableError",
    "QdrantSearchHit",
    "QdrantStoredPoint",
    "VECTOR_NAME",
]
