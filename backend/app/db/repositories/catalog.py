from collections.abc import Iterable
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.catalog import (
    BodyArea,
    BodyFocus,
    CatalogVersion,
    Equipment,
    Exercise,
    ExerciseBodyPart,
    ExerciseEquipment,
    ExerciseLocation,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.modules.catalog.codes import (
    CATALOG_CODE_SET_VERSION,
    BodyAreaRoleCode,
    EquipmentRequirementCode,
    approved_display_name,
)
from backend.app.modules.catalog.service import CatalogArtifact


class CatalogRepository:
    def get_by_version_code(
        self,
        session: Session,
        version_code: str,
    ) -> CatalogVersion | None:
        return session.scalar(
            select(CatalogVersion).where(CatalogVersion.version_code == version_code)
        )

    def _ensure_lookup_rows(
        self,
        session: Session,
        model: type[TrainingType]
        | type[BodyFocus]
        | type[MovementPattern]
        | type[Equipment]
        | type[Location]
        | type[BodyArea],
        codes: Iterable[StrEnum],
    ) -> None:
        for code in sorted(set(codes), key=str):
            if session.get(model, str(code)) is None:
                session.add(
                    model(
                        code=str(code),
                        code_set_version=CATALOG_CODE_SET_VERSION,
                        display_name_ko=approved_display_name(code),
                    )
                )

    def create_from_artifact(
        self,
        session: Session,
        artifact: CatalogArtifact,
    ) -> CatalogVersion:
        records = artifact.records
        self._ensure_lookup_rows(session, TrainingType, (row.training_type_code for row in records))
        self._ensure_lookup_rows(session, BodyFocus, (row.body_focus_code for row in records))
        self._ensure_lookup_rows(
            session,
            MovementPattern,
            (row.primary_movement_pattern_code for row in records),
        )
        self._ensure_lookup_rows(
            session,
            Equipment,
            (code for row in records for code in row.equipment_codes),
        )
        self._ensure_lookup_rows(
            session,
            Location,
            (code for row in records for code in row.location_codes),
        )
        self._ensure_lookup_rows(
            session,
            BodyArea,
            (
                code
                for row in records
                for code in (*row.primary_body_area_codes, *row.secondary_body_area_codes)
            ),
        )

        manifest = artifact.manifest
        catalog_version = CatalogVersion(
            id=uuid4(),
            version_code=manifest.catalog_version.version_code,
            status_code=manifest.catalog_version.status_code,
            manifest_schema_version=manifest.schema_version,
            generator_version=manifest.generator_version,
            code_set_version=CATALOG_CODE_SET_VERSION,
            source_manifest_hash=artifact.manifest_hash,
            source_track_code=manifest.source.track,
            review_status_code=manifest.review.status,
            review_method_code=manifest.review.review_method_code,
            status_interpretation_code=manifest.review.status_interpretation,
            production_eligible=manifest.review.production_eligible,
            exercise_record_count=len(records),
            manifest_metadata=manifest.model_dump(mode="json"),
        )
        session.add(catalog_version)

        for record in records:
            exercise = Exercise(
                id=uuid4(),
                catalog_version=catalog_version,
                stable_code=record.stable_code,
                name_ko=record.name_ko,
                name_en=record.name_en or None,
                training_type_code=record.training_type_code,
                body_focus_code=record.body_focus_code,
                primary_movement_pattern_code=record.primary_movement_pattern_code,
                difficulty_code=record.difficulty_code,
                beginner_suitable=record.beginner_suitable,
                timing_mode_code=record.timing_mode_code,
                default_seconds_per_rep=record.default_seconds_per_rep,
                default_work_seconds=record.default_work_seconds,
                default_rest_seconds=record.default_rest_seconds,
                default_transition_seconds=record.default_transition_seconds,
                recovery_eligible=record.recovery_eligible,
                instruction_summary_ko=record.instruction_summary_ko,
                form_cues_ko=record.form_cues_ko,
                instruction_content_version=record.instruction_content_version,
                review_status_code=record.review_status_code,
                source_track_code=record.source_track,
                source_identity=record.source_identity,
                body_parts=[
                    ExerciseBodyPart(
                        body_area_code=code,
                        role_code=BodyAreaRoleCode.PRIMARY,
                    )
                    for code in record.primary_body_area_codes
                ]
                + [
                    ExerciseBodyPart(
                        body_area_code=code,
                        role_code=BodyAreaRoleCode.SECONDARY,
                    )
                    for code in record.secondary_body_area_codes
                ],
                equipment_links=[
                    ExerciseEquipment(
                        equipment_code=code,
                        requirement_code=EquipmentRequirementCode.REQUIRED,
                    )
                    for code in record.equipment_codes
                ],
                location_links=[
                    ExerciseLocation(location_code=code) for code in record.location_codes
                ],
            )
            session.add(exercise)

        session.flush()
        return catalog_version


__all__ = ["CatalogRepository"]
