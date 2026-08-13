"""Add onboarding profile, consent, and mutation idempotency storage.

Revision ID: 0004_onboarding_consent
Revises: 0003_identity_auth_boundary
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_onboarding_consent"
down_revision: str | None = "0003_identity_auth_boundary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("protected_birthdate", sa.String(length=1024), nullable=False),
        sa.Column("nickname", sa.String(length=64), nullable=False),
        sa.Column("primary_goal_code", sa.String(length=64), nullable=False),
        sa.Column("experience_level_code", sa.String(length=64), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("preferred_location_code", sa.String(length=64), nullable=False),
        sa.Column("default_requested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("desired_weekly_workout_count", sa.Integer(), nullable=False),
        sa.Column("coaching_style_code", sa.String(length=32), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("sex_code", sa.String(length=32), nullable=True),
        sa.Column("code_set_version", sa.String(length=32), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
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
            "code_set_version = 'profile-mvp-v1'", name="ck_user_profiles_code_set_version"
        ),
        sa.CheckConstraint(
            "default_requested_duration_minutes > 0",
            name="ck_user_profiles_requested_duration_positive",
        ),
        sa.CheckConstraint(
            "desired_weekly_workout_count BETWEEN 1 AND 7", name="ck_user_profiles_weekly_count"
        ),
        sa.CheckConstraint(
            "coaching_style_code IN ('SUPPORTIVE', 'CONCISE', 'ENERGETIC')",
            name="ck_user_profiles_coaching_style",
        ),
        sa.CheckConstraint("profile_version > 0", name="ck_user_profiles_version_positive"),
        sa.ForeignKeyConstraint(
            ["preferred_location_code"],
            ["locations.code"],
            name="fk_user_profiles_preferred_location_code_locations",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_profiles_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_profiles"),
    )
    op.create_table(
        "user_equipment",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["equipment_code"],
            ["equipment.code"],
            name="fk_user_equipment_equipment_code_equipment",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_equipment_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "equipment_code", name="pk_user_equipment"),
    )
    op.create_table(
        "user_attention_areas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["body_area_code"],
            ["body_areas.code"],
            name="fk_user_attention_areas_body_area_code_body_areas",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_attention_areas_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_attention_areas"),
        sa.UniqueConstraint("user_id", "body_area_code", name="uq_user_attention_area"),
    )
    op.create_index("ix_user_attention_areas_user_id", "user_attention_areas", ["user_id"])
    op.create_table(
        "user_preferred_exercise_types",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_type_code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_type_code"],
            ["training_types.code"],
            name="fk_user_pref_types_type_training_types",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_preferred_exercise_types_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "exercise_type_code", name="pk_user_preferred_exercise_types"
        ),
    )
    op.create_table(
        "user_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("consent_type_code", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_consents_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_consents"),
        sa.CheckConstraint(
            "consent_type_code IN ('GENERAL_PERSONAL_DATA', 'SENSITIVE_DATA', "
            "'WEARABLE_INTEGRATION', 'CALENDAR_INTEGRATION', 'MARKETING')",
            name="ck_user_consents_type",
        ),
        sa.UniqueConstraint("user_id", "consent_type_code", name="uq_user_consent_type"),
    )
    op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"])
    op.create_table(
        "user_consent_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("consent_type_code", sa.String(length=64), nullable=False),
        sa.Column("event_code", sa.String(length=16), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_consent_events_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_consent_events"),
        sa.CheckConstraint(
            "consent_type_code IN ('GENERAL_PERSONAL_DATA', 'SENSITIVE_DATA', "
            "'WEARABLE_INTEGRATION', 'CALENDAR_INTEGRATION', 'MARKETING')",
            name="ck_user_consent_events_type",
        ),
        sa.CheckConstraint(
            "event_code IN ('GRANTED', 'REVOKED')",
            name="ck_user_consent_events_event",
        ),
    )
    op.create_index("ix_user_consent_events_user_id", "user_consent_events", ["user_id"])
    op.create_table(
        "mutation_idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_code", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_mutation_idempotency_records_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mutation_idempotency_records"),
        sa.CheckConstraint(
            "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS')",
            name="ck_mutation_idempotency_endpoint",
        ),
        sa.UniqueConstraint(
            "user_id", "endpoint_code", "idempotency_key", name="uq_mutation_idempotency_scope"
        ),
    )
    op.create_index(
        "ix_mutation_idempotency_records_user_id", "mutation_idempotency_records", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mutation_idempotency_records_user_id", table_name="mutation_idempotency_records"
    )
    op.drop_table("mutation_idempotency_records")
    op.drop_index("ix_user_consent_events_user_id", table_name="user_consent_events")
    op.drop_table("user_consent_events")
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_table("user_consents")
    op.drop_table("user_preferred_exercise_types")
    op.drop_index("ix_user_attention_areas_user_id", table_name="user_attention_areas")
    op.drop_table("user_attention_areas")
    op.drop_table("user_equipment")
    op.drop_table("user_profiles")
