"""Add public decision narration records with template or LLM provenance.

Revision ID: 0019_decision_explanations
Revises: 0018_agent_proposal_policy
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_decision_explanations"
down_revision: str | None = "0018_agent_proposal_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_explanations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_code", sa.String(16), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("agent_summaries", postgresql.JSONB(), nullable=False),
        sa.Column("safety_summary", postgresql.JSONB(), nullable=False),
        sa.Column("final_adjustment_reason", sa.String(500), nullable=True),
        sa.Column("coaching_style_code", sa.String(32), nullable=False),
        sa.Column("template_version", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(128), nullable=True),
        sa.Column("model_code", sa.String(128), nullable=True),
        sa.Column("fallback_reason_code", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_code IN ('TEMPLATE','LLM')",
            name="ck_decision_explanations_source",
        ),
        # LLM 문구를 저장한 경우에만 모델과 프롬프트 버전을 함께 남긴다.
        sa.CheckConstraint(
            "(source_code = 'LLM') = (prompt_version IS NOT NULL AND model_code IS NOT NULL)",
            name="ck_decision_explanations_llm_versions",
        ),
        # 템플릿으로 되돌아간 경우에는 그 이유를 감사할 수 있게 남긴다.
        sa.CheckConstraint(
            "(source_code = 'TEMPLATE') = (fallback_reason_code IS NOT NULL)",
            name="ck_decision_explanations_fallback_reason",
        ),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_run_id", name="uq_decision_explanations_run"),
    )


def downgrade() -> None:
    op.drop_table("decision_explanations")
