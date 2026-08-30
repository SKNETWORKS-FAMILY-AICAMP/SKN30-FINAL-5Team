"""Relax the routine day duration CHECK to the approved tolerance window.

Revision ID: 0029_routine_duration_tolerance
Revises: 0028_discomfort_alt_conditions
Create Date: 2026-08-30

Migration 0005 required ``estimated_duration_seconds`` to equal the requested
duration exactly. The approved duration policy (AGENTS.md section 7) lets a plan
land within five minutes of the request when the eligible pool cannot hit it
exactly, and the routine service already composes plans inside that window, so
the exact-match CHECK rejected plans the service is allowed to build.

Every existing row satisfies exact equality, which also satisfies the tolerance
window, so the upgrade needs no backfill. The downgrade is safe only while no
row uses the widened window; once one exists, keep this constraint and use a
forward-fix migration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_routine_duration_tolerance"
down_revision: str | None = "0028_discomfort_alt_conditions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with backend.app.domain.rules.duration.DURATION_TOLERANCE_SECONDS.
_TOLERANCE_SECONDS = 300


def upgrade() -> None:
    op.drop_constraint("ck_routine_days_exact_duration", "routine_days", type_="check")
    op.create_check_constraint(
        "ck_routine_days_duration_tolerance",
        "routine_days",
        f"abs(estimated_duration_seconds - requested_duration_minutes * 60) "
        f"<= {_TOLERANCE_SECONDS}",
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM routine_days
            WHERE estimated_duration_seconds <> requested_duration_minutes * 60
          ) THEN
            RAISE EXCEPTION
              '0029 downgrade requires forward-fix while routine days use the '
              '+/-{_TOLERANCE_SECONDS}s duration window';
          END IF;
        END $$;
        """
    )
    op.drop_constraint("ck_routine_days_duration_tolerance", "routine_days", type_="check")
    op.create_check_constraint(
        "ck_routine_days_exact_duration",
        "routine_days",
        "estimated_duration_seconds = requested_duration_minutes * 60",
    )
