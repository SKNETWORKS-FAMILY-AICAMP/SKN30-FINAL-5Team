"""Emit a domain-review input CSV for the compound exercise promotion.

Seven compound movements were reviewed and approved for v2.0.2, then dropped
before the bundle was packaged: ``prune_v2_0_2_user_catalog.keep_base`` keeps a
base record only when the upstream payload marked it ``general_pool_included``,
and these seven were never marked. Nothing rejected them -- the prune report
records ``deleted_record_count: 0``.

The cost shows up in the v2.0.3 approval record, which closes with an
outstanding item: MUSCLE_GAIN has only seven CORE exercises, so the composer
fills a session with isolation and stretching work. Restoring these seven adds
squat, split squat, leg press, kettlebell swing, pull-up, scapular pull-up and
shoulder press to the pool for all three goals.

This script proposes dosage from already-approved tables and leaves every review
column blank. Nothing here may write DOMAIN_APPROVED on its own.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = PROJECT_ROOT / "data/normalized/compound_promotion_policy.json"
DEFAULT_GOAL_POLICY = PROJECT_ROOT / "data/normalized/goal_prescription_review_policy.json"
DEFAULT_GENERAL_POLICY = PROJECT_ROOT / "data/normalized/v2_prescription_review_policy.json"
DEFAULT_CANONICAL = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.2-final/audit/canonical_exercises_v2_final.jsonl"
)
DEFAULT_SHIPPED = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.3-final/backend_bundle/catalog/exercises.jsonl"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "data/validation/review_input/compound_promotion_review_input.csv"

# Same column set as the goal expansion sheet, so a reviewer who has seen that
# sheet already knows this one, and both results files load the same way.
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

# Mirrors backend.app.domain.rules.training_level: a BEGINNER user never
# receives an INTERMEDIATE exercise, so proposing that row would be dead weight
# on the sheet and a dead row in the catalog.
ALLOWED_DIFFICULTIES: dict[str, tuple[str, ...]] = {
    "BEGINNER": ("BEGINNER",),
    "INTERMEDIATE": ("BEGINNER", "INTERMEDIATE"),
}


class ReviewInputError(RuntimeError):
    """Raised when the policies and catalog cannot produce a reviewable sheet."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _role_for(mapping: dict[str, Any], pattern: str, goal_code: str) -> str:
    for role in ("CORE", "SUPPORT", "OPTIONAL"):
        if pattern in (mapping.get(role) or ()):
            return role
    raise ReviewInputError(
        f"movement pattern {pattern} is unmapped for {goal_code}; "
        "extend role_eligibility_by_movement_pattern before generating"
    )


def _dosage(
    policy: dict[str, Any],
    goal_policy: dict[str, Any],
    goal_code: str,
    timing_mode: str,
    level: str,
) -> dict[str, Any]:
    """Read the dosage row from whichever approved table governs this goal."""
    basis = policy["dosage_basis"][goal_code]
    if timing_mode in basis:
        return dict(basis[timing_mode][level])
    # FAT_LOSS and MUSCLE_GAIN defer to the approved goal expansion policy
    # rather than restating its numbers, so there is one place to correct.
    table = goal_policy["prescription_by_goal_timing_mode"][goal_code]
    return dict(table[timing_mode][level])


