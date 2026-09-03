"""Drop the retired external calendar integration tables.

Revision ID: 0037_retire_calendar_integration
Revises: 0036_checkin_safety_recovery
Create Date: 2026-09-03

ADR-0016 retired the external calendar integration. The four tables 0013 created
only ever held provider connection state, so nothing in them is user workout data:
the in-app monthly record calendar is derived from `workout_sessions` and is not
touched here.

All four tables are empty on staging, so this drop loses no rows.

Both directions delegate to 0013 rather than restating its DDL: `upgrade` runs
0013's `downgrade` to drop the tables, and `downgrade` runs 0013's `upgrade` to
recreate them. Restating ~190 lines of table definitions, or even the drop order
alone, is a transcription risk with nothing to catch a mistake -- the first draft of
this file did exactly that and named an index that never existed. Delegating keeps
one definition of these tables and their index names.

0013 imports only SQLAlchemy and `alembic.op`, and `op` resolves against whichever
migration context is running, so executing it from here is equivalent to running it
in place.

Numbering note: this revision was authored as 0039 on top of 0035 while 0036-0038 were
held for the in-flight check-in, workout execution and feedback-loop work. Check-in landed
as 0036 first, so it is renumbered to 0037 and chains onto that head rather than opening a
second branch off 0035.
"""

import importlib.util
import pathlib
from collections.abc import Sequence

revision: str = "0037_retire_calendar_integration"
down_revision: str | None = "0036_checkin_safety_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_REVISION = "0013_calendar_persistence"


def _calendar_persistence_module() -> object:
    """Load 0013 so the rollback reuses its table definitions verbatim."""

    path = pathlib.Path(__file__).with_name(f"{_SOURCE_REVISION}.py")
    spec = importlib.util.spec_from_file_location(f"_{_SOURCE_REVISION}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging guard
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    module = _calendar_persistence_module()
    module.downgrade()  # type: ignore[attr-defined]


def downgrade() -> None:
    module = _calendar_persistence_module()
    module.upgrade()  # type: ignore[attr-defined]
