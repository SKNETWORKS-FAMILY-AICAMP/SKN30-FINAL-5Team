"""Validate the Gym Visual raw snapshot and the four internal catalog seeds.

This is the stage-1 baseline gate. It validates only source integrity and the
existing seed contracts; it does not create mapping candidates or modify any
catalog, safety rule, API, or database artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

EXPECTED_EXTERNAL_RECORD_COUNT = 1324
EXPECTED_INTERNAL_RECORD_COUNT = 56
VALIDATION_VERSION = "gym-visual-baseline-v0.1.0"

REQUIRED_INTERNAL_FIELDS = (
    "stable_code",
    "name_ko",
    "training_type_code",
    "body_focus_code",
    "primary_movement_pattern_code",
    "difficulty_code",
    "beginner_suitable",
    "timing_mode_code",
    "default_seconds_per_rep",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "recovery_eligible",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "equipment_codes",
    "location_codes",
    "instruction_summary_ko",
    "form_cues_ko",
    "instruction_content_version",
    "review_status_code",
    "source_track",
    "source_identity",
)

SEED_SPECS = (
    ("wger_mvp", "exercise-catalog-seed-wger-mvp-v0.2.0", 27, "wger"),
    ("kspo_mvp", "exercise-catalog-seed-kspo-mvp-v0.2.0", 23, "kspo"),
    ("wger_tranche3", "exercise-catalog-seed-wger-tranche3-v0.1.0", 3, "wger"),
    ("kspo_tranche3", "exercise-catalog-seed-kspo-tranche3-v0.1.0", 3, "kspo"),
)


class ValidationFailure(RuntimeError):
    """A fail-closed baseline validation error."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def relative_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationFailure(f"JSON is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"JSON is invalid: {path}") from exc


def validate_external(raw_dir: Path) -> dict[str, Any]:
    exercises_path = raw_dir / "exercises.json"
    schema_path = raw_dir / "exercises.schema.json"
    schema = load_json(schema_path)
    records = load_json(exercises_path)

    try:
        from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise ValidationFailure(
            "JSON Schema validation requires the development package 'jsonschema'"
        ) from exc

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ValidationFailure(f"JSON Schema is invalid: {exc}") from exc

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(records),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if errors:
        details = [
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:20]
        ]
        more = len(errors) - len(details)
        suffix = f"; and {more} more" if more else ""
        raise ValidationFailure("JSON Schema validation failed: " + " | ".join(details) + suffix)

    if not isinstance(records, list):
        raise ValidationFailure("external exercises root must be an array")
    if len(records) != EXPECTED_EXTERNAL_RECORD_COUNT:
        raise ValidationFailure(
            f"external record count is {len(records)}; expected {EXPECTED_EXTERNAL_RECORD_COUNT}"
        )

    missing_ids = [
        index + 1
        for index, record in enumerate(records)
        if not isinstance(record.get("id"), str) or not record["id"].strip()
    ]
    missing_names = [
        index + 1
        for index, record in enumerate(records)
        if not isinstance(record.get("name"), str) or not record["name"].strip()
    ]
    duplicate_ids = sorted(
        identifier
        for identifier, count in Counter(record["id"] for record in records).items()
        if count > 1
    )
    problems: list[str] = []
    if missing_ids:
        problems.append(f"id missing at record(s) {missing_ids[:20]}")
    if missing_names:
        problems.append(f"name missing at record(s) {missing_names[:20]}")
    if duplicate_ids:
        problems.append(f"duplicate id(s): {duplicate_ids[:20]}")
    if problems:
        raise ValidationFailure("external identity checks failed: " + "; ".join(problems))

    return {
        "record_count": len(records),
        "schema": "valid",
        "required_fields": {"id_missing": 0, "name_missing": 0},
        "id_duplicates": 0,
    }


