import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.modules.catalog.schemas import (
    AlternativeManifest,
    ExerciseAlternativeRecord,
    ExerciseSafetyRuleRecord,
    SafetyRuleManifest,
)
from backend.app.modules.catalog.service import (
    AlternativeArtifact,
    CatalogArtifact,
    CatalogDataBundleImporter,
    CatalogImportError,
    CatalogRepositoryPort,
    DerivedSetState,
    PrescriptionArtifact,
    SafetyRuleArtifact,
    _load_v2_bundle_manifest,
    _validate_bundle_exercise_references,
    _validate_v2_alternative_metadata,
    _validate_v2_safety_metadata,
    load_alternative_artifact,
    load_catalog_artifact,
    load_prescription_artifact,
    load_safety_rule_artifact,
)

GENERATED = Path("data/generated")
CATALOG_DIRECTORIES = (GENERATED / "exercise-catalog-seed-merged-mvp-v0.4.0",)
SAFETY_DIRECTORY = GENERATED / "exercise-safety-rules-merged-mvp-v0.5.0"
ALTERNATIVE_DIRECTORY = GENERATED / "exercise-alternatives-merged-mvp-v0.4.0"
PRESCRIPTION_DIRECTORY = GENERATED / "exercise-prescriptions-merged-mvp-v0.1.0"
V2_BUNDLE_DIRECTORY = GENERATED / "exercise-catalog-v2.0.1-final" / "backend_bundle"
V2_BUNDLE_HASH = "8ac896f3de3f2e292d7e27554c7dd3a2e3aa8afed69031bd493daf1f98df6ff5"
V2_TAXONOMY_HASH = "79e487cc1a41ea39db9b4afb0799b3297840de878a2ae4ed621ef3e4403a0985"


class FakeSession:
    @contextmanager
    def begin(self) -> Iterator[None]:
        yield


class FakeRepository:
    def __init__(self) -> None:
        self.catalogs: dict[str, SimpleNamespace] = {}
        self.safety_state: DerivedSetState | None = None
        self.alternative_state: DerivedSetState | None = None
        self.prescription_state: DerivedSetState | None = None

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

    def get_prescription_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None:
        return self.prescription_state

    def create_prescriptions(self, session: Session, artifact: PrescriptionArtifact) -> None:
        self.prescription_state = DerivedSetState(
            len(artifact.goal_tag_records) + len(artifact.prescription_records),
            artifact.manifest_hash,
        )


class FailingAlternativeRepository(FakeRepository):
    def create_alternatives(self, session: Session, artifact: AlternativeArtifact) -> None:
        raise RuntimeError("synthetic middle-stage failure")


class RollbackFakeSession:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository

    @contextmanager
    def begin(self) -> Iterator[None]:
        snapshot = deepcopy(self.repository.__dict__)
        try:
            yield
        except Exception:
            self.repository.__dict__.clear()
            self.repository.__dict__.update(snapshot)
            raise


def test_loads_current_derived_artifacts() -> None:
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    prescriptions = load_prescription_artifact(PRESCRIPTION_DIRECTORY)

    assert len(safety.records) == 282
    assert safety.manifest.review.production_eligible is False
    assert len(alternatives.records) == 238
    assert alternatives.manifest.review.production_eligible is False
    assert "catalog_seed_artifacts" in safety.manifest.source
    assert "input_artifacts" in alternatives.manifest.source
    assert len(prescriptions.goal_tag_records) == 32
    assert len(prescriptions.prescription_records) == 36


