import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    BodyFocus,
    CatalogVersion,
    Exercise,
    ExerciseAlternative,
    ExerciseBodyPart,
    ExerciseGoalTagLink,
    ExerciseMediaAsset,
    ExercisePrescriptionProfile,
    ExerciseSafetyRule,
)
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.db.repositories.vector_index import (
    VectorIndexBuildWrite,
    VectorIndexRepository,
)
from backend.app.modules.catalog.codes import BodyAreaCode, BodyAreaRoleCode
from backend.app.modules.catalog.service import (
    CatalogArtifact,
    CatalogDataBundleImporter,
    CatalogImporter,
    load_catalog_artifact,
)
from backend.scripts.catalog_activate import activate
from backend.scripts.demo_seed import seed_catalog

ALEMBIC_CONFIG = Path("backend/alembic.ini")
GENERATED_ARTIFACT = Path("data/generated/exercise-catalog-seed-kspo-tranche3-v0.1.0")
BUNDLE_CATALOGS = (Path("data/generated/exercise-catalog-seed-merged-mvp-v0.4.0"),)
BUNDLE_SAFETY = Path("data/generated/exercise-safety-rules-merged-mvp-v0.5.0")
BUNDLE_ALTERNATIVES = Path("data/generated/exercise-alternatives-merged-mvp-v0.4.0")
BUNDLE_PRESCRIPTIONS = Path("data/generated/exercise-prescriptions-merged-mvp-v0.1.0")


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
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.execute(delete(CatalogVersion))
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
def test_repository_persists_catalog_v2_code_set_and_gymvisual_source(
    postgres_session: Session,
) -> None:
    source = load_catalog_artifact(GENERATED_ARTIFACT)
    record = source.records[0].model_copy(
        update={
            "stable_code": "catalog_v2_repository_contract",
            "body_focus_code": "CHEST",
            "equipment_codes": ["BODYWEIGHT"],
            "source_track": "gymvisual",
        }
    )
    artifact = CatalogArtifact(
        source.manifest,
        "f" * 64,
        (record,),
        code_set_version="catalog-v2",
    )

    version = CatalogRepository().create_from_artifact(postgres_session, artifact)
    postgres_session.flush()

    exercise = postgres_session.scalar(
        select(Exercise).where(Exercise.catalog_version_id == version.id)
    )
    focus = postgres_session.get(BodyFocus, "CHEST")
    assert version.code_set_version == "catalog-v2"
    assert exercise is not None
    assert exercise.body_focus_code == "CHEST"
    assert exercise.source_track_code == "gymvisual"
    assert focus is not None and focus.code_set_version == "catalog-v2"


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
def test_lists_only_the_approved_catalog_with_filters_and_stable_keyset_pagination(
    postgres_session: Session,
) -> None:
    repository = CatalogRepository()
    importer = CatalogImporter(repository, "test")
    importer.import_artifact(postgres_session, GENERATED_ARTIFACT)
    draft_exercise_ids = set(postgres_session.scalars(select(Exercise.id)))

    # A domain-approved import is still ineligible while its catalog is DRAFT
    # and lacks the explicit production-review metadata.
    assert repository.get_approved_catalog(postgres_session) is None

    catalog_id = seed_catalog(postgres_session, datetime(2026, 8, 18, tzinfo=UTC))
    postgres_session.flush()
    catalog = repository.get_approved_catalog(postgres_session)
    assert catalog is not None
    assert catalog.catalog_version_id == catalog_id
    assert catalog.version_code == "demo-synthetic-v1"

    all_records = repository.list_approved_exercises(
        postgres_session,
        catalog_id,
        body_area_code=None,
        equipment_code=None,
        training_type_code=None,
        difficulty_code=None,
        after_exercise_id=None,
        limit=200,
    )
    assert all_records
    assert [row.exercise_id for row in all_records] == sorted(
        row.exercise_id for row in all_records
    )
    assert len({row.exercise_id for row in all_records}) == len(all_records)
    assert draft_exercise_ids.isdisjoint(row.exercise_id for row in all_records)
    assert all(
        row.primary_body_area_codes == tuple(sorted(row.primary_body_area_codes))
        and row.required_equipment_codes == tuple(sorted(row.required_equipment_codes))
        for row in all_records
    )

    reference = all_records[0]
    filtered = repository.list_approved_exercises(
        postgres_session,
        catalog_id,
        body_area_code=reference.primary_body_area_codes[0],
        equipment_code=reference.required_equipment_codes[0],
        training_type_code=reference.training_type_code,
        difficulty_code=reference.difficulty_code,
        after_exercise_id=None,
        limit=200,
    )
    assert reference.exercise_id in {row.exercise_id for row in filtered}
    assert all(
        reference.primary_body_area_codes[0] in row.primary_body_area_codes
        and reference.required_equipment_codes[0] in row.required_equipment_codes
        and row.training_type_code == reference.training_type_code
        and row.difficulty_code == reference.difficulty_code
        for row in filtered
    )

    secondary_only_code = next(
        code for code in BodyAreaCode if code not in reference.primary_body_area_codes
    )
    postgres_session.add(
        ExerciseBodyPart(
            exercise_id=reference.exercise_id,
            body_area_code=secondary_only_code,
            role_code=BodyAreaRoleCode.SECONDARY,
        )
    )
    postgres_session.flush()
    secondary_filter = repository.list_approved_exercises(
        postgres_session,
        catalog_id,
        body_area_code=secondary_only_code,
        equipment_code=None,
        training_type_code=None,
        difficulty_code=None,
        after_exercise_id=None,
        limit=200,
    )
    assert reference.exercise_id not in {row.exercise_id for row in secondary_filter}

    paged_ids: list[UUID] = []
    after_exercise_id: UUID | None = None
    while True:
        page = repository.list_approved_exercises(
            postgres_session,
            catalog_id,
            body_area_code=None,
            equipment_code=None,
            training_type_code=None,
            difficulty_code=None,
            after_exercise_id=after_exercise_id,
            limit=2,
        )
        if not page:
            break
        paged_ids.extend(row.exercise_id for row in page)
        after_exercise_id = page[-1].exercise_id

    assert paged_ids == [row.exercise_id for row in all_records]


