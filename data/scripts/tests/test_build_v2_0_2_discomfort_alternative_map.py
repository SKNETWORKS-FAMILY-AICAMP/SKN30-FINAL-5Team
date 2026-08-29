from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
OUTPUT = FINAL_DIR / "alternatives"
SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_2_discomfort_alternative_map.py"
spec = importlib.util.spec_from_file_location("build_v2_0_2_discomfort_alternative_map", SCRIPT)
assert spec and spec.loader
map_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(map_builder)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class DiscomfortAlternativeMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_jsonl(OUTPUT / "discomfort_alternative_map_v2_0_2.jsonl")
        cls.target_sets = json.loads(
            (OUTPUT / "discomfort_alternative_target_sets_v2_0_2.json").read_text(encoding="utf-8")
        )
        cls.report = json.loads(
            (OUTPUT / "discomfort_alternative_map_integrity_report_v2_0_2.json").read_text(
                encoding="utf-8"
            )
        )

    def test_all_supported_pain_areas_have_mild_and_moderate_targets(self) -> None:
        self.assertEqual(set(self.target_sets["pain_areas"]), set(map_builder.PAIN_AREAS))
        for area in map_builder.PAIN_AREAS:
            area_set = self.target_sets["sets"][area]
            for condition in ("NRS_1_3", "NRS_4_6"):
                summary = area_set["conditions"][condition]
                self.assertGreater(summary["source_exercise_count"], 0)
                self.assertEqual(summary["sources_with_target"], summary["source_exercise_count"])
                self.assertEqual(summary["sources_without_target"], [])

    def test_every_map_target_excludes_the_selected_pain_area(self) -> None:
        self.assertGreater(len(self.rows), 0)
        for row in self.rows:
            pain_area = row["pain_discomfort_area_code"]
            target_areas = set(row["target_primary_body_area_codes"]) | set(
                row["target_secondary_body_area_codes"]
            )
            source_areas = set(row["source_primary_body_area_codes"]) | set(
                row["source_secondary_body_area_codes"]
            )
            self.assertIn(pain_area, source_areas)
            self.assertNotIn(pain_area, target_areas)
            self.assertEqual(row["target_pain_area_overlap"], False)
            self.assertEqual(row["direction_code"], "A_TO_B")
            self.assertEqual(row["review_status_code"], "REVIEW_REQUIRED")
            self.assertFalse(row["production_eligible"])

    def test_severe_pain_is_stop_policy_not_an_alternative_row(self) -> None:
        self.assertFalse(any(row["condition_code"] == "NRS_7_10" for row in self.rows))
        self.assertEqual(self.report["integrity_metrics"]["difficulty_increase_count"], 0)
        self.assertTrue(all(self.report["invariants"].values()))

    def test_examples_route_around_pain_area(self) -> None:
        shoulder_targets = {
            row["target_exercise_stable_code"]
            for row in self.rows
            if row["pain_discomfort_area_code"] == "SHOULDER"
        }
        knee_targets = {
            row["target_exercise_stable_code"]
            for row in self.rows
            if row["pain_discomfort_area_code"] == "KNEE"
        }
        self.assertIn("bodyweight_standing_calf_raise_isolation_bodyweight", shoulder_targets)
        self.assertIn("lat_pulldown_vertical_pull_cable_machine", knee_targets)


if __name__ == "__main__":
    unittest.main()
