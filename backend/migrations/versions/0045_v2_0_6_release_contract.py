"""Allow the reviewed v2.0.6 catalog release contract.

The v2.0.6 bundle is the first catalog release in this branch that uses the
Gymvisual source track, manifest schema 1.1, and the reviewed ADDUCTORS body
focus. The changes are additive and preserve all existing catalog rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045_v2_0_6_release_contract"
down_revision: str | None = "0044_profile_image_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_catalog_versions_manifest_schema_version",
        "catalog_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_versions_manifest_schema_version",
        "catalog_versions",
        "manifest_schema_version IN ('1.0', '1.1')",
    )
    op.drop_constraint(
        "ck_catalog_versions_source_track_code",
        "catalog_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_versions_source_track_code",
        "catalog_versions",
        "source_track_code IN ('wger', 'kspo', 'gymvisual', 'merged')",
    )
    op.execute(
        """
        INSERT INTO body_focuses (code, code_set_version, display_name_ko)
        VALUES ('ADDUCTORS', 'catalog-v2', '내전근')
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM catalog_versions
            WHERE manifest_schema_version = '1.1'
               OR source_track_code = 'gymvisual'
          ) OR EXISTS (
            SELECT 1 FROM exercises WHERE body_focus_code = 'ADDUCTORS'
          ) OR EXISTS (
            SELECT 1 FROM routine_days WHERE body_focus_code = 'ADDUCTORS'
          ) THEN
            RAISE EXCEPTION
              '0041 downgrade requires forward-fix while v2.0.6 contract data exists';
          END IF;
        END $$;
        """
    )
    op.execute("DELETE FROM body_focuses WHERE code = 'ADDUCTORS'")
    op.drop_constraint(
        "ck_catalog_versions_source_track_code",
        "catalog_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_versions_source_track_code",
        "catalog_versions",
        "source_track_code IN ('wger', 'kspo', 'merged')",
    )
    op.drop_constraint(
        "ck_catalog_versions_manifest_schema_version",
        "catalog_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_versions_manifest_schema_version",
        "catalog_versions",
        "manifest_schema_version IN ('1.0')",
    )
