from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
OUTPUT = FINAL_DIR / "alternatives"
SCRIPT = Path(__file__).resolve().parents[1] / "review_v2_0_2_discomfort_alternative_map.py"
spec = importlib.util.spec_from_file_location("review_v2_0_2_discomfort_alternative_map", SCRIPT)
assert spec and spec.loader
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class ReviewedDiscomfortAlternativeMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kept_rows = read_jsonl(OUTPUT / "reviewed_discomfort_alternative_map_v2_0_2.jsonl")
        cls.removed_rows = read_jsonl(OUTPUT / "removed_discomfort_alternative_map_v2_0_2.jsonl")
        cls.report = json.loads(
            (OUTPUT / "discomfort_alternative_map_review_report_v2_0_2.json").read_text(
                encoding="utf-8"
            )
        )
        cls.target_sets = json.loads(
            (OUTPUT / "reviewed_discomfort_alternative_target_sets_v2_0_2.json").read_text(
                encoding="utf-8"
            )
        )
        cls.catalog = reviewer.load_catalog(FINAL_DIR / "catalog/exercises.jsonl")

    def test_counts_are_reconciled_and_ambiguous_candidates_are_removed(self) -> None:
        self.assertEqual(len(self.kept_rows), 1517)
        self.assertEqual(len(self.removed_rows), 938)
        self.assertEqual(
            Counter(row["review_decision"] for row in self.kept_rows + self.removed_rows),
            Counter({"KEEP": 1517, "REMOVE": 938}),
        )
        self.assertEqual(
            Counter(row["review_reason_code"] for row in self.removed_rows),
            Counter(
                {
                    "CATALOG_REFERENCE_NOT_ELIGIBLE": 554,
                    "MOVEMENT_LOAD_IMPACT_RISK": 384,
                }
            ),
        )
        self.assertEqual(self.report["counts"]["ambiguous_sent_to_human_review_count"], 0)
        self.assertEqual(
            self.report["counts"]["review_stage_counts"],
            {
                "CATALOG_REFERENCE_ELIGIBILITY": 554,
                "MOVEMENT_LOAD_IMPACT_RISK": 384,
                "REMAINING_CANDIDATE_KEEP": 1517,
            },
        )

    def test_kept_rows_pass_all_ordered_safety_filters(self) -> None:
        for row in self.kept_rows:
            area = row["pain_discomfort_area_code"]
            source = self.catalog[row["source_exercise_stable_code"]]
            target = self.catalog[row["target_exercise_stable_code"]]
            source_areas = set(source["primary_body_area_codes"]) | set(
                source["secondary_body_area_codes"]
            )
            target_areas = set(target["primary_body_area_codes"]) | set(
                target["secondary_body_area_codes"]
            )
            self.assertIn(area, source_areas)
            self.assertNotIn(area, target_areas)
            self.assertEqual(target["record_type"], row["target_record_type"])
            self.assertEqual(source["review_status_code"], "DOMAIN_APPROVED")
            self.assertEqual(target["review_status_code"], "DOMAIN_APPROVED")
            self.assertTrue(set(target["location_codes"]).issubset({"HOME", "GYM"}))
            self.assertTrue(set(target["equipment_codes"]))
            self.assertFalse(set(target["equipment_codes"]) & {"BENCH", "CHAIR", "REVIEW_REQUIRED"})
            self.assertLessEqual(
                reviewer.DIFFICULTY_RANK[target["difficulty_code"]],
                reviewer.DIFFICULTY_RANK[source["difficulty_code"]],
            )
            self.assertEqual(row["movement_load_impact_check_code"], "PASS")
            self.assertEqual(row["nrs_recovery_check_code"], "PASS")
            self.assertEqual(row["context_equipment_check_code"], "PASS")
            self.assertEqual(row["review_decision"], "KEEP")
            self.assertEqual(row["review_status_code"], "DOMAIN_APPROVED")
            self.assertFalse(row["production_eligible"])
            if row["condition_code"] == "NRS_4_6":
                self.assertTrue(target["recovery_eligible"])

    def test_target_sets_cover_each_area_and_condition(self) -> None:
        self.assertEqual(
            set(self.target_sets["sets"]),
            set(reviewer.read_json(reviewer.DEFAULT_POLICY)["supported_pain_area_codes"]),
        )
        for area in reviewer.read_json(reviewer.DEFAULT_POLICY)["supported_pain_area_codes"]:
            for condition in reviewer.VALID_CONDITIONS:
                self.assertGreater(
                    self.target_sets["sets"][area][condition]["target_exercise_count"], 0
                )

    def test_severe_pain_and_variant_overlap_are_not_represented(self) -> None:
        self.assertFalse(any(row["condition_code"] == "NRS_7_10" for row in self.kept_rows))
        self.assertFalse(any(row["target_record_type"] == "VARIANT" for row in self.kept_rows))
        self.assertTrue(all(self.report["invariants"].values()))
        self.assertEqual(self.report["integrity_metrics"]["self_reference_count"], 0)
        self.assertEqual(self.report["integrity_metrics"]["target_pain_area_overlap_count"], 0)
        self.assertEqual(self.report["integrity_metrics"]["unapproved_exercise_reference_count"], 0)

    def test_cross_training_examples_survive_review(self) -> None:
        self.assertTrue(
            any(
                row["pain_discomfort_area_code"] == "SHOULDER"
                and row["target_exercise_stable_code"]
                == "bodyweight_standing_calf_raise_isolation_bodyweight"
                for row in self.kept_rows
            )
        )
        self.assertTrue(
            any(
                row["pain_discomfort_area_code"] == "KNEE"
                and row["target_exercise_stable_code"]
                == "dumbbell_standing_curl_isolation_dumbbell"
                for row in self.kept_rows
            )
        )

    def test_regeneration_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = reviewer.build(output_dir=Path(directory))
            self.assertEqual(result["candidate_map_count"], 2455)
            self.assertEqual(result["reviewed_keep_count"], 1517)
            self.assertEqual(result["removed_count"], 938)
            generated = read_jsonl(
                Path(directory) / "reviewed_discomfort_alternative_map_v2_0_2.jsonl"
            )
            self.assertEqual(generated, self.kept_rows)


if __name__ == "__main__":
    unittest.main()
