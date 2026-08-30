import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL = ROOT / "data/generated/exercise-catalog-v2.0.2-final"
SCRIPT = Path(__file__).resolve().parents[1] / "sync_v2_0_2_integrated_reference_artifacts.py"
SPEC = importlib.util.spec_from_file_location("sync_v2_0_2_integrated_reference_artifacts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class MechanicalReferenceRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_jsonl(FINAL / "catalog/exercises.jsonl")
        cls.bindings = read_jsonl(FINAL / "audit/reference_binding_status_v2_0_2.jsonl")
        cls.media = MODULE.read_csv(FINAL / "media/media_assets_v2_0_2.csv")
        cls.registry = json.loads((FINAL / "audit/stable_code_registry_v2.json").read_text())
        cls.report = json.loads(
            (FINAL / "audit/integrity/auto_reference_repair_report_v2_0_2.json").read_text()
        )

    def test_safe_variants_are_general_pool_records_with_conditioned_relations(self) -> None:
        safe = [
            row
            for row in self.catalog
            if row.get("alternative_relation_code") == "PAIN_AREA_NO_LOAD_SAFE_VARIANT"
        ]
        self.assertEqual(len(safe), 75)
        self.assertTrue(all(row["record_type"] == "SEPARATE_EXERCISE" for row in safe))
        self.assertTrue(all(row["alternative_only"] is False for row in safe))
        self.assertTrue(all(row["general_pool_included"] for row in safe))
        self.assertTrue(all("condition_codes" not in row for row in safe))
        self.assertTrue(all(row.get("pain_discomfort_area_code") is None for row in safe))
        self.assertTrue(all(row["production_eligible"] is True for row in safe))
        self.assertTrue(all(row["fitt_template_ids_by_experience"] for row in safe))
        self.assertTrue(all(row["safety_mapping_status_code"] == "DOMAIN_APPROVED" for row in safe))

    def test_registry_bindings_and_media_are_record_complete(self) -> None:
        codes = {row["stable_code"] for row in self.catalog}
        self.assertEqual(codes, {row["stable_code"] for row in self.registry["records"]})
        self.assertEqual(codes, {row["stable_code"] for row in self.bindings})
        self.assertEqual(codes, {row["stable_code"] for row in self.media})
        self.assertEqual(
            Counter(row["media_state_code"] for row in self.media),
            {"AVAILABLE": 68, "UNAVAILABLE": 102},
        )

    def test_media_source_linkage_fields_are_catalog_bound(self) -> None:
        required = {
            "source_origin_code",
            "source_track",
            "source_identity",
            "source_identity_validation",
        }
        self.assertTrue(required.issubset(self.media[0]))
        allowed = {"KSPO", "WGER", "GYMVISUAL", "PAIN_ALTERNATIVE_POLICY", "UNAVAILABLE"}
        self.assertTrue(all(row["source_origin_code"] in allowed for row in self.media))
        gymvisual = [row for row in self.media if row["source_origin_code"] == "GYMVISUAL"]
        self.assertEqual(len(gymvisual), 87)
        self.assertTrue(all(row["source_identity"].isdigit() for row in gymvisual))
        self.assertTrue(
            all(row["source_identity_validation"] == "VALID_NUMERIC" for row in gymvisual)
        )
        pain = [row for row in self.media if row["source_origin_code"] == "PAIN_ALTERNATIVE_POLICY"]
        self.assertEqual(len(pain), 75)
        self.assertTrue(all(row["record_source_identity"].startswith("DVAR-") for row in pain))
        self.assertEqual(
            Counter(row["media_source_origin_code"] for row in pain),
            {"GYMVISUAL": 74, "KSPO": 1},
        )
        self.assertTrue(
            all(row["source_identity"] != row["record_source_identity"] for row in pain)
        )
        self.assertEqual(
            self.report["media_source_feature_version"], "v2.0.2-media-source-linkage-v1.0.0"
        )

    def test_independent_source_materialization_is_recorded(self) -> None:
        self.assertFalse(self.report["production_eligible"])
        self.assertEqual(self.report["catalog"]["integrated_record_count"], 170)
        self.assertEqual(self.report["stable_code_registry"]["removed_prior_active_code_count"], 57)
        self.assertEqual(self.report["media"]["removed_orphan_media_id"], 19)


if __name__ == "__main__":
    unittest.main()
