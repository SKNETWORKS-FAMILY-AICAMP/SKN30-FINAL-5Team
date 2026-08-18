import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseAlternative,
    ExerciseSafetyRule,
)
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import CatalogDataBundleImporter, CatalogImporter

ALEMBIC_CONFIG = Path("backend/alembic.ini")
GENERATED_ARTIFACT = Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0")
BUNDLE_CATALOGS = (
    Path("data/generated/exercise-catalog-seed-kspo-mvp-v0.2.0"),
    Path("data/generated/exercise-catalog-seed-wger-mvp-v0.2.0"),
    Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0"),
    Path("data/generated/exercise-catalog-seed-wger-tranche3-v0.1.0"),
)
BUNDLE_SAFETY = Path("data/generated/exercise-safety-rules-mvp-v0.3.0")
BUNDLE_ALTERNATIVES = Path("data/generated/exercise-alternatives-mvp-v0.2.0")


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not make_url(test_database_url).database.endswith("_test"):
        pytest.fail("Catalog repository tests require a dedicated *_test database")

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
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_imports_catalog_atomically_and_is_idempotent(postgres_session: Session) -> None:
    importer = CatalogImporter(CatalogRepository(), "test")

    first = importer.import_artifact(postgres_session, GENERATED_ARTIFACT)
    second = importer.import_artifact(postgres_session, GENERATED_ARTIFACT)

    assert first.imported is True
    assert first.exercise_record_count == 3
    assert second.imported is False
    assert second.catalog_version_id == first.catalog_version_id
    assert postgres_session.scalar(select(func.count()).select_from(CatalogVersion)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(Exercise)) == 3
    version = postgres_session.get(CatalogVersion, first.catalog_version_id)
    assert version is not None
    assert version.generator_version == "0.1.0"
    assert version.code_set_version == "mvp-v1"
    assert version.production_eligible is False
    assert version.manifest_metadata["files"][0]["records"] == 3


@pytest.mark.integration
def test_repository_failure_rolls_back_catalog_and_exercises(
    postgres_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = CatalogRepository()
    original_create = repository.create_from_artifact

    def fail_after_flush(session: Session, artifact: object) -> CatalogVersion:
        original_create(session, artifact)  # type: ignore[arg-type]
        raise RuntimeError("synthetic repository failure")

    monkeypatch.setattr(repository, "create_from_artifact", fail_after_flush)
    importer = CatalogImporter(repository, "test")

    with pytest.raises(RuntimeError, match="synthetic repository failure"):
        importer.import_artifact(postgres_session, GENERATED_ARTIFACT)

    assert postgres_session.scalar(select(func.count()).select_from(CatalogVersion)) == 0
    assert postgres_session.scalar(select(func.count()).select_from(Exercise)) == 0


@pytest.mark.integration
def test_imports_complete_bundle_with_metadata_and_is_idempotent(
    postgres_session: Session,
) -> None:
    importer = CatalogDataBundleImporter(CatalogRepository(), "test")

    first = importer.import_bundle(
        postgres_session, BUNDLE_CATALOGS, BUNDLE_SAFETY, BUNDLE_ALTERNATIVES
    )
    second = importer.import_bundle(
        postgres_session, BUNDLE_CATALOGS, BUNDLE_SAFETY, BUNDLE_ALTERNATIVES
    )

    assert first.safety_rules.record_count == 354
    assert first.alternatives.record_count == 238
    assert second.safety_rules.imported is False
    assert second.alternatives.imported is False
    assert postgres_session.scalar(select(func.count()).select_from(CatalogVersion)) == 4
    assert postgres_session.scalar(select(func.count()).select_from(Exercise)) == 56
    assert postgres_session.scalar(select(func.count()).select_from(ExerciseSafetyRule)) == 354
    assert postgres_session.scalar(select(func.count()).select_from(ExerciseAlternative)) == 238
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(ExerciseSafetyRule)
            .where(ExerciseSafetyRule.production_eligible.is_(True))
        )
        == 0
    )
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(ExerciseAlternative)
            .where(ExerciseAlternative.production_eligible.is_(True))
        )
        == 0
    )
    safety = postgres_session.scalar(select(ExerciseSafetyRule).limit(1))
    alternative = postgres_session.scalar(select(ExerciseAlternative).limit(1))
    assert safety is not None and "catalog_seed_artifacts" in safety.source_metadata["source"]
    assert alternative is not None and "input_artifacts" in alternative.source_metadata["source"]
