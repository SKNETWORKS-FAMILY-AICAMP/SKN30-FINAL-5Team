from __future__ import annotations

import csv
import hashlib
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_v2_0_4_backend_bundle import (  # noqa: E402
    SOURCE_VERSION,
    TARGET_VERSION,
    _retarget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_BUNDLE = PROJECT_ROOT / f"data/generated/{SOURCE_VERSION}/backend_bundle"
TARGET_BUNDLE = PROJECT_ROOT / f"data/generated/{TARGET_VERSION}/backend_bundle"
PROMOTE_SCRIPT = PROJECT_ROOT / "backend/scripts/catalog_promote_v2_0_4.py"
POLICY = PROJECT_ROOT / "data/normalized/compound_promotion_policy.json"
RESULTS = PROJECT_ROOT / "data/validation/review_results/compound_promotion_review_results.csv"

GOALS = ("GENERAL_FITNESS", "FAT_LOSS", "MUSCLE_GAIN")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _promoted_codes() -> set[str]:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    return set(policy["scope"]["exercise_stable_codes"])


class PublishedV204BundleTests(unittest.TestCase):
    """Guards on the published artifact, not on a synthetic fixture."""

    def test_source_version_is_untouched_by_the_promotion(self) -> None:
        exercises = _read_jsonl(SOURCE_BUNDLE / "catalog/exercises.jsonl")

        codes = {row["stable_code"] for row in exercises}

        self.assertEqual(len(exercises), 155)
        self.assertEqual(codes & _promoted_codes(), set())

    def test_target_version_carries_every_promoted_exercise(self) -> None:
        exercises = _read_jsonl(TARGET_BUNDLE / "catalog/exercises.jsonl")

        by_code = {row["stable_code"]: row for row in exercises}
        promoted = _promoted_codes()

        self.assertEqual(len(exercises), 162)
        self.assertTrue(promoted <= set(by_code))
        for code in promoted:
            record = by_code[code]
            # The promotion is exactly this flag: without it the record is in
            # the catalog but the composer never draws it.
            self.assertIs(record["general_pool_included"], True)
            self.assertEqual(record["review_status_code"], "DOMAIN_APPROVED")
            self.assertEqual(record["record_type"], "REPRESENTATIVE")
            self.assertIsNone(record["representative_stable_code"])

    def test_promoted_exercises_are_core_work_for_every_goal(self) -> None:
        links = _read_jsonl(TARGET_BUNDLE / "prescriptions/goal_tag_links.jsonl")

        promoted = _promoted_codes()
        by_code: dict[str, dict[str, str]] = {}
        for row in links:
            code = str(row["exercise_stable_code"])
            if code in promoted:
                by_code.setdefault(code, {})[str(row["goal_code"])] = str(
                    row["role_eligibility_code"]
                )

        for code in promoted:
            self.assertEqual(set(by_code[code]), set(GOALS), code)
            # Compound, multi-joint movements. If any of these came back as
            # SUPPORT the promotion would not have fixed what it was for: a
            # main block with no real strength work in it.
            self.assertEqual(set(by_code[code].values()), {"CORE"}, code)

    def test_every_promoted_exercise_carries_a_substantive_safety_rule(self) -> None:
        rules = _read_jsonl(TARGET_BUNDLE / "safety/safety_rules.jsonl")

        promoted = _promoted_codes()
        covered = {
            str(rule["exercise_stable_code"])
            for rule in rules
            if rule.get("rule_scope") is not None
        }

        # A record behind only a placeholder row could never be excluded for any
        # reported pain area, which is the failure the safety veto exists for.
        self.assertEqual(promoted - covered, set())
        for rule in rules:
            if str(rule["exercise_stable_code"]) in promoted:
                self.assertEqual(rule["review_status_code"], "DOMAIN_APPROVED")

    def test_intermediate_exercises_never_reach_a_beginner(self) -> None:
        exercises = {
            row["stable_code"]: row
            for row in _read_jsonl(TARGET_BUNDLE / "catalog/exercises.jsonl")
        }
        profiles = _read_jsonl(TARGET_BUNDLE / "prescriptions/prescription_profiles.jsonl")

        for row in profiles:
            record = exercises[row["exercise_stable_code"]]
            if row["experience_level_code"] == "BEGINNER":
                self.assertEqual(record["difficulty_code"], "BEGINNER", row["exercise_stable_code"])

    def test_every_published_prescription_row_was_reviewed(self) -> None:
        with RESULTS.open(encoding="utf-8", newline="") as handle:
            reviewed = list(csv.DictReader(handle))

        self.assertTrue(reviewed)
        for row in reviewed:
            self.assertEqual(row["review_status_code"], "DOMAIN_APPROVED")
            self.assertTrue(row["reviewer_reference"].strip())
            self.assertTrue(row["reviewed_at"].strip())

        profiles = _read_jsonl(TARGET_BUNDLE / "prescriptions/prescription_profiles.jsonl")
        promoted = _promoted_codes()
        published = {
            (
                str(row["exercise_stable_code"]),
                str(row["goal_code"]),
                str(row["experience_level_code"]),
            )
            for row in profiles
            if str(row["exercise_stable_code"]) in promoted
        }
        expected = {
            (row["stable_code"], row["goal_code"], row["experience_level_code"]) for row in reviewed
        }

        self.assertEqual(published, expected)

    def test_no_record_still_points_at_the_source_version(self) -> None:
        for jsonl in sorted(TARGET_BUNDLE.rglob("*.jsonl")):
            for row in _read_jsonl(jsonl):
                self.assertNotIn(SOURCE_VERSION, json.dumps(row, ensure_ascii=False))

    def test_derivation_is_recorded_and_verifiable(self) -> None:
        manifest = json.loads((TARGET_BUNDLE / "bundle_manifest.json").read_text("utf-8"))
        derived = manifest["derived_from"]

        self.assertEqual(derived["catalog_version_code"], SOURCE_VERSION)
        source_hash = hashlib.sha256(
            (SOURCE_BUNDLE / "bundle_manifest.json").read_bytes()
        ).hexdigest()
        self.assertEqual(derived["bundle_manifest_sha256"], source_hash)
        self.assertEqual(
            sorted(derived["compound_promotion"]["exercise_stable_codes"]),
            sorted(_promoted_codes()),
        )

    def test_manifest_hashes_match_the_files_on_disk(self) -> None:
        manifest = json.loads((TARGET_BUNDLE / "bundle_manifest.json").read_text("utf-8"))

        for entry in manifest["files"]:
            path = TARGET_BUNDLE / entry["path"]
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(entry["bytes"], path.stat().st_size)

    def test_promotion_script_pins_the_published_manifest_hash(self) -> None:
        # A stale pin would fail the import at deploy time instead of here.
        published = hashlib.sha256(
            (TARGET_BUNDLE / "bundle_manifest.json").read_bytes()
        ).hexdigest()

        self.assertIn(published, PROMOTE_SCRIPT.read_text(encoding="utf-8"))

    def test_retarget_moves_versions_without_touching_other_text(self) -> None:
        payload = {
            "catalog_version_code": SOURCE_VERSION,
            "carried_over_source": "exercise-catalog-v2.0.1-final/runtime",
            "note": "unrelated text",
        }

        moved = _retarget(payload)

        self.assertEqual(moved["catalog_version_code"], TARGET_VERSION)
        self.assertEqual(moved["carried_over_source"], "exercise-catalog-v2.0.1-final/runtime")
        self.assertEqual(moved["note"], "unrelated text")


if __name__ == "__main__":
    unittest.main()
