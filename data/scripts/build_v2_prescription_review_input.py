"""Write a V2 prescription and goal-tag review-input candidate from the 102-row catalog."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from kspo_fitness100_pipeline import PipelineError

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = (
    DATA_ROOT / "generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv"
)
DEFAULT_POLICY = DATA_ROOT / "normalized/v2_prescription_review_policy.json"
DEFAULT_OUTPUT = DATA_ROOT / "validation/review_results/v2_prescription_review_input.csv"

RESULT_FIELDS = (
    "stable_code",
    "goal_code",
    "role_eligibility_code",
    "experience_level_code",
    "phase_code",
    "sets",
    "reps",
    "work_seconds_per_set",
    "rest_seconds_per_set",
    "intensity_code",
    "prescription_version",
    "reviewer_role_code",
    "reviewer_reference",
    "evidence_reference",
    "reviewed_at",
    "review_status_code",
    "artifact_status_code",
    "production_eligible",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "stable_code" not in reader.fieldnames:
                raise PipelineError(f"V2 catalog is missing stable_code: {path}")
            return list(reader)
    except OSError as exc:
        raise PipelineError(f"V2 catalog is unreadable: {path}") from exc


def _read_policy(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"V2 prescription policy is invalid: {path}") from exc
    if value.get("status") != "DRAFT" or value.get("production_eligible") is not False:
        raise PipelineError("V2 prescription policy must remain DRAFT and production-ineligible")
    return value


def _role(policy: dict[str, Any], movement_pattern: str) -> str:
    matches = [
        role
        for role, patterns in policy["role_eligibility_by_movement_pattern"].items()
        if movement_pattern in patterns
    ]
    if len(matches) != 1:
        raise PipelineError(
            f"movement pattern is not assigned exactly one role: {movement_pattern}"
        )
    return matches[0]


def build_rows(
    catalog_path: Path = DEFAULT_CATALOG, policy_path: Path = DEFAULT_POLICY
) -> list[dict[str, object]]:
    catalog = _read_csv(catalog_path)
    policy = _read_policy(policy_path)
    stable_codes = [row["stable_code"] for row in catalog]
    if len(catalog) != 102 or len(set(stable_codes)) != 102:
        raise PipelineError("V2 prescription review input requires 102 unique catalog stable codes")

    rows: list[dict[str, object]] = []
    for exercise in sorted(catalog, key=lambda row: row["stable_code"]):
        training_type = exercise["training_type_code"]
        phase_specs = policy["prescription_by_training_type"].get(training_type)
        if not phase_specs:
            raise PipelineError(f"no prescription review policy for training type: {training_type}")
        if "timing_mode_policy" in phase_specs:
            phase_specs = policy["prescription_by_timing_mode"].get(exercise["timing_mode_code"])
        if not phase_specs:
            raise PipelineError(
                f"no prescription review policy for timing mode: {exercise['timing_mode_code']}"
            )
        for spec in phase_specs["phases"]:
            rows.append(
                {
                    "stable_code": exercise["stable_code"],
                    "goal_code": policy["goal_code"],
                    "role_eligibility_code": _role(
                        policy, exercise["primary_movement_pattern_code"]
                    ),
                    "experience_level_code": policy["experience_level_code"],
                    "phase_code": spec["phase_code"],
                    "sets": spec["sets"],
                    "reps": spec.get("reps", ""),
                    "work_seconds_per_set": spec.get("work_seconds_per_set", ""),
                    "rest_seconds_per_set": spec["rest_seconds_per_set"],
                    "intensity_code": spec["intensity_code"],
                    "prescription_version": policy["prescription_version"],
                    "reviewer_role_code": policy["reviewer_role_code"],
                    "reviewer_reference": policy["reviewer_reference"],
                    "evidence_reference": policy["evidence_reference"],
                    "reviewed_at": policy["reviewed_at"],
                    "review_status_code": policy["review_status_code"],
                    "artifact_status_code": policy["status"],
                    "production_eligible": str(policy["production_eligible"]).lower(),
                }
            )
    return rows


def write_rows(output: Path, rows: list[dict[str, object]], *, force: bool = False) -> None:
    if output.exists() and not force:
        raise PipelineError(f"review input already exists; use --force to regenerate: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        rows = build_rows(args.catalog, args.policy)
        write_rows(args.out, rows, force=args.force)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "written", "rows": len(rows), "path": str(args.out)}, ensure_ascii=False
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