@pytest.mark.integration
def test_repository_exposes_only_registry_and_rights_approved_media(
    postgres_session: Session,
) -> None:
    catalog_id = seed_catalog(postgres_session, datetime(2026, 8, 18, tzinfo=UTC))
    exercise_ids = tuple(
        postgres_session.scalars(
            select(Exercise.id)
            .where(Exercise.catalog_version_id == catalog_id)
            .order_by(Exercise.id)
            .limit(2)
        )
    )
    assert len(exercise_ids) == 2
    reviewed_at = datetime(2026, 8, 26, tzinfo=UTC)
    common = {
        "catalog_version_id": catalog_id,
        "media_status": "AVAILABLE",
        "rights_review_status": "APPROVED",
        "rights_reviewer": "DOMAIN_REVIEWER",
        "rights_reviewed_at": reviewed_at,
        "rights_evidence_reference": "MEDIA-RIGHTS-R01",
        "media_set_version_code": "media-set-v2",
        "source_manifest_hash": "a" * 64,
        "source_metadata": {"source": "synthetic-test"},
    }
    postgres_session.add_all(
        (
            ExerciseMediaAsset(
                exercise_id=exercise_ids[0],
                s3_key="catalog-media/exercises/unapproved.webp",
                approval_metadata=None,
                **common,
            ),
            ExerciseMediaAsset(
                exercise_id=exercise_ids[1],
                s3_key="catalog-media/exercises/approved.webp",
                approval_metadata={"approval_record_code": "MEDIA-APPROVAL-R01"},
                **common,
            ),
        )
    )
    postgres_session.flush()
    repository = CatalogRepository()

    rows = repository.list_approved_exercises(
        postgres_session,
        catalog_id,
        body_area_code=None,
        equipment_code=None,
        training_type_code=None,
        difficulty_code=None,
        after_exercise_id=None,
        limit=200,
    )
    media_by_exercise = {row.exercise_id: row.media_asset_key for row in rows}

    assert media_by_exercise[exercise_ids[0]] is None
    assert media_by_exercise[exercise_ids[1]] == "catalog-media/exercises/approved.webp"
    assert repository.get_exercise_detail(postgres_session, exercise_ids[0]).media_asset_key is None  # type: ignore[union-attr]
    assert (
        repository.get_exercise_detail(postgres_session, exercise_ids[1]).media_asset_key  # type: ignore[union-attr]
        == "catalog-media/exercises/approved.webp"
    )


