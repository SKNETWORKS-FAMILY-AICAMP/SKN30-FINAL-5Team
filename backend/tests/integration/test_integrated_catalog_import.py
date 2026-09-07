"""Real PostgreSQL check for the v2.0.7 integrated DRAFT importer."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db.models.catalog import CatalogVersion, Exercise
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import IntegratedCatalogBundleImporter

ALEMBIC_CONFIG = Path("backend/alembic.ini")
BUNDLE = Path("data/generated/integrated-catalog-v2.0.7-draft/backend_bundle")
VERSION_CODE = "exercise-catalog-v2.0.7-draft"


@pytest.mark.integration
def test_integrated_catalog_import_is_idempotent_on_postgresql() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    assert (make_url(database_url).database or "").endswith("_test")

    engine = create_engine(database_url)
    try:
        assert engine.dialect.name == "postgresql"
        expected_head = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG))).get_current_head()
        with engine.connect() as connection:
            assert (
                connection.scalar(text("select version_num from alembic_version")) == expected_head
            )

        importer = IntegratedCatalogBundleImporter(CatalogRepository(), "test")
        with Session(engine) as session:
            with session.begin():
                session.execute(
                    delete(CatalogVersion).where(CatalogVersion.version_code == VERSION_CODE)
                )

            first = importer.import_bundle(session, BUNDLE)
            assert first.imported is True
            assert first.exercise_record_count == 237
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(CatalogVersion)
                    .where(CatalogVersion.version_code == VERSION_CODE)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Exercise)
                    .where(Exercise.catalog_version_id == first.catalog_version_id)
                )
                == 237
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Exercise)
                    .where(
                        Exercise.catalog_version_id == first.catalog_version_id,
                        Exercise.met_value.is_not(None),
                        Exercise.met_review_status_code == "DOMAIN_APPROVED",
                    )
                )
                == 237
            )

            # Scalar assertions start a read transaction; close it before the
            # importer opens its own idempotent write transaction again.
            session.commit()
            second = importer.import_bundle(session, BUNDLE)
            assert second.imported is False
            assert second.catalog_version_id == first.catalog_version_id
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Exercise)
                    .where(Exercise.catalog_version_id == first.catalog_version_id)
                )
                == 237
            )
    finally:
        engine.dispose()
