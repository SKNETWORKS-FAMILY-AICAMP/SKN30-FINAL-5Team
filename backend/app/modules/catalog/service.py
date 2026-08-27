import base64
import binascii
import csv
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.modules.catalog.approvals import (
    get_catalog_approval,
    get_derived_data_approval,
)
from backend.app.modules.catalog.codes import (
    APPROVED_TAXONOMY_REGISTRY_SHA256,
    CATALOG_CODE_SET_VERSION,
    CATALOG_V2_CODE_SET_VERSION,
    BodyAreaCode,
    DifficultyCode,
    EquipmentCode,
    LocationCode,
    TrainingTypeCode,
)
from backend.app.modules.catalog.schemas import (
    AlternativeManifest,
    CatalogBundleManifest,
    CatalogManifest,
    ExerciseAlternativeRecord,
    ExerciseDetailResponse,
    ExerciseGoalTagRecord,
    ExerciseListItem,
    ExerciseListResponse,
    ExercisePrescriptionRecord,
    ExerciseRecord,
    ExerciseSafetyRuleRecord,
    ManifestFile,
    MediaAssetRecord,
    MediaManifest,
    PrescriptionManifest,
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
    code_set_version: str = CATALOG_CODE_SET_VERSION


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
class PrescriptionArtifact:
    manifest: PrescriptionManifest
    manifest_hash: str
    goal_tag_records: tuple[ExerciseGoalTagRecord, ...]
    prescription_records: tuple[ExercisePrescriptionRecord, ...]


@dataclass(frozen=True)
class MediaArtifact:
    manifest: MediaManifest
    manifest_hash: str
    records: tuple[MediaAssetRecord, ...]
    exercise_stable_codes: tuple[str, ...]


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
    prescriptions: DerivedImportResult
    media_assets: DerivedImportResult | None = None


@dataclass(frozen=True)
class ExerciseDetailRecord:
    exercise_id: UUID
    exercise_name: str
    training_type_code: str
    primary_body_area_codes: tuple[str, ...]
    instruction_summary: str
    form_cues: tuple[str, ...]
    instruction_content_version: str
    media_asset_key: str | None = None


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
    media_asset_key: str | None = None


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
                    media_asset_key=record.media_asset_key,
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
        return ExerciseDetailResponse(
            exercise_id=record.exercise_id,
            exercise_name=record.exercise_name,
            training_type_code=record.training_type_code,
            primary_body_area_codes=list(record.primary_body_area_codes),
            instruction_summary=record.instruction_summary,
            form_cues=list(record.form_cues),
            media_asset_key=record.media_asset_key,
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

    def get_prescription_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None: ...

    def create_prescriptions(self, session: Session, artifact: PrescriptionArtifact) -> None: ...

    def get_media_set_state(
        self, session: Session, version_code: str
    ) -> DerivedSetState | None: ...

    def create_media_assets(self, session: Session, artifact: MediaArtifact) -> None: ...


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


def load_catalog_artifact(
    artifact_directory: Path,
    *,
    v2_import: bool = False,
    v2_taxonomy_registry_sha256: str | None = None,
) -> CatalogArtifact:
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
    if v2_import and v2_taxonomy_registry_sha256 is None:
        raise CatalogImportError(
            "V2_TAXONOMY_REGISTRY_NOT_CONFIGURED",
            "V2 import requires an explicitly approved taxonomy registry hash",
        )
    expected_taxonomy_hash = (
        v2_taxonomy_registry_sha256 if v2_import else APPROVED_TAXONOMY_REGISTRY_SHA256
    )
    if manifest.source.taxonomy_registry_sha256 != expected_taxonomy_hash:
        raise CatalogImportError(
            "CODE_SET_MISMATCH",
            "catalog taxonomy registry hash is not the approved import hash",
        )

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
                records.append(
                    ExerciseRecord.model_validate_json(
                        line,
                        context={"v2_import": v2_import},
                    )
                )
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
        code_set_version=(CATALOG_V2_CODE_SET_VERSION if v2_import else CATALOG_CODE_SET_VERSION),
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


def _validate_v2_safety_metadata(
    manifest: SafetyRuleManifest,
    records: tuple[ExerciseSafetyRuleRecord, ...],
) -> None:
    if manifest.review.review_method_code != "DOMAIN_REVIEWER":
        raise CatalogImportError(
            "V2_REVIEW_METHOD_INVALID",
            "V2 safety artifacts require DOMAIN_REVIEWER evidence",
        )
    expected_version = manifest.rule_set_version.version_code
    for record in records:
        if (
            record.rule_set_version_code is None
            or record.production_eligible is None
            or record.source_manifest_hash is None
            or record.source_metadata is None
            or record.created_at is None
            or record.updated_at is None
        ):
            raise CatalogImportError(
                "V2_SAFETY_METADATA_REQUIRED",
                "V2 safety records require versioned audit metadata",
            )
        if record.rule_set_version_code != expected_version:
            raise CatalogImportError(
                "DERIVED_VERSION_MISMATCH",
                "safety record version does not match its manifest",
            )
        if record.production_eligible is not False:
            raise CatalogImportError(
                "PRODUCTION_ELIGIBILITY_INVALID",
                "unapproved V2 safety records must remain production ineligible",
            )
        if record.updated_at < record.created_at:
            raise CatalogImportError(
                "V2_AUDIT_TIMESTAMP_INVALID",
                "safety updated_at must not precede created_at",
            )
    if len({record.source_manifest_hash for record in records}) != 1:
        raise CatalogImportError(
            "V2_SOURCE_MANIFEST_MIXED",
            "V2 safety records must share one source manifest hash",
        )


def load_safety_rule_artifact(
    artifact_directory: Path,
    *,
    v2_import: bool = False,
) -> SafetyRuleArtifact:
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
    if v2_import:
        _validate_v2_safety_metadata(manifest, records)
    return SafetyRuleArtifact(manifest, _sha256(manifest_raw), records)


def _validate_v2_alternative_metadata(
    manifest: AlternativeManifest,
    records: tuple[ExerciseAlternativeRecord, ...],
) -> None:
    if manifest.review.review_method_code != "DOMAIN_REVIEWER":
        raise CatalogImportError(
            "V2_REVIEW_METHOD_INVALID",
            "V2 alternative artifacts require DOMAIN_REVIEWER evidence",
        )
    expected_version = manifest.alternative_set_version.version_code
    for record in records:
        if (
            record.alternative_set_version_code is None
            or record.production_eligible is None
            or record.source_manifest_hash is None
            or record.source_metadata is None
        ):
            raise CatalogImportError(
                "V2_ALTERNATIVE_METADATA_REQUIRED",
                "V2 alternative records require versioned audit metadata",
            )
        if record.alternative_set_version_code != expected_version:
            raise CatalogImportError(
                "DERIVED_VERSION_MISMATCH",
                "alternative record version does not match its manifest",
            )
        if record.production_eligible is not False:
            raise CatalogImportError(
                "PRODUCTION_ELIGIBILITY_INVALID",
                "unapproved V2 alternative records must remain production ineligible",
            )
        if record.review_method_code != "DOMAIN_REVIEWER":
            raise CatalogImportError(
                "V2_REVIEW_METHOD_INVALID",
                "V2 alternative records require DOMAIN_REVIEWER evidence",
            )
        if record.updated_at is not None and record.updated_at < record.created_at:
            raise CatalogImportError(
                "V2_AUDIT_TIMESTAMP_INVALID",
                "alternative updated_at must not precede created_at",
            )
    if len({record.source_manifest_hash for record in records}) != 1:
        raise CatalogImportError(
            "V2_SOURCE_MANIFEST_MIXED",
            "V2 alternative records must share one source manifest hash",
        )


def load_alternative_artifact(
    artifact_directory: Path,
    *,
    v2_import: bool = False,
) -> AlternativeArtifact:
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
    relationship_keys = {
        (
            record.source_catalog_version_code,
            record.source_exercise_stable_code,
            record.alternative_catalog_version_code,
            record.alternative_exercise_stable_code,
            record.reason_code,
            record.goal_preservation_code,
            record.rule_version,
        )
        for record in records
    }
    if len(relationship_keys) != len(records):
        raise CatalogImportError("DUPLICATE_ALTERNATIVE", "alternatives contain duplicates")
    if v2_import:
        _validate_v2_alternative_metadata(manifest, records)
    return AlternativeArtifact(manifest, _sha256(manifest_raw), records)


def load_prescription_artifact(artifact_directory: Path) -> PrescriptionArtifact:
    root = artifact_directory.resolve()
    if not root.is_dir():
        raise CatalogImportError("ARTIFACT_DIRECTORY_INVALID", "artifact directory is invalid")
    manifest_raw = _read_bytes(root / "prescription_manifest.json", "MANIFEST_UNREADABLE")
    try:
        manifest = PrescriptionManifest.model_validate_json(manifest_raw)
    except ValidationError as exc:
        raise CatalogImportError("MANIFEST_INVALID", "prescription manifest is invalid") from exc
    if manifest.review.production_eligible is not False:
        raise CatalogImportError(
            "PRODUCTION_ELIGIBILITY_INVALID",
            "DRAFT prescriptions must remain production ineligible",
        )
    goal_raw = _load_derived_file(root, manifest.files, "goal_tag_links.jsonl")
    profile_raw = _load_derived_file(root, manifest.files, "prescription_profiles.jsonl")
    try:
        goals = tuple(
            ExerciseGoalTagRecord.model_validate_json(line)
            for line in goal_raw.splitlines()
            if line.strip()
        )
        profiles = tuple(
            ExercisePrescriptionRecord.model_validate_json(line)
            for line in profile_raw.splitlines()
            if line.strip()
        )
    except ValidationError as exc:
        raise CatalogImportError(
            "PRESCRIPTION_RECORD_INVALID", "prescription record is invalid"
        ) from exc
    if len(goals) != manifest.summary.goal_tag_records or len(profiles) != (
        manifest.summary.prescription_records
    ):
        raise CatalogImportError("RECORD_COUNT_MISMATCH", "prescription counts do not match")
    goal_keys = {
        (row.catalog_version_code, row.exercise_stable_code, row.goal_code) for row in goals
    }
    profile_keys = {
        (
            row.catalog_version_code,
            row.exercise_stable_code,
            row.goal_code,
            row.experience_level_code,
            row.phase_code,
        )
        for row in profiles
    }
    if len(goal_keys) != len(goals) or len(profile_keys) != len(profiles):
        raise CatalogImportError("DUPLICATE_PRESCRIPTION", "prescription artifact has duplicates")
    if any(
        (row.catalog_version_code, row.exercise_stable_code, row.goal_code) not in goal_keys
        for row in profiles
    ):
        raise CatalogImportError("GOAL_TAG_REFERENCE_NOT_FOUND", "prescription lacks a goal tag")
    return PrescriptionArtifact(manifest, _sha256(manifest_raw), goals, profiles)


def load_media_artifact(
    artifact_directory: Path,
    *,
    representative_to_stable_code: dict[str, str] | None = None,
) -> MediaArtifact:
    root = artifact_directory.resolve()
    if not root.is_dir():
        raise CatalogImportError(
            "ARTIFACT_DIRECTORY_INVALID", "media artifact directory is invalid"
        )
    manifest_raw = _read_bytes(root / "media_manifest.json", "MANIFEST_UNREADABLE")
    try:
        manifest = MediaManifest.model_validate_json(manifest_raw)
    except ValidationError as exc:
        raise CatalogImportError("MANIFEST_INVALID", "media manifest is invalid") from exc
    if manifest.review.production_eligible is not False:
        raise CatalogImportError(
            "PRODUCTION_ELIGIBILITY_INVALID",
            "DRAFT media artifact must remain production ineligible",
        )
    data_raw = _load_derived_file(root, manifest.files, "media_assets.jsonl")
    try:
        records = tuple(
            MediaAssetRecord.model_validate_json(line)
            for line in data_raw.splitlines()
            if line.strip()
        )
    except ValidationError as exc:
        raise CatalogImportError("MEDIA_RECORD_INVALID", "media asset record is invalid") from exc
    if len(records) != manifest.summary.media_asset_records:
        raise CatalogImportError("RECORD_COUNT_MISMATCH", "media asset count does not match")
    if len({record.s3_key for record in records}) != len(records):
        raise CatalogImportError("DUPLICATE_MEDIA", "media assets contain duplicate S3 keys")
    reference_map = representative_to_stable_code or {}
    stable_codes = tuple(
        reference_map.get(record.representative_exercise_id, record.representative_exercise_id)
        for record in records
    )
    if len(set(stable_codes)) != len(stable_codes):
        raise CatalogImportError("DUPLICATE_MEDIA", "media assets contain duplicate exercises")
    return MediaArtifact(manifest, _sha256(manifest_raw), records, stable_codes)


def _load_v2_bundle_manifest(
    bundle_directory: Path,
    *,
    expected_manifest_sha256: str,
) -> CatalogBundleManifest:
    root = bundle_directory.resolve()
    raw = _read_bytes(root / "bundle_manifest.json", "BUNDLE_MANIFEST_UNREADABLE")
    if _sha256(raw) != expected_manifest_sha256:
        raise CatalogImportError(
            "BUNDLE_MANIFEST_HASH_MISMATCH", "bundle manifest hash is not approved"
        )
    try:
        manifest = CatalogBundleManifest.model_validate_json(raw)
    except ValidationError as exc:
        raise CatalogImportError("BUNDLE_MANIFEST_INVALID", "bundle manifest is invalid") from exc
    listed_files = {_resolve_inside(root, entry.path) for entry in manifest.files}
    actual_files = {
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.name != "bundle_manifest.json"
    }
    if actual_files != listed_files:
        raise CatalogImportError(
            "BUNDLE_FILE_SET_MISMATCH",
            "bundle contains missing or unlisted files",
        )
    for entry in manifest.files:
        candidate = _resolve_inside(root, entry.path)
        content = _read_bytes(candidate, "BUNDLE_FILE_UNREADABLE")
        candidates: tuple[bytes, ...] = (content,)
        if candidate.suffix.lower() == ".csv":
            canonical_crlf = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            candidates = (content, canonical_crlf)
        if not any(len(raw) == entry.bytes and _sha256(raw) == entry.sha256 for raw in candidates):
            raise CatalogImportError(
                "BUNDLE_FILE_INTEGRITY_MISMATCH",
                f"bundle file does not match manifest: {entry.path}",
            )
    return manifest


def _v2_representative_registry(
    catalog_directory: Path,
    catalog_artifact: CatalogArtifact,
) -> dict[str, str]:
    inputs = catalog_artifact.manifest.source.input_artifacts
    registry_entry = next(
        (entry for entry in inputs if entry.role == "representative_catalog_csv"), None
    )
    if registry_entry is None:
        raise CatalogImportError(
            "REPRESENTATIVE_REGISTRY_MISSING", "V2 catalog lacks representative ID mapping"
        )
    raw = _read_bytes(
        catalog_directory / registry_entry.path,
        "REPRESENTATIVE_REGISTRY_UNREADABLE",
    )
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    mapping: dict[str, str] = {}
    for row in rows:
        representative_id = (row.get("representative_exercise_id") or "").strip()
        stable_code = (row.get("stable_code") or "").strip()
        if not representative_id or not stable_code or representative_id in mapping:
            raise CatalogImportError(
                "REPRESENTATIVE_REGISTRY_INVALID", "V2 representative ID mapping is invalid"
            )
        mapping[representative_id] = stable_code
    if set(mapping.values()) != {record.stable_code for record in catalog_artifact.records}:
        raise CatalogImportError(
            "REPRESENTATIVE_REGISTRY_MISMATCH",
            "V2 representative ID mapping does not exactly cover the catalog",
        )
    return mapping


def _validate_bundle_exercise_references(
    catalog_artifacts: tuple[CatalogArtifact, ...],
    safety_artifact: SafetyRuleArtifact,
    alternative_artifact: AlternativeArtifact,
    prescription_artifact: PrescriptionArtifact,
    *,
    v2_import: bool,
) -> None:
    exercise_records = {
        (artifact.manifest.catalog_version.version_code, record.stable_code): record
        for artifact in catalog_artifacts
        for record in artifact.records
    }
    exercise_keys = set(exercise_records)
    referenced_keys = {
        (record.catalog_version_code, record.exercise_stable_code)
        for record in safety_artifact.records
        if record.exercise_stable_code is not None
    }
    referenced_keys |= {
        key
        for record in alternative_artifact.records
        for key in (
            (
                record.source_catalog_version_code,
                record.source_exercise_stable_code,
            ),
            (
                record.alternative_catalog_version_code,
                record.alternative_exercise_stable_code,
            ),
        )
    }
    referenced_keys |= {
        (record.catalog_version_code, record.exercise_stable_code)
        for record in prescription_artifact.goal_tag_records
    }
    referenced_keys |= {
        (record.catalog_version_code, record.exercise_stable_code)
        for record in prescription_artifact.prescription_records
    }
    if missing := referenced_keys - exercise_keys:
        missing_version, missing_stable_code = min(missing)
        raise CatalogImportError(
            "EXERCISE_REFERENCE_NOT_FOUND",
            "derived data references an exercise absent from its catalog: "
            f"{missing_version}/{missing_stable_code}",
        )
    if not v2_import:
        return

    strap_sources = {
        key
        for key, exercise in exercise_records.items()
        if EquipmentCode.STRETCH_STRAP in exercise.equipment_codes
    }
    strap_sources_with_bodyweight_alternative: set[tuple[str, str]] = set()
    for record in alternative_artifact.records:
        source_key = (
            record.source_catalog_version_code,
            record.source_exercise_stable_code,
        )
        alternative_key = (
            record.alternative_catalog_version_code,
            record.alternative_exercise_stable_code,
        )
        source = exercise_records[source_key]
        alternative = exercise_records[alternative_key]
        if LocationCode.OUTDOOR in source.location_codes or (
            LocationCode.OUTDOOR in alternative.location_codes
        ):
            raise CatalogImportError(
                "ALTERNATIVE_LOCATION_FORBIDDEN",
                "V2 alternative relationships allow HOME and GYM exercises only",
            )
        if EquipmentCode.STRETCH_STRAP in source.equipment_codes:
            if (
                record.reason_code == "EQUIPMENT"
                and EquipmentCode.BODYWEIGHT in alternative.equipment_codes
            ):
                strap_sources_with_bodyweight_alternative.add(source_key)

    if missing_strap_fallback := strap_sources - strap_sources_with_bodyweight_alternative:
        missing_version, missing_stable_code = min(missing_strap_fallback)
        raise CatalogImportError(
            "STRETCH_STRAP_FALLBACK_MISSING",
            "STRETCH_STRAP exercise lacks an EQUIPMENT bodyweight alternative: "
            f"{missing_version}/{missing_stable_code}",
        )


class CatalogImporter:
    def __init__(
        self,
        repository: CatalogRepositoryPort,
        app_env: str,
        *,
        v2_import: bool = False,
        v2_taxonomy_registry_sha256: str | None = None,
    ) -> None:
        self._repository = repository
        self._app_env = app_env
        self._v2_import = v2_import
        self._v2_taxonomy_registry_sha256 = v2_taxonomy_registry_sha256

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

        artifact = load_catalog_artifact(
            artifact_directory,
            v2_import=self._v2_import,
            v2_taxonomy_registry_sha256=self._v2_taxonomy_registry_sha256,
        )
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
    """Atomically import catalogs and their DRAFT derived datasets."""

    def __init__(
        self,
        repository: CatalogRepositoryPort,
        app_env: str,
        *,
        v2_import: bool = False,
        v2_taxonomy_registry_sha256: str | None = None,
    ) -> None:
        self._repository = repository
        self._app_env = app_env
        self._v2_import = v2_import
        self._v2_taxonomy_registry_sha256 = v2_taxonomy_registry_sha256

    def import_bundle(
        self,
        session: Session,
        catalog_directories: tuple[Path, ...],
        safety_rule_directory: Path,
        alternative_directory: Path,
        prescription_directory: Path,
        media_directory: Path | None = None,
        media_reference_map: dict[str, str] | None = None,
        approved_v2_bundle: bool = False,
    ) -> CatalogDataBundleImportResult:
        # A DRAFT bundle stays confined to local/test. The reviewed V2 release is
        # a different artifact: import_v2_bundle only reaches this call after every
        # one of its four manifests matched an exact approval-registry entry, and
        # those entries carry the DOMAIN_REVIEWER sign-off that the repository
        # turns into PRODUCTION_APPROVED. Staging is allowed for that path alone;
        # production still requires its own separately reviewed release decision.
        release_import = self._v2_import and approved_v2_bundle
        allowed_envs = {"local", "test", "staging"} if release_import else {"local", "test"}
        if self._app_env not in allowed_envs:
            raise CatalogImportError(
                "CATALOG_IMPORT_ENVIRONMENT_FORBIDDEN",
                (
                    "approved V2 release import is allowed only in local, test, or staging"
                    if release_import
                    else "DRAFT catalog data import is allowed only in local or test"
                ),
            )

        catalog_artifacts = tuple(
            load_catalog_artifact(
                path,
                v2_import=self._v2_import,
                v2_taxonomy_registry_sha256=self._v2_taxonomy_registry_sha256,
            )
            for path in catalog_directories
        )
        safety_artifact = load_safety_rule_artifact(
            safety_rule_directory,
            v2_import=self._v2_import and not approved_v2_bundle,
        )
        alternative_artifact = load_alternative_artifact(
            alternative_directory,
            v2_import=self._v2_import and not approved_v2_bundle,
        )
        prescription_artifact = load_prescription_artifact(prescription_directory)
        media_artifact = (
            load_media_artifact(
                media_directory,
                representative_to_stable_code=media_reference_map,
            )
            if media_directory is not None
            else None
        )
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
        referenced_versions |= {
            row.catalog_version_code for row in prescription_artifact.goal_tag_records
        } | {row.catalog_version_code for row in prescription_artifact.prescription_records}
        if supplied_versions != referenced_versions:
            raise CatalogImportError(
                "CATALOG_BUNDLE_INCOMPLETE",
                "catalog bundle must exactly cover every derived-data catalog reference",
            )
        _validate_bundle_exercise_references(
            catalog_artifacts,
            safety_artifact,
            alternative_artifact,
            prescription_artifact,
            v2_import=self._v2_import,
        )
        if media_artifact is not None:
            catalog_stable_codes = {
                record.stable_code for artifact in catalog_artifacts for record in artifact.records
            }
            if media_artifact.manifest.catalog_version_code not in supplied_versions or (
                set(media_artifact.exercise_stable_codes) - catalog_stable_codes
            ):
                raise CatalogImportError(
                    "MEDIA_EXERCISE_REFERENCE_NOT_FOUND",
                    "media asset references an exercise absent from its catalog",
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
            prescription_count = len(prescription_artifact.goal_tag_records) + len(
                prescription_artifact.prescription_records
            )
            prescription_result = self._import_derived_set(
                session,
                prescription_artifact.manifest.prescription_set_version.version_code,
                prescription_artifact.manifest_hash,
                prescription_count,
                self._repository.get_prescription_set_state,
                lambda: self._repository.create_prescriptions(session, prescription_artifact),
            )
            media_result = None
            if media_artifact is not None:
                media_result = self._import_derived_set(
                    session,
                    media_artifact.manifest.media_set_version.version_code,
                    media_artifact.manifest_hash,
                    len(media_artifact.records),
                    self._repository.get_media_set_state,
                    lambda: self._repository.create_media_assets(session, media_artifact),
                )

        return CatalogDataBundleImportResult(
            catalogs=tuple(catalog_results),
            safety_rules=safety_result,
            alternatives=alternative_result,
            prescriptions=prescription_result,
            media_assets=media_result,
        )

    def import_v2_bundle(
        self,
        session: Session,
        bundle_directory: Path,
        *,
        expected_bundle_manifest_sha256: str,
    ) -> CatalogDataBundleImportResult:
        if not self._v2_import:
            raise CatalogImportError("V2_IMPORT_REQUIRED", "V2 bundle importer mode is required")
        root = bundle_directory.resolve()
        bundle = _load_v2_bundle_manifest(
            root,
            expected_manifest_sha256=expected_bundle_manifest_sha256,
        )
        catalog_path = _resolve_inside(root, bundle.importer_paths["catalog"])
        catalog_artifact = load_catalog_artifact(
            catalog_path.parent,
            v2_import=True,
            v2_taxonomy_registry_sha256=self._v2_taxonomy_registry_sha256,
        )
        safety_path = _resolve_inside(root, bundle.importer_paths["safety"])
        alternative_path = _resolve_inside(root, bundle.importer_paths["alternatives"])
        prescription_path = _resolve_inside(root, bundle.importer_paths["prescriptions"])
        safety = load_safety_rule_artifact(safety_path.parent)
        alternatives = load_alternative_artifact(alternative_path.parent)
        prescriptions = load_prescription_artifact(prescription_path.parent)
        actual = {
            "catalog": (
                catalog_artifact.manifest.catalog_version.version_code,
                catalog_artifact.manifest_hash,
                len(catalog_artifact.records),
            ),
            "safety": (
                safety.manifest.rule_set_version.version_code,
                safety.manifest_hash,
                len(safety.records),
            ),
            "alternatives": (
                alternatives.manifest.alternative_set_version.version_code,
                alternatives.manifest_hash,
                len(alternatives.records),
            ),
            "prescriptions": (
                prescriptions.manifest.prescription_set_version.version_code,
                prescriptions.manifest_hash,
                len(prescriptions.goal_tag_records) + len(prescriptions.prescription_records),
            ),
        }
        expected = {
            "catalog": (
                bundle.catalog_version_code,
                next(
                    entry.sha256
                    for entry in bundle.files
                    if entry.path == bundle.importer_paths["catalog"]
                ),
                bundle.summary.catalog_records,
            ),
            "safety": (
                bundle.derived_set_versions.rule_set_version_code,
                next(
                    entry.sha256
                    for entry in bundle.files
                    if entry.path == bundle.importer_paths["safety"]
                ),
                bundle.summary.safety_rule_records,
            ),
            "alternatives": (
                bundle.derived_set_versions.alternative_set_version_code,
                next(
                    entry.sha256
                    for entry in bundle.files
                    if entry.path == bundle.importer_paths["alternatives"]
                ),
                bundle.summary.alternative_records,
            ),
            "prescriptions": (
                bundle.derived_set_versions.prescription_set_version_code,
                next(
                    entry.sha256
                    for entry in bundle.files
                    if entry.path == bundle.importer_paths["prescriptions"]
                ),
                bundle.summary.goal_tag_records + bundle.summary.prescription_records,
            ),
        }
        if actual != expected:
            raise CatalogImportError(
                "BUNDLE_CONTRACT_MISMATCH",
                "bundle versions, manifest hashes, or record counts do not exactly match",
            )
        approvals = (
            get_catalog_approval(*actual["catalog"]),
            get_derived_data_approval("SAFETY_RULES", *actual["safety"]),
            get_derived_data_approval("ALTERNATIVES", *actual["alternatives"]),
            get_derived_data_approval("PRESCRIPTIONS", *actual["prescriptions"]),
        )
        if any(approval is None for approval in approvals):
            raise CatalogImportError(
                "APPROVAL_REGISTRY_MISMATCH",
                "V2 artifact is not covered by an exact approval registry entry",
            )
        media_directory = None
        media_reference_map = None
        if media_path_value := bundle.importer_paths.get("media"):
            media_directory = _resolve_inside(root, media_path_value).parent
            media_reference_map = _v2_representative_registry(catalog_path.parent, catalog_artifact)
        return self.import_bundle(
            session,
            (catalog_path.parent,),
            safety_path.parent,
            alternative_path.parent,
            prescription_path.parent,
            media_directory,
            media_reference_map,
            True,
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
    "MediaArtifact",
    "PrescriptionArtifact",
    "SafetyRuleArtifact",
    "load_alternative_artifact",
    "load_catalog_artifact",
    "load_media_artifact",
    "load_prescription_artifact",
    "load_safety_rule_artifact",
]
