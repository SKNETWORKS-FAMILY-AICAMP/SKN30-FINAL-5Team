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

from build_goal_prescription_bundle import BundleError, build  # noqa: E402

REVIEW_COLUMNS = [
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
]


def _row(goal: str, status: str = "DOMAIN_APPROVED") -> dict[str, str]:
    return {
        "stable_code": "squat",
        "exercise_name_ko": "스쿼트",
        "goal_code": goal,
        "role_eligibility_code": "CORE",
        "experience_level_code": "BEGINNER",
        "phase_code": "MAIN",
        "sets": "2",
        "reps": "10",
        "work_seconds_per_set": "",
        "rest_seconds_per_set": "60",
        "intensity_code": "MODERATE",
        "prescription_version": "v2.0.3-goal-expansion-draft",
        "movement_pattern_code": "KNEE_DOMINANT",
        "training_type_code": "STRENGTH",
        "timing_mode_code": "REPS",
        "exercise_difficulty_code": "BEGINNER",
        "reviewer_role_code": "DOMAIN_REVIEWER",
        "reviewer_reference": "REF-R01",
        "evidence_reference": "EVIDENCE",
        "reviewed_at": "2026-08-31T15:00:00+09:00",
        "review_status_code": status,
        "artifact_status_code": "DRAFT",
        "production_eligible": "true",
    }


class BuildGoalPrescriptionBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bundle = self.root / "prescriptions"
        self.bundle.mkdir()
        baseline_link = {
            "catalog_version_code": "exercise-catalog-v2.0.2-final",
            "exercise_stable_code": "squat",
            "goal_code": "GENERAL_FITNESS",
            "review_status_code": "DOMAIN_APPROVED",
            "role_eligibility_code": "CORE",
        }
        baseline_profile = dict(
            baseline_link,
            experience_level_code="BEGINNER",
            phase_code="MAIN",
            sets=2,
            reps=8,
            rest_seconds_per_set=45,
            intensity_code="MODERATE",
            work_seconds_per_set=None,
        )
        (self.bundle / "goal_tag_links.jsonl").write_text(
            json.dumps(baseline_link, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (self.bundle / "prescription_profiles.jsonl").write_text(
            json.dumps(baseline_profile, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (self.bundle / "prescription_manifest.json").write_text(
            json.dumps(
                {
                    "files": [
                        {"path": "goal_tag_links.jsonl", "sha256": "", "bytes": 0, "records": 0},
                        {
                            "path": "prescription_profiles.jsonl",
                            "sha256": "",
                            "bytes": 0,
                            "records": 0,
                        },
                    ],
                    "summary": {"goal_tag_records": 0, "prescription_records": 0},
                }
            ),
            encoding="utf-8",
        )
        self.policy = self.root / "policy.json"
        self._write_policy("DOMAIN_APPROVED")
        self.results = self.root / "results.csv"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_policy(self, status: str) -> None:
        self.policy.write_text(
            json.dumps(
                {
                    "review_status_code": status,
                    "approval_method_code": "OWNER_BATCH_CONFIRMATION",
                    "reviewer_reference": "REF-R01",
                    "reviewed_at": "2026-08-31T15:00:00+09:00",
                    "prescription_version": "v2.0.3-goal-expansion-draft",
                    "policy_version": "goal-prescription-review-policy-2026-08-31",
                    "scope": {"goal_codes": ["FAT_LOSS", "MUSCLE_GAIN"]},
                }
            ),
            encoding="utf-8",
        )

    def _write_results(self, rows: list[dict[str, str]]) -> None:
        with self.results.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def _profiles(self) -> list[dict[str, object]]:
        with (self.bundle / "prescription_profiles.jsonl").open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_approved_rows_are_added_without_touching_the_baseline_goal(self) -> None:
        self._write_results([_row("FAT_LOSS"), _row("MUSCLE_GAIN")])

        build(results_path=self.results, policy_path=self.policy, bundle_dir=self.bundle)

        goals = [row["goal_code"] for row in self._profiles()]
        self.assertEqual(sorted(goals), ["FAT_LOSS", "GENERAL_FITNESS", "MUSCLE_GAIN"])

    def test_rows_that_were_not_approved_are_excluded(self) -> None:
        self._write_results([_row("FAT_LOSS"), _row("MUSCLE_GAIN", status="REJECTED")])

        build(results_path=self.results, policy_path=self.policy, bundle_dir=self.bundle)

        goals = {row["goal_code"] for row in self._profiles()}
        self.assertNotIn("MUSCLE_GAIN", goals)

    def test_rebuilding_is_idempotent(self) -> None:
        self._write_results([_row("FAT_LOSS")])

        build(results_path=self.results, policy_path=self.policy, bundle_dir=self.bundle)
        first = len(self._profiles())
        build(results_path=self.results, policy_path=self.policy, bundle_dir=self.bundle)

        self.assertEqual(len(self._profiles()), first)

    def test_unreviewed_policy_fails_closed(self) -> None:
        self._write_policy("PENDING_DOMAIN_REVIEW")
        self._write_results([_row("FAT_LOSS")])

        with self.assertRaises(BundleError):
            build(results_path=self.results, policy_path=self.policy, bundle_dir=self.bundle)

    def test_manifest_hashes_track_the_written_files(self) -> None:
        self._write_results([_row("FAT_LOSS")])

        build(results_path=self.results, policy_path=self.policy, bundle_dir=self.bundle)

        manifest = json.loads((self.bundle / "prescription_manifest.json").read_text("utf-8"))
        for entry in manifest["files"]:
            self.assertTrue(entry["sha256"])
            self.assertEqual(entry["bytes"], (self.bundle / entry["path"]).stat().st_size)


if __name__ == "__main__":
    unittest.main()
