import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    BodyArea,
    BodyFocus,
    CatalogVersion,
    Equipment,
    Exercise,
    ExerciseGoalTagLink,
    ExercisePrescriptionProfile,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import CatalogDataBundleImporter, CatalogImporter
from backend.scripts.catalog_activate import _routine_input_counts, activate, missing_review_fields
from backend.scripts.catalog_promote_v2 import DEFAULT_BUNDLE_DIRECTORY, promote_v2
from backend.scripts.demo_seed import DEMO_CATALOG_VERSION_CODE, seed_catalog

ALEMBIC_CONFIG = Path("backend/alembic.ini")
BUNDLE_CATALOG = Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0")
BUNDLE_VERSION_CODE = "kspo-tranche3-v0.1.0"
MERGED_CATALOGS = (Path("data/generated/exercise-catalog-seed-merged-mvp-v0.4.0"),)
MERGED_SAFETY = Path("data/generated/exercise-safety-rules-merged-mvp-v0.5.0")
MERGED_ALTERNATIVES = Path("data/generated/exercise-alternatives-merged-mvp-v0.4.0")
MERGED_PRESCRIPTIONS = Path("data/generated/exercise-prescriptions-merged-mvp-v0.1.0")
MERGED_VERSION_CODE = "merged-mvp-v0.4.0"


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Catalog activation tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(ALEMBIC_CONFIG)), "head")

    engine: Engine = create_engine(test_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        # The catalog importer commits its own transaction, so the rollback
        # above does not always reach it. Sibling integration modules assume an
        # empty catalog, so anything left behind has to go.
        try:
            with Session(engine) as cleanup, cleanup.begin():
                cleanup.execute(delete(CatalogVersion))
                for model in (
                    TrainingType,
                    BodyFocus,
                    MovementPattern,
                    Equipment,
                    Location,
                    BodyArea,
                ):
                    cleanup.execute(delete(model))
        finally:
            engine.dispose()
            get_settings.cache_clear()


def _import_bundle_catalog(session: Session) -> CatalogVersion:
    CatalogImporter(CatalogRepository(), "test").import_artifact(session, BUNDLE_CATALOG)
    catalog = session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == BUNDLE_VERSION_CODE)
    )
    assert catalog is not None
    return catalog


def _add_routine_inputs(session: Session, catalog: CatalogVersion) -> None:
    """Give an imported catalog the rows the routine query inner joins.

    The importer never writes these, so without them activation is refused for
    a reason unrelated to whatever a test is actually asserting.
    """
    exercise_id = session.scalar(
        select(Exercise.id).where(Exercise.catalog_version_id == catalog.id).limit(1)
    )
    assert exercise_id is not None
    session.add(
        ExerciseGoalTagLink(
            exercise_id=exercise_id,
            goal_code="GENERAL_FITNESS",
            role_eligibility_code="CORE",
            review_status_code="DOMAIN_APPROVED",
        )
    )
    session.add(
        ExercisePrescriptionProfile(
            exercise_id=exercise_id,
            goal_code="GENERAL_FITNESS",
            experience_level_code="BEGINNER",
            phase_code="MAIN",
            sets=3,
            reps=10,
            rest_seconds_per_set=60,
            intensity_code="MODERATE",
            prescription_version="test-v1",
            review_status_code="DOMAIN_APPROVED",
        )
    )
    session.flush()


@pytest.mark.integration
def test_imported_bundle_catalog_has_no_recorded_domain_review(
    postgres_session: Session,
) -> None:
    catalog = _import_bundle_catalog(postgres_session)

    assert catalog.review_method_code == "AGENT_ONLY"
    assert catalog.status_interpretation_code == "PIPELINE_COMPATIBILITY_ONLY"
    assert len(missing_review_fields(catalog)) == 2


@pytest.mark.integration
def test_unreviewed_catalog_is_refused_without_the_demo_override(
    postgres_session: Session,
) -> None:
    _add_routine_inputs(postgres_session, _import_bundle_catalog(postgres_session))

    with pytest.raises(SystemExit) as refusal:
        activate(postgres_session, BUNDLE_VERSION_CODE, now=datetime.now(UTC))

    message = str(refusal.value)
    assert "domain review is not recorded" in message
    assert "review_method_code" in message
    catalog = postgres_session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == BUNDLE_VERSION_CODE)
    )
    assert catalog is not None
    assert catalog.status_code == "DRAFT"
    assert catalog.production_eligible is False


