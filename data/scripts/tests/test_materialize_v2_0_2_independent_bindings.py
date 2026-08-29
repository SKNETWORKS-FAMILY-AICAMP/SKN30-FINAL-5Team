import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL = ROOT / "data/generated/exercise-catalog-v2.0.2-final"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class IndependentBindingMaterializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_jsonl(FINAL / "catalog/exercises.jsonl")
        cls.fitt = read_jsonl(FINAL / "prescriptions/prescription_profiles.jsonl")
        cls.safety = read_jsonl(FINAL / "runtime/safety_rules.jsonl")
        cls.goals = read_jsonl(FINAL / "prescriptions/goal_tag_links.jsonl")
        cls.bindings = read_jsonl(FINAL / "audit/reference_binding_status_v2_0_2.jsonl")
        cls.report = json.loads(
            (FINAL / "audit/integrity/independent_bindings_materialization_report_v2_0_2.json").read_text(
                encoding="utf-8"
            )
        )

    def test_all_variants_and_separate_exercises_are_materialized(self) -> None:
        targets = [
            row
            for row in self.catalog
            if row.get("record_type") == "VARIANT"
            or row.get("record_type") == "SEPARATE_EXERCISE"
        ]
        self.assertEqual(Counter(row.get("record_type") for row in targets), {"SEPARATE_EXERCISE": 79, "VARIANT": 15})
        self.assertEqual(self.report["target_record_count"], 94)
        self.assertEqual(self.report["materialized_record_count"], 94)
        self.assertEqual(self.report["unmatched_record_count"], 0)

    def test_independent_fk_sets_and_states_are_complete(self) -> None:
        target_codes = {
            row["stable_code"]
            for row in self.catalog
            if row.get("record_type") in {"VARIANT", "SEPARATE_EXERCISE"}
        }
        self.assertTrue(target_codes <= {row["exercise_stable_code"] for row in self.fitt})
        self.assertTrue(target_codes <= {row["exercise_stable_code"] for row in self.safety})
        self.assertTrue(target_codes <= {row["exercise_stable_code"] for row in self.goals})
        states = {row["stable_code"]: row for row in self.bindings}
        self.assertTrue(
            all(
                states[code][field] == "AVAILABLE"
                for code in target_codes
                for field in (
                    "safety_binding_state_code",
                    "fitt_binding_state_code",
                    "goal_binding_state_code",
                )
            )
        )

    def test_cable_records_use_intermediate_policy(self) -> None:
        cable = [
            row
            for row in self.catalog
            if "CABLE_MACHINE" in row.get("equipment_codes", [])
        ]
        self.assertTrue(cable)
        self.assertTrue(all(row["difficulty_code"] == "INTERMEDIATE" for row in cable))
        for row in cable:
            profiles = [p for p in self.fitt if p["exercise_stable_code"] == row["stable_code"]]
            self.assertTrue(any(p["experience_level_code"] == "INTERMEDIATE" for p in profiles))


if __name__ == "__main__":
    unittest.main()
