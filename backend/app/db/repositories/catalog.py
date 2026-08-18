from collections.abc import Iterable
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.catalog import (
    BodyArea,
    BodyFocus,
    CatalogVersion,
    Equipment,
    Exercise,
    ExerciseAlternative,
    ExerciseBodyPart,
    ExerciseEquipment,
    ExerciseLocation,
    ExerciseSafetyRule,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.modules.catalog.approvals import get_derived_data_approval
from backend.app.modules.catalog.codes import (
    CATALOG_CODE_SET_VERSION,
    BodyAreaRoleCode,
    EquipmentRequirementCode,
    approved_display_name,
)
from backend.app.modules.catalog.service import (
    AlternativeArtifact,
    CatalogArtifact,
    CatalogImportError,
    DerivedSetState,
    ExerciseDetailRecord,
    SafetyRuleArtifact,
)


class CatalogRepository:
    def get_exercise_detail(
        self,
        session: Session,
        exercise_id: UUID,
    ) -> ExerciseDetailRecord | None:
        exercise = session.get(Exercise, exercise_id)
        if exercise is None or exercise.review_status_code != "DOMAIN_APPROVED":
            return None
        primary_body_area_codes = tuple(
            session.scalars(
                select(ExerciseBodyPart.body_area_code)
                .where(
                    ExerciseBodyPart.exercise_id == exercise_id,
                    ExerciseBodyPart.role_code == BodyAreaRoleCode.PRIMARY,
                )
                .order_by(ExerciseBodyPart.body_area_code)
            )
        )
        return ExerciseDetailRecord(
            exercise_id=exercise.id,
            exercise_name=exercise.name_ko,
            training_type_code=exercise.training_type_code,
            primary_body_area_codes=primary_body_area_codes,
            instruction_summary=exercise.instruction_summary_ko,
            form_cues=tuple(exercise.form_cues_ko),
            instruction_content_version=exercise.instruction_content_version,
        )

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

    def get_safety_rule_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None:
        count, minimum_hash, maximum_hash = session.execute(
            select(
                func.count(ExerciseSafetyRule.id),
                func.min(ExerciseSafetyRule.source_manifest_hash),
                func.max(ExerciseSafetyRule.source_manifest_hash),
            ).where(ExerciseSafetyRule.rule_set_version_code == version_code)
        ).one()
        if count == 0:
            return None
        if minimum_hash != maximum_hash or minimum_hash is None:
            raise CatalogImportError(
                "DERIVED_SET_CONFLICT", "safety rule set contains mixed manifest hashes"
            )
        return DerivedSetState(record_count=count, manifest_hash=minimum_hash)

    def get_alternative_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None:
        count, minimum_hash, maximum_hash = session.execute(
            select(
                func.count(ExerciseAlternative.id),
                func.min(ExerciseAlternative.source_manifest_hash),
                func.max(ExerciseAlternative.source_manifest_hash),
            ).where(ExerciseAlternative.alternative_set_version_code == version_code)
        ).one()
        if count == 0:
            return None
        if minimum_hash != maximum_hash or minimum_hash is None:
            raise CatalogImportError(
                "DERIVED_SET_CONFLICT", "alternative set contains mixed manifest hashes"
            )
        return DerivedSetState(record_count=count, manifest_hash=minimum_hash)

    def _catalog_ids(self, session: Session) -> dict[str, UUID]:
        rows = session.execute(select(CatalogVersion.version_code, CatalogVersion.id))
        return {version_code: catalog_id for version_code, catalog_id in rows}

    def _exercise_ids(self, session: Session) -> dict[tuple[str, str], UUID]:
        rows = session.execute(
            select(CatalogVersion.version_code, Exercise.stable_code, Exercise.id).join(
                Exercise, Exercise.catalog_version_id == CatalogVersion.id
            )
        )
        return {
            (version_code, stable_code): exercise_id
            for version_code, stable_code, exercise_id in rows
        }

    def create_safety_rules(self, session: Session, artifact: SafetyRuleArtifact) -> None:
        catalog_ids = self._catalog_ids(session)
        exercise_ids = self._exercise_ids(session)
        manifest = artifact.manifest
        version_code = manifest.rule_set_version.version_code
        metadata = manifest.model_dump(mode="json")
        approval = get_derived_data_approval(
            "SAFETY_RULES", version_code, artifact.manifest_hash, len(artifact.records)
        )
        if approval is not None:
            metadata["production_approval"] = approval.metadata()
        for record in artifact.records:
            catalog_id = catalog_ids.get(record.catalog_version_code)
            if catalog_id is None:
                raise CatalogImportError(
                    "CATALOG_REFERENCE_NOT_FOUND", "safety rule references an unknown catalog"
                )
            exercise_id = None
            if record.exercise_stable_code is not None:
                exercise_id = exercise_ids.get(
                    (record.catalog_version_code, record.exercise_stable_code)
                )
                if exercise_id is None:
                    raise CatalogImportError(
                        "EXERCISE_REFERENCE_NOT_FOUND",
                        "safety rule references an unknown exercise",
                    )
            session.add(
                ExerciseSafetyRule(
                    id=uuid4(),
                    catalog_version_id=catalog_id,
                    exercise_id=exercise_id,
                    movement_pattern_code=record.movement_pattern_code,
                    body_area_code=record.body_area_code,
                    body_part_role_code=record.body_part_role_code,
                    minimum_severity_code=record.minimum_severity_code,
                    maximum_severity_code=record.maximum_severity_code,
                    effect_code=record.effect_code,
                    reason_code=record.reason_code,
                    review_status_code=record.review_status_code,
                    rule_version=record.rule_version,
                    rule_set_version_code=version_code,
                    production_eligible=approval is not None,
                    source_manifest_hash=artifact.manifest_hash,
                    source_metadata=metadata,
                )
            )
        session.flush()

    def create_alternatives(self, session: Session, artifact: AlternativeArtifact) -> None:
        exercise_ids = self._exercise_ids(session)
        manifest = artifact.manifest
        version_code = manifest.alternative_set_version.version_code
        metadata = manifest.model_dump(mode="json")
        approval = get_derived_data_approval(
            "ALTERNATIVES", version_code, artifact.manifest_hash, len(artifact.records)
        )
        if approval is not None:
            metadata["production_approval"] = approval.metadata()
        for record in artifact.records:
            source_id = exercise_ids.get(
                (record.source_catalog_version_code, record.source_exercise_stable_code)
            )
            alternative_id = exercise_ids.get(
                (
                    record.alternative_catalog_version_code,
                    record.alternative_exercise_stable_code,
                )
            )
            if source_id is None or alternative_id is None:
                raise CatalogImportError(
                    "EXERCISE_REFERENCE_NOT_FOUND",
                    "alternative references an unknown exercise",
                )
            session.add(
                ExerciseAlternative(
                    id=uuid4(),
                    source_exercise_id=source_id,
                    alternative_exercise_id=alternative_id,
                    reason_code=record.reason_code,
                    goal_preservation_code=record.goal_preservation_code,
                    difficulty_delta=record.difficulty_delta,
                    review_status_code=record.review_status_code,
                    rule_version=record.rule_version,
                    alternative_set_version_code=version_code,
                    production_eligible=approval is not None,
                    source_manifest_hash=artifact.manifest_hash,
                    source_metadata=metadata,
                    created_at=record.created_at,
                )
            )
        session.flush()


__all__ = ["CatalogRepository"]
