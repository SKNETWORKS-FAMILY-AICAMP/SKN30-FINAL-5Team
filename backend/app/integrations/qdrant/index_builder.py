"""Idempotent exercise embedding index build service."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.db.repositories.vector_index import (
    IndexableExerciseRecord,
    VectorIndexBuildWrite,
    VectorIndexRepository,
)
from backend.app.integrations.qdrant.client import QdrantPoint
from backend.app.integrations.qdrant.collection_manager import (
    QdrantCollectionManager,
    immutable_collection_name,
)
from backend.app.integrations.qdrant.embedding import EmbeddingPort


def canonical_embedding_document(record: IndexableExerciseRecord) -> str:
    """Create the reviewed, non-user exercise text allowed by input schema v1."""

    payload = {
        "beginner_suitable": record.beginner_suitable,
        "body_focus_code": record.body_focus_code,
        "difficulty_code": record.difficulty_code,
        "equipment_codes": list(record.equipment_codes),
        "goal_codes": list(record.goal_codes),
        "instruction_summary_ko": record.instruction_summary_ko,
        "location_codes": list(record.location_codes),
        "name_en": record.name_en,
        "name_ko": record.name_ko,
        "phase_codes": list(record.phase_codes),
        "primary_movement_pattern_code": record.primary_movement_pattern_code,
        "recovery_eligible": record.recovery_eligible,
        "training_type_code": record.training_type_code,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _build_hash(
    *,
    records: tuple[IndexableExerciseRecord, ...],
    source_document_hashes: tuple[str, ...],
    vector_index_version: str,
    embedding: EmbeddingPort,
) -> str:
    payload = {
        "catalog_version": records[0].catalog_version_code,
        "source_manifest_hash": records[0].catalog_manifest_hash,
        "vector_index_version": vector_index_version,
        "embedding_contract": {
            "provider_code": embedding.contract.provider_code,
            "model_version": embedding.contract.model_version,
            "input_schema_version": embedding.contract.input_schema_version,
            "vector_dimension": embedding.contract.vector_dimension,
            "distance_metric_code": embedding.contract.distance_metric_code,
        },
        "points": [
            {"exercise_id": str(record.exercise_id), "source_document_hash": source_hash}
            for record, source_hash in zip(records, source_document_hashes, strict=True)
        ],
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True, slots=True)
class VectorIndexBuildResult:
    vector_index_version: str
    collection_name: str
    build_hash: str
    point_count: int
    alias_changed: bool


class ExerciseVectorIndexBuilder:
    def __init__(
        self,
        *,
        repository: VectorIndexRepository,
        collection_manager: QdrantCollectionManager,
        embedding: EmbeddingPort,
        collection_prefix: str,
        environment: str,
    ) -> None:
        self._repository = repository
        self._collection_manager = collection_manager
        self._embedding = embedding
        self._collection_prefix = collection_prefix
        self._environment = environment

    def build_and_activate(
        self,
        session: Session,
        *,
        catalog_version: str,
        vector_index_version: str,
        now: datetime,
    ) -> VectorIndexBuildResult:
        records = self._repository.list_indexable_exercises(session, catalog_version)
        if not records:
            raise ValueError("no production-approved exercises are available for indexing")
        if any(
            not record.production_eligible
            or record.review_status_code != "DOMAIN_APPROVED"
            or record.review_method_code != "DOMAIN_REVIEWER"
            or record.status_interpretation_code != "PRODUCTION_APPROVED"
            for record in records
        ):
            raise ValueError(
                "index input contains an exercise outside the production approval gate"
            )
        documents = tuple(canonical_embedding_document(record) for record in records)
        source_document_hashes = tuple(_sha256(document) for document in documents)
        build_hash = _build_hash(
            records=records,
            source_document_hashes=source_document_hashes,
            vector_index_version=vector_index_version,
            embedding=self._embedding,
        )
        collection_name = immutable_collection_name(
            prefix=self._collection_prefix,
            environment=self._environment,
            catalog_version=catalog_version,
            embedding_model_version=self._embedding.contract.model_version,
            vector_index_version=vector_index_version,
        )
        registry = self._repository.create_build(
            session,
            VectorIndexBuildWrite(
                catalog_version_id=records[0].catalog_version_id,
                collection_name=collection_name,
                vector_index_version=vector_index_version,
                source_manifest_hash=records[0].catalog_manifest_hash,
                embedding_model_version=self._embedding.contract.model_version,
                embedding_input_schema_version=self._embedding.contract.input_schema_version,
                distance_metric_code=self._embedding.contract.distance_metric_code,
                vector_dimension=self._embedding.contract.vector_dimension,
                build_hash=build_hash,
            ),
        )
        if registry.status_code == "ACTIVE":
            self._collection_manager.validate(
                collection_name=collection_name,
                expected_ids=tuple(record.exercise_id for record in records),
                expected_build_hash=build_hash,
            )
            alias_changed = self._collection_manager.activate(collection_name)
            return VectorIndexBuildResult(
                vector_index_version=vector_index_version,
                collection_name=collection_name,
                build_hash=build_hash,
                point_count=len(records),
                alias_changed=alias_changed,
            )
        try:
            vectors = self._embedding.embed_documents(documents)
            if len(vectors) != len(records) or any(
                len(vector) != self._embedding.contract.vector_dimension
                or any(not math.isfinite(value) for value in vector)
                for vector in vectors
            ):
                raise ValueError("embedding provider returned an invalid vector batch")
            points = tuple(
                QdrantPoint(
                    exercise_id=record.exercise_id,
                    vector=vector,
                    payload={
                        "payload_schema_version": 1,
                        "catalog_version_id": str(record.catalog_version_id),
                        "catalog_version_code": record.catalog_version_code,
                        "catalog_manifest_hash": record.catalog_manifest_hash,
                        "vector_index_version": vector_index_version,
                        "embedding_model_version": self._embedding.contract.model_version,
                        "embedding_input_schema_version": (
                            self._embedding.contract.input_schema_version
                        ),
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
                        "primary_movement_pattern_code": (record.primary_movement_pattern_code),
                        "beginner_suitable": record.beginner_suitable,
                        "recovery_eligible": record.recovery_eligible,
                        "instruction_content_version": record.instruction_content_version,
                        "source_document_hash": source_hash,
                        "build_hash": build_hash,
                    },
                )
                for record, vector, source_hash in zip(
                    records, vectors, source_document_hashes, strict=True
                )
            )
            self._collection_manager.build(
                collection_name=collection_name,
                vector_dimension=self._embedding.contract.vector_dimension,
                distance_metric_code=self._embedding.contract.distance_metric_code,
                points=points,
                expected_build_hash=build_hash,
            )
            self._repository.mark_ready(session, registry, built_at=now)
            alias_changed = self._collection_manager.activate(collection_name)
            self._repository.activate(session, registry, activated_at=now)
        except Exception:
            self._repository.mark_failed(session, registry)
            raise
        return VectorIndexBuildResult(
            vector_index_version=vector_index_version,
            collection_name=collection_name,
            build_hash=build_hash,
            point_count=len(points),
            alias_changed=alias_changed,
        )


__all__ = [
    "ExerciseVectorIndexBuilder",
    "VectorIndexBuildResult",
    "canonical_embedding_document",
]
