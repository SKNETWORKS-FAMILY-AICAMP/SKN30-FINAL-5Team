"""Let a user edit the day's plan without overwriting what the agents decided.

Revision ID: 0041_user_plan_revisions
Revises: 0040_weekly_safety_and_calorie
Create Date: 2026-09-04

`DOMAIN_RULES.md` 11.2 allows a user to change set and repetition counts and to reorder
exercises inside a phase, and requires the result to be stored as a user-edited plan so
the record stays reproducible.

The edit is kept beside the agent's own numbers rather than on top of them. `plan_items`
already holds what the decision prescribed, and that is the evidence a past decision is
replayed from (`AGENTS.md` 12); overwriting it would make the run irreproducible the
moment a user touched a set count. Every added column is a nullable override, so a plan
with no user edit is byte-identical to what it was, and reads resolve the effective value
with COALESCE.

`plan_candidates.user_revision_sequence` is the optimistic-concurrency token the edit
endpoints require. It starts at 0, which is what an unedited plan reports, so existing
rows need no backfill beyond the server default.

Sequence uniqueness for the override is a partial index rather than a constraint: a
reorder swaps positions, so writers null the column out before writing the new order.

The endpoint allowlist on `mutation_idempotency_records` gains the two edit endpoints,
and `PATCH_WORKOUT_SESSION_STOP` with them. That last one is a fix, not a feature: the
stop endpoint has been writing an idempotency record under that code since P1-C while the
constraint still rejected it, so every workout stop failed on PostgreSQL. Unit and API
tests use a fake repository, which is why it survived.

Additive in both directions; the rollback drops only what this adds. It is safe to run
against a database that already carries user edits, but those edits are then lost, which
is why the columns are dropped rather than emptied first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_user_plan_revisions"
down_revision: str | None = "0040_weekly_safety_and_calorie"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ITEM_OVERRIDES = (
    "user_sequence",
    "user_sets",
    "user_reps",
    "user_work_seconds_per_set",
    "user_work_seconds",
    "user_rest_seconds",
)

_CANDIDATE_COLUMNS = (
    "user_revision_sequence",
    "user_revised_estimated_duration_seconds",
    "user_revision_policy_version",
    "user_revised_at",
)

_EXISTING_ENDPOINTS = (
    "'PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES','PUT_DAILY_CONTEXT',"
    "'POST_DECISIONS','POST_DECISION_SELECTION',"
    "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
    "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
    "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
    "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK',"
    "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT',"
    "'POST_WEEKLY_PLAN','POST_WEEKLY_PLAN_REVISION','DELETE_ME','PATCH_ME_PROFILE'"
)

_ADDED_ENDPOINTS = (
    "'PATCH_WORKOUT_SESSION_STOP','PATCH_DECISION_PLAN_ITEM','PUT_DECISION_PLAN_ITEM_ORDER'"
)


def upgrade() -> None:
    for name in _ITEM_OVERRIDES:
        op.add_column("plan_items", sa.Column(name, sa.Integer(), nullable=True))

    # A user edit lowers or raises volume; it never turns a count into zero or a
    # negative. Rejecting that at the API alone would leave the invariant to one
    # caller, and the table is what the plan is read back from.
    for name in ("user_sequence", "user_sets", "user_work_seconds_per_set"):
        op.create_check_constraint(
            f"ck_plan_items_{name}_positive",
            "plan_items",
            f"{name} IS NULL OR {name} > 0",
        )
    op.create_check_constraint(
        "ck_plan_items_user_reps_positive",
        "plan_items",
        "user_reps IS NULL OR user_reps > 0",
    )
    for name in ("user_work_seconds", "user_rest_seconds"):
        op.create_check_constraint(
            f"ck_plan_items_{name}_nonnegative",
            "plan_items",
            f"{name} IS NULL OR {name} >= 0",
        )
    op.create_index(
        "uq_plan_items_candidate_user_sequence",
        "plan_items",
        ["plan_candidate_id", "user_sequence"],
        unique=True,
        postgresql_where=sa.text("user_sequence IS NOT NULL"),
    )

    op.add_column(
        "plan_candidates",
        sa.Column(
            "user_revision_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "plan_candidates",
        sa.Column("user_revised_estimated_duration_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "plan_candidates",
        sa.Column("user_revision_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "plan_candidates",
        sa.Column("user_revised_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_plan_candidates_user_revision_sequence",
        "plan_candidates",
        "user_revision_sequence >= 0",
    )
    # An unedited plan carries none of the revision metadata, and an edited one
    # carries all of it. Allowing half of it would leave a plan that claims a user
    # edit with nothing recording which policy produced it.
    op.create_check_constraint(
        "ck_plan_candidates_user_revision_shape",
        "plan_candidates",
        "(user_revision_sequence = 0 AND user_revised_at IS NULL "
        "AND user_revision_policy_version IS NULL "
        "AND user_revised_estimated_duration_seconds IS NULL) OR "
        "(user_revision_sequence > 0 AND user_revised_at IS NOT NULL "
        "AND user_revision_policy_version IS NOT NULL "
        "AND user_revised_estimated_duration_seconds IS NOT NULL)",
    )

    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        f"endpoint_code IN ({_EXISTING_ENDPOINTS},{_ADDED_ENDPOINTS})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    # Rows written under the newly allowed codes would fail the narrower constraint, so
    # they go first. Losing them costs replay protection on requests already answered,
    # which is the price of moving backwards past the release that allowed them.
    op.execute(
        f"DELETE FROM mutation_idempotency_records WHERE endpoint_code IN ({_ADDED_ENDPOINTS})"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        f"endpoint_code IN ({_EXISTING_ENDPOINTS})",
    )

    op.drop_constraint("ck_plan_candidates_user_revision_shape", "plan_candidates", type_="check")
    op.drop_constraint(
        "ck_plan_candidates_user_revision_sequence", "plan_candidates", type_="check"
    )
    for name in reversed(_CANDIDATE_COLUMNS):
        op.drop_column("plan_candidates", name)

    op.drop_index("uq_plan_items_candidate_user_sequence", table_name="plan_items")
    for name in ("user_work_seconds", "user_rest_seconds"):
        op.drop_constraint(f"ck_plan_items_{name}_nonnegative", "plan_items", type_="check")
    op.drop_constraint("ck_plan_items_user_reps_positive", "plan_items", type_="check")
    for name in ("user_sequence", "user_sets", "user_work_seconds_per_set"):
        op.drop_constraint(f"ck_plan_items_{name}_positive", "plan_items", type_="check")
    for name in reversed(_ITEM_OVERRIDES):
        op.drop_column("plan_items", name)
