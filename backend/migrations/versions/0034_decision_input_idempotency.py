"""Prevent duplicate completed ORIGINAL decisions for one immutable daily-context input.

The predicate deliberately excludes regenerations. A regenerated decision shares
``(user_id, daily_context_id, daily_context_version, input_hash)`` with the run it was
derived from, because regeneration re-runs the very same immutable input on purpose and
records the lineage in ``root_decision_run_id`` / ``regeneration_sequence``. Constraining
the four columns alone would therefore reject the second regeneration of a day and break
the feature. Legacy V1/V2 rows carry ``generation_mode_code IS NULL`` and are treated as
originals so they stay covered.

Revision ID: 0034_decision_input_idempotency
Revises: 0033_media_s3_key_per_catalog
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_decision_input_idempotency"
down_revision = "0033_media_s3_key_per_catalog"
branch_labels = None
depends_on = None

_PREDICATE = "status_code = 'COMPLETED' AND coalesce(generation_mode_code, 'ORIGINAL') = 'ORIGINAL'"


def upgrade() -> None:
    op.create_index(
        "uq_decision_runs_completed_input",
        "decision_runs",
        ["user_id", "daily_context_id", "daily_context_version", "input_hash"],
        unique=True,
        postgresql_where=sa.text(_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_decision_runs_completed_input", table_name="decision_runs")
