"""Scope media s3_key uniqueness to the catalog version.

The global unique index on ``s3_key`` made a catalog version the sole owner of
a media file, so publishing v2.0.3 -- which carries v2.0.2's 68 approved assets
over unchanged -- failed on the first row. Two versions legitimately reference
the same GIF for the same exercise.

The invariant worth keeping is that one file is not claimed twice inside a
single catalog version, so the constraint moves to (catalog_version_id, s3_key).
The existing (catalog_version_id, exercise_id) constraint is untouched.

Revision ID: 0033_media_s3_key_per_catalog
Revises: 0032_form_cue_provenance
"""

from alembic import op

revision = "0033_media_s3_key_per_catalog"
down_revision = "0032_form_cue_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_exercise_media_assets_s3_key",
        "exercise_media_assets",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_exercise_media_assets_catalog_s3_key",
        "exercise_media_assets",
        ["catalog_version_id", "s3_key"],
    )


def downgrade() -> None:
    # Rolling back re-imposes global ownership of a file. That is only possible
    # while no two catalog versions share one, which is true for any database
    # that has not yet imported a second version. Where it is not, the rollback
    # fails loudly rather than dropping rows to fit the old shape.
    op.drop_constraint(
        "uq_exercise_media_assets_catalog_s3_key",
        "exercise_media_assets",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_exercise_media_assets_s3_key",
        "exercise_media_assets",
        ["s3_key"],
    )
