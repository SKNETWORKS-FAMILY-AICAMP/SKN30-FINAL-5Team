"""Drop the profile location, sex and height storage ADR-0017 retired.

Revision ID: 0050_drop_retired_profile_cols
Revises: 0049_drop_profile_coaching_style
Create Date: 2026-09-07

BL-7 stage 2. ADR-0017 moved the workout location to the Daily Check-in
(`location_code`) and stopped collecting sex and height, and stage 1 (`134316e`)
stopped applying all three: `PATCH /api/v1/me/profile` accepts the fields and
discards them, and onboarding no longer takes a location from the request. The
columns have been write-only for a release, which is what AGENTS.md section 10
requires before a drop.

`user_available_locations` goes with them. It only ever held the onboarding
location set, nothing has written a row since stage 1, and the base routine has
not gated on location since ADR-0017 -- the day's location constraint comes from
the Safety-approved Pool that is rebuilt on every check-in.

`weight_kg` is deliberately untouched. It is still a required onboarding input and
BM-6's calorie estimate reads it.

Rollback recreates the three columns and the table, restores the location default
of `HOME` that ADR-0017's stage-1 contract already produced for every profile, and
re-seeds `user_available_locations` from it the same way 0005 first did. Sex and
height come back empty: the values were not read after stage 1 and this drop is the
release that removes them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_drop_retired_profile_cols"
down_revision: str | None = "0049_drop_profile_coaching_style"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCATION_FK = "fk_user_profiles_preferred_location_code_locations"


def upgrade() -> None:
    op.drop_table("user_available_locations")
    # PostgreSQL drops the column's foreign key with the column.
    op.drop_column("user_profiles", "preferred_location_code")
    op.drop_column("user_profiles", "height_cm")
    op.drop_column("user_profiles", "sex_code")


def downgrade() -> None:
    op.add_column("user_profiles", sa.Column("sex_code", sa.String(length=32), nullable=True))
    op.add_column("user_profiles", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column(
        "user_profiles",
        sa.Column(
            "preferred_location_code",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'HOME'"),
        ),
    )
    # The default only exists to backfill existing rows; the column was never
    # defaulted in the schema this rollback restores.
    op.alter_column("user_profiles", "preferred_location_code", server_default=None)
    op.create_foreign_key(
        _LOCATION_FK,
        "user_profiles",
        "locations",
        ["preferred_location_code"],
        ["code"],
    )
    op.create_table(
        "user_available_locations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["location_code"],
            ["locations.code"],
            name="fk_user_available_locations_location_code_locations",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_available_locations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "location_code", name="pk_user_available_locations"),
    )
    op.execute(
        "INSERT INTO user_available_locations (user_id, location_code) "
        "SELECT user_id, preferred_location_code FROM user_profiles"
    )
