"""Fail-closed validation for the reviewed home-equipment bundle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast


class HomeEquipmentBundleValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class HouseholdGuide:
    exercise_stable_code: str
    equipment_code: str
    proposal_ko: str
    examples_ko: tuple[str, ...]
    cautions_ko: tuple[str, ...]
    review_status_code: str
    content_version: str


@dataclass(frozen=True)
class EquipmentVariant:
    source_exercise_stable_code: str
    missing_equipment_code: str
    candidate_exercise_stable_code: str
    reason_code: str
    selection_rationale_ko: str
    review_status_code: str
    source_dataset_code: str


@dataclass(frozen=True)
class HomeEquipmentBundle:
    manifest_hash: str
    bundle_version: str
    registry: dict[str, Any]
    guides: tuple[HouseholdGuide, ...]
    variants: tuple[EquipmentVariant, ...]


@dataclass(frozen=True)
class ApprovedExerciseReference:
    catalog_version_code: str
    required_equipment_codes: frozenset[str]


class HomeEquipmentGuideProviderPort(Protocol):
    def guides_for(self, exercise_stable_code: str) -> tuple[HouseholdGuide, ...]: ...


class FileHomeEquipmentGuideProvider:
    """Read only validated bundle content; this class never writes to a database."""

    def __init__(self, bundle_root: Path) -> None:
        self._bundle_root = bundle_root

    def guides_for(self, exercise_stable_code: str) -> tuple[HouseholdGuide, ...]:
        return tuple(
            guide
            for guide in load_home_equipment_bundle(self._bundle_root).guides
            if guide.exercise_stable_code == exercise_stable_code
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HomeEquipmentBundleValidationError("BUNDLE_FILE_INVALID") from exc
    if not isinstance(value, dict):
        raise HomeEquipmentBundleValidationError("BUNDLE_FILE_INVALID")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise HomeEquipmentBundleValidationError("BUNDLE_FILE_INVALID") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise HomeEquipmentBundleValidationError("BUNDLE_FILE_INVALID")
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise HomeEquipmentBundleValidationError(code)


def _string_list(value: object, code: str) -> tuple[str, ...]:
    _require(isinstance(value, list) and all(isinstance(item, str) for item in value), code)
    return tuple(cast(list[str], value))


def _checked_file(root: Path, entry: dict[str, Any]) -> Path:
    path_value = entry.get("path")
    _require(isinstance(path_value, str), "MANIFEST_INVALID")
    assert isinstance(path_value, str)
    path = (root / path_value).resolve()
    _require(path.is_relative_to(root) and path.is_file(), "MANIFEST_FILE_MISSING")
    _require(path.stat().st_size == entry.get("bytes"), "MANIFEST_BYTE_MISMATCH")
    _require(_sha256(path) == entry.get("sha256"), "MANIFEST_HASH_MISMATCH")
    if "records" in entry:
        _require(len(_read_jsonl(path)) == entry["records"], "MANIFEST_RECORD_COUNT_MISMATCH")
    return path


def load_home_equipment_bundle(root: Path) -> HomeEquipmentBundle:
    root = root.resolve()
    _require(root.is_dir(), "BUNDLE_DIRECTORY_INVALID")
    manifest_path = root / "bundle_manifest.json"
    manifest = _read_json(manifest_path)
    _require(
        manifest.get("schema_version") == "home-equipment-importer-v1"
        and manifest.get("importer_entry_path") == "bundle_manifest.json",
        "MANIFEST_INVALID",
    )
    entries_raw = manifest.get("files")
    _require(isinstance(entries_raw, list) and bool(entries_raw), "MANIFEST_INVALID")
    entries = cast(list[dict[str, Any]], entries_raw)
    _require(all(isinstance(entry, dict) for entry in entries), "MANIFEST_INVALID")
    files = {
        str(entry.get("path")): _checked_file(root, entry)
        for entry in entries
        if isinstance(entry, dict)
    }
    _require(len(files) == len(entries), "MANIFEST_INVALID")
    paths_raw = manifest.get("importer_paths")
    _require(isinstance(paths_raw, dict), "MANIFEST_INVALID")
    paths = cast(dict[str, Any], paths_raw)
    _require(set(paths) == {"substitution_guides", "variant_candidates"}, "MANIFEST_INVALID")
    guide_manifest_path = paths.get("substitution_guides")
    variant_manifest_path = paths.get("variant_candidates")
    _require(
        isinstance(guide_manifest_path, str) and isinstance(variant_manifest_path, str),
        "MANIFEST_INVALID",
    )
    assert isinstance(guide_manifest_path, str)
    assert isinstance(variant_manifest_path, str)
    _require(
        guide_manifest_path in files and variant_manifest_path in files, "MANIFEST_PATH_MISMATCH"
    )
    registry_path = manifest.get("approval_registry_path")
    _require(isinstance(registry_path, str) and registry_path in files, "APPROVAL_REGISTRY_MISSING")
    assert isinstance(registry_path, str)
    registry = _read_json(files[registry_path])
    _require(
        registry.get("status_code") == "DOMAIN_APPROVED"
        and registry.get("production_eligible") is True,
        "APPROVAL_REGISTRY_NOT_APPROVED",
    )
    _require(
        registry.get("bundle_version") == manifest.get("bundle_version")
        and registry.get("importer_entry_path") == registry_path,
        "APPROVAL_REGISTRY_MISMATCH",
    )
    datasets_raw = registry.get("datasets")
    _require(isinstance(datasets_raw, list) and len(datasets_raw) == 2, "APPROVAL_REGISTRY_INVALID")
    datasets = cast(list[dict[str, Any]], datasets_raw)
    _require(all(isinstance(item, dict) for item in datasets), "APPROVAL_REGISTRY_INVALID")
    by_code = {item.get("dataset_code"): item for item in datasets if isinstance(item, dict)}
    _require(
        set(by_code)
        == {"HOME_EQUIPMENT_SUBSTITUTION_GUIDES", "HOME_EQUIPMENT_BODYWEIGHT_VARIANTS"},
        "APPROVAL_REGISTRY_INVALID",
    )

    def dataset(manifest_path_value: str, code: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        meta = _read_json(files[manifest_path_value])
        approval = by_code[code]
        _require(
            approval.get("status_code") == "DOMAIN_APPROVED"
            and approval.get("manifest_path") == manifest_path_value
            and approval.get("approved_version") == meta.get("dataset_version"),
            "APPROVAL_REGISTRY_MISMATCH",
        )
        _require(
            meta.get("bundle_version") == manifest.get("bundle_version")
            and meta.get("importer_entry_path") == manifest_path_value
            and meta.get("schema_version") == "home-equipment-importer-v1",
            "MANIFEST_INVALID",
        )
        review_paths_raw = approval.get("review_artifact_paths")
        _require(isinstance(review_paths_raw, list), "REVIEW_ARTIFACT_MISSING")
        review_paths = cast(list[str], review_paths_raw)
        _require(
            all(isinstance(path, str) and Path(path).is_file() for path in review_paths),
            "REVIEW_ARTIFACT_MISSING",
        )
        data_path = meta.get("data_path")
        _require(isinstance(data_path, str) and data_path in files, "MANIFEST_PATH_MISMATCH")
        assert isinstance(data_path, str)
        rows = _read_jsonl(files[data_path])
        _require(
            meta.get("review_status_code") == "DOMAIN_APPROVED"
            and meta.get("record_count") == len(rows)
            and approval.get("record_count") == len(rows)
            and meta.get("data_sha256") == _sha256(files[data_path]),
            "MANIFEST_RECORD_COUNT_MISMATCH",
        )
        return meta, rows

    _, guide_rows = dataset(guide_manifest_path, "HOME_EQUIPMENT_SUBSTITUTION_GUIDES")
    _, variant_rows = dataset(variant_manifest_path, "HOME_EQUIPMENT_BODYWEIGHT_VARIANTS")
    guides = tuple(
        HouseholdGuide(
            exercise_stable_code=str(row.get("exercise_stable_code", "")),
            equipment_code=str(row.get("equipment_code", "")),
            proposal_ko=str(row.get("proposal_ko", "")),
            examples_ko=_string_list(row.get("examples_ko"), "GUIDE_RECORD_INVALID"),
            cautions_ko=_string_list(row.get("cautions_ko"), "GUIDE_RECORD_INVALID"),
            review_status_code=str(row.get("review_status_code", "")),
            content_version=str(row.get("content_version", "")),
        )
        for row in guide_rows
    )
    variants = tuple(
        EquipmentVariant(
            source_exercise_stable_code=str(row.get("source_exercise_stable_code", "")),
            missing_equipment_code=str(row.get("missing_equipment_code", "")),
            candidate_exercise_stable_code=str(row.get("candidate_exercise_stable_code", "")),
            reason_code=str(row.get("reason_code", "")),
            selection_rationale_ko=str(row.get("selection_rationale_ko", "")),
            review_status_code=str(row.get("review_status_code", "")),
            source_dataset_code=str(row.get("source_dataset_code", "")),
        )
        for row in variant_rows
    )
    _require(len(guides) == 34 and len(variants) == 20, "BUNDLE_RECORD_COUNT_MISMATCH")
    _require(
        all(
            item.exercise_stable_code
            and item.equipment_code
            and item.review_status_code == "DOMAIN_APPROVED"
            and item.content_version
            for item in guides
        )
        and len({(item.exercise_stable_code, item.equipment_code) for item in guides})
        == len(guides),
        "GUIDE_RECORD_INVALID",
    )
    _require(
        all(
            item.source_exercise_stable_code
            and item.missing_equipment_code
            and item.candidate_exercise_stable_code
            and item.source_exercise_stable_code != item.candidate_exercise_stable_code
            and item.reason_code == "EQUIPMENT"
            and item.review_status_code == "DOMAIN_APPROVED"
            and item.source_dataset_code
            and item.selection_rationale_ko
            for item in variants
        )
        and len(
            {
                (
                    item.source_exercise_stable_code,
                    item.candidate_exercise_stable_code,
                    item.missing_equipment_code,
                )
                for item in variants
            }
        )
        == len(variants),
        "VARIANT_RECORD_INVALID",
    )
    return HomeEquipmentBundle(
        manifest_hash=_sha256(manifest_path),
        bundle_version=str(manifest.get("bundle_version", "")),
        registry=registry,
        guides=guides,
        variants=variants,
    )


def validate_bundle_references(
    bundle: HomeEquipmentBundle,
    exercises_by_stable_code: Mapping[str, ApprovedExerciseReference],
) -> None:
    """Reject references that a data-loading workflow must never persist.

    This is deliberately validation-only: it does not open a transaction or
    mutate a database. The data-loading owner calls it with its approved
    catalog lookup before any persistence operation.
    """

    for guide in bundle.guides:
        _require(guide.review_status_code == "DOMAIN_APPROVED", "GUIDE_RECORD_INVALID")
        exercise = exercises_by_stable_code.get(guide.exercise_stable_code)
        _require(exercise is not None, "EXERCISE_REFERENCE_NOT_FOUND")
        assert exercise is not None
        _require(
            guide.equipment_code in exercise.required_equipment_codes,
            "GUIDE_EQUIPMENT_REFERENCE_INVALID",
        )
    for variant in bundle.variants:
        _require(
            variant.reason_code == "EQUIPMENT"
            and variant.review_status_code == "DOMAIN_APPROVED"
            and variant.source_exercise_stable_code != variant.candidate_exercise_stable_code,
            "VARIANT_RECORD_INVALID",
        )
        source = exercises_by_stable_code.get(variant.source_exercise_stable_code)
        candidate = exercises_by_stable_code.get(variant.candidate_exercise_stable_code)
        _require(source is not None and candidate is not None, "EXERCISE_REFERENCE_NOT_FOUND")
        assert source is not None and candidate is not None
        _require(
            source.catalog_version_code == candidate.catalog_version_code
            and variant.missing_equipment_code in source.required_equipment_codes,
            "VARIANT_EXERCISE_REFERENCE_INVALID",
        )