def build_rows(
    policy: dict[str, Any],
    goal_policy: dict[str, Any],
    general_policy: dict[str, Any],
    canonical: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scope = policy["scope"]
    codes = list(scope["exercise_stable_codes"])
    by_code = {row["stable_code"]: row for row in canonical}
    missing = [code for code in codes if code not in by_code]
    if missing:
        raise ReviewInputError(f"canonical payload does not carry {missing}")

    role_maps = {
        "GENERAL_FITNESS": general_policy["role_eligibility_by_movement_pattern"],
        "FAT_LOSS": goal_policy["role_eligibility_by_movement_pattern"]["FAT_LOSS"],
        "MUSCLE_GAIN": goal_policy["role_eligibility_by_movement_pattern"]["MUSCLE_GAIN"],
    }
    version = policy["prescription_version"]

    rows: list[dict[str, Any]] = []
    for code in codes:
        exercise = by_code[code]
        if exercise.get("review_status_code") != "DOMAIN_APPROVED":
            raise ReviewInputError(f"{code} is not DOMAIN_APPROVED in the canonical payload")
        pattern = exercise["primary_movement_pattern_code"]
        timing_mode = exercise["timing_mode_code"]
        difficulty = exercise["difficulty_code"]
        for goal_code in scope["goal_codes"]:
            role = _role_for(role_maps[goal_code], pattern, goal_code)
            for level in scope["experience_level_codes"]:
                if difficulty not in ALLOWED_DIFFICULTIES[level]:
                    continue
                dosage = _dosage(policy, goal_policy, goal_code, timing_mode, level)
                rows.append(
                    {
                        "stable_code": code,
                        "exercise_name_ko": exercise["name_ko"],
                        "goal_code": goal_code,
                        "role_eligibility_code": role,
                        "experience_level_code": level,
                        "phase_code": dosage["phase_code"],
                        "sets": dosage["sets"],
                        "reps": dosage.get("reps", ""),
                        "work_seconds_per_set": dosage.get("work_seconds_per_set", ""),
                        "rest_seconds_per_set": dosage["rest_seconds_per_set"],
                        "intensity_code": dosage["intensity_code"],
                        "prescription_version": version,
                        "movement_pattern_code": pattern,
                        "training_type_code": exercise["training_type_code"],
                        "timing_mode_code": timing_mode,
                        "exercise_difficulty_code": difficulty,
                        # Verdict columns stay empty; only a reviewer fills them.
                        "reviewer_role_code": "",
                        "reviewer_reference": "",
                        "evidence_reference": "",
                        "reviewed_at": "",
                        "review_status_code": "",
                        "artifact_status_code": "DRAFT",
                        "production_eligible": "false",
                    }
                )
    rows.sort(
        key=lambda row: (
            str(row["goal_code"]),
            str(row["experience_level_code"]),
            str(row["stable_code"]),
        )
    )
    return rows


def build(
    policy_path: Path = DEFAULT_POLICY,
    goal_policy_path: Path = DEFAULT_GOAL_POLICY,
    general_policy_path: Path = DEFAULT_GENERAL_POLICY,
    canonical_path: Path = DEFAULT_CANONICAL,
    shipped_path: Path = DEFAULT_SHIPPED,
    output: Path = DEFAULT_OUTPUT,
) -> Path:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    goal_policy = json.loads(goal_policy_path.read_text(encoding="utf-8"))
    if goal_policy.get("review_status_code") != "DOMAIN_APPROVED":
        raise ReviewInputError("the goal expansion policy this sheet reads is not approved")
    general_policy = json.loads(general_policy_path.read_text(encoding="utf-8"))
    canonical = _read_jsonl(canonical_path)

    # A code already in the shipped catalog is not a promotion candidate, and
    # publishing it again would collide on the stable code.
    shipped = {row["stable_code"] for row in _read_jsonl(shipped_path)}
    already = sorted(set(policy["scope"]["exercise_stable_codes"]) & shipped)
    if already:
        raise ReviewInputError(f"already shipped in the source catalog: {already}")

    rows = build_rows(policy, goal_policy, general_policy, canonical)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--goal-policy", type=Path, default=DEFAULT_GOAL_POLICY)
    parser.add_argument("--general-policy", type=Path, default=DEFAULT_GENERAL_POLICY)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--shipped", type=Path, default=DEFAULT_SHIPPED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    path = build(
        args.policy,
        args.goal_policy,
        args.general_policy,
        args.canonical,
        args.shipped,
        args.output,
    )
    print(f"review input written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
