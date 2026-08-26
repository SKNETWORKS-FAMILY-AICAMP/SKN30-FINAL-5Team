"""Persistence operations for immutable Qdrant index builds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseEquipment,
    ExerciseGoalTagLink,
    ExerciseLocation,
    ExercisePrescriptionProfile,
)
from backend.app.db.models.vector_index import VectorIndexRegistry


@dataclass(frozen=True, slots=True)
class VectorIndexBuildWrite:
    catalog_version_id: UUID
    collection_name: str
    vector_index_version: str
    source_manifest_hash: str
    embedding_model_version: str
    embedding_input_schema_version: str
    distance_metric_code: str
    vector_dimension: int
    build_hash: str


@dataclass(frozen=True, slots=True)
class IndexableExerciseRecord:
    exercise_id: UUID
    catalog_version_id: UUID
    catalog_version_code: str
    catalog_manifest_hash: str
    name_ko: str
    name_en: str | None
    instruction_summary_ko: str
    instruction_content_version: str
    training_type_code: str
    body_focus_code: str
    primary_movement_pattern_code: str
    difficulty_code: str
    beginner_suitable: bool
    recovery_eligible: bool
    review_status_code: str
    review_method_code: str
    status_interpretation_code: str
    production_eligible: bool
    goal_codes: tuple[str, ...]
    equipment_codes: tuple[str, ...]
    location_codes: tuple[str, ...]
    phase_codes: tuple[str, ...]
    stable_code: str = ""
    timing_mode_code: str = "REPS"


class VectorIndexRepository:
    def list_indexable_exercises(
        self, session: Session, catalog_version_code: str
    ) -> tuple[IndexableExerciseRecord, ...]:
        catalog = session.scalar(
            select(CatalogVersion).where(
                CatalogVersion.version_code == catalog_version_code,
                CatalogVersion.status_code == "ACTIVE",
                CatalogVersion.review_status_code == "DOMAIN_APPROVED",
                CatalogVersion.review_method_code == "DOMAIN_REVIEWER",
                CatalogVersion.status_interpretation_code == "PRODUCTION_APPROVED",
                CatalogVersion.production_eligible.is_(True),
                CatalogVersion.activated_at.is_not(None),
            )
        )
        if catalog is None:
            return ()
        exercises = tuple(
            session.scalars(
                select(Exercise)
                .where(
                    Exercise.catalog_version_id == catalog.id,
                    Exercise.review_status_code == "DOMAIN_APPROVED",
                )
                .order_by(Exercise.id)
            )
        )
        ids = tuple(exercise.id for exercise in exercises)
        goals: dict[UUID, list[str]] = {exercise_id: [] for exercise_id in ids}
        equipment: dict[UUID, list[str]] = {exercise_id: [] for exercise_id in ids}
        locations: dict[UUID, list[str]] = {exercise_id: [] for exercise_id in ids}
        phases: dict[UUID, list[str]] = {exercise_id: [] for exercise_id in ids}
        if ids:
            for exercise_id, code in session.execute(
                select(ExerciseGoalTagLink.exercise_id, ExerciseGoalTagLink.goal_code)
                .where(
                    ExerciseGoalTagLink.exercise_id.in_(ids),
                    ExerciseGoalTagLink.review_status_code == "DOMAIN_APPROVED",
                )
                .order_by(ExerciseGoalTagLink.exercise_id, ExerciseGoalTagLink.goal_code)
            ):
                goals[exercise_id].append(code)
            for exercise_id, code in session.execute(
                select(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code)
                .where(ExerciseEquipment.exercise_id.in_(ids))
                .order_by(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code)
            ):
                equipment[exercise_id].append(code)
            for exercise_id, code in session.execute(
                select(ExerciseLocation.exercise_id, ExerciseLocation.location_code)
                .where(ExerciseLocation.exercise_id.in_(ids))
                .order_by(ExerciseLocation.exercise_id, ExerciseLocation.location_code)
            ):
                locations[exercise_id].append(code)
            for exercise_id, code in session.execute(
                select(
                    ExercisePrescriptionProfile.exercise_id,
                    ExercisePrescriptionProfile.phase_code,
                )
                .where(
                    ExercisePrescriptionProfile.exercise_id.in_(ids),
                    ExercisePrescriptionProfile.review_status_code == "DOMAIN_APPROVED",
                )
                .distinct()
                .order_by(
                    ExercisePrescriptionProfile.exercise_id,
                    ExercisePrescriptionProfile.phase_code,
                )
            ):
                phases[exercise_id].append(code)
        return tuple(
            IndexableExerciseRecord(
                exercise_id=exercise.id,
                catalog_version_id=catalog.id,
                catalog_version_code=catalog.version_code,
                catalog_manifest_hash=catalog.source_manifest_hash,
                name_ko=exercise.name_ko,
                name_en=exercise.name_en,
                instruction_summary_ko=exercise.instruction_summary_ko,
                instruction_content_version=exercise.instruction_content_version,
                training_type_code=exercise.training_type_code,
                body_focus_code=exercise.body_focus_code,
                primary_movement_pattern_code=exercise.primary_movement_pattern_code,
                difficulty_code=exercise.difficulty_code,
                beginner_suitable=exercise.beginner_suitable,
                recovery_eligible=exercise.recovery_eligible,
                review_status_code=exercise.review_status_code,
                review_method_code=catalog.review_method_code,
                status_interpretation_code=catalog.status_interpretation_code,
                production_eligible=catalog.production_eligible,
                goal_codes=tuple(goals[exercise.id]),
                equipment_codes=tuple(equipment[exercise.id]),
                location_codes=tuple(locations[exercise.id]),
                phase_codes=tuple(phases[exercise.id]),
                stable_code=exercise.stable_code,
                timing_mode_code=exercise.timing_mode_code,
            )
            for exercise in exercises
        )

    def get_by_version(
        self, session: Session, vector_index_version: str
    ) -> VectorIndexRegistry | None:
        return session.scalar(
            select(VectorIndexRegistry).where(
                VectorIndexRegistry.vector_index_version == vector_index_version
            )
        )

    def get_active_for_catalog(
        self, session: Session, catalog_version_id: UUID
    ) -> VectorIndexRegistry | None:
        return session.scalar(
            select(VectorIndexRegistry).where(
                VectorIndexRegistry.catalog_version_id == catalog_version_id,
                VectorIndexRegistry.status_code == "ACTIVE",
            )
        )

    def create_build(self, session: Session, write: VectorIndexBuildWrite) -> VectorIndexRegistry:
        existing = self.get_by_version(session, write.vector_index_version)
        if existing is not None:
            expected = (
                write.catalog_version_id,
                write.collection_name,
                write.source_manifest_hash,
                write.embedding_model_version,
                write.embedding_input_schema_version,
                write.distance_metric_code,
                write.vector_dimension,
                write.build_hash,
            )
            actual = (
                existing.catalog_version_id,
                existing.collection_name,
                existing.source_manifest_hash,
                existing.embedding_model_version,
                existing.embedding_input_schema_version,
                existing.distance_metric_code,
                existing.vector_dimension,
                existing.build_hash,
            )
            if actual != expected:
                raise ValueError("vector_index_version already exists with a different contract")
            return existing
        record = VectorIndexRegistry(
            id=uuid4(),
            catalog_version_id=write.catalog_version_id,
            collection_name=write.collection_name,
            vector_index_version=write.vector_index_version,
            source_manifest_hash=write.source_manifest_hash,
            embedding_model_version=write.embedding_model_version,
            embedding_input_schema_version=write.embedding_input_schema_version,
            distance_metric_code=write.distance_metric_code,
            vector_dimension=write.vector_dimension,
            build_hash=write.build_hash,
            status_code="BUILDING",
            built_at=None,
            activated_at=None,
        )
        session.add(record)
        session.flush()
        return record

    def mark_ready(
        self, session: Session, record: VectorIndexRegistry, *, built_at: datetime
    ) -> None:
        if record.status_code not in {"BUILDING", "READY", "FAILED"}:
            raise ValueError("only a building index can become ready")
        record.status_code = "READY"
        record.built_at = record.built_at or built_at
        session.flush()

    def activate(
        self, session: Session, record: VectorIndexRegistry, *, activated_at: datetime
    ) -> None:
        if record.status_code == "ACTIVE":
            return
        if record.status_code != "READY" or record.built_at is None:
            raise ValueError("only a ready index can become active")
        session.execute(
            update(VectorIndexRegistry)
            .where(
                VectorIndexRegistry.catalog_version_id == record.catalog_version_id,
                VectorIndexRegistry.status_code == "ACTIVE",
                VectorIndexRegistry.id != record.id,
            )
            .values(status_code="STALE")
        )
        record.status_code = "ACTIVE"
        record.activated_at = activated_at
        session.flush()

    def mark_failed(self, session: Session, record: VectorIndexRegistry) -> None:
        if record.status_code == "ACTIVE":
            raise ValueError("an active index cannot be marked failed")
        record.status_code = "FAILED"
        record.activated_at = None
        session.flush()


__all__ = ["IndexableExerciseRecord", "VectorIndexBuildWrite", "VectorIndexRepository"]