def test_v2_runtime_metadata_is_accepted_by_pydantic() -> None:
    runtime = GENERATED / "exercise-catalog-v2.0.1-final" / "runtime"
    safety_manifest = SafetyRuleManifest.model_validate_json(
        (runtime / "safety_manifest.json").read_text(encoding="utf-8")
    )
    alternative_manifest = AlternativeManifest.model_validate_json(
        (runtime / "alternatives_manifest.json").read_text(encoding="utf-8")
    )
    safety_records = tuple(
        ExerciseSafetyRuleRecord.model_validate_json(line)
        for line in (runtime / "safety_rules.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    alternative_records = tuple(
        ExerciseAlternativeRecord.model_validate_json(line)
        for line in (runtime / "alternatives.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    safety = safety_records[0]
    alternative = alternative_records[0]

    assert len(safety_records) == safety_manifest.summary.rule_records
    assert len(alternative_records) == alternative_manifest.summary.alternative_records
    assert safety.rule_set_version_code == "safety-rule-set-v2.0.1"
    assert safety.production_eligible is False
    assert safety.created_at is not None and safety.updated_at is not None
    assert alternative.alternative_set_version_code == "alternative-set-v2.0.1"
    assert alternative.review_method_code == "DOMAIN_REVIEWER"
    assert alternative.production_eligible is False


def test_v2_metadata_validation_matches_manifest_and_stays_draft() -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    safety_manifest = safety.manifest.model_copy(
        update={
            "review": safety.manifest.review.model_copy(
                update={"review_method_code": "DOMAIN_REVIEWER"}
            )
        }
    )
    safety_record = safety.records[0].model_copy(
        update={
            "rule_set_version_code": safety_manifest.rule_set_version.version_code,
            "production_eligible": False,
            "source_manifest_hash": "a" * 64,
            "source_metadata": {"source": "synthetic-test"},
            "created_at": now,
            "updated_at": now,
        }
    )
    _validate_v2_safety_metadata(safety_manifest, (safety_record,))

    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    alternative_manifest = alternatives.manifest.model_copy(
        update={
            "review": alternatives.manifest.review.model_copy(
                update={"review_method_code": "DOMAIN_REVIEWER"}
            )
        }
    )
    alternative_record = alternatives.records[0].model_copy(
        update={
            "alternative_set_version_code": (
                alternative_manifest.alternative_set_version.version_code
            ),
            "production_eligible": False,
            "source_manifest_hash": "b" * 64,
            "source_metadata": {"source": "synthetic-test"},
            "review_method_code": "DOMAIN_REVIEWER",
        }
    )
    _validate_v2_alternative_metadata(alternative_manifest, (alternative_record,))

    with pytest.raises(CatalogImportError) as exc_info:
        _validate_v2_alternative_metadata(
            alternative_manifest,
            (alternative_record.model_copy(update={"production_eligible": True}),),
        )
    assert exc_info.value.code == "PRODUCTION_ELIGIBILITY_INVALID"


def test_safety_rule_rejects_reversed_severity_range() -> None:
    payload = load_safety_rule_artifact(SAFETY_DIRECTORY).records[0].model_dump(mode="json")
    payload["minimum_severity_code"] = "SEVERE"
    payload["maximum_severity_code"] = "MILD"

    with pytest.raises(ValidationError, match="minimum severity"):
        ExerciseSafetyRuleRecord.model_validate(payload)


def test_alternative_rejects_runtime_downshift_as_goal_preservation() -> None:
    payload = load_alternative_artifact(ALTERNATIVE_DIRECTORY).records[0].model_dump(mode="json")
    payload["goal_preservation_code"] = "INTENSITY_REDUCED"

    with pytest.raises(ValidationError, match="runtime downshift"):
        ExerciseAlternativeRecord.model_validate(payload)


def test_alternative_loader_rejects_duplicate_relationship_key(tmp_path: Path) -> None:
    artifact = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    first = artifact.records[0]
    duplicate = first.model_copy(
        update={
            "created_at": first.created_at + timedelta(seconds=1),
        }
    )
    raw = b"".join((record.model_dump_json() + "\n").encode() for record in (first, duplicate))
    root = tmp_path / "alternatives"
    root.mkdir()
    (root / "alternatives.jsonl").write_bytes(raw)
    manifest = artifact.manifest.model_dump(mode="json")
    manifest["summary"]["alternative_records"] = 2
    file_entry = next(entry for entry in manifest["files"] if entry["path"] == "alternatives.jsonl")
    file_entry.update(
        {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "records": 2,
        }
    )
    (root / "alternatives_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(CatalogImportError) as exc_info:
        load_alternative_artifact(root)

    assert exc_info.value.code == "DUPLICATE_ALTERNATIVE"


def test_v2_bundle_rejects_outdoor_alternative_endpoint() -> None:
    catalog = load_catalog_artifact(CATALOG_DIRECTORIES[0])
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    prescriptions = load_prescription_artifact(PRESCRIPTION_DIRECTORY)
    relation = alternatives.records[0]
    records = tuple(
        record.model_copy(update={"location_codes": ["OUTDOOR"]})
        if record.stable_code == relation.source_exercise_stable_code
        else record
        for record in catalog.records
    )

    with pytest.raises(CatalogImportError) as exc_info:
        _validate_bundle_exercise_references(
            (CatalogArtifact(catalog.manifest, catalog.manifest_hash, records),),
            safety,
            alternatives,
            prescriptions,
            v2_import=True,
        )

    assert exc_info.value.code == "ALTERNATIVE_LOCATION_FORBIDDEN"


def test_v2_bundle_requires_bodyweight_equipment_fallback_for_stretch_strap() -> None:
    catalog = load_catalog_artifact(CATALOG_DIRECTORIES[0])
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    prescriptions = load_prescription_artifact(PRESCRIPTION_DIRECTORY)
    relation = alternatives.records[0].model_copy(update={"reason_code": "LOCATION"})
    records = tuple(
        record.model_copy(update={"equipment_codes": ["STRETCH_STRAP"]})
        if record.stable_code == relation.source_exercise_stable_code
        else record
        for record in catalog.records
    )

    with pytest.raises(CatalogImportError) as exc_info:
        _validate_bundle_exercise_references(
            (CatalogArtifact(catalog.manifest, catalog.manifest_hash, records),),
            safety,
            AlternativeArtifact(
                alternatives.manifest,
                alternatives.manifest_hash,
                (relation,),
            ),
            prescriptions,
            v2_import=True,
        )

    assert exc_info.value.code == "STRETCH_STRAP_FALLBACK_MISSING"


def test_v2_bundle_accepts_equipment_bodyweight_fallback_for_stretch_strap() -> None:
    catalog = load_catalog_artifact(CATALOG_DIRECTORIES[0])
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    prescriptions = load_prescription_artifact(PRESCRIPTION_DIRECTORY)
    relation = alternatives.records[0].model_copy(update={"reason_code": "EQUIPMENT"})
    records = tuple(
        record.model_copy(update={"equipment_codes": ["STRETCH_STRAP"], "location_codes": ["HOME"]})
        if record.stable_code == relation.source_exercise_stable_code
        else record.model_copy(
            update={"equipment_codes": ["BODYWEIGHT"], "location_codes": ["GYM"]}
        )
        if record.stable_code == relation.alternative_exercise_stable_code
        else record
        for record in catalog.records
    )

    _validate_bundle_exercise_references(
        (CatalogArtifact(catalog.manifest, catalog.manifest_hash, records),),
        safety,
        AlternativeArtifact(
            alternatives.manifest,
            alternatives.manifest_hash,
            (relation,),
        ),
        prescriptions,
        v2_import=True,
    )


def test_bundle_rejects_missing_exercise_reference_before_repository_access() -> None:
    catalog = load_catalog_artifact(CATALOG_DIRECTORIES[0])
    safety = load_safety_rule_artifact(SAFETY_DIRECTORY)
    alternatives = load_alternative_artifact(ALTERNATIVE_DIRECTORY)
    prescriptions = load_prescription_artifact(PRESCRIPTION_DIRECTORY)
    invalid_relation = alternatives.records[0].model_copy(
        update={"alternative_exercise_stable_code": "missing_exercise"}
    )

    with pytest.raises(CatalogImportError) as exc_info:
        _validate_bundle_exercise_references(
            (catalog,),
            safety,
            AlternativeArtifact(
                alternatives.manifest,
                alternatives.manifest_hash,
                (invalid_relation,),
            ),
            prescriptions,
            v2_import=True,
        )

    assert exc_info.value.code == "EXERCISE_REFERENCE_NOT_FOUND"


def test_bundle_import_is_idempotent() -> None:
    repository = FakeRepository()
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, repository), "test")
    session = cast(Session, FakeSession())

    first = importer.import_bundle(
        session,
        CATALOG_DIRECTORIES,
        SAFETY_DIRECTORY,
        ALTERNATIVE_DIRECTORY,
        PRESCRIPTION_DIRECTORY,
    )
    second = importer.import_bundle(
        session,
        CATALOG_DIRECTORIES,
        SAFETY_DIRECTORY,
        ALTERNATIVE_DIRECTORY,
        PRESCRIPTION_DIRECTORY,
    )

    assert [item.exercise_record_count for item in first.catalogs] == [56]
    assert all(item.imported for item in first.catalogs)
    assert first.safety_rules.record_count == 282
    assert first.safety_rules.imported is True
    assert first.alternatives.record_count == 238
    assert first.alternatives.imported is True
    assert not any(item.imported for item in second.catalogs)
    assert second.safety_rules.imported is False
    assert second.alternatives.imported is False
    assert first.prescriptions.record_count == 68
    assert first.prescriptions.imported is True
    assert second.prescriptions.imported is False


def test_bundle_rejects_missing_referenced_catalogs() -> None:
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, FakeRepository()), "test")

    with pytest.raises(CatalogImportError, match="exactly cover") as exc_info:
        importer.import_bundle(
            cast(Session, FakeSession()),
            (),
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
            PRESCRIPTION_DIRECTORY,
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
            PRESCRIPTION_DIRECTORY,
        )

    assert exc_info.value.code == "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN"
    assert repository.catalogs == {}


