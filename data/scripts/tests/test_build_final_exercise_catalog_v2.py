from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_final_exercise_catalog_v2.py"
spec = importlib.util.spec_from_file_location("build_final_exercise_catalog_v2", SCRIPT)
assert spec and spec.loader
final_catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_catalog)


class FinalExerciseCatalogV2Tests(unittest.TestCase):
    def test_builds_final_named_artifacts_with_inactive_bridge_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = final_catalog.build(output)

            self.assertEqual(report["representative_count"], 102)
            self.assertEqual(report["taxonomy_approved_representative_count"], 102)
            self.assertEqual(report["representatives_with_approved_met"], 102)
            self.assertEqual(report["representatives_with_met_review_required"], 0)
            self.assertEqual(report["representatives_with_approved_difficulty"], 102)
            self.assertEqual(report["representatives_with_difficulty_review_required"], 0)
            self.assertEqual(report["representatives_with_approved_body_areas"], 102)
            self.assertEqual(report["representatives_with_approved_target_muscle"], 102)
            self.assertEqual(report["representatives_with_target_muscle_review_required"], 0)
            self.assertEqual(report["active_safety_bridge_rule_count"], 0)
            self.assertEqual(report["approved_media_asset_count"], 0)
            self.assertEqual(report["media_storage_backend"], "AWS_MANAGED")
            self.assertFalse(report["media_binary_local_storage"])
            self.assertFalse(report["media_local_db_storage"])
            self.assertEqual(len(report["artifact_sha256"]), 7)
            self.assertEqual(report["stable_code_count"], 102)
            self.assertTrue(report["runtime_json_eligible"])
            self.assertEqual(report["runtime_json_blockers"], {})
            self.assertEqual(len(report["source_artifact_sha256"]), 2)

            with (output / "representative_exercises_v2_final.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                representatives = list(csv.DictReader(handle))
            self.assertEqual(len(representatives), 102)
            self.assertTrue(
                all(
                    not row["exercise_family_code"].startswith("REVIEW_REQUIRED_")
                    for row in representatives
                )
            )
            self.assertTrue(
                all(row["taxonomy_review_status"] == "TAXONOMY_APPROVED" for row in representatives)
            )
            self.assertEqual(
                next(
                    row
                    for row in representatives
                    if row["representative_exercise_id"] == "REX-000056"
                )["taxonomy_reviewed_at"],
                final_catalog.APPROVAL_DATE,
            )
            self.assertEqual(
                next(
                    row
                    for row in representatives
                    if row["representative_exercise_id"] == "REX-000066"
                )["met_status"],
                "DOMAIN_APPROVED",
            )
            deadlift = next(
                row for row in representatives if row["representative_exercise_id"] == "REX-000004"
            )
            self.assertTrue(deadlift["source_name"])
            self.assertEqual(deadlift["body_focus_code"], "GLUTES")
            self.assertEqual(deadlift["primary_body_area_codes"], '["HIP"]')
            self.assertEqual(deadlift["secondary_body_area_codes"], '["KNEE","LOWER_BACK"]')
            self.assertEqual(deadlift["difficulty_code"], "INTERMEDIATE")
            self.assertEqual(deadlift["difficulty_status"], "APPROVED")
            self.assertNotIn("REVIEW_REQUIRED", {row["difficulty_code"] for row in representatives})
            self.assertEqual(
                next(
                    row
                    for row in representatives
                    if row["representative_exercise_id"] == "REX-000049"
                )["equipment_codes"],
                "MACHINE",
            )
            self.assertEqual(
                next(
                    row
                    for row in representatives
                    if row["representative_exercise_id"] == "REX-000094"
                )["equipment_codes"],
                "STRETCH_STRAP",
            )
            self.assertTrue(
                all(
                    not ({"BENCH", "CHAIR"} & set(row["equipment_codes"].split("|")))
                    for row in representatives
                )
            )
            self.assertTrue(
                all(
                    set(row["location_codes"].split("|")) <= {"HOME", "GYM"}
                    for row in representatives
                )
            )
            self.assertTrue(
                all(row["source_track"] in {"wger", "kspo", "gymvisual"} for row in representatives)
            )
            self.assertTrue(
                next(
                    row
                    for row in representatives
                    if row["representative_exercise_id"] == "REX-000008"
                )["setup_condition_ko"]
            )

            with (output / "representative_exercise_taxonomy_v2_final.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                taxonomy = list(csv.DictReader(handle))
            deadlift_taxonomy = next(
                row for row in taxonomy if row["representative_id"] == "REX-000004"
            )
            self.assertEqual(deadlift_taxonomy["target_muscle"], "GLUTES")
            self.assertEqual(deadlift_taxonomy["difficulty"], "INTERMEDIATE")

            with (output / "safety_rules_v2_final.jsonl").open(encoding="utf-8") as handle:
                rules = [json.loads(line) for line in handle if line.strip()]
            self.assertTrue(all(rule["activation_status"] != "ACTIVE" for rule in rules))
            self.assertTrue(
                all(
                    rule["pain_score_policy_version"] == "pain-intensity-action-v2"
                    and "body_area_code" in rule
                    and "effect_code" in rule
                    and "reason_code" in rule
                    and "movement_pattern_code" in rule
                    and rule["pain_score_decisions"][-1]["decision_code"] == "STOP_EXERCISE"
                    and rule["pain_score_decisions"][-1]["minimum_score"] == 7
                    and rule["pain_score_decisions"][-1]["maximum_score"] == 10
                    for rule in rules
                )
            )
            self.assertTrue(
                all(
                    rule["activation_status"] == "INACTIVE_PENDING_DOMAIN_APPROVAL"
                    for rule in rules
                    if rule["migration_status"] == "NEW_PATTERN_RULE_REVIEW_REQUIRED"
                )
            )

            with (output / "representative_exercise_safety_mapping_v2_final.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                mappings = list(csv.DictReader(handle))
            self.assertEqual(
                {row["representative_exercise_id"] for row in mappings},
                {row["representative_exercise_id"] for row in representatives},
            )
            self.assertTrue(all(row["activation_status"] != "ACTIVE" for row in mappings))

            with (output / "exercise_alternatives_v2_final.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                alternatives = list(csv.DictReader(handle))
            self.assertEqual(len(alternatives), report["alternative_relationship_count"])
            strap_to_bodyweight = next(
                row
                for row in alternatives
                if row["source_representative_exercise_id"] == "REX-000094"
                and row["alternative_representative_exercise_id"] == "REX-000034"
            )
            self.assertEqual(strap_to_bodyweight["reason_code"], "EQUIPMENT")
            self.assertEqual(strap_to_bodyweight["goal_preservation_code"], "MOBILITY_HAMSTRING")
            self.assertEqual(strap_to_bodyweight["difficulty_delta"], "0")
            self.assertEqual(strap_to_bodyweight["allowed_equipment_codes"], "BODYWEIGHT")
            self.assertEqual(strap_to_bodyweight["production_eligible"], "false")
            discomfort = [row for row in alternatives if row["reason_code"] == "DISCOMFORT"]
            self.assertEqual(len(discomfort), 520)
            score_band_counts = {}
            for row in discomfort:
                metadata = json.loads(row["source_metadata"])
                score_band = row["pain_score_min"] + "-" + row["pain_score_max"]
                score_band_counts[score_band] = score_band_counts.get(score_band, 0) + 1
                alternative_primary = set(json.loads(row["alternative_primary_body_area_codes"]))
                alternative_areas = alternative_primary | set(
                    json.loads(row["alternative_secondary_body_area_codes"])
                )
                if score_band == "1-3":
                    self.assertEqual(row["service_action_code"], "LOAD_REDUCED")
                    self.assertEqual(row["goal_preservation_code"], "SAME_GOAL")
                else:
                    self.assertEqual(score_band, "4-6")
                    self.assertEqual(row["service_action_code"], "SKIP_AFFECTED_AREA")
                    self.assertEqual(row["alternative_strategy_code"], "AVOID_PAIN_AREA_ACTIVE_RECOVERY")
                    self.assertNotIn(metadata["body_area_code"], alternative_areas)
            self.assertEqual(score_band_counts, {"1-3": 259, "4-6": 261})
            self.assertTrue(
                all(
                    row["reason_code"] in {"EQUIPMENT", "LOCATION", "DIFFICULTY", "DISCOMFORT"}
                    for row in alternatives
                )
            )
            self.assertTrue(all(row["difficulty_delta"] in {"-1", "0"} for row in alternatives))
            self.assertTrue(all(row["direction_code"] == "A_TO_B" for row in alternatives))
            self.assertTrue(all(row["production_eligible"] == "false" for row in alternatives))
            self.assertTrue(all(row["goal_preservation_code"] for row in alternatives))
            self.assertTrue(
                all(
                    row["source_primary_body_area_codes"]
                    and row["alternative_primary_body_area_codes"]
                    for row in alternatives
                )
            )

            with (output / "media_assets_v2_final.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])

    def test_finalization_rejects_an_unexpected_placeholder_family(self) -> None:
        rows = final_catalog.read_csv(final_catalog.TAXONOMY_PATH)
        rows[0]["exercise_family"] = "REVIEW_REQUIRED_UNEXPECTED"
        with self.assertRaisesRegex(final_catalog.FinalizationError, "resolution set"):
            final_catalog.finalized_taxonomy(rows)

    def test_enrichment_rejects_non_english_body_focus(self) -> None:
        taxonomy = final_catalog.finalized_taxonomy(
            final_catalog.read_csv(final_catalog.TAXONOMY_PATH)
        )
        integrated = final_catalog.read_csv(final_catalog.INTEGRATED_PATH)
        enrichment = final_catalog.read_csv(final_catalog.ENRICHMENT_PATH)
        selected = final_catalog.selected_nex_by_rex(integrated)["REX-000004"]
        target = next(
            row for row in enrichment if row["exercise_id"] == selected["normalized_exercise_id"]
        )
        target["body_focus_code"] = "\ub465\uadfc"
        with self.assertRaisesRegex(final_catalog.FinalizationError, "English machine code"):
            final_catalog.apply_enrichment_to_taxonomy(taxonomy, integrated, enrichment)


if __name__ == "__main__":
    unittest.main()
