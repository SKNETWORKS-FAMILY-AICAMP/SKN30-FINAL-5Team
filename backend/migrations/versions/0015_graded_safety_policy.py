"""Install the graded safety decision policy version.

Revision ID: 0015_graded_safety_policy
Revises: 0014_catalog_derived_data
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_graded_safety_policy"
down_revision: str | None = "0014_catalog_derived_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE decision_policy_versions SET status_code = 'DEPRECATED' "
        "WHERE version_code = 'decision-policy-v1'"
    )
    op.execute(
        "INSERT INTO decision_policy_versions (id, version_code, status_code) "
        "VALUES ('00000000-0000-0000-0000-000000000015', "
        "'decision-policy-v2', 'ACTIVE') "
        "ON CONFLICT (version_code) DO UPDATE SET status_code = 'ACTIVE'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE decision_policy_versions SET status_code = 'DEPRECATED' "
        "WHERE version_code = 'decision-policy-v2'"
    )
    op.execute(
        "UPDATE decision_policy_versions SET status_code = 'ACTIVE' "
        "WHERE version_code = 'decision-policy-v1'"
    )
