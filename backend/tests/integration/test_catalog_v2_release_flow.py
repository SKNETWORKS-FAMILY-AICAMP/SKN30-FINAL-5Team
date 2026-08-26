import hashlib
import json
import os
import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    CatalogVersion,
    Exercise,
    ExerciseAlternative,
    ExerciseGoalTagLink,
    ExerciseMediaAsset,
    ExercisePrescriptionProfile,
    ExerciseSafetyRule,
)
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.modules.catalog.service import CatalogDataBundleImporter, CatalogImportError
from backend.scripts.catalog_activate import activate
from backend.scripts.catalog_promote_v2 import (
    APPROVED_BUNDLE_MANIFEST_SHA256,
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    DEFAULT_BUNDLE_DIRECTORY,
    V2_CATALOG_VERSION_CODE,
    promote_v2,
)

ALEMBIC_CONFIG = Path("backend/alembic.ini")


@pytest.fixture
def postgres_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    database_name = make_url(test_database_url).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("V2 release-flow tests require a dedicated *_test database")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    engine: Engine = create_engine(test_database_url)
    assert engine.dialect.name == "postgresql"
    expected_head = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG))).get_current_head()
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == expected_head
    with Session(engine) as cleanup, cleanup.begin():
        cleanup.execute(delete(CatalogVersion))

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


def _count(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _rewrite_bundle_manifest(
    bundle_directory: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> str:
    manifest_path = bundle_directory / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    manifest_path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.integration
def test_v2_release_import_draft_activate_and_replay_are_exact(
    postgres_session: Session,
) -> None:
    repository = CatalogRepository()

    first = promote_v2(postgres_session, DEFAULT_BUNDLE_DIRECTORY, app_env="test")
    draft = repository.get_by_version_code(postgres_session, V2_CATALOG_VERSION_CODE)

    assert draft is not None
    assert draft.status_code == "DRAFT"
    assert repository.get_approved_catalog(postgres_session) is None
    assert [item.exercise_record_count for item in first.catalogs] == [102]
    assert first.safety_rules.record_count == 394
    assert first.alternatives.record_count == 285
    assert first.prescriptions.record_count == 239
    assert _count(postgres_session, Exercise) == 102
    assert _count(postgres_session, ExerciseSafetyRule) == 394
    assert _count(postgres_session, ExerciseAlternative) == 285
    assert _count(postgres_session, ExerciseGoalTagLink) == 102
    assert _count(postgres_session, ExercisePrescriptionProfile) == 137
    assert _count(postgres_session, ExerciseMediaAsset) == 0
    postgres_session.commit()

    with postgres_session.begin():
        activated = activate(
            postgres_session,
            V2_CATALOG_VERSION_CODE,
            now=datetime(2026, 8, 26, tzinfo=UTC),
        )
        activated_at = activated.activated_at

    assert _count(postgres_session, CatalogVersion) == 1
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(CatalogVersion)
            .where(CatalogVersion.status_code == "ACTIVE")
        )
        == 1
    )
    approved = repository.get_approved_catalog(postgres_session)
    assert approved is not None
    rows = repository.list_approved_exercises(
        postgres_session,
        approved.catalog_version_id,
        body_area_code=None,
        equipment_code=None,
        training_type_code=None,
        difficulty_code=None,
        after_exercise_id=None,
        limit=200,
    )
    assert len(rows) == 102
    assert all(row.media_asset_key is None for row in rows)
    postgres_session.commit()

    second = promote_v2(postgres_session, DEFAULT_BUNDLE_DIRECTORY, app_env="test")
    with postgres_session.begin():
        reactivated = activate(
            postgres_session,
            V2_CATALOG_VERSION_CODE,
            now=datetime(2026, 8, 27, tzinfo=UTC),
        )

    assert all(item.imported is False for item in second.catalogs)
    assert second.safety_rules.imported is False
    assert second.alternatives.imported is False
    assert second.prescriptions.imported is False
    assert reactivated.activated_at == activated_at
    assert _count(postgres_session, Exercise) == 102
    assert _count(postgres_session, ExerciseSafetyRule) == 394
    assert _count(postgres_session, ExerciseAlternative) == 285
    assert _count(postgres_session, ExerciseGoalTagLink) == 102
    assert _count(postgres_session, ExercisePrescriptionProfile) == 137


