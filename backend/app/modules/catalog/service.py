import base64
import binascii
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.modules.catalog.codes import (
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    CATALOG_CODE_SET_VERSION,
    BodyAreaCode,
    DifficultyCode,
    EquipmentCode,
    TrainingTypeCode,
)
from backend.app.modules.catalog.schemas import (
    AlternativeManifest,
    CatalogManifest,
    ExerciseAlternativeRecord,
    ExerciseDetailResponse,
    ExerciseListItem,
    ExerciseListResponse,
    ExerciseRecord,
    ExerciseSafetyRuleRecord,
    ManifestFile,
    SafetyRuleManifest,
)


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


@dataclass(frozen=True)
class SafetyRuleArtifact:
    manifest: SafetyRuleManifest
    manifest_hash: str
    records: tuple[ExerciseSafetyRuleRecord, ...]


@dataclass(frozen=True)
class AlternativeArtifact:
    manifest: AlternativeManifest
    manifest_hash: str
    records: tuple[ExerciseAlternativeRecord, ...]


@dataclass(frozen=True)
class DerivedSetState:
    record_count: int
    manifest_hash: str


@dataclass(frozen=True)
class DerivedImportResult:
    version_code: str
    manifest_hash: str
    record_count: int
    imported: bool


@dataclass(frozen=True)
class CatalogDataBundleImportResult:
    catalogs: tuple[CatalogImportResult, ...]
    safety_rules: DerivedImportResult
    alternatives: DerivedImportResult


@dataclass(frozen=True)
class ExerciseDetailRecord:
    exercise_id: UUID
    exercise_name: str
    training_type_code: str
    primary_body_area_codes: tuple[str, ...]
    instruction_summary: str
    form_cues: tuple[str, ...]
    instruction_content_version: str


@dataclass(frozen=True)
class ApprovedCatalogRecord:
    catalog_version_id: UUID
    version_code: str


@dataclass(frozen=True)
class ExerciseListRecord:
    exercise_id: UUID
    exercise_name: str
    training_type_code: str
    difficulty_code: str
    primary_body_area_codes: tuple[str, ...]
    required_equipment_codes: tuple[str, ...]


@dataclass(frozen=True)
class ExerciseListCursor:
    catalog_version_id: UUID
    exercise_id: UUID


class ExerciseNotFoundError(Exception):
    """No reviewed exercise with this id is available to the caller."""


class ExerciseCatalogUnavailableError(Exception):
    """No active, domain-approved production catalog is available."""


class InvalidExerciseListQueryError(Exception):
    """The exercise list cursor is malformed or belongs to another catalog."""


class ExerciseReadRepositoryPort(Protocol):
    def get_approved_catalog(self, session: Session) -> ApprovedCatalogRecord | None: ...

    def list_approved_exercises(
        self,
        session: Session,
        catalog_version_id: UUID,
        *,
        body_area_code: str | None,
        equipment_code: str | None,
        training_type_code: str | None,
        difficulty_code: str | None,
        after_exercise_id: UUID | None,
        limit: int,
    ) -> tuple[ExerciseListRecord, ...]: ...

    def get_exercise_detail(
        self,
        session: Session,
        exercise_id: UUID,
    ) -> ExerciseDetailRecord | None: ...


