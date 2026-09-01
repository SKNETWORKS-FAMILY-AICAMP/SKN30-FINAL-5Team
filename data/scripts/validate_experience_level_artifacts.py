"""Validate the Data-owned difficulty/experience-level artifact contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_DIFFICULTIES = {"BEGINNER", "INTERMEDIATE"}
ALLOWED_EXPERIENCES = {"BEGINNER", "INTERMEDIATE"}
ALLOWED_PHASES = {"WARMUP", "MAIN", "COOLDOWN"}
ALLOWED_REASONS = {"DIFFICULTY", "EQUIPMENT", "LOCATION", "DISCOMFORT"}
DIFFICULTY_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1}
CATALOG_VERSION = "exercise-catalog-v2.0.2-draft"
PRESCRIPTION_VERSION = "prescription-set-v2.0.2-draft"
ALTERNATIVE_VERSION = "alternative-set-v2.0.2-draft"
V1_CATALOG_VERSION = "exercise-catalog-v1.0.0"


class ArtifactValidationError(ValueError):
    """Raised when a new Data-owned artifact is not fail-closed valid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ArtifactValidationError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ArtifactValidationError(f"JSONL is unreadable: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArtifactValidationError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ArtifactValidationError(f"JSONL row must be an object: {path}:{line_number}")
        rows.append(value)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv_record_count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _assert_no_legacy_field(value: Any, location: str = "artifact") -> None:
    if isinstance(value, dict):
        if "beginner_suitable" in value:
            raise ArtifactValidationError(f"legacy suitability field is forbidden: {location}")
        for key, child in value.items():
            _assert_no_legacy_field(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_legacy_field(child, f"{location}[{index}]")


def _required_text(row: dict[str, Any], field: str, location: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ArtifactValidationError(f"{location}.{field} is blank")
    return value


def _int_value(row: dict[str, Any], field: str, location: str, minimum: int = 0) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ArtifactValidationError(f"{location}.{field} must be an integer >= {minimum}")
    return value


def _versioned(row: dict[str, Any], field: str, expected: str, location: str) -> None:
    if row.get(field) != expected:
        raise ArtifactValidationError(f"{location}.{field} is not {expected}")


def validate_catalog_records(
    rows: list[dict[str, Any]], *, production_eligible: bool
) -> dict[str, Any]:
    if not rows:
        raise ArtifactValidationError("catalog is empty")
    seen: set[str] = set()
    difficulty_counts: Counter[str] = Counter()
    for row in rows:
        stable_code = _required_text(row, "stable_code", "catalog")
        if stable_code in seen:
            raise ArtifactValidationError(f"duplicate catalog stable_code: {stable_code}")
        seen.add(stable_code)
        _versioned(row, "catalog_version_code", CATALOG_VERSION, stable_code)
        difficulty = row.get("difficulty_code")
        if difficulty not in ALLOWED_DIFFICULTIES:
            if production_eligible:
                raise ArtifactValidationError(f"unresolved catalog difficulty: {stable_code}")
            raise ArtifactValidationError(f"invalid catalog difficulty: {stable_code}")
        difficulty_counts[str(difficulty)] += 1
        if row.get("difficulty_status") != "APPROVED":
            if production_eligible:
                raise ArtifactValidationError(
                    f"unresolved catalog difficulty status: {stable_code}"
                )
            raise ArtifactValidationError(
                f"catalog difficulty status is not APPROVED: {stable_code}"
            )
        for field in (
            "name_ko",
            "name_en",
            "training_type_code",
            "body_focus_code",
            "primary_movement_pattern_code",
            "timing_mode_code",
            "review_status_code",
            "source_track",
            "source_identity",
        ):
            _required_text(row, field, stable_code)
        for field in (
            "equipment_codes",
            "location_codes",
            "primary_body_area_codes",
            "secondary_body_area_codes",
        ):
            value = row.get(field)
            if (
                not isinstance(value, list)
                or (field != "secondary_body_area_codes" and not value)
                or not all(isinstance(item, str) and item for item in value)
            ):
                raise ArtifactValidationError(
                    f"{stable_code}.{field} must be a non-empty string array"
                )
        if row.get("production_eligible") is not False:
            raise ArtifactValidationError(
                f"catalog must remain production-ineligible: {stable_code}"
            )
    return {"records": len(rows), "difficulty_counts": dict(sorted(difficulty_counts.items()))}


def validate_enrichment_records(
    rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if len(rows) != len(catalog):
        raise ArtifactValidationError("catalog enrichment does not cover the catalog")
    by_stable: dict[str, dict[str, Any]] = {}
    for row in rows:
        stable_code = _required_text(row, "exercise_stable_code", "enrichment")
        if stable_code in by_stable or stable_code not in catalog:
            raise ArtifactValidationError(
                f"invalid or duplicate enrichment reference: {stable_code}"
            )
        _versioned(row, "catalog_version_code", CATALOG_VERSION, stable_code)
        if row.get("difficulty_code") != catalog[stable_code]["difficulty_code"]:
            raise ArtifactValidationError(
                f"enrichment difficulty disagrees with catalog: {stable_code}"
            )
        expected = (
            ["BEGINNER", "INTERMEDIATE"]
            if row["difficulty_code"] == "BEGINNER"
            else ["INTERMEDIATE"]
        )
        if row.get("allowed_experience_level_codes") != expected:
            raise ArtifactValidationError(f"invalid experience coverage mapping: {stable_code}")
        v1_ids = row.get("v1_exercise_ids")
        if (
            not isinstance(v1_ids, list)
            or not v1_ids
            or not all(isinstance(exercise_id, str) and exercise_id for exercise_id in v1_ids)
            or len(v1_ids) != len(set(v1_ids))
        ):
            raise ArtifactValidationError(f"invalid V1 exercise mapping: {stable_code}")
        templates = row.get("fitt_template_ids_by_experience")
        if not isinstance(templates, dict) or set(templates) != set(
            row["allowed_experience_level_codes"]
        ):
            raise ArtifactValidationError(f"FITT template mapping is incomplete: {stable_code}")
        by_stable[stable_code] = row
    return by_stable


def validate_goal_links(rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]) -> None:
    keys: set[tuple[str, str, str]] = set()
    for row in rows:
        stable_code = _required_text(row, "exercise_stable_code", "goal link")
        if stable_code not in catalog:
            raise ArtifactValidationError(f"goal link references unknown exercise: {stable_code}")
        _versioned(row, "catalog_version_code", CATALOG_VERSION, stable_code)
        if row.get("goal_code") != "GENERAL_FITNESS":
            raise ArtifactValidationError(f"unsupported goal link: {stable_code}")
        key = (CATALOG_VERSION, stable_code, str(row["goal_code"]))
        if key in keys:
            raise ArtifactValidationError(f"duplicate goal link: {key}")
        keys.add(key)
    if {key[1] for key in keys} != set(catalog):
        raise ArtifactValidationError("goal links do not cover the catalog")


def validate_v1_alias_records(
    rows: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    enrichment: dict[str, dict[str, Any]],
) -> int:
    if not rows:
        raise ArtifactValidationError("V1 exercise aliases are empty")
    seen_v1_ids: set[str] = set()
    expected_v1_ids: set[str] = set()
    for mapping in enrichment.values():
        expected_v1_ids.update(mapping["v1_exercise_ids"])
    for row in rows:
        exercise_id = _required_text(row, "v1_exercise_id", "V1 alias")
        if exercise_id in seen_v1_ids:
            raise ArtifactValidationError(f"duplicate V1 exercise alias: {exercise_id}")
        seen_v1_ids.add(exercise_id)
        _versioned(row, "catalog_version_code", CATALOG_VERSION, exercise_id)
        if row.get("source_catalog_version_code") != V1_CATALOG_VERSION:
            raise ArtifactValidationError(f"V1 alias source version is invalid: {exercise_id}")
        stable_code = _required_text(row, "exercise_stable_code", "V1 alias")
        if stable_code not in catalog:
            raise ArtifactValidationError(f"V1 alias references unknown exercise: {exercise_id}")
        if row.get("difficulty_code") != catalog[stable_code]["difficulty_code"]:
            raise ArtifactValidationError(f"V1 alias difficulty is stale: {exercise_id}")
        if row.get("difficulty_status") != "APPROVED":
            raise ArtifactValidationError(f"V1 alias difficulty is unresolved: {exercise_id}")
        mapping = enrichment[stable_code]
        if row.get("allowed_experience_level_codes") != mapping["allowed_experience_level_codes"]:
            raise ArtifactValidationError(f"V1 alias experience mapping is stale: {exercise_id}")
        if row.get("fitt_template_ids_by_experience") != mapping["fitt_template_ids_by_experience"]:
            raise ArtifactValidationError(f"V1 alias FITT mapping is stale: {exercise_id}")
        for field in (
            "v1_exercise_name_ko",
            "v1_name_en",
            "v1_source_name_en",
            "v1_training_type_code",
            "v1_body_focus_code",
            "v1_timing_mode_code",
            "v1_intensity_level",
        ):
            _required_text(row, field, exercise_id)
        for field in (
            "v1_primary_body_area_codes",
            "v1_secondary_body_area_codes",
            "v1_target_body_area_codes",
        ):
            value = row.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item for item in value
            ):
                raise ArtifactValidationError(
                    f"V1 alias feature snapshot is invalid: {exercise_id}"
                )
        for field in (
            "v1_default_sets",
            "v1_default_reps",
            "v1_default_work_seconds",
            "v1_default_rest_seconds",
            "v1_default_transition_seconds",
        ):
            if not isinstance(row.get(field), str):
                raise ArtifactValidationError(f"V1 alias timing snapshot is invalid: {exercise_id}")
        if row.get("alias_only") is not True or row.get("production_eligible") is not False:
            raise ArtifactValidationError(f"V1 alias eligibility is invalid: {exercise_id}")
    if seen_v1_ids != expected_v1_ids:
        raise ArtifactValidationError("V1 aliases do not cover the representative mapping")
    return len(rows)


def validate_combined_exercise_records(
    rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    enrichment_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Validate the single Data-side V1/V2 handoff file."""
    expected_count = len(catalog_rows) + len(alias_rows)
    if len(rows) != expected_count:
        raise ArtifactValidationError(
            f"combined exercise record count is {len(rows)}, expected {expected_count}"
        )
    actual_catalog: dict[str, dict[str, Any]] = {}
    actual_aliases: dict[str, dict[str, Any]] = {}
    for row in rows:
        record_type = row.get("record_type")
        payload = {key: value for key, value in row.items() if key != "record_type"}
        if record_type == "EXERCISE":
            stable_code = _required_text(row, "stable_code", "combined exercise")
            if stable_code in actual_catalog:
                raise ArtifactValidationError(
                    f"duplicate combined exercise stable_code: {stable_code}"
                )
            actual_catalog[stable_code] = payload
        elif record_type == "V1_ALIAS":
            exercise_id = _required_text(row, "v1_exercise_id", "combined V1 alias")
            if exercise_id in actual_aliases:
                raise ArtifactValidationError(f"duplicate combined V1 exercise ID: {exercise_id}")
            actual_aliases[exercise_id] = payload
        else:
            raise ArtifactValidationError(f"invalid combined record_type: {record_type}")
    expected_catalog = {row["stable_code"]: row for row in catalog_rows}
    enrichment = {row["exercise_stable_code"]: row for row in enrichment_rows}
    expected_aliases = {row["v1_exercise_id"]: row for row in alias_rows}
    for stable_code, catalog in expected_catalog.items():
        combined = actual_catalog.get(stable_code)
        mapping = enrichment.get(stable_code)
        if combined is None or mapping is None:
            raise ArtifactValidationError("combined V2 exercise coverage is incomplete")
        expected = {
            **catalog,
            "allowed_experience_level_codes": mapping["allowed_experience_level_codes"],
            "fitt_template_ids_by_experience": mapping["fitt_template_ids_by_experience"],
            "fitt_mapping_exception_code": mapping["fitt_mapping_exception_code"],
            "fitt_mapping_note": mapping["fitt_mapping_note"],
            "mapping_source_exercise_id": mapping["mapping_source_exercise_id"],
            "v1_exercise_ids": mapping["v1_exercise_ids"],
            "artifact_review_status_code": "REVIEW_REQUIRED",
            "review_required": True,
        }
        if combined != expected:
            raise ArtifactValidationError(f"combined V2 exercise is stale: {stable_code}")
    for exercise_id, alias in expected_aliases.items():
        combined = actual_aliases.get(exercise_id)
        if combined != {
            **alias,
            "artifact_review_status_code": "REVIEW_REQUIRED",
            "review_required": True,
        }:
            raise ArtifactValidationError(f"combined V1 alias is stale: {exercise_id}")
    return {"EXERCISE": len(actual_catalog), "V1_ALIAS": len(actual_aliases)}


def validate_prescription_records(
    rows: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    enrichment: dict[str, dict[str, Any]],
) -> dict[str, int]:
    keys: set[tuple[str, str, str, str, str]] = set()
    coverage: Counter[tuple[str, str]] = Counter()
    for row in rows:
        stable_code = _required_text(row, "exercise_stable_code", "prescription")
        if stable_code not in catalog:
            raise ArtifactValidationError(
                f"prescription references unknown exercise: {stable_code}"
            )
        _versioned(row, "catalog_version_code", CATALOG_VERSION, stable_code)
        _versioned(row, "prescription_version", PRESCRIPTION_VERSION, stable_code)
        experience = row.get("experience_level_code")
        difficulty = catalog[stable_code]["difficulty_code"]
        if experience not in ALLOWED_EXPERIENCES:
            raise ArtifactValidationError(f"invalid experience level: {stable_code}")
        if experience == "BEGINNER" and difficulty != "BEGINNER":
            raise ArtifactValidationError(
                f"intermediate exercise has a beginner profile: {stable_code}"
            )
        if experience == "INTERMEDIATE" and difficulty not in ALLOWED_DIFFICULTIES:
            raise ArtifactValidationError(f"invalid intermediate profile source: {stable_code}")
        phase = row.get("phase_code")
        if phase not in ALLOWED_PHASES:
            raise ArtifactValidationError(f"invalid prescription phase: {stable_code}")
        key = (CATALOG_VERSION, stable_code, str(row.get("goal_code")), str(experience), str(phase))
        if key in keys:
            raise ArtifactValidationError(f"duplicate prescription natural key: {key}")
        keys.add(key)
        if row.get("goal_code") != "GENERAL_FITNESS":
            raise ArtifactValidationError(f"unsupported prescription goal: {stable_code}")
        if row.get("exercise_difficulty_code") != difficulty:
            raise ArtifactValidationError(
                f"prescription difficulty snapshot is stale: {stable_code}"
            )
        expected_template = enrichment[stable_code]["fitt_template_ids_by_experience"].get(
            experience
        )
        if row.get("fitt_template_id") != expected_template:
            raise ArtifactValidationError(f"prescription FITT reference is stale: {stable_code}")
        if row.get("production_eligible") is not False:
            raise ArtifactValidationError(
                f"prescription must remain production-ineligible: {stable_code}"
            )
        _int_value(row, "sets", stable_code, minimum=1)
        _int_value(row, "rest_seconds_per_set", stable_code, minimum=0)
        timing_values = [row.get("reps"), row.get("work_seconds_per_set")]
        if sum(value is not None for value in timing_values) != 1:
            raise ArtifactValidationError(f"prescription timing is ambiguous: {stable_code}")
        for value in timing_values:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ArtifactValidationError(f"prescription timing is invalid: {stable_code}")
        _required_text(row, "intensity_code", stable_code)
        _required_text(row, "review_status_code", stable_code)
        coverage[(str(difficulty), str(experience))] += 1
    if not rows:
        raise ArtifactValidationError("prescription profiles are empty")
    if coverage["BEGINNER", "BEGINNER"] == 0:
        raise ArtifactValidationError("BEGINNER difficulty has no BEGINNER profile")
    if coverage["BEGINNER", "INTERMEDIATE"] == 0:
        raise ArtifactValidationError("BEGINNER difficulty has no INTERMEDIATE profile")
    if coverage["INTERMEDIATE", "INTERMEDIATE"] == 0:
        raise ArtifactValidationError("INTERMEDIATE difficulty has no INTERMEDIATE profile")
    if coverage["INTERMEDIATE", "BEGINNER"] != 0:
        raise ArtifactValidationError("INTERMEDIATE difficulty has a BEGINNER profile")
    return {
        f"{difficulty}:{experience}": count
        for (difficulty, experience), count in sorted(coverage.items())
    }


def prescription_exercise_coverage(
    rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, int]:
    coverage: dict[str, set[str]] = {}
    for row in rows:
        stable_code = row["exercise_stable_code"]
        key = f"{catalog[stable_code]['difficulty_code']}:{row['experience_level_code']}"
        coverage.setdefault(key, set()).add(stable_code)
    return {key: len(values) for key, values in sorted(coverage.items())}


def _catalog_areas(row: dict[str, Any]) -> set[str]:
    return set(row["primary_body_area_codes"]) | set(row["secondary_body_area_codes"])


def validate_alternative_records(
    rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, int]:
    keys: set[tuple[str, str, str, str]] = set()
    reason_counts: Counter[str] = Counter()
    for row in rows:
        source = _required_text(row, "source_exercise_stable_code", "alternative")
        target = _required_text(row, "alternative_exercise_stable_code", "alternative")
        if source not in catalog or target not in catalog:
            raise ArtifactValidationError(f"alternative endpoint is unknown: {source}:{target}")
        if source == target:
            raise ArtifactValidationError(f"alternative self-reference: {source}")
        _versioned(row, "source_catalog_version_code", CATALOG_VERSION, source)
        _versioned(row, "alternative_catalog_version_code", CATALOG_VERSION, source)
        if row.get("alternative_set_version_code") != ALTERNATIVE_VERSION:
            raise ArtifactValidationError(f"alternative version is stale: {source}:{target}")
        reason = row.get("reason_code")
        if reason not in ALLOWED_REASONS:
            raise ArtifactValidationError(f"invalid alternative reason: {source}:{target}")
        goal = _required_text(row, "goal_preservation_code", "alternative")
        key = (source, target, str(reason), goal)
        if key in keys:
            raise ArtifactValidationError(f"duplicate alternative natural key: {key}")
        keys.add(key)
        try:
            delta = int(row["difficulty_delta"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactValidationError(f"invalid alternative difficulty delta: {key}") from exc
        expected_delta = (
            DIFFICULTY_RANK[catalog[target]["difficulty_code"]]
            - DIFFICULTY_RANK[catalog[source]["difficulty_code"]]
        )
        if delta != expected_delta or delta not in {-1, 0}:
            raise ArtifactValidationError(f"alternative difficulty policy violation: {key}")
        if row.get("production_eligible") is not False:
            raise ArtifactValidationError(f"alternative must remain production-ineligible: {key}")
        _required_text(row, "rule_version", "alternative")
        metadata = row.get("source_metadata")
        if not isinstance(metadata, dict):
            raise ArtifactValidationError(f"alternative provenance is missing: {key}")
        if reason == "EQUIPMENT" and set(catalog[source]["equipment_codes"]) == set(
            catalog[target]["equipment_codes"]
        ):
            raise ArtifactValidationError(f"equipment relation has no equipment change: {key}")
        if reason == "LOCATION" and set(catalog[source]["location_codes"]) == set(
            catalog[target]["location_codes"]
        ):
            raise ArtifactValidationError(f"location relation has no location change: {key}")
        if reason == "DIFFICULTY" and delta != -1:
            raise ArtifactValidationError(f"difficulty relation is not a downshift: {key}")
        if reason == "DISCOMFORT":
            score_band = metadata.get("score_band_code")
            pain_area = metadata.get("body_area_code")
            if score_band == "NRS_4_6" and pain_area in _catalog_areas(catalog[target]):
                raise ArtifactValidationError(f"discomfort relation retains affected area: {key}")
        reason_counts[str(reason)] += 1
    if not rows:
        raise ArtifactValidationError("alternatives are empty")
    return dict(sorted(reason_counts.items()))


def validate_safety_records(rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]) -> int:
    if not rows:
        raise ArtifactValidationError("safety rules are empty")
    for row in rows:
        stable_code = _required_text(row, "exercise_stable_code", "safety")
        if stable_code not in catalog:
            raise ArtifactValidationError(f"safety rule references unknown exercise: {stable_code}")
        _versioned(row, "catalog_version_code", CATALOG_VERSION, stable_code)
        if row.get("production_eligible") is not False:
            raise ArtifactValidationError(
                f"safety rule must remain production-ineligible: {stable_code}"
            )
    return len(rows)


def _verify_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    if manifest.get("production_eligible") is not False:
        raise ArtifactValidationError("artifact manifest must remain production-ineligible")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ArtifactValidationError("artifact manifest has no files")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ArtifactValidationError("manifest file entry is invalid")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ArtifactValidationError("manifest path is invalid")
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise ArtifactValidationError("manifest path escapes artifact directory")
        if not path.is_file():
            raise ArtifactValidationError(f"manifest file is missing: {relative}")
        raw = path.read_bytes()
        if entry.get("sha256") != hashlib.sha256(raw).hexdigest() or entry.get("bytes") != len(raw):
            raise ArtifactValidationError(f"manifest hash or byte count mismatch: {relative}")
        if "records" in entry:
            actual_records = (
                len([line for line in raw.decode("utf-8").splitlines() if line.strip()])
                if path.suffix == ".jsonl"
                else _csv_record_count(path)
                if path.suffix == ".csv"
                else 1
            )
            if entry["records"] != actual_records:
                raise ArtifactValidationError(f"manifest record count mismatch: {relative}")
    return manifest


def _assert_payload_copy(root: Path, source: str, copy: str) -> None:
    if (root / source).read_bytes() != (root / copy).read_bytes():
        raise ArtifactValidationError(f"payload copy is inconsistent: {source} != {copy}")


def validate_combined_csv(path: Path, expected: dict[str, int]) -> None:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "record_type" not in reader.fieldnames:
                raise ArtifactValidationError("combined CSV record_type column is missing")
            counts: Counter[str] = Counter()
            for row in reader:
                counts[row.get("record_type", "")] += 1
    except OSError as exc:
        raise ArtifactValidationError(f"combined CSV is unreadable: {path}") from exc
    if dict(sorted(counts.items())) != dict(sorted(expected.items())):
        raise ArtifactValidationError("combined CSV record types are invalid")


def select_profile(
    catalog_rows: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]],
    experience_level_code: str,
    *,
    downshift: bool = False,
) -> dict[str, Any]:
    """Select a deterministic profile under the requested candidate policy."""
    if experience_level_code not in ALLOWED_EXPERIENCES:
        raise ArtifactValidationError("unsupported experience level")
    if downshift and experience_level_code != "INTERMEDIATE":
        raise ArtifactValidationError("downshift is only supported for INTERMEDIATE")
    profile_level = "BEGINNER" if downshift else experience_level_code
    allowed_difficulties = {"BEGINNER"} if profile_level == "BEGINNER" else ALLOWED_DIFFICULTIES
    catalog_by_code = {row["stable_code"]: row for row in catalog_rows}
    candidates = [
        row
        for row in profile_rows
        if row["experience_level_code"] == profile_level
        and catalog_by_code[row["exercise_stable_code"]]["difficulty_code"] in allowed_difficulties
    ]
    if not candidates:
        raise ArtifactValidationError("no profile satisfies the candidate policy")
    return sorted(candidates, key=lambda row: (row["exercise_stable_code"], row["phase_code"]))[0]


def validate_directory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = _verify_manifest(root, root / "manifest.json")
    if (
        manifest.get("catalog_version_code") != CATALOG_VERSION
        or manifest.get("prescription_set_version_code") != PRESCRIPTION_VERSION
        or manifest.get("alternative_set_version_code") != ALTERNATIVE_VERSION
    ):
        raise ArtifactValidationError("catalog version is invalid")
    policy = manifest.get("policy")
    if (
        not isinstance(policy, dict)
        or policy.get("difficulty_experience_equality_required") is not False
    ):
        raise ArtifactValidationError("difficulty and experience equality must not be required")
    if policy.get("candidate_matrix") != {
        "BEGINNER": ["BEGINNER"],
        "INTERMEDIATE": ["BEGINNER", "INTERMEDIATE"],
        "INTERMEDIATE_DOWNSHIFT": ["BEGINNER"],
    }:
        raise ArtifactValidationError("candidate policy matrix is invalid")
    if policy.get("fitt_selection") != {
        "BEGINNER": "BEGINNER",
        "INTERMEDIATE": "INTERMEDIATE",
        "INTERMEDIATE_DOWNSHIFT": "BEGINNER",
    }:
        raise ArtifactValidationError("FITT selection policy is invalid")
    _verify_manifest(root, root / "runtime/manifest.json")
    _verify_manifest(root, root / "backend_bundle/manifest.json")
    catalog_rows = _read_jsonl(root / "catalog/exercises.jsonl")
    _assert_no_legacy_field(catalog_rows, "catalog")
    catalog_report = validate_catalog_records(catalog_rows, production_eligible=False)
    catalog = {row["stable_code"]: row for row in catalog_rows}
    enrichment_rows = _read_jsonl(root / "catalog/catalog_enrichment.jsonl")
    _assert_no_legacy_field(enrichment_rows, "enrichment")
    enrichment = validate_enrichment_records(enrichment_rows, catalog)
    v1_alias_rows = _read_jsonl(root / "catalog/v1_exercise_aliases.jsonl")
    _assert_no_legacy_field(v1_alias_rows, "V1 aliases")
    v1_alias_count = validate_v1_alias_records(v1_alias_rows, catalog, enrichment)
    combined_rows = _read_jsonl(root / "catalog/exercises_v1_v2.jsonl")
    _assert_no_legacy_field(combined_rows, "combined exercises")
    combined_report = validate_combined_exercise_records(
        combined_rows, catalog_rows, enrichment_rows, v1_alias_rows
    )
    validate_combined_csv(root / "catalog/exercises_v1_v2.csv", combined_report)
    goal_rows = _read_jsonl(root / "prescriptions/goal_tag_links.jsonl")
    profile_rows = _read_jsonl(root / "prescriptions/prescription_profiles.jsonl")
    _assert_no_legacy_field(goal_rows, "goal links")
    _assert_no_legacy_field(profile_rows, "prescriptions")
    validate_goal_links(goal_rows, catalog)
    profile_report = validate_prescription_records(profile_rows, catalog, enrichment)
    alternative_rows = _read_jsonl(root / "alternatives/alternatives.jsonl")
    _assert_no_legacy_field(alternative_rows, "alternatives")
    alternative_report = validate_alternative_records(alternative_rows, catalog)
    safety_rows = _read_jsonl(root / "runtime/safety_rules.jsonl")
    _assert_no_legacy_field(safety_rows, "safety")
    safety_count = validate_safety_records(safety_rows, catalog)
    for relative in (
        "runtime/catalog.jsonl",
        "runtime/exercises_v1_v2.jsonl",
        "runtime/exercises_v1_v2.csv",
        "runtime/v1_exercise_aliases.jsonl",
        "runtime/prescription_profiles.jsonl",
        "runtime/alternatives.jsonl",
        "backend_bundle/catalog/exercises.jsonl",
        "backend_bundle/catalog/exercises_v1_v2.jsonl",
        "backend_bundle/catalog/exercises_v1_v2.csv",
        "backend_bundle/catalog/catalog_enrichment.jsonl",
        "backend_bundle/catalog/v1_exercise_aliases.jsonl",
        "backend_bundle/prescriptions/goal_tag_links.jsonl",
        "backend_bundle/prescriptions/prescription_profiles.jsonl",
        "backend_bundle/alternatives/alternatives.jsonl",
        "backend_bundle/safety/safety_rules.jsonl",
    ):
        payload = (root / relative).read_text(encoding="utf-8")
        if "beginner_suitable" in payload:
            raise ArtifactValidationError(f"legacy field text found in {relative}")
    for path in root.rglob("*"):
        if path.is_file() and "beginner_suitable" in path.read_text(encoding="utf-8"):
            raise ArtifactValidationError(f"legacy field text found in {path.relative_to(root)}")
    for source, copy in (
        ("catalog/exercises.jsonl", "runtime/catalog.jsonl"),
        ("catalog/exercises_v1_v2.jsonl", "runtime/exercises_v1_v2.jsonl"),
        ("catalog/exercises_v1_v2.csv", "runtime/exercises_v1_v2.csv"),
        ("catalog/exercises.jsonl", "backend_bundle/catalog/exercises.jsonl"),
        (
            "catalog/exercises_v1_v2.jsonl",
            "backend_bundle/catalog/exercises_v1_v2.jsonl",
        ),
        (
            "catalog/exercises_v1_v2.csv",
            "backend_bundle/catalog/exercises_v1_v2.csv",
        ),
        ("catalog/catalog_enrichment.jsonl", "backend_bundle/catalog/catalog_enrichment.jsonl"),
        (
            "catalog/v1_exercise_aliases.jsonl",
            "runtime/v1_exercise_aliases.jsonl",
        ),
        (
            "catalog/v1_exercise_aliases.jsonl",
            "backend_bundle/catalog/v1_exercise_aliases.jsonl",
        ),
        ("prescriptions/goal_tag_links.jsonl", "backend_bundle/prescriptions/goal_tag_links.jsonl"),
        (
            "prescriptions/prescription_profiles.jsonl",
            "runtime/prescription_profiles.jsonl",
        ),
        (
            "prescriptions/prescription_profiles.jsonl",
            "backend_bundle/prescriptions/prescription_profiles.jsonl",
        ),
        ("alternatives/alternatives.jsonl", "runtime/alternatives.jsonl"),
        ("alternatives/alternatives.jsonl", "backend_bundle/alternatives/alternatives.jsonl"),
        ("runtime/safety_rules.jsonl", "backend_bundle/safety/safety_rules.jsonl"),
    ):
        _assert_payload_copy(root, source, copy)
    if any(entry.get("catalog_version_code") != CATALOG_VERSION for entry in safety_rows):
        raise ArtifactValidationError("safety catalog version is inconsistent")
    return {
        "status": "valid",
        "catalog_records": catalog_report["records"],
        "difficulty_counts": catalog_report["difficulty_counts"],
        "prescription_coverage": profile_report,
        "prescription_exercise_coverage": prescription_exercise_coverage(profile_rows, catalog),
        "prescription_records": len(profile_rows),
        "goal_tag_records": len(goal_rows),
        "v1_alias_records": v1_alias_count,
        "combined_exercise_records": combined_report,
        "alternative_records": len(alternative_rows),
        "alternative_reason_counts": alternative_report,
        "safety_rule_records": safety_count,
        "legacy_field_occurrences": 0,
        "version_consistent": True,
        "manifest_sha256": _sha256(root / "manifest.json"),
        "production_eligible": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(validate_directory(args.artifact), ensure_ascii=False, sort_keys=True))
    except (ArtifactValidationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
