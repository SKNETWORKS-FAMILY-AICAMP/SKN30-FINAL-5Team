"""Create the empty backend migration baseline.

Revision ID: 0001_backend_baseline
Revises:
Create Date: 2026-08-13
"""

from collections.abc import Sequence

revision: str = "0001_backend_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the migration root without creating product tables."""


def downgrade() -> None:
    """Return to the pre-baseline state."""