def test_draft_bundle_stays_blocked_in_staging() -> None:
    """Staging opened for the reviewed release must not reopen the DRAFT path."""
    repository = FakeRepository()
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, repository), "staging")

    with pytest.raises(CatalogImportError) as exc_info:
        importer.import_bundle(
            cast(Session, FakeSession()),
            CATALOG_DIRECTORIES,
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
            PRESCRIPTION_DIRECTORY,
        )

    assert exc_info.value.code == "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN"
    assert repository.catalogs == {}


def test_approved_release_flag_alone_does_not_open_staging() -> None:
    """approved_v2_bundle only counts inside the V2 importer mode."""
    repository = FakeRepository()
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, repository), "staging")

    with pytest.raises(CatalogImportError) as exc_info:
        importer.import_bundle(
            cast(Session, FakeSession()),
            CATALOG_DIRECTORIES,
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
            PRESCRIPTION_DIRECTORY,
            approved_v2_bundle=True,
        )

    assert exc_info.value.code == "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN"
    assert repository.catalogs == {}


def test_reviewed_release_import_stays_blocked_in_production() -> None:
    """Production needs its own release decision, not the staging allowance."""
    repository = FakeRepository()
    importer = CatalogDataBundleImporter(
        cast(CatalogRepositoryPort, repository), "production", v2_import=True
    )

    with pytest.raises(CatalogImportError) as exc_info:
        importer.import_bundle(
            cast(Session, FakeSession()),
            CATALOG_DIRECTORIES,
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
            PRESCRIPTION_DIRECTORY,
            approved_v2_bundle=True,
        )

    assert exc_info.value.code == "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN"
    assert repository.catalogs == {}


