"""Add request-driven weekly reports and acknowledgement.

Revision ID: 0010_weekly_report_flow
Revises: 0009_workout_session_outcomes
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_weekly_report_flow"
down_revision: str | None = "0009_workout_session_outcomes"
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
        "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT')",
    )
    op.create_table(
        "user_weeks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("week_start_local_date", sa.Date(), nullable=False),
        sa.Column("week_end_local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("target_workout_count", sa.Integer(), nullable=False),
        sa.Column("plan_origin_code", sa.String(24), nullable=False),
        sa.Column("cold_start_applied", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_workout_count BETWEEN 1 AND 7", name="ck_user_weeks_target_count"
        ),
        sa.CheckConstraint(
            "plan_origin_code IN ('COLD_START','WEEKLY_REPORT')",
            name="ck_user_weeks_plan_origin",
        ),
        sa.CheckConstraint("status_code IN ('OPEN','CLOSED')", name="ck_user_weeks_status"),
        sa.CheckConstraint(
            "(status_code = 'OPEN' AND closed_at IS NULL) OR "
            "(status_code = 'CLOSED' AND closed_at IS NOT NULL)",
            name="ck_user_weeks_closed_at",
        ),
        sa.CheckConstraint(
            "(plan_origin_code = 'COLD_START' AND cold_start_applied) OR "
            "(plan_origin_code = 'WEEKLY_REPORT' AND NOT cold_start_applied)",
            name="ck_user_weeks_cold_start",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start_local_date", name="uq_user_weeks_user_start"),
    )
    op.create_index(
        "ix_user_weeks_user_status_start",
        "user_weeks",
        ["user_id", "status_code", "week_start_local_date"],
    )
    op.create_table(
        "weekly_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_week_id", sa.Uuid(), nullable=False),
        sa.Column("status_code", sa.String(24), nullable=False),
        sa.Column("input_schema_version", sa.String(48), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("not_completed_count", sa.Integer(), nullable=False),
        sa.Column("stopped_for_safety", sa.Integer(), nullable=False),
        sa.Column("primary_miss_reason_code", sa.String(48), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=False),
        sa.Column("persistence_rate", sa.Float(), nullable=False),
        sa.Column("negotiation_success_rate", sa.Float(), nullable=True),
        sa.Column("weekday_failure_summary", postgresql.JSONB(), nullable=False),
        sa.Column("high_completion_windows", postgresql.JSONB(), nullable=False),
        sa.Column("pattern_summary", postgresql.JSONB(), nullable=False),
        sa.Column("decision_summary", sa.String(500), nullable=False),
        sa.Column("adjustment_direction_code", sa.String(16), nullable=False),
        sa.Column("next_action", sa.String(500), nullable=False),
        sa.Column("agent_summaries", postgresql.JSONB(), nullable=True),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("report_policy_version", sa.String(48), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status_code IN ('GENERATED','ACKNOWLEDGED','FAILED')",
            name="ck_weekly_reports_status",
        ),
        sa.CheckConstraint(
            "adjustment_direction_code IN ('MAINTAIN','REDUCE','INCREASE','MIXED')",
            name="ck_weekly_reports_adjustment_direction",
        ),
        sa.CheckConstraint(
            "completed_count >= 0 AND partial_count >= 0 AND not_completed_count >= 0 "
            "AND stopped_for_safety >= 0",
            name="ck_weekly_reports_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "completion_rate BETWEEN 0 AND 1", name="ck_weekly_reports_completion_rate"
        ),
        sa.CheckConstraint(
            "persistence_rate BETWEEN 0 AND 1", name="ck_weekly_reports_persistence_rate"
        ),
        sa.CheckConstraint(
            "negotiation_success_rate IS NULL OR negotiation_success_rate BETWEEN 0 AND 1",
            name="ck_weekly_reports_negotiation_rate",
        ),
        sa.CheckConstraint(
            "(status_code = 'ACKNOWLEDGED' AND acknowledged_at IS NOT NULL) OR "
            "(status_code IN ('GENERATED','FAILED') AND acknowledged_at IS NULL)",
            name="ck_weekly_reports_acknowledged_at",
        ),
        sa.ForeignKeyConstraint(["user_week_id"], ["user_weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_week_id"),
        sa.UniqueConstraint("user_week_id", "input_hash", name="uq_weekly_reports_week_hash"),
    )
    op.create_index(
        "ix_weekly_reports_user_week_status",
        "weekly_reports",
        ["user_week_id", "status_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_weekly_reports_user_week_status", table_name="weekly_reports")
    op.drop_table("weekly_reports")
    op.drop_index("ix_user_weeks_user_status_start", table_name="user_weeks")
    op.drop_table("user_weeks")
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute(
        "DELETE FROM mutation_idempotency_records WHERE endpoint_code IN ("
        "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT')"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
        "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
        "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK')",
    )
