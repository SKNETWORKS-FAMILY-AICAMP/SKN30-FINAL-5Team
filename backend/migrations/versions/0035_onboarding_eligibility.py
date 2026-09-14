"""Add the P1-A onboarding eligibility persistence contract.

Revision ID: 0035_onboarding_eligibility
Revises: 0034_decision_input_idempotency
"""

import sqlalchemy as sa
from alembic import op

revision = "0035_onboarding_eligibility"
down_revision = "0034_decision_input_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable preserves legacy profiles without decrypting or backfilling
    # sensitive birthdate data during the migration.
    op.add_column(
        "user_profiles", sa.Column("medical_exercise_restriction", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "user_profiles", sa.Column("eligibility_result_code", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "user_profiles", sa.Column("weekly_target_sessions", sa.SmallInteger(), nullable=True)
    )
    op.create_check_constraint(
        "ck_user_profiles_eligibility_result",
        "user_profiles",
        "eligibility_result_code IS NULL OR eligibility_result_code IN "
        "('ELIGIBLE', 'OUT_OF_SCOPE_AGE', 'OUT_OF_SCOPE_MEDICAL_MANAGEMENT')",
    )
    op.create_check_constraint(
        "ck_user_profiles_weekly_target_sessions",
        "user_profiles",
        "weekly_target_sessions IS NULL OR weekly_target_sessions BETWEEN 1 AND 7",
    )
    op.create_table(
        "user_terms_agreements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("terms_version", sa.String(length=64), nullable=False),
        sa.Column("terms_agreed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "terms_version", name="uq_user_terms_agreement"),
    )
    op.create_index("ix_user_terms_agreements_user_id", "user_terms_agreements", ["user_id"])
    op.create_table(
        "user_persistent_pains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("body_area_code", sa.String(length=64), nullable=False),
        sa.Column("intensity_score", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "intensity_score BETWEEN 1 AND 10", name="ck_user_persistent_pains_intensity"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["body_area_code"], ["body_areas.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "body_area_code", name="uq_user_persistent_pain_area"),
    )
    op.create_index("ix_user_persistent_pains_user_id", "user_persistent_pains", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_persistent_pains_user_id", table_name="user_persistent_pains")
    op.drop_table("user_persistent_pains")
    op.drop_index("ix_user_terms_agreements_user_id", table_name="user_terms_agreements")
    op.drop_table("user_terms_agreements")
    op.drop_constraint("ck_user_profiles_weekly_target_sessions", "user_profiles", type_="check")
    op.drop_constraint("ck_user_profiles_eligibility_result", "user_profiles", type_="check")
    op.drop_column("user_profiles", "weekly_target_sessions")
    op.drop_column("user_profiles", "eligibility_result_code")
    op.drop_column("user_profiles", "medical_exercise_restriction")
