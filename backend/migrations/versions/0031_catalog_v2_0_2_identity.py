"""Accept the v2.0.2 catalog identity fields and its pain-alternative track.

Revision ID: 0031_catalog_v2_0_2_identity
Revises: 0030_alternative_pain_area_key
Create Date: 2026-08-30

The v2.0.2 catalog carries three things the ``exercises`` table cannot hold:

* 75 records whose ``source_track`` is ``pain_alternative_policy``. They are not
  a new provenance-free bucket - they are independent exercises derived from the
  reviewed pain-alternative policy, and rewriting them as ``merged`` would erase
  where they came from.
* ``record_type`` and ``family_code`` on every record, plus the representative a
  ``VARIANT`` belongs to. ``AGENTS.md`` section 10 asks for typed columns on
  fields the service filters by, so these do not go into JSONB.
* ``general_pool_included``, which decides whether a record is a base routine
  candidate at all.

Every column is nullable and additive, so the v2.0.1 rows already in the table
stay valid and no backfill is needed. ``general_pool_included`` is deliberately
nullable rather than ``NOT NULL DEFAULT false``: the v2.0.2 payload leaves it
unset on 59 records, and the importer has to treat "unset" as "not a candidate"
explicitly rather than inherit a default that hides the distinction.

The downgrade drops the columns and re-narrows the CHECK, so it is safe only
while no row uses the pain-alternative track; once one exists, keep this
migration and use a forward-fix.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_catalog_v2_0_2_identity"
down_revision: str | None = "0030_alternative_pain_area_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TRACKS_WITH_POLICY = (
    "source_track_code IN ('wger', 'kspo', 'gymvisual', 'pain_alternative_policy')"
)
_SOURCE_TRACKS_WITHOUT_POLICY = "source_track_code IN ('wger', 'kspo', 'gymvisual')"


def upgrade() -> None:
    op.drop_constraint("ck_exercises_source_track_code", "exercises", type_="check")
    op.create_check_constraint(
        "ck_exercises_source_track_code",
        "exercises",
        _SOURCE_TRACKS_WITH_POLICY,
    )
    op.add_column("exercises", sa.Column("record_type", sa.String(length=32), nullable=True))
    op.add_column("exercises", sa.Column("family_code", sa.String(length=120), nullable=True))
    op.add_column(
        "exercises",
        sa.Column("representative_stable_code", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "exercises",
        sa.Column("general_pool_included", sa.Boolean(), nullable=True),
    )
    op.create_check_constraint(
        "ck_exercises_record_type",
        "exercises",
        "record_type IS NULL OR record_type IN ('REPRESENTATIVE', 'VARIANT', 'SEPARATE_EXERCISE')",
    )
    # A VARIANT is the only record type that names a parent, and it must name
    # one. Anything else pointing at a representative would make the family
    # graph ambiguous.
    op.create_check_constraint(
        "ck_exercises_variant_parent",
        "exercises",
        "(record_type = 'VARIANT') = (representative_stable_code IS NOT NULL)",
    )
    op.create_index(
        "ix_exercises_general_pool",
        "exercises",
        ["catalog_version_id", "general_pool_included"],
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM exercises WHERE source_track_code = 'pain_alternative_policy'
          ) THEN
            RAISE EXCEPTION
              '0031 downgrade requires forward-fix while pain_alternative_policy '
              'exercises are loaded';
          END IF;
        END $$;
        """
    )
    op.drop_index("ix_exercises_general_pool", table_name="exercises")
    op.drop_constraint("ck_exercises_variant_parent", "exercises", type_="check")
    op.drop_constraint("ck_exercises_record_type", "exercises", type_="check")
    op.drop_column("exercises", "general_pool_included")
    op.drop_column("exercises", "representative_stable_code")
    op.drop_column("exercises", "family_code")
    op.drop_column("exercises", "record_type")
    op.drop_constraint("ck_exercises_source_track_code", "exercises", type_="check")
    op.create_check_constraint(
        "ck_exercises_source_track_code",
        "exercises",
        _SOURCE_TRACKS_WITHOUT_POLICY,
    )
