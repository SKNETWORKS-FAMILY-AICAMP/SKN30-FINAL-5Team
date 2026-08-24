"""Provider-neutral embedding contracts used by the Qdrant derived index."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

_DISTANCE_METRICS = frozenset({"COSINE", "DOT", "EUCLID", "MANHATTAN"})


@dataclass(frozen=True, slots=True)
class EmbeddingContract:
    """Immutable model contract supplied by deployment-approved configuration."""

    provider_code: str
    model_version: str
    input_schema_version: str
    vector_dimension: int
    distance_metric_code: str

    def __post_init__(self) -> None:
        if self.vector_dimension <= 0:
            raise ValueError("vector_dimension must be positive")
        if self.distance_metric_code not in _DISTANCE_METRICS:
            raise ValueError("distance_metric_code is not supported")
        for value in (self.provider_code, self.model_version, self.input_schema_version):
            if not value or any(character.isspace() for character in value):
                raise ValueError("embedding contract references must be non-empty machine codes")


class EmbeddingPort(Protocol):
    """Framework-neutral boundary; concrete production model selection is out of scope."""

    @property
    def contract(self) -> EmbeddingContract: ...

    def embed_documents(self, documents: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, normalized_query_codes: tuple[str, ...]) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class DeterministicFakeEmbeddingAdapter:
    """Credential-free deterministic vectors for unit and integration tests only."""

    contract: EmbeddingContract

    def _vector(self, value: str) -> tuple[float, ...]:
        vector: list[float] = []
        counter = 0
        while len(vector) < self.contract.vector_dimension:
            digest = hashlib.sha256(f"{counter}:{value}".encode()).digest()
            vector.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1
        result = tuple(vector[: self.contract.vector_dimension])
        if self.contract.distance_metric_code == "COSINE":
            norm = math.sqrt(sum(component * component for component in result))
            if norm == 0:
                raise ValueError("deterministic vector unexpectedly has zero norm")
            return tuple(component / norm for component in result)
        return result

    def embed_documents(self, documents: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._vector(document) for document in documents)

    def embed_query(self, normalized_query_codes: tuple[str, ...]) -> tuple[float, ...]:
        return self._vector("\n".join(normalized_query_codes))


__all__ = ["DeterministicFakeEmbeddingAdapter", "EmbeddingContract", "EmbeddingPort"]
