"""Alembic must migrate the database the caller named, not the configured one.

`backend/migrations/env.py` used to overwrite `sqlalchemy.url` from settings on every
run. A fixture that selected a database with `config.set_main_option(...)` -- the way
Alembic's own API says to -- was silently redirected to whatever `DATABASE_URL` pointed
at, and the migration output named the revision but never the target. Running the
integration suite locally therefore migrated the deployed database.

The guard lives here rather than in a unit test because it only means anything when
`env.py` actually opens a connection.
"""

import os

import pytest
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from backend.tests.integration.test_migrations import ALEMBIC_CONFIG


def _connected_url(config: Config) -> str:
    """Run env.py far enough to see which database it opened, without migrating."""

    script = ScriptDirectory.from_config(config)
    seen: dict[str, str] = {}

    def capture(_rev: object, context: object) -> list[object]:
        seen["url"] = context.connection.engine.url.render_as_string(  # type: ignore[attr-defined]
            hide_password=True
        )
        return []

    with EnvironmentContext(config, script, fn=capture):
        script.run_env()
    return seen["url"]


@pytest.mark.integration
def test_env_uses_the_url_the_caller_set() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    expected = make_url(database_url).database
    if not (expected or "").endswith("_test"):
        pytest.fail("Migration tests require a dedicated *_test database")

    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("sqlalchemy.url", database_url)

    assert make_url(_connected_url(config)).database == expected


@pytest.mark.integration
def test_env_still_falls_back_to_settings_when_no_url_is_given() -> None:
    """Plain `alembic upgrade head` must keep working off the configured DATABASE_URL."""

    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    config = Config(str(ALEMBIC_CONFIG))
    assert not config.get_main_option("sqlalchemy.url")

    # DATABASE_URL is what the fallback reads; point it at the test database so this
    # assertion never opens a deployed one.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        from backend.app.core.config import get_settings

        get_settings.cache_clear()
        assert make_url(_connected_url(config)).database == make_url(database_url).database
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