def test_bundle_middle_stage_failure_rolls_back_every_new_set() -> None:
    repository = FailingAlternativeRepository()
    importer = CatalogDataBundleImporter(cast(CatalogRepositoryPort, repository), "test")

    with pytest.raises(RuntimeError, match="middle-stage"):
        importer.import_bundle(
            cast(Session, RollbackFakeSession(repository)),
            CATALOG_DIRECTORIES,
            SAFETY_DIRECTORY,
            ALTERNATIVE_DIRECTORY,
            PRESCRIPTION_DIRECTORY,
        )

    assert repository.catalogs == {}
    assert repository.safety_state is None
    assert repository.alternative_state is None
    assert repository.prescription_state is None


def test_v2_bundle_exact_hash_count_and_versions_are_accepted() -> None:
    importer = CatalogDataBundleImporter(
        cast(CatalogRepositoryPort, FakeRepository()),
        "test",
        v2_import=True,
        v2_taxonomy_registry_sha256=V2_TAXONOMY_HASH,
    )

    result = importer.import_v2_bundle(
        cast(Session, FakeSession()),
        V2_BUNDLE_DIRECTORY,
        expected_bundle_manifest_sha256=V2_BUNDLE_HASH,
    )

    assert [item.exercise_record_count for item in result.catalogs] == [102]
    assert result.safety_rules.record_count == 394
    assert result.alternatives.record_count == 285
    assert result.prescriptions.record_count == 239
    assert result.media_assets is None


def test_v2_bundle_rejects_unapproved_manifest_hash() -> None:
    with pytest.raises(CatalogImportError) as exc_info:
        _load_v2_bundle_manifest(
            V2_BUNDLE_DIRECTORY,
            expected_manifest_sha256="0" * 64,
        )

    assert exc_info.value.code == "BUNDLE_MANIFEST_HASH_MISMATCH"
