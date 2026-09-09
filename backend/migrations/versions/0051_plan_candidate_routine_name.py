"""Store the decided routine name on the selected plan candidate.

Revision ID: 0051_plan_candidate_routine_name
Revises: 0050_drop_retired_profile_cols
Create Date: 2026-09-09

`build_plan_name` decides a plan's public name at decision time, and the create
response carried it, but nothing wrote it down. `DecisionRepository.get_response`
rebuilds the response from these tables, so replaying a stored decision returned
a `final_plan` with no name at all -- and because both decision GET routes use
`response_model_exclude_unset=True`, the field was dropped from the payload
rather than sent as null. A client that reopened the day's plan therefore fell
back to composing its own title, and the same routine changed name on screen
just from navigating away and back.

The name cannot be recomputed on read. It is derived from the MAIN block's
catalog attributes, and the catalog version that produced it may since have been
superseded, so a recomputed name could differ from the one the user was shown.
Storing it alongside `duration_rule_version` follows what `backend/app/db/AGENTS.md`
already requires of this table: preserve the versions a decision was made under.

All three columns are nullable. Runs created before this migration have no
recorded name and replay without one, which is exactly the state the client's
existing compatibility fallback already handles -- so this is additive for
stored data and for the public contract.

Rollback drops the three columns. No other table references them and nothing
reads them outside the decision response, so a forward-fix is not required.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0051_plan_candidate_routine_name"
down_revision: str | None = "0050_drop_retired_profile_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "plan_candidates"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("routine_name", sa.String(length=120), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column(
            "routine_name_reason_codes",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE, sa.Column("routine_naming_rule_version", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "routine_naming_rule_version")
    op.drop_column(_TABLE, "routine_name_reason_codes")
    op.drop_column(_TABLE, "routine_name")
