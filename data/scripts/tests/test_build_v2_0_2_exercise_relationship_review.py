from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_2_exercise_relationship_review.py"
spec = importlib.util.spec_from_file_location("build_v2_0_2_exercise_relationship_review", SCRIPT)
assert spec and spec.loader
relationship = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relationship)


class ExerciseRelationshipReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rows = relationship.read_csv(relationship.DEFAULT_INPUT)
        canonical, aliases = relationship.validate_input(rows)
        cls.canonical = {
            row["stable_code"]: relationship.compact_record(row, "EXERCISE") for row in canonical
        }
        cls.aliases = {
            row["v1_exercise_id"]: relationship.compact_record(row, "V1_ALIAS") for row in aliases
        }

    def test_combined_catalog_shape_is_preserved(self) -> None:
        self.assertEqual(len(self.canonical), 102)
        self.assertEqual(len(self.aliases), 114)
        self.assertEqual(
            len(self.canonical), len({row["stable_code"] for row in self.canonical.values()})
        )

    def test_same_stable_code_does_not_hide_equipment_variant(self) -> None:
        alias = self.aliases["NEX-000032"]
        target = self.canonical["barbell_deadlift_hip_dominant_barbell"]
        relation = relationship.classify_alias_pair(alias, target)
        self.assertEqual(relation[0], "PRIMARY_VARIANT")
        self.assertIn("EQUIPMENT", relation[2])

    def test_exact_duplicate_aliases_are_absent_after_source_deduplication(self) -> None:
        self.assertNotIn("NEX-000001", self.aliases)
        self.assertEqual(
            sum(
                1
                for alias in self.aliases.values()
                if alias["normalized_name"] == "barbell deadlift"
            ),
            0,
        )

    def test_generated_batch_is_pending_and_non_production(self) -> None:
        with tempfile.TemporaryDirectory(dir=relationship.ROOT) as temporary_dir:
            temporary = Path(temporary_dir)
            relationship.build(
                relationship.DEFAULT_INPUT,
                relationship.DEFAULT_ALTERNATIVES,
                temporary / "profile",
                temporary / "batch",
                "test-batch",
            )
            rows = relationship.read_csv(temporary / "batch" / "review_batch.csv")
        self.assertEqual(len(rows), 603)
        self.assertTrue(
            all(
                row["review_decision"] == "PENDING"
                and row["review_status_code"] == "REVIEW_REQUIRED"
                and row["production_eligible"] == "false"
                for row in rows
            )
        )


if __name__ == "__main__":
    unittest.main()
