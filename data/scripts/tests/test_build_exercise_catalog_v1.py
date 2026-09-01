from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_exercise_catalog_v1.py"
spec = importlib.util.spec_from_file_location("build_exercise_catalog_v1", SCRIPT)
assert spec and spec.loader
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def row(index: int, **changes: str) -> dict[str, str]:
    value = {column: "" for column in catalog.ENRICHMENT_COLUMNS}
    value.update(
        {
            "exercise_id": f"NEX-{index:06d}",
            "exercise_name_ko": f"운동 {index}",
            "name_en": f"Exercise {index}",
            "body_focus_code": "CHEST",
            "primary_body_area_codes": '["CHEST"]',
            "secondary_body_area_codes": '["SHOULDER"]',
            "body_focus_basis": "source target",
            "body_area_basis": "source target",
            "name_ko_basis": "source label",
            "difficulty_basis": "review pending",
            "fitt_basis": "review pending",
            "name_ko_status": "REVIEW_REQUIRED",
            "body_focus_status": "REVIEW_REQUIRED",
            "body_area_status": "REVIEW_REQUIRED",
            "difficulty_status": "REVIEW_REQUIRED",
            "fitt_status": "REVIEW_REQUIRED",
            "catalog_exposure_code": "PRIMARY",
            "canonical_exercise_id": f"NEX-{index:06d}",
            "variant_relation_code": "NONE",
            "variant_basis": "no source version pair",
        }
    )
    value.update(changes)
    return value


class CatalogEnrichmentTests(unittest.TestCase):
    def write_input(self, directory: Path, rows: list[dict[str, str]]) -> Path:
        path = directory / "catalog_enrichment_v2.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=catalog.ENRICHMENT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def valid_rows(self) -> list[dict[str, str]]:
        return [row(index) for index in range(1, 209)]

    def test_review_required_never_promotes_to_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path = self.write_input(directory, self.valid_rows())
            output_path = directory / "catalog.csv"
            statuses = catalog.build(input_path, output_path)
            self.assertEqual(statuses, {"REVIEW_REQUIRED": 208})
            with output_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), catalog.CATALOG_COLUMNS)
                output_rows = list(reader)
            self.assertEqual(
                {item["production_status"] for item in output_rows}, {"REVIEW_REQUIRED"}
            )
            self.assertEqual(
                [item["source_name_en"] for item in output_rows],
                [f"Exercise {index}" for index in range(1, 209)],
            )

    def test_rejects_area_json_overlap_and_bad_focus(self) -> None:
        rows = self.valid_rows()
        rows[0]["secondary_body_area_codes"] = '["CHEST"]'
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "overlap"):
                catalog.build_catalog(self.write_input(Path(temp), rows))

    def test_rejects_invalid_media_variant_relation(self) -> None:
        rows = self.valid_rows()
        rows[0]["catalog_exposure_code"] = "MEDIA_VARIANT"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "MEDIA_VARIANT relation is invalid"):
                catalog.build_catalog(self.write_input(Path(temp), rows))
        rows = self.valid_rows()
        rows[0]["body_focus_code"] = "CHEST,BACK"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "single machine code"):
                catalog.build_catalog(self.write_input(Path(temp), rows))

    def test_approved_requires_evidence_and_deterministic_output(self) -> None:
        rows = self.valid_rows()
        rows[0]["name_ko_status"] = "APPROVED"
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path = self.write_input(directory, rows)
            with self.assertRaisesRegex(ValueError, "lacks basis, reviewer, or reviewed_at"):
                catalog.build_catalog(input_path)
        rows = self.valid_rows()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path = self.write_input(directory, rows)
            first, second = directory / "first.csv", directory / "second.csv"
            catalog.build(input_path, first)
            catalog.build(input_path, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_rejects_missing_name_en(self) -> None:
        rows = self.valid_rows()
        rows[0]["name_en"] = ""
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "name_en is missing"):
                catalog.build_catalog(self.write_input(Path(temp), rows))

    def test_allows_inclusive_fitt_ranges_and_rejects_descending_range(self) -> None:
        rows = self.valid_rows()
        rows[0].update(
            {
                "timing_mode_code": "REPS",
                "default_sets": "2-3",
                "default_reps": "8-12",
                "default_rest_seconds": "60-90",
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            catalog.build_catalog(self.write_input(Path(temp), rows))
        rows[0]["default_reps"] = "12-8"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "range is descending"):
                catalog.build_catalog(self.write_input(Path(temp), rows))


if __name__ == "__main__":
    unittest.main()
