from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class CatalogVersion(Base):
    __tablename__ = "catalog_versions"
    __table_args__ = (
        CheckConstraint(
            "status_code IN ('DRAFT', 'ACTIVE', 'DEPRECATED')",
            name="ck_catalog_versions_status_code",
        ),
        CheckConstraint(
            "manifest_schema_version IN ('1.0')",
            name="ck_catalog_versions_manifest_schema_version",
        ),
        CheckConstraint(
            "code_set_version IN ('mvp-v1', 'catalog-v2')",
            name="ck_catalog_versions_code_set_version",
        ),
        CheckConstraint(
            "source_track_code IN ('wger', 'kspo', 'merged')",
            name="ck_catalog_versions_source_track_code",
        ),
        CheckConstraint(
            "review_status_code IN ('DOMAIN_APPROVED')",
            name="ck_catalog_versions_review_status_code",
        ),
        CheckConstraint(
            "review_method_code IN ('AGENT_ONLY', 'DOMAIN_REVIEWER')",
            name="ck_catalog_versions_review_method_code",
        ),
        CheckConstraint(
            "status_interpretation_code IN ('PIPELINE_COMPATIBILITY_ONLY', 'PRODUCTION_APPROVED')",
            name="ck_catalog_versions_status_interpretation_code",
        ),
        CheckConstraint(
            "production_eligible = false OR "
            "(status_code = 'ACTIVE' AND review_status_code = 'DOMAIN_APPROVED' "
            "AND review_method_code = 'DOMAIN_REVIEWER' "
            "AND status_interpretation_code = 'PRODUCTION_APPROVED' "
            "AND activated_at IS NOT NULL)",
            name="ck_catalog_versions_production_approval",
        ),
        CheckConstraint("exercise_record_count >= 0", name="ck_catalog_versions_record_count"),
        Index(
            "uq_catalog_versions_single_active",
            "status_code",
            unique=True,
            postgresql_where=text("status_code = 'ACTIVE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    version_code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_track_code: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    review_method_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status_interpretation_code: Mapped[str] = mapped_column(String(64), nullable=False)
    production_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exercise_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    exercises: Mapped[list["Exercise"]] = relationship(
        back_populates="catalog_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TrainingType(Base):
    __tablename__ = "training_types"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(120), nullable=True)


class BodyFocus(Base):
    __tablename__ = "body_focuses"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MovementPattern(Base):
    __tablename__ = "movement_patterns"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Equipment(Base):
    __tablename__ = "equipment"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Location(Base):
    __tablename__ = "locations"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(120), nullable=True)


class BodyArea(Base):
    __tablename__ = "body_areas"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        UniqueConstraint(
            "catalog_version_id",
            "stable_code",
            name="uq_exercises_catalog_version_stable_code",
        ),
        CheckConstraint(
            "difficulty_code IN ('BEGINNER', 'INTERMEDIATE')",
            name="ck_exercises_difficulty_code",
        ),
        CheckConstraint(
            "timing_mode_code IN ('REPS', 'DURATION')",
            name="ck_exercises_timing_mode_code",
        ),
        CheckConstraint(
            "review_status_code IN ('DOMAIN_APPROVED')",
            name="ck_exercises_review_status_code",
        ),
        CheckConstraint(
            "source_track_code IN ('wger', 'kspo', 'gymvisual', 'pain_alternative_policy')",
            name="ck_exercises_source_track_code",
        ),
        CheckConstraint(
            "record_type IS NULL OR "
            "record_type IN ('REPRESENTATIVE', 'VARIANT', 'SEPARATE_EXERCISE')",
            name="ck_exercises_record_type",
        ),
        CheckConstraint(
            "(record_type = 'VARIANT') = (representative_stable_code IS NOT NULL)",
            name="ck_exercises_variant_parent",
        ),
        CheckConstraint("default_rest_seconds >= 0", name="ck_exercises_rest_seconds"),
        CheckConstraint(
            "default_transition_seconds BETWEEN 10 AND 20",
            name="ck_exercises_transition_seconds",
        ),
        CheckConstraint(
            "(timing_mode_code = 'REPS' AND default_seconds_per_rep > 0 "
            "AND default_work_seconds IS NULL) OR "
            "(timing_mode_code = 'DURATION' AND default_work_seconds > 0 "
            "AND default_seconds_per_rep IS NULL)",
            name="ck_exercises_timing_values",
        ),
        Index("ix_exercises_catalog_review", "catalog_version_id", "review_status_code"),
        Index("ix_exercises_general_pool", "catalog_version_id", "general_pool_included"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("catalog_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stable_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ko: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    training_type_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("training_types.code"), nullable=False
    )
    body_focus_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_focuses.code"), nullable=False
    )
    primary_movement_pattern_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("movement_patterns.code"), nullable=False
    )
    difficulty_code: Mapped[str] = mapped_column(String(32), nullable=False)
    # Transitional compatibility column. New catalog inputs no longer expose
    # this field and recommendation logic must not read it. Keep a deterministic
    # ORM value until the later Alembic removal after all consumers are gone.
    beginner_suitable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # v2.0.2 identity. NULL on v2.0.1 rows, which predate the family model.
    record_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    family_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    representative_stable_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # NULL means the payload did not state it, which the importer reads as "not
    # a base routine candidate". Never defaulted, so the two stay distinguishable.
    general_pool_included: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    timing_mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    default_seconds_per_rep: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_work_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_rest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    default_transition_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    instruction_summary_ko: Mapped[str] = mapped_column(Text, nullable=False)
    form_cues_ko: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    instruction_content_version: Mapped[str] = mapped_column(String(80), nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source_track_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    catalog_version: Mapped[CatalogVersion] = relationship(back_populates="exercises")
    body_parts: Mapped[list["ExerciseBodyPart"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    equipment_links: Mapped[list["ExerciseEquipment"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    location_links: Mapped[list["ExerciseLocation"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class ExerciseMediaAsset(Base):
    __tablename__ = "exercise_media_assets"
    __table_args__ = (
        UniqueConstraint("s3_key", name="uq_exercise_media_assets_s3_key"),
        UniqueConstraint(
            "catalog_version_id",
            "exercise_id",
            name="uq_exercise_media_assets_catalog_exercise",
        ),
        CheckConstraint(
            "media_status IN ('AVAILABLE', 'UNAVAILABLE')",
            name="ck_exercise_media_assets_media_status",
        ),
        CheckConstraint(
            "rights_review_status IN ('APPROVED', 'PENDING', 'REJECTED')",
            name="ck_exercise_media_assets_rights_status",
        ),
        CheckConstraint(
            "rights_review_status <> 'APPROVED' OR "
            "(rights_reviewer IS NOT NULL AND rights_reviewed_at IS NOT NULL "
            "AND rights_evidence_reference IS NOT NULL)",
            name="ck_exercise_media_assets_approved_evidence",
        ),
        CheckConstraint(
            "s3_key ~ '^catalog-media/[a-z0-9][a-z0-9_./-]*\\.(gif|jpe?g|mp4|png|webp)$' "
            "AND position('..' in s3_key) = 0",
            name="ck_exercise_media_assets_s3_key",
        ),
        Index(
            "ix_exercise_media_assets_approved",
            "catalog_version_id",
            "exercise_id",
            postgresql_where=text(
                "media_status = 'AVAILABLE' AND rights_review_status = 'APPROVED'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("catalog_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    media_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rights_review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rights_reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rights_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rights_evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_set_version_code: Mapped[str] = mapped_column(String(120), nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approval_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExerciseBodyPart(Base):
    __tablename__ = "exercise_body_parts"
    __table_args__ = (
        CheckConstraint(
            "role_code IN ('PRIMARY', 'SECONDARY')",
            name="ck_exercise_body_parts_role_code",
        ),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        primary_key=True,
    )
    body_area_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_areas.code"), primary_key=True
    )
    role_code: Mapped[str] = mapped_column(String(16), primary_key=True)


class ExerciseEquipment(Base):
    __tablename__ = "exercise_equipment"
    __table_args__ = (
        CheckConstraint(
            "requirement_code IN ('REQUIRED')",
            name="ck_exercise_equipment_requirement_code",
        ),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        primary_key=True,
    )
    equipment_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("equipment.code"), primary_key=True
    )
    requirement_code: Mapped[str] = mapped_column(String(16), primary_key=True)


class ExerciseLocation(Base):
    __tablename__ = "exercise_locations"

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        primary_key=True,
    )
    location_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("locations.code"), primary_key=True
    )


class ExerciseGoalTagLink(Base):
    __tablename__ = "exercise_goal_tag_links"
    __table_args__ = (
        CheckConstraint(
            "role_eligibility_code IN ('CORE', 'SUPPORT', 'OPTIONAL')",
            name="ck_exercise_goal_tag_links_role",
        ),
        CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_goal_tag_links_review",
        ),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True
    )
    goal_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_eligibility_code: Mapped[str] = mapped_column(String(16), nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExercisePrescriptionProfile(Base):
    __tablename__ = "exercise_prescription_profiles"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id",
            "goal_code",
            "experience_level_code",
            "phase_code",
            name="uq_exercise_prescription_profile",
        ),
        CheckConstraint(
            "phase_code IN ('WARMUP', 'MAIN', 'COOLDOWN')",
            name="ck_exercise_prescription_profiles_phase",
        ),
        CheckConstraint("sets > 0", name="ck_exercise_prescription_profiles_sets"),
        CheckConstraint(
            "(reps > 0 AND work_seconds_per_set IS NULL) OR "
            "(reps IS NULL AND work_seconds_per_set > 0)",
            name="ck_exercise_prescription_profiles_timing",
        ),
        CheckConstraint(
            "rest_seconds_per_set >= 0",
            name="ck_exercise_prescription_profiles_rest",
        ),
        CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_prescription_profiles_review",
        ),
        Index(
            "ix_exercise_prescriptions_lookup",
            "goal_code",
            "experience_level_code",
            "phase_code",
            "review_status_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    exercise_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )
    goal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    experience_level_code: Mapped[str] = mapped_column(String(64), nullable=False)
    phase_code: Mapped[str] = mapped_column(String(16), nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_seconds_per_set: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds_per_set: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity_code: Mapped[str] = mapped_column(String(32), nullable=False)
    prescription_version: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExerciseSafetyRule(Base):
    __tablename__ = "exercise_safety_rules"
    __table_args__ = (
        CheckConstraint(
            "(exercise_id IS NOT NULL AND movement_pattern_code IS NULL) OR "
            "(exercise_id IS NULL AND movement_pattern_code IS NOT NULL)",
            name="ck_exercise_safety_rules_exact_target",
        ),
        CheckConstraint(
            "body_part_role_code IN ('PRIMARY', 'SECONDARY')",
            name="ck_exercise_safety_rules_body_part_role",
        ),
        CheckConstraint(
            "minimum_severity_code IN ('MILD', 'MODERATE', 'SEVERE') AND "
            "maximum_severity_code IN ('MILD', 'MODERATE', 'SEVERE')",
            name="ck_exercise_safety_rules_severity",
        ),
        CheckConstraint(
            "effect_code IN ('EXCLUDE', 'CAUTION')",
            name="ck_exercise_safety_rules_effect",
        ),
        CheckConstraint(
            "reason_code IN ('DIRECT_JOINT_LOAD', 'STABILIZER_LOAD')",
            name="ck_exercise_safety_rules_reason",
        ),
        CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_safety_rules_review",
        ),
        CheckConstraint(
            "production_eligible = false OR review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_safety_rules_production_approval",
        ),
        CheckConstraint(
            "source_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_exercise_safety_rules_manifest_hash",
        ),
        Index(
            "uq_exercise_safety_rules_exercise_scope",
            "rule_set_version_code",
            "catalog_version_id",
            "exercise_id",
            "body_area_code",
            "minimum_severity_code",
            "maximum_severity_code",
            "effect_code",
            unique=True,
            postgresql_where=text("exercise_id IS NOT NULL"),
        ),
        Index(
            "uq_exercise_safety_rules_pattern_scope",
            "rule_set_version_code",
            "catalog_version_id",
            "movement_pattern_code",
            "body_area_code",
            "minimum_severity_code",
            "maximum_severity_code",
            "effect_code",
            unique=True,
            postgresql_where=text("movement_pattern_code IS NOT NULL"),
        ),
        Index(
            "ix_exercise_safety_rules_lookup",
            "body_area_code",
            "minimum_severity_code",
            "review_status_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalog_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_versions.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=True
    )
    movement_pattern_code: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("movement_patterns.code"), nullable=True
    )
    body_area_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("body_areas.code"), nullable=False
    )
    body_part_role_code: Mapped[str] = mapped_column(String(16), nullable=False)
    minimum_severity_code: Mapped[str] = mapped_column(String(16), nullable=False)
    maximum_severity_code: Mapped[str] = mapped_column(String(16), nullable=False)
    effect_code: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_set_version_code: Mapped[str] = mapped_column(String(120), nullable=False)
    production_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ExerciseAlternative(Base):
    __tablename__ = "exercise_alternatives"
    __table_args__ = (
        UniqueConstraint(
            "alternative_set_version_code",
            "source_exercise_id",
            "alternative_exercise_id",
            "reason_code",
            "goal_preservation_code",
            "rule_version",
            "condition_code",
            "pain_discomfort_area_code",
            name="uq_exercise_alternatives_relation",
        ),
        CheckConstraint(
            "source_exercise_id <> alternative_exercise_id",
            name="ck_exercise_alternatives_distinct_exercises",
        ),
        CheckConstraint(
            "reason_code IN ('DIFFICULTY', 'EQUIPMENT', 'LOCATION', 'DISCOMFORT')",
            name="ck_exercise_alternatives_reason",
        ),
        CheckConstraint(
            "difficulty_delta IN (-1, 0)",
            name="ck_exercise_alternatives_difficulty_delta",
        ),
        CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_alternatives_review",
        ),
        CheckConstraint(
            "production_eligible = false OR review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_alternatives_production_approval",
        ),
        CheckConstraint(
            "source_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_exercise_alternatives_manifest_hash",
        ),
        Index(
            "ix_exercise_alternatives_discomfort_lookup",
            "source_exercise_id",
            "pain_discomfort_area_code",
            "condition_code",
            "review_status_code",
        ),
        Index("ix_exercise_alternatives_source", "source_exercise_id", "review_status_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_exercise_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )
    alternative_exercise_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    goal_preservation_code: Mapped[str] = mapped_column(String(80), nullable=False)
    difficulty_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status_code: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    alternative_set_version_code: Mapped[str] = mapped_column(String(120), nullable=False)
    production_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    pain_discomfort_area_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service_action_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_strategy_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
