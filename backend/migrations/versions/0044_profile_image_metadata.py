"""Store private profile-image object metadata.

Revision ID: 0044_profile_image_metadata
Revises: 0043_banana_wallet_rewards
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_profile_image_metadata"
down_revision: str | None = "0043_banana_wallet_rewards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDEMPOTENCY_ENDPOINTS = (
    "endpoint_code IN ('PUT_ME_ONBOARDING', 'PUT_ME_CONSENTS', 'PATCH_ME_PROFILE', "
    "'POST_ROUTINES', 'PUT_DAILY_CONTEXT', 'POST_DECISIONS', "
    "'POST_DECISION_SELECTION', 'PATCH_WORKOUT_SESSION_START', "
    "'PATCH_WORKOUT_SESSION_ITEM', 'POST_WORKOUT_TIMER_EVENT', "
    "'POST_WORKOUT_ADDITIONAL_ACTIVITY', 'POST_WORKOUT_SAFETY_EVENT', "
    "'PATCH_WORKOUT_SESSION_STOP', 'PATCH_WORKOUT_SESSION_FINISH', "
    "'PATCH_WORKOUT_SESSION_NOT_COMPLETED', 'POST_WORKOUT_FEEDBACK', "
    "'POST_WEEKLY_REPORT', 'POST_WEEKLY_REPORT_ACKNOWLEDGEMENT', "
    "'POST_WEEKLY_PLAN', 'POST_WEEKLY_PLAN_REVISION', 'DELETE_ME', "
    "'PATCH_DECISION_PLAN_ITEM', 'PUT_DECISION_PLAN_ITEM_ORDER')"
)
_IDEMPOTENCY_ENDPOINTS_WITH_PROFILE_IMAGES = _IDEMPOTENCY_ENDPOINTS[:-1] + (
    ", 'POST_ME_PROFILE_IMAGE', 'DELETE_ME_PROFILE_IMAGE')"
)


def upgrade() -> None:
    op.add_column(
        "user_profiles", sa.Column("profile_image_object_key", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "user_profiles",
        sa.Column("profile_image_content_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "user_profiles", sa.Column("profile_image_byte_size", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_user_profiles_profile_image_metadata",
        "user_profiles",
        "(profile_image_object_key IS NULL AND "
        "profile_image_content_type IS NULL AND "
        "profile_image_byte_size IS NULL) OR "
        "(profile_image_object_key ~ '^profile-images/[0-9a-f-]+/[0-9a-f-]+\\.(jpg|png|webp)$' AND "
        "profile_image_content_type IN ('image/jpeg','image/png','image/webp') AND "
        "profile_image_byte_size > 0 AND profile_image_byte_size <= 10485760)",
    )
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint",
        "mutation_idempotency_records",
        _IDEMPOTENCY_ENDPOINTS_WITH_PROFILE_IMAGES,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", type_="check"
    )
    op.execute(
        "DELETE FROM mutation_idempotency_records WHERE endpoint_code IN "
        "('POST_ME_PROFILE_IMAGE', 'DELETE_ME_PROFILE_IMAGE')"
    )
    op.create_check_constraint(
        "ck_mutation_idempotency_endpoint", "mutation_idempotency_records", _IDEMPOTENCY_ENDPOINTS
    )
    op.drop_constraint("ck_user_profiles_profile_image_metadata", "user_profiles", type_="check")
    op.drop_column("user_profiles", "profile_image_byte_size")
    op.drop_column("user_profiles", "profile_image_content_type")
    op.drop_column("user_profiles", "profile_image_object_key")
