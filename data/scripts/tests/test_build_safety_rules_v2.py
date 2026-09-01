from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_safety_rules_v2.py"
spec = importlib.util.spec_from_file_location("build_safety_rules_v2", SCRIPT)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class SafetyRulesV2MigrationTests(unittest.TestCase):
    def test_build_preserves_reference_and_covers_catalog(self) -> None:
        source_before = hashlib.sha256(migration.DEFAULT_SOURCE_RULES.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            summary = migration.build(output_dir=Path(directory))
            output = Path(directory)
            self.assertEqual(summary["mapped_exercises"], 208)
            self.assertGreater(summary["new_rules"], 0)

            rules = [
                json.loads(line)
                for line in (output / "safety_rules_v2.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            ]
            self.assertTrue(all(tuple(rule) == migration.RULE_FIELDS for rule in rules))
            self.assertTrue(
                all(
                    rule["pain_score_policy_version"] == migration.PAIN_SCORE_POLICY_VERSION
                    for rule in rules
                )
            )
            mild_caution = next(
                rule
                for rule in rules
                if rule["migration_status"] == "NEW_PATTERN_RULE_REVIEW_REQUIRED"
                and rule["pain_level"] == "MILD"
                and rule["action"] == "CAUTION"
            )
            self.assertEqual(
                [
                    (
                        decision["minimum_score"],
                        decision["maximum_score"],
                        decision["decision_code"],
                    )
                    for decision in mild_caution["pain_score_decisions"]
                ],
                [(1, 3, "LOAD_REDUCED"), (4, 6, "SKIP_AFFECTED_AREA"), (7, 10, "STOP_EXERCISE")],
            )
            moderate_exclude = next(
                rule
                for rule in rules
                if rule["migration_status"] == "NEW_PATTERN_RULE_REVIEW_REQUIRED"
                and rule["pain_level"] == "MODERATE-SEVERE"
                and rule["action"] == "EXCLUDE"
            )
            self.assertEqual(
                [
                    (
                        decision["minimum_score"],
                        decision["maximum_score"],
                        decision["decision_code"],
                    )
                    for decision in moderate_exclude["pain_score_decisions"]
                ],
                [
                    (1, 3, "LOAD_REDUCED"),
                    (4, 6, "SKIP_AFFECTED_AREA"),
                    (7, 10, "STOP_EXERCISE"),
                ],
            )
            self.assertTrue(
                all(
                    rule["service_action_policy_version"] == "pain-intensity-action-v2"
                    and rule["red_flag_override_code"] == "STOP_AND_SEEK_HELP"
                    for rule in rules
                )
            )
            legacy_source_rules = [
                json.loads(line)
                for line in migration.DEFAULT_SOURCE_RULES.read_text(encoding="utf-8").splitlines()
                if line
            ]
            legacy_movement_rules = [
                row for row in legacy_source_rules if row["rule_scope"] == "MOVEMENT_PATTERN"
            ]
            self.assertEqual(summary["legacy_rules"], len(legacy_movement_rules))
            self.assertEqual(len(rules), len(legacy_movement_rules) + summary["new_rules"])
            self.assertTrue(
                all(
                    row["migration_status"] != "LEGACY_EXERCISE_UNMAPPED_REVIEW_REQUIRED"
                    for row in rules
                )
            )
            self.assertEqual(
                {
                    row["source_rule_id"]
                    for row in rules
                    if row["migration_status"] != "NEW_PATTERN_RULE_REVIEW_REQUIRED"
                    and row["action"] == "EXCLUDE"
                },
                {
                    f"LEGACY-RULE-{index:04d}"
                    for index, row in enumerate(legacy_source_rules, 1)
                    if row["rule_scope"] == "MOVEMENT_PATTERN"
                    if row["effect_code"] == "EXCLUDE"
                },
            )

            with (output / "exercise_safety_mapping_v2.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                mapping_reader = csv.DictReader(handle)
                self.assertEqual(tuple(mapping_reader.fieldnames or ()), migration.MAPPING_FIELDS)
                mappings = list(mapping_reader)
            with (output / "safety_migration_review_log.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                review_reader = csv.DictReader(handle)
                self.assertEqual(tuple(review_reader.fieldnames or ()), migration.REVIEW_FIELDS)
                reviews = list(review_reader)
            with (output / "safety_rule_template_v2.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                template_rows = list(csv.DictReader(handle))
            self.assertEqual(
                {row["field_name"] for row in template_rows}, set(migration.RULE_FIELDS)
            )
            catalog = migration.load_catalog_and_patterns(
                migration.DEFAULT_CATALOG, migration.DEFAULT_PATTERN_REVIEW
            )
            review_source = migration.read_csv(
                migration.DEFAULT_PATTERN_REVIEW,
                (
                    "exercise_id",
                    "suggested_movement_pattern",
                    "review_required",
                ),
            )
            self.assertTrue(all(row["review_required"] == "NO" for row in review_source))
            self.assertEqual(
                {row["exercise_id"] for row in mappings}, {row["exercise_id"] for row in catalog}
            )
            self.assertEqual(
                {row["movement_pattern"] for row in mappings},
                {row["movement_pattern"] for row in catalog},
            )
            self.assertEqual(len(reviews), len(catalog))
            self.assertTrue(all(row["missing_rule"] == "NO" for row in reviews))
            self.assertTrue(all(row["new_rule_created"] == "YES" for row in reviews))
            self.assertTrue(all(row["review_required"] == "YES" for row in reviews))
        self.assertEqual(source_before, migration.SOURCE_RULES_SHA256)

    def test_rejects_legacy_reference_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed_source = Path(directory) / "safety_rules.jsonl"
            changed_source.write_bytes(migration.DEFAULT_SOURCE_RULES.read_bytes() + b"\n")
            with self.assertRaisesRegex(migration.MigrationError, "hash changed"):
                migration.read_legacy_rules(changed_source)

    def test_direct_load_rule_has_all_three_score_decisions(self) -> None:
        self.assertEqual(
            [
                (row["minimum_score"], row["maximum_score"], row["decision_code"])
                for row in migration.pain_score_decisions("MILD-SEVERE", "EXCLUDE")
            ],
            [
                (1, 3, "LOAD_REDUCED"),
                (4, 6, "SKIP_AFFECTED_AREA"),
                (7, 10, "STOP_EXERCISE"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
