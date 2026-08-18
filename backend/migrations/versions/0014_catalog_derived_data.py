"""Add DRAFT exercise safety rules and alternatives.

Revision ID: 0014_catalog_derived_data
Revises: 0013_calendar_persistence
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_catalog_derived_data"
down_revision: str | None = "0013_calendar_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercise_safety_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=True),
        sa.Column("movement_pattern_code", sa.String(length=64), nullable=True),
        sa.Column("body_area_code", sa.String(length=64), nullable=False),
        sa.Column("body_part_role_code", sa.String(length=16), nullable=False),
        sa.Column("minimum_severity_code", sa.String(length=16), nullable=False),
        sa.Column("maximum_severity_code", sa.String(length=16), nullable=False),
        sa.Column("effect_code", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("review_status_code", sa.String(length=32), nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("rule_set_version_code", sa.String(length=120), nullable=False),
        sa.Column("production_eligible", sa.Boolean(), nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            "(exercise_id IS NOT NULL AND movement_pattern_code IS NULL) OR "
            "(exercise_id IS NULL AND movement_pattern_code IS NOT NULL)",
            name="ck_exercise_safety_rules_exact_target",
        ),
        sa.CheckConstraint(
            "body_part_role_code IN ('PRIMARY', 'SECONDARY')",
            name="ck_exercise_safety_rules_body_part_role",
        ),
        sa.CheckConstraint(
            "minimum_severity_code IN ('MILD', 'MODERATE', 'SEVERE') AND "
            "maximum_severity_code IN ('MILD', 'MODERATE', 'SEVERE')",
            name="ck_exercise_safety_rules_severity",
        ),
        sa.CheckConstraint(
            "effect_code IN ('EXCLUDE', 'CAUTION')",
            name="ck_exercise_safety_rules_effect",
        ),
        sa.CheckConstraint(
            "reason_code IN ('DIRECT_JOINT_LOAD', 'STABILIZER_LOAD')",
            name="ck_exercise_safety_rules_reason",
        ),
        sa.CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_safety_rules_review",
        ),
        sa.CheckConstraint(
            "production_eligible = false",
            name="ck_exercise_safety_rules_production_ineligible",
        ),
        sa.CheckConstraint(
            "source_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_exercise_safety_rules_manifest_hash",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"], ["catalog_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movement_pattern_code"], ["movement_patterns.code"]),
        sa.ForeignKeyConstraint(["body_area_code"], ["body_areas.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_exercise_safety_rules_exercise_scope",
        "exercise_safety_rules",
        [
            "rule_set_version_code",
            "catalog_version_id",
            "exercise_id",
            "body_area_code",
            "minimum_severity_code",
            "maximum_severity_code",
            "effect_code",
        ],
        unique=True,
        postgresql_where=sa.text("exercise_id IS NOT NULL"),
    )
    op.create_index(
        "uq_exercise_safety_rules_pattern_scope",
        "exercise_safety_rules",
        [
            "rule_set_version_code",
            "catalog_version_id",
            "movement_pattern_code",
            "body_area_code",
            "minimum_severity_code",
            "maximum_severity_code",
            "effect_code",
        ],
        unique=True,
        postgresql_where=sa.text("movement_pattern_code IS NOT NULL"),
    )
    op.create_index(
        "ix_exercise_safety_rules_lookup",
        "exercise_safety_rules",
        ["body_area_code", "minimum_severity_code", "review_status_code"],
    )

    op.create_table(
        "exercise_alternatives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_exercise_id", sa.Uuid(), nullable=False),
        sa.Column("alternative_exercise_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("goal_preservation_code", sa.String(length=80), nullable=False),
        sa.Column("difficulty_delta", sa.Integer(), nullable=False),
        sa.Column("review_status_code", sa.String(length=32), nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("alternative_set_version_code", sa.String(length=120), nullable=False),
        sa.Column("production_eligible", sa.Boolean(), nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_exercise_id <> alternative_exercise_id",
            name="ck_exercise_alternatives_distinct_exercises",
        ),
        sa.CheckConstraint(
            "reason_code IN ('DIFFICULTY', 'EQUIPMENT', 'LOCATION', 'DISCOMFORT')",
            name="ck_exercise_alternatives_reason",
        ),
        sa.CheckConstraint(
            "difficulty_delta IN (-1, 0)",
            name="ck_exercise_alternatives_difficulty_delta",
        ),
        sa.CheckConstraint(
            "review_status_code = 'DOMAIN_APPROVED'",
            name="ck_exercise_alternatives_review",
        ),
        sa.CheckConstraint(
            "production_eligible = false",
            name="ck_exercise_alternatives_production_ineligible",
        ),
        sa.CheckConstraint(
            "source_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_exercise_alternatives_manifest_hash",
        ),
        sa.ForeignKeyConstraint(["source_exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["alternative_exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alternative_set_version_code",
            "source_exercise_id",
            "alternative_exercise_id",
            "reason_code",
            "goal_preservation_code",
            "rule_version",
            name="uq_exercise_alternatives_relation",
        ),
    )
    op.create_index(
        "ix_exercise_alternatives_source",
        "exercise_alternatives",
        ["source_exercise_id", "review_status_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_exercise_alternatives_source", table_name="exercise_alternatives")
    op.drop_table("exercise_alternatives")
    op.drop_index("ix_exercise_safety_rules_lookup", table_name="exercise_safety_rules")
    op.drop_index("uq_exercise_safety_rules_pattern_scope", table_name="exercise_safety_rules")
    op.drop_index("uq_exercise_safety_rules_exercise_scope", table_name="exercise_safety_rules")
    op.drop_table("exercise_safety_rules")