@pytest.mark.integration
def test_catalog_without_routine_inputs_is_refused_even_with_the_override(
    postgres_session: Session,
) -> None:
    """An imported catalog activates into a state where no routine can be built,
    because the importer writes neither prescription profiles nor goal tag links."""
    _import_bundle_catalog(postgres_session)

    with pytest.raises(SystemExit) as refusal:
        activate(
            postgres_session,
            BUNDLE_VERSION_CODE,
            now=datetime.now(UTC),
            allow_unreviewed=True,
        )

    message = str(refusal.value)
    assert "no routine could be built from it" in message
    assert "exercise_prescription_profiles=0" in message
    assert "exercise_goal_tag_links=0" in message
    catalog = postgres_session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == BUNDLE_VERSION_CODE)
    )
    assert catalog is not None
    assert catalog.status_code == "DRAFT"


@pytest.mark.integration
def test_missing_catalog_is_refused(postgres_session: Session) -> None:
    with pytest.raises(SystemExit) as refusal:
        activate(postgres_session, "does-not-exist", now=datetime.now(UTC))

    assert "not found" in str(refusal.value)


@pytest.mark.integration
def test_demo_override_activates_and_records_the_missing_review(
    postgres_session: Session,
) -> None:
    _add_routine_inputs(postgres_session, _import_bundle_catalog(postgres_session))

    catalog = activate(
        postgres_session,
        BUNDLE_VERSION_CODE,
        now=datetime.now(UTC),
        allow_unreviewed=True,
    )

    assert catalog.status_code == "ACTIVE"
    assert catalog.production_eligible is True
    assert catalog.activated_at is not None
    activation = catalog.manifest_metadata["demo_activation"]
    assert activation["domain_review"] == "none - local demo only, not for production"
    assert len(activation["overridden_fields"]) == 2


@pytest.mark.integration
def test_activation_deprecates_the_catalog_it_replaces(postgres_session: Session) -> None:
    # Imported first: the importer opens its own transaction, which conflicts
    # with the one `seed_catalog` autobegins.
    _add_routine_inputs(postgres_session, _import_bundle_catalog(postgres_session))
    seed_catalog(postgres_session, datetime.now(UTC))
    postgres_session.flush()

    activate(
        postgres_session,
        BUNDLE_VERSION_CODE,
        now=datetime.now(UTC),
        allow_unreviewed=True,
    )

    active = postgres_session.scalars(
        select(CatalogVersion).where(CatalogVersion.status_code == "ACTIVE")
    ).all()
    assert [row.version_code for row in active] == [BUNDLE_VERSION_CODE]

    replaced = postgres_session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == DEMO_CATALOG_VERSION_CODE)
    )
    assert replaced is not None
    assert replaced.status_code == "DEPRECATED"
    assert replaced.production_eligible is False
    assert replaced.activated_at is None


@pytest.mark.integration
def test_reviewed_catalog_activates_without_the_override(postgres_session: Session) -> None:
    seed_catalog(postgres_session, datetime.now(UTC))
    postgres_session.flush()

    catalog = activate(postgres_session, DEMO_CATALOG_VERSION_CODE, now=datetime.now(UTC))

    assert catalog.status_code == "ACTIVE"
    assert catalog.production_eligible is True
    assert "demo_activation" not in catalog.manifest_metadata
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(CatalogVersion)
            .where(CatalogVersion.status_code == "ACTIVE")
        )
        == 1
    )


@pytest.mark.integration
def test_complete_merged_bundle_activates_without_override(
    postgres_session: Session,
) -> None:
    result = CatalogDataBundleImporter(CatalogRepository(), "test").import_bundle(
        postgres_session,
        MERGED_CATALOGS,
        MERGED_SAFETY,
        MERGED_ALTERNATIVES,
        MERGED_PRESCRIPTIONS,
    )

    catalog = activate(postgres_session, MERGED_VERSION_CODE, now=datetime.now(UTC))

    assert result.prescriptions.record_count == 68
    assert catalog.status_code == "ACTIVE"
    assert catalog.production_eligible is True
    assert catalog.review_method_code == "DOMAIN_REVIEWER"
    assert catalog.status_interpretation_code == "PRODUCTION_APPROVED"
    assert _routine_input_counts(postgres_session, catalog) == (36, 32)


@pytest.mark.integration
def test_v2_import_promote_then_activate_preserves_approval_packet(
    postgres_session: Session,
) -> None:
    result = promote_v2(postgres_session, DEFAULT_BUNDLE_DIRECTORY, app_env="test")

    catalog = activate(
        postgres_session,
        "exercise-catalog-v2.0.1-final",
        now=datetime.now(UTC),
    )

    assert result.safety_rules.record_count == 394
    assert result.alternatives.record_count == 285
    assert result.prescriptions.record_count == 239
    assert catalog.status_code == "ACTIVE"
    assert catalog.production_eligible is True
    approval = catalog.manifest_metadata["production_approval"]
    assert approval["waiver"]["reference"] == "V2-PROMOTION-WAIVER-2026-08-25-R01"