class ExerciseReadService:
    """Serve reviewed instruction content for a planned exercise block."""

    def __init__(self, repository: ExerciseReadRepositoryPort) -> None:
        self._repository = repository

    def list_exercises(
        self,
        session: Session,
        *,
        body_area_code: str | None,
        equipment_code: str | None,
        training_type_code: str | None,
        difficulty_code: str | None,
        cursor: str | None,
        limit: int,
    ) -> ExerciseListResponse:
        catalog = self._repository.get_approved_catalog(session)
        if catalog is None:
            raise ExerciseCatalogUnavailableError

        decoded_cursor = _decode_exercise_list_cursor(cursor) if cursor is not None else None
        if decoded_cursor is not None and (
            decoded_cursor.catalog_version_id != catalog.catalog_version_id
        ):
            raise InvalidExerciseListQueryError

        records = self._repository.list_approved_exercises(
            session,
            catalog.catalog_version_id,
            body_area_code=body_area_code,
            equipment_code=equipment_code,
            training_type_code=training_type_code,
            difficulty_code=difficulty_code,
            after_exercise_id=(decoded_cursor.exercise_id if decoded_cursor is not None else None),
            limit=limit + 1,
        )
        page = records[:limit]
        next_cursor = None
        if len(records) > limit and page:
            next_cursor = _encode_exercise_list_cursor(
                ExerciseListCursor(
                    catalog_version_id=catalog.catalog_version_id,
                    exercise_id=page[-1].exercise_id,
                )
            )
        return ExerciseListResponse(
            items=[
                ExerciseListItem(
                    id=record.exercise_id,
                    name=record.exercise_name,
                    training_type_code=TrainingTypeCode(record.training_type_code),
                    difficulty_code=DifficultyCode(record.difficulty_code),
                    primary_body_area_codes=[
                        BodyAreaCode(code) for code in record.primary_body_area_codes
                    ],
                    required_equipment_codes=[
                        EquipmentCode(code) for code in record.required_equipment_codes
                    ],
                    media_asset_key=None,
                )
                for record in page
            ],
            next_cursor=next_cursor,
            catalog_version=catalog.version_code,
        )

    def get_detail(self, session: Session, exercise_id: UUID) -> ExerciseDetailResponse:
        record = self._repository.get_exercise_detail(session, exercise_id)
        if record is None:
            raise ExerciseNotFoundError
        # Media and mascot assets have no approved catalog column yet, so the
        # contract's nullable keys stay null rather than inventing asset keys.
        return ExerciseDetailResponse(
            exercise_id=record.exercise_id,
            exercise_name=record.exercise_name,
            training_type_code=record.training_type_code,
            primary_body_area_codes=list(record.primary_body_area_codes),
            instruction_summary=record.instruction_summary,
            form_cues=list(record.form_cues),
            media_asset_key=None,
            mascot_animation_asset_key=None,
            instruction_content_version=record.instruction_content_version,
        )


