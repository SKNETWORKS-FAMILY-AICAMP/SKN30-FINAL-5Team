import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from backend.app.core.config import get_settings

ALEMBIC_CONFIG = Path("backend/alembic.ini")


def test_migration_history_has_daily_context_head() -> None:
    config = Config(str(ALEMBIC_CONFIG))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["0006_daily_contexts"]
    assert scripts.get_revision("0006_daily_contexts").down_revision == "0005_routine_core"
    assert scripts.get_revision("0005_routine_core").down_revision == ("0004_onboarding_consent")
    assert scripts.get_revision("0004_onboarding_consent").down_revision == (
        "0003_identity_auth_boundary"
    )
    assert scripts.get_revision("0003_identity_auth_boundary").down_revision == "0002_catalog_core"
    assert scripts.get_revision("0002_catalog_core").down_revision == "0001_backend_baseline"
    assert scripts.get_revision("0001_backend_baseline").down_revision is None


@pytest.mark.integration
def test_postgresql_migration_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Migration round trip requires a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_CONFIG))
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