@pytest.mark.integration
def test_imports_complete_bundle_with_metadata_and_is_idempotent(
    postgres_session: Session,
) -> None:
    importer = CatalogDataBundleImporter(CatalogRepository(), "test")

    first = importer.import_bundle(
        postgres_session,
        BUNDLE_CATALOGS,
        BUNDLE_SAFETY,
        BUNDLE_ALTERNATIVES,
        BUNDLE_PRESCRIPTIONS,
    )
    second = importer.import_bundle(
        postgres_session,
        BUNDLE_CATALOGS,
        BUNDLE_SAFETY,
        BUNDLE_ALTERNATIVES,
        BUNDLE_PRESCRIPTIONS,
    )

    assert first.safety_rules.record_count == 282
    assert first.alternatives.record_count == 238
    assert second.safety_rules.imported is False
    assert second.alternatives.imported is False
    assert first.prescriptions.record_count == 68
    assert second.prescriptions.imported is False
    assert postgres_session.scalar(select(func.count()).select_from(CatalogVersion)) == 1
    assert postgres_session.scalar(select(func.count()).select_from(Exercise)) == 56
    assert postgres_session.scalar(select(func.count()).select_from(ExerciseSafetyRule)) == 282
    assert postgres_session.scalar(select(func.count()).select_from(ExerciseAlternative)) == 238
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(ExerciseSafetyRule)
            .where(ExerciseSafetyRule.production_eligible.is_(True))
        )
        == 282
    )
    assert postgres_session.scalar(select(func.count()).select_from(ExerciseGoalTagLink)) == 32
    assert (
        postgres_session.scalar(select(func.count()).select_from(ExercisePrescriptionProfile)) == 36
    )
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(ExerciseAlternative)
            .where(ExerciseAlternative.production_eligible.is_(True))
        )
        == 238
    )
    safety = postgres_session.scalar(select(ExerciseSafetyRule).limit(1))
    alternative = postgres_session.scalar(select(ExerciseAlternative).limit(1))
    assert safety is not None and "catalog_seed_artifacts" in safety.source_metadata["source"]
    assert alternative is not None and "input_artifacts" in alternative.source_metadata["source"]
    assert safety.source_metadata["production_approval"]["scope"] == "ALL_RECORDS"
    assert alternative.source_metadata["production_approval"]["scope"] == "ALL_RECORDS"


@pytest.mark.integration
def test_vector_index_registry_round_trip_uses_only_production_catalog(
    postgres_session: Session,
) -> None:
    CatalogDataBundleImporter(CatalogRepository(), "test").import_bundle(
        postgres_session,
        BUNDLE_CATALOGS,
        BUNDLE_SAFETY,
        BUNDLE_ALTERNATIVES,
        BUNDLE_PRESCRIPTIONS,
    )
    repository = VectorIndexRepository()
    assert repository.list_indexable_exercises(postgres_session, "merged-mvp-v0.4.0") == ()

    now = datetime(2026, 8, 24, tzinfo=UTC)
    activate(postgres_session, "merged-mvp-v0.4.0", now=now)
    records = repository.list_indexable_exercises(postgres_session, "merged-mvp-v0.4.0")

    assert len(records) == 56
    assert all(record.production_eligible for record in records)
    registry = repository.create_build(
        postgres_session,
        VectorIndexBuildWrite(
            catalog_version_id=records[0].catalog_version_id,
            collection_name="exercise_catalog__test__merged_v0_4_0__fake_v1__index_v1",
            vector_index_version="index-v1",
            source_manifest_hash=records[0].catalog_manifest_hash,
            embedding_model_version="fake-v1",
            embedding_input_schema_version="exercise-embedding-input-v1",
            distance_metric_code="COSINE",
            vector_dimension=4,
            build_hash="b" * 64,
        ),
    )
    repository.mark_ready(postgres_session, registry, built_at=now)
    repository.activate(postgres_session, registry, activated_at=now)

    loaded = repository.get_by_version(postgres_session, "index-v1")
    active = repository.get_active_for_catalog(postgres_session, records[0].catalog_version_id)
    assert loaded is not None and loaded.status_code == "ACTIVE"
    assert active is not None and active.id == loaded.id
