"""Qdrant derived-index adapters for the V3 exercise retrieval boundary."""

from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter
from backend.app.integrations.qdrant.collection_manager import QdrantCollectionManager
from backend.app.integrations.qdrant.embedding import (
    DeterministicFakeEmbeddingAdapter,
    EmbeddingContract,
    EmbeddingPort,
)
from backend.app.integrations.qdrant.exercise_retriever import (
    QdrantExerciseRetriever,
    VectorIndexContract,
    deterministic_retrieval_fallback,
    exercise_retrieval_query_hash,
)
from backend.app.integrations.qdrant.index_builder import ExerciseVectorIndexBuilder
from backend.app.integrations.qdrant.snapshot_loader import (
    EligibleExerciseProjection,
    PostgreSQLExercisePoolSourcePort,
    QdrantExercisePoolSnapshotLoader,
    V3ExercisePoolSnapshotError,
)

__all__ = [
    "DeterministicFakeEmbeddingAdapter",
    "EmbeddingContract",
    "EmbeddingPort",
    "EligibleExerciseProjection",
    "ExerciseVectorIndexBuilder",
    "OfficialQdrantClientAdapter",
    "PostgreSQLExercisePoolSourcePort",
    "QdrantCollectionManager",
    "QdrantExerciseRetriever",
    "QdrantExercisePoolSnapshotLoader",
    "V3ExercisePoolSnapshotError",
    "VectorIndexContract",
    "deterministic_retrieval_fallback",
    "exercise_retrieval_query_hash",
]
