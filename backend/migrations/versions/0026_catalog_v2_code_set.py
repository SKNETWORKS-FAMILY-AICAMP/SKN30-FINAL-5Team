"""Add the versioned V2 catalog body-focus lookup contract.

Revision ID: 0026_catalog_v2_code_set
Revises: 0025_v3_decision_persistence
Create Date: 2026-08-25

The downgrade is safe only before catalog-v2 rows are imported. Once V2 catalog
data exists, retain the additive constraints and use a forward-fix migration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_catalog_v2_code_set"
down_revision: str | None = "0025_v3_decision_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_catalog_versions_code_set_version", "catalog_versions", type_="check")
    op.create_check_constraint(
        "ck_catalog_versions_code_set_version",
        "catalog_versions",
        "code_set_version IN ('mvp-v1', 'catalog-v2')",
    )
    op.drop_constraint("ck_exercises_source_track_code", "exercises", type_="check")
    op.create_check_constraint(
        "ck_exercises_source_track_code",
        "exercises",
        "source_track_code IN ('wger', 'kspo', 'gymvisual')",
    )
    op.execute(
        """
        INSERT INTO body_focuses (code, code_set_version, display_name_ko)
        SELECT values_to_add.code, 'catalog-v2', values_to_add.display_name_ko
        FROM (VALUES
          ('CHEST', '가슴'),
          ('BACK', '등'),
          ('SHOULDERS', '어깨'),
          ('BICEPS', '이두근'),
          ('TRICEPS', '삼두근'),
          ('FOREARMS', '전완'),
          ('GLUTES', '둔근'),
          ('QUADRICEPS', '대퇴사두근'),
          ('HAMSTRINGS', '햄스트링'),
          ('CALVES', '종아리'),
          ('CORE', '코어'),
          ('FULL_BODY', '전신'),
          ('CARDIO', '유산소'),
          ('MOBILITY', '가동성')
        ) AS values_to_add(code, display_name_ko)
        WHERE NOT EXISTS (
          SELECT 1 FROM body_focuses existing WHERE existing.code = values_to_add.code
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM catalog_versions WHERE code_set_version = 'catalog-v2'
          ) OR EXISTS (
            SELECT 1 FROM exercises WHERE source_track_code = 'gymvisual'
          ) THEN
            RAISE EXCEPTION
              '0026 downgrade requires forward-fix after catalog-v2 data is imported';
          END IF;
        END $$;
        """
    )
    # CORE and FULL_BODY may be shared with an existing mvp-v1 catalog because
    # body_focuses uses the stable code itself as its global primary key. Preserve
    # every lookup row still referenced by either catalog exercises or routines.
    op.execute(
        """
        DELETE FROM body_focuses candidate
        WHERE candidate.code_set_version = 'catalog-v2'
          AND NOT EXISTS (
            SELECT 1 FROM exercises WHERE body_focus_code = candidate.code
          )
          AND NOT EXISTS (
            SELECT 1 FROM routine_days WHERE body_focus_code = candidate.code
          )
        """
    )
    op.drop_constraint("ck_exercises_source_track_code", "exercises", type_="check")
    op.create_check_constraint(
        "ck_exercises_source_track_code",
        "exercises",
        "source_track_code IN ('wger', 'kspo')",
    )
    op.drop_constraint("ck_catalog_versions_code_set_version", "catalog_versions", type_="check")
    op.create_check_constraint(
        "ck_catalog_versions_code_set_version",
        "catalog_versions",
        "code_set_version IN ('mvp-v1')",
    )
