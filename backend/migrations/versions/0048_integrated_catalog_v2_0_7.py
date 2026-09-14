"""Persist reviewed MET provenance from the integrated v2.0.7 catalog.

The fields are additive and nullable so historic catalog versions retain their
existing meaning. This migration intentionally does not load or activate data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_integrated_catalog_v2_0_7"
down_revision: str | None = "0047_social_oauth_google"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("met_value", sa.Float(), nullable=True))
    op.add_column("exercises", sa.Column("met_source_code", sa.String(length=120), nullable=True))
    op.add_column(
        "exercises", sa.Column("met_source_activity_code", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "exercises", sa.Column("met_mapping_method_code", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "exercises", sa.Column("met_review_status_code", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "exercises", sa.Column("met_policy_version", sa.String(length=120), nullable=True)
    )
    op.create_check_constraint(
        "ck_exercises_met_value", "exercises", "met_value IS NULL OR met_value > 0"
    )
    op.create_check_constraint(
        "ck_exercises_met_review_status",
        "exercises",
        "met_review_status_code IS NULL OR "
        "met_review_status_code IN ('REVIEW_REQUIRED', 'DOMAIN_APPROVED')",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM exercises WHERE met_value IS NOT NULL) THEN
            RAISE EXCEPTION
              '0047 downgrade requires a forward fix while MET provenance exists';
          END IF;
        END $$;
        """
    )
    op.drop_constraint("ck_exercises_met_review_status", "exercises", type_="check")
    op.drop_constraint("ck_exercises_met_value", "exercises", type_="check")
    op.drop_column("exercises", "met_policy_version")
    op.drop_column("exercises", "met_review_status_code")
    op.drop_column("exercises", "met_mapping_method_code")
    op.drop_column("exercises", "met_source_activity_code")
    op.drop_column("exercises", "met_source_code")
    op.drop_column("exercises", "met_value")
