"""Request-safe Qdrant retrieval composition for the V3 demo application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models.catalog import CatalogVersion
from backend.app.db.repositories.vector_index import VectorIndexRepository
from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    ExerciseRetrievalResult,
    RetrievalStatusCode,
)
from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter
from backend.app.integrations.qdrant.embedding import EmbeddingContract
from backend.app.integrations.qdrant.exercise_retriever import (
    QdrantExerciseRetriever,
    VectorIndexContract,
    deterministic_retrieval_fallback,
)


@dataclass(frozen=True, slots=True)
class _OpenAIEmbeddingAdapter:
    contract: EmbeddingContract
    provider: OpenAIEmbeddings

    def embed_documents(self, documents: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(tuple(value) for value in self.provider.embed_documents(list(documents)))

    def embed_query(self, normalized_query_codes: tuple[str, ...]) -> tuple[float, ...]:
        return tuple(self.provider.embed_query("\n".join(normalized_query_codes)))


class DatabaseBoundQdrantExerciseRetriever:
    """Resolve the ACTIVE index per catalog and fail deterministically when unavailable."""

    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Session],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._vectors = VectorIndexRepository()

    def retrieve(self, request: ExerciseRetrievalRequest) -> ExerciseRetrievalResult:
        settings = self._settings
        if (
            not settings.qdrant_enabled
            or settings.embedding_provider_code != "OPENAI"
            or settings.embedding_model_version == "unconfigured"
            or settings.openai_api_key is None
        ):
            return deterministic_retrieval_fallback(
                request, RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE
            )
        with self._session_factory() as session:
            catalog = session.scalar(
                select(CatalogVersion).where(CatalogVersion.version_code == request.catalog_version)
            )
            if catalog is None:
                return deterministic_retrieval_fallback(
                    request, RetrievalStatusCode.VECTOR_INDEX_NOT_READY
                )
            index = self._vectors.get_active_for_catalog(session, catalog.id)
            if index is None:
                return deterministic_retrieval_fallback(
                    request, RetrievalStatusCode.VECTOR_INDEX_NOT_READY
                )
            contract = EmbeddingContract(
                provider_code="OPENAI",
                model_version=index.embedding_model_version,
                input_schema_version=index.embedding_input_schema_version,
                vector_dimension=index.vector_dimension,
                distance_metric_code=index.distance_metric_code,
            )
            try:
                provider = OpenAIEmbeddings(
                    model=settings.embedding_model_version,
                    api_key=settings.openai_api_key,
                    base_url=settings.llm_api_base_url,
                    dimensions=index.vector_dimension,
                )
                gateway = OfficialQdrantClientAdapter.from_settings(settings)
            except Exception:
                return deterministic_retrieval_fallback(
                    request, RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE
                )
            retriever = QdrantExerciseRetriever(
                gateway=gateway,
                embedding=_OpenAIEmbeddingAdapter(contract, provider),
                index=VectorIndexContract(
                    catalog_version=request.catalog_version,
                    collection_name=index.collection_name,
                    vector_index_version=index.vector_index_version,
                    embedding_model_version=index.embedding_model_version,
                    embedding_input_schema_version=index.embedding_input_schema_version,
                    vector_dimension=index.vector_dimension,
                    distance_metric_code=index.distance_metric_code,
                    status_code=index.status_code,
                ),
                max_provider_attempts=2,
            )
            return retriever.retrieve(request)


__all__ = ["DatabaseBoundQdrantExerciseRetriever"]