def validate_source_hashes(raw_dir: Path) -> dict[str, Any]:
    source_path = raw_dir / "source.json"
    source = load_json(source_path)
    if not isinstance(source, dict):
        raise ValidationFailure("source.json root must be an object")
    if source.get("record_count") != EXPECTED_EXTERNAL_RECORD_COUNT:
        raise ValidationFailure(
            "source.json record_count does not match the expected external record count"
        )

    manifest_files = source.get("files")
    if not isinstance(manifest_files, list):
        raise ValidationFailure("source.json files must be an array")
    manifest: dict[str, str] = {}
    for entry in manifest_files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValidationFailure("source.json contains an invalid file entry")
        path = entry["path"]
        digest = entry.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValidationFailure(f"source.json has an invalid SHA-256 for {path}")
        if path in manifest:
            raise ValidationFailure(f"source.json lists {path} more than once")
        manifest[path] = digest

    expected_paths = {"exercises.json", "exercises.schema.json"}
    if set(manifest) != expected_paths:
        raise ValidationFailure(
            "source.json must list exactly exercises.json and exercises.schema.json"
        )

    actual: dict[str, str] = {}
    mismatches: list[str] = []
    for filename in sorted(expected_paths):
        path = raw_dir / filename
        try:
            digest = sha256_bytes(path.read_bytes())
        except FileNotFoundError as exc:
            raise ValidationFailure(f"source file is missing: {path}") from exc
        actual[filename] = digest
        if digest != manifest[filename]:
            mismatches.append(filename)
    if mismatches:
        raise ValidationFailure("source SHA-256 mismatch: " + ", ".join(mismatches))

    return {
        "status": "matched",
        "files": {
            filename: {"expected_sha256": manifest[filename], "actual_sha256": actual[filename]}
            for filename in sorted(expected_paths)
        },
    }


