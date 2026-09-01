"""Emit a domain-review input CSV for the FAT_LOSS and MUSCLE_GAIN expansion.

The catalog ships DOMAIN_APPROVED prescriptions for GENERAL_FITNESS only, so a
user who picks the other two onboarding goals gets no candidates and routine
creation fails. This script proposes dosage for those goals from the reviewed
policy and leaves every review column blank: a reviewer fills them, and nothing
here may write DOMAIN_APPROVED on its own.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = PROJECT_ROOT / "data/normalized/goal_prescription_review_policy.json"
DEFAULT_CATALOG = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.2-final/backend_bundle/catalog/exercises.jsonl"
)
# Phase assignment is inherited rather than re-derived: the approved
# GENERAL_FITNESS set already records which mobility work is warmup-only and
# which is also approved as cooldown. Re-deriving it would re-open a curated
# domain decision and put 56 unwanted cooldown rows in front of the reviewer.
DEFAULT_BASELINE = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.2-final/backend_bundle/prescriptions"
    / "prescription_profiles.jsonl"
)
BASELINE_GOAL_CODE = "GENERAL_FITNESS"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data/validation/review_input/goal_expansion_prescription_review_input.csv"
)

RESULT_FIELDS = (
    "stable_code",
    "exercise_name_ko",
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
    "movement_pattern_code",
    "training_type_code",
    "timing_mode_code",
    "exercise_difficulty_code",
    "reviewer_role_code",
    "reviewer_reference",
    "evidence_reference",
    "reviewed_at",
    "review_status_code",
    "artifact_status_code",
    "production_eligible",
)

# Difficulty gate mirrors backend.app.domain.rules.training_level so the review
# sheet never proposes an exercise a user of that level can never receive.
ALLOWED_DIFFICULTIES: dict[str, tuple[str, ...]] = {
    "BEGINNER": ("BEGINNER",),
    "INTERMEDIATE": ("BEGINNER", "INTERMEDIATE"),
}


class ReviewInputError(RuntimeError):
    """Raised when the policy and catalog cannot produce a reviewable sheet."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _role_for(policy: dict[str, Any], goal_code: str, pattern: str) -> str | None:
    mapping = policy["role_eligibility_by_movement_pattern"][goal_code]
    if pattern in mapping["CORE"]:
        return "CORE"
    if pattern in mapping["SUPPORT"]:
        return "SUPPORT"
    return None


def _blank_review_columns() -> dict[str, str]:
    """Review verdict columns stay empty; only a human may fill them."""

    return {
        "reviewer_role_code": "",
        "reviewer_reference": "",
        "evidence_reference": "",
        "reviewed_at": "",
        "review_status_code": "",
        "artifact_status_code": "DRAFT",
        "production_eligible": "false",
    }


def build_rows(
    policy: dict[str, Any],
    catalog: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    goals = policy["scope"]["goal_codes"]
    version = policy["prescription_version"]
    mobility_phases = {
        phase["phase_code"]: phase
        for phase in policy["prescription_by_training_type"]["MOBILITY"]["phases"]
    }
    by_goal_timing = policy["prescription_by_goal_timing_mode"]
    by_stable_code = {exercise["stable_code"]: exercise for exercise in catalog}

    seen: set[tuple[str, str, str, str]] = set()
    rows: list[dict[str, Any]] = []
    for source in baseline:
        if source["goal_code"] != BASELINE_GOAL_CODE:
            continue
        stable_code = source["exercise_stable_code"]
        exercise = by_stable_code.get(stable_code)
        if exercise is None:
            raise ReviewInputError(
                f"baseline prescription references unknown exercise {stable_code}"
            )
        level = source["experience_level_code"]
        phase_code = source["phase_code"]
        pattern = exercise["primary_movement_pattern_code"]
        training_type = exercise["training_type_code"]
        timing_mode = exercise["timing_mode_code"]
        difficulty = exercise["difficulty_code"]
        if difficulty not in ALLOWED_DIFFICULTIES[level]:
            continue
        for goal_code in goals:
            key = (goal_code, level, phase_code, stable_code)
            if key in seen:
                continue
            seen.add(key)
            role = _role_for(policy, goal_code, pattern)
            if role is None:
                raise ReviewInputError(
                    f"movement pattern {pattern} is unmapped for {goal_code}; "
                    "extend role_eligibility_by_movement_pattern before generating"
                )
            if phase_code in mobility_phases and training_type == "MOBILITY":
                phase = dict(mobility_phases[phase_code])
            else:
                phase = dict(by_goal_timing[goal_code][timing_mode][level])
                phase["phase_code"] = phase_code
            rows.append(
                {
                    "stable_code": stable_code,
                    "exercise_name_ko": exercise["name_ko"],
                    "goal_code": goal_code,
                    "role_eligibility_code": role,
                    "experience_level_code": level,
                    "phase_code": phase_code,
                    "sets": phase["sets"],
                    "reps": phase.get("reps", ""),
                    "work_seconds_per_set": phase.get("work_seconds_per_set", ""),
                    "rest_seconds_per_set": phase["rest_seconds_per_set"],
                    "intensity_code": phase["intensity_code"],
                    "prescription_version": version,
                    "movement_pattern_code": pattern,
                    "training_type_code": training_type,
                    "timing_mode_code": timing_mode,
                    "exercise_difficulty_code": difficulty,
                    **_blank_review_columns(),
                }
            )
    rows.sort(
        key=lambda row: (
            str(row["goal_code"]),
            str(row["experience_level_code"]),
            str(row["phase_code"]),
            str(row["stable_code"]),
        )
    )
    return rows


def build(
    policy_path: Path = DEFAULT_POLICY,
    catalog_path: Path = DEFAULT_CATALOG,
    output: Path = DEFAULT_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
) -> Path:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("review_status_code") == "DOMAIN_APPROVED":
        raise ReviewInputError("policy must not be pre-approved before domain review")
    catalog = _read_jsonl(catalog_path)
    baseline = _read_jsonl(baseline_path)
    rows = build_rows(policy, catalog, baseline)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()
    path = build(args.policy, args.catalog, args.output, args.baseline)
    print(f"review input written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
