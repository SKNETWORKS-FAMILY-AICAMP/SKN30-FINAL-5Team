from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_data_golden_scenarios as golden  # noqa: E402


class ValidateDataGoldenScenariosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="helkki-golden-test-"))
        self.safety = self.root / "safety"
        self.safety.mkdir()
        (self.safety / "coverage_report.json").write_text(
            json.dumps(
                {
                    "KNEE": {
                        "MILD": {"excluded_codes": ["leg_press"]},
                        "MODERATE": {"excluded_codes": ["leg_press", "hip_hinge"]},
                    }
                }
            ),
            encoding="utf-8",
        )
        self.exercises = {
            "leg_press": {
                "stable_code": "leg_press",
                "location_codes": ["GYM"],
                "equipment_codes": ["MACHINE"],
            },
            "hip_hinge": {
                "stable_code": "hip_hinge",
                "location_codes": ["GYM"],
                "equipment_codes": ["DUMBBELL"],
            },
        }
        self.relations = [
            {
                "source_exercise_stable_code": "leg_press",
                "alternative_exercise_stable_code": "hip_hinge",
                "reason_code": "DISCOMFORT",
                "difficulty_delta": 0,
            }
        ]

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def scenario(self, severity: str, equipment: list[str], action: str) -> dict[str, object]:
        return {
            "scenario_code": f"TEST_{severity}_{action}",
            "original_exercise_code": "leg_press",
            "body_area_code": "KNEE",
            "severity_code": severity,
            "location_code": "GYM",
            "available_equipment_codes": equipment,
            "expected_action_code": action,
            "expected_original_excluded": severity != "NONE",
            "minimum_alternative_candidates": 1 if action == "CHANGE" else 0,
            "maximum_alternative_candidates": 0 if action == "FALLBACK_REQUIRED" else 1,
        }

    def test_healthy_scenario_keeps_original(self) -> None:
        result = golden.evaluate_scenario(
            self.scenario("NONE", ["MACHINE"], "KEEP"),
            self.exercises,
            self.relations,
            self.safety,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["actual_action_code"], "KEEP")

    def test_mild_scenario_uses_only_available_safe_alternative(self) -> None:
        result = golden.evaluate_scenario(
            self.scenario("MILD", ["MACHINE", "DUMBBELL"], "CHANGE"),
            self.exercises,
            self.relations,
            self.safety,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["alternative_candidate_codes"], ["hip_hinge"])

    def test_safety_veto_and_equipment_gap_require_fallback(self) -> None:
        moderate = self.scenario("MODERATE", ["MACHINE", "DUMBBELL"], "FALLBACK_REQUIRED")
        moderate["proposed_alternative_code"] = "hip_hinge"
        moderate["expected_proposal_accepted"] = False
        result = golden.evaluate_scenario(
            moderate,
            self.exercises,
            self.relations,
            self.safety,
        )
        self.assertTrue(result["passed"])
        self.assertFalse(result["proposal_accepted"])

        equipment_gap = golden.evaluate_scenario(
            self.scenario("MILD", ["MACHINE"], "FALLBACK_REQUIRED"),
            self.exercises,
            self.relations,
            self.safety,
        )
        self.assertTrue(equipment_gap["passed"])


if __name__ == "__main__":
    unittest.main()
