from collections.abc import Iterable
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from backend.app.db.models.catalog import (
    BodyArea,
    BodyFocus,
    CatalogVersion,
    Equipment,
    Exercise,
    ExerciseAlternative,
    ExerciseBodyPart,
    ExerciseEquipment,
    ExerciseGoalTagLink,
    ExerciseLocation,
    ExerciseMediaAsset,
    ExercisePrescriptionProfile,
    ExerciseSafetyRule,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.modules.catalog.approvals import get_catalog_approval, get_derived_data_approval
from backend.app.modules.catalog.codes import (
    BodyAreaRoleCode,
    EquipmentRequirementCode,
    approved_display_name,
)
from backend.app.modules.catalog.service import (
    AlternativeArtifact,
    ApprovedCatalogRecord,
    CatalogArtifact,
    CatalogImportError,
    DerivedSetState,
    ExerciseDetailRecord,
    ExerciseListRecord,
    ExerciseVariantRecord,
    ExerciseVariantSetUnavailableError,
    ExerciseVariantsRecord,
    MediaArtifact,
    PrescriptionArtifact,
    SafetyRuleArtifact,
)


class CatalogRepository:
    def get_approved_catalog(self, session: Session) -> ApprovedCatalogRecord | None:
        catalog = session.scalar(
            select(CatalogVersion).where(
                CatalogVersion.status_code == "ACTIVE",
                CatalogVersion.review_status_code == "DOMAIN_APPROVED",
                CatalogVersion.review_method_code == "DOMAIN_REVIEWER",
                CatalogVersion.status_interpretation_code == "PRODUCTION_APPROVED",
                CatalogVersion.production_eligible.is_(True),
                CatalogVersion.activated_at.is_not(None),
            )
        )
        if catalog is None:
            return None
        return ApprovedCatalogRecord(
            catalog_version_id=catalog.id,
            version_code=catalog.version_code,
        )

    def list_approved_exercises(
        self,
        session: Session,
        catalog_version_id: UUID,
        *,
        body_area_code: str | None,
        equipment_code: str | None,
        training_type_code: str | None,
        difficulty_code: str | None,
        after_exercise_id: UUID | None,
        limit: int,
    ) -> tuple[ExerciseListRecord, ...]:
        statement = (
            select(
                Exercise.id,
                Exercise.name_ko,
                Exercise.training_type_code,
                Exercise.difficulty_code,
                ExerciseMediaAsset.s3_key.label("media_asset_key"),
            )
            .outerjoin(
                ExerciseMediaAsset,
                and_(
                    ExerciseMediaAsset.exercise_id == Exercise.id,
                    ExerciseMediaAsset.media_status == "AVAILABLE",
                    ExerciseMediaAsset.rights_review_status == "APPROVED",
                    ExerciseMediaAsset.approval_metadata.is_not(None),
                ),
            )
            .where(
                Exercise.catalog_version_id == catalog_version_id,
                Exercise.review_status_code == "DOMAIN_APPROVED",
            )
        )
        if body_area_code is not None:
            statement = statement.where(
                select(ExerciseBodyPart.exercise_id)
                .where(
                    ExerciseBodyPart.exercise_id == Exercise.id,
                    ExerciseBodyPart.body_area_code == body_area_code,
                    ExerciseBodyPart.role_code == BodyAreaRoleCode.PRIMARY,
                )
                .exists()
            )
        if equipment_code is not None:
            statement = statement.where(
                select(ExerciseEquipment.exercise_id)
                .where(
                    ExerciseEquipment.exercise_id == Exercise.id,
                    ExerciseEquipment.equipment_code == equipment_code,
                    ExerciseEquipment.requirement_code == EquipmentRequirementCode.REQUIRED,
                )
                .exists()
            )
        if training_type_code is not None:
            statement = statement.where(Exercise.training_type_code == training_type_code)
        if difficulty_code is not None:
            statement = statement.where(Exercise.difficulty_code == difficulty_code)
        if after_exercise_id is not None:
            statement = statement.where(Exercise.id > after_exercise_id)

        rows = session.execute(statement.order_by(Exercise.id).limit(limit)).all()
        exercise_ids = [row.id for row in rows]
        primary_body_areas: dict[UUID, list[str]] = {
            exercise_id: [] for exercise_id in exercise_ids
        }
        required_equipment: dict[UUID, list[str]] = {
            exercise_id: [] for exercise_id in exercise_ids
        }
        if exercise_ids:
            for exercise_id, code in session.execute(
                select(ExerciseBodyPart.exercise_id, ExerciseBodyPart.body_area_code)
                .where(
                    ExerciseBodyPart.exercise_id.in_(exercise_ids),
                    ExerciseBodyPart.role_code == BodyAreaRoleCode.PRIMARY,
                )
                .order_by(ExerciseBodyPart.exercise_id, ExerciseBodyPart.body_area_code)
            ):
                primary_body_areas[exercise_id].append(code)
            for exercise_id, code in session.execute(
                select(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code)
                .where(
                    ExerciseEquipment.exercise_id.in_(exercise_ids),
                    ExerciseEquipment.requirement_code == EquipmentRequirementCode.REQUIRED,
                )
                .order_by(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code)
            ):
                required_equipment[exercise_id].append(code)

        return tuple(
            ExerciseListRecord(
                exercise_id=row.id,
                exercise_name=row.name_ko,
                training_type_code=row.training_type_code,
                difficulty_code=row.difficulty_code,
                primary_body_area_codes=tuple(primary_body_areas[row.id]),
                required_equipment_codes=tuple(required_equipment[row.id]),
                media_asset_key=row.media_asset_key,
            )
            for row in rows
        )

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
        media_asset_key = session.scalar(
            select(ExerciseMediaAsset.s3_key).where(
                ExerciseMediaAsset.exercise_id == exercise_id,
                ExerciseMediaAsset.catalog_version_id == exercise.catalog_version_id,
                ExerciseMediaAsset.media_status == "AVAILABLE",
                ExerciseMediaAsset.rights_review_status == "APPROVED",
                ExerciseMediaAsset.approval_metadata.is_not(None),
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
            media_asset_key=media_asset_key,
        )

    def get_equipment_variants(
        self,
        session: Session,
        catalog_version_id: UUID,
        exercise_id: UUID,
    ) -> ExerciseVariantsRecord | None:
        source_exercise = session.scalar(
            select(Exercise).where(
                Exercise.id == exercise_id,
                Exercise.catalog_version_id == catalog_version_id,
                Exercise.review_status_code == "DOMAIN_APPROVED",
            )
        )
        if source_exercise is None:
            return None

        source_required_equipment_codes = tuple(
            session.scalars(
                select(ExerciseEquipment.equipment_code)
                .where(
                    ExerciseEquipment.exercise_id == exercise_id,
                    ExerciseEquipment.requirement_code == EquipmentRequirementCode.REQUIRED,
                )
                .order_by(ExerciseEquipment.equipment_code)
            )
        )

        variant_exercise = aliased(Exercise)
        rows = session.execute(
            select(
                ExerciseAlternative.alternative_set_version_code,
                ExerciseAlternative.goal_preservation_code,
                variant_exercise.id,
                variant_exercise.name_ko,
                variant_exercise.instruction_summary_ko,
                variant_exercise.form_cues_ko,
                ExerciseMediaAsset.s3_key.label("media_asset_key"),
            )
            .join(
                variant_exercise,
                variant_exercise.id == ExerciseAlternative.alternative_exercise_id,
            )
            .outerjoin(
                ExerciseMediaAsset,
                and_(
                    ExerciseMediaAsset.exercise_id == variant_exercise.id,
                    ExerciseMediaAsset.catalog_version_id == catalog_version_id,
                    ExerciseMediaAsset.media_status == "AVAILABLE",
                    ExerciseMediaAsset.rights_review_status == "APPROVED",
                    ExerciseMediaAsset.approval_metadata.is_not(None),
                ),
            )
            .where(
                ExerciseAlternative.source_exercise_id == exercise_id,
                ExerciseAlternative.reason_code == "EQUIPMENT",
                ExerciseAlternative.review_status_code == "DOMAIN_APPROVED",
                ExerciseAlternative.production_eligible.is_(True),
                ExerciseAlternative.source_metadata["production_approval"].is_not(None),
                variant_exercise.catalog_version_id == catalog_version_id,
                variant_exercise.review_status_code == "DOMAIN_APPROVED",
            )
            .order_by(
                variant_exercise.id,
                ExerciseAlternative.goal_preservation_code,
                ExerciseAlternative.id,
            )
        ).all()

        alternative_set_versions = {row.alternative_set_version_code for row in rows}
        if len(alternative_set_versions) > 1:
            raise ExerciseVariantSetUnavailableError

        variant_ids = [row.id for row in rows]
        required_equipment: dict[UUID, list[str]] = {variant_id: [] for variant_id in variant_ids}
        if variant_ids:
            for variant_id, code in session.execute(
                select(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code)
                .where(
                    ExerciseEquipment.exercise_id.in_(variant_ids),
                    ExerciseEquipment.requirement_code == EquipmentRequirementCode.REQUIRED,
                )
                .order_by(ExerciseEquipment.exercise_id, ExerciseEquipment.equipment_code)
            ):
                required_equipment[variant_id].append(code)

        return ExerciseVariantsRecord(
            source_exercise_id=exercise_id,
            source_required_equipment_codes=source_required_equipment_codes,
            alternative_set_version=(
                next(iter(alternative_set_versions)) if alternative_set_versions else None
            ),
            items=tuple(
                ExerciseVariantRecord(
                    exercise_id=row.id,
                    exercise_name=row.name_ko,
                    required_equipment_codes=tuple(required_equipment[row.id]),
                    instruction_summary=row.instruction_summary_ko,
                    form_cues=tuple(row.form_cues_ko),
                    goal_preservation_code=row.goal_preservation_code,
                    media_asset_key=row.media_asset_key,
                )
                for row in rows
            ),
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
        *,
        code_set_version: str,
    ) -> None:
        for code in sorted(set(codes), key=str):
            if session.get(model, str(code)) is None:
                session.add(
                    model(
                        code=str(code),
                        code_set_version=code_set_version,
                        display_name_ko=approved_display_name(code),
                    )
                )

    def create_from_artifact(
        self,
        session: Session,
        artifact: CatalogArtifact,
    ) -> CatalogVersion:
        records = artifact.records
        code_set_version = artifact.code_set_version
        self._ensure_lookup_rows(
            session,
            TrainingType,
            (row.training_type_code for row in records),
            code_set_version=code_set_version,
        )
        self._ensure_lookup_rows(
            session,
            BodyFocus,
            (row.body_focus_code for row in records),
            code_set_version=code_set_version,
        )
        self._ensure_lookup_rows(
            session,
            MovementPattern,
            (row.primary_movement_pattern_code for row in records),
            code_set_version=code_set_version,
        )
        self._ensure_lookup_rows(
            session,
            Equipment,
            (code for row in records for code in row.equipment_codes),
            code_set_version=code_set_version,
        )
        self._ensure_lookup_rows(
            session,
            Location,
            (code for row in records for code in row.location_codes),
            code_set_version=code_set_version,
        )
        self._ensure_lookup_rows(
            session,
            BodyArea,
            (
                code
                for row in records
                for code in (*row.primary_body_area_codes, *row.secondary_body_area_codes)
            ),
            code_set_version=code_set_version,
        )

        manifest = artifact.manifest
        approval = get_catalog_approval(
            manifest.catalog_version.version_code, artifact.manifest_hash, len(records)
        )
        metadata = manifest.model_dump(mode="json")
        if approval is not None:
            metadata["production_approval"] = approval.metadata()
        catalog_version = CatalogVersion(
            id=uuid4(),
            version_code=manifest.catalog_version.version_code,
            status_code=manifest.catalog_version.status_code,
            manifest_schema_version=manifest.schema_version,
            generator_version=manifest.generator_version,
            code_set_version=artifact.code_set_version,
            source_manifest_hash=artifact.manifest_hash,
            source_track_code=manifest.source.track,
            review_status_code=manifest.review.status,
            review_method_code=(
                "DOMAIN_REVIEWER" if approval is not None else manifest.review.review_method_code
            ),
            status_interpretation_code=(
                "PRODUCTION_APPROVED"
                if approval is not None
                else manifest.review.status_interpretation
            ),
            production_eligible=manifest.review.production_eligible,
            exercise_record_count=len(records),
            manifest_metadata=metadata,
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

    def get_prescription_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None:
        catalogs = session.scalars(select(CatalogVersion)).all()
        for catalog in catalogs:
            metadata = catalog.manifest_metadata.get("prescription_artifact")
            if not isinstance(metadata, dict) or metadata.get("version_code") != version_code:
                continue
            exercise_ids = select(Exercise.id).where(Exercise.catalog_version_id == catalog.id)
            goals = session.scalar(
                select(func.count())
                .select_from(ExerciseGoalTagLink)
                .where(ExerciseGoalTagLink.exercise_id.in_(exercise_ids))
            )
            profiles = session.scalar(
                select(func.count())
                .select_from(ExercisePrescriptionProfile)
                .where(ExercisePrescriptionProfile.exercise_id.in_(exercise_ids))
            )
            count = int(goals or 0) + int(profiles or 0)
            manifest_hash = metadata.get("manifest_sha256")
            if not isinstance(manifest_hash, str):
                raise CatalogImportError(
                    "DERIVED_SET_CONFLICT", "prescription metadata has no manifest hash"
                )
            return DerivedSetState(count, manifest_hash)
        return None

    def create_prescriptions(self, session: Session, artifact: PrescriptionArtifact) -> None:
        exercise_ids = self._exercise_ids(session)
        catalogs = {row.version_code: row for row in session.scalars(select(CatalogVersion)).all()}
        for goal_record in artifact.goal_tag_records:
            exercise_id = exercise_ids.get(
                (goal_record.catalog_version_code, goal_record.exercise_stable_code)
            )
            if exercise_id is None:
                raise CatalogImportError(
                    "EXERCISE_REFERENCE_NOT_FOUND", "goal tag references an unknown exercise"
                )
            session.add(
                ExerciseGoalTagLink(
                    exercise_id=exercise_id,
                    goal_code=goal_record.goal_code,
                    role_eligibility_code=goal_record.role_eligibility_code,
                    review_status_code=goal_record.review_status_code,
                )
            )
        for profile_record in artifact.prescription_records:
            exercise_id = exercise_ids.get(
                (profile_record.catalog_version_code, profile_record.exercise_stable_code)
            )
            if exercise_id is None:
                raise CatalogImportError(
                    "EXERCISE_REFERENCE_NOT_FOUND",
                    "prescription references an unknown exercise",
                )
            session.add(
                ExercisePrescriptionProfile(
                    exercise_id=exercise_id,
                    goal_code=profile_record.goal_code,
                    experience_level_code=profile_record.experience_level_code,
                    phase_code=profile_record.phase_code,
                    sets=profile_record.sets,
                    reps=profile_record.reps,
                    work_seconds_per_set=profile_record.work_seconds_per_set,
                    rest_seconds_per_set=profile_record.rest_seconds_per_set,
                    intensity_code=profile_record.intensity_code,
                    prescription_version=profile_record.prescription_version,
                    review_status_code=profile_record.review_status_code,
                )
            )
        version_code = artifact.manifest.prescription_set_version.version_code
        total = len(artifact.goal_tag_records) + len(artifact.prescription_records)
        approval = get_derived_data_approval(
            "PRESCRIPTIONS", version_code, artifact.manifest_hash, total
        )
        catalog_versions = {row.catalog_version_code for row in artifact.goal_tag_records} | {
            row.catalog_version_code for row in artifact.prescription_records
        }
        for version in catalog_versions:
            catalog = catalogs.get(version)
            if catalog is None:
                raise CatalogImportError(
                    "CATALOG_REFERENCE_NOT_FOUND",
                    "prescription references an unknown catalog",
                )
            prescription_metadata: dict[str, object] = {
                "version_code": version_code,
                "manifest_sha256": artifact.manifest_hash,
                "goal_tag_records": len(artifact.goal_tag_records),
                "prescription_records": len(artifact.prescription_records),
            }
            if approval is not None:
                prescription_metadata["production_approval"] = approval.metadata()
            catalog.manifest_metadata = {
                **catalog.manifest_metadata,
                "prescription_artifact": prescription_metadata,
            }
        session.flush()

    def get_media_set_state(self, session: Session, version_code: str) -> DerivedSetState | None:
        count, minimum_hash, maximum_hash = session.execute(
            select(
                func.count(ExerciseMediaAsset.id),
                func.min(ExerciseMediaAsset.source_manifest_hash),
                func.max(ExerciseMediaAsset.source_manifest_hash),
            ).where(ExerciseMediaAsset.media_set_version_code == version_code)
        ).one()
        if count == 0:
            return None
        if minimum_hash != maximum_hash or minimum_hash is None:
            raise CatalogImportError(
                "DERIVED_SET_CONFLICT", "media set contains mixed manifest hashes"
            )
        return DerivedSetState(record_count=count, manifest_hash=minimum_hash)

    def create_media_assets(self, session: Session, artifact: MediaArtifact) -> None:
        exercise_ids = self._exercise_ids(session)
        manifest = artifact.manifest
        version_code = manifest.media_set_version.version_code
        approval = get_derived_data_approval(
            "MEDIA_ASSETS", version_code, artifact.manifest_hash, len(artifact.records)
        )
        manifest_metadata = manifest.model_dump(mode="json")
        for record, stable_code in zip(
            artifact.records, artifact.exercise_stable_codes, strict=True
        ):
            exercise_id = exercise_ids.get((manifest.catalog_version_code, stable_code))
            if exercise_id is None:
                raise CatalogImportError(
                    "MEDIA_EXERCISE_REFERENCE_NOT_FOUND",
                    "media asset references an unknown exercise",
                )
            catalog = session.scalar(
                select(CatalogVersion).where(
                    CatalogVersion.version_code == manifest.catalog_version_code
                )
            )
            if catalog is None:
                raise CatalogImportError(
                    "CATALOG_REFERENCE_NOT_FOUND", "media asset references an unknown catalog"
                )
            session.add(
                ExerciseMediaAsset(
                    id=uuid4(),
                    catalog_version_id=catalog.id,
                    exercise_id=exercise_id,
                    s3_key=record.s3_key,
                    media_status=record.media_status,
                    rights_review_status=record.rights_review_status,
                    rights_reviewer=record.rights_reviewer,
                    rights_reviewed_at=record.rights_reviewed_at,
                    rights_evidence_reference=record.rights_evidence_reference,
                    media_set_version_code=version_code,
                    source_manifest_hash=artifact.manifest_hash,
                    source_metadata={
                        "manifest": manifest_metadata,
                        "record": record.source_metadata,
                        "representative_exercise_id": record.representative_exercise_id,
                    },
                    approval_metadata=approval.metadata() if approval is not None else None,
                )
            )
        session.flush()


__all__ = ["CatalogRepository"]
