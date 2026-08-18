from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend.app.modules.catalog.service import (
    AlternativeArtifact,
    CatalogArtifact,
    CatalogDataBundleImporter,
    CatalogImportError,
    CatalogRepositoryPort,
    DerivedSetState,
    SafetyRuleArtifact,
    load_alternative_artifact,
    load_safety_rule_artifact,
)

GENERATED = Path("data/generated")
CATALOG_DIRECTORIES = (
    GENERATED / "exercise-catalog-seed-kspo-mvp-v0.2.0",
    GENERATED / "exercise-catalog-seed-wger-mvp-v0.2.0",
    GENERATED / "exercise-catalog-seed-kspo-tranche3-v0.1.0",
    GENERATED / "exercise-catalog-seed-wger-tranche3-v0.1.0",
)
SAFETY_DIRECTORY = GENERATED / "exercise-safety-rules-mvp-v0.3.0"
ALTERNATIVE_DIRECTORY = GENERATED / "exercise-alternatives-mvp-v0.2.0"


class FakeSession:
    @contextmanager
    def begin(self) -> AbstractContextManager[None]:
        yield


class FakeRepository:
    def __init__(self) -> None:
        self.catalogs: dict[str, SimpleNamespace] = {}
        self.safety_state: DerivedSetState | None = None
        self.alternative_state: DerivedSetState | None = None

    def get_by_version_code(self, session: Session, version_code: str) -> SimpleNamespace | None:
        return self.catalogs.get(version_code)

    def create_from_artifact(self, session: Session, artifact: CatalogArtifact) -> SimpleNamespace:
        version_code = artifact.manifest.catalog_version.version_code
        row = SimpleNamespace(
            id=uuid4(),
            version_code=version_code,
            source_manifest_hash=artifact.manifest_hash,
            exercise_record_count=len(artifact.records),
        )
        self.catalogs[version_code] = row
        return row

    def get_safety_rule_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None:
        return self.safety_state

    def create_safety_rules(self, session: Session, artifact: SafetyRuleArtifact) -> None:
        self.safety_state = DerivedSetState(len(artifact.records), artifact.manifest_hash)

    def get_alternative_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None:
        return self.alternative_state

    def create_alternatives(self, session: Session, artifact: AlternativeArtifact) -> None:
        self.alternative_state = DerivedSetState(len(artifact.records), artifact.manifest_hash)


def test_loads_current_derived_artifacts() -> None:
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)

    assert len(safety.records) == 354
    assert safety.manifest.review.production_eligible is False
    assert len(alternatives.records) == 238
    assert alternatives.manifest.review.production_eligible is False
    assert "catalog_seed_artifacts" in safety.manifest.source
    assert "input_artifacts" in alternatives.manifest.source


def test_bundle_import_is_idempotent() -> None:
    repository = FakeRepository()
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, repository), "test")
    session = cast(Session, FakeSession())

    first = importer.import_bundle(
        session, CATALOG_DIRECTORIES, SAFETY_DIRECTORY, ALTERNATIVE_DIRECTORY
    )
    second = importer.import_bundle(
        session, CATALOG_DIRECTORIES, SAFETY_DIRECTORY, ALTERNATIVE_DIRECTORY
    )

    assert [item.exercise_record_count for item in first.catalogs] == [23, 27, 3, 3]
    assert all(item.imported for item in first.catalogs)
    assert first.safety_rules.record_count == 354
    assert first.safety_rules.imported is True
    assert first.alternatives.record_count == 238
    assert first.alternatives.imported is True
    assert not any(item.imported for item in second.catalogs)
    assert second.safety_rules.imported is False
    assert second.alternatives.imported is False


def test_bundle_rejects_missing_referenced_catalogs() -> None:
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, FakeRepository()), "test")

    with pytest.raises(CatalogImportError, match="exactly cover") as exc_info:
        importer.import_bundle(
            cast(Session, FakeSession()),
            CATALOG_DIRECTORIES[:1],
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
        )

    assert exc_info.value.code == "CATALOG_BUNDLE_INCOMPLETE"


def test_bundle_rejects_non_local_environment_before_database_access() -> None:
    repository = FakeRepository()
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, repository), "production")

    with pytest.raises(CatalogImportError) as exc_info:
        importer.import_bundle(
            cast(Session, FakeSession()),
            CATALOG_DIRECTORIES,
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
        )

    assert exc_info.value.code == "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN"
    assert repository.catalogs == {}
