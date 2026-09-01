"""Add the pain area to the exercise alternative relation identity.

Revision ID: 0030_alternative_pain_area_key
Revises: 0029_routine_duration_tolerance
Create Date: 2026-08-30

Migration 0028 added ``condition_code`` to
``uq_exercise_alternatives_relation`` so a source/target pair could carry one
relation per NRS band. The reviewed data is keyed by pain area as well: the same
pair is approved for several areas at the same band, with its own target
strategy each time. Without the area in the key those relations collide, which
would drop 82 of the 1,104 reviewed v2.0.2 relations and 300 of the 520 v2.0.1
discomfort relations at import.

The lookup contract in docs/DATA_MODEL.md already reads a relation by
``pain_discomfort_area_code + condition_code``, so the identity has to include
both. Equipment and location relations leave the column NULL and are unaffected.

Widening a unique key never rejects rows the narrower key accepted, so the
upgrade needs no backfill. The downgrade re-narrows the key and therefore fails
while area-distinguished relations exist; keep this constraint and use a
forward-fix migration in that case.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_alternative_pain_area_key"
down_revision: str | None = "0029_routine_duration_tolerance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RELATION_COLUMNS = [
    "alternative_set_version_code",
    "source_exercise_id",
    "alternative_exercise_id",
    "reason_code",
    "goal_preservation_code",
    "rule_version",
    "condition_code",
]


def upgrade() -> None:
    op.drop_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        [*_RELATION_COLUMNS, "pain_discomfort_area_code"],
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM exercise_alternatives
            GROUP BY alternative_set_version_code, source_exercise_id,
                     alternative_exercise_id, reason_code, goal_preservation_code,
                     rule_version, condition_code
            HAVING count(DISTINCT pain_discomfort_area_code) > 1
          ) THEN
            RAISE EXCEPTION
              '0030 downgrade requires forward-fix while alternatives are '
              'distinguished by pain_discomfort_area_code';
          END IF;
        END $$;
        """
    )
    op.drop_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_exercise_alternatives_relation",
        "exercise_alternatives",
        _RELATION_COLUMNS,
    )
