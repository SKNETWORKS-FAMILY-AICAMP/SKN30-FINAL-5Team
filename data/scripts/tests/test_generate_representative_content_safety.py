from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_representative_content_safety.py"
spec = importlib.util.spec_from_file_location("generate_representative_content_safety", SCRIPT)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class RepresentativeContentSafetyTests(unittest.TestCase):
    def test_uses_primary_body_area_and_resets_generated_review_status(self) -> None:
        row = {
            "representative_id": "REX-000001",
            "representative_name_ko": "고관절 스트레칭",
            "movement_pattern": "MOBILITY_STRETCH",
            "training_type": "MOBILITY",
            "target_muscle": "MOBILITY",
            "primary_body_area_codes": '["HIP"]',
            "secondary_body_area_codes": '["KNEE"]',
            "difficulty": "BEGINNER",
            "exercise_family": "MOBILITY",
            "source_ids": "NEX-000001",
            "taxonomy_review_status": "TAXONOMY_APPROVED",
            "review_required_codes": "",
        }
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path = directory / "taxonomy.csv"
            output_dir = directory / "output"
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)

            generator.build(input_path, output_dir)

            with (output_dir / "representative_exercise_content.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                content = next(csv.DictReader(handle))
            with (output_dir / "exercise_safety_rules.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                safety = next(csv.DictReader(handle))

            self.assertIn("고관절 주변", content["short_description"])
            self.assertEqual(content["target_muscle"], "MOBILITY")
            self.assertEqual(content["content_review_status"], "GENERATED_CONTENT_REVIEW_REQUIRED")
            self.assertEqual(safety["safety_review_status"], "DOMAIN_REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
