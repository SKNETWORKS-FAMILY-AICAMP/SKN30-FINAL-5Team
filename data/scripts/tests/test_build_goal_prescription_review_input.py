from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_goal_prescription_review_input import (  # noqa: E402
    DEFAULT_POLICY,
    ReviewInputError,
    build,
    build_rows,
)

_POLICY = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))

_CATALOG = [
    {
        "stable_code": "squat_knee_dominant",
        "name_ko": "스쿼트",
        "primary_movement_pattern_code": "KNEE_DOMINANT",
        "training_type_code": "STRENGTH",
        "timing_mode_code": "REPS",
        "difficulty_code": "BEGINNER",
    },
    {
        "stable_code": "calf_stretch_mobility",
        "name_ko": "종아리 스트레칭",
        "primary_movement_pattern_code": "MOBILITY_STRETCH",
        "training_type_code": "MOBILITY",
        "timing_mode_code": "DURATION",
        "difficulty_code": "BEGINNER",
    },
    {
        "stable_code": "advanced_pull_intermediate",
        "name_ko": "중급 풀",
        "primary_movement_pattern_code": "VERTICAL_PULL",
        "training_type_code": "STRENGTH",
        "timing_mode_code": "REPS",
        "difficulty_code": "INTERMEDIATE",
    },
]


def _baseline(stable_code: str, level: str, phase: str) -> dict[str, str]:
    return {
        "goal_code": "GENERAL_FITNESS",
        "exercise_stable_code": stable_code,
        "experience_level_code": level,
        "phase_code": phase,
    }


class BuildGoalPrescriptionReviewInputTests(unittest.TestCase):
    def test_phase_assignment_is_inherited_from_the_approved_baseline(self) -> None:
        # The baseline approves this stretch for warmup only. Proposing it as a
        # cooldown would re-open a curated domain decision.
        baseline = [
            _baseline("calf_stretch_mobility", "BEGINNER", "WARMUP"),
            _baseline("squat_knee_dominant", "BEGINNER", "MAIN"),
        ]

        rows = build_rows(_POLICY, _CATALOG, baseline)

        phases = {(row["goal_code"], row["stable_code"], row["phase_code"]) for row in rows}
        self.assertIn(("FAT_LOSS", "calf_stretch_mobility", "WARMUP"), phases)
        self.assertNotIn(("FAT_LOSS", "calf_stretch_mobility", "COOLDOWN"), phases)

    def test_goal_specific_dosage_differs_for_the_same_exercise(self) -> None:
        baseline = [_baseline("squat_knee_dominant", "BEGINNER", "MAIN")]

        rows = build_rows(_POLICY, _CATALOG, baseline)
        by_goal = {row["goal_code"]: row for row in rows}

        # Hypertrophy rests longer; fat loss keeps the interval short.
        self.assertGreater(
            int(by_goal["MUSCLE_GAIN"]["rest_seconds_per_set"]),
            int(by_goal["FAT_LOSS"]["rest_seconds_per_set"]),
        )
        self.assertGreater(int(by_goal["FAT_LOSS"]["reps"]), int(by_goal["MUSCLE_GAIN"]["reps"]))

    def test_role_eligibility_follows_the_goal(self) -> None:
        baseline = [_baseline("squat_knee_dominant", "BEGINNER", "MAIN")]

        rows = {row["goal_code"]: row for row in build_rows(_POLICY, _CATALOG, baseline)}

        self.assertEqual(rows["MUSCLE_GAIN"]["role_eligibility_code"], "CORE")
        self.assertEqual(rows["FAT_LOSS"]["role_eligibility_code"], "CORE")

    def test_exercises_above_the_user_difficulty_gate_are_skipped(self) -> None:
        baseline = [_baseline("advanced_pull_intermediate", "BEGINNER", "MAIN")]

        self.assertEqual(build_rows(_POLICY, _CATALOG, baseline), [])

    def test_review_verdict_columns_are_never_pre_filled(self) -> None:
        baseline = [_baseline("squat_knee_dominant", "BEGINNER", "MAIN")]

        for row in build_rows(_POLICY, _CATALOG, baseline):
            self.assertEqual(row["review_status_code"], "")
            self.assertEqual(row["reviewer_role_code"], "")
            self.assertEqual(row["production_eligible"], "false")

    def test_unmapped_movement_pattern_fails_closed(self) -> None:
        catalog = [dict(_CATALOG[0], primary_movement_pattern_code="UNKNOWN_PATTERN")]
        baseline = [_baseline("squat_knee_dominant", "BEGINNER", "MAIN")]

        with self.assertRaises(ReviewInputError):
            build_rows(_POLICY, catalog, baseline)

    def test_build_writes_every_baseline_phase_for_both_goals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "exercises.jsonl"
            catalog_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in _CATALOG),
                encoding="utf-8",
            )
            baseline_path = root / "baseline.jsonl"
            baseline_path.write_text(
                json.dumps(_baseline("squat_knee_dominant", "BEGINNER", "MAIN")) + "\n",
                encoding="utf-8",
            )
            output = root / "review.csv"
            # Use a pending copy: once the live policy carries the reviewer's
            # verdict, regenerating a review sheet from it is refused by design.
            pending_policy = root / "policy.json"
            pending = dict(_POLICY, review_status_code="PENDING_DOMAIN_REVIEW")
            pending_policy.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")

            build(pending_policy, catalog_path, output, baseline_path)

            with output.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["goal_code"] for row in rows}, {"FAT_LOSS", "MUSCLE_GAIN"})


if __name__ == "__main__":
    unittest.main()
