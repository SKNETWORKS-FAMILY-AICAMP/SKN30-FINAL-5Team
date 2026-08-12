"""Normalize verified public-health guidance into production-ineligible reference data."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from collect_physical_activity_guidelines import load_jsonl, verify_manifest
from kspo_fitness100_pipeline import PipelineError, sha256_bytes

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = DATA_ROOT / "raw" / "physical_activity_guidelines"
DEFAULT_OUTPUT_DIR = DATA_ROOT / "normalized" / "physical_activity_reference_v0.1.0"
OUTPUT_NAMES = (
    "intensity_reference.json",
    "adult_weekly_fitt_reference.json",
    "adult_compendium_reference_subset.json",
)
COMMON_GUARDS = [
    "PUBLIC_HEALTH_REFERENCE_IS_NOT_INDIVIDUAL_PRESCRIPTION",
    "REFERENCE_MUST_NOT_OVERRIDE_SAFETY_VETO",
    "SCHEMA_TARGET_UNRESOLVED",
    "NO_AUTOMATIC_EXERCISE_MET_MAPPING",
    "NO_DIAGNOSIS_TREATMENT_OR_REHABILITATION_INFERENCE",
]


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"JSON is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"JSON root must be an object: {path}")
    return value


def common_payload(reference_type: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "reference_version": "0.1.0",
        "reference_type": reference_type,
        "status": "DRAFT",
        "review_method_code": "AGENT_ONLY",
        "production_eligible": False,
        "population_code": "GENERAL_ADULT",
        "interpretation_guards": list(COMMON_GUARDS),
    }


def facts_by_id(raw_dir: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(raw_dir / "general_guideline_facts.json")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise PipelineError("raw guideline facts are missing")
    result: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if not isinstance(fact, dict):
            raise PipelineError("raw guideline fact must be an object")
        fact_id = str(fact.get("fact_id", ""))
        if not fact_id or fact_id in result:
            raise PipelineError(f"raw guideline fact ID is invalid or duplicated: {fact_id}")
        result[fact_id] = fact
    return result


def require_fact(facts: dict[str, dict[str, Any]], fact_id: str) -> dict[str, Any]:
    try:
        return facts[fact_id]
    except KeyError as exc:
        raise PipelineError(f"required raw guideline fact is missing: {fact_id}") from exc


def build_intensity_reference(facts: dict[str, dict[str, Any]]) -> dict[str, object]:
    moderate = require_fact(facts, "CDC_ABSOLUTE_MODERATE_MET_RANGE")
    vigorous = require_fact(facts, "CDC_ABSOLUTE_VIGOROUS_MET_MINIMUM")
    relative_moderate = require_fact(facts, "CDC_RELATIVE_MODERATE_EFFORT_RANGE")
    relative_vigorous = require_fact(facts, "CDC_RELATIVE_VIGOROUS_EFFORT_START")
    if (
        moderate.get("minimum") != 3.0
        or moderate.get("maximum") != 5.9
        or vigorous.get("minimum") != 6.0
        or vigorous.get("maximum") is not None
    ):
        raise PipelineError("absolute intensity source boundaries changed unexpectedly")
    if relative_moderate.get("minimum") != 5 or relative_moderate.get("maximum") != 6:
        raise PipelineError("relative moderate intensity source boundaries changed")
    if relative_vigorous.get("minimum") != 7 or relative_vigorous.get("maximum") != 8:
        raise PipelineError("relative vigorous onset source boundaries changed")

    payload = common_payload("INTENSITY_CLASSIFICATION_REFERENCE")
    payload["absolute_met_rules"] = [
        {
            "reference_code": "BELOW_MODERATE_MET",
            "minimum": None,
            "maximum": 3.0,
            "minimum_inclusive": False,
            "maximum_inclusive": False,
            "derivation_code": "COMPLEMENT_BELOW_CDC_MODERATE_THRESHOLD",
            "usage_note": "Reference bucket only; this does not create an application LIGHT code.",
            "source_fact_ids": [moderate["fact_id"]],
        },
        {
            "reference_code": "MODERATE_MET",
            "minimum": 3.0,
            "maximum": 5.9,
            "minimum_inclusive": True,
            "maximum_inclusive": True,
            "derivation_code": "DIRECT_SOURCE_RANGE",
            "source_fact_ids": [moderate["fact_id"]],
        },
        {
            "reference_code": "VIGOROUS_MET",
            "minimum": 6.0,
            "maximum": None,
            "minimum_inclusive": True,
            "maximum_inclusive": False,
            "derivation_code": "DIRECT_SOURCE_RANGE",
            "source_fact_ids": [vigorous["fact_id"]],
        },
    ]
    payload["relative_effort_references"] = [
        {
            "reference_code": "MODERATE_EFFORT_0_10",
            "minimum": 5,
            "maximum": 6,
            "classification_mode_code": "RANGE",
            "source_fact_ids": [relative_moderate["fact_id"]],
        },
        {
            "reference_code": "VIGOROUS_EFFORT_ONSET_0_10",
            "minimum": 7,
            "maximum": 8,
            "classification_mode_code": "ONSET_REFERENCE_NOT_COMPLETE_RANGE",
            "source_fact_ids": [relative_vigorous["fact_id"]],
        },
    ]
    payload["source_ids"] = ["CDC_PA_INTENSITY_2025"]
    return payload


def build_fitt_reference(facts: dict[str, dict[str, Any]]) -> dict[str, object]:
    intensity_fact_ids = {
        "CDC_ABSOLUTE_MODERATE_MET_RANGE",
        "CDC_ABSOLUTE_VIGOROUS_MET_MINIMUM",
        "CDC_RELATIVE_MODERATE_EFFORT_RANGE",
        "CDC_RELATIVE_VIGOROUS_EFFORT_START",
    }
    assertions = [fact for fact_id, fact in facts.items() if fact_id not in intensity_fact_ids]
    assertions.sort(key=lambda fact: str(fact["fact_id"]))
    if len(assertions) != 10:
        raise PipelineError("adult weekly FITT source assertion count changed")

    expected_values = {
        "CDC_ADULT_AEROBIC_MINIMUM_MODERATE": (150, None),
        "CDC_ADULT_AEROBIC_MINIMUM_VIGOROUS": (75, None),
        "KDCA_ADULT_AEROBIC_MODERATE_RANGE": (150, 300),
        "KDCA_ADULT_AEROBIC_VIGOROUS_RANGE": (75, 150),
        "WHO_ADULT_AEROBIC_MODERATE_RANGE": (150, 300),
        "WHO_ADULT_AEROBIC_VIGOROUS_RANGE": (75, 150),
    }
    for fact_id, (minimum, maximum) in expected_values.items():
        fact = require_fact(facts, fact_id)
        if (
            fact.get("minimum_minutes_per_week") != minimum
            or fact.get("maximum_minutes_per_week") != maximum
        ):
            raise PipelineError(f"adult weekly aerobic source value changed: {fact_id}")
    for fact_id in (
        "CDC_ADULT_STRENGTH_MINIMUM_DAYS",
        "KDCA_ADULT_STRENGTH_MINIMUM_DAYS",
        "WHO_ADULT_STRENGTH_MINIMUM_DAYS",
    ):
        if require_fact(facts, fact_id).get("minimum_days_per_week") != 2:
            raise PipelineError(f"adult weekly strength source value changed: {fact_id}")

    payload = common_payload("ADULT_WEEKLY_FITT_REFERENCE")
    payload["source_assertions"] = assertions
    payload["reference_envelope"] = {
        "aerobic": {
            "moderate_minutes_per_week": {"minimum": 150, "maximum": 300},
            "vigorous_minutes_per_week": {"minimum": 75, "maximum": 150},
            "vigorous_to_moderate_minute_equivalence": {"vigorous": 1, "moderate": 2},
        },
        "strength": {"minimum_days_per_week": 2},
        "derivation_code": "WHO_KDCA_RANGE_WITH_CDC_MINIMUM_CORROBORATION",
        "application_status": "REFERENCE_ONLY_SCHEMA_UNRESOLVED",
        "source_fact_ids": sorted(fact["fact_id"] for fact in assertions),
    }
    payload["source_ids"] = sorted({str(fact["source_id"]) for fact in assertions})
    return payload


def met_reference_code(value: float) -> str:
    if value < 3.0:
        return "BELOW_MODERATE_MET"
    if value <= 5.9:
        return "MODERATE_MET"
    return "VIGOROUS_MET"


def build_compendium_reference(raw_dir: Path) -> dict[str, object]:
    rows = load_jsonl(raw_dir / "adult_compendium_mvp_reference_subset.jsonl")
    activities: list[dict[str, object]] = []
    for row in rows:
        met_value = row.get("met_value")
        if not isinstance(met_value, int | float):
            raise PipelineError("Compendium MET value is not numeric")
        if "normalized_exercise_id" in row:
            raise PipelineError("Compendium activity must not be mapped to an exercise")
        activities.append(
            {
                "activity_code": row["activity_code"],
                "major_heading": row["major_heading"],
                "activity_description": row["activity_description"],
                "met_value": met_value,
                "absolute_intensity_reference_code": met_reference_code(float(met_value)),
                "source_id": row["source_id"],
                "source_locator": row["source_locator"],
                "review_status": "DRAFT",
                "production_eligible": False,
            }
        )
    payload = common_payload("ADULT_COMPENDIUM_MVP_RELEVANT_SUBSET")
    payload["coverage_code"] = "MVP_RELEVANT_REFERENCE_SUBSET_NOT_FULL_COMPENDIUM"
    payload["met_value_policy"] = "PRESERVE_OFFICIAL_VALUE_EXACTLY"
    payload["source_ids"] = ["ADULT_COMPENDIUM_PDF_2024", "CDC_PA_INTENSITY_2025"]
    payload["activities"] = activities
    return payload


def expected_outputs(raw_dir: Path) -> dict[str, dict[str, object]]:
    verify_manifest(raw_dir, raw_dir / "snapshot_manifest.json")
    facts = facts_by_id(raw_dir)
    return {
        "intensity_reference.json": build_intensity_reference(facts),
        "adult_weekly_fitt_reference.json": build_fitt_reference(facts),
        "adult_compendium_reference_subset.json": build_compendium_reference(raw_dir),
    }


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_outputs(raw_dir: Path, output_dir: Path) -> dict[str, object]:
    outputs = expected_outputs(raw_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in outputs.items():
        write_json(output_dir / name, payload)
    files = []
    for name in OUTPUT_NAMES:
        path = output_dir / name
        raw = path.read_bytes()
        files.append({"path": name, "sha256": sha256_bytes(raw), "bytes": len(raw)})
    raw_manifest = raw_dir / "snapshot_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "reference_version": "0.1.0",
        "status": "DRAFT",
        "review_method_code": "AGENT_ONLY",
        "production_eligible": False,
        "source_snapshot_manifest": {
            "path": raw_manifest.relative_to(DATA_ROOT).as_posix(),
            "sha256": sha256_bytes(raw_manifest.read_bytes()),
        },
        "files": files,
    }
    write_json(output_dir / "reference_manifest.json", manifest)
    return verify_outputs(raw_dir, output_dir)


def verify_outputs(raw_dir: Path, output_dir: Path) -> dict[str, object]:
    expected = expected_outputs(raw_dir)
    for name, payload in expected.items():
        if load_json(output_dir / name) != payload:
            raise PipelineError(f"normalized reference does not match verified inputs: {name}")
    manifest = load_json(output_dir / "reference_manifest.json")
    if (
        manifest.get("status") != "DRAFT"
        or manifest.get("review_method_code") != "AGENT_ONLY"
        or manifest.get("production_eligible") is not False
    ):
        raise PipelineError("normalized reference manifest state is invalid")
    raw_manifest = raw_dir / "snapshot_manifest.json"
    source = manifest.get("source_snapshot_manifest")
    if not isinstance(source, dict) or source.get("sha256") != sha256_bytes(
        raw_manifest.read_bytes()
    ):
        raise PipelineError("normalized reference source manifest hash does not match")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(OUTPUT_NAMES):
        raise PipelineError("normalized reference manifest file list is invalid")
    for entry in files:
        if not isinstance(entry, dict) or entry.get("path") not in OUTPUT_NAMES:
            raise PipelineError("normalized reference manifest file entry is invalid")
        path = output_dir / str(entry["path"])
        raw = path.read_bytes()
        if (
            entry.get("sha256") != sha256_bytes(raw)
            or entry.get("bytes") != len(raw)
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))
        ):
            raise PipelineError(f"normalized reference file hash mismatch: {path.name}")
    activities = expected["adult_compendium_reference_subset.json"]["activities"]
    if not isinstance(activities, list):
        raise PipelineError("normalized Compendium activities are invalid")
    return {
        "status": "valid",
        "intensity_rule_count": 5,
        "fitt_assertion_count": 10,
        "compendium_activity_count": len(activities),
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    build.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    verify.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        result = (
            build_outputs(args.raw_dir, args.output_dir)
            if args.command == "build"
            else verify_outputs(args.raw_dir, args.output_dir)
        )
    except (PipelineError, OSError, ValueError, AssertionError, KeyError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
