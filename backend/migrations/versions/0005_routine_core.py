"""Add production-approved versioned routine persistence.

Revision ID: 0005_routine_core
Revises: 0004_onboarding_consent
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_routine_core"
down_revision: str | None = "0004_onboarding_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_catalog_versions_status_code", "catalog_versions", type_="check")
    op.drop_constraint("ck_catalog_versions_review_method_code", "catalog_versions", type_="check")
    op.drop_constraint(
        "ck_catalog_versions_status_interpretation_code",
        "catalog_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_catalog_versions_production_ineligible",
        "catalog_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_versions_status_code",
        "catalog_versions",
        "status_code IN ('DRAFT', 'ACTIVE', 'DEPRECATED')",
    )
    op.create_check_constraint(
        "ck_catalog_versions_review_method_code",
        "catalog_versions",
        "review_method_code IN ('AGENT_ONLY', 'DOMAIN_REVIEWER')",
    )
    op.create_check_constraint(
        "ck_catalog_versions_status_interpretation_code",
        "catalog_versions",
        "status_interpretation_code IN ('PIPELINE_COMPATIBILITY_ONLY', 'PRODUCTION_APPROVED')",
    )
    op.create_check_constraint(
        "ck_catalog_versions_production_approval",
        "catalog_versions",
        "production_eligible = false OR "
        "(status_code = 'ACTIVE' AND review_status_code = 'DOMAIN_APPROVED' "
        "AND review_method_code = 'DOMAIN_REVIEWER' "
        "AND status_interpretation_code = 'PRODUCTION_APPROVED' "
        "AND activated_at IS NOT NULL)",
    )
    op.create_index(
        "uq_catalog_versions_single_active",
        "catalog_versions",
        ["status_code"],
        unique=True,
        postgresql_where=sa.text("status_code = 'ACTIVE'"),
    )

    op.create_table(
        "user_available_locations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["location_code"],
            ["locations.code"],
            name="fk_user_available_locations_location_code_locations",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_available_locations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "location_code", name="pk_user_available_locations"),
    )
    op.execute(
        "INSERT INTO user_available_locations (user_id, location_code) "
        "SELECT user_id, preferred_location_code FROM user_profiles"
    )

    op.create_table(
        "exercise_goal_tag_links",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("goal_code", sa.String(length=64), nullable=False),
        sa.Column("role_eligibility_code", sa.String(length=16), nullable=False),
        sa.Column("review_status_code", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role_eligibility_code IN ('CORE', 'SUPPORT', 'OPTIONAL')",
            name="ck_exercise_goal_tag_links_role",
        ),
        sa.CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_goal_tag_links_review",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_exercise_goal_tag_links_exercise_id_exercises",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("exercise_id", "goal_code", name="pk_exercise_goal_tag_links"),
    )
    op.create_table(
        "exercise_prescription_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("goal_code", sa.String(length=64), nullable=False),
        sa.Column("experience_level_code", sa.String(length=64), nullable=False),
        sa.Column("phase_code", sa.String(length=16), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("work_seconds_per_set", sa.Integer(), nullable=True),
        sa.Column("rest_seconds_per_set", sa.Integer(), nullable=False),
        sa.Column("intensity_code", sa.String(length=32), nullable=False),
        sa.Column("prescription_version", sa.String(length=64), nullable=False),
        sa.Column("review_status_code", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "phase_code IN ('WARMUP', 'MAIN', 'COOLDOWN')",
            name="ck_exercise_prescription_profiles_phase",
        ),
        sa.CheckConstraint(
            "rest_seconds_per_set >= 0",
            name="ck_exercise_prescription_profiles_rest",
        ),
        sa.CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_prescription_profiles_review",
        ),
        sa.CheckConstraint("sets > 0", name="ck_exercise_prescription_profiles_sets"),
        sa.CheckConstraint(
            "(reps > 0 AND work_seconds_per_set IS NULL) OR "
            "(reps IS NULL AND work_seconds_per_set > 0)",
            name="ck_exercise_prescription_profiles_timing",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_exercise_prescription_profiles_exercise_id_exercises",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exercise_prescription_profiles"),
        sa.UniqueConstraint(
            "exercise_id",
            "goal_code",
            "experience_level_code",
            "phase_code",
            name="uq_exercise_prescription_profile",
        ),
    )
    op.create_index(
        "ix_exercise_prescriptions_lookup",
        "exercise_prescription_profiles",
        ["goal_code", "experience_level_code", "phase_code", "review_status_code"],
    )

    op.create_table(
        "routines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("goal_code", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.String(length=16), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_routines_effective_period",
        ),
        sa.CheckConstraint(
            "status_code IN ('DRAFT', 'ACTIVE', 'ARCHIVED')",
            name="ck_routines_status_code",
        ),
        sa.CheckConstraint("version > 0", name="ck_routines_version_positive"),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"],
            ["catalog_versions.id"],
            name="fk_routines_catalog_version_id_catalog_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_routines_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_routines"),
        sa.UniqueConstraint("user_id", "version", name="uq_routines_user_version"),
    )
    op.create_index(
        "ix_routines_user_status_effective",
        "routines",
        ["user_id", "status_code", "effective_from"],
    )
    op.create_table(
        "routine_days",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("routine_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("schedule_rule", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("training_type_code", sa.String(length=64), nullable=False),
        sa.Column("body_focus_code", sa.String(length=64), nullable=True),
        sa.Column("requested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("setup_seconds", sa.Integer(), nullable=False),
        sa.Column("estimated_calories_burned", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "estimated_duration_seconds = requested_duration_minutes * 60",
            name="ck_routine_days_exact_duration",
        ),
        sa.CheckConstraint(
            "requested_duration_minutes > 0",
            name="ck_routine_days_requested_duration_positive",
        ),
        sa.CheckConstraint("schedule_rule = 'ROTATION'", name="ck_routine_days_schedule_rule"),
        sa.CheckConstraint("sequence > 0", name="ck_routine_days_sequence_positive"),
        sa.CheckConstraint("setup_seconds BETWEEN 0 AND 60", name="ck_routine_days_setup"),
        sa.ForeignKeyConstraint(
            ["body_focus_code"],
            ["body_focuses.code"],
            name="fk_routine_days_body_focus_code_body_focuses",
        ),
        sa.ForeignKeyConstraint(
            ["routine_id"],
            ["routines.id"],
            name="fk_routine_days_routine_id_routines",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["training_type_code"],
            ["training_types.code"],
            name="fk_routine_days_training_type_code_training_types",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_routine_days"),
        sa.UniqueConstraint("routine_id", "sequence", name="uq_routine_days_sequence"),
    )
    op.create_table(
        "routine_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("routine_day_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase_code", sa.String(length=16), nullable=False),
        sa.Column("tier_code", sa.String(length=16), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("work_seconds_per_set", sa.Integer(), nullable=True),
        sa.Column("rest_seconds_per_set", sa.Integer(), nullable=False),
        sa.Column("intensity_code", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "phase_code IN ('WARMUP', 'MAIN', 'COOLDOWN')",
            name="ck_routine_items_phase_code",
        ),
        sa.CheckConstraint("rest_seconds_per_set >= 0", name="ck_routine_items_rest"),
        sa.CheckConstraint("sequence > 0", name="ck_routine_items_sequence_positive"),
        sa.CheckConstraint("sets > 0", name="ck_routine_items_sets_positive"),
        sa.CheckConstraint(
            "tier_code IN ('CORE', 'SUPPORT', 'OPTIONAL')",
            name="ck_routine_items_tier_code",
        ),
        sa.CheckConstraint(
            "(reps > 0 AND work_seconds_per_set IS NULL) OR "
            "(reps IS NULL AND work_seconds_per_set > 0)",
            name="ck_routine_items_timing",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_routine_items_exercise_id_exercises",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["routine_day_id"],
            ["routine_days.id"],
            name="fk_routine_items_routine_day_id_routine_days",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_routine_items"),
        sa.UniqueConstraint("routine_day_id", "sequence", name="uq_routine_items_sequence"),
    )
    op.create_index(
        "ix_routine_items_day_phase_sequence",
        "routine_items",
        ["routine_day_id", "phase_code", "sequence"],
    )

    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS', 'POST_ROUTINES')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.execute("DELETE FROM mutation_idempotency_records WHERE endpoint_code = 'POST_ROUTINES'")
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS')",
    )
    op.drop_index("ix_routine_items_day_phase_sequence", table_name="routine_items")
    op.drop_table("routine_items")
    op.drop_table("routine_days")
    op.drop_index("ix_routines_user_status_effective", table_name="routines")
    op.drop_table("routines")
    op.drop_index(
        "ix_exercise_prescriptions_lookup",
        table_name="exercise_prescription_profiles",
    )
    op.drop_table("exercise_prescription_profiles")
    op.drop_table("exercise_goal_tag_links")
    op.drop_table("user_available_locations")

    op.execute(
        "UPDATE catalog_versions SET status_code = 'DRAFT', production_eligible = false, "
        "review_method_code = 'AGENT_ONLY', "
        "status_interpretation_code = 'PIPELINE_COMPATIBILITY_ONLY', activated_at = NULL"
    )
    op.drop_index("uq_catalog_versions_single_active", table_name="catalog_versions")
    op.drop_constraint("ck_catalog_versions_production_approval", "catalog_versions", type_="check")
    op.drop_constraint(
        "ck_catalog_versions_status_interpretation_code",
        "catalog_versions",
        type_="check",
    )
    op.drop_constraint("ck_catalog_versions_review_method_code", "catalog_versions", type_="check")
    op.drop_constraint("ck_catalog_versions_status_code", "catalog_versions", type_="check")
    op.create_check_constraint(
        "ck_catalog_versions_production_ineligible",
        "catalog_versions",
        "production_eligible = false",
    )
    op.create_check_constraint(
        "ck_catalog_versions_status_interpretation_code",
        "catalog_versions",
        "status_interpretation_code IN ('PIPELINE_COMPATIBILITY_ONLY')",
    )
    op.create_check_constraint(
        "ck_catalog_versions_review_method_code",
        "catalog_versions",
        "review_method_code IN ('AGENT_ONLY')",
    )
    op.create_check_constraint(
        "ck_catalog_versions_status_code",
        "catalog_versions",
        "status_code IN ('DRAFT')",
    )
