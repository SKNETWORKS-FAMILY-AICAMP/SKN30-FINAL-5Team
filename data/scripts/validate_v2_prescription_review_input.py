"""Fail-closed validation for the V2 102-exercise prescription review input."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from build_v2_prescription_review_input import RESULT_FIELDS
from kspo_fitness100_pipeline import PipelineError, sha256_bytes

VALID_ROLES = {"CORE", "SUPPORT", "OPTIONAL"}
VALID_PHASES = {"WARMUP", "MAIN", "COOLDOWN"}
VALID_INTENSITIES = {"LOW", "MODERATE"}
SUPPORTED_LOCATIONS = ("HOME", "GYM")
SUPPORTED_MINUTES = (20, 30, 40, 50)


def load_catalog(path: Path) -> dict[str, dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except OSError as exc:
        raise PipelineError(f"V2 catalog is unreadable: {path}") from exc
    if len(rows) != 102:
        raise PipelineError("V2 catalog must contain exactly 102 rows")
    result = {row["stable_code"]: row for row in rows}
    if len(result) != len(rows):
        raise PipelineError("V2 catalog stable_code is duplicated")
    return result


def load_results(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != RESULT_FIELDS:
                raise PipelineError("V2 prescription review columns do not match the contract")
            rows = list(reader)
    except OSError as exc:
        raise PipelineError(f"V2 prescription review input is unreadable: {path}") from exc
    if not rows:
        raise PipelineError("V2 prescription review input is empty")
    return rows


def _integer(row: dict[str, str], field: str, *, minimum: int) -> int:
    try:
        value = int(row[field])
    except (KeyError, ValueError) as exc:
        raise PipelineError(f"{field} must be an integer") from exc
    if value < minimum:
        raise PipelineError(f"{field} must be >= {minimum}")
    return value


def _duration(row: dict[str, str], exercise: dict[str, str]) -> int:
    sets = _integer(row, "sets", minimum=1)
    rest = _integer(row, "rest_seconds_per_set", minimum=0)
    reps, work = row["reps"].strip(), row["work_seconds_per_set"].strip()
    if bool(reps) == bool(work):
        raise PipelineError("exactly one of reps and work_seconds_per_set is required")
    if reps:
        if exercise.get("timing_mode_code") != "REPS":
            raise PipelineError("repetition prescription conflicts with V2 catalog timing mode")
        try:
            work_per_set = int(reps) * int(exercise["default_seconds_per_rep"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineError("REPS catalog timing is incomplete") from exc
    else:
        if exercise.get("timing_mode_code") != "DURATION":
            raise PipelineError("duration prescription conflicts with V2 catalog timing mode")
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
    validated: list[tuple[dict[str, str], dict[str, str], int]], location: str, target: int
) -> bool:
    eligible = [
        (row, duration)
        for row, exercise, duration in validated
        if location in exercise["location_codes"].split("|")
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


def validate_results(
    catalog_path: Path, results_path: Path, *, policy_path: Path | None = None
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    rows = load_results(results_path)
    if policy_path is not None:
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("V2 prescription policy is unreadable") from exc
        if policy.get("status") != "DRAFT" or policy.get("production_eligible") is not False:
            raise PipelineError("V2 prescription policy must remain DRAFT and ineligible")

    seen: set[tuple[str, str, str, str]] = set()
    goals: dict[tuple[str, str], str] = {}
    validated: list[tuple[dict[str, str], dict[str, str], int]] = []
    for row in rows:
        stable_code = row["stable_code"].strip()
        exercise = catalog.get(stable_code)
        if exercise is None:
            raise PipelineError(f"V2 prescription references an unknown stable_code: {stable_code}")
        if row["goal_code"] != "GENERAL_FITNESS" or row["experience_level_code"] != "BEGINNER":
            raise PipelineError("unsupported V2 goal or experience level")
        if row["role_eligibility_code"] not in VALID_ROLES:
            raise PipelineError("invalid V2 role eligibility code")
        if row["phase_code"] not in VALID_PHASES or row["intensity_code"] not in VALID_INTENSITIES:
            raise PipelineError("invalid V2 phase or intensity code")
        if row["review_status_code"] != "DOMAIN_APPROVED":
            raise PipelineError("V2 review input lacks review status evidence")
        if row["artifact_status_code"] != "DRAFT" or row["production_eligible"] != "false":
            raise PipelineError("V2 review input must remain DRAFT and production-ineligible")
        if row["reviewer_role_code"] != "DOMAIN_REVIEWER":
            raise PipelineError("V2 review input lacks domain reviewer role")
        if not row["reviewer_reference"].strip() or not row["evidence_reference"].strip():
            raise PipelineError("V2 review evidence reference is missing")
        try:
            reviewed_at = datetime.fromisoformat(row["reviewed_at"])
        except ValueError as exc:
            raise PipelineError("V2 reviewed_at is invalid") from exc
        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
            raise PipelineError("V2 reviewed_at must include timezone information")
        key = (stable_code, row["goal_code"], row["experience_level_code"], row["phase_code"])
        if key in seen:
            raise PipelineError(f"V2 prescription natural key is duplicated: {key}")
        seen.add(key)
        goal_key = (stable_code, row["goal_code"])
        if goal_key in goals and goals[goal_key] != row["role_eligibility_code"]:
            raise PipelineError(f"V2 goal tag role differs between phases: {stable_code}")
        goals[goal_key] = row["role_eligibility_code"]
        validated.append((row, exercise, _duration(row, exercise)))

    if len(goals) != 102:
        raise PipelineError(f"V2 goal tag input must cover 102 exercises, got {len(goals)}")
    phases = {row["phase_code"] for row in rows}
    if phases != VALID_PHASES:
        raise PipelineError("V2 review input must cover every routine phase")
    feasibility = {
        f"{location}_{minutes}": _has_exact_plan(validated, location, minutes * 60)
        for location in SUPPORTED_LOCATIONS
        for minutes in SUPPORTED_MINUTES
    }
    if not all(feasibility.values()):
        missing = sorted(key for key, exists in feasibility.items() if not exists)
        raise PipelineError(f"no exact V2 routine solution for: {', '.join(missing)}")
    return {
        "status": "valid",
        "catalog_records": len(catalog),
        "goal_tag_records": len(goals),
        "prescription_records": len(rows),
        "feasibility": feasibility,
        "review_input_sha256": sha256_bytes(results_path.read_bytes()),
        "production_eligible": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_results(args.catalog, args.results, policy_path=args.policy)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
