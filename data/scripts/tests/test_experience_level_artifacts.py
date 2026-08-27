from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_script(name: str, filename: str):
    script = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("build_experience_level_artifacts", "build_experience_level_artifacts.py")
validator = load_script(
    "validate_experience_level_artifacts", "validate_experience_level_artifacts.py"
)


class ExperienceLevelArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "artifact"
        cls.report = builder.build(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def _jsonl(self, relative: str) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in (self.root / relative).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_difficulty_is_resolved_and_suitability_field_is_absent(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        self.assertEqual(len(catalog), 102)
        self.assertEqual({row["difficulty_status"] for row in catalog}, {"APPROVED"})
        self.assertEqual(
            {
                difficulty: sum(row["difficulty_code"] == difficulty for row in catalog)
                for difficulty in ("BEGINNER", "INTERMEDIATE")
            },
            {"BEGINNER": 85, "INTERMEDIATE": 17},
        )
        self.assertTrue(all("beginner_suitable" not in row for row in catalog))
        for path in self.root.rglob("*"):
            if path.is_file() and path.name != "validation_report.json":
                self.assertNotIn("beginner_suitable", path.read_text(encoding="utf-8"))

    def test_prescription_matrix_and_natural_keys(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        enrichment = self._jsonl("catalog/catalog_enrichment.jsonl")
        profiles = self._jsonl("prescriptions/prescription_profiles.jsonl")
        result = validator.validate_prescription_records(
            profiles,
            {row["stable_code"]: row for row in catalog},
            {row["exercise_stable_code"]: row for row in enrichment},
        )
        self.assertGreater(result["BEGINNER:BEGINNER"], 0)
        self.assertGreater(result["BEGINNER:INTERMEDIATE"], 0)
        self.assertGreater(result["INTERMEDIATE:INTERMEDIATE"], 0)
        self.assertNotIn("INTERMEDIATE:BEGINNER", result)
        self.assertEqual(
            validator.prescription_exercise_coverage(
                profiles,
                {row["stable_code"]: row for row in catalog},
            ),
            {
                "BEGINNER:BEGINNER": 85,
                "BEGINNER:INTERMEDIATE": 85,
                "INTERMEDIATE:INTERMEDIATE": 17,
            },
        )

    def test_v1_catalog_is_fully_mapped_without_duplicate_v2_exercises(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        aliases = self._jsonl("catalog/v1_exercise_aliases.jsonl")
        self.assertEqual(len(aliases), 208)
        self.assertEqual(len({row["v1_exercise_id"] for row in aliases}), 208)
        self.assertEqual(
            {row["exercise_stable_code"] for row in aliases},
            {row["stable_code"] for row in catalog},
        )
        self.assertTrue(all(row["alias_only"] is True for row in aliases))
        self.assertTrue(all("v1_difficulty_code" not in row for row in aliases))

    def test_v1_and_v2_are_available_in_one_combined_file(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        enrichment = self._jsonl("catalog/catalog_enrichment.jsonl")
        aliases = self._jsonl("catalog/v1_exercise_aliases.jsonl")
        combined = self._jsonl("catalog/exercises_v1_v2.jsonl")
        self.assertEqual(len(combined), 310)
        self.assertEqual(
            {
                record_type: sum(row["record_type"] == record_type for row in combined)
                for record_type in ("EXERCISE", "V1_ALIAS")
            },
            {"EXERCISE": 102, "V1_ALIAS": 208},
        )
        self.assertEqual(
            validator.validate_combined_exercise_records(combined, catalog, enrichment, aliases),
            {"EXERCISE": 102, "V1_ALIAS": 208},
        )
        self.assertTrue(
            all(
                field in row
                for row in combined
                if row["record_type"] == "V1_ALIAS"
                for field in (
                    "v1_timing_mode_code",
                    "v1_default_sets",
                    "v1_default_reps",
                    "v1_default_work_seconds",
                    "v1_default_rest_seconds",
                    "v1_default_transition_seconds",
                    "v1_intensity_level",
                )
            )
        )
        self.assertTrue(all("beginner_suitable" not in row for row in combined))
        self.assertTrue(all(row["review_required"] is True for row in combined))
        self.assertTrue(
            all(row["artifact_review_status_code"] == "REVIEW_REQUIRED" for row in combined)
        )
        for row in combined:
            if row["record_type"] == "EXERCISE":
                mapping = next(
                    item
                    for item in enrichment
                    if item["exercise_stable_code"] == row["stable_code"]
                )
                self.assertEqual(
                    row["allowed_experience_level_codes"],
                    mapping["allowed_experience_level_codes"],
                )
                self.assertEqual(
                    row["fitt_template_ids_by_experience"],
                    mapping["fitt_template_ids_by_experience"],
                )
        csv_path = self.root / "catalog/exercises_v1_v2.csv"
        self.assertEqual(validator._csv_record_count(csv_path), 310)
        self.assertEqual(
            csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")[0],
            "record_type",
        )

    def test_selection_policy_supports_intermediate_and_downshift(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        profiles = self._jsonl("prescriptions/prescription_profiles.jsonl")
        normal = validator.select_profile(catalog, profiles, "INTERMEDIATE")
        self.assertEqual(normal["experience_level_code"], "INTERMEDIATE")
        self.assertEqual(normal["exercise_difficulty_code"], "BEGINNER")
        downshift = validator.select_profile(catalog, profiles, "INTERMEDIATE", downshift=True)
        self.assertEqual(downshift["experience_level_code"], "BEGINNER")
        self.assertEqual(downshift["exercise_difficulty_code"], "BEGINNER")

    def test_alternatives_are_referenced_unique_and_policy_safe(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        alternatives = self._jsonl("alternatives/alternatives.jsonl")
        result = validator.validate_alternative_records(
            alternatives, {row["stable_code"]: row for row in catalog}
        )
        self.assertGreater(sum(result.values()), 0)

    def test_version_manifest_and_runtime_bundle_are_consistent(self) -> None:
        result = validator.validate_directory(self.root)
        self.assertTrue(result["version_consistent"])
        self.assertEqual(result["legacy_field_occurrences"], 0)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(self.report["manifest_sha256"], result["manifest_sha256"])
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            path = self.root / entry["path"]
            self.assertEqual(entry["bytes"], path.stat().st_size)
            self.assertTrue(entry["sha256"])

    def test_invalid_difficulty_code_is_rejected(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        catalog[0]["difficulty_code"] = "EXPERT"
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_catalog_records(catalog, production_eligible=False)

    def test_unresolved_difficulty_is_fail_closed_for_production(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        catalog[0]["difficulty_status"] = "REVIEW_REQUIRED"
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_catalog_records(catalog, production_eligible=True)

    def test_unknown_alternative_reference_is_rejected(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        alternatives = self._jsonl("alternatives/alternatives.jsonl")
        alternatives[0]["alternative_exercise_stable_code"] = "unknown_exercise"
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_alternative_records(
                alternatives, {row["stable_code"]: row for row in catalog}
            )

    def test_alternative_duplicate_is_rejected(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        alternatives = self._jsonl("alternatives/alternatives.jsonl")
        alternatives.append(dict(alternatives[0]))
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_alternative_records(
                alternatives, {row["stable_code"]: row for row in catalog}
            )

    def test_builder_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            second = Path(directory) / "artifact"
            builder.build(second)
            first_files = sorted(
                path.relative_to(self.root) for path in self.root.rglob("*") if path.is_file()
            )
            second_files = sorted(
                path.relative_to(second) for path in second.rglob("*") if path.is_file()
            )
            self.assertEqual(first_files, second_files)
            for relative in first_files:
                if relative.name == "validation_report.json":
                    continue
                self.assertEqual(
                    (self.root / relative).read_bytes(),
                    (second / relative).read_bytes(),
                    str(relative),
                )

    def test_fail_closed_for_invalid_difficulty_and_duplicate_profile(self) -> None:
        catalog = self._jsonl("catalog/exercises.jsonl")
        catalog[0]["difficulty_code"] = ""
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_catalog_records(catalog, production_eligible=True)

        profiles = self._jsonl("prescriptions/prescription_profiles.jsonl")
        profiles.append(dict(profiles[0]))
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_prescription_records(
                profiles,
                {row["stable_code"]: row for row in self._jsonl("catalog/exercises.jsonl")},
                {
                    row["exercise_stable_code"]: row
                    for row in self._jsonl("catalog/catalog_enrichment.jsonl")
                },
            )


if __name__ == "__main__":
    unittest.main()