def load_seed_records(seed_dir: Path, expected_count: int) -> list[dict[str, Any]]:
    manifest = load_json(seed_dir / "seed_manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValidationFailure(f"invalid seed manifest: {seed_dir}")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise ValidationFailure(f"seed manifest must list one exercises file: {seed_dir}")
    entry = files[0]
    if entry.get("path") != "exercises.jsonl":
        raise ValidationFailure(f"seed manifest exercises path is invalid: {seed_dir}")

    exercises_path = seed_dir / "exercises.jsonl"
    try:
        raw = exercises_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValidationFailure(f"seed exercises file is missing: {exercises_path}") from exc
    if entry.get("sha256") != sha256_bytes(raw) or entry.get("bytes") != len(raw):
        raise ValidationFailure(f"seed manifest hash or byte count mismatch: {seed_dir}")

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationFailure(
                f"seed JSONL is invalid at {exercises_path}:{line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise ValidationFailure(f"seed record is not an object: {exercises_path}:{line_number}")
        records.append(record)

    if len(records) != expected_count or entry.get("records") != len(records):
        raise ValidationFailure(
            f"seed record count mismatch for {seed_dir}: actual={len(records)}, "
            f"expected={expected_count}"
        )
    return records


def nonempty_string(record: dict[str, Any], field: str) -> bool:
    value = record.get(field)
    return isinstance(value, str) and bool(value.strip())


def validate_internal_record(
    record: dict[str, Any], expected_track: str, location: str
) -> list[str]:
    missing = [field for field in REQUIRED_INTERNAL_FIELDS if field not in record]
    problems = [f"{location}: missing field(s): {', '.join(missing)}"] if missing else []
    for field in (
        "stable_code",
        "name_ko",
        "training_type_code",
        "body_focus_code",
        "primary_movement_pattern_code",
        "difficulty_code",
        "timing_mode_code",
        "instruction_summary_ko",
        "instruction_content_version",
        "review_status_code",
        "source_track",
        "source_identity",
    ):
        if not nonempty_string(record, field):
            problems.append(f"{location}: {field} is empty or not a string")

    if record.get("source_track") != expected_track:
        problems.append(f"{location}: source_track does not match {expected_track}")
    if type(record.get("beginner_suitable")) is not bool:
        problems.append(f"{location}: beginner_suitable must be boolean")
    if type(record.get("recovery_eligible")) is not bool:
        problems.append(f"{location}: recovery_eligible must be boolean")

    for field in ("default_rest_seconds", "default_transition_seconds"):
        value = record.get(field)
        if type(value) is not int or value < 0:
            problems.append(f"{location}: {field} must be a non-negative integer")
    transition = record.get("default_transition_seconds")
    if type(transition) is int and not 10 <= transition <= 20:
        problems.append(f"{location}: default_transition_seconds must be between 10 and 20")

    for field in (
        "primary_body_area_codes",
        "secondary_body_area_codes",
        "equipment_codes",
        "location_codes",
        "form_cues_ko",
    ):
        value = record.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            problems.append(f"{location}: {field} must be a list of non-empty strings")
    for field in ("primary_body_area_codes", "equipment_codes", "location_codes", "form_cues_ko"):
        value = record.get(field)
        if isinstance(value, list) and not value:
            problems.append(f"{location}: {field} must not be empty")

    timing = record.get("timing_mode_code")
    seconds_per_rep = record.get("default_seconds_per_rep")
    work_seconds = record.get("default_work_seconds")
    if timing == "REPS":
        if type(seconds_per_rep) is not int or seconds_per_rep <= 0:
            problems.append(f"{location}: REPS requires positive default_seconds_per_rep")
        if work_seconds is not None:
            problems.append(f"{location}: REPS must not set default_work_seconds")
    elif timing == "DURATION":
        if type(work_seconds) is not int or work_seconds <= 0:
            problems.append(f"{location}: DURATION requires positive default_work_seconds")
        if seconds_per_rep is not None:
            problems.append(f"{location}: DURATION must not set default_seconds_per_rep")
    else:
        problems.append(f"{location}: timing_mode_code must be REPS or DURATION")
    return problems


def validate_internal(seed_root: Path) -> dict[str, Any]:
    all_records: list[dict[str, Any]] = []
    seed_results: list[dict[str, Any]] = []
    field_problems: list[str] = []
    for label, directory_name, expected_count, expected_track in SEED_SPECS:
        seed_dir = seed_root / directory_name
        records = load_seed_records(seed_dir, expected_count)
        all_records.extend(records)
        for index, record in enumerate(records, start=1):
            field_problems.extend(
                validate_internal_record(record, expected_track, f"{label}[{index}]")
            )
        seed_results.append({"seed": label, "records": len(records), "status": "valid"})

    if field_problems:
        raise ValidationFailure(
            "internal required mapping field checks failed: " + " | ".join(field_problems[:20])
        )
    if len(all_records) != EXPECTED_INTERNAL_RECORD_COUNT:
        raise ValidationFailure(
            f"combined internal record count is {len(all_records)}; "
            f"expected {EXPECTED_INTERNAL_RECORD_COUNT}"
        )

    stable_codes = [record["stable_code"] for record in all_records]
    duplicate_codes = sorted(code for code, count in Counter(stable_codes).items() if count > 1)
    if duplicate_codes:
        raise ValidationFailure("duplicate internal stable_code(s): " + ", ".join(duplicate_codes))

    return {
        "record_count": len(all_records),
        "stable_code_count": len(set(stable_codes)),
        "stable_code_duplicates": 0,
        "required_mapping_fields_missing": 0,
        "seeds": seed_results,
    }


def run_validation(raw_dir: Path, seed_root: Path, repo_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def run_check(name: str, function: Callable[[], dict[str, Any]]) -> None:
        try:
            details = function()
        except (ValidationFailure, OSError, UnicodeDecodeError, ValueError, KeyError) as exc:
            checks.append({"name": name, "status": "FAIL", "error": str(exc)})
        else:
            checks.append({"name": name, "status": "PASS", "details": details})

    run_check("external_schema_and_identity", lambda: validate_external(raw_dir))
    run_check("source_sha256", lambda: validate_source_hashes(raw_dir))
    run_check("internal_seed_bundle", lambda: validate_internal(seed_root))

    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    return {
        "validation_version": VALIDATION_VERSION,
        "status": status,
        "inputs": {
            "raw_directory": relative_path(raw_dir, repo_root),
            "internal_seed_root": relative_path(seed_root, repo_root),
        },
        "checks": checks,
        "changed_artifacts": [],
        "mapping_candidates_created": False,
    }


def create_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    data_root = repo_root / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=data_root / "raw" / "gym_visual")
    parser.add_argument("--seed-root", type=Path, default=data_root / "generated")
    parser.add_argument("--output", type=Path, help="write the validation report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    report = run_validation(args.raw_dir.resolve(), args.seed_root.resolve(), repo_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
