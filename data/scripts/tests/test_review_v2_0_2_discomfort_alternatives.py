from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve().parents[1] / "review_v2_0_2_discomfort_alternatives.py"
spec = importlib.util.spec_from_file_location("review_v2_0_2_discomfort_alternatives", SCRIPT)
assert spec and spec.loader
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class DiscomfortAlternativeReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.output = ROOT / "data/generated/exercise-catalog-v2.0.2-final/audit/alternatives"
        cls.review_rows = read_jsonl(cls.output / "pain_alternative_review_result_v2_0_2.jsonl")
        cls.normalized_rows = read_jsonl(
            cls.output / "normalized_discomfort_alternatives_v2_0_2.jsonl"
        )
        cls.report = json.loads(
            (cls.output / "alternative_integrity_report_v2_0_2.json").read_text(encoding="utf-8")
        )
        cls.neck_rows = read_jsonl(cls.output / "neck_alternative_review_v2_0_2.jsonl")
        cls.lower_back_rows = read_jsonl(
            cls.output / "lower_back_alternative_safety_review_v2_0_2.jsonl"
        )

    def test_legacy_decision_counts_are_reconciled(self) -> None:
        self.assertEqual(len(self.review_rows), 279)
        self.assertEqual(
            Counter(row["legacy_reason_code"] for row in self.review_rows),
            Counter(
                {
                    "DISCOMFORT": 220,
                    "LOCATION": 34,
                    "EQUIPMENT": 19,
                    "DIFFICULTY": 6,
                }
            ),
        )
        self.assertEqual(
            Counter(row["decision"] for row in self.review_rows),
            Counter(
                {
                    "KEEP": 157,
                    "REMOVE_RECLASSIFY": 122,
                }
            ),
        )

    def test_same_area_targets_are_removed_even_for_mild_discomfort(self) -> None:
        same_area_rows = [
            row
            for row in self.review_rows
            if row["legacy_reason_code"] == "DISCOMFORT"
            and row["reclassification_code"] == "REMOVE_TARGET_RETAINS_DISCOMFORT_AREA"
        ]
        self.assertEqual(len(same_area_rows), 52)
        self.assertTrue(all(row["condition_code"] == "NRS_1_3" for row in same_area_rows))
        self.assertTrue(all(row["decision"] == "REMOVE_RECLASSIFY" for row in same_area_rows))
        self.assertTrue(
            all(
                row["reclassification_code"] == "REMOVE_TARGET_RETAINS_DISCOMFORT_AREA"
                for row in same_area_rows
            )
        )
        self.assertFalse(any(row["decision"] == "REVIEW_REQUIRED" for row in self.review_rows))

    def test_neck_candidates_are_separately_reviewed(self) -> None:
        self.assertEqual(len(self.neck_rows), 4)
        self.assertEqual(
            Counter(row["decision"] for row in self.neck_rows),
            Counter({"KEEP": 3, "REMOVE_RECLASSIFY": 1}),
        )
        self.assertEqual(
            next(row for row in self.neck_rows if row["target_exercise_id"] == "REX-000009")[
                "reclassification_code"
            ],
            "REMOVE_NECK_TARGET_SAFETY_UNCONFIRMED",
        )
        self.assertTrue(
            all(
                not (
                    {"NECK", "SHOULDER"}
                    & (
                        set(row["target_primary_body_area_codes"])
                        | set(row["target_secondary_body_area_codes"])
                    )
                )
                for row in self.neck_rows
                if row["decision"] == "KEEP"
            )
        )

    def test_lower_back_existing_alternatives_have_runtime_guards(self) -> None:
        self.assertEqual(len(self.lower_back_rows), 12)
        self.assertTrue(
            all(
                row["decision"] == "KEEP"
                and row["area_specific_safety_review_code"] == "LOWER_BACK_CONDITIONALLY_RETAINED"
                and row["target_pain_area_overlap"] is False
                and "NEUTRAL_SPINE_REQUIRED" in row["area_specific_safety_guard_codes"]
                for row in self.lower_back_rows
            )
        )

    def test_generalized_recovery_and_stop_policy_is_separate(self) -> None:
        policy = json.loads(
            (ROOT / "data/normalized/generalized_recovery_stop_policy_v2_0_2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(policy["scope"], "GENERALIZED_OR_MULTI_AREA_DISCOMFORT")
        decisions = {item["decision_code"] for item in policy["decision_policy"]}
        self.assertIn("GENERALIZED_ACTIVE_RECOVERY_OR_REST", decisions)
        self.assertIn("STOP_EXERCISE_NO_ALTERNATIVE", decisions)
        self.assertIn("NO_OVERLAP_WITH_ANY_REPORTED_AREA", policy["recovery_pool_guards"])

    def test_normalized_output_is_discomfort_only_and_condition_scoped(self) -> None:
        self.assertEqual(len(self.normalized_rows), 157)
        self.assertTrue(all(row["reason_code"] == "DISCOMFORT" for row in self.normalized_rows))
        self.assertTrue(
            all(
                row["pain_discomfort_area_code"] and row["condition_code"] in {"NRS_1_3", "NRS_4_6"}
                for row in self.normalized_rows
            )
        )
        self.assertTrue(
            all(
                row["source_load_pain_area_overlap"] is True
                and row["target_pain_area_overlap"] is False
                and row["direction_code"] == "A_TO_B"
                for row in self.normalized_rows
            )
        )

    def test_final_catalog_and_variant_integrity_pass(self) -> None:
        self.assertTrue(all(self.report["invariants"].values()))
        self.assertEqual(self.report["integrity_metrics"]["self_reference_count"], 0)
        self.assertEqual(self.report["integrity_metrics"]["missing_exercise_reference_count"], 0)
        self.assertEqual(self.report["integrity_metrics"]["excluded_exercise_reference_count"], 0)
        self.assertEqual(self.report["integrity_metrics"]["variant_relation_overlap_count"], 0)
        self.assertEqual(self.report["integrity_metrics"]["secondary_variant_alternative_count"], 0)
        self.assertFalse(self.report["production_eligible"])

    def test_reclassification_preserves_the_legacy_relation_identity(self) -> None:
        dispositions = [row for row in self.review_rows if row["decision"] == "REMOVE_RECLASSIFY"]
        self.assertEqual(len({row["legacy_relation_identity"] for row in dispositions}), 122)
        self.assertEqual(
            Counter(row["reclassification_code"] for row in dispositions),
            Counter(
                {
                    "RECLASSIFY_VARIANT": 19,
                    "RECLASSIFY_CONTEXT_DEFAULT": 34,
                    "RECLASSIFY_DIFFICULTY_VARIANT": 6,
                    "RECLASSIFY_VARIANT_OR_EXERCISE_IDENTITY": 10,
                    "REMOVE_TARGET_RETAINS_DISCOMFORT_AREA": 52,
                    "REMOVE_NECK_TARGET_SAFETY_UNCONFIRMED": 1,
                }
            ),
        )

    def test_regeneration_is_deterministic_in_a_temporary_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = review.build(output_dir=Path(directory))
            self.assertEqual(result["counts"], self.report["counts"])
            generated = read_jsonl(
                Path(directory) / "normalized_discomfort_alternatives_v2_0_2.jsonl"
            )
            self.assertEqual(generated, self.normalized_rows)

            with (Path(directory) / "pain_alternative_review_result_v2_0_2.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(len(csv_rows), 279)


if __name__ == "__main__":
    unittest.main()
