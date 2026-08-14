"""Add versioned manual daily contexts.

Revision ID: 0006_daily_contexts
Revises: 0005_routine_core
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_daily_contexts"
down_revision: str | None = "0005_routine_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO body_areas (code, code_set_version, display_name_ko) "
        "VALUES ('GENERALIZED', 'mvp-v1', NULL), ('OTHER', 'mvp-v1', NULL) "
        "ON CONFLICT (code) DO NOTHING"
    )
    op.create_table(
        "daily_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("fatigue_level_code", sa.String(length=16), nullable=False),
        sa.Column("requested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("duration_adjustment_source_code", sa.String(length=32), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False),
        sa.Column("sleep_minutes", sa.Integer(), nullable=True),
        sa.Column("fasting_state_code", sa.String(length=32), nullable=True),
        sa.Column("hydration_state_code", sa.String(length=32), nullable=True),
        sa.Column("context_version", sa.Integer(), nullable=False),
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
            "duration_adjustment_source_code IN ('PROFILE', 'USER_OVERRIDE')",
            name="ck_daily_contexts_duration_source",
        ),
        sa.CheckConstraint(
            "requested_duration_minutes BETWEEN 1 AND 240",
            name="ck_daily_contexts_duration",
        ),
        sa.CheckConstraint(
            "fatigue_level_code IN ('LOW', 'MODERATE', 'HIGH')",
            name="ck_daily_contexts_fatigue",
        ),
        sa.CheckConstraint(
            "sleep_minutes IS NULL OR sleep_minutes BETWEEN 0 AND 1440",
            name="ck_daily_contexts_sleep_minutes",
        ),
        sa.CheckConstraint("context_version > 0", name="ck_daily_contexts_version"),
        sa.ForeignKeyConstraint(
            ["location_code"],
            ["locations.code"],
            name="fk_daily_contexts_location_code_locations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_daily_contexts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_contexts"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_daily_contexts_user_local_date"),
    )
    op.create_index("ix_daily_contexts_user_id", "daily_contexts", ["user_id"])
    op.create_table(
        "daily_context_discomforts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("daily_context_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(length=64), nullable=False),
        sa.Column("severity_code", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "severity_code IN ('MILD', 'MODERATE', 'SEVERE')",
            name="ck_daily_context_discomfort_severity",
        ),
        sa.ForeignKeyConstraint(
            ["body_area_code"],
            ["body_areas.code"],
            name="fk_daily_context_discomforts_body_area",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["daily_context_id"],
            ["daily_contexts.id"],
            name="fk_daily_context_discomforts_context",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_context_discomforts"),
        sa.UniqueConstraint(
            "daily_context_id", "body_area_code", name="uq_daily_context_discomfort_body"
        ),
    )
    op.create_table(
        "daily_context_adverse_reactions",
        sa.Column("daily_context_id", sa.Uuid(), nullable=False),
        sa.Column("reaction_code", sa.String(length=80), nullable=False),
        sa.CheckConstraint(
            "reaction_code IN ("
            "'CHEST_DISCOMFORT','UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH',"
            "'SEVERE_DIZZINESS','FAINTING','SUDDEN_WEAKNESS_OR_NUMBNESS',"
            "'RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS','SUDDEN_SEVERE_PAIN',"
            "'ACUTE_SWELLING_OR_DEFORMITY','CANNOT_BEAR_WEIGHT','OTHER_SERIOUS_REACTION')",
            name="ck_daily_context_adverse_reaction_code",
        ),
        sa.ForeignKeyConstraint(
            ["daily_context_id"],
            ["daily_contexts.id"],
            name="fk_daily_context_adverse_reactions_context",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "daily_context_id", "reaction_code", name="pk_daily_context_adverse_reactions"
        ),
    )
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS', "
        "'POST_ROUTINES', 'PUT_DAILY_CONTEXT')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute("DELETE FROM mutation_idempotency_records WHERE endpoint_code = 'PUT_DAILY_CONTEXT'")
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS', 'POST_ROUTINES')",
    )
    op.drop_table("daily_context_adverse_reactions")
    op.drop_table("daily_context_discomforts")
    op.drop_index("ix_daily_contexts_user_id", table_name="daily_contexts")
    op.drop_table("daily_contexts")
    op.execute("DELETE FROM body_areas WHERE code IN ('GENERALIZED', 'OTHER')")
