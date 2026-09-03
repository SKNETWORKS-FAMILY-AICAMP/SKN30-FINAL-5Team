"""Add P1-B Daily Check-in safety and recovery persistence.

Revision ID: 0036_checkin_safety_recovery
Revises: 0035_onboarding_eligibility
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_checkin_safety_recovery"
down_revision = "0035_onboarding_eligibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_contexts", sa.Column("sleep_source_code", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "daily_contexts", sa.Column("available_time_minutes", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "daily_contexts",
        sa.Column("pain_present", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "daily_contexts",
        sa.Column("red_flag_present", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_daily_contexts_sleep_source",
        "daily_contexts",
        "sleep_source_code IS NULL OR sleep_source_code IN ('MANUAL', 'WEARABLE')",
    )
    op.create_check_constraint(
        "ck_daily_contexts_available_time",
        "daily_contexts",
        "available_time_minutes IS NULL OR available_time_minutes BETWEEN 10 AND 60",
    )
    op.create_table(
        "daily_context_pains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("daily_context_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(length=64), nullable=False),
        sa.Column("intensity_score", sa.SmallInteger(), nullable=False),
        sa.Column("severity_code", sa.String(length=16), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "intensity_score BETWEEN 1 AND 10", name="ck_daily_context_pain_intensity"
        ),
        sa.CheckConstraint(
            "severity_code IN ('MILD', 'MODERATE', 'SEVERE')",
            name="ck_daily_context_pain_severity",
        ),
        sa.ForeignKeyConstraint(["daily_context_id"], ["daily_contexts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["body_area_code"], ["body_areas.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "daily_context_id", "body_area_code", name="uq_daily_context_pain_body"
        ),
    )
    op.create_index(
        "ix_daily_context_pains_daily_context_id", "daily_context_pains", ["daily_context_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_daily_context_pains_daily_context_id", table_name="daily_context_pains")
    op.drop_table("daily_context_pains")
    op.drop_constraint("ck_daily_contexts_available_time", "daily_contexts", type_="check")
    op.drop_constraint("ck_daily_contexts_sleep_source", "daily_contexts", type_="check")
    op.drop_column("daily_contexts", "red_flag_present")
    op.drop_column("daily_contexts", "pain_present")
    op.drop_column("daily_contexts", "available_time_minutes")
    op.drop_column("daily_contexts", "sleep_source_code")