def _encode_exercise_list_cursor(cursor: ExerciseListCursor) -> str:
    payload = json.dumps(
        {
            "catalog_version_id": str(cursor.catalog_version_id),
            "exercise_id": str(cursor.exercise_id),
            "version": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_exercise_list_cursor(value: str) -> ExerciseListCursor:
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {
            "catalog_version_id",
            "exercise_id",
            "version",
        }:
            raise ValueError
        cursor = ExerciseListCursor(
            catalog_version_id=UUID(payload["catalog_version_id"]),
            exercise_id=UUID(payload["exercise_id"]),
        )
        if payload["version"] != 1 or _encode_exercise_list_cursor(cursor) != value:
            raise ValueError
        return cursor
    except (binascii.Error, json.JSONDecodeError, TypeError, ValueError):
        raise InvalidExerciseListQueryError from None


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

    def get_safety_rule_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None: ...

    def create_safety_rules(self, session: Session, artifact: SafetyRuleArtifact) -> None: ...

    def get_alternative_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None: ...

    def create_alternatives(self, session: Session, artifact: AlternativeArtifact) -> None: ...


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


def _load_derived_file(
    root: Path,
    files: list[ManifestFile],
    expected_path: str,
) -> bytes:
    file_entry = next(entry for entry in files if getattr(entry, "path", None) == expected_path)
    candidate = _resolve_inside(root, expected_path)
    data_raw = _read_bytes(candidate, "DERIVED_DATA_FILE_UNREADABLE")
    if len(data_raw) != file_entry.bytes or _sha256(data_raw) != file_entry.sha256:
        raise CatalogImportError(
            "DERIVED_DATA_FILE_INTEGRITY_MISMATCH",
            "derived data file hash or byte count does not match manifest",
        )
    return data_raw


def load_safety_rule_artifact(artifact_directory: Path) -> SafetyRuleArtifact:
    root = artifact_directory.resolve()
    if not root.is_dir():
        raise CatalogImportError("ARTIFACT_DIRECTORY_INVALID", "artifact directory is invalid")
    manifest_raw = _read_bytes(root / "rules_manifest.json", "MANIFEST_UNREADABLE")
    try:
        manifest = SafetyRuleManifest.model_validate_json(manifest_raw)
    except ValidationError as exc:
        raise CatalogImportError("MANIFEST_INVALID", "safety rule manifest is invalid") from exc
    if manifest.review.production_eligible is not False:
        raise CatalogImportError(
            "PRODUCTION_ELIGIBILITY_INVALID",
            "DRAFT safety rules must remain production ineligible",
        )
    data_raw = _load_derived_file(root, manifest.files, "safety_rules.jsonl")
    try:
        records = tuple(
            ExerciseSafetyRuleRecord.model_validate_json(line)
            for line in data_raw.splitlines()
            if line.strip()
        )
    except ValidationError as exc:
        raise CatalogImportError("SAFETY_RULE_RECORD_INVALID", "safety rule is invalid") from exc
    if len(records) != manifest.summary.rule_records:
        raise CatalogImportError("RECORD_COUNT_MISMATCH", "safety rule count does not match")
    if len({record.model_dump_json() for record in records}) != len(records):
        raise CatalogImportError("DUPLICATE_SAFETY_RULE", "safety rules contain duplicates")
    return SafetyRuleArtifact(manifest, _sha256(manifest_raw), records)


def load_alternative_artifact(artifact_directory: Path) -> AlternativeArtifact:
    root = artifact_directory.resolve()
    if not root.is_dir():
        raise CatalogImportError("ARTIFACT_DIRECTORY_INVALID", "artifact directory is invalid")
    manifest_raw = _read_bytes(root / "alternatives_manifest.json", "MANIFEST_UNREADABLE")
    try:
        manifest = AlternativeManifest.model_validate_json(manifest_raw)
    except ValidationError as exc:
        raise CatalogImportError("MANIFEST_INVALID", "alternatives manifest is invalid") from exc
    if manifest.review.production_eligible is not False:
        raise CatalogImportError(
            "PRODUCTION_ELIGIBILITY_INVALID",
            "DRAFT alternatives must remain production ineligible",
        )
    data_raw = _load_derived_file(root, manifest.files, "alternatives.jsonl")
    try:
        records = tuple(
            ExerciseAlternativeRecord.model_validate_json(line)
            for line in data_raw.splitlines()
            if line.strip()
        )
    except ValidationError as exc:
        raise CatalogImportError(
            "ALTERNATIVE_RECORD_INVALID", "exercise alternative is invalid"
        ) from exc
    if len(records) != manifest.summary.alternative_records:
        raise CatalogImportError("RECORD_COUNT_MISMATCH", "alternative count does not match")
    if len({record.model_dump_json() for record in records}) != len(records):
        raise CatalogImportError("DUPLICATE_ALTERNATIVE", "alternatives contain duplicates")
    return AlternativeArtifact(manifest, _sha256(manifest_raw), records)


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


class CatalogDataBundleImporter:
    """Atomically import the four catalogs and their DRAFT derived datasets."""

    def __init__(self, repository: CatalogRepositoryPort, app_env: str) -> None:
        self._repository = repository
        self._app_env = app_env

    def import_bundle(
        self,
        session: Session,
        catalog_directories: tuple[Path, ...],
        safety_rule_directory: Path,
        alternative_directory: Path,
    ) -> CatalogDataBundleImportResult:
        if self._app_env not in {"local", "test"}:
            raise CatalogImportError(
                "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN",
                "DRAFT catalog data import is allowed only in local or test",
            )

        catalog_artifacts = tuple(load_catalog_artifact(path) for path in catalog_directories)
        safety_artifact = load_safety_rule_artifact(safety_rule_directory)
        alternative_artifact = load_alternative_artifact(alternative_directory)
        supplied_versions = {
            artifact.manifest.catalog_version.version_code for artifact in catalog_artifacts
        }
        referenced_versions = {
            record.catalog_version_code for record in safety_artifact.records
        } | {
            version
            for record in alternative_artifact.records
            for version in (
                record.source_catalog_version_code,
                record.alternative_catalog_version_code,
            )
        }
        if supplied_versions != referenced_versions:
            raise CatalogImportError(
                "CATALOG_BUNDLE_INCOMPLETE",
                "catalog bundle must exactly cover every derived-data catalog reference",
            )

        catalog_results: list[CatalogImportResult] = []
        with session.begin():
            for artifact in catalog_artifacts:
                version_code = artifact.manifest.catalog_version.version_code
                existing = self._repository.get_by_version_code(session, version_code)
                if existing is not None:
                    if existing.source_manifest_hash != artifact.manifest_hash:
                        raise CatalogImportError(
                            "CATALOG_VERSION_HASH_CONFLICT",
                            "catalog version already exists with another manifest hash",
                        )
                    catalog_results.append(
                        CatalogImportResult(
                            existing.id,
                            existing.version_code,
                            existing.source_manifest_hash,
                            existing.exercise_record_count,
                            False,
                        )
                    )
                else:
                    created = self._repository.create_from_artifact(session, artifact)
                    catalog_results.append(
                        CatalogImportResult(
                            created.id,
                            created.version_code,
                            created.source_manifest_hash,
                            created.exercise_record_count,
                            True,
                        )
                    )

            safety_result = self._import_derived_set(
                session,
                safety_artifact.manifest.rule_set_version.version_code,
                safety_artifact.manifest_hash,
                len(safety_artifact.records),
                self._repository.get_safety_rule_set_state,
                lambda: self._repository.create_safety_rules(session, safety_artifact),
            )
            alternative_result = self._import_derived_set(
                session,
                alternative_artifact.manifest.alternative_set_version.version_code,
                alternative_artifact.manifest_hash,
                len(alternative_artifact.records),
                self._repository.get_alternative_set_state,
                lambda: self._repository.create_alternatives(session, alternative_artifact),
            )

        return CatalogDataBundleImportResult(
            catalogs=tuple(catalog_results),
            safety_rules=safety_result,
            alternatives=alternative_result,
        )

    def _import_derived_set(
        self,
        session: Session,
        version_code: str,
        manifest_hash: str,
        record_count: int,
        get_state: Callable[[Session, str], DerivedSetState | None],
        create: Callable[[], None],
    ) -> DerivedImportResult:
        state = get_state(session, version_code)
        if state is not None:
            if state.manifest_hash != manifest_hash or state.record_count != record_count:
                raise CatalogImportError(
                    "DERIVED_SET_CONFLICT",
                    "derived set exists with another manifest hash or record count",
                )
            return DerivedImportResult(version_code, manifest_hash, record_count, False)
        create()
        return DerivedImportResult(version_code, manifest_hash, record_count, True)


__all__ = [
    "CATALOG_CODE_SET_VERSION",
    "CatalogArtifact",
    "CatalogImportError",
    "CatalogImportResult",
    "CatalogImporter",
    "CatalogDataBundleImporter",
    "CatalogDataBundleImportResult",
    "DerivedImportResult",
    "DerivedSetState",
    "AlternativeArtifact",
    "SafetyRuleArtifact",
    "load_alternative_artifact",
    "load_catalog_artifact",
    "load_safety_rule_artifact",
]
