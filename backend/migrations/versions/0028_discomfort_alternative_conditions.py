"""Add typed pain-area and NRS selectors to exercise alternatives.

Revision ID: 0028_discomfort_alternative_conditions
Revises: 0027_catalog_media_assets
Create Date: 2026-08-29

The columns are nullable so existing equipment/location alternatives remain
backward compatible. New DISCOMFORT rows carry the typed selectors instead of
requiring the decision service to inspect JSON metadata.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_discomfort_alternative_conditions"
down_revision: str | None = "0027_catalog_media_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exercise_alternatives",
        sa.Column("pain_discomfort_area_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "exercise_alternatives",
        sa.Column("condition_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "exercise_alternatives",
        sa.Column("service_action_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "exercise_alternatives",
        sa.Column("target_strategy_code", sa.String(length=120), nullable=True),
    )
    op.drop_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        [
            "alternative_set_version_code",
            "source_exercise_id",
            "alternative_exercise_id",
            "reason_code",
            "goal_preservation_code",
            "rule_version",
            "condition_code",
        ],
    )
    op.create_index(
        "ix_exercise_alternatives_discomfort_lookup",
        "exercise_alternatives",
        [
            "source_exercise_id",
            "pain_discomfort_area_code",
            "condition_code",
            "review_status_code",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_exercise_alternatives_discomfort_lookup",
        table_name="exercise_alternatives",
    )
    op.drop_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        [
            "alternative_set_version_code",
            "source_exercise_id",
            "alternative_exercise_id",
            "reason_code",
            "goal_preservation_code",
            "rule_version",
        ],
    )
    op.drop_column("exercise_alternatives", "target_strategy_code")
    op.drop_column("exercise_alternatives", "service_action_code")
    op.drop_column("exercise_alternatives", "condition_code")
    op.drop_column("exercise_alternatives", "pain_discomfort_area_code")
