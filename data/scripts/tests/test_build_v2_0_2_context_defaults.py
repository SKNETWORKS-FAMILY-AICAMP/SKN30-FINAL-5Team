from __future__ import annotations

# ruff: noqa: E501
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
CONTEXT_DIR = FINAL_DIR / "context"
SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_2_context_defaults.py"
spec = importlib.util.spec_from_file_location("build_v2_0_2_context_defaults", SCRIPT)
assert spec and spec.loader
context_defaults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context_defaults)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class ContextDefaultsTests(unittest.TestCase):
    defaults: list[dict]
    candidates: list[dict]
    coverage: list[dict]
    routines: list[dict]
    review_queue: list[dict]
    report: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.defaults = read_jsonl(CONTEXT_DIR / "context_defaults_v2_0_2.jsonl")
        cls.candidates = read_jsonl(CONTEXT_DIR / "context_default_candidates_v2_0_2.jsonl")
        cls.coverage = read_jsonl(CONTEXT_DIR / "family_context_coverage_v2_0_2.jsonl")
        cls.routines = read_jsonl(CONTEXT_DIR / "routine_coverage_v2_0_2.jsonl")
        cls.review_queue = read_jsonl(CONTEXT_DIR / "context_default_review_queue_v2_0_2.jsonl")
        cls.report = json.loads(
            (CONTEXT_DIR / "context_coverage_report_v2_0_2.json").read_text(encoding="utf-8")
        )

    def test_home_policy_includes_bodyweight_and_household_weight_only_with_supported_set(
        self,
    ) -> None:
        expected = {
            "BODYWEIGHT",
            "HOUSEHOLD_WEIGHT",
            "MAT",
            "DUMBBELL",
            "RESISTANCE_BAND",
            "FOAM_ROLLER",
            "JUMP_ROPE",
        }
        self.assertEqual(set(context_defaults.HOME_SUPPORTED_EQUIPMENT), expected)
        self.assertEqual(set(self.report["policy"]["home_supported_equipment_codes"]), expected)

    def test_home_defaults_contain_bodyweight_and_household_weight(self) -> None:
        home_defaults = [row for row in self.defaults if row["context_code"] == "HOME"]
        self.assertTrue(
            any("BODYWEIGHT" in row["default_equipment_codes"] for row in home_defaults)
        )
        household_rows = [
            row for row in home_defaults if "HOUSEHOLD_WEIGHT" in row["default_equipment_codes"]
        ]
        self.assertEqual(
            [(row["family_code"], row["default_exercise_id"]) for row in household_rows],
            [("HAND_GRIP_SQUEEZE", "REX-000035")],
        )
        for row in home_defaults:
            self.assertTrue(
                set(row["default_equipment_codes"])
                <= set(context_defaults.HOME_SUPPORTED_EQUIPMENT)
            )

    def test_equipment_is_metadata_not_runtime_selection_input(self) -> None:
        self.assertEqual(
            self.report["policy"]["equipment_metadata_role"],
            "equipment_codes는 운동 분류와 수행 안내에만 사용하며 사용자 입력·개인화 필터로 사용하지 않는다.",
        )
        self.assertEqual(
            self.report["policy"]["context_priority"][-1],
            "BEGINNER_DIFFICULTY_THEN_EXERCISE_ID_TIEBREAK",
        )

    def test_defaults_and_fallbacks_stay_inside_the_same_family(self) -> None:
        candidates_by_key: dict[tuple[str, str], set[str]] = {}
        for row in self.candidates:
            key = (row["family_code"], row["context_code"])
            candidates_by_key.setdefault(key, set()).add(row["candidate_exercise_id"])
        for row in self.defaults:
            key = (row["family_code"], row["context_code"])
            ids = candidates_by_key.get(key, set())
            if row["default_exercise_id"]:
                self.assertIn(row["default_exercise_id"], ids)
            self.assertTrue(
                {item["candidate_exercise_id"] for item in row["fallback_candidates"]} <= ids
            )
        self.assertNotIn("SEPARATE_EXERCISE", {row["record_type"] for row in self.candidates})

    def test_variant_defaults_are_review_gated(self) -> None:
        variant_defaults = [row for row in self.defaults if row["default_record_type"] == "VARIANT"]
        self.assertEqual(len(variant_defaults), 7)
        self.assertTrue(
            all(
                row["default_variant_type_code"] in {"PRIMARY_VARIANT", "SECONDARY_VARIANT"}
                and row["review_status_code"] == "REVIEW_REQUIRED"
                and row["production_eligible"] is False
                for row in variant_defaults
            )
        )

    def test_routine_coverage_is_draft_composable_but_not_operational(self) -> None:
        self.assertEqual(len(self.routines), 4)
        self.assertTrue(
            all(row["draft_pool_status_code"] == "DRAFT_COMPOSABLE" for row in self.routines)
        )
        self.assertTrue(
            all(all(row["duration_support_by_requested_minutes"].values()) for row in self.routines)
        )
        self.assertTrue(
            all(
                row["operational_status_code"] == "BLOCKED_PRODUCTION_GATE" for row in self.routines
            )
        )

    def test_coverage_summary_and_blockers_are_reproduced(self) -> None:
        self.assertEqual(
            Counter(
                (row["context_code"], row["context_coverage_status_code"]) for row in self.coverage
            ),
            Counter(
                {
                    ("HOME", "COVERED_DRAFT"): 58,
                    ("HOME", "REVIEW_REQUIRED"): 9,
                    ("HOME", "UNAVAILABLE"): 19,
                    ("GYM", "COVERED_DRAFT"): 84,
                    ("GYM", "REVIEW_REQUIRED"): 2,
                    ("GYM", "UNAVAILABLE"): 0,
                }
            ),
        )
        self.assertEqual(self.report["counts"]["home_location_equipment_conflict_rows"], 0)
        self.assertEqual(self.report["counts"]["home_without_gym_rows"], 0)
        self.assertEqual(self.report["counts"]["review_queue_rows"], 114)
        self.assertEqual(
            sum(row["reason_code"] == "HOME_NOT_GYM_LOCATION" for row in self.review_queue),
            0,
        )
        self.assertTrue(all(row["item_type_code"] != "ALTERNATIVE" for row in self.review_queue))


if __name__ == "__main__":
    unittest.main()
