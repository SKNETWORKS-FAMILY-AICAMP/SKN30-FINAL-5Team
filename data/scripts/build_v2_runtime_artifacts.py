#!/usr/bin/env python3
"""Materialize reviewed V2 catalog rows into validated JSONL artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.modules.catalog.schemas import (  # noqa: E402
    AlternativeManifest,
    CatalogManifest,
    ExerciseAlternativeRecord,
    ExerciseRecord,
    ExerciseSafetyRuleRecord,
    ManifestFile,
    SafetyRuleManifest,
)

DATA_ROOT = PROJECT_ROOT / "data"
FINAL_DIR = DATA_ROOT / "generated" / "exercise-catalog-v2.0.0-final"
DEFAULT_OUTPUT_DIR = FINAL_DIR / "runtime"
DECISIONS_PATH = DATA_ROOT / "normalized" / "v2_representative_decisions.json"
ALTERNATIVES_PATH = FINAL_DIR / "exercise_alternatives_v2_final.csv"
SAFETY_MAPPING_PATH = (
    DATA_ROOT
    / "generated"
    / "exercise-catalog-v2.0.0-final"
    / "representative_exercise_safety_mapping_v2_final.csv"
)
REPRESENTATIVES_PATH = FINAL_DIR / "representative_exercises_v2_final.csv"
TAXONOMY_REGISTRY_PATH = DATA_ROOT / "normalized" / "exercise_taxonomy_codes.json"
GENERATED_AT = datetime.fromisoformat("2026-08-24T00:00:00+09:00")


class RuntimeArtifactError(ValueError):
    """Raised when a reviewed runtime artifact cannot be materialized safely."""


class V2BodyFocusCode(StrEnum):
    """V2 reviewed body-focus values; backend projection is a separate packaging step."""

    CHEST = "CHEST"
    BACK = "BACK"
    SHOULDERS = "SHOULDERS"
    BICEPS = "BICEPS"
    TRICEPS = "TRICEPS"
    FOREARMS = "FOREARMS"
    GLUTES = "GLUTES"
    QUADRICEPS = "QUADRICEPS"
    HAMSTRINGS = "HAMSTRINGS"
    CALVES = "CALVES"
    CORE = "CORE"
    FULL_BODY = "FULL_BODY"
    CARDIO = "CARDIO"
    MOBILITY = "MOBILITY"


class V2ReviewMethodCode(StrEnum):
    DOMAIN_REVIEWER = "DOMAIN_REVIEWER"


class V2ExerciseRecord(ExerciseRecord):
    body_focus_code: V2BodyFocusCode  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_training_focus_pair(self) -> V2ExerciseRecord:
        expected_focus = {
            "CARDIO": V2BodyFocusCode.CARDIO,
            "MOBILITY": V2BodyFocusCode.MOBILITY,
        }.get(str(self.training_type_code))
        if expected_focus is not None and self.body_focus_code is not expected_focus:
            raise RuntimeArtifactError(
                "CARDIO and MOBILITY records must use their matching body_focus_code"
            )
        if str(self.training_type_code) == "STRENGTH" and self.body_focus_code in {
            V2BodyFocusCode.CARDIO,
            V2BodyFocusCode.MOBILITY,
        }:
            raise RuntimeArtifactError(
                "STRENGTH records cannot use CARDIO or MOBILITY body_focus_code"
            )
        return self


class V2ExerciseAlternativeRecord(ExerciseAlternativeRecord):
    review_method_code: V2ReviewMethodCode  # type: ignore[assignment]
    alternative_set_version_code: str
    production_eligible: bool
    source_manifest_hash: str
    source_metadata: dict[str, Any]


class V2ExerciseSafetyRuleRecord(ExerciseSafetyRuleRecord):
    rule_set_version_code: str
    production_eligible: bool
    source_manifest_hash: str
    source_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


V2ExerciseRecord.model_rebuild(_types_namespace={"V2BodyFocusCode": V2BodyFocusCode})
V2ExerciseAlternativeRecord.model_rebuild(
    _types_namespace={"Any": Any, "V2ReviewMethodCode": V2ReviewMethodCode}
)
V2ExerciseSafetyRuleRecord.model_rebuild(_types_namespace={"Any": Any, "datetime": datetime})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeArtifactError(f"CSV header missing: {path}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def read_decisions() -> dict[str, Any]:
    try:
        decisions = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeArtifactError("V2 decisions file is missing or invalid") from error
    domain_review = decisions.get("domain_review", {})
    if domain_review.get("status") != "DOMAIN_APPROVED":
        raise RuntimeArtifactError(
            "domain review approval is required before runtime materialization"
        )
    return decisions


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_json_list(value: str, field: str, key: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise RuntimeArtifactError(f"{field} is not JSON: {key}") from error
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise RuntimeArtifactError(f"{field} must be a string array: {key}")
    return parsed


def split_codes(value: str, field: str, key: str) -> list[str]:
    values = [item for item in value.split("|") if item]
    if not values:
        raise RuntimeArtifactError(f"{field} is empty: {key}")
    return values


def boolean_value(value: str, field: str, key: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeArtifactError(f"{field} is not a materialized bool: {key}")


def int_value(value: str, field: str, key: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeArtifactError(f"{field} is not an integer: {key}") from error
    return parsed


def representative_records(rows: list[dict[str, str]]) -> list[V2ExerciseRecord]:
    records: list[V2ExerciseRecord] = []
    for row in rows:
        key = row["representative_exercise_id"]
        timing_mode = row["timing_mode_code"]
        record = V2ExerciseRecord.model_validate(
            {
                "stable_code": row["stable_code"],
                "name_ko": row["name_ko"],
                "name_en": row["name_en"],
                "training_type_code": row["training_type_code"],
                "body_focus_code": row["body_focus_code"],
                "primary_movement_pattern_code": row["primary_movement_pattern_code"],
                "difficulty_code": row["difficulty_code"],
                "beginner_suitable": boolean_value(
                    row["beginner_suitable"], "beginner_suitable", key
                ),
                "timing_mode_code": timing_mode,
                "default_seconds_per_rep": (
                    int_value(row["default_seconds_per_rep"], "default_seconds_per_rep", key)
                    if timing_mode == "REPS"
                    else None
                ),
                "default_work_seconds": (
                    int_value(row["default_work_seconds"], "default_work_seconds", key)
                    if timing_mode == "DURATION"
                    else None
                ),
                "default_rest_seconds": int_value(
                    row["default_rest_seconds"], "default_rest_seconds", key
                ),
                "default_transition_seconds": int_value(
                    row["default_transition_seconds"], "default_transition_seconds", key
                ),
                "recovery_eligible": boolean_value(
                    row["recovery_eligible"], "recovery_eligible", key
                ),
                "primary_body_area_codes": parse_json_list(
                    row["primary_body_area_codes"], "primary_body_area_codes", key
                ),
                "secondary_body_area_codes": parse_json_list(
                    row["secondary_body_area_codes"], "secondary_body_area_codes", key
                ),
                "equipment_codes": split_codes(row["equipment_codes"], "equipment_codes", key),
                "location_codes": split_codes(row["location_codes"], "location_codes", key),
                "instruction_summary_ko": row["instruction_summary_ko"],
                "form_cues_ko": parse_json_list(row["form_cues_ko"], "form_cues_ko", key),
                "instruction_content_version": row["instruction_content_version"],
                "review_status_code": row["review_status_code"],
                "source_track": row["source_track"],
                "source_identity": row["source_identity"],
            }
        )
        records.append(record)
    if len(records) != 102 or len({record.stable_code for record in records}) != len(records):
        raise RuntimeArtifactError("representative records must contain 102 unique stable codes")
    return records


def stable_code_index(records: list[ExerciseRecord]) -> dict[str, str]:
    output: dict[str, str] = {}
    for record in records:
        output[record.stable_code] = record.stable_code
    return output


def materialize_alternatives(
    records: list[V2ExerciseRecord], decisions: dict[str, Any]
) -> list[V2ExerciseAlternativeRecord]:
    source_rows = read_csv(ALTERNATIVES_PATH)
    policy = decisions["alternative_materialization"]
    stable_codes = {record.stable_code for record in records}
    seen: dict[tuple[str, str, str, str], dict[str, str]] = {}
    result: list[V2ExerciseAlternativeRecord] = []
    source_hash = sha256(ALTERNATIVES_PATH)
    for source in source_rows:
        source_stable = source["source_exercise_stable_code"]
        alternative_stable = source["alternative_exercise_stable_code"]
        if source_stable not in stable_codes or alternative_stable not in stable_codes:
            raise RuntimeArtifactError(
                "alternative endpoint is not in stable registry: "
                f"{source_stable}:{alternative_stable}"
            )
        if source_stable == alternative_stable:
            raise RuntimeArtifactError(f"alternative relation self-targets: {source_stable}")
        if source["direction_code"] != "A_TO_B":
            raise RuntimeArtifactError("alternative relation direction must be A_TO_B")
        if source["production_eligible"] != "false":
            raise RuntimeArtifactError("alternative relation must remain production-ineligible")
        if source["review_status_code"] != decisions["domain_review"]["status"]:
            raise RuntimeArtifactError("alternative relation review status is inconsistent")
        try:
            difficulty_delta = int(source["difficulty_delta"])
        except ValueError as error:
            raise RuntimeArtifactError("alternative difficulty_delta is not an integer") from error
        if difficulty_delta not in {-1, 0}:
            raise RuntimeArtifactError("alternative difficulty_delta must be -1 or 0")
        key = (
            source_stable,
            alternative_stable,
            source["reason_code"],
            source["goal_preservation_code"],
        )
        if key in seen:
            previous = seen[key]
            projection_fields = (
                "difficulty_delta",
                "rule_version",
                "alternative_set_version_code",
                "review_status_code",
                "direction_code",
                "production_eligible",
            )
            if any(previous[field] != source[field] for field in projection_fields):
                raise RuntimeArtifactError(
                    f"duplicate alternative relation has conflicting runtime fields: {key}"
                )
            continue
        seen[key] = source
        record = V2ExerciseAlternativeRecord.model_validate(
            {
                "alternative_catalog_version_code": "exercise-catalog-v2.0.0-final",
                "alternative_exercise_stable_code": alternative_stable,
                "created_at": GENERATED_AT,
                "difficulty_delta": difficulty_delta,
                "goal_preservation_code": source["goal_preservation_code"],
                "reason_code": source["reason_code"],
                "review_method_code": decisions["domain_review"]["review_method_code"],
                "review_status_code": decisions["domain_review"]["status"],
                "rule_version": policy["rule_version"],
                "alternative_set_version_code": source["alternative_set_version_code"],
                "production_eligible": False,
                "source_manifest_hash": source_hash,
                "source_metadata": {
                    **json.loads(source["source_metadata"]),
                    "source_relation_key": source["source_relation_key"],
                    "materialization_version": decisions["decision_version"],
                },
                "source_catalog_version_code": "exercise-catalog-v2.0.0-final",
                "source_exercise_stable_code": source_stable,
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            }
        )
        result.append(record)
    if not result:
        raise RuntimeArtifactError("no alternatives were materialized")
    return result


def materialize_safety(
    records: list[V2ExerciseRecord], decisions: dict[str, Any]
) -> list[V2ExerciseSafetyRuleRecord]:
    policy = decisions["safety_materialization"]
    source_hash = sha256(SAFETY_MAPPING_PATH)
    result: list[V2ExerciseSafetyRuleRecord] = []
    for exercise in records:
        areas = [(area, "PRIMARY") for area in exercise.primary_body_area_codes]
        areas.extend((area, "SECONDARY") for area in exercise.secondary_body_area_codes)
        for area, role in areas:
            specs = (
                [("MILD", "SEVERE", "EXCLUDE", "DIRECT_JOINT_LOAD")]
                if role == "PRIMARY"
                else [
                    ("MILD", "MILD", "CAUTION", "STABILIZER_LOAD"),
                    ("MODERATE", "SEVERE", "EXCLUDE", "STABILIZER_LOAD"),
                ]
            )
            for minimum, maximum, effect, reason in specs:
                result.append(
                    V2ExerciseSafetyRuleRecord.model_validate(
                        {
                            "body_area_code": area,
                            "body_part_role_code": role,
                            "catalog_version_code": "exercise-catalog-v2.0.0-final",
                            "effect_code": effect,
                            "exercise_stable_code": exercise.stable_code,
                            "maximum_severity_code": maximum,
                            "minimum_severity_code": minimum,
                            "movement_pattern_code": None,
                            "reason_code": reason,
                            "review_status_code": decisions["domain_review"]["status"],
                            "rule_scope": "EXERCISE",
                            "rule_version": policy["rule_version"],
                            "rule_set_version_code": policy["rule_set_version_code"],
                            "production_eligible": False,
                            "source_manifest_hash": source_hash,
                            "source_metadata": {
                                "source_path": str(SAFETY_MAPPING_PATH.relative_to(DATA_ROOT)),
                                "materialization_version": decisions["decision_version"],
                            },
                            "created_at": GENERATED_AT,
                            "updated_at": GENERATED_AT,
                        }
                    )
                )
    return result


def write_jsonl(path: Path, records: list[Any]) -> tuple[str, int, int]:
    text = "".join(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(text.encode("utf-8")), len(records)


def write_manifest(path: Path, manifest: Any) -> None:
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def build(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    decisions = read_decisions()
    representatives = representative_records(read_csv(REPRESENTATIVES_PATH))
    alternatives = materialize_alternatives(representatives, decisions)
    safety_rules = materialize_safety(representatives, decisions)
    output_dir.mkdir(parents=True, exist_ok=True)
    representative_hash, representative_bytes, representative_count = write_jsonl(
        output_dir / "representative_exercises.jsonl", representatives
    )
    alternative_hash, alternative_bytes, alternative_count = write_jsonl(
        output_dir / "alternatives.jsonl", alternatives
    )
    safety_hash, safety_bytes, safety_count = write_jsonl(
        output_dir / "safety_rules.jsonl", safety_rules
    )
    common_review = {
        "status": decisions["domain_review"]["status"],
        "review_method_code": "AGENT_ONLY",
        "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        "production_eligible": False,
    }
    source = {
        "track": "merged",
        "review_batch_directory": "data/reports",
        "taxonomy_registry_sha256": sha256(TAXONOMY_REGISTRY_PATH),
        "input_artifacts": [
            {
                "role": "representative_csv",
                "path": str(REPRESENTATIVES_PATH.relative_to(DATA_ROOT)),
                "sha256": sha256(REPRESENTATIVES_PATH),
                "bytes": REPRESENTATIVES_PATH.stat().st_size,
            }
        ],
    }
    catalog_manifest = CatalogManifest.model_validate(
        {
            "schema_version": "1.0",
            "generator_version": "v2-runtime-materializer-1.0.0",
            "catalog_version": {
                "version_code": "exercise-catalog-v2.0.0-final",
                "status_code": "DRAFT",
            },
            "source": source,
            "review": common_review,
            "summary": {"exercise_records": representative_count},
            "files": [
                ManifestFile(
                    path="representative_exercises.jsonl",
                    sha256=representative_hash,
                    bytes=representative_bytes,
                    records=representative_count,
                )
            ],
        }
    )
    alternative_manifest = AlternativeManifest.model_validate(
        {
            "schema_version": "1.0",
            "generator_version": "v2-runtime-materializer-1.0.0",
            "source": source,
            "review": common_review,
            "summary": {"alternative_records": alternative_count},
            "files": [
                ManifestFile(
                    path="alternatives.jsonl",
                    sha256=alternative_hash,
                    bytes=alternative_bytes,
                    records=alternative_count,
                )
            ],
            "alternative_set_version": {
                "version_code": "alternative-set-v2.0.0",
                "status_code": "DRAFT",
            },
        }
    )
    safety_manifest = SafetyRuleManifest.model_validate(
        {
            "schema_version": "1.0",
            "generator_version": "v2-runtime-materializer-1.0.0",
            "source": source,
            "review": common_review,
            "summary": {"rule_records": safety_count},
            "files": [
                ManifestFile(
                    path="safety_rules.jsonl",
                    sha256=safety_hash,
                    bytes=safety_bytes,
                    records=safety_count,
                )
            ],
            "rule_set_version": {
                "version_code": "safety-rule-set-v2.0.0",
                "status_code": "DRAFT",
            },
        }
    )
    write_manifest(output_dir / "catalog_manifest.json", catalog_manifest)
    write_manifest(output_dir / "alternatives_manifest.json", alternative_manifest)
    write_manifest(output_dir / "safety_manifest.json", safety_manifest)
    return {
        "representative_records": representative_count,
        "alternative_records": alternative_count,
        "safety_rule_records": safety_count,
        "production_eligible": False,
        "files": [
            "representative_exercises.jsonl",
            "alternatives.jsonl",
            "safety_rules.jsonl",
            "catalog_manifest.json",
            "alternatives_manifest.json",
            "safety_manifest.json",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output_dir), ensure_ascii=False, sort_keys=True))
    except (OSError, KeyError, RuntimeArtifactError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
