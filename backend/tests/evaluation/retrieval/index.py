"""Build the evaluation vector index in an in-process Qdrant.

`ExerciseVectorIndexBuilder` needs PostgreSQL for its registry rows, which an
offline evaluation has no access to.  This builds the same index without it, by
reusing the production document format (`canonical_embedding_document`), the
production build hash, the production point payload and the production
collection manager.  Only the registry bookkeeping is left out.

That matters for PHASE 3: what is scored has to be the retriever the service
ships, ranking over documents shaped exactly as production shapes them.  A
bespoke index would score a different system.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from qdrant_client import QdrantClient

from backend.app.db.repositories.vector_index import IndexableExerciseRecord
from backend.app.integrations.qdrant.client import OfficialQdrantClientAdapter, QdrantPoint
from backend.app.integrations.qdrant.collection_manager import (
    QdrantCollectionManager,
    immutable_collection_name,
)
from backend.app.integrations.qdrant.embedding import (
    DeterministicFakeEmbeddingAdapter,
    EmbeddingContract,
    EmbeddingPort,
)
from backend.app.integrations.qdrant.exercise_retriever import (
    QdrantExerciseRetriever,
    VectorIndexContract,
)
from backend.app.integrations.qdrant.index_builder import (
    canonical_embedding_document,
    vector_index_build_hash,
)
from backend.tests.evaluation import catalog_text

COLLECTION_PREFIX: Final = "exercise_catalog"
COLLECTION_ENVIRONMENT: Final = "test"
ALIAS_NAME: Final = "exercise_catalog_active"
VECTOR_INDEX_VERSION: Final = "eval-index-v1"
EMBEDDING_INPUT_SCHEMA_VERSION: Final = "exercise-embedding-input-v2"

# The offline default. Hash-derived vectors carry no semantics, so a score
# produced with this describes the wiring, never the retriever's quality.
FAKE_EMBEDDING_CONTRACT: Final = EmbeddingContract(
    provider_code="DETERMINISTIC_FAKE",
    model_version="eval-fake-embedding-v1",
    input_schema_version=EMBEDDING_INPUT_SCHEMA_VERSION,
    vector_dimension=64,
    distance_metric_code="COSINE",
)


@dataclass(frozen=True, slots=True)
class EvaluationIndex:
    """A live in-process index plus the retriever bound to it."""

    retriever: QdrantExerciseRetriever
    contract: VectorIndexContract
    embedding_contract: EmbeddingContract
    point_count: int
    build_hash: str

    @property
    def is_semantic(self) -> bool:
        """Whether the vectors carry real meaning, or are hash-derived stand-ins."""

        return self.embedding_contract.provider_code != "DETERMINISTIC_FAKE"


def build_evaluation_index(
    *,
    embedding: EmbeddingPort | None = None,
    records: tuple[IndexableExerciseRecord, ...] | None = None,
    client: QdrantClient | None = None,
) -> EvaluationIndex:
    """Index the evaluation catalog and return a retriever over it."""

    resolved_embedding = embedding or DeterministicFakeEmbeddingAdapter(FAKE_EMBEDDING_CONTRACT)
    resolved_records = records or catalog_text.all_indexable_records()
    if not resolved_records:
        raise ValueError("cannot build an index without records")

    contract = resolved_embedding.contract
    documents = tuple(canonical_embedding_document(record) for record in resolved_records)
    source_hashes = tuple(hashlib.sha256(document.encode()).hexdigest() for document in documents)
    build_hash = vector_index_build_hash(
        records=resolved_records,
        source_document_hashes=source_hashes,
        vector_index_version=VECTOR_INDEX_VERSION,
        embedding_contract=contract,
    )
    collection_name = immutable_collection_name(
        prefix=COLLECTION_PREFIX,
        environment=COLLECTION_ENVIRONMENT,
        catalog_version=resolved_records[0].catalog_version_code,
        embedding_model_version=contract.model_version,
        vector_index_version=VECTOR_INDEX_VERSION,
    )

    vectors = resolved_embedding.embed_documents(documents)
    points = tuple(
        QdrantPoint(
            exercise_id=record.exercise_id,
            vector=vector,
            payload={
                "payload_schema_version": 2,
                "catalog_version_id": str(record.catalog_version_id),
                "catalog_version_code": record.catalog_version_code,
                "catalog_manifest_hash": record.catalog_manifest_hash,
                "vector_index_version": VECTOR_INDEX_VERSION,
                "embedding_model_version": contract.model_version,
                "embedding_input_schema_version": contract.input_schema_version,
                "review_status_code": record.review_status_code,
                "review_method_code": record.review_method_code,
                "status_interpretation_code": record.status_interpretation_code,
                "production_eligible": record.production_eligible,
                "goal_codes": list(record.goal_codes),
                "equipment_codes": list(record.equipment_codes),
                "location_codes": list(record.location_codes),
                "phase_codes": list(record.phase_codes),
                "training_type_code": record.training_type_code,
                "body_focus_code": record.body_focus_code,
                "difficulty_code": record.difficulty_code,
                "primary_movement_pattern_code": record.primary_movement_pattern_code,
                "recovery_eligible": record.recovery_eligible,
                "instruction_content_version": record.instruction_content_version,
                "source_document_hash": source_hash,
                "build_hash": build_hash,
            },
        )
        for record, vector, source_hash in zip(
            resolved_records, vectors, source_hashes, strict=True
        )
    )

    raw = client or QdrantClient(":memory:")
    adapter = OfficialQdrantClientAdapter(raw, timeout_seconds=5)
    manager = QdrantCollectionManager(gateway=adapter, alias_name=ALIAS_NAME, batch_size=32)
    manager.build(
        collection_name=collection_name,
        vector_dimension=contract.vector_dimension,
        distance_metric_code=contract.distance_metric_code,
        points=points,
        expected_build_hash=build_hash,
    )
    manager.activate(collection_name)

    index_contract = VectorIndexContract(
        catalog_version=resolved_records[0].catalog_version_code,
        collection_name=collection_name,
        vector_index_version=VECTOR_INDEX_VERSION,
        embedding_model_version=contract.model_version,
        embedding_input_schema_version=contract.input_schema_version,
        vector_dimension=contract.vector_dimension,
        distance_metric_code=contract.distance_metric_code,
        status_code="ACTIVE",
    )
    return EvaluationIndex(
        retriever=QdrantExerciseRetriever(
            gateway=adapter,
            embedding=resolved_embedding,
            index=index_contract,
        ),
        contract=index_contract,
        embedding_contract=contract,
        point_count=len(points),
        build_hash=build_hash,
    )


__all__ = [
    "ALIAS_NAME",
    "EMBEDDING_INPUT_SCHEMA_VERSION",
    "FAKE_EMBEDDING_CONTRACT",
    "VECTOR_INDEX_VERSION",
    "EvaluationIndex",
    "build_evaluation_index",
]
