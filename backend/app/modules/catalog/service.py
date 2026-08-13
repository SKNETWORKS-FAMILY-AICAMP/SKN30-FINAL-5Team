import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.modules.catalog.codes import (
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    CATALOG_CODE_SET_VERSION,
)
from backend.app.modules.catalog.schemas import CatalogManifest, ExerciseRecord


class CatalogImportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CatalogArtifact:
    manifest: CatalogManifest
    manifest_hash: str
    records: tuple[ExerciseRecord, ...]


@dataclass(frozen=True)
class CatalogImportResult:
    catalog_version_id: UUID
    version_code: str
    manifest_hash: str
    exercise_record_count: int
    imported: bool


class CatalogVersionRecord(Protocol):
    id: UUID
    version_code: str
    source_manifest_hash: str
    exercise_record_count: int


class CatalogRepositoryPort(Protocol):
    def get_by_version_code(
        self,
        session: Session,
        version_code: str,
    ) -> CatalogVersionRecord | None: ...

    def create_from_artifact(
        self,
        session: Session,
        artifact: CatalogArtifact,
    ) -> CatalogVersionRecord: ...


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_bytes(path: Path, error_code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CatalogImportError(error_code, "catalog artifact file is unreadable") from exc


def _resolve_inside(root: Path, referenced_path: str) -> Path:
    candidate = (root / referenced_path).resolve()
    if not candidate.is_relative_to(root):
        raise CatalogImportError(
            "ARTIFACT_PATH_OUTSIDE_DIRECTORY",
            "manifest file path leaves the artifact directory",
        )
    return candidate


def load_catalog_artifact(artifact_directory: Path) -> CatalogArtifact:
    root = artifact_directory.resolve()
    if not root.is_dir():
        raise CatalogImportError("ARTIFACT_DIRECTORY_INVALID", "artifact directory is invalid")

    manifest_raw = _read_bytes(root / "seed_manifest.json", "MANIFEST_UNREADABLE")
    try:
        manifest = CatalogManifest.model_validate_json(manifest_raw)
    except ValidationError as exc:
        raise CatalogImportError("MANIFEST_INVALID", "catalog manifest is invalid") from exc

    if manifest.review.production_eligible is not False:
        raise CatalogImportError(
            "PRODUCTION_ELIGIBILITY_INVALID",
            "DRAFT catalog artifact must remain production ineligible",
        )
    if manifest.source.taxonomy_registry_sha256 != APPROVED_TAXONOMY_REGISTRY_SHA256:
        raise CatalogImportError("CODE_SET_MISMATCH", "catalog code set is not MVP v1")

    for input_artifact in manifest.source.input_artifacts:
        _resolve_inside(root, input_artifact.path)

    file_entry = manifest.files[0]
    candidate = _resolve_inside(root, file_entry.path)

    data_raw = _read_bytes(candidate, "CATALOG_FILE_UNREADABLE")
    if len(data_raw) != file_entry.bytes or _sha256(data_raw) != file_entry.sha256:
        raise CatalogImportError(
            "CATALOG_FILE_INTEGRITY_MISMATCH",
            "catalog file hash or byte count does not match manifest",
        )

    records: list[ExerciseRecord] = []
    try:
        for line in data_raw.splitlines():
            if line.strip():
                records.append(ExerciseRecord.model_validate_json(line))
    except ValidationError as exc:
        raise CatalogImportError("EXERCISE_RECORD_INVALID", "exercise record is invalid") from exc

    if len(records) != file_entry.records:
        raise CatalogImportError(
            "RECORD_COUNT_MISMATCH",
            "catalog record count does not match manifest",
        )
    stable_codes = [record.stable_code for record in records]
    if len(stable_codes) != len(set(stable_codes)):
        raise CatalogImportError(
            "DUPLICATE_STABLE_CODE",
            "catalog contains duplicate stable codes",
        )

    return CatalogArtifact(
        manifest=manifest,
        manifest_hash=_sha256(manifest_raw),
        records=tuple(records),
    )


class CatalogImporter:
    def __init__(self, repository: CatalogRepositoryPort, app_env: str) -> None:
        self._repository = repository
        self._app_env = app_env

    def import_artifact(
        self,
        session: Session,
        artifact_directory: Path,
    ) -> CatalogImportResult:
        if self._app_env not in {"local", "test"}:
            raise CatalogImportError(
                "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN",
                "DRAFT catalog import is allowed only in local or test",
            )

        artifact = load_catalog_artifact(artifact_directory)
        version_code = artifact.manifest.catalog_version.version_code

        with session.begin():
            existing = self._repository.get_by_version_code(session, version_code)
            if existing is not None:
                if existing.source_manifest_hash != artifact.manifest_hash:
                    raise CatalogImportError(
                        "CATALOG_VERSION_HASH_CONFLICT",
                        "catalog version already exists with another manifest hash",
                    )
                return CatalogImportResult(
                    catalog_version_id=existing.id,
                    version_code=existing.version_code,
                    manifest_hash=existing.source_manifest_hash,
                    exercise_record_count=existing.exercise_record_count,
                    imported=False,
                )

            created = self._repository.create_from_artifact(session, artifact)
            return CatalogImportResult(
                catalog_version_id=created.id,
                version_code=created.version_code,
                manifest_hash=created.source_manifest_hash,
                exercise_record_count=created.exercise_record_count,
                imported=True,
            )


__all__ = [
    "CATALOG_CODE_SET_VERSION",
    "CatalogArtifact",
    "CatalogImportError",
    "CatalogImportResult",
    "CatalogImporter",
    "load_catalog_artifact",
]
