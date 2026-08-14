"""Add decision selection and workout session progression.

Revision ID: 0008_workout_session_flow
Revises: 0007_decision_persistence
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_workout_session_flow"
down_revision: str | None = "0007_decision_persistence"
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
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY')",
    )
    op.create_table(
        "scheduled_workouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("routine_day_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_local_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status_code IN ('SCHEDULED','STARTED','COMPLETED','PARTIAL',"
            "'NOT_COMPLETED','REST_SELECTED')",
            name="ck_scheduled_workouts_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["routine_day_id"], ["routine_days.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "scheduled_local_date",
            "routine_day_id",
            name="uq_scheduled_workouts_user_date_day",
        ),
    )
    op.create_index("ix_scheduled_workouts_user_id", "scheduled_workouts", ["user_id"])
    op.create_table(
        "decision_selections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("decision_option_id", sa.Uuid(), nullable=False),
        sa.Column("selected_action_code", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "selected_action_code IN ('KEEP','DOWNSHIFT','CHANGE','RECOVERY','REST')",
            name="ck_decision_selections_action",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_option_id"], ["decision_options.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_run_id"),
    )
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("decision_selection_id", sa.Uuid(), nullable=False),
        sa.Column("plan_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_workout_id", sa.Uuid(), nullable=True),
        sa.Column("status_code", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_elapsed_seconds", sa.Integer(), nullable=True),
        sa.Column("estimated_calories_burned", sa.Float(), nullable=True),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status_code IN ('PLANNED','IN_PROGRESS','COMPLETED','PARTIAL',"
            "'NOT_COMPLETED','STOPPED_FOR_SAFETY')",
            name="ck_workout_sessions_status",
        ),
        sa.CheckConstraint(
            "actual_elapsed_seconds IS NULL OR actual_elapsed_seconds >= 0",
            name="ck_workout_sessions_elapsed_nonnegative",
        ),
        sa.CheckConstraint(
            "estimated_calories_burned IS NULL OR estimated_calories_burned >= 0",
            name="ck_workout_sessions_calories_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_selection_id"], ["decision_selections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["plan_candidate_id"], ["plan_candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["scheduled_workout_id"], ["scheduled_workouts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_selection_id"),
    )
    op.create_index("ix_workout_sessions_user_id", "workout_sessions", ["user_id"])
    op.create_index(
        "ix_workout_sessions_user_ended_status",
        "workout_sessions",
        ["user_id", "ended_at", "status_code"],
    )
    op.create_table(
        "workout_session_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("plan_item_id", sa.Uuid(), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status_code IN ('PENDING','COMPLETED')",
            name="ck_workout_session_items_status",
        ),
        sa.CheckConstraint(
            "(status_code = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status_code = 'PENDING' AND completed_at IS NULL)",
            name="ck_workout_session_items_completed_at",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["plan_item_id"], ["plan_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_session_id", "plan_item_id", name="uq_workout_session_items_session_plan"
        ),
    )
    op.create_table(
        "workout_timer_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("event_code", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_code IN ('START','PAUSE','RESUME','END')",
            name="ck_workout_timer_events_code",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workout_timer_events_workout_session_id",
        "workout_timer_events",
        ["workout_session_id"],
    )
    op.create_table(
        "workout_additional_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type_code", sa.String(64), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("intensity_code", sa.String(32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_seconds > 0", name="ck_workout_additional_duration_positive"),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workout_additional_activities_workout_session_id",
        "workout_additional_activities",
        ["workout_session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workout_additional_activities_workout_session_id",
        table_name="workout_additional_activities",
    )
    op.drop_table("workout_additional_activities")
    op.drop_index("ix_workout_timer_events_workout_session_id", table_name="workout_timer_events")
    op.drop_table("workout_timer_events")
    op.drop_table("workout_session_items")
    op.drop_index("ix_workout_sessions_user_ended_status", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_user_id", table_name="workout_sessions")
    op.drop_table("workout_sessions")
    op.drop_table("decision_selections")
    op.drop_index("ix_scheduled_workouts_user_id", table_name="scheduled_workouts")
    op.drop_table("scheduled_workouts")
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute(
        "DELETE FROM mutation_idempotency_records WHERE endpoint_code IN ("
        "'POST_DECISION_SELECTION','PATCH_WORKOUT_SESSION_START',"
        "'PATCH_WORKOUT_SESSION_ITEM','POST_WORKOUT_TIMER_EVENT',"
        "'POST_WORKOUT_ADDITIONAL_ACTIVITY')"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS')",
    )
