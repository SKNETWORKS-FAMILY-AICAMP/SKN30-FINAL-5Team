import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from backend.app.core.config import get_settings

ALEMBIC_CONFIG = Path("backend/alembic.ini")


def test_migration_history_has_calendar_persistence_head() -> None:
    config = Config(str(ALEMBIC_CONFIG))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["0013_calendar_persistence_foundation"]
    assert scripts.get_revision("0013_calendar_persistence_foundation").down_revision == (
        "0012_account_deletion_retention"
    )
    assert scripts.get_revision("0012_account_deletion_retention").down_revision == (
        "0011_weekly_plan_revisions"
    )
    assert scripts.get_revision("0011_weekly_plan_revisions").down_revision == (
        "0010_weekly_report_flow"
    )
    assert scripts.get_revision("0010_weekly_report_flow").down_revision == (
        "0009_workout_session_outcomes"
    )
    assert scripts.get_revision("0009_workout_session_outcomes").down_revision == (
        "0008_workout_session_flow"
    )
    assert scripts.get_revision("0008_workout_session_flow").down_revision == (
        "0007_decision_persistence"
    )
    assert scripts.get_revision("0007_decision_persistence").down_revision == "0006_daily_contexts"
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
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        assert {
            "calendar_connections",
            "calendar_event_links",
            "calendar_oauth_requests",
            "calendar_rate_limit_counters",
        }.issubset(inspector.get_table_names())
        assert {column["name"] for column in inspector.get_columns("calendar_connections")} == {
            "id",
            "user_id",
            "provider_code",
            "provider_subject",
            "token_secret_ref",
            "status_code",
            "granted_at",
            "revoked_at",
            "created_at",
            "updated_at",
        }
    finally:
        engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
