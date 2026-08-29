# ruff: noqa: E501
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
SCRIPT = Path(__file__).resolve().parents[1] / "materialize_v2_0_2_variant_catalog.py"
spec = importlib.util.spec_from_file_location("materialize_v2_0_2_variant_catalog", SCRIPT)
assert spec and spec.loader
materialize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materialize)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class MaterializedVariantCatalogTests(unittest.TestCase):
    catalog: list[dict]
    relationships: list[dict]
    report: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_jsonl(FINAL_DIR / "catalog/exercises.jsonl")
        cls.relationships = read_jsonl(FINAL_DIR / "variant_relationship_review_v2_0_2.jsonl")
        cls.report = json.loads(
            (FINAL_DIR / "variant_integrity_report_v2_0_2.json").read_text(encoding="utf-8")
        )
        cls.manifest = json.loads((FINAL_DIR / "manifest.json").read_text(encoding="utf-8"))

    def test_catalog_counts(self) -> None:
        self.assertEqual(len(self.catalog), 170)
        self.assertEqual(
            Counter(row["record_type"] for row in self.catalog),
            Counter({"REPRESENTATIVE": 76, "SEPARATE_EXERCISE": 79, "VARIANT": 15}),
        )
        self.assertEqual(
            Counter(row.get("variant_type_code", "") for row in self.catalog),
            Counter({"": 155, "PRIMARY_VARIANT": 15}),
        )
        self.assertEqual(
            Counter(tuple(row["location_codes"]) for row in self.catalog),
            Counter({("HOME", "GYM"): 135, ("GYM",): 29, ("HOME",): 6}),
        )

    def test_variant_integrity_report_passes(self) -> None:
        self.assertTrue(all(self.report["invariants"].values()))
        self.assertFalse(self.report["production_eligible"])

    def test_user_reviewed_difficulty_policy(self) -> None:
        self.assertEqual(
            self.manifest["difficulty_policy"]["policy_version"],
            "exercise-difficulty-policy-v2.0.2-user-review-2026-08-28",
        )
        self.assertTrue(
            all(row["difficulty_code"] == "INTERMEDIATE" for row in self.catalog if "CABLE_MACHINE" in row["equipment_codes"])
        )

    def test_user_facing_equipment_names_are_normalized(self) -> None:
        for row in self.catalog:
            equipment = set(row.get("equipment_codes", []))
            name = row["name_ko"]
            if "BARBELL" in equipment:
                self.assertTrue(name.startswith("바벨 "), row["exercise_id"])
            if "DUMBBELL" in equipment:
                self.assertTrue(name.startswith("덤벨 "), row["exercise_id"])
            if "MACHINE" in equipment or "CABLE_MACHINE" in equipment:
                self.assertTrue(name.endswith(" 머신") or "스텝밀 머신(" in name, row["exercise_id"])
        stepmill = next(row for row in self.catalog if row["exercise_id"] == "REX-000071")
        self.assertEqual(stepmill["name_ko"], "스텝밀 머신(천국의 계단)")
        self.assertEqual(stepmill["display_name_ko"], stepmill["name_ko"])

    def test_variant_rows_are_independent_and_point_to_representatives(self) -> None:
        reps = {
            row["exercise_id"]: row
            for row in self.catalog
            if row["record_type"] == "REPRESENTATIVE"
        }
        variants = [row for row in self.catalog if row["record_type"] == "VARIANT"]
        self.assertEqual(len(variants), 15)
        self.assertTrue(all(row["is_representative"] is False for row in variants))
        self.assertTrue(all(row["representative_exercise_id"] in reps for row in variants))
        self.assertTrue(
            all(
                row["family_code"] == reps[row["representative_exercise_id"]]["family_code"]
                for row in variants
            )
        )
        self.assertTrue(
            all(row["exercise_id"] != row["representative_exercise_id"] for row in variants)
        )
        self.assertEqual(len({row["stable_code"] for row in self.catalog}), len(self.catalog))

    def test_review_required_candidates_are_not_finalized(self) -> None:
        self.assertEqual(len(self.relationships), 15)
        self.assertEqual(
            Counter(row["variant_type_code"] for row in self.relationships),
            Counter({"PRIMARY_VARIANT": 15}),
        )
        self.assertTrue(
            all(row["review_status_code"] == "DOMAIN_APPROVED" for row in self.relationships)
        )
        self.assertTrue(all(row["relation_finalized"] is False for row in self.relationships))
        self.assertEqual(
            sum(
                row["materialization_status_code"] == "NOT_MATERIALIZED_REVIEW_REQUIRED"
                for row in self.relationships
            ),
            0,
        )

    def test_same_exercise_is_not_materialized_as_variant(self) -> None:
        self.assertTrue(
            all(
                row["variant_type_code"] in {"PRIMARY_VARIANT", "SECONDARY_VARIANT"}
                for row in self.catalog
                if row["record_type"] == "VARIANT"
            )
        )
        self.assertFalse(
            any(row.get("variant_type_code") == "SAME_EXERCISE" for row in self.catalog)
        )

    def test_home_location_is_a_gym_superset_for_supported_equipment(self) -> None:
        self.assertEqual(materialize.locations_for(["MAT"], ["HOME"]), ["HOME", "GYM"])
        self.assertEqual(materialize.locations_for(["RESISTANCE_BAND"], ["HOME"]), ["HOME", "GYM"])
        self.assertEqual(materialize.locations_for(["STABILITY_BALL"], ["HOME"]), ["GYM"])
        self.assertEqual(materialize.locations_for(["STEP_BOX"], ["HOME"]), ["GYM"])


if __name__ == "__main__":
    unittest.main()
