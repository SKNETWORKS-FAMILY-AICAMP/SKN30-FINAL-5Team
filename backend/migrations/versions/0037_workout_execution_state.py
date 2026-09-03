"""separate workout completion from execution state

Revision ID: 0037_workout_execution_state
Revises: 0036_checkin_safety_recovery
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_workout_execution_state"
down_revision: str | Sequence[str] | None = "0036_checkin_safety_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("plan_candidates", sa.Column("expected_duration_min_seconds", sa.Integer()))
    op.add_column("plan_candidates", sa.Column("expected_duration_max_seconds", sa.Integer()))
    op.add_column(
        "plan_candidates", sa.Column("duration_estimation_policy_version", sa.String(length=128))
    )
    op.create_check_constraint(
        "ck_plan_candidates_expected_duration_range",
        "plan_candidates",
        "(expected_duration_min_seconds IS NULL AND expected_duration_max_seconds IS NULL) OR "
        "(expected_duration_min_seconds > 0 AND expected_duration_max_seconds > 0 "
        "AND expected_duration_min_seconds <= expected_duration_max_seconds)",
    )

    op.add_column("workout_sessions", sa.Column("completion_code", sa.String(length=24)))
    op.add_column("workout_sessions", sa.Column("execution_state_code", sa.String(length=24)))
    op.add_column("workout_sessions", sa.Column("target_duration_seconds", sa.Integer()))
    op.add_column(
        "workout_sessions",
        sa.Column("accumulated_progress_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workout_sessions",
        sa.Column("accumulated_rest_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workout_sessions",
        sa.Column("accumulated_paused_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workout_sessions", sa.Column("last_state_changed_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "workout_sessions",
        sa.Column("is_resumable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("workout_sessions", sa.Column("stop_reason_code", sa.String(length=32)))
    op.execute(
        "UPDATE workout_sessions SET completion_code = status_code "
        "WHERE status_code IN ('COMPLETED', 'PARTIAL', 'NOT_COMPLETED')"
    )
    op.execute(
        "UPDATE workout_sessions SET execution_state_code = CASE "
        "WHEN status_code = 'STOPPED_FOR_SAFETY' THEN 'STOPPED_SAFETY' "
        "WHEN status_code IN ('COMPLETED', 'PARTIAL', 'NOT_COMPLETED') THEN 'COMPLETED' "
        "WHEN status_code = 'IN_PROGRESS' THEN 'RUNNING' ELSE NULL END"
    )
    op.create_check_constraint(
        "ck_workout_sessions_completion",
        "workout_sessions",
        "completion_code IS NULL OR completion_code IN ('COMPLETED','PARTIAL','NOT_COMPLETED')",
    )
    op.create_check_constraint(
        "ck_workout_sessions_execution_state",
        "workout_sessions",
        "execution_state_code IS NULL OR execution_state_code IN "
        "('RUNNING','RESTING','PAUSED','STOPPED_RESUMABLE','STOPPED_SAFETY','COMPLETED')",
    )
    op.create_check_constraint(
        "ck_workout_sessions_stop_reason",
        "workout_sessions",
        "stop_reason_code IS NULL OR stop_reason_code IN "
        "('HIGH_FATIGUE','TIME_SHORTAGE','RESUME_LATER','PAIN_OR_ABNORMAL_RESPONSE')",
    )
    op.create_check_constraint(
        "ck_workout_sessions_target_duration_positive",
        "workout_sessions",
        "target_duration_seconds IS NULL OR target_duration_seconds > 0",
    )
    op.create_check_constraint(
        "ck_workout_sessions_accumulated_duration_nonnegative",
        "workout_sessions",
        "accumulated_progress_seconds >= 0 AND accumulated_rest_seconds >= 0 "
        "AND accumulated_paused_seconds >= 0",
    )
    op.alter_column("workout_sessions", "accumulated_progress_seconds", server_default=None)
    op.alter_column("workout_sessions", "accumulated_rest_seconds", server_default=None)
    op.alter_column("workout_sessions", "accumulated_paused_seconds", server_default=None)
    op.alter_column("workout_sessions", "is_resumable", server_default=None)

    op.alter_column("workout_safety_events", "instruction_code", nullable=True)
    op.alter_column("workout_safety_events", "guidance_code", nullable=True)
    op.alter_column("workout_safety_events", "reason_code", nullable=True)
    op.add_column("workout_safety_events", sa.Column("plan_item_id", sa.Uuid()))
    op.add_column("workout_safety_events", sa.Column("result_code", sa.String(length=32)))
    op.add_column("workout_safety_events", sa.Column("symptom_code", sa.String(length=64)))
    op.add_column("workout_safety_events", sa.Column("body_area_code", sa.String(length=64)))
    op.add_column("workout_safety_events", sa.Column("nrs_score", sa.SmallInteger()))
    op.create_foreign_key(
        "fk_workout_safety_events_plan_item",
        "workout_safety_events",
        "plan_items",
        ["plan_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_workout_safety_events_body_area",
        "workout_safety_events",
        "body_areas",
        ["body_area_code"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_workout_safety_events_result",
        "workout_safety_events",
        "result_code IS NULL OR result_code IN ('SESSION_STOPPED','STOP_AND_SEEK_HELP')",
    )
    op.create_check_constraint(
        "ck_workout_safety_events_nrs",
        "workout_safety_events",
        "nrs_score IS NULL OR nrs_score BETWEEN 1 AND 10",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workout_safety_events_nrs", "workout_safety_events", type_="check")
    op.drop_constraint("ck_workout_safety_events_result", "workout_safety_events", type_="check")
    op.drop_constraint(
        "fk_workout_safety_events_body_area", "workout_safety_events", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_workout_safety_events_plan_item", "workout_safety_events", type_="foreignkey"
    )
    op.drop_column("workout_safety_events", "nrs_score")
    op.drop_column("workout_safety_events", "body_area_code")
    op.drop_column("workout_safety_events", "symptom_code")
    op.drop_column("workout_safety_events", "result_code")
    op.drop_column("workout_safety_events", "plan_item_id")
    # Preserve the historical row shape before restoring the legacy NOT NULL
    # constraints; P1-C structured values have no one-to-one legacy equivalent.
    op.execute(
        "UPDATE workout_safety_events SET "
        "instruction_code = COALESCE(instruction_code, CASE "
        "WHEN result_code = 'STOP_AND_SEEK_HELP' THEN 'STOP_AND_SEEK_HELP' "
        "ELSE 'STOP_SESSION' END), "
        "resulting_action_code = COALESCE(resulting_action_code, CASE "
        "WHEN result_code = 'STOP_AND_SEEK_HELP' THEN 'STOP_AND_SEEK_HELP' ELSE 'REST' END), "
        "guidance_code = COALESCE(guidance_code, CASE "
        "WHEN result_code = 'STOP_AND_SEEK_HELP' THEN 'SERIOUS_ADVERSE_REACTION_STOP' "
        "ELSE 'SEVERE_OR_ACUTE_STOP' END), "
        "reason_code = COALESCE(reason_code, 'SEVERE_DISCOMFORT')"
    )
    op.alter_column("workout_safety_events", "reason_code", nullable=False)
    op.alter_column("workout_safety_events", "guidance_code", nullable=False)
    op.alter_column("workout_safety_events", "instruction_code", nullable=False)

    for name in (
        "ck_workout_sessions_accumulated_duration_nonnegative",
        "ck_workout_sessions_target_duration_positive",
        "ck_workout_sessions_stop_reason",
        "ck_workout_sessions_execution_state",
        "ck_workout_sessions_completion",
    ):
        op.drop_constraint(name, "workout_sessions", type_="check")
    for name in (
        "stop_reason_code",
        "is_resumable",
        "last_state_changed_at",
        "accumulated_paused_seconds",
        "accumulated_rest_seconds",
        "accumulated_progress_seconds",
        "target_duration_seconds",
        "execution_state_code",
        "completion_code",
    ):
        op.drop_column("workout_sessions", name)

    op.drop_constraint(
        "ck_plan_candidates_expected_duration_range", "plan_candidates", type_="check"
    )
    op.drop_column("plan_candidates", "duration_estimation_policy_version")
    op.drop_column("plan_candidates", "expected_duration_max_seconds")
    op.drop_column("plan_candidates", "expected_duration_min_seconds")
