import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate_v2_0_2_integrated_catalog.py"
SPEC = importlib.util.spec_from_file_location("validate_v2_0_2_integrated_catalog", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class IntegratedCatalogValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reports = MODULE.build_reports()

    def test_catalog_and_variant_counts_cover_all_record_types(self):
        counts = self.reports["reference"]["catalog_counts_by_record_type"]
        self.assertEqual(counts["REPRESENTATIVE"], 76)
        self.assertEqual(counts["PRIMARY_VARIANT"], 15)
        self.assertEqual(counts.get("SECONDARY_VARIANT", 0), 0)
        self.assertEqual(counts["SEPARATE_EXERCISE"], 79)
        self.assertEqual(len(self.reports["variant_review"]), 15)

    def test_safe_variant_catalog_rows_do_not_store_pain_conditions(self):
        catalog = MODULE.read_jsonl(MODULE.FINAL / "catalog/exercises.jsonl")
        safe = [
            row
            for row in catalog
            if row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT"
        ]
        self.assertEqual(len(safe), 75)
        self.assertTrue(all(row.get("pain_discomfort_area_code") is None for row in safe))
        self.assertTrue(all("condition_codes" not in row for row in safe))
        self.assertFalse(
            any(
                row["issue_code"] == "SAFE_VARIANT_CATALOG_CONTRACT_VIOLATION"
                for row in self.reports["reference"]["auto_fixable"]
            )
        )

    def test_variants_have_independent_bindings_and_batch_approval(self):
        for row in self.reports["variant_review"]:
            self.assertEqual(row["review_classification"], "DOMAIN_APPROVED")
            self.assertTrue(row["production_eligible"])
            self.assertIn(
                "INDEPENDENT_VARIANT_SAFETY_REVIEW_REQUIRED", row["safety_review_reason_codes"]
            )
            self.assertIn(
                "INDEPENDENT_VARIANT_FITT_REVIEW_REQUIRED", row["fitt_review_reason_codes"]
            )
            expected = (
                ["BEGINNER", "INTERMEDIATE"]
                if row["difficulty_code"] == "BEGINNER"
                else ["INTERMEDIATE"]
            )
            self.assertEqual(row["assigned_experience_levels"], expected)
            self.assertEqual(row["safety_mapping_status_code"], "DOMAIN_APPROVED")
            self.assertEqual(row["fitt_mapping_status_code"], "DOMAIN_APPROVED")

    def test_reference_report_has_no_remaining_automatic_reference_repairs(self):
        codes = {row["issue_code"] for row in self.reports["reference"]["auto_fixable"]}
        self.assertFalse(codes)
        self.assertTrue(self.reports["reference"]["invariants"]["no_orphan_reference"])
        self.assertTrue(self.reports["reference"]["invariants"]["no_legacy_code_residue"])

    def test_alternative_report_rejects_catalog_orphans_but_not_pain_semantics(self):
        metrics = self.reports["alternative"]["metrics"]
        self.assertEqual(metrics["resolved_relation_count"], 1104)
        self.assertEqual(metrics["target_outside_catalog_unique_exercise_count"], 0)
        self.assertEqual(metrics["target_outside_catalog_count"], 0)
        self.assertEqual(metrics["non_pain_reason_relation_count"], 0)
        self.assertEqual(metrics["difficulty_policy_added_relation_count"], 29)
        self.assertEqual(metrics["difficulty_policy_removed_relation_count"], 0)
        self.assertTrue(self.reports["alternative"]["invariants"]["pain_response_relations_only"])
        self.assertTrue(
            self.reports["alternative"]["invariants"]["all_source_targets_in_integrated_catalog"]
        )

    def test_media_goal_metrics_are_record_scoped(self):
        metrics = self.reports["media_goal"]["metrics"]
        self.assertEqual(metrics["catalog_record_count"], 170)
        self.assertEqual(metrics["valid_media_mapping_count"], 170)
        self.assertEqual(metrics["missing_explicit_media_state_count"], 0)
        self.assertEqual(metrics["goal_linked_catalog_record_count"], 170)

    def test_writes_all_requested_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            MODULE.write_reports(output, self.reports)
            expected = {
                "reference_integrity_report_v2_0_2.json",
                "variant_safety_fitt_review_batch_v2_0_2.jsonl",
                "variant_safety_fitt_review_batch_v2_0_2.csv",
                "media_goal_integrity_report_v2_0_2.json",
                "alternative_integrity_report_v2_0_2.json",
                "alternative_difficulty_policy_review_batch_v2_0_2.jsonl",
                "alternative_difficulty_policy_review_batch_v2_0_2.csv",
                "production_blockers_v2_0_2.json",
            }
            self.assertEqual({path.name for path in output.iterdir()}, expected)
            blockers = json.loads(
                (output / "production_blockers_v2_0_2.json").read_text(encoding="utf-8")
            )
            self.assertEqual(blockers["status"], "APPROVED")
            self.assertEqual(blockers["blocker_count"], 0)


if __name__ == "__main__":
    unittest.main()
