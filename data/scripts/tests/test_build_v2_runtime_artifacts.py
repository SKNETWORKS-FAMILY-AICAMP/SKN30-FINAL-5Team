from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.modules.catalog.schemas import (
    AlternativeManifest,
    CatalogManifest,
    SafetyRuleManifest,
)

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_runtime_artifacts.py"
spec = importlib.util.spec_from_file_location("build_v2_runtime_artifacts", SCRIPT)
assert spec and spec.loader
runtime_artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_artifacts)


class V2RuntimeArtifactTests(unittest.TestCase):
    def test_materializes_validated_runtime_artifacts_without_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = runtime_artifacts.build(output)

            self.assertEqual(report["representative_records"], 102)
            self.assertEqual(report["alternative_records"], 585)
            self.assertEqual(report["safety_rule_records"], 394)
            self.assertFalse(report["production_eligible"])

            catalog_manifest = json.loads(
                (output / "catalog_manifest.json").read_text(encoding="utf-8")
            )
            alternative_manifest = json.loads(
                (output / "alternatives_manifest.json").read_text(encoding="utf-8")
            )
            safety_manifest = json.loads(
                (output / "safety_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(catalog_manifest["review"]["status"], "DOMAIN_APPROVED")
            self.assertEqual(catalog_manifest["review"]["review_method_code"], "AGENT_ONLY")
            self.assertFalse(catalog_manifest["review"]["production_eligible"])
            self.assertEqual(catalog_manifest["catalog_version"]["status_code"], "DRAFT")
            self.assertEqual(alternative_manifest["summary"]["alternative_records"], 585)
            self.assertEqual(safety_manifest["summary"]["rule_records"], 394)
            self.assertEqual(
                alternative_manifest["alternative_set_version"]["status_code"], "DRAFT"
            )
            self.assertEqual(safety_manifest["rule_set_version"]["status_code"], "DRAFT")

            representative_payloads = [
                json.loads(line)
                for line in (output / "representative_exercises.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertTrue(all("beginner_suitable" not in row for row in representative_payloads))

            CatalogManifest.model_validate_json((output / "catalog_manifest.json").read_bytes())
            AlternativeManifest.model_validate_json(
                (output / "alternatives_manifest.json").read_bytes()
            )
            SafetyRuleManifest.model_validate_json((output / "safety_manifest.json").read_bytes())
            for filename, model, expected_count in (
                ("representative_exercises.jsonl", runtime_artifacts.V2ExerciseRecord, 102),
                ("alternatives.jsonl", runtime_artifacts.V2ExerciseAlternativeRecord, 585),
                ("safety_rules.jsonl", runtime_artifacts.V2ExerciseSafetyRuleRecord, 394),
            ):
                rows = [
                    model.model_validate_json(line)
                    for line in (output / filename).read_bytes().splitlines()
                    if line.strip()
                ]
                self.assertEqual(len(rows), expected_count)
                self.assertTrue(
                    all(
                        row.production_eligible is False
                        for row in rows
                        if hasattr(row, "production_eligible")
                    )
                )


class V2PainSelectorProjectionTests(unittest.TestCase):
    """The reviewed pain area and NRS band must survive materialization."""

    def test_discomfort_relations_keep_area_and_band(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            runtime_artifacts.build(output)
            rows = [
                json.loads(line)
                for line in (output / "alternatives.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        discomfort = [row for row in rows if row["reason_code"] == "DISCOMFORT"]
        other = [row for row in rows if row["reason_code"] != "DISCOMFORT"]
        selectors = (
            "pain_discomfort_area_code",
            "condition_code",
            "service_action_code",
            "target_strategy_code",
        )

        self.assertEqual(len(discomfort), 520)
        self.assertTrue(
            all(row[name] is not None for row in discomfort for name in selectors),
            "every discomfort relation carries the full selector set",
        )
        self.assertTrue(
            all(row[name] is None for row in other for name in selectors),
            "equipment and location relations leave the selectors NULL",
        )
        expected_action = {"NRS_1_3": "LOAD_REDUCED", "NRS_4_6": "SKIP_AFFECTED_AREA"}
        self.assertTrue(
            all(
                row["service_action_code"] == expected_action[row["condition_code"]]
                for row in discomfort
            ),
            "the service action matches the band the relation was approved under",
        )

    def test_relations_are_unique_under_the_database_key(self) -> None:
        """uq_exercise_alternatives_relation includes the band and the area."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            runtime_artifacts.build(output)
            rows = [
                json.loads(line)
                for line in (output / "alternatives.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        keys = {
            (
                row["alternative_set_version_code"],
                row["source_exercise_stable_code"],
                row["alternative_exercise_stable_code"],
                row["reason_code"],
                row["goal_preservation_code"],
                row["rule_version"],
                row["condition_code"],
                row["pain_discomfort_area_code"],
            )
            for row in rows
        }

        self.assertEqual(len(keys), len(rows))


if __name__ == "__main__":
    unittest.main()
