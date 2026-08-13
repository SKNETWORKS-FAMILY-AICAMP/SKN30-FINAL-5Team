"""Add DRAFT exercise catalog core tables.

Revision ID: 0002_catalog_core
Revises: 0001_backend_baseline
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_catalog_core"
down_revision: str | None = "0001_backend_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_lookup_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_set_version", sa.String(length=32), nullable=False),
        sa.Column("display_name_ko", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("code", name=f"pk_{name}"),
    )


def upgrade() -> None:
    for table_name in (
        "training_types",
        "body_focuses",
        "movement_patterns",
        "equipment",
        "locations",
        "body_areas",
    ):
        _create_lookup_table(table_name)

    op.create_table(
        "catalog_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_code", sa.String(length=120), nullable=False),
        sa.Column("status_code", sa.String(length=32), nullable=False),
        sa.Column("manifest_schema_version", sa.String(length=32), nullable=False),
        sa.Column("generator_version", sa.String(length=80), nullable=False),
        sa.Column("code_set_version", sa.String(length=32), nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("source_track_code", sa.String(length=32), nullable=False),
        sa.Column("review_status_code", sa.String(length=32), nullable=False),
        sa.Column("review_method_code", sa.String(length=32), nullable=False),
        sa.Column("status_interpretation_code", sa.String(length=64), nullable=False),
        sa.Column("production_eligible", sa.Boolean(), nullable=False),
        sa.Column("exercise_record_count", sa.Integer(), nullable=False),
        sa.Column("manifest_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status_code IN ('DRAFT')", name="ck_catalog_versions_status_code"),
        sa.CheckConstraint(
            "manifest_schema_version IN ('1.0')",
            name="ck_catalog_versions_manifest_schema_version",
        ),
        sa.CheckConstraint(
            "code_set_version IN ('mvp-v1')",
            name="ck_catalog_versions_code_set_version",
        ),
        sa.CheckConstraint(
            "source_track_code IN ('wger', 'kspo')",
            name="ck_catalog_versions_source_track_code",
        ),
        sa.CheckConstraint(
            "review_status_code IN ('DOMAIN_APPROVED')",
            name="ck_catalog_versions_review_status_code",
        ),
        sa.CheckConstraint(
            "review_method_code IN ('AGENT_ONLY')",
            name="ck_catalog_versions_review_method_code",
        ),
        sa.CheckConstraint(
            "status_interpretation_code IN ('PIPELINE_COMPATIBILITY_ONLY')",
            name="ck_catalog_versions_status_interpretation_code",
        ),
        sa.CheckConstraint(
            "production_eligible = false",
            name="ck_catalog_versions_production_ineligible",
        ),
        sa.CheckConstraint("exercise_record_count >= 0", name="ck_catalog_versions_record_count"),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_versions"),
        sa.UniqueConstraint("version_code", name="uq_catalog_versions_version_code"),
    )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("stable_code", sa.String(length=120), nullable=False),
        sa.Column("name_ko", sa.String(length=200), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=True),
        sa.Column("training_type_code", sa.String(length=64), nullable=False),
        sa.Column("body_focus_code", sa.String(length=64), nullable=False),
        sa.Column("primary_movement_pattern_code", sa.String(length=64), nullable=False),
        sa.Column("difficulty_code", sa.String(length=32), nullable=False),
        sa.Column("beginner_suitable", sa.Boolean(), nullable=False),
        sa.Column("timing_mode_code", sa.String(length=32), nullable=False),
        sa.Column("default_seconds_per_rep", sa.Integer(), nullable=True),
        sa.Column("default_work_seconds", sa.Integer(), nullable=True),
        sa.Column("default_rest_seconds", sa.Integer(), nullable=False),
        sa.Column("default_transition_seconds", sa.Integer(), nullable=False),
        sa.Column("recovery_eligible", sa.Boolean(), nullable=False),
        sa.Column("instruction_summary_ko", sa.Text(), nullable=False),
        sa.Column("form_cues_ko", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("instruction_content_version", sa.String(length=80), nullable=False),
        sa.Column("review_status_code", sa.String(length=32), nullable=False),
        sa.Column("source_track_code", sa.String(length=32), nullable=False),
        sa.Column("source_identity", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "difficulty_code IN ('BEGINNER', 'INTERMEDIATE')",
            name="ck_exercises_difficulty_code",
        ),
        sa.CheckConstraint(
            "timing_mode_code IN ('REPS', 'DURATION')",
            name="ck_exercises_timing_mode_code",
        ),
        sa.CheckConstraint(
            "review_status_code IN ('DOMAIN_APPROVED')",
            name="ck_exercises_review_status_code",
        ),
        sa.CheckConstraint(
            "source_track_code IN ('wger', 'kspo')",
            name="ck_exercises_source_track_code",
        ),
        sa.CheckConstraint("default_rest_seconds >= 0", name="ck_exercises_rest_seconds"),
        sa.CheckConstraint(
            "default_transition_seconds BETWEEN 10 AND 20",
            name="ck_exercises_transition_seconds",
        ),
        sa.CheckConstraint(
            "(timing_mode_code = 'REPS' AND default_seconds_per_rep > 0 "
            "AND default_work_seconds IS NULL) OR "
            "(timing_mode_code = 'DURATION' AND default_work_seconds > 0 "
            "AND default_seconds_per_rep IS NULL)",
            name="ck_exercises_timing_values",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"],
            ["catalog_versions.id"],
            name="fk_exercises_catalog_version_id_catalog_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["training_type_code"],
            ["training_types.code"],
            name="fk_exercises_training_type_code_training_types",
        ),
        sa.ForeignKeyConstraint(
            ["body_focus_code"],
            ["body_focuses.code"],
            name="fk_exercises_body_focus_code_body_focuses",
        ),
        sa.ForeignKeyConstraint(
            ["primary_movement_pattern_code"],
            ["movement_patterns.code"],
            name="fk_exercises_primary_movement_pattern_code_movement_patterns",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exercises"),
        sa.UniqueConstraint(
            "catalog_version_id",
            "stable_code",
            name="uq_exercises_catalog_version_stable_code",
        ),
    )
    op.create_index(
        "ix_exercises_catalog_review",
        "exercises",
        ["catalog_version_id", "review_status_code"],
        unique=False,
    )

    op.create_table(
        "exercise_body_parts",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(length=64), nullable=False),
        sa.Column("role_code", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role_code IN ('PRIMARY', 'SECONDARY')",
            name="ck_exercise_body_parts_role_code",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_exercise_body_parts_exercise_id_exercises",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["body_area_code"],
            ["body_areas.code"],
            name="fk_exercise_body_parts_body_area_code_body_areas",
        ),
        sa.PrimaryKeyConstraint(
            "exercise_id",
            "body_area_code",
            "role_code",
            name="pk_exercise_body_parts",
        ),
    )
    op.create_table(
        "exercise_equipment",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_code", sa.String(length=64), nullable=False),
        sa.Column("requirement_code", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "requirement_code IN ('REQUIRED')",
            name="ck_exercise_equipment_requirement_code",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_exercise_equipment_exercise_id_exercises",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["equipment_code"],
            ["equipment.code"],
            name="fk_exercise_equipment_equipment_code_equipment",
        ),
        sa.PrimaryKeyConstraint(
            "exercise_id",
            "equipment_code",
            "requirement_code",
            name="pk_exercise_equipment",
        ),
    )
    op.create_table(
        "exercise_locations",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_exercise_locations_exercise_id_exercises",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["location_code"],
            ["locations.code"],
            name="fk_exercise_locations_location_code_locations",
        ),
        sa.PrimaryKeyConstraint(
            "exercise_id",
            "location_code",
            name="pk_exercise_locations",
        ),
    )


def downgrade() -> None:
    op.drop_table("exercise_locations")
    op.drop_table("exercise_equipment")
    op.drop_table("exercise_body_parts")
    op.drop_index("ix_exercises_catalog_review", table_name="exercises")
    op.drop_table("exercises")
    op.drop_table("catalog_versions")
    for table_name in (
        "body_areas",
        "locations",
        "equipment",
        "movement_patterns",
        "body_focuses",
        "training_types",
    ):
        op.drop_table(table_name)
