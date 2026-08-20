"""Add V2 structured deliberation persistence.

Revision ID: 0023_v2_deliberation_store
Revises: 0022_promote_merged_data
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_v2_deliberation_store"
down_revision: str | None = "0022_promote_merged_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_deliberations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("deliberation_schema_version", sa.String(32), nullable=False),
        sa.Column("graph_version", sa.String(128), nullable=False),
        sa.Column("round_count", sa.Integer(), nullable=False),
        sa.Column("round_two_status_code", sa.String(32), nullable=False),
        sa.Column("conflict_detector_version", sa.String(128), nullable=False),
        sa.Column("precedence_version", sa.String(128), nullable=False),
        sa.Column("conflict_codes", postgresql.JSONB(), nullable=False),
        sa.Column("conflict_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("round_count IN (1,2)", name="ck_decision_deliberations_round_count"),
        sa.CheckConstraint(
            "round_two_status_code IN ('SKIPPED_NO_CONFLICT','COMPLETED','NEEDS_INPUT','FAILED')",
            name="ck_decision_deliberations_round_two_status",
        ),
        sa.CheckConstraint(
            "char_length(conflict_hash) = 64",
            name="ck_decision_deliberations_conflict_hash",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["decision_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_run_id", name="uq_decision_deliberations_run"),
    )

    op.create_table(
        "agent_proposal_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("deliberation_id", sa.Uuid(), nullable=False),
        sa.Column("source_proposal_id", sa.Uuid(), nullable=True),
        sa.Column("baseline_revision_id", sa.Uuid(), nullable=True),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("agent_type_code", sa.String(32), nullable=False),
        sa.Column("proposal_status_code", sa.String(24), nullable=False),
        sa.Column("proposal_schema_version", sa.String(32), nullable=False),
        sa.Column("proposal_payload", postgresql.JSONB(), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("round_number IN (1,2)", name="ck_agent_proposal_revisions_round"),
        sa.CheckConstraint(
            "agent_type_code IN ('TRAINING','RECOVERY','SAFETY','FEASIBILITY')",
            name="ck_agent_proposal_revisions_type",
        ),
        sa.CheckConstraint(
            "proposal_status_code IN ('READY','NEEDS_INPUT','FAILED')",
            name="ck_agent_proposal_revisions_status",
        ),
        sa.CheckConstraint(
            "(round_number = 1 AND source_proposal_id IS NOT NULL "
            "AND baseline_revision_id IS NULL) OR "
            "(round_number = 2 AND baseline_revision_id IS NOT NULL)",
            name="ck_agent_proposal_revisions_lineage",
        ),
        sa.CheckConstraint(
            "char_length(proposal_hash) = 64",
            name="ck_agent_proposal_revisions_hash",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["deliberation_id"], ["decision_deliberations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_proposal_id"], ["agent_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["baseline_revision_id"], ["agent_proposal_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["decision_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_run_id",
            "round_number",
            "agent_type_code",
            name="uq_agent_proposal_revisions_run_round_type",
        ),
    )

    op.create_table(
        "agent_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("deliberation_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_revision_id", sa.Uuid(), nullable=False),
        sa.Column("revised_revision_id", sa.Uuid(), nullable=True),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("agent_type_code", sa.String(32), nullable=False),
        sa.Column("review_status_code", sa.String(24), nullable=False),
        sa.Column("revision_status_code", sa.String(24), nullable=True),
        sa.Column("review_schema_version", sa.String(32), nullable=False),
        sa.Column("baseline_proposal_hash", sa.String(64), nullable=False),
        sa.Column("reviewed_proposal_references", postgresql.JSONB(), nullable=False),
        sa.Column("review_payload", postgresql.JSONB(), nullable=False),
        sa.Column("review_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("round_number = 2", name="ck_agent_review_events_round"),
        sa.CheckConstraint(
            "agent_type_code IN ('TRAINING','RECOVERY','SAFETY','FEASIBILITY')",
            name="ck_agent_review_events_type",
        ),
        sa.CheckConstraint(
            "review_status_code IN ('READY','NOT_REQUIRED','NEEDS_INPUT','FAILED')",
            name="ck_agent_review_events_status",
        ),
        sa.CheckConstraint(
            "revision_status_code IS NULL OR revision_status_code IN "
            "('UNCHANGED','REVISED','NOT_REQUIRED')",
            name="ck_agent_review_events_revision_status",
        ),
        sa.CheckConstraint(
            "(review_status_code = 'READY' AND revision_status_code IN "
            "('UNCHANGED','REVISED')) OR "
            "(review_status_code = 'NOT_REQUIRED' AND "
            "revision_status_code = 'NOT_REQUIRED') OR "
            "(review_status_code IN ('NEEDS_INPUT','FAILED') AND "
            "revision_status_code IS NULL)",
            name="ck_agent_review_events_status_pair",
        ),
        sa.CheckConstraint(
            "(revision_status_code = 'REVISED') = (revised_revision_id IS NOT NULL)",
            name="ck_agent_review_events_revised_link",
        ),
        sa.CheckConstraint(
            "char_length(baseline_proposal_hash) = 64 AND char_length(review_hash) = 64",
            name="ck_agent_review_events_hashes",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["deliberation_id"], ["decision_deliberations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["baseline_revision_id"], ["agent_proposal_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["revised_revision_id"], ["agent_proposal_revisions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_run_id",
            "round_number",
            "agent_type_code",
            name="uq_agent_review_events_run_round_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_review_events")
    op.drop_table("agent_proposal_revisions")
    op.drop_table("decision_deliberations")
