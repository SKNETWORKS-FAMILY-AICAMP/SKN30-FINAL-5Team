"""Add atomic decision reproducibility records.

Revision ID: 0007_decision_persistence
Revises: 0006_daily_contexts
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_decision_persistence"
down_revision: str | None = "0006_daily_contexts"
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
        "'PUT_DAILY_CONTEXT','POST_DECISIONS')",
    )
    op.create_table(
        "decision_policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_code", sa.String(128), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_code"),
        sa.CheckConstraint(
            "status_code IN ('ACTIVE','DEPRECATED')", name="ck_decision_policy_status"
        ),
    )
    op.execute(
        "INSERT INTO decision_policy_versions (id, version_code, status_code) "
        "VALUES ('00000000-0000-0000-0000-000000000007', 'decision-policy-v1', 'ACTIVE')"
    )
    op.create_table(
        "decision_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("daily_context_id", sa.Uuid(), nullable=False),
        sa.Column("daily_context_version", sa.Integer(), nullable=False),
        sa.Column("base_routine_id", sa.Uuid(), nullable=False),
        sa.Column("input_schema_version", sa.String(64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("safety_rule_version", sa.String(128), nullable=False),
        sa.Column("duration_rule_version", sa.String(128), nullable=False),
        sa.Column("graph_version", sa.String(128), nullable=False),
        sa.Column("coordinator_version", sa.String(128), nullable=False),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("safety_status_code", sa.String(16), nullable=False),
        sa.Column("recommended_action_code", sa.String(32), nullable=True),
        sa.Column("coordinator_result", postgresql.JSONB(), nullable=False),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status_code IN ('RUNNING','COMPLETED','FAILED','NEEDS_INPUT')",
            name="ck_decision_runs_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["daily_context_id"], ["daily_contexts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_routine_id"], ["routines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"], ["catalog_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["decision_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_runs_user_id", "decision_runs", ["user_id"])
    op.create_index("ix_decision_runs_user_date", "decision_runs", ["user_id", "local_date"])
    op.create_index("ix_decision_runs_input_hash", "decision_runs", ["input_hash"])
    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_type_code", sa.String(32), nullable=False),
        sa.Column("proposal_status_code", sa.String(24), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("proposal_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "agent_type_code IN ('TRAINING','RECOVERY','SAFETY','FEASIBILITY')",
            name="ck_agent_proposals_type",
        ),
        sa.CheckConstraint(
            "proposal_status_code IN ('READY','NEEDS_INPUT','FAILED')",
            name="ck_agent_proposals_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_run_id", "agent_type_code", name="uq_agent_proposals_run_type"
        ),
    )
    op.create_table(
        "plan_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_code", sa.String(128), nullable=False),
        sa.Column("action_code", sa.String(32), nullable=False),
        sa.Column("training_type_code", sa.String(64), nullable=False),
        sa.Column("body_focus_code", sa.String(64), nullable=True),
        sa.Column("requested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("duration_adjustment_source_code", sa.String(32), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("estimated_calories_burned", sa.Float(), nullable=True),
        sa.Column("setup_seconds", sa.Integer(), nullable=False),
        sa.Column("warmup_seconds", sa.Integer(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("goal_tags", postgresql.JSONB(), nullable=False),
        sa.Column("duration_rule_version", sa.String(128), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action_code IN ('KEEP','DOWNSHIFT','CHANGE','RECOVERY')",
            name="ck_plan_candidates_action",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_run_id", "candidate_code", name="uq_plan_candidates_run_code"
        ),
    )
    op.create_table(
        "plan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase_code", sa.String(16), nullable=False),
        sa.Column("tier_code", sa.String(16), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("work_seconds_per_set", sa.Integer(), nullable=True),
        sa.Column("rest_seconds_per_set", sa.Integer(), nullable=False),
        sa.Column("work_seconds", sa.Integer(), nullable=False),
        sa.Column("rest_seconds", sa.Integer(), nullable=False),
        sa.Column("transition_seconds", sa.Integer(), nullable=False),
        sa.Column("intensity_code", sa.String(32), nullable=False),
        sa.Column("instruction_content_version", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.ForeignKeyConstraint(["plan_candidate_id"], ["plan_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_candidate_id", "sequence", name="uq_plan_items_candidate_sequence"
        ),
    )
    op.create_table(
        "safety_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("plan_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("safety_status_code", sa.String(16), nullable=False),
        sa.Column("vetoed", sa.Boolean(), nullable=False),
        sa.Column("ruleset_version", sa.String(128), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("excluded_exercise_ids", postgresql.JSONB(), nullable=False),
        sa.Column("public_guidance", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_candidate_id"], ["plan_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_run_id"),
    )
    op.create_table(
        "decision_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("option_code", sa.String(32), nullable=False),
        sa.Column("action_code", sa.String(32), nullable=False),
        sa.Column("plan_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("selectable", sa.Boolean(), nullable=False),
        sa.Column("blocked_reason_code", sa.String(128), nullable=True),
        sa.CheckConstraint(
            "option_code IN ('FINAL_ROUTINE','REST')", name="ck_decision_options_code"
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_candidate_id"], ["plan_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_run_id", "option_code", name="uq_decision_options_run_code"),
    )


def downgrade() -> None:
    op.drop_table("decision_options")
    op.drop_table("safety_reviews")
    op.drop_table("plan_items")
    op.drop_table("plan_candidates")
    op.drop_table("agent_proposals")
    op.drop_index("ix_decision_runs_input_hash", table_name="decision_runs")
    op.drop_index("ix_decision_runs_user_date", table_name="decision_runs")
    op.drop_index("ix_decision_runs_user_id", table_name="decision_runs")
    op.drop_table("decision_runs")
    op.drop_table("decision_policy_versions")
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute("DELETE FROM mutation_idempotency_records WHERE endpoint_code = 'POST_DECISIONS'")
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        "endpoint_code IN ('PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
        "'PUT_DAILY_CONTEXT')",
    )
