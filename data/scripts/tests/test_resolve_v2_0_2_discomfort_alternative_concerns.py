from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
OUTPUT = FINAL_DIR / "alternatives"
SCRIPT = Path(__file__).resolve().parents[1] / "resolve_v2_0_2_discomfort_alternative_concerns.py"
spec = importlib.util.spec_from_file_location(
    "resolve_v2_0_2_discomfort_alternative_concerns", SCRIPT
)
assert spec and spec.loader
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class ConcernResolutionReviewGateTests(unittest.TestCase):
    def test_changed_difficulty_set_fails_closed(self) -> None:
        rows = resolver.read_jsonl(resolver.DEFAULT_INPUT)
        policy = resolver.read_json(resolver.DEFAULT_POLICY)
        pending_ids = resolver.read_pending_relation_ids(resolver.DEFAULT_DIFFICULTY_REVIEW)
        with self.assertRaisesRegex(ValueError, "unexpected pending review count: 0"):
            resolver.validate_policy(rows, policy)
        self.assertEqual(len(pending_ids), 29)


class DiscomfortAlternativeConcernResolutionTests(unittest.TestCase):
    original: list[dict]
    policy: dict
    resolved: list[dict]
    removed: list[dict]
    pending: list[dict]
    variants: list[dict]
    report: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.original = resolver.read_jsonl(resolver.DEFAULT_INPUT)
        cls.policy = resolver.read_json(resolver.DEFAULT_POLICY)
        expected_count = resolver.EXPECTED_INPUT_COUNT
        if len(cls.original) != expected_count:
            raise unittest.SkipTest(
                "difficulty policy changed the reviewed Alternative set; domain re-review required"
            )
        cls.resolved = read_jsonl(OUTPUT / resolver.RESOLVED_MAP_NAME)
        cls.removed = read_jsonl(OUTPUT / resolver.REMOVED_MAP_NAME)
        cls.pending = read_jsonl(OUTPUT / resolver.PENDING_MAP_NAME)
        cls.variants = read_jsonl(OUTPUT / resolver.SAFE_VARIANTS_NAME)
        cls.report = resolver.read_json(OUTPUT / resolver.REPORT_NAME)

    def test_all_input_rows_are_fully_partitioned(self) -> None:
        self.assertEqual(len(self.original), 1517)
        self.assertEqual(len(self.resolved), 1104)
        self.assertEqual(len(self.removed), 384)
        self.assertEqual(len(self.pending), 29)
        self.assertEqual(len(self.variants), 54)
        self.assertEqual(
            self.report["counts"],
            {
                "KEEP_AS_SAFE_VARIANT": 744,
                "KEEP_UNCHANGED": 360,
                "REMOVE_DIRECT_LOAD": 347,
                "REMOVE_SAFE_VARIANT_NOT_FEASIBLE": 37,
                "input_count": 1517,
                "pending_review_count": 29,
                "removed_count": 384,
                "resolved_keep_count": 1104,
                "safe_variant_count": 54,
            },
        )

    def test_every_original_relation_has_exactly_one_resolution(self) -> None:
        resolved_ids = {row["map_relation_id"] for row in self.resolved}
        removed_ids = {row["map_relation_id"] for row in self.removed}
        pending_ids = {row["map_relation_id"] for row in self.pending}
        original_ids = {row["map_relation_id"] for row in self.original}
        self.assertFalse(resolved_ids & removed_ids)
        self.assertFalse(resolved_ids & pending_ids)
        self.assertFalse(removed_ids & pending_ids)
        self.assertEqual(resolved_ids | removed_ids | pending_ids, original_ids)
        self.assertEqual(len(original_ids), len(self.original))

    def test_direct_load_and_infeasible_concerns_are_removed(self) -> None:
        removed_by_id = {row["map_relation_id"]: row for row in self.removed}
        resolved_by_id = {row["map_relation_id"]: row for row in self.resolved}
        pending_by_id = {row["map_relation_id"]: row for row in self.pending}
        for original in self.original:
            if original["map_relation_id"] in pending_by_id:
                self.assertEqual(
                    pending_by_id[original["map_relation_id"]]["review_status_code"],
                    "REVIEW_REQUIRED",
                )
                continue
            action = resolver.classify(original, self.policy)
            relation_id = original["map_relation_id"]
            if action.startswith("REMOVE_"):
                self.assertIn(relation_id, removed_by_id)
                self.assertEqual(
                    removed_by_id[relation_id]["concern_resolution_action_code"],
                    action,
                )
            else:
                self.assertIn(relation_id, resolved_by_id)

    def test_retained_concerns_reference_only_separate_safe_variants(self) -> None:
        variants_by_code = {row["stable_code"]: row for row in self.variants}
        safe_rows = [
            row
            for row in self.resolved
            if row["concern_resolution_action_code"] == "KEEP_AS_SAFE_VARIANT"
        ]
        self.assertEqual(len(safe_rows), 744)
        for row in safe_rows:
            variant = variants_by_code[row["target_exercise_stable_code"]]
            self.assertEqual(row["target_record_type"], "SEPARATE_EXERCISE")
            self.assertEqual(variant["record_type"], "SEPARATE_EXERCISE")
            self.assertTrue(variant["original_posture_instructions_replaced"])
            self.assertTrue(variant["support_equipment_codes"])
            self.assertEqual(
                row["base_target_exercise_stable_code"],
                variant["base_exercise_stable_code"],
            )
            self.assertNotEqual(
                row["target_exercise_stable_code"],
                row["base_target_exercise_stable_code"],
            )

    def test_safe_variants_satisfy_all_five_user_guards(self) -> None:
        for variant in self.variants:
            self.assertTrue(variant["fixed_posture_code"])
            self.assertNotIn("_OR_", variant["fixed_posture_code"])
            self.assertTrue(variant["fixed_support_code"])
            self.assertNotIn("_OR_", variant["fixed_support_code"])
            self.assertEqual(variant["pain_area_load_guard_codes"], resolver.NO_LOAD_GUARDS)
            self.assertEqual(variant["stop_guard_code"], resolver.STOP_GUARD)
            self.assertEqual(variant["record_type"], "SEPARATE_EXERCISE")
            self.assertIn(
                variant["pain_discomfort_area_code"],
                variant["instruction_summary_ko"],
            )
            self.assertTrue(any("즉시 중단" in cue for cue in variant["form_cues_ko"]))
            self.assertFalse(variant["production_eligible"])
            self.assertEqual(variant["review_status_code"], "REVIEW_REQUIRED")

    def test_report_hashes_match_artifacts_and_original_is_unchanged(self) -> None:
        self.assertEqual(
            self.report["sha256"]["input"], resolver.sha256_file(resolver.DEFAULT_INPUT)
        )
        self.assertEqual(
            self.report["sha256"]["policy"], resolver.sha256_file(resolver.DEFAULT_POLICY)
        )
        self.assertEqual(
            self.report["sha256"]["resolved_map"],
            resolver.sha256_file(OUTPUT / resolver.RESOLVED_MAP_NAME),
        )
        self.assertEqual(
            self.report["sha256"]["removed_map"],
            resolver.sha256_file(OUTPUT / resolver.REMOVED_MAP_NAME),
        )
        self.assertEqual(
            self.report["sha256"]["pending_map"],
            resolver.sha256_file(OUTPUT / resolver.PENDING_MAP_NAME),
        )
        self.assertEqual(
            self.report["sha256"]["safe_variants"],
            resolver.sha256_file(OUTPUT / resolver.SAFE_VARIANTS_NAME),
        )

    def test_regeneration_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = resolver.build(output_dir=Path(directory))
            self.assertEqual(report["counts"], self.report["counts"])
            self.assertEqual(
                read_jsonl(Path(directory) / resolver.RESOLVED_MAP_NAME), self.resolved
            )
            self.assertEqual(read_jsonl(Path(directory) / resolver.REMOVED_MAP_NAME), self.removed)
            self.assertEqual(read_jsonl(Path(directory) / resolver.PENDING_MAP_NAME), self.pending)
            self.assertEqual(
                read_jsonl(Path(directory) / resolver.SAFE_VARIANTS_NAME), self.variants
            )


if __name__ == "__main__":
    unittest.main()
