"""Add workout safety events, outcomes, and feedback.

Revision ID: 0009_workout_session_outcomes
Revises: 0008_workout_session_flow
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_workout_session_outcomes"
down_revision: str | None = "0008_workout_session_flow"
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
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK')",
    )
    op.create_table(
        "workout_safety_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instruction_code", sa.String(32), nullable=False),
        sa.Column("resulting_action_code", sa.String(32), nullable=True),
        sa.Column("guidance_code", sa.String(48), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "instruction_code IN ('SHOW_CAUTION','STOP_SESSION','STOP_AND_SEEK_HELP')",
            name="ck_workout_safety_events_instruction",
        ),
        sa.CheckConstraint(
            "resulting_action_code IS NULL OR "
            "resulting_action_code IN ('REST','STOP_AND_SEEK_HELP')",
            name="ck_workout_safety_events_action",
        ),
        sa.CheckConstraint(
            "guidance_code IN ('MILD_DISCOMFORT_CAUTION','MODERATE_DISCOMFORT_CAUTION',"
            "'SEVERE_OR_ACUTE_STOP','SERIOUS_ADVERSE_REACTION_STOP')",
            name="ck_workout_safety_events_guidance",
        ),
        sa.CheckConstraint(
            "reason_code IN ('MILD_DISCOMFORT','MODERATE_DISCOMFORT','SEVERE_DISCOMFORT',"
            "'ACUTE_MUSCULOSKELETAL_REACTION','EMERGENCY_ADVERSE_REACTION')",
            name="ck_workout_safety_events_reason",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workout_safety_events_workout_session_id",
        "workout_safety_events",
        ["workout_session_id"],
    )
    op.create_table(
        "workout_safety_event_discomforts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_safety_event_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(64), nullable=False),
        sa.Column("severity_code", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "severity_code IN ('MILD','MODERATE','SEVERE')",
            name="ck_workout_safety_event_discomfort_severity",
        ),
        sa.ForeignKeyConstraint(
            ["workout_safety_event_id"], ["workout_safety_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["body_area_code"], ["body_areas.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_safety_event_id",
            "body_area_code",
            name="uq_workout_safety_event_discomfort_body",
        ),
    )
    op.create_table(
        "workout_safety_event_adverse_reactions",
        sa.Column("workout_safety_event_id", sa.Uuid(), nullable=False),
        sa.Column("reaction_code", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(
            ["workout_safety_event_id"], ["workout_safety_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("workout_safety_event_id", "reaction_code"),
    )
    op.create_table(
        "workout_feedback",
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("difficulty_code", sa.String(16), nullable=False),
        sa.Column("fatigue_code", sa.String(64), nullable=True),
        sa.Column("satisfaction_code", sa.String(64), nullable=True),
        sa.Column("pain_occurred", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "difficulty_code IN ('EASY','APPROPRIATE','HARD')",
            name="ck_workout_feedback_difficulty",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("workout_session_id"),
    )
    op.create_table(
        "workout_feedback_discomforts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(64), nullable=False),
        sa.Column("severity_code", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "severity_code IN ('MILD','MODERATE','SEVERE')",
            name="ck_workout_feedback_discomfort_severity",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"],
            ["workout_feedback.workout_session_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["body_area_code"], ["body_areas.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_session_id", "body_area_code", name="uq_workout_feedback_discomfort_body"
        ),
    )
    op.create_table(
        "workout_feedback_adverse_reactions",
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("reaction_code", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(
            ["workout_session_id"],
            ["workout_feedback.workout_session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workout_session_id", "reaction_code"),
    )
    op.create_table(
        "workout_skip_feedback",
        sa.Column("workout_session_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason_code IN ('TIME_SHORTAGE','FATIGUE','MUSCLE_SORENESS','PAIN',"
            "'SCHEDULE_CHANGE','LOCATION_EQUIPMENT','WEATHER','DIFFICULTY',"
            "'LOW_INTEREST','LOW_MOTIVATION')",
            name="ck_workout_skip_feedback_reason",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("workout_session_id"),
    )


def downgrade() -> None:
    op.drop_table("workout_skip_feedback")
    op.drop_table("workout_feedback_adverse_reactions")
    op.drop_table("workout_feedback_discomforts")
    op.drop_table("workout_feedback")
    op.drop_table("workout_safety_event_adverse_reactions")
    op.drop_table("workout_safety_event_discomforts")
    op.drop_index("ix_workout_safety_events_workout_session_id", table_name="workout_safety_events")
    op.drop_table("workout_safety_events")
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute(
        "DELETE FROM mutation_idempotency_records WHERE endpoint_code IN ("
        "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
        "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK')"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
        "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
        "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY')",
    )
