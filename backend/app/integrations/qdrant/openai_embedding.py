"""Bounded OpenAI embedding adapter for the rebuildable exercise index."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast

from openai import OpenAI

from backend.app.core.config import Settings
from backend.app.integrations.qdrant.embedding import EmbeddingContract


class EmbeddingProviderError(RuntimeError):
    """Sanitized provider failure that never includes response or credential text."""


class _EmbeddingDatum(Protocol):
    index: int
    embedding: Sequence[float]


class _EmbeddingResponse(Protocol):
    data: Sequence[_EmbeddingDatum]


class _EmbeddingsResource(Protocol):
    def create(self, **kwargs: object) -> _EmbeddingResponse: ...


class _OpenAIClient(Protocol):
    embeddings: _EmbeddingsResource


@dataclass(frozen=True, slots=True)
class OpenAIEmbeddingAdapter:
    """Embed only reviewed exercise documents and normalized machine-code queries."""

    contract: EmbeddingContract
    client: _OpenAIClient = field(repr=False)

    def _embed(self, inputs: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not inputs:
            return ()
        try:
            response = self.client.embeddings.create(
                model=self.contract.model_version,
                input=list(inputs),
                dimensions=self.contract.vector_dimension,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(inputs))):
                raise ValueError
            return tuple(tuple(float(value) for value in item.embedding) for item in ordered)
        except Exception:
            raise EmbeddingProviderError("EMBEDDING_PROVIDER_FAILURE") from None

    def embed_documents(self, documents: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return self._embed(documents)

    def embed_query(self, normalized_query_codes: tuple[str, ...]) -> tuple[float, ...]:
        if not normalized_query_codes:
            raise ValueError("normalized query codes must not be empty")
        query = json.dumps(
            {
                "normalized_query_codes": list(normalized_query_codes),
                "schema_version": self.contract.input_schema_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._embed((query,))[0]


def build_openai_embedding_adapter(settings: Settings) -> OpenAIEmbeddingAdapter:
    """Construct the provider only after the caller has passed staging gates."""

    api_key = settings.openai_api_key
    if settings.embedding_provider_code != "OPENAI" or api_key is None:
        raise ValueError("approved OpenAI embedding configuration is required")
    contract = EmbeddingContract(
        provider_code=settings.embedding_provider_code,
        model_version=settings.embedding_model_version,
        input_schema_version=settings.embedding_input_schema_version,
        vector_dimension=settings.embedding_vector_dimension,
        distance_metric_code=settings.embedding_distance_metric_code,
    )
    client = OpenAI(
        api_key=api_key.get_secret_value(),
        base_url=settings.llm_api_base_url,
        timeout=settings.embedding_timeout_seconds,
        max_retries=0,
    )
    return OpenAIEmbeddingAdapter(contract=contract, client=cast(_OpenAIClient, client))


__all__ = [
    "EmbeddingProviderError",
    "OpenAIEmbeddingAdapter",
    "build_openai_embedding_adapter",
]