@pytest.mark.integration
@pytest.mark.parametrize("invalid_contract", ["file_hash", "byte_count", "record_count", "version"])
def test_v2_release_rejects_invalid_bundle_without_partial_rows(
    postgres_session: Session,
    tmp_path: Path,
    invalid_contract: str,
) -> None:
    bundle_directory = tmp_path / "backend_bundle"
    shutil.copytree(DEFAULT_BUNDLE_DIRECTORY, bundle_directory)

    def mutate(manifest: dict[str, Any]) -> None:
        if invalid_contract == "file_hash":
            catalog_manifest = next(
                entry
                for entry in manifest["files"]
                if entry["path"] == "catalog/seed_manifest.json"
            )
            catalog_manifest["sha256"] = "0" * 64
        elif invalid_contract == "byte_count":
            catalog_manifest = next(
                entry
                for entry in manifest["files"]
                if entry["path"] == "catalog/seed_manifest.json"
            )
            catalog_manifest["bytes"] += 1
        elif invalid_contract == "record_count":
            manifest["summary"]["catalog_records"] = 101
        else:
            manifest["derived_set_versions"]["rule_set_version_code"] = "unapproved-v2"

    expected_hash = _rewrite_bundle_manifest(bundle_directory, mutate)
    importer = CatalogDataBundleImporter(
        CatalogRepository(),
        "test",
        v2_import=True,
        v2_taxonomy_registry_sha256=APPROVED_TAXONOMY_REGISTRY_SHA256,
    )

    with pytest.raises(CatalogImportError) as exc_info:
        importer.import_v2_bundle(
            postgres_session,
            bundle_directory,
            expected_bundle_manifest_sha256=expected_hash,
        )

    expected_codes = {
        "file_hash": "BUNDLE_FILE_INTEGRITY_MISMATCH",
        "byte_count": "BUNDLE_FILE_INTEGRITY_MISMATCH",
        "record_count": "BUNDLE_CONTRACT_MISMATCH",
        "version": "BUNDLE_CONTRACT_MISMATCH",
    }
    assert exc_info.value.code == expected_codes[invalid_contract]
    assert _count(postgres_session, CatalogVersion) == 0
    assert _count(postgres_session, Exercise) == 0
    assert _count(postgres_session, ExerciseSafetyRule) == 0
    assert _count(postgres_session, ExerciseAlternative) == 0


class _FailAfterSafetyRepository(CatalogRepository):
    def create_alternatives(self, session: Session, artifact: Any) -> None:
        raise RuntimeError("synthetic failure after catalog and safety writes")


@pytest.mark.integration
def test_v2_release_rolls_back_all_rows_after_middle_stage_failure(
    postgres_session: Session,
) -> None:
    importer = CatalogDataBundleImporter(
        _FailAfterSafetyRepository(),
        "test",
        v2_import=True,
        v2_taxonomy_registry_sha256=APPROVED_TAXONOMY_REGISTRY_SHA256,
    )

    with pytest.raises(RuntimeError, match="after catalog and safety writes"):
        importer.import_v2_bundle(
            postgres_session,
            DEFAULT_BUNDLE_DIRECTORY,
            expected_bundle_manifest_sha256=APPROVED_BUNDLE_MANIFEST_SHA256,
        )

    assert _count(postgres_session, CatalogVersion) == 0
    assert _count(postgres_session, Exercise) == 0
    assert _count(postgres_session, ExerciseSafetyRule) == 0
    assert _count(postgres_session, ExerciseAlternative) == 0
    assert _count(postgres_session, ExerciseGoalTagLink) == 0
    assert _count(postgres_session, ExercisePrescriptionProfile) == 0


@pytest.mark.integration
def test_v2_release_keeps_unregistered_media_hidden_and_blocks_activation(
    postgres_session: Session,
) -> None:
    promote_v2(postgres_session, DEFAULT_BUNDLE_DIRECTORY, app_env="test")
    catalog = postgres_session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == V2_CATALOG_VERSION_CODE)
    )
    assert catalog is not None
    exercise = postgres_session.scalar(
        select(Exercise).where(Exercise.catalog_version_id == catalog.id).limit(1)
    )
    assert exercise is not None
    postgres_session.add(
        ExerciseMediaAsset(
            catalog_version_id=catalog.id,
            exercise_id=exercise.id,
            s3_key="catalog-media/exercises/unregistered.webp",
            media_status="AVAILABLE",
            rights_review_status="APPROVED",
            rights_reviewer="DOMAIN_REVIEWER",
            rights_reviewed_at=datetime(2026, 8, 26, tzinfo=UTC),
            rights_evidence_reference="SYNTHETIC-MEDIA-RIGHTS-R01",
            media_set_version_code="unregistered-media-set-v2",
            source_manifest_hash="0" * 64,
            source_metadata={"source": "synthetic-release-test"},
            approval_metadata=None,
        )
    )
    postgres_session.commit()

    detail = CatalogRepository().get_exercise_detail(postgres_session, exercise.id)
    assert detail is not None
    assert detail.media_asset_key is None
    postgres_session.commit()
    with postgres_session.begin():
        with pytest.raises(SystemExit, match="lacks registry approval"):
            activate(
                postgres_session,
                V2_CATALOG_VERSION_CODE,
                now=datetime(2026, 8, 26, tzinfo=UTC),
            )
    assert catalog.status_code == "DRAFT"
