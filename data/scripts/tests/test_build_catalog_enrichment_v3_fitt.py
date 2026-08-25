from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_catalog_enrichment_v3_fitt.py"
spec = importlib.util.spec_from_file_location("build_catalog_enrichment_v3_fitt", SCRIPT)
assert spec and spec.loader
fitt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fitt)


class CatalogEnrichmentFittTests(unittest.TestCase):
    def test_enrich_row_preserves_name_en_and_sets_fitt_timing_and_intensity(self) -> None:
        template = {
            "fitt_template_id": "FITT-COMPOUND-HINGE-V1",
            "training_category": "COMPOUND_STRENGTH",
            "default_sets": "3",
            "default_reps": "8-12",
            "default_work_seconds": "",
            "default_rest_seconds": "90",
            "default_transition_seconds": "",
            "default_intensity": "MODERATE",
            "fitt_basis": "reviewed template",
        }
        result = fitt.enrich_row(
            {"exercise_id": "NEX-000001", "fitt_status": "REVIEW_REQUIRED"},
            {"suggested_movement_pattern": "HINGE", "current_training_type": "STRENGTH"},
            {template["fitt_template_id"]: template},
            "barbell deadlift",
        )
        self.assertEqual(result["name_en"], "barbell deadlift")
        self.assertEqual(result["timing_mode_code"], "REPS")
        self.assertEqual(result["intensity_level"], "MODERATE")
        self.assertEqual(result["fitt_status"], "APPROVED")
        self.assertEqual(result["fitt_template_id"], "FITT-COMPOUND-HINGE-V1")


if __name__ == "__main__":
    unittest.main()
