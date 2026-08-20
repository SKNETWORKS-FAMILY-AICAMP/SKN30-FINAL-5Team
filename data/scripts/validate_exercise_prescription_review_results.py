"""Validate authored exercise goal-tag and prescription review results.

The validator is intentionally independent from the authoring module: it validates the
CSV contract, catalog references, timing compatibility, review evidence, and exact-duration
routine feasibility for HOME/GYM at every supported duration.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError, sha256_bytes
from prescription_review_authoring import RESULT_FIELDS

VALID_ROLES = {"CORE", "SUPPORT", "OPTIONAL"}
VALID_PHASES = {"WARMUP", "MAIN", "COOLDOWN"}
VALID_INTENSITIES = {"LOW", "MODERATE"}
SUPPORTED_LOCATIONS = ("HOME", "GYM")
SUPPORTED_MINUTES = (20, 30, 40, 50)


def _integer(row: dict[str, str], field: str, *, minimum: int) -> int:
    try:
        value = int(row[field])
    except (KeyError, ValueError) as exc:
        raise PipelineError(f"{field} must be an integer") from exc
    if value < minimum:
        raise PipelineError(f"{field} must be >= {minimum}")
    return value


def load_catalog(seed_dir: Path) -> dict[str, dict[str, Any]]:
    manifest_path = seed_dir / "seed_manifest.json"
    records_path = seed_dir / "exercises.jsonl"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw = records_path.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("catalog seed is missing or invalid") from exc
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise PipelineError("catalog seed manifest must declare one exercise file")
    entry = files[0]
    if entry.get("path") != "exercises.jsonl" or entry.get("sha256") != sha256_bytes(raw):
        raise PipelineError("catalog exercise hash mismatch")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != entry.get("records"):
        raise PipelineError("catalog exercise count mismatch")
    records = {str(row["stable_code"]): row for row in rows}
    if len(records) != len(rows):
        raise PipelineError("catalog stable_code is duplicated")
    return records


def load_results(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != RESULT_FIELDS:
                raise PipelineError("prescription review CSV columns do not match the contract")
            rows = list(reader)
    except OSError as exc:
        raise PipelineError("prescription review CSV is unreadable") from exc
    if not rows:
        raise PipelineError("prescription review CSV is empty")
    return rows


def _duration(row: dict[str, str], exercise: dict[str, Any]) -> int:
    sets = _integer(row, "sets", minimum=1)
    rest = _integer(row, "rest_seconds_per_set", minimum=0)
    reps, work = row["reps"].strip(), row["work_seconds_per_set"].strip()
    if bool(reps) == bool(work):
        raise PipelineError("exactly one of reps and work_seconds_per_set is required")
    if reps:
        if exercise.get("timing_mode_code") != "REPS":
            raise PipelineError("repetition prescription conflicts with catalog timing mode")
        work_per_set = int(reps) * int(exercise["default_seconds_per_rep"])
    else:
        if exercise.get("timing_mode_code") != "DURATION":
            raise PipelineError("duration prescription conflicts with catalog timing mode")
        work_per_set = _integer(row, "work_seconds_per_set", minimum=1)
    return (
        sets * work_per_set + max(sets - 1, 0) * rest + int(exercise["default_transition_seconds"])
    )


def _phase_states(items: list[tuple[int, bool]], limit: int) -> set[tuple[int, bool]]:
    states = {(0, False)}
    for seconds, core in items:
        states |= {
            (total + seconds, has_core or core)
            for total, has_core in tuple(states)
            if total + seconds <= limit
        }
    return states


def _has_exact_plan(
    validated: list[tuple[dict[str, str], dict[str, Any], int]], location: str, target: int
) -> bool:
    eligible = [
        (row, duration)
        for row, exercise, duration in validated
        if location in exercise["location_codes"]
    ]
    by_phase = {
        phase: [
            (duration, row["role_eligibility_code"] == "CORE")
            for row, duration in eligible
            if row["phase_code"] == phase
        ]
        for phase in VALID_PHASES
    }
    warmups = _phase_states(by_phase["WARMUP"], min(target, 180))
    mains = _phase_states(by_phase["MAIN"], target)
    cooldowns = _phase_states(by_phase["COOLDOWN"], min(target, 120))
    return any(
        0 <= target - warmup - main - cooldown <= 60
        for warmup, _ in warmups
        if 60 <= warmup <= 180
        for main, has_core in mains
        if main > 0 and has_core
        for cooldown, _ in cooldowns
        if 45 <= cooldown <= 120
    )


def validate_results(seed_dir: Path, results_path: Path) -> dict[str, object]:
    catalog = load_catalog(seed_dir)
    rows = load_results(results_path)
    seen: set[tuple[str, str, str, str]] = set()
    roles: dict[tuple[str, str], str] = {}
    validated: list[tuple[dict[str, str], dict[str, Any], int]] = []
    for row in rows:
        stable_code = row["stable_code"].strip()
        exercise = catalog.get(stable_code)
        if exercise is None or exercise.get("beginner_suitable") is not True:
            raise PipelineError(
                f"review references an unknown/non-beginner exercise: {stable_code}"
            )
        if row["goal_code"] != "GENERAL_FITNESS" or row["experience_level_code"] != "BEGINNER":
            raise PipelineError("unsupported goal or experience level")
        if row["role_eligibility_code"] not in VALID_ROLES:
            raise PipelineError("invalid role eligibility code")
        if row["phase_code"] not in VALID_PHASES or row["intensity_code"] not in VALID_INTENSITIES:
            raise PipelineError("invalid phase or intensity code")
        if (
            row["review_status_code"] != "DOMAIN_APPROVED"
            or row["reviewer_role_code"] != "DOMAIN_REVIEWER"
        ):
            raise PipelineError("prescription review lacks domain approval evidence")
        if not row["reviewer_reference"].strip() or not row["evidence_reference"].strip():
            raise PipelineError("prescription review evidence reference is missing")
        try:
            reviewed_at = datetime.fromisoformat(row["reviewed_at"])
        except ValueError as exc:
            raise PipelineError("reviewed_at is invalid") from exc
        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
            raise PipelineError("reviewed_at must include timezone information")
        key = (stable_code, row["goal_code"], row["experience_level_code"], row["phase_code"])
        if key in seen:
            raise PipelineError("prescription natural key is duplicated")
        seen.add(key)
        role_key = (stable_code, row["goal_code"])
        if role_key in roles and roles[role_key] != row["role_eligibility_code"]:
            raise PipelineError("goal-tag role differs between phases")
        roles[role_key] = row["role_eligibility_code"]
        validated.append((row, exercise, _duration(row, exercise)))

    phases = {row["phase_code"] for row in rows}
    if phases != VALID_PHASES:
        raise PipelineError("review results must cover every routine phase")
    feasibility = {
        f"{location}_{minutes}": _has_exact_plan(validated, location, minutes * 60)
        for location in SUPPORTED_LOCATIONS
        for minutes in SUPPORTED_MINUTES
    }
    if not all(feasibility.values()):
        missing = sorted(key for key, exists in feasibility.items() if not exists)
        raise PipelineError(f"no exact routine solution for: {', '.join(missing)}")
    return {
        "status": "valid",
        "prescription_records": len(rows),
        "goal_tag_records": len(roles),
        "feasibility": feasibility,
    }


__all__ = ["load_catalog", "load_results", "validate_results"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed", type=Path)
    parser.add_argument("results", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_results(args.seed, args.results)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
