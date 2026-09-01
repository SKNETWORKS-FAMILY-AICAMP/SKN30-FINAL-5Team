"""Allow a merged catalog version while retaining exercise-level provenance.

Revision ID: 0021_merged_catalog_source
Revises: 0020_manual_availability
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_merged_catalog_source"
down_revision: str | None = "0020_manual_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_catalog_versions_source_track_code", "catalog_versions", type_="check")
    op.create_check_constraint(
        "ck_catalog_versions_source_track_code",
        "catalog_versions",
        "source_track_code IN ('wger', 'kspo', 'merged')",
    )


def downgrade() -> None:
    # Do not delete or rewrite merged provenance during rollback. Restore the narrow
    # constraint only when no merged row exists; otherwise retain the additive constraint
    # as the documented forward-fix strategy until those rows are retired explicitly.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM catalog_versions WHERE source_track_code = 'merged') THEN
            ALTER TABLE catalog_versions
              DROP CONSTRAINT ck_catalog_versions_source_track_code;
            ALTER TABLE catalog_versions
              ADD CONSTRAINT ck_catalog_versions_source_track_code
              CHECK (source_track_code IN ('wger', 'kspo'));
          END IF;
        END $$;
        """
    )
