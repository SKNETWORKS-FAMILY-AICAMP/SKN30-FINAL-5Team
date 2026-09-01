from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from backend.app.db.repositories.vector_index import IndexableExerciseRecord
from backend.app.integrations.qdrant.embedding import (
    DeterministicFakeEmbeddingAdapter,
    EmbeddingContract,
)
from backend.app.integrations.qdrant.index_builder import (
    ExerciseVectorIndexBuilder,
    canonical_embedding_document,
)


def _record() -> IndexableExerciseRecord:
    return IndexableExerciseRecord(
        exercise_id=UUID("00000000-0000-0000-0000-000000000001"),
        catalog_version_id=UUID("10000000-0000-0000-0000-000000000001"),
        catalog_version_code="catalog-v1",
        catalog_manifest_hash="a" * 64,
        name_ko="합성 운동",
        name_en="Synthetic Exercise",
        instruction_summary_ko="검수된 자세 설명",
        instruction_content_version="instruction-v1",
        training_type_code="STRENGTH",
        body_focus_code="FULL_BODY",
        primary_movement_pattern_code="SQUAT",
        difficulty_code="BEGINNER",
        recovery_eligible=False,
        review_status_code="DOMAIN_APPROVED",
        review_method_code="DOMAIN_REVIEWER",
        status_interpretation_code="PRODUCTION_APPROVED",
        production_eligible=True,
        goal_codes=("GENERAL_FITNESS",),
        equipment_codes=("BODYWEIGHT",),
        location_codes=("HOME",),
        phase_codes=("MAIN",),
        prescription_experience_level_codes=("BEGINNER", "INTERMEDIATE"),
    )


class FakeRepository:
    def __init__(self, records: tuple[IndexableExerciseRecord, ...]) -> None:
        self.records = records
        self.registry: SimpleNamespace | None = None

    def list_indexable_exercises(
        self, _session: Any, _catalog: str
    ) -> tuple[IndexableExerciseRecord, ...]:
        return self.records

    def create_build(self, _session: Any, write: Any) -> SimpleNamespace:
        if self.registry is None:
            self.registry = SimpleNamespace(
                status_code="BUILDING",
                catalog_version_id=write.catalog_version_id,
                built_at=None,
            )
        return self.registry

    def mark_ready(self, _session: Any, record: SimpleNamespace, *, built_at: datetime) -> None:
        record.status_code = "READY"
        record.built_at = built_at

    def activate(self, _session: Any, record: SimpleNamespace, *, activated_at: datetime) -> None:
        record.status_code = "ACTIVE"
        record.activated_at = activated_at

    def mark_failed(self, _session: Any, record: SimpleNamespace) -> None:
        record.status_code = "FAILED"


class FakeCollectionManager:
    def __init__(self) -> None:
        self.points: tuple[Any, ...] = ()
        self.activations = 0
        self.active_collection: str | None = None
        self.validation_calls = 0

    def build(self, **kwargs: Any) -> None:
        self.points = kwargs["points"]

    def validate(self, **_kwargs: Any) -> None:
        self.validation_calls += 1

    def activate(self, collection_name: str) -> bool:
        if self.active_collection == collection_name:
            return False
        self.active_collection = collection_name
        self.activations += 1
        return True


def _builder(
    records: tuple[IndexableExerciseRecord, ...],
) -> tuple[ExerciseVectorIndexBuilder, FakeCollectionManager]:
    manager = FakeCollectionManager()
    embedding = DeterministicFakeEmbeddingAdapter(
        EmbeddingContract(
            provider_code="FAKE",
            model_version="fake-v1",
            input_schema_version="exercise-embedding-input-v2",
            vector_dimension=4,
            distance_metric_code="COSINE",
        )
    )
    return (
        ExerciseVectorIndexBuilder(
            repository=FakeRepository(records),  # type: ignore[arg-type]
            collection_manager=manager,  # type: ignore[arg-type]
            embedding=embedding,
            collection_prefix="exercise_catalog",
            environment="test",
        ),
        manager,
    )


def test_index_builder_uses_uuid_points_and_privacy_allowlisted_payload() -> None:
    builder, manager = _builder((_record(),))

    result = builder.build_and_activate(
        object(),  # type: ignore[arg-type]
        catalog_version="catalog-v1",
        vector_index_version="index-v1",
        now=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert result.point_count == 1
    assert manager.activations == 1
    point = manager.points[0]
    assert point.exercise_id == _record().exercise_id
    assert point.payload["payload_schema_version"] == 2
    assert "beginner_suitable" not in point.payload
    forbidden = {
        "user_id",
        "decision_id",
        "pain_present",
        "body_area_code",
        "pain_intensity_score",
        "severity",
        "raw_checkin",
        "wearable",
        "calendar",
        "email",
        "name",
    }
    assert forbidden.isdisjoint(point.payload)
    assert "검수된 자세 설명" not in str(point.payload)


def test_unapproved_exercise_is_never_indexed() -> None:
    builder, manager = _builder((replace(_record(), production_eligible=False),))

    with pytest.raises(ValueError, match="production approval gate"):
        builder.build_and_activate(
            object(),  # type: ignore[arg-type]
            catalog_version="catalog-v1",
            vector_index_version="index-v1",
            now=datetime(2026, 8, 24, tzinfo=UTC),
        )

    assert manager.points == ()


def test_same_exercise_and_index_version_rerun_is_idempotent() -> None:
    builder, manager = _builder((_record(),))
    now = datetime(2026, 8, 24, tzinfo=UTC)

    first = builder.build_and_activate(
        object(),  # type: ignore[arg-type]
        catalog_version="catalog-v1",
        vector_index_version="index-v1",
        now=now,
    )
    second = builder.build_and_activate(
        object(),  # type: ignore[arg-type]
        catalog_version="catalog-v1",
        vector_index_version="index-v1",
        now=now,
    )

    assert first.build_hash == second.build_hash
    assert first.point_count == second.point_count == 1
    assert second.alias_changed is False
    assert manager.activations == 1
    assert manager.validation_calls == 1


def test_embedding_document_has_only_reviewed_catalog_projection() -> None:
    document = canonical_embedding_document(_record())

    assert "합성 운동" in document
    assert "GENERAL_FITNESS" in document
    assert "beginner_suitable" not in document
    for forbidden in ("pain_present", "severity", "user_id", "wearable", "calendar"):
        assert forbidden not in document
