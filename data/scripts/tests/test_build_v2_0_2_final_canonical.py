import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
REVIEW_DIR = (
    ROOT / "data/validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0"
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class FinalCanonicalCatalogTests(unittest.TestCase):
    def test_merge_report_is_valid(self) -> None:
        report = json.loads(
            (FINAL_DIR / "merge_validation_report.json").read_text(encoding="utf-8")
        )
        self.assertTrue(report["validation"]["valid"])
        self.assertEqual(report["validation"]["active_canonical_stable_code_duplicates"], 0)
        self.assertEqual(report["validation"]["legacy_mapping_missing_count"], 0)
        self.assertEqual(report["validation"]["pending_review_required_count"], 0)

    def test_active_canonical_stable_codes_are_unique(self) -> None:
        rows = read_jsonl(FINAL_DIR / "canonical_exercises_v2_final.jsonl")
        stable_codes = [row["stable_code"] for row in rows]
        self.assertEqual(len(rows), 136)
        self.assertEqual(len(stable_codes), len(set(stable_codes)))
        self.assertNotIn(
            "leg_up_hamstring_stretch_mobility_stretch_bodyweight",
            stable_codes,
        )

    def test_user_selected_variant_candidate_is_collected(self) -> None:
        rows = read_jsonl(FINAL_DIR / "variant_relationship_candidates_v2_final.jsonl")
        candidate = next(
            row for row in rows if row["candidate_pair_id"] == "ERP-20260828-REX000105"
        )
        self.assertEqual(len(rows), 80)
        self.assertEqual(candidate["left_record_id"], "REX-000105")
        self.assertEqual(candidate["right_record_id"], "REX-000006")
        self.assertEqual(candidate["candidate_relation_code"], "PRIMARY_VARIANT")
        self.assertEqual(candidate["decision_source"], "USER_DIRECT_REVIEW")
        self.assertEqual(candidate["review_status_code"], "REVIEW_REQUIRED")

    def test_direct_review_decisions_are_recorded(self) -> None:
        rows = read_jsonl(REVIEW_DIR / "human_review_queue.jsonl")
        by_pair = {row["candidate_pair_id"]: row for row in rows}
        self.assertEqual(len(rows), 332)
        self.assertEqual(
            by_pair["ERP-20260827-00200"]["human_final_decision_code"],
            "SEPARATE_EXERCISE",
        )
        self.assertEqual(
            by_pair["ERP-20260827-00549"]["human_final_decision_code"],
            "SEPARATE_EXERCISE",
        )
        self.assertEqual(
            by_pair["ERP-20260827-00450"]["human_final_decision_code"],
            "SAME_EXERCISE",
        )
        self.assertEqual(by_pair["ERP-20260827-00450"]["human_final_retained_side"], "left")

    def test_all_original_source_ids_have_mapping(self) -> None:
        mapping = read_jsonl(FINAL_DIR / "legacy_consolidation_mapping_v2_final.jsonl")
        self.assertEqual(len(mapping), 310)
        source_keys = [row["source_key"] for row in mapping]
        self.assertEqual(len(source_keys), len(set(source_keys)))
        self.assertTrue(all(row["final_stable_code"] for row in mapping))

    def test_csv_and_jsonl_canonical_counts_match(self) -> None:
        jsonl_rows = read_jsonl(FINAL_DIR / "canonical_exercises_v2_final.jsonl")
        with (FINAL_DIR / "canonical_exercises_v2_final.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            csv_rows = list(csv.DictReader(handle))
        self.assertEqual(len(jsonl_rows), len(csv_rows))
        self.assertEqual(
            {row["stable_code"] for row in jsonl_rows},
            {row["stable_code"] for row in csv_rows},
        )


if __name__ == "__main__":
    unittest.main()
