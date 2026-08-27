from dataclasses import replace
from uuid import UUID

import pytest

from backend.app.db.repositories.vector_index import IndexableExerciseRecord
from backend.app.integrations.qdrant.client import QdrantPoint
from backend.app.integrations.qdrant.index_builder import canonical_embedding_document
from backend.scripts.remap_staging_qdrant_index import remap_points


def _record(exercise_id: str, catalog_id: str) -> IndexableExerciseRecord:
    return IndexableExerciseRecord(
        exercise_id=UUID(exercise_id),
        catalog_version_id=UUID(catalog_id),
        catalog_version_code="exercise-catalog-v2.0.1-final",
        catalog_manifest_hash="a" * 64,
        name_ko="스쿼트",
        name_en="Squat",
        instruction_summary_ko="검수된 설명",
        instruction_content_version="v1",
        training_type_code="STRENGTH",
        body_focus_code="LOWER",
        primary_movement_pattern_code="SQUAT",
        difficulty_code="BEGINNER",
        recovery_eligible=False,
        review_status_code="DOMAIN_APPROVED",
        review_method_code="DOMAIN_REVIEWER",
        status_interpretation_code="PRODUCTION_APPROVED",
        production_eligible=True,
        goal_codes=("STRENGTH",),
        equipment_codes=(),
        location_codes=("HOME",),
        phase_codes=("MAIN",),
        prescription_experience_level_codes=("BEGINNER", "INTERMEDIATE"),
        stable_code="SQUAT",
    )


def _source_hash(record: IndexableExerciseRecord) -> str:
    import hashlib

    return hashlib.sha256(canonical_embedding_document(record).encode()).hexdigest()


def test_remap_points_preserves_vector_and_replaces_catalog_identity() -> None:
    old = _record(
        "00000000-0000-0000-0000-000000000001",
        "10000000-0000-0000-0000-000000000001",
    )
    source = replace(
        old,
        exercise_id=UUID("00000000-0000-0000-0000-000000000002"),
        catalog_version_id=UUID("20000000-0000-0000-0000-000000000001"),
    )
    point = QdrantPoint(
        exercise_id=old.exercise_id,
        vector=(0.1, 0.2),
        payload={"source_document_hash": _source_hash(old), "build_hash": "old"},
    )

    result = remap_points(
        source_records=(source,),
        old_records=(old,),
        old_points=(point,),
        vector_index_version="new-version",
        build_hash="new-hash",
    )

    assert result[0].exercise_id == source.exercise_id
    assert result[0].vector == point.vector
    assert result[0].payload["catalog_version_id"] == str(source.catalog_version_id)
    assert result[0].payload["vector_index_version"] == "new-version"
    assert result[0].payload["build_hash"] == "new-hash"


def test_remap_points_rejects_changed_embedding_document() -> None:
    old = _record(
        "00000000-0000-0000-0000-000000000001",
        "10000000-0000-0000-0000-000000000001",
    )
    source = replace(
        old,
        exercise_id=UUID("00000000-0000-0000-0000-000000000002"),
        name_ko="변경된 이름",
    )
    point = QdrantPoint(
        exercise_id=old.exercise_id,
        vector=(0.1, 0.2),
        payload={"source_document_hash": _source_hash(old)},
    )

    with pytest.raises(ValueError, match="embedding document changed"):
        remap_points(
            source_records=(source,),
            old_records=(old,),
            old_points=(point,),
            vector_index_version="new-version",
            build_hash="new-hash",
        )
