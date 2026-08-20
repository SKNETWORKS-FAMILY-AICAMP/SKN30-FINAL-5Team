import hashlib
import json
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.modules.catalog.codes import APPROVED_TAXONOMY_REGISTRY_SHA256
from backend.app.modules.catalog.schemas import ExerciseRecord
from backend.app.modules.catalog.service import (
    CatalogArtifact,
    CatalogImporter,
    CatalogImportError,
    CatalogRepositoryPort,
    load_catalog_artifact,
)

GENERATED_CATALOG_ARTIFACTS = (
    ("exercise-catalog-seed-kspo-mvp-v0.2.0", 23),
    ("exercise-catalog-seed-wger-mvp-v0.2.0", 27),
    ("exercise-catalog-seed-kspo-tranche3-v0.1.0", 3),
    ("exercise-catalog-seed-wger-tranche3-v0.1.0", 3),
    ("exercise-catalog-seed-merged-mvp-v0.4.0", 56),
)


def _exercise_record(stable_code: str = "supported_sit_to_stand") -> dict[str, Any]:
    return {
        "stable_code": stable_code,
        "name_ko": "의자에서 일어나기",
        "name_en": "Supported Sit to Stand",
        "training_type_code": "STRENGTH",
        "body_focus_code": "LOWER_BODY",
        "primary_movement_pattern_code": "KNEE_DOMINANT",
        "difficulty_code": "BEGINNER",
        "beginner_suitable": True,
        "timing_mode_code": "REPS",
        "default_seconds_per_rep": 4,
        "default_work_seconds": None,
        "default_rest_seconds": 30,
        "default_transition_seconds": 15,
        "recovery_eligible": False,
        "primary_body_area_codes": ["HIP", "KNEE"],
        "secondary_body_area_codes": ["ANKLE_FOOT"],
        "equipment_codes": ["CHAIR"],
        "location_codes": ["HOME"],
        "instruction_summary_ko": "의자를 지지해 천천히 일어납니다.",
        "form_cues_ko": ["무릎과 발끝 방향을 맞춥니다."],
        "instruction_content_version": "1.0.0",
        "review_status_code": "DOMAIN_APPROVED",
        "source_track": "kspo",
        "source_identity": "synthetic-source-1",
    }


