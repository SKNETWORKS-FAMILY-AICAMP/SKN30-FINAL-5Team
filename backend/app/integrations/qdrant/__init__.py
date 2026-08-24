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
)
from backend.app.integrations.qdrant.index_builder import ExerciseVectorIndexBuilder

__all__ = [
    "DeterministicFakeEmbeddingAdapter",
    "EmbeddingContract",
    "EmbeddingPort",
    "ExerciseVectorIndexBuilder",
    "OfficialQdrantClientAdapter",
    "QdrantCollectionManager",
    "QdrantExerciseRetriever",
    "VectorIndexContract",
]
