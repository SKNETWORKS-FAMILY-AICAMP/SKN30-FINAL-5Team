"""Prevent duplicate completed decisions for one immutable daily-context input.

Revision ID: 0034_decision_input_idempotency
Revises: 0033_media_s3_key_per_catalog
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_decision_input_idempotency"
down_revision = "0033_media_s3_key_per_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_decision_runs_completed_input",
        "decision_runs",
        ["user_id", "daily_context_id", "daily_context_version", "input_hash"],
        unique=True,
        postgresql_where=sa.text("status_code = 'COMPLETED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_decision_runs_completed_input", table_name="decision_runs")
