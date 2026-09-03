"""Give the integration suite a known starting state.

The suite passed on a fresh database and failed on the second run against the same one.
Several modules commit lookup rows, catalogs and users, and their teardowns only clean up
what they believe they own; a teardown that hits a foreign key rolls back silently and
leaves everything behind. The next run then collides on codes like `locations.HOME`.

CI never saw this because it provisions a new PostgreSQL service per job, so the failures
only ever showed up locally -- which is worse, because it trained everyone to read a red
integration run as noise.

Rebuilding the schema, rather than truncating, is deliberate: migrations seed
`body_areas`, `body_focuses`, `decision_policy_versions` and `user_available_locations`,
so emptying every table leaves the suite without rows it never inserts itself. Fixing the
individual teardowns was the other option, but the modules disagree about who owns the
shared lookup tables; a shared starting point settles that without making one module's
cleanup responsible for another's rows. Per-test isolation still comes from each module's
own transaction fixture.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ALEMBIC_CONFIG = Path("backend/alembic.ini")


@pytest.fixture(scope="session", autouse=True)
def reset_integration_database() -> Iterator[None]:
    """Rebuild the test schema once before the integration tests run.

    Skips silently when no test database is configured so unit-only runs are unaffected,
    and refuses to touch anything that is not a dedicated ``*_test`` database.
    """

    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        yield
        return
    if not (make_url(database_url).database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a dedicated *_test database")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.commit()
    finally:
        engine.dispose()

    config = Config(str(ALEMBIC_CONFIG))
    # Name the target explicitly. `env.py` falls back to the configured DATABASE_URL when
    # the caller sets nothing, and that fallback is how a local run once migrated a
    # deployed database.
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    yield
