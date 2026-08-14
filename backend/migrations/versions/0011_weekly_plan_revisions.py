"""Add weekly plan revisions and finalize state.

Revision ID: 0011_weekly_plan_revisions
Revises: 0010_weekly_report_flow
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_weekly_plan_revisions"
down_revision: str | None = "0010_weekly_report_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
        "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
        "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK',"
        "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT',"
        "'POST_WEEKLY_PLAN','POST_WEEKLY_PLAN_REVISION')",
    )
    op.create_table(
        "weekly_plan_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_user_week_id", sa.Uuid(), nullable=False),
        sa.Column("source_weekly_report_id", sa.Uuid(), nullable=True),
        sa.Column("revision_sequence", sa.Integer(), nullable=False),
        sa.Column("ai_revision_number", sa.Integer(), nullable=True),
        sa.Column("revision_source_code", sa.String(16), nullable=False),
        sa.Column("routine_id", sa.Uuid(), nullable=True),
        sa.Column("selected_location_code", sa.String(64), nullable=True),
        sa.Column("safety_status_code", sa.String(16), nullable=False),
        sa.Column("input_schema_version", sa.String(48), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("weekly_plan_policy_version", sa.String(48), nullable=False),
        sa.Column("revision_reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("finalization_reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_sequence > 0", name="ck_weekly_plan_revisions_sequence"),
        sa.CheckConstraint(
            "(revision_source_code = 'AI' AND "
            "((safety_status_code IN ('PASS','REVISE') AND ai_revision_number IN (1, 2)) OR "
            "(safety_status_code IN ('NEEDS_INPUT','BLOCKED','FAILED') "
            "AND ai_revision_number IS NULL))) OR "
            "(revision_source_code IN ('INITIAL', 'USER') AND ai_revision_number IS NULL)",
            name="ck_weekly_plan_revisions_source_ai_number",
        ),
        sa.CheckConstraint(
            "safety_status_code IN ('PASS','NEEDS_INPUT','REVISE','BLOCKED','FAILED')",
            name="ck_weekly_plan_revisions_safety_status",
        ),
        sa.CheckConstraint(
            "(safety_status_code IN ('PASS','REVISE') AND routine_id IS NOT NULL "
            "AND selected_location_code IS NOT NULL) OR "
            "(safety_status_code IN ('NEEDS_INPUT','BLOCKED','FAILED') AND routine_id IS NULL "
            "AND selected_location_code IS NULL)",
            name="ck_weekly_plan_revisions_routine_status",
        ),
        sa.CheckConstraint(
            "finalized_at IS NULL OR "
            "(routine_id IS NOT NULL AND safety_status_code IN ('PASS','REVISE'))",
            name="ck_weekly_plan_revisions_finalize",
        ),
        sa.CheckConstraint("length(input_hash) = 64", name="ck_weekly_plan_revisions_input_hash"),
        sa.ForeignKeyConstraint(["target_user_week_id"], ["user_weeks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_weekly_report_id"], ["weekly_reports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_user_week_id",
            "revision_sequence",
            name="uq_weekly_plan_revisions_week_sequence",
        ),
        sa.UniqueConstraint(
            "target_user_week_id",
            "ai_revision_number",
            name="uq_weekly_plan_revisions_week_ai_number",
        ),
    )
    op.create_index(
        "uq_weekly_plan_revisions_initial",
        "weekly_plan_revisions",
        ["target_user_week_id"],
        unique=True,
        postgresql_where=sa.text("revision_source_code = 'INITIAL'"),
    )
    op.create_index(
        "ix_weekly_plan_revisions_week_created",
        "weekly_plan_revisions",
        ["target_user_week_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_weekly_plan_revisions_week_created", table_name="weekly_plan_revisions")
    op.drop_index("uq_weekly_plan_revisions_initial", table_name="weekly_plan_revisions")
    op.drop_table("weekly_plan_revisions")
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute(
        "DELETE FROM mutation_idempotency_records WHERE endpoint_code IN ("
        "'POST_WEEKLY_PLAN','POST_WEEKLY_PLAN_REVISION')"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
        "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
        "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK',"
        "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT')",
    )
