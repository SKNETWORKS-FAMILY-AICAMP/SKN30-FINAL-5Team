"""Build verified incremental catalog seeds from tranche 3 review results."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from build_exercise_catalog_seed import (
    ATTRIBUTE_FIELDS,
    attribute_problems,
    load_taxonomy_registry,
    verify_seed,
)
from build_exercise_safety_rules import (
    check_pattern_rules_hold,
    load_seed_exercises,
)
from build_exercise_safety_rules import (
    load_policy as load_safety_policy,
)
from korean_display_name_rules import duplicate_display_names
from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from review_tranche_3_candidates import DEFAULT_OUTPUT, DEFAULT_PLAN, verify_results

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = DATA_ROOT / "generated"
TAXONOMY = DATA_ROOT / "normalized" / "exercise_taxonomy_codes.json"
SAFETY_POLICY = DATA_ROOT / "normalized" / "exercise_safety_rule_policy.json"
EXISTING_SEEDS = (
    DATA_ROOT / "generated" / "exercise-catalog-seed-kspo-mvp-v0.2.0",
    DATA_ROOT / "generated" / "exercise-catalog-seed-wger-mvp-v0.2.0",
)
VERSION_CODES = {
    "kspo": "kspo-tranche3-v0.1.0",
    "wger": "wger-tranche3-v0.1.0",
}
GENERATOR_VERSION = "0.1.0"


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


def joined(values: object) -> str:
    if not isinstance(values, list):
        raise PipelineError("catalog list attribute is invalid")
    return " | ".join(str(value) for value in values)


def attribute_row(record: dict[str, Any]) -> dict[str, str]:
    spec = record.get("attributes")
    if not isinstance(spec, dict):
        raise PipelineError("included review record has no attributes")
    timing = str(spec.get("timing_mode_code", ""))
    row: dict[str, str] = {
        "source_identity": str(record.get("source_identity", "")),
        "review_normalized_exercise_id": str(spec.get("stable_code", "")),
        "review_display_name_ko": str(spec.get("name_ko", "")),
        "training_type_code": str(spec.get("training_type_code", "")),
        "body_focus_code": str(spec.get("body_focus_code", "")),
        "primary_movement_pattern_code": str(spec.get("movement_pattern_code", "")),
        "difficulty_code": str(spec.get("difficulty_code", "")),
        "timing_mode_code": timing,
        "default_seconds_per_rep": (
            str(spec.get("default_seconds_per_rep", "")) if timing == "REPS" else ""
        ),
        "default_work_seconds": (
            str(spec.get("default_work_seconds", "")) if timing == "DURATION" else ""
        ),
        "default_rest_seconds": str(spec.get("default_rest_seconds", "")),
        "default_transition_seconds": "15",
        "recovery_eligible": "TRUE" if spec.get("recovery_eligible") is True else "FALSE",
        "primary_body_area_codes": joined(spec.get("primary_body_area_codes")),
        "secondary_body_area_codes": joined(spec.get("secondary_body_area_codes")),
        "equipment_codes": joined(spec.get("equipment_codes")),
        "location_codes": joined(spec.get("location_codes")),
        "instruction_summary_ko": str(spec.get("instruction_summary_ko", "")),
        "form_cues_ko": joined(spec.get("form_cues_ko")),
        "instruction_content_version": "1.0.0",
        "draft_source": "AGENT_REVIEW_TRANCHE3_v0.1.0",
        "attribute_status": "DOMAIN_APPROVED",
    }
    if list(row) != ATTRIBUTE_FIELDS:
        raise PipelineError("tranche 3 attribute fields do not match the catalog contract")
    return row


def split(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def seed_record(review_record: dict[str, Any], registry: dict[str, set[str]]) -> dict[str, object]:
    row = attribute_row(review_record)
    problems = attribute_problems(row, registry)
    if problems:
        raise PipelineError(
            f"tranche 3 exercise {row['review_normalized_exercise_id']} is not seed ready: "
            f"{problems[0]}"
        )
    spec = review_record["attributes"]
    assert isinstance(spec, dict)
    return {
        "stable_code": row["review_normalized_exercise_id"],
        "name_ko": row["review_display_name_ko"],
        "name_en": str(review_record["source_name"]) if review_record["track"] == "wger" else "",
        "training_type_code": row["training_type_code"],
        "body_focus_code": row["body_focus_code"],
        "primary_movement_pattern_code": row["primary_movement_pattern_code"],
        "difficulty_code": row["difficulty_code"],
        "beginner_suitable": spec.get("beginner_suitability") == "YES",
        "timing_mode_code": row["timing_mode_code"],
        "default_seconds_per_rep": (
            int(row["default_seconds_per_rep"]) if row["default_seconds_per_rep"] else None
        ),
        "default_work_seconds": (
            int(row["default_work_seconds"]) if row["default_work_seconds"] else None
        ),
        "default_rest_seconds": int(row["default_rest_seconds"]),
        "default_transition_seconds": 15,
        "recovery_eligible": row["recovery_eligible"] == "TRUE",
        "primary_body_area_codes": split(row["primary_body_area_codes"]),
        "secondary_body_area_codes": split(row["secondary_body_area_codes"]),
        "equipment_codes": split(row["equipment_codes"]),
        "location_codes": split(row["location_codes"]),
        "instruction_summary_ko": row["instruction_summary_ko"],
        "form_cues_ko": split(row["form_cues_ko"]),
        "instruction_content_version": row["instruction_content_version"],
        "review_status_code": "DOMAIN_APPROVED",
        "source_track": str(review_record["track"]),
        "source_identity": str(review_record["source_identity"]),
    }


def expected_records(results_path: Path) -> dict[str, list[dict[str, object]]]:
    verify_results(DEFAULT_PLAN, results_path)
    results = load_json(results_path)
    values = results.get("records")
    if not isinstance(values, list):
        raise PipelineError("tranche 3 review results have no records")
    registry = load_taxonomy_registry(TAXONOMY)
    by_track: dict[str, list[dict[str, object]]] = {"kspo": [], "wger": []}
    for value in values:
        if not isinstance(value, dict) or value.get("review_decision") != "INCLUDE":
            continue
        track = str(value.get("track", ""))
        if track not in by_track:
            raise PipelineError(f"tranche 3 included record has invalid track: {track}")
        by_track[track].append(seed_record(value, registry))
    if any(not records for records in by_track.values()):
        raise PipelineError("tranche 3 must include records for both tracks")

    existing = load_seed_exercises(list(EXISTING_SEEDS))
    existing_codes = {str(record["stable_code"]) for record in existing}
    existing_names = [str(record["name_ko"]) for record in existing]
    new_records = [record for records in by_track.values() for record in records]
    new_codes = [str(record["stable_code"]) for record in new_records]
    if len(new_codes) != len(set(new_codes)) or set(new_codes) & existing_codes:
        raise PipelineError("tranche 3 stable codes overlap existing catalogs")
    duplicates = duplicate_display_names(
        [*existing_names, *(str(record["name_ko"]) for record in new_records)]
    )
    if duplicates:
        raise PipelineError(f"tranche 3 display names overlap catalogs: {', '.join(duplicates)}")
    check_pattern_rules_hold(load_safety_policy(SAFETY_POLICY), [*existing, *new_records])
    return by_track


def file_entry(path: Path, records: int) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.name,
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "records": records,
    }


def build_seed_for_track(
    track: str,
    records: list[dict[str, object]],
    results_path: Path,
    output_root: Path,
) -> Path:
    version_code = VERSION_CODES[track]
    final_dir = output_root.resolve() / f"exercise-catalog-seed-{version_code}"
    partial_dir = output_root.resolve() / f".exercise-catalog-seed-{version_code}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PipelineError(f"tranche 3 seed output already exists: {final_dir.name}")
    partial_dir.mkdir(parents=True)
    try:
        exercises_path = partial_dir / "exercises.jsonl"
        with exercises_path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        inputs = (
            ("review_results", results_path),
            ("review_plan", DEFAULT_PLAN),
            ("taxonomy_registry", TAXONOMY),
            ("safety_policy", SAFETY_POLICY),
        )
        manifest = {
            "schema_version": "1.0",
            "generator_version": GENERATOR_VERSION,
            "catalog_version": {"version_code": version_code, "status_code": "DRAFT"},
            "source": {
                "track": track,
                "review_batch_directory": "review-tranche-3-agent-json",
                "taxonomy_registry_sha256": sha256_bytes(TAXONOMY.read_bytes()),
                "input_artifacts": [
                    {
                        "role": role,
                        "path": path.name,
                        "sha256": sha256_bytes(path.read_bytes()),
                        "bytes": len(path.read_bytes()),
                    }
                    for role, path in inputs
                ],
            },
            "review": {
                "status": "DOMAIN_APPROVED",
                "review_method_code": "AGENT_ONLY",
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "production_eligible": False,
            },
            "summary": {"exercise_records": len(records)},
            "files": [file_entry(exercises_path, len(records))],
        }
        (partial_dir / "seed_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        verify_seed(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def build_all(results_path: Path, output_root: Path) -> dict[str, object]:
    records = expected_records(results_path)
    built = {
        track: build_seed_for_track(track, track_records, results_path, output_root)
        for track, track_records in records.items()
    }
    return {
        "status": "built",
        "seeds": {track: path.name for track, path in built.items()},
        "records": {track: len(values) for track, values in records.items()},
        "production_eligible": False,
    }


def verify_all(results_path: Path, output_root: Path) -> dict[str, object]:
    expected = expected_records(results_path)
    counts: dict[str, int] = {}
    for track, expected_track in expected.items():
        directory = output_root / f"exercise-catalog-seed-{VERSION_CODES[track]}"
        verify_seed(directory)
        actual = [
            json.loads(line)
            for line in (directory / "exercises.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if actual != expected_track:
            raise PipelineError(f"tranche 3 {track} seed does not match review results")
        manifest = load_json(directory / "seed_manifest.json")
        source = manifest.get("source")
        if not isinstance(source, dict) or source.get("track") != track:
            raise PipelineError(f"tranche 3 {track} seed source metadata is invalid")
        inputs = source.get("input_artifacts")
        if not isinstance(inputs, list):
            raise PipelineError(f"tranche 3 {track} seed input artifacts are missing")
        by_role = {entry.get("role"): entry for entry in inputs if isinstance(entry, dict)}
        if by_role.get("review_results", {}).get("sha256") != sha256_bytes(
            results_path.read_bytes()
        ):
            raise PipelineError(f"tranche 3 {track} review results hash is invalid")
        counts[track] = len(actual)
    return {"status": "valid", "records": counts, "production_eligible": False}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--results", type=Path, default=DEFAULT_OUTPUT)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--results", type=Path, default=DEFAULT_OUTPUT)
    verify.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        result = (
            build_all(args.results, args.output_root)
            if args.command == "build"
            else verify_all(args.results, args.output_root)
        )
    except (PipelineError, OSError, ValueError, KeyError, AssertionError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
