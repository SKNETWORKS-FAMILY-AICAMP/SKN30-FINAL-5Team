from __future__ import annotations

import csv
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
AUDIT_DIR = FINAL_DIR / "audit"
SCRIPT = Path(__file__).resolve().parents[1] / "review_v2_0_2_canonical_fields.py"
spec = importlib.util.spec_from_file_location("review_v2_0_2_canonical_fields", SCRIPT)
assert spec and spec.loader
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class CanonicalFieldReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_jsonl(AUDIT_DIR / "canonical_exercises_v2_0_2_refined.jsonl")
        cls.by_id = {row["representative_exercise_id"]: row for row in cls.rows}
        cls.variant_candidates = read_jsonl(
            AUDIT_DIR / "representative_variant_candidates_v2_0_2.jsonl"
        )
        cls.variant_by_id = {
            row["representative_exercise_id"]: row for row in cls.variant_candidates
        }
        cls.report = json.loads(
            (AUDIT_DIR / "canonical_field_validation_report_v2_0_2.json").read_text(
                encoding="utf-8"
            )
        )
        cls.changes = read_jsonl(AUDIT_DIR / "field_corrections_v2_0_2.jsonl")
        cls.migrations = read_jsonl(AUDIT_DIR / "alias_migration_v2_0_2.jsonl")
        cls.data_reviews = read_jsonl(AUDIT_DIR / "canonical_data_first_pass_review_v2_0_2.jsonl")
        cls.deletions = read_jsonl(AUDIT_DIR / "canonical_deletions_v2_0_2.jsonl")
        cls.equipment_reviews = read_jsonl(
            AUDIT_DIR / "equipment_only_same_method_review_v2_0_2.jsonl"
        )

    def test_summary_counts_and_hard_validation(self) -> None:
        self.assertEqual(len(self.rows), 131)
        self.assertEqual(self.report["representative_count"], 131)
        self.assertEqual(self.report["variant_candidate_count"], 1)
        self.assertEqual(self.report["variant_candidate_review_required_count"], 1)
        self.assertEqual(self.report["variant_candidate_data_review_required_count"], 1)
        self.assertEqual(self.report["field_correction_count"], 220)
        self.assertEqual(self.report["review_required_count"], 131)
        self.assertEqual(self.report["data_review_required_count"], 31)
        self.assertEqual(self.report["first_pass_data_review_count"], 36)
        self.assertEqual(self.report["deleted_representative_count"], 4)
        self.assertEqual(self.report["ambiguous_review_required_count"], 1)
        self.assertEqual(self.report["identity_review_required_count"], 1)
        self.assertEqual(self.report["migration_history_error_count"], 0)
        self.assertFalse(self.report["validation"]["hard_validation_passed"])
        self.assertEqual(self.report["validation"]["logical_conflict_count"], 9)

    def test_taxonomy_and_identity_are_unique(self) -> None:
        self.assertEqual(len({row["representative_exercise_id"] for row in self.rows}), 131)
        self.assertEqual(len({row["stable_code"] for row in self.rows}), 131)
        self.assertEqual(len({row["display_name_ko"] for row in self.rows}), 131)
        self.assertTrue(all(row["difficulty_code"] in review.VALID_DIFFICULTY for row in self.rows))
        self.assertNotIn("ADVANCED", {row["difficulty_code"] for row in self.rows})
        self.assertTrue(
            all(
                not review.FORBIDDEN_V2_EQUIPMENT.intersection(row["equipment_codes"])
                for row in self.rows
            )
        )

    def test_deterministic_field_corrections(self) -> None:
        self.assertEqual(self.by_id["REX-000002"]["name_en"], "quadruped quadriceps stretch")
        self.assertEqual(
            self.by_id["REX-000002"]["display_name_ko"], "네발기기 대퇴사두근 스트레칭"
        )
        self.assertEqual(
            self.by_id["REX-000002"]["stable_code"],
            "quadruped_quadriceps_stretch_mobility_stretch_bodyweight",
        )
        self.assertEqual(self.by_id["REX-000104"]["difficulty_code"], "INTERMEDIATE")
        self.assertEqual(self.by_id["REX-000010"]["difficulty_code"], "BEGINNER")
        self.assertEqual(self.by_id["REX-000009"]["difficulty_code"], "BEGINNER")
        self.assertEqual(self.by_id["REX-000013"]["difficulty_code"], "INTERMEDIATE")
        self.assertEqual(self.by_id["REX-000023"]["difficulty_code"], "INTERMEDIATE")
        self.assertTrue(
            all(
                row["difficulty_code"] == "INTERMEDIATE"
                for row in self.rows + self.variant_candidates
                if "CABLE_MACHINE" in row["equipment_codes"]
            )
        )
        self.assertEqual(self.variant_by_id["REX-000105"]["equipment_codes"], ["CABLE_MACHINE"])
        self.assertEqual(
            self.variant_by_id["REX-000105"]["variant_parent_representative_exercise_id"],
            "REX-000006",
        )
        self.assertEqual(self.variant_by_id["REX-000105"]["canonical_status"], "VARIANT_CANDIDATE")
        self.assertIn("로프", self.variant_by_id["REX-000105"]["setup_condition_ko"])
        self.assertEqual(self.by_id["REX-000109"]["difficulty_code"], "INTERMEDIATE")
        self.assertEqual(self.by_id["REX-000120"]["difficulty_code"], "INTERMEDIATE")
        self.assertEqual(self.by_id["REX-000120"]["timing_mode_code"], "REPS")
        self.assertIn("벤치", self.by_id["REX-000112"]["instruction_summary_ko"])
        self.assertIn("이마", self.by_id["REX-000112"]["form_cues_ko"][0])
        self.assertEqual(self.by_id["REX-000121"]["name_en"], "bicycle crunch")
        self.assertEqual(self.by_id["REX-000121"]["display_name_ko"], "바이시클 크런치")
        self.assertEqual(self.by_id["REX-000121"]["equipment_codes"], ["BODYWEIGHT"])
        self.assertEqual(
            self.by_id["REX-000121"]["stable_code"],
            "bicycle_crunch_core_brace_bodyweight",
        )
        self.assertEqual(self.by_id["REX-000125"]["difficulty_code"], "INTERMEDIATE")
        self.assertEqual(
            self.by_id["REX-000111"]["name_en"], "dumbbell over bench reverse wrist curl"
        )
        self.assertEqual(self.by_id["REX-000114"]["equipment_codes"], ["BODYWEIGHT"])
        self.assertEqual(self.by_id["REX-000120"]["equipment_codes"], ["HOUSEHOLD_WEIGHT"])
        self.assertEqual(self.by_id["REX-000131"]["equipment_codes"], ["EZ_BAR"])
        self.assertEqual(
            self.by_id["REX-000133"]["primary_body_area_codes"],
            ["SHOULDER", "UPPER_BACK"],
        )
        self.assertEqual(
            self.by_id["REX-000134"]["primary_body_area_codes"],
            ["UPPER_BACK", "SHOULDER"],
        )
        self.assertEqual(self.by_id["REX-000134"]["difficulty_code"], "INTERMEDIATE")
        self.assertEqual(self.by_id["REX-000137"]["location_codes"], ["GYM"])
        self.assertEqual(self.by_id["REX-000001"]["location_codes"], ["HOME"])

    def test_support_and_timing_fields_are_materialized(self) -> None:
        for representative_id in [
            "REX-000006",
            "REX-000008",
            "REX-000020",
            "REX-000027",
            "REX-000037",
            "REX-000049",
            "REX-000057",
            "REX-000064",
            "REX-000080",
            "REX-000103",
            "REX-000104",
            "REX-000111",
            "REX-000114",
            "REX-000119",
            "REX-000123",
            "REX-000126",
            "REX-000127",
            "REX-000128",
            "REX-000130",
            "REX-000131",
            "REX-000134",
            "REX-000137",
        ]:
            self.assertTrue(self.by_id[representative_id]["setup_condition_ko"])
        for row in self.rows:
            expected = (
                ["WARMUP", "COOLDOWN"] if row["training_type_code"] == "MOBILITY" else ["MAIN"]
            )
            self.assertEqual(row["phase_codes"], expected)
            self.assertEqual(row["timing_phase_review_status"], "APPROVED_FROM_POLICY")

    def test_ambiguous_rows_remain_review_targets(self) -> None:
        expected = {
            "REX-000121": "SOURCE_MEDIA_EQUIPMENT_IDENTITY_REVIEW_REQUIRED",
        }
        for representative_id, code in expected.items():
            row = self.by_id[representative_id]
            self.assertTrue(row["review_required"])
            self.assertIn(code, row["review_required_codes"])
        self.assertEqual(
            {row["representative_exercise_id"] for row in self.deletions},
            {"REX-000107", "REX-000116", "REX-000129", "REX-000132"},
        )
        for representative_id in {"REX-000107", "REX-000116", "REX-000129", "REX-000132"}:
            self.assertNotIn(representative_id, self.by_id)

    def test_first_pass_review_and_equipment_only_candidates(self) -> None:
        self.assertEqual(len(self.data_reviews), 36)
        self.assertEqual(self.data_reviews[-1]["representative_exercise_id"], "REX-000137")
        confirmed = [
            row
            for row in self.equipment_reviews
            if row["equipment_only_status"].startswith("CONFIRMED")
        ]
        self.assertEqual(len(confirmed), 1)
        self.assertTrue(
            any(
                row["left_representative_exercise_id"] == "REX-000006"
                and row["right_representative_exercise_id"] == "REX-000105"
                for row in confirmed
            )
        )
        calf_pair = next(
            row for row in self.equipment_reviews if row["pair_id"] == "REX-000016__REX-000124"
        )
        self.assertEqual(calf_pair["equipment_only_status"], "SEPARATE_EXERCISE_RETAINED")

    def test_source_provenance_and_alias_history_are_preserved(self) -> None:
        row = self.by_id["REX-000111"]
        self.assertEqual(row["source_track"], "gymvisual")
        self.assertEqual(row["source_identity"], "0368")
        self.assertEqual(row["legacy_source_key"], "v1:NEX-000045")
        self.assertEqual(row["source_name_en"], "dumbbell over bench revers wrist curl")
        self.assertEqual(row["license_id"], "MIT")
        self.assertTrue(row["source_url"])
        aliases = {
            (item["representative_exercise_id"], item["field_name"], item["alias_value"])
            for item in self.migrations
        }
        self.assertIn(
            ("REX-000111", "name_en", "dumbbell over bench revers wrist curl"),
            aliases,
        )
        self.assertIn(
            ("REX-000112", "display_name_ko", "덤벨 레터럴 레이즈"),
            aliases,
        )
        self.assertIn(
            (
                "REX-000002",
                "stable_code",
                "all_fours_squat_stretch_mobility_stretch_bodyweight",
            ),
            aliases,
        )
        self.assertTrue(
            any(
                row["representative_exercise_id"] == "REX-000129"
                and row["alias_type"] == "CANONICAL_DELETION"
                for row in self.migrations
            )
        )
        self.assertTrue(
            any(
                row["representative_exercise_id"] == "REX-000105"
                and row["migration_target"] == "REX-000105"
                for row in self.migrations
            )
        )
        stable_before = {
            row["representative_exercise_id"]: {
                change["stable_code_before"]
                for change in self.changes
                if change["representative_exercise_id"] == row["representative_exercise_id"]
            }
            for row in self.rows
        }
        self.assertTrue(all(len(values) == 1 for values in stable_before.values() if values))
        self.assertTrue(all(row["production_eligible"] is False for row in self.rows))
        self.assertTrue(all(row["production_eligible"] is False for row in self.variant_candidates))

    def test_csv_and_jsonl_counts_match(self) -> None:
        with (AUDIT_DIR / "canonical_exercises_v2_0_2_refined.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            csv_rows = list(csv.DictReader(handle))
        self.assertEqual(len(csv_rows), len(self.rows))
        self.assertEqual(
            {row["stable_code"] for row in csv_rows}, {row["stable_code"] for row in self.rows}
        )


if __name__ == "__main__":
    unittest.main()
