"""Separate the safety-stop count and record where a calorie estimate came from.

Revision ID: 0040_weekly_safety_and_calorie
Revises: 0039_workout_difficulty_reasons
Create Date: 2026-09-03

Two additions the weekly report needs.

`weekly_reports.stopped_for_safety` counts sessions under the old single status axis,
where a safety stop was one of the official completion states. P1-C split those axes: the
official state now comes from completed block counts alone, and a safety stop is an
execution state. `safety_stopped_session_count` counts the new meaning.

Both columns are kept and dual-written. `AGENTS.md` 10 forbids dropping a production
column in the same release that stops writing it, and a closed report's numbers must not
change under a reader who already acknowledged them: existing rows keep the value they
were generated with, and the aggregate schema version tells the two meanings apart.

`workout_sessions` gains the calorie provenance the contract already promises --
`calorie_source_code`, the policy version behind the number, and the minimal snapshot it
was derived from. Without the source a client cannot tell a wearable reading from a MET
estimate, and both are already rendered as one number.

Additive in both directions; the rollback drops only what this adds.

The revision id is kept under 32 characters because that is the width of Alembic's
alembic_version.version_num column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_weekly_safety_and_calorie"
down_revision: str | None = "0039_workout_difficulty_reasons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weekly_reports",
        sa.Column("safety_stopped_session_count", sa.Integer(), nullable=True),
    )
    # Existing rows carry the old meaning; seeding from it keeps closed reports readable
    # without claiming the two counts were ever computed the same way.
    op.execute(
        "UPDATE weekly_reports "
        "SET safety_stopped_session_count = stopped_for_safety "
        "WHERE safety_stopped_session_count IS NULL"
    )
    op.alter_column("weekly_reports", "safety_stopped_session_count", nullable=False)
    op.create_check_constraint(
        "ck_weekly_reports_safety_stopped_nonnegative",
        "weekly_reports",
        "safety_stopped_session_count >= 0",
    )

    op.add_column(
        "workout_sessions",
        sa.Column("calorie_source_code", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "workout_sessions",
        sa.Column("calorie_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workout_sessions",
        sa.Column("calorie_input_snapshot", sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        "ck_workout_sessions_calorie_source",
        "workout_sessions",
        "calorie_source_code IS NULL OR "
        "calorie_source_code IN ('WEARABLE','MET_ESTIMATE','UNAVAILABLE')",
    )
    # A number without its provenance is what this migration exists to prevent.
    op.create_check_constraint(
        "ck_workout_sessions_calorie_provenance",
        "workout_sessions",
        "estimated_calories_burned IS NULL OR calorie_source_code IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workout_sessions_calorie_provenance", "workout_sessions", type_="check")
    op.drop_constraint("ck_workout_sessions_calorie_source", "workout_sessions", type_="check")
    op.drop_column("workout_sessions", "calorie_input_snapshot")
    op.drop_column("workout_sessions", "calorie_policy_version")
    op.drop_column("workout_sessions", "calorie_source_code")
    op.drop_constraint(
        "ck_weekly_reports_safety_stopped_nonnegative", "weekly_reports", type_="check"
    )
    op.drop_column("weekly_reports", "safety_stopped_session_count")