def _write_artifact(
    root: Path,
    *,
    records: list[dict[str, Any]] | None = None,
    version_code: str = "catalog-test-v1",
    file_path: str = "exercises.jsonl",
    declared_records: int | None = None,
    generator_version: str = "0.1.0",
    input_artifact_path: str | None = None,
) -> Path:
    root.mkdir()
    rows = records or [_exercise_record()]
    raw = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode() for row in rows
    )
    target = (root / file_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    count = len(rows) if declared_records is None else declared_records
    manifest = {
        "schema_version": "1.0",
        "generator_version": generator_version,
        "catalog_version": {"version_code": version_code, "status_code": "DRAFT"},
        "source": {
            "track": "kspo",
            "review_batch_directory": "synthetic-review-batch",
            "taxonomy_registry_sha256": APPROVED_TAXONOMY_REGISTRY_SHA256,
            "input_artifacts": (
                []
                if input_artifact_path is None
                else [
                    {
                        "role": "evidence",
                        "path": input_artifact_path,
                        "sha256": "0" * 64,
                        "bytes": 0,
                    }
                ]
            ),
        },
        "review": {
            "status": "DOMAIN_APPROVED",
            "review_method_code": "AGENT_ONLY",
            "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            "production_eligible": False,
        },
        "summary": {"exercise_records": count},
        "files": [
            {
                "path": file_path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "records": count,
            }
        ],
    }
    (root / "seed_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_loads_valid_draft_manifest_and_records(tmp_path: Path) -> None:
    artifact = load_catalog_artifact(_write_artifact(tmp_path / "artifact"))

    assert artifact.manifest.catalog_version.status_code == "DRAFT"
    assert artifact.manifest.review.production_eligible is False
    assert [record.stable_code for record in artifact.records] == ["supported_sit_to_stand"]


@pytest.mark.parametrize(("directory_name", "record_count"), GENERATED_CATALOG_ARTIFACTS)
def test_loads_current_generated_catalog_artifacts(
    directory_name: str,
    record_count: int,
) -> None:
    root = Path("data/generated") / directory_name

    artifact = load_catalog_artifact(root)

    assert len(artifact.records) == record_count


def test_pydantic_strenum_rejects_unknown_machine_code() -> None:
    record = _exercise_record()
    record["training_type_code"] = "UNKNOWN"

    with pytest.raises(ValidationError):
        ExerciseRecord.model_validate(record)


def test_exercise_record_rejects_merged_as_item_provenance() -> None:
    record = _exercise_record()
    record["source_track"] = "merged"

    with pytest.raises(ValidationError, match="original source track"):
        ExerciseRecord.model_validate(record)


def test_rejects_tampered_file_hash(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    (root / "exercises.jsonl").write_bytes(b"tampered\n")

    with pytest.raises(CatalogImportError, match="hash or byte count") as exc_info:
        load_catalog_artifact(root)

    assert exc_info.value.code == "CATALOG_FILE_INTEGRITY_MISMATCH"


def test_rejects_declared_byte_count_mismatch(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    manifest_path = root / "seed_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["bytes"] += 1
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CatalogImportError, match="hash or byte count") as exc_info:
        load_catalog_artifact(root)

    assert exc_info.value.code == "CATALOG_FILE_INTEGRITY_MISMATCH"


def test_rejects_record_count_mismatch(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", declared_records=2)

    with pytest.raises(CatalogImportError, match="record count") as exc_info:
        load_catalog_artifact(root)

    assert exc_info.value.code == "RECORD_COUNT_MISMATCH"


def test_rejects_path_outside_artifact_directory(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", file_path="../outside.jsonl")

    with pytest.raises(CatalogImportError, match="leaves") as exc_info:
        load_catalog_artifact(root)

    assert exc_info.value.code == "ARTIFACT_PATH_OUTSIDE_DIRECTORY"


def test_rejects_source_reference_outside_artifact_directory(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", input_artifact_path="../evidence.csv")

    with pytest.raises(CatalogImportError, match="leaves") as exc_info:
        load_catalog_artifact(root)

    assert exc_info.value.code == "ARTIFACT_PATH_OUTSIDE_DIRECTORY"


def test_rejects_duplicate_stable_code(tmp_path: Path) -> None:
    record = _exercise_record()
    root = _write_artifact(tmp_path / "artifact", records=[record, record])

    with pytest.raises(CatalogImportError, match="duplicate stable") as exc_info:
        load_catalog_artifact(root)

    assert exc_info.value.code == "DUPLICATE_STABLE_CODE"


class FakeSession:
    rolled_back = False

    @contextmanager
    def begin(self) -> AbstractContextManager[None]:
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise


class FakeRepository:
    def __init__(self) -> None:
        self.by_version: dict[str, SimpleNamespace] = {}

    def get_by_version_code(self, session: Session, version_code: str) -> SimpleNamespace | None:
        return self.by_version.get(version_code)

    def create_from_artifact(
        self,
        session: Session,
        artifact: CatalogArtifact,
    ) -> SimpleNamespace:
        record = SimpleNamespace(
            id=uuid4(),
            version_code=artifact.manifest.catalog_version.version_code,
            source_manifest_hash=artifact.manifest_hash,
            exercise_record_count=len(artifact.records),
        )
        self.by_version[record.version_code] = record
        return record


def _importer(repository: FakeRepository, app_env: str = "test") -> CatalogImporter:
    return CatalogImporter(cast(CatalogRepositoryPort, repository), app_env)


def test_same_version_and_hash_is_idempotent(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    repository = FakeRepository()
    session = cast(Session, FakeSession())
    importer = _importer(repository)

    first = importer.import_artifact(session, root)
    second = importer.import_artifact(session, root)

    assert first.imported is True
    assert second.imported is False
    assert second.catalog_version_id == first.catalog_version_id
    assert len(repository.by_version) == 1


def test_same_version_with_another_manifest_hash_fails_closed(tmp_path: Path) -> None:
    repository = FakeRepository()
    session = cast(Session, FakeSession())
    importer = _importer(repository)
    importer.import_artifact(session, _write_artifact(tmp_path / "first"))

    second = _write_artifact(tmp_path / "second", generator_version="0.1.1")
    with pytest.raises(CatalogImportError, match="another manifest hash") as exc_info:
        importer.import_artifact(session, second)

    assert exc_info.value.code == "CATALOG_VERSION_HASH_CONFLICT"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_non_development_environment_rejects_draft_import(
    tmp_path: Path,
    app_env: str,
) -> None:
    root = _write_artifact(tmp_path / "artifact")
    repository = FakeRepository()
    importer = _importer(repository, app_env)

    with pytest.raises(CatalogImportError, match="only in local or test") as exc_info:
        importer.import_artifact(cast(Session, FakeSession()), root)

    assert exc_info.value.code == "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN"
    assert repository.by_version == {}
