"""Build the Data-owned vNext catalog, FITT profiles, runtime, and bundle.

The source catalog and existing FITT templates are read-only inputs.  This
builder intentionally does not read the historical beginner-suitability value.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from validate_experience_level_artifacts import (
    ALTERNATIVE_VERSION,
    CATALOG_VERSION,
    PRESCRIPTION_VERSION,
    ArtifactValidationError,
    validate_directory,
)  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
SOURCE_CATALOG = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.1-final/representative_exercises_v2_final.csv"
)
SOURCE_V1_CATALOG = DATA_ROOT / "generated/exercise-catalog-v1.0.0/exercise_catalog_v1.csv"
SOURCE_ENRICHMENT = DATA_ROOT / "normalized/catalog_enrichment_v3_fitt.csv"
SOURCE_BEGINNER_TEMPLATE = (
    DATA_ROOT / "generated/exercise-prescriptions-v2.0.2-draft/fitt_template_beginner_v1.csv"
)
SOURCE_BEGINNER_REVIEW = DATA_ROOT / "FITT_REFERENCE_ASSESSMENT.md"
SOURCE_INTERMEDIATE_TEMPLATE = (
    DATA_ROOT / "generated/exercise-prescriptions-v2.0.2-draft/fitt_template_intermediate_v1.json"
)
SOURCE_ALTERNATIVES = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.1-final/runtime/alternatives.jsonl"
)
SOURCE_GOAL_LINKS = DATA_ROOT / "generated/exercise-prescriptions-v2.0.1-draft/goal_tag_links.jsonl"
SOURCE_SAFETY = DATA_ROOT / "generated/exercise-catalog-v2.0.1-final/runtime/safety_rules.jsonl"
DEFAULT_OUTPUT = DATA_ROOT / "generated/exercise-catalog-v2.0.2-draft"

GENERATOR_VERSION = "experience-level-artifacts-v2-1.0.0"
V1_CATALOG_VERSION = "exercise-catalog-v1.0.0"
ALLOWED_DIFFICULTIES = {"BEGINNER", "INTERMEDIATE"}
ALLOWED_EXPERIENCES = {"BEGINNER", "INTERMEDIATE"}
TEMPLATE_STATUS_BEGINNER = "DRAFT"


class BuildError(ValueError):
    """Raised when a source cannot be materialized into the vNext contract."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise BuildError(f"CSV header is missing: {path}")
            return [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    except OSError as exc:
        raise BuildError(f"CSV is unreadable: {path}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"JSON is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"JSON object is required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BuildError(f"JSONL is unreadable: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BuildError(f"JSONL is invalid at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise BuildError(f"JSONL row must be an object: {path}:{line_number}")
        rows.append(value)
    return rows


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise BuildError(f"cannot write empty CSV: {path}")
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {field: _csv_value(row.get(field)) for field in fieldnames} for row in rows
        )


def _csv_record_count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _json_array(value: str, field: str, key: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise BuildError(f"{field} is not JSON for {key}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) and item for item in parsed):
        raise BuildError(f"{field} must be a string array for {key}")
    return parsed


def _bool(value: str, field: str, key: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise BuildError(f"{field} is not boolean for {key}")


def _first_int(value: str, field: str, key: str, *, required: bool = True) -> int | None:
    if not value:
        if required:
            raise BuildError(f"{field} is blank for {key}")
        return None
    match = re.match(r"^\s*(\d+)", value)
    if match is None or int(match.group(1)) <= 0:
        raise BuildError(f"{field} is not a positive integer/range for {key}")
    return int(match.group(1))


def _int_or_default(value: str, default: int, field: str, key: str) -> int:
    parsed = _first_int(value, field, key, required=False)
    return default if parsed is None else parsed


def _base_template_id(template_id: str) -> str:
    return template_id.replace("-INTERMEDIATE-V1", "-V1")


def _assessment_status(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^상태:\s*`?([A-Z_]+)`?\s*$", text, re.MULTILINE)
    production = re.search(r"^프로덕션 사용 가능:\s*`?([^\s`]+)`?\s*$", text, re.MULTILINE)
    if match is None or production is None or production.group(1).lower() != "false":
        raise BuildError("BEGINNER FITT review assessment is missing DRAFT/ineligible evidence")
    return match.group(1)


def load_templates() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, Any]], dict[str, Any]]:
    beginner_rows = _read_csv(SOURCE_BEGINNER_TEMPLATE)
    if not beginner_rows:
        raise BuildError("BEGINNER FITT template is empty")
    beginner: dict[str, dict[str, str]] = {}
    for row in beginner_rows:
        template_id = row.get("fitt_template_id", "")
        if not template_id or template_id in beginner:
            raise BuildError(f"BEGINNER FITT template ID is duplicated or blank: {template_id}")
        if row.get("experience_level_code") != "BEGINNER":
            raise BuildError(f"BEGINNER FITT template has invalid experience level: {template_id}")
        beginner[template_id] = row
    beginner_status = _assessment_status(SOURCE_BEGINNER_REVIEW)
    if beginner_status != TEMPLATE_STATUS_BEGINNER:
        raise BuildError("BEGINNER FITT review status is not DRAFT")

    intermediate_document = _read_json(SOURCE_INTERMEDIATE_TEMPLATE)
    if (
        intermediate_document.get("schema_version") != "1.1"
        or intermediate_document.get("artifact_version") != "fitt-template-intermediate-v1"
        or intermediate_document.get("target_catalog_version") != CATALOG_VERSION
        or intermediate_document.get("target_prescription_version")
        != "exercise-prescriptions-v2.0.2-draft"
        or intermediate_document.get("status_code") != "DRAFT"
        or intermediate_document.get("review_status_code") != "REVIEW_REQUIRED"
        or intermediate_document.get("production_eligible") is not False
        or intermediate_document.get("review_required") is not True
        or not str(intermediate_document.get("review_reason", "")).strip()
    ):
        raise BuildError("INTERMEDIATE FITT template schema/version/review evidence is invalid")
    intermediate_rows = intermediate_document.get("templates")
    if not isinstance(intermediate_rows, list) or not intermediate_rows:
        raise BuildError("INTERMEDIATE FITT templates are empty")
    intermediate: dict[str, dict[str, Any]] = {}
    for row in intermediate_rows:
        if not isinstance(row, dict):
            raise BuildError("INTERMEDIATE FITT template row is invalid")
        template_id = str(row.get("fitt_template_id", ""))
        if not template_id or template_id in intermediate:
            raise BuildError(f"INTERMEDIATE FITT template ID is duplicated or blank: {template_id}")
        if row.get("experience_level_code") != "INTERMEDIATE":
            raise BuildError(
                f"INTERMEDIATE FITT template has invalid experience level: {template_id}"
            )
        intermediate[template_id] = row
    if {_base_template_id(key) for key in intermediate} != set(beginner):
        raise BuildError("BEGINNER and INTERMEDIATE FITT template sets do not align")
    for intermediate_id, row in intermediate.items():
        base_id = _base_template_id(intermediate_id)
        for field in ("movement_pattern", "training_category", "prescription_unit"):
            if row.get(field) != beginner[base_id].get(field):
                raise BuildError(
                    f"FITT template structure differs by experience: {base_id}:{field}"
                )
    return (
        beginner,
        intermediate,
        {
            "beginner_review_status_code": beginner_status,
            "intermediate_review_status_code": intermediate_document["review_status_code"],
            "intermediate_artifact_version": intermediate_document.get("artifact_version"),
        },
    )


def load_catalog() -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    rows = _read_csv(SOURCE_CATALOG)
    if not rows:
        raise BuildError("source catalog is empty")
    by_stable: dict[str, dict[str, Any]] = {}
    for source in rows:
        stable_code = source.get("stable_code", "")
        if not stable_code or stable_code in by_stable:
            raise BuildError(f"source catalog stable_code is blank or duplicated: {stable_code}")
        difficulty = source.get("difficulty_code", "")
        if difficulty not in ALLOWED_DIFFICULTIES:
            raise BuildError(f"source catalog difficulty is unresolved: {stable_code}")
        if source.get("difficulty_status") != "APPROVED":
            raise BuildError(f"source catalog difficulty is not approved: {stable_code}")
        by_stable[stable_code] = {"source": source}
    return rows, by_stable


def load_v1_catalog() -> list[dict[str, str]]:
    rows = _read_csv(SOURCE_V1_CATALOG)
    seen: set[str] = set()
    for row in rows:
        exercise_id = row.get("exercise_id", "")
        if not exercise_id or exercise_id in seen:
            raise BuildError(f"V1 catalog exercise_id is blank or duplicated: {exercise_id}")
        if row.get("difficulty_code") not in ALLOWED_DIFFICULTIES:
            raise BuildError(f"V1 catalog difficulty is unresolved: {exercise_id}")
        if row.get("production_status") != "REVIEW_REQUIRED":
            raise BuildError(f"V1 catalog review status is unexpected: {exercise_id}")
        seen.add(exercise_id)
    return rows


def load_enrichment() -> dict[str, dict[str, str]]:
    rows = _read_csv(SOURCE_ENRICHMENT)
    by_nex: dict[str, dict[str, str]] = {}
    for row in rows:
        exercise_id = row.get("exercise_id", "")
        if not exercise_id or exercise_id in by_nex:
            raise BuildError(f"FITT enrichment ID is blank or duplicated: {exercise_id}")
        by_nex[exercise_id] = row
    return by_nex


def _nex_ids(source: dict[str, str]) -> list[str]:
    stable_code = source["stable_code"]
    try:
        nex_ids = json.loads(source["nex_exercise_ids"])
    except json.JSONDecodeError as exc:
        raise BuildError(f"catalog NEX IDs are invalid: {stable_code}") from exc
    if not isinstance(nex_ids, list) or not nex_ids:
        raise BuildError(f"catalog NEX IDs are missing: {stable_code}")
    if not all(isinstance(nex_id, str) and nex_id for nex_id in nex_ids):
        raise BuildError(f"catalog NEX IDs are invalid: {stable_code}")
    return nex_ids


def _catalog_enrichment(
    source: dict[str, str], by_nex: dict[str, dict[str, str]]
) -> dict[str, str]:
    stable_code = source["stable_code"]
    nex_ids = _nex_ids(source)
    candidates = [by_nex.get(str(nex_id)) for nex_id in nex_ids]
    if any(candidate is None for candidate in candidates):
        raise BuildError(f"FITT enrichment is missing for {stable_code}")
    first = candidates[0]
    assert first is not None
    candidate_template_ids = {
        candidate["fitt_template_id"] for candidate in candidates if candidate
    }
    for candidate in candidates[1:]:
        assert candidate is not None
        if candidate.get("fitt_template_id") != first.get("fitt_template_id"):
            if candidate_template_ids <= {
                "FITT-BODYWEIGHT-BEGINNER-V1",
                "FITT-ISOLATION-STRENGTH-V1",
            }:
                break
            raise BuildError(f"selected NEX FITT mappings conflict: {stable_code}")
    # The vNext catalog owns exercise difficulty.  The enrichment row is used
    # only for the reviewed movement/FITT mapping; its historical difficulty
    # snapshot is not copied or used as an override.
    return first


def choose_template(
    difficulty_code: str,
    experience_level_code: str,
    movement_pattern: str,
    training_category: str,
    *,
    exercise_exception_id: str | None = None,
    beginner_template_id: str | None = None,
) -> str:
    """Choose an experience-specific template without equating difficulty and experience."""
    if difficulty_code not in ALLOWED_DIFFICULTIES:
        raise BuildError(f"unsupported difficulty_code: {difficulty_code}")
    if experience_level_code not in ALLOWED_EXPERIENCES:
        raise BuildError(f"unsupported experience_level_code: {experience_level_code}")
    if experience_level_code == "BEGINNER" and difficulty_code != "BEGINNER":
        raise BuildError(
            f"BEGINNER profile is not eligible for {exercise_exception_id or movement_pattern}"
        )
    if experience_level_code == "INTERMEDIATE" and difficulty_code not in ALLOWED_DIFFICULTIES:
        raise BuildError(
            f"INTERMEDIATE profile source is invalid: {exercise_exception_id or movement_pattern}"
        )
    base_template_id = beginner_template_id
    if not base_template_id:
        category_prefix = {
            ("COMPOUND_STRENGTH", "SQUAT"): "FITT-COMPOUND-SQUAT-V1",
            ("COMPOUND_STRENGTH", "HINGE"): "FITT-COMPOUND-HINGE-V1",
            ("COMPOUND_STRENGTH", "PUSH"): "FITT-COMPOUND-PUSH-V1",
            ("COMPOUND_STRENGTH", "PULL"): "FITT-COMPOUND-PULL-V1",
            ("COMPOUND_STRENGTH", "LUNGE"): "FITT-COMPOUND-LUNGE-V1",
            ("ISOLATION_STRENGTH", "ISOLATION"): "FITT-ISOLATION-STRENGTH-V1",
            ("ISOMETRIC_STRENGTH", "PUSH"): "FITT-ISOMETRIC-STRENGTH-V1",
            ("POWER", "HINGE"): "FITT-HINGE-POWER-V1",
            ("CORE_DYNAMIC", "CORE"): "FITT-CORE-DYNAMIC-V1",
            ("CORE_ISOMETRIC", "CORE"): "FITT-CORE-ISOMETRIC-V1",
            ("MOBILITY", "MOBILITY"): "FITT-MOBILITY-V1",
            ("CARDIO", "CARDIO"): "FITT-CARDIO-V1",
        }
        base_template_id = category_prefix.get((training_category, movement_pattern))
    if not base_template_id:
        raise BuildError(f"no FITT template for {exercise_exception_id or movement_pattern}")
    return (
        base_template_id
        if experience_level_code == "BEGINNER"
        else base_template_id.replace("-V1", "-INTERMEDIATE-V1")
    )


def resolve_beginner_template_id(
    source: dict[str, str], mapping: dict[str, str], beginner_templates: dict[str, dict[str, str]]
) -> str:
    """Map retired v2.0.1 generic FITT IDs into the v2.0.2 draft library."""
    template_id = mapping["fitt_template_id"]
    if template_id in beginner_templates:
        return template_id
    if template_id == "FITT-CORE-STABILITY-V1":
        return (
            "FITT-CORE-DYNAMIC-PER-SIDE-V1"
            if set(_nex_ids(source)) & {"NEX-000030", "NEX-000063", "NEX-000179"}
            else "FITT-CORE-DYNAMIC-V1"
        )
    if template_id == "FITT-BODYWEIGHT-BEGINNER-V1":
        if source["primary_movement_pattern_code"] == "ISOLATION":
            return "FITT-ISOLATION-STRENGTH-V1"
        by_pattern = {
            "SQUAT": "FITT-COMPOUND-SQUAT-V1",
            "HINGE": "FITT-COMPOUND-HINGE-V1",
            "PUSH": "FITT-COMPOUND-PUSH-V1",
        }
        replacement = by_pattern.get(mapping["suggested_movement_pattern"])
        if replacement:
            return replacement
    if source["training_type_code"] == "MOBILITY":
        return "FITT-MOBILITY-V1"
    if source["training_type_code"] == "CARDIO":
        return "FITT-CARDIO-V1"
    return template_id


def materialize_catalog(
    source_rows: list[dict[str, str]],
    by_nex: dict[str, dict[str, str]],
    beginner_templates: dict[str, dict[str, str]],
    intermediate_templates: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    catalog_rows: list[dict[str, Any]] = []
    enrichment_rows: list[dict[str, Any]] = []
    for source in sorted(source_rows, key=lambda row: row["stable_code"]):
        stable_code = source["stable_code"]
        mapping = _catalog_enrichment(source, by_nex)
        base_template_id = resolve_beginner_template_id(source, mapping, beginner_templates)
        if base_template_id not in beginner_templates:
            raise BuildError(
                f"BEGINNER FITT template is not found: {stable_code}:{base_template_id}"
            )
        intermediate_template_id = choose_template(
            source["difficulty_code"],
            "INTERMEDIATE",
            mapping["suggested_movement_pattern"],
            beginner_templates[base_template_id]["training_category"],
            exercise_exception_id=stable_code,
            beginner_template_id=base_template_id,
        )
        if intermediate_template_id not in intermediate_templates:
            raise BuildError(
                f"INTERMEDIATE FITT template is not found: {stable_code}:{intermediate_template_id}"
            )
        allowed_experience = (
            ["BEGINNER", "INTERMEDIATE"]
            if source["difficulty_code"] == "BEGINNER"
            else ["INTERMEDIATE"]
        )
        template_ids = {
            "INTERMEDIATE": intermediate_template_id,
            **({"BEGINNER": base_template_id} if source["difficulty_code"] == "BEGINNER" else {}),
        }
        catalog_rows.append(
            {
                "catalog_version_code": CATALOG_VERSION,
                "stable_code": stable_code,
                "representative_exercise_id": source["representative_exercise_id"],
                "name_ko": source["name_ko"],
                "name_en": source["name_en"],
                "training_type_code": source["training_type_code"],
                "body_focus_code": source["body_focus_code"],
                "primary_movement_pattern_code": source["primary_movement_pattern_code"],
                "difficulty_code": source["difficulty_code"],
                "difficulty_status": source["difficulty_status"],
                "timing_mode_code": source["timing_mode_code"],
                "default_seconds_per_rep": int(source["default_seconds_per_rep"])
                if source["default_seconds_per_rep"]
                else None,
                "default_work_seconds": int(source["default_work_seconds"])
                if source["default_work_seconds"]
                else None,
                "default_rest_seconds": int(source["default_rest_seconds"]),
                "default_transition_seconds": int(source["default_transition_seconds"]),
                "equipment_codes": source["equipment_codes"].split("|"),
                "location_codes": source["location_codes"].split("|"),
                "primary_body_area_codes": _json_array(
                    source["primary_body_area_codes"], "primary_body_area_codes", stable_code
                ),
                "secondary_body_area_codes": _json_array(
                    source["secondary_body_area_codes"], "secondary_body_area_codes", stable_code
                ),
                "recovery_eligible": _bool(
                    source["recovery_eligible"], "recovery_eligible", stable_code
                ),
                "instruction_summary_ko": source["instruction_summary_ko"],
                "form_cues_ko": _json_array(source["form_cues_ko"], "form_cues_ko", stable_code),
                "instruction_content_version": source["instruction_content_version"],
                "review_status_code": source["review_status_code"],
                "source_track": source["source_track"],
                "source_identity": source["source_identity"],
                "production_eligible": False,
            }
        )
        enrichment_rows.append(
            {
                "catalog_version_code": CATALOG_VERSION,
                "exercise_stable_code": stable_code,
                "difficulty_code": source["difficulty_code"],
                "difficulty_status": source["difficulty_status"],
                "movement_pattern_code": mapping["suggested_movement_pattern"],
                "training_category": beginner_templates[base_template_id]["training_category"],
                "fitt_template_ids_by_experience": template_ids,
                "allowed_experience_level_codes": allowed_experience,
                "fitt_mapping_exception_code": mapping.get("fitt_mapping_exception_code", "NONE"),
                "fitt_mapping_note": mapping.get("fitt_mapping_note", ""),
                "mapping_source_exercise_id": mapping["exercise_id"],
                "v1_exercise_ids": _nex_ids(source),
            }
        )
    return catalog_rows, enrichment_rows


def materialize_v1_aliases(
    v1_rows: list[dict[str, str]],
    catalog_rows: list[dict[str, Any]],
    enrichment_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    catalog = {row["stable_code"]: row for row in catalog_rows}
    enrichment = {row["exercise_stable_code"]: row for row in enrichment_rows}
    stable_by_v1: dict[str, str] = {}
    for row in enrichment_rows:
        stable_code = row["exercise_stable_code"]
        for exercise_id in row["v1_exercise_ids"]:
            if exercise_id in stable_by_v1:
                raise BuildError(f"V1 exercise maps to multiple V2 exercises: {exercise_id}")
            stable_by_v1[exercise_id] = stable_code
    v1_by_id = {row["exercise_id"]: row for row in v1_rows}
    if set(v1_by_id) != set(stable_by_v1):
        raise BuildError("V1 catalog coverage does not match V2 representative mapping")
    aliases: list[dict[str, Any]] = []
    for exercise_id in sorted(v1_by_id):
        source = v1_by_id[exercise_id]
        stable_code = stable_by_v1[exercise_id]
        canonical = catalog[stable_code]
        mapping = enrichment[stable_code]
        aliases.append(
            {
                "catalog_version_code": CATALOG_VERSION,
                "source_catalog_version_code": V1_CATALOG_VERSION,
                "v1_exercise_id": exercise_id,
                "v1_exercise_name_ko": source["exercise_name_ko"],
                "v1_name_en": source["name_en"],
                "v1_source_name_en": source["source_name_en"],
                "v1_training_type_code": source["training_type_code"],
                "v1_body_focus_code": source["body_focus_code"],
                "v1_primary_body_area_codes": _json_array(
                    source["primary_body_area_codes"],
                    "v1_primary_body_area_codes",
                    exercise_id,
                ),
                "v1_secondary_body_area_codes": _json_array(
                    source["secondary_body_area_codes"],
                    "v1_secondary_body_area_codes",
                    exercise_id,
                ),
                "v1_target_body_area_codes": _json_array(
                    source["target_body_area_codes"],
                    "v1_target_body_area_codes",
                    exercise_id,
                ),
                "v1_timing_mode_code": source["timing_mode_code"],
                "v1_default_sets": source["default_sets"],
                "v1_default_reps": source["default_reps"],
                "v1_default_work_seconds": source["default_work_seconds"],
                "v1_default_rest_seconds": source["default_rest_seconds"],
                "v1_default_transition_seconds": source["default_transition_seconds"],
                "v1_intensity_level": source["intensity_level"],
                "exercise_stable_code": stable_code,
                "difficulty_code": canonical["difficulty_code"],
                "difficulty_status": canonical["difficulty_status"],
                "allowed_experience_level_codes": mapping["allowed_experience_level_codes"],
                "fitt_template_ids_by_experience": mapping["fitt_template_ids_by_experience"],
                "source_review_status_code": source["production_status"],
                "alias_only": True,
                "production_eligible": False,
            }
        )
    return aliases


def materialize_combined_exercise_records(
    catalog_rows: list[dict[str, Any]],
    enrichment_rows: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create a self-contained, review-required V1/V2 Data handoff file."""
    enrichment = {row["exercise_stable_code"]: row for row in enrichment_rows}
    exercises: list[dict[str, Any]] = []
    for catalog in catalog_rows:
        stable_code = catalog["stable_code"]
        mapping = enrichment.get(stable_code)
        if mapping is None:
            raise BuildError(f"combined exercise enrichment is missing: {stable_code}")
        exercises.append(
            {
                "record_type": "EXERCISE",
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
        )
    return exercises + [
        {
            "record_type": "V1_ALIAS",
            **row,
            "artifact_review_status_code": "REVIEW_REQUIRED",
            "review_required": True,
        }
        for row in aliases
    ]


def _profile_timing(
    template: dict[str, Any], stable_code: str
) -> tuple[int, int | None, int | None]:
    sets = _int_or_default(str(template.get("default_sets", "")), 1, "default_sets", stable_code)
    unit = str(template.get("prescription_unit", ""))
    if unit in {"REPS", "REPS_PER_SIDE"}:
        reps = _first_int(str(template.get("default_reps", "")), "default_reps", stable_code)
        return sets, reps, None
    if unit == "SECONDS":
        work = _first_int(
            str(template.get("default_work_seconds", "")), "default_work_seconds", stable_code
        )
        return sets, None, work
    raise BuildError(f"unsupported prescription unit: {stable_code}:{unit}")


def materialize_profiles(
    catalog_rows: list[dict[str, Any]],
    enrichment_rows: list[dict[str, Any]],
    beginner_templates: dict[str, dict[str, str]],
    intermediate_templates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enrichment = {row["exercise_stable_code"]: row for row in enrichment_rows}
    profiles: list[dict[str, Any]] = []
    for catalog in catalog_rows:
        stable_code = catalog["stable_code"]
        mapping = enrichment[stable_code]
        for experience in mapping["allowed_experience_level_codes"]:
            template_id = mapping["fitt_template_ids_by_experience"][experience]
            template = (
                beginner_templates[template_id]
                if experience == "BEGINNER"
                else intermediate_templates[template_id]
            )
            sets, reps, work = _profile_timing(template, stable_code)
            rest = _int_or_default(
                str(template.get("default_rest_seconds", "")),
                0,
                "default_rest_seconds",
                stable_code,
            )
            phases = (
                ("WARMUP", "COOLDOWN") if catalog["training_type_code"] == "MOBILITY" else ("MAIN",)
            )
            for phase in phases:
                profiles.append(
                    {
                        "catalog_version_code": CATALOG_VERSION,
                        "exercise_stable_code": stable_code,
                        "exercise_difficulty_code": catalog["difficulty_code"],
                        "goal_code": "GENERAL_FITNESS",
                        "experience_level_code": experience,
                        "phase_code": phase,
                        "sets": sets,
                        "reps": reps,
                        "work_seconds_per_set": work,
                        "rest_seconds_per_set": rest,
                        "intensity_code": template["default_intensity"],
                        "fitt_template_id": template_id,
                        "prescription_version": PRESCRIPTION_VERSION,
                        "review_status_code": TEMPLATE_STATUS_BEGINNER
                        if experience == "BEGINNER"
                        else "REVIEW_REQUIRED",
                        "production_eligible": False,
                    }
                )
    return sorted(
        profiles,
        key=lambda row: (
            row["exercise_stable_code"],
            row["experience_level_code"],
            row["phase_code"],
        ),
    )


def _deduplicate_alternatives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)):
        key = (
            str(row["source_exercise_stable_code"]),
            str(row["alternative_exercise_stable_code"]),
            str(row["reason_code"]),
            str(row["goal_preservation_code"]),
            str(row.get("condition_code") or ""),
        )
        previous = result.get(key)
        if previous is not None:
            comparable = (
                "difficulty_delta",
                "reason_code",
                "goal_preservation_code",
                "rule_version",
            )
            if any(previous.get(field) != row.get(field) for field in comparable):
                raise BuildError(f"conflicting duplicate alternative relation: {key}")
            continue
        result[key] = row
    return list(result.values())


def materialize_alternatives(
    rows: list[dict[str, Any]], catalog_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    catalog = {row["stable_code"]: row for row in catalog_rows}
    projected: list[dict[str, Any]] = []
    for row in rows:
        source = catalog.get(row["source_exercise_stable_code"])
        target = catalog.get(row["alternative_exercise_stable_code"])
        if source is None or target is None:
            raise BuildError("alternative endpoint is missing from the vNext catalog")
        difficulty_rank = {"BEGINNER": 0, "INTERMEDIATE": 1}
        target_rank = difficulty_rank[target["difficulty_code"]]
        source_rank = difficulty_rank[source["difficulty_code"]]
        delta = target_rank - source_rank
        if delta > 0:
            continue
        # A difficulty relation whose endpoints became equal after the
        # catalog review is no longer a difficulty alternative.
        if row["reason_code"] == "DIFFICULTY" and delta != -1:
            continue
        projected.append(
            {
                "alternative_catalog_version_code": CATALOG_VERSION,
                "alternative_exercise_stable_code": row["alternative_exercise_stable_code"],
                "alternative_set_version_code": ALTERNATIVE_VERSION,
                "created_at": row.get("created_at"),
                "difficulty_delta": delta,
                "goal_preservation_code": row["goal_preservation_code"],
                "production_eligible": False,
                "reason_code": row["reason_code"],
                "review_method_code": row.get("review_method_code", "DOMAIN_REVIEWER"),
                "review_status_code": row.get("review_status_code", "DOMAIN_APPROVED"),
                "rule_version": row["rule_version"],
                "source_catalog_version_code": CATALOG_VERSION,
                "source_exercise_stable_code": row["source_exercise_stable_code"],
                "source_manifest_hash": _sha256(SOURCE_ALTERNATIVES),
                "source_metadata": row.get("source_metadata", {}),
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "pain_discomfort_area_code": row.get("pain_discomfort_area_code"),
                "condition_code": row.get("condition_code"),
                "service_action_code": row.get("service_action_code"),
                "target_strategy_code": row.get("target_strategy_code"),
            }
        )
    return sorted(
        _deduplicate_alternatives(projected),
        key=lambda row: (
            row["source_exercise_stable_code"],
            row["alternative_exercise_stable_code"],
            row["reason_code"],
            row["goal_preservation_code"],
        ),
    )


def materialize_goal_links(
    rows: list[dict[str, Any]], catalog: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    source_by_code = {row["exercise_stable_code"]: row for row in rows}
    if set(source_by_code) != {row["stable_code"] for row in catalog}:
        raise BuildError("goal link source does not cover the new catalog")
    return [
        {
            "catalog_version_code": CATALOG_VERSION,
            "exercise_stable_code": stable_code,
            "goal_code": source_by_code[stable_code]["goal_code"],
            "role_eligibility_code": source_by_code[stable_code]["role_eligibility_code"],
            "review_status_code": source_by_code[stable_code].get(
                "review_status_code", "DOMAIN_APPROVED"
            ),
            "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        }
        for stable_code in sorted(source_by_code)
    ]


def materialize_safety(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_hash = _sha256(SOURCE_SAFETY)
    result: list[dict[str, Any]] = []
    for row in rows:
        projected = dict(row)
        projected["catalog_version_code"] = CATALOG_VERSION
        projected["source_manifest_hash"] = source_hash
        projected["production_eligible"] = False
        result.append(projected)
    return sorted(
        result,
        key=lambda row: (
            row["exercise_stable_code"],
            str(row.get("body_area_code")),
            str(row.get("minimum_severity_code")),
            str(row.get("maximum_severity_code")),
            str(row.get("effect_code")),
        ),
    )


def _file_entry(root: Path, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    records = (
        len([line for line in raw.decode("utf-8").splitlines() if line.strip()])
        if path.suffix == ".jsonl"
        else _csv_record_count(path)
        if path.suffix == ".csv"
        else 1
    )
    return {
        "path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "records": records,
    }


def _write_submanifest(root: Path, relative_path: str, files: list[Path], *, kind: str) -> None:
    manifest_path = root / relative_path
    entries = [_file_entry(root, path) for path in sorted(files)]
    _write_json(
        manifest_path,
        {
            "schema_version": "vnext-1.0",
            "kind": kind,
            "status_code": "DRAFT",
            "production_eligible": False,
            "catalog_version_code": CATALOG_VERSION,
            "prescription_set_version_code": PRESCRIPTION_VERSION,
            "alternative_set_version_code": ALTERNATIVE_VERSION,
            "files": entries,
        },
    )


def build(output: Path = DEFAULT_OUTPUT, *, force: bool = False) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        if not force:
            raise BuildError(
                f"output exists; use --force only for the new draft directory: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    beginner_templates, intermediate_templates, template_review = load_templates()
    source_rows, _ = load_catalog()
    v1_rows = load_v1_catalog()
    enrichment_by_nex = load_enrichment()
    catalog_rows, enrichment_rows = materialize_catalog(
        source_rows, enrichment_by_nex, beginner_templates, intermediate_templates
    )
    profiles = materialize_profiles(
        catalog_rows, enrichment_rows, beginner_templates, intermediate_templates
    )
    v1_aliases = materialize_v1_aliases(v1_rows, catalog_rows, enrichment_rows)
    combined_exercise_records = materialize_combined_exercise_records(
        catalog_rows, enrichment_rows, v1_aliases
    )
    alternatives = materialize_alternatives(_read_jsonl(SOURCE_ALTERNATIVES), catalog_rows)
    goals = materialize_goal_links(_read_jsonl(SOURCE_GOAL_LINKS), catalog_rows)
    safety = materialize_safety(_read_jsonl(SOURCE_SAFETY))

    payloads: dict[str, list[dict[str, Any]]] = {
        "catalog/exercises.jsonl": catalog_rows,
        "catalog/exercises_v1_v2.jsonl": combined_exercise_records,
        "catalog/catalog_enrichment.jsonl": enrichment_rows,
        "catalog/v1_exercise_aliases.jsonl": v1_aliases,
        "prescriptions/goal_tag_links.jsonl": goals,
        "prescriptions/prescription_profiles.jsonl": profiles,
        "alternatives/alternatives.jsonl": alternatives,
        "runtime/catalog.jsonl": catalog_rows,
        "runtime/exercises_v1_v2.jsonl": combined_exercise_records,
        "runtime/prescription_profiles.jsonl": profiles,
        "runtime/alternatives.jsonl": alternatives,
        "runtime/v1_exercise_aliases.jsonl": v1_aliases,
        "runtime/safety_rules.jsonl": safety,
        "backend_bundle/catalog/exercises.jsonl": catalog_rows,
        "backend_bundle/catalog/exercises_v1_v2.jsonl": combined_exercise_records,
        "backend_bundle/catalog/catalog_enrichment.jsonl": enrichment_rows,
        "backend_bundle/catalog/v1_exercise_aliases.jsonl": v1_aliases,
        "backend_bundle/prescriptions/goal_tag_links.jsonl": goals,
        "backend_bundle/prescriptions/prescription_profiles.jsonl": profiles,
        "backend_bundle/alternatives/alternatives.jsonl": alternatives,
        "backend_bundle/safety/safety_rules.jsonl": safety,
    }
    for relative, rows in payloads.items():
        _write_jsonl(output / relative, rows)
    csv_payloads = {
        "catalog/exercises_v1_v2.csv": combined_exercise_records,
        "runtime/exercises_v1_v2.csv": combined_exercise_records,
        "backend_bundle/catalog/exercises_v1_v2.csv": combined_exercise_records,
    }
    for relative, rows in csv_payloads.items():
        _write_csv(output / relative, rows)
    runtime_files = [output / relative for relative in payloads if relative.startswith("runtime/")]
    runtime_files.extend(
        output / relative for relative in csv_payloads if relative.startswith("runtime/")
    )
    bundle_files = [
        output / relative for relative in payloads if relative.startswith("backend_bundle/")
    ]
    bundle_files.extend(
        output / relative for relative in csv_payloads if relative.startswith("backend_bundle/")
    )
    _write_submanifest(output, "runtime/manifest.json", runtime_files, kind="runtime")
    _write_submanifest(output, "backend_bundle/manifest.json", bundle_files, kind="backend_bundle")
    all_files = (
        [output / relative for relative in payloads]
        + [output / relative for relative in csv_payloads]
        + [
            output / "runtime/manifest.json",
            output / "backend_bundle/manifest.json",
        ]
    )
    manifest = {
        "schema_version": "vnext-1.0",
        "generator_version": GENERATOR_VERSION,
        "catalog_version_code": CATALOG_VERSION,
        "prescription_set_version_code": PRESCRIPTION_VERSION,
        "alternative_set_version_code": ALTERNATIVE_VERSION,
        "status_code": "DRAFT",
        "production_eligible": False,
        "review": {
            "catalog_status_code": "DRAFT",
            "difficulty_review_status_code": "APPROVED",
            "difficulty_review_required_count": 0,
            "fitt_beginner_status_code": template_review["beginner_review_status_code"],
            "fitt_intermediate_status_code": template_review["intermediate_review_status_code"],
            "production_eligible": False,
        },
        "policy": {
            "candidate_matrix": {
                "BEGINNER": ["BEGINNER"],
                "INTERMEDIATE": ["BEGINNER", "INTERMEDIATE"],
                "INTERMEDIATE_DOWNSHIFT": ["BEGINNER"],
            },
            "fitt_selection": {
                "BEGINNER": "BEGINNER",
                "INTERMEDIATE": "INTERMEDIATE",
                "INTERMEDIATE_DOWNSHIFT": "BEGINNER",
            },
            "difficulty_experience_equality_required": False,
        },
        "summary": {
            "catalog_records": len(catalog_rows),
            "combined_exercise_records": len(combined_exercise_records),
            "difficulty_counts": {
                "BEGINNER": sum(row["difficulty_code"] == "BEGINNER" for row in catalog_rows),
                "INTERMEDIATE": sum(
                    row["difficulty_code"] == "INTERMEDIATE" for row in catalog_rows
                ),
            },
            "goal_tag_records": len(goals),
            "prescription_records": len(profiles),
            "alternative_records": len(alternatives),
            "safety_rule_records": len(safety),
            "v1_alias_records": len(v1_aliases),
        },
        "source": {
            "catalog": {"path": _repo_relative(SOURCE_CATALOG), "sha256": _sha256(SOURCE_CATALOG)},
            "v1_catalog": {
                "path": _repo_relative(SOURCE_V1_CATALOG),
                "sha256": _sha256(SOURCE_V1_CATALOG),
            },
            "catalog_enrichment": {
                "path": _repo_relative(SOURCE_ENRICHMENT),
                "sha256": _sha256(SOURCE_ENRICHMENT),
            },
            "beginner_fitt_template": {
                "path": _repo_relative(SOURCE_BEGINNER_TEMPLATE),
                "sha256": _sha256(SOURCE_BEGINNER_TEMPLATE),
            },
            "beginner_fitt_review": {
                "path": _repo_relative(SOURCE_BEGINNER_REVIEW),
                "sha256": _sha256(SOURCE_BEGINNER_REVIEW),
            },
            "intermediate_fitt_template": {
                "path": _repo_relative(SOURCE_INTERMEDIATE_TEMPLATE),
                "sha256": _sha256(SOURCE_INTERMEDIATE_TEMPLATE),
            },
            "alternatives": {
                "path": _repo_relative(SOURCE_ALTERNATIVES),
                "sha256": _sha256(SOURCE_ALTERNATIVES),
            },
            "goal_links": {
                "path": _repo_relative(SOURCE_GOAL_LINKS),
                "sha256": _sha256(SOURCE_GOAL_LINKS),
            },
            "safety": {"path": _repo_relative(SOURCE_SAFETY), "sha256": _sha256(SOURCE_SAFETY)},
        },
        "files": [_file_entry(output, path) for path in sorted(all_files)],
        "backend_follow_up": {
            "status_code": "REQUIRED",
            "import_compatibility": "BLOCKED_BY_CURRENT_BACKEND_SCHEMA",
            "notes": [
                "Remove difficulty/experience equality assumptions in backend validators "
                "and wording.",
                "Allow INTERMEDIATE prescription profiles and select by experience policy.",
                "Remove candidate lookup dependence on the historical suitability field.",
                "Import this Data-side vNext bundle into the database and rebuild Qdrant "
                "payload/index when approved.",
                "Import the v1_exercise_aliases projection so all existing V1 exercise IDs "
                "resolve to their V2 stable codes without duplicating exercise rows.",
                "Treat exercises_v1_v2.jsonl as a Data-side combined handoff; its V1_ALIAS "
                "records are not directly compatible with the current Backend exercise-row "
                "schema.",
                "Revalidate candidate selection, downshift, duration composition, and "
                "Safety runtime behavior.",
            ],
        },
    }
    _write_json(output / "manifest.json", manifest)
    report = validate_directory(output)
    report["template_review"] = template_review
    report["source_difficulty_review_required_count"] = 0
    report["v1_alias_records"] = len(v1_aliases)
    report["combined_exercise_records"] = len(combined_exercise_records)
    _write_json(output / "validation_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(args.output, force=args.force), ensure_ascii=False, sort_keys=True))
    except (BuildError, ArtifactValidationError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
