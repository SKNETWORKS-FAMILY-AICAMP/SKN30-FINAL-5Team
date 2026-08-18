"""Allow idempotency records for profile settings updates.

Revision ID: 0017_profile_settings
Revises: 0016_approve_safety_data
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_profile_settings"
down_revision: str | None = "0016_approve_safety_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXISTING_ENDPOINTS = (
    "'PUT_ME_ONBOARDING','PUT_ME_CONSENTS','POST_ROUTINES',"
    "'PUT_DAILY_CONTEXT','POST_DECISIONS','POST_DECISION_SELECTION',"
    "'PATCH_WORKOUT_SESSION_START','PATCH_WORKOUT_SESSION_ITEM',"
    "'POST_WORKOUT_TIMER_EVENT','POST_WORKOUT_ADDITIONAL_ACTIVITY',"
    "'POST_WORKOUT_SAFETY_EVENT','PATCH_WORKOUT_SESSION_FINISH',"
    "'PATCH_WORKOUT_SESSION_NOT_COMPLETED','POST_WORKOUT_FEEDBACK',"
    "'POST_WEEKLY_REPORT','POST_WEEKLY_REPORT_ACKNOWLEDGEMENT',"
    "'POST_WEEKLY_PLAN','POST_WEEKLY_PLAN_REVISION','DELETE_ME'"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        f"endpoint_code IN ({_EXISTING_ENDPOINTS},'PATCH_ME_PROFILE')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        type_="check",
    )
    op.execute("DELETE FROM mutation_idempotency_records WHERE endpoint_code = 'PATCH_ME_PROFILE'")
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        f"endpoint_code IN ({_EXISTING_ENDPOINTS})",
    )
