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
BUNDLE_CATALOGS = (Path("data/generated/exercise-catalog-seed-merged-mvp-v0.4.0"),)
BUNDLE_SAFETY = Path("data/generated/exercise-safety-rules-merged-mvp-v0.5.0")
BUNDLE_ALTERNATIVES = Path("data/generated/exercise-alternatives-merged-mvp-v0.4.0")
BUNDLE_PRESCRIPTIONS = Path("data/generated/exercise-prescriptions-merged-mvp-v0.1.0")


def test_migration_history_has_a_single_linear_head() -> None:
    config = Config(str(ALEMBIC_CONFIG))
    scripts = ScriptDirectory.from_config(config)

    # A second head means two branches were authored against the same parent, which
    # blocks every later migration until someone merges them by hand.
    assert scripts.get_heads() == ["0039_retire_calendar_integration"]
    assert scripts.get_revision("0039_retire_calendar_integration").down_revision == (
        "0035_onboarding_eligibility"
    )
    assert scripts.get_revision("0035_onboarding_eligibility").down_revision == (
        "0034_decision_input_idempotency"
    )
    assert scripts.get_revision("0034_decision_input_idempotency").down_revision == (
        "0033_media_s3_key_per_catalog"
    )
    assert scripts.get_revision("0033_media_s3_key_per_catalog").down_revision == (
        "0032_form_cue_provenance"
    )
    assert scripts.get_revision("0032_form_cue_provenance").down_revision == (
        "0031_catalog_v2_0_2_identity"
    )
    assert scripts.get_revision("0031_catalog_v2_0_2_identity").down_revision == (
        "0030_alternative_pain_area_key"
    )
    assert scripts.get_revision("0030_alternative_pain_area_key").down_revision == (
        "0029_routine_duration_tolerance"
    )
    assert scripts.get_revision("0029_routine_duration_tolerance").down_revision == (
        "0028_discomfort_alt_conditions"
    )
    assert scripts.get_revision("0028_discomfort_alt_conditions").down_revision == (
        "0027_catalog_media_assets"
    )
    assert scripts.get_revision("0027_catalog_media_assets").down_revision == (
        "0026_catalog_v2_code_set"
    )
    assert scripts.get_revision("0026_catalog_v2_code_set").down_revision == (
        "0025_v3_decision_persistence"
    )
    assert scripts.get_revision("0025_v3_decision_persistence").down_revision == (
        "0024_vector_index_registry"
    )
    assert scripts.get_revision("0024_vector_index_registry").down_revision == (
        "0023_v2_deliberation_store"
    )
    assert scripts.get_revision("0023_v2_deliberation_store").down_revision == (
        "0022_promote_merged_data"
    )
    assert scripts.get_revision("0022_promote_merged_data").down_revision == (
        "0021_merged_catalog_source"
    )
    assert scripts.get_revision("0021_merged_catalog_source").down_revision == (
        "0020_manual_availability"
    )
    assert scripts.get_revision("0020_manual_availability").down_revision == (
        "0019_decision_explanations"
    )
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
def test_completed_input_index_does_not_block_regenerations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unique input index must cover originals only.

    A regeneration re-runs the same immutable daily-context input on purpose and shares
    ``(user_id, daily_context_id, daily_context_version, input_hash)`` with its root. If the
    predicate covered every COMPLETED row, the second regeneration of a day would violate the
    index and the feature would break, so the predicate is asserted here rather than left to
    review.
    """

    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(database_url).database.endswith("_test"):
        pytest.fail("Migration tests require a dedicated *_test database")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")

    with create_engine(database_url).connect() as connection:
        indexdef = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_decision_runs_completed_input'"
            )
        ).scalar_one()

    # PostgreSQL re-renders the predicate with explicit casts, so assert on the parts
    # that carry the contract rather than on exact formatting.
    normalized = " ".join(indexdef.split()).lower()
    assert "unique index" in normalized
    assert "(user_id, daily_context_id, daily_context_version, input_hash)" in normalized
    assert "'completed'" in normalized
    # Legacy V1/V2 rows carry a NULL mode and must stay covered as originals.
    assert "coalesce(generation_mode_code" in normalized
    assert "'original'" in normalized


_CALENDAR_TABLES = (
    "calendar_connections",
    "calendar_event_links",
    "calendar_oauth_requests",
    "calendar_rate_limit_counters",
)


@pytest.mark.integration
def test_retiring_calendar_drops_its_tables_and_restores_them_on_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0039 must drop only the integration tables and be reversible.

    Both directions delegate to 0013, so this asserts the delegation actually runs rather
    than trusting that the two revisions stay in step. The rollback half matters because a
    drop migration that cannot be undone strands anyone who needs to step back past it.
    """

    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(database_url).database.endswith("_test"):
        pytest.fail("Migration tests require a dedicated *_test database")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_CONFIG))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        present = set(inspect(connection).get_table_names())
    assert not (present & set(_CALENDAR_TABLES))
    # The in-app monthly record calendar is derived from workout sessions, so the
    # retirement must leave that source untouched.
    assert "workout_sessions" in present

    command.downgrade(config, "-1")
    with engine.connect() as connection:
        restored = set(inspect(connection).get_table_names())
        indexes = {
            name
            for table in _CALENDAR_TABLES
            for name in (index["name"] for index in inspect(connection).get_indexes(table))
            if name
        }
    assert set(_CALENDAR_TABLES) <= restored
    assert "uq_calendar_connections_token_secret_ref" in indexes

    command.upgrade(config, "head")
    with engine.connect() as connection:
        final = set(inspect(connection).get_table_names())
    assert not (final & set(_CALENDAR_TABLES))


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
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        # The calendar integration tables are absent at head; 0039 retired them.
        assert {
            "decision_explanations",
            "decision_deliberations",
            "agent_proposal_revisions",
            "agent_review_events",
            "vector_index_registry",
            "decision_constraint_envelopes",
            "decision_exercise_pools",
            "decision_exercise_retrievals",
            "decision_coordination_attempts",
            "plan_integrity_validations",
            "exercise_safety_rules",
            "exercise_alternatives",
            "exercise_media_assets",
        }.issubset(inspector.get_table_names())
        assert {
            "id",
            "catalog_version_id",
            "exercise_id",
            "s3_key",
            "media_status",
            "rights_review_status",
            "rights_reviewer",
            "rights_reviewed_at",
            "rights_evidence_reference",
            "media_set_version_code",
            "source_manifest_hash",
            "source_metadata",
            "approval_metadata",
            "created_at",
        } == {column["name"] for column in inspector.get_columns("exercise_media_assets")}
        assert {
            "root_decision_run_id",
            "parent_decision_run_id",
            "generation_mode_code",
            "regeneration_sequence",
            "decision_engine_code",
            "langchain_contract_version",
            "langgraph_contract_version",
        }.issubset({column["name"] for column in inspector.get_columns("decision_runs")})
        assert {
            "proposal_hash",
            "prompt_version",
            "provider_code",
            "model_code",
            "output_schema_version",
            "attempt_number",
            "invocation_status_code",
            "latency_ms",
        }.issubset({column["name"] for column in inspector.get_columns("agent_proposals")})
        assert {
            "id",
            "catalog_version_id",
            "collection_name",
            "vector_index_version",
            "source_manifest_hash",
            "embedding_model_version",
            "embedding_input_schema_version",
            "distance_metric_code",
            "vector_dimension",
            "build_hash",
            "status_code",
            "built_at",
            "activated_at",
            "created_at",
        } == {column["name"] for column in inspector.get_columns("vector_index_registry")}
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("vector_index_registry")
        } == {"uq_vector_index_registry_version"}
        assert {
            "id",
            "decision_run_id",
            "policy_version_id",
            "deliberation_schema_version",
            "graph_version",
            "round_count",
            "round_two_status_code",
            "conflict_detector_version",
            "precedence_version",
            "conflict_codes",
            "conflict_hash",
            "created_at",
        } == {column["name"] for column in inspector.get_columns("decision_deliberations")}
        assert {
            "id",
            "decision_run_id",
            "deliberation_id",
            "source_proposal_id",
            "baseline_revision_id",
            "policy_version_id",
            "round_number",
            "agent_type_code",
            "proposal_status_code",
            "proposal_schema_version",
            "proposal_payload",
            "proposal_hash",
            "created_at",
        } == {column["name"] for column in inspector.get_columns("agent_proposal_revisions")}
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("agent_proposal_revisions")
        } == {"uq_agent_proposal_revisions_run_round_type"}
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("agent_review_events")
        } == {"uq_agent_review_events_run_round_type"}
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
        catalog_checks = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspector.get_check_constraints("catalog_versions")
        }
        exercise_checks = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspector.get_check_constraints("exercises")
        }
        routine_day_checks = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspector.get_check_constraints("routine_days")
        }
        assert "catalog-v2" in catalog_checks["ck_catalog_versions_code_set_version"]
        assert "gymvisual" in exercise_checks["ck_exercises_source_track_code"]
        assert "ck_routine_days_exact_duration" not in routine_day_checks
        assert "300" in routine_day_checks["ck_routine_days_duration_tolerance"]
        alternative_relation_key = next(
            constraint
            for constraint in inspector.get_unique_constraints("exercise_alternatives")
            if constraint["name"] == "uq_exercise_alternatives_relation"
        )
        assert {"condition_code", "pain_discomfort_area_code"}.issubset(
            alternative_relation_key["column_names"]
        )
        with engine.connect() as connection:
            body_focus_codes = set(
                connection.scalars(
                    text(
                        "SELECT code FROM body_focuses "
                        "WHERE code IN ('CHEST', 'BACK', 'SHOULDERS', 'BICEPS', 'TRICEPS', "
                        "'FOREARMS', 'GLUTES', 'QUADRICEPS', 'HAMSTRINGS', 'CALVES', "
                        "'CORE', 'FULL_BODY', 'CARDIO', 'MOBILITY')"
                    )
                )
            )
            policy_statuses = dict(
                connection.execute(
                    text(
                        "SELECT version_code, status_code FROM decision_policy_versions "
                        "WHERE version_code IN ("
                        "'decision-policy-v1', 'decision-policy-v2', 'decision-policy-v3')"
                    )
                ).all()
            )
        assert body_focus_codes == {
            "CHEST",
            "BACK",
            "SHOULDERS",
            "BICEPS",
            "TRICEPS",
            "FOREARMS",
            "GLUTES",
            "QUADRICEPS",
            "HAMSTRINGS",
            "CALVES",
            "CORE",
            "FULL_BODY",
            "CARDIO",
            "MOBILITY",
        }
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
    monkeypatch.setattr(
        "backend.app.db.repositories.catalog.get_catalog_approval",
        lambda *_args: None,
    )
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_CONFIG))
    command.downgrade(config, "base")
    command.upgrade(config, "0021_merged_catalog_source")
    engine = create_engine(test_database_url)
    try:
        with Session(engine) as session:
            CatalogDataBundleImporter(CatalogRepository(), "test").import_bundle(
                session,
                BUNDLE_CATALOGS,
                BUNDLE_SAFETY,
                BUNDLE_ALTERNATIVES,
                BUNDLE_PRESCRIPTIONS,
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
                == 282
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
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM catalog_versions "
                        "WHERE version_code = 'merged-mvp-v0.4.0' "
                        "AND review_method_code = 'DOMAIN_REVIEWER' "
                        "AND status_interpretation_code = 'PRODUCTION_APPROVED'"
                    )
                )
                == 1
            )
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        get_settings.cache_clear()
