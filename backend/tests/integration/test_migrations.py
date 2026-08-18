import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import CatalogDataBundleImporter

ALEMBIC_CONFIG = Path("backend/alembic.ini")
BUNDLE_CATALOGS = (
    Path("data/generated/exercise-catalog-seed-kspo-mvp-v0.2.0"),
    Path("data/generated/exercise-catalog-seed-wger-mvp-v0.2.0"),
    Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0"),
    Path("data/generated/exercise-catalog-seed-wger-tranche3-v0.1.0"),
)
BUNDLE_SAFETY = Path("data/generated/exercise-safety-rules-mvp-v0.3.0")
BUNDLE_ALTERNATIVES = Path("data/generated/exercise-alternatives-mvp-v0.2.0")


def test_migration_history_has_decision_explanation_head() -> None:
    config = Config(str(ALEMBIC_CONFIG))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["0019_decision_explanations"]
    assert scripts.get_revision("0019_decision_explanations").down_revision == (
        "0018_agent_proposal_policy"
    )
    assert scripts.get_revision("0018_agent_proposal_policy").down_revision == (
        "0017_profile_settings"
    )
    assert scripts.get_revision("0017_profile_settings").down_revision == (
        "0016_approve_safety_data"
    )
    assert scripts.get_revision("0016_approve_safety_data").down_revision == (
        "0015_graded_safety_policy"
    )
    assert scripts.get_revision("0014_catalog_derived_data").down_revision == (
        "0013_calendar_persistence"
    )
    assert scripts.get_revision("0013_calendar_persistence").down_revision == (
        "0012_account_deletion_retention"
    )
    assert all(len(revision.revision) <= 32 for revision in scripts.walk_revisions())
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
            "decision_explanations",
            "exercise_safety_rules",
            "exercise_alternatives",
        }.issubset(inspector.get_table_names())
        assert {column["name"] for column in inspector.get_columns("decision_explanations")} == {
            "id",
            "decision_run_id",
            "source_code",
            "summary",
            "reason_codes",
            "agent_summaries",
            "safety_summary",
            "final_adjustment_reason",
            "coaching_style_code",
            "template_version",
            "prompt_version",
            "model_code",
            "fallback_reason_code",
            "created_at",
        }
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
        with engine.connect() as connection:
            policy_statuses = dict(
                connection.execute(
                    text(
                        "SELECT version_code, status_code FROM decision_policy_versions "
                        "WHERE version_code IN ("
                        "'decision-policy-v1', 'decision-policy-v2', 'decision-policy-v3')"
                    )
                ).all()
            )
        assert policy_statuses == {
            "decision-policy-v1": "DEPRECATED",
            "decision-policy-v2": "DEPRECATED",
            "decision-policy-v3": "ACTIVE",
        }
    finally:
        engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.mark.integration
def test_approval_migration_promotes_an_existing_complete_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(test_database_url).database or "").endswith("_test"):
        pytest.fail("Approval migration test requires a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(
        "backend.app.db.repositories.catalog.get_derived_data_approval",
        lambda *_args: None,
    )
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_CONFIG))
    command.downgrade(config, "base")
    command.upgrade(config, "0015_graded_safety_policy")
    engine = create_engine(test_database_url)
    try:
        with Session(engine) as session:
            CatalogDataBundleImporter(CatalogRepository(), "test").import_bundle(
                session,
                BUNDLE_CATALOGS,
                BUNDLE_SAFETY,
                BUNDLE_ALTERNATIVES,
            )
            session.commit()
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM exercise_safety_rules "
                        "WHERE production_eligible = true"
                    )
                )
                == 354
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM exercise_alternatives "
                        "WHERE production_eligible = true"
                    )
                )
                == 238
            )
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        get_settings.cache_clear()
