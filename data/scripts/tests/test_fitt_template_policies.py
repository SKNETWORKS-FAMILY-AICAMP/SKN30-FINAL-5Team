from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def load_script(name: str, filename: str):
    script = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


beginner = load_script("build_fitt_template_v1", "build_fitt_template_v1.py")
catalog = load_script(
    "build_catalog_enrichment_v3_fitt", "build_catalog_enrichment_v3_fitt.py"
)
intermediate = load_script(
    "build_fitt_template_intermediate_v1", "build_fitt_template_intermediate_v1.py"
)


class FittTemplatePolicyTests(unittest.TestCase):
    def test_beginner_defaults_and_units(self) -> None:
        by_id = {row["fitt_template_id"]: row for row in beginner.TEMPLATES}
        self.assertNotIn("FITT-BODYWEIGHT-BEGINNER-V1", by_id)
        self.assertEqual(
            (by_id["FITT-COMPOUND-SQUAT-V1"]["default_sets"], by_id["FITT-COMPOUND-SQUAT-V1"]["default_reps"]),
            ("2", "10"),
        )
        self.assertEqual(by_id["FITT-COMPOUND-LUNGE-V1"]["prescription_unit"], "REPS_PER_SIDE")
        self.assertEqual(by_id["FITT-CORE-ISOMETRIC-V1"]["prescription_unit"], "SECONDS")
        self.assertEqual(by_id["FITT-MOBILITY-V1"]["default_work_seconds"], "15")

    def test_exercise_specific_mapping_keeps_equipment_out_of_exercise_group(self) -> None:
        self.assertEqual(catalog.choose_template("NEX-000074", "PUSH")[0], "FITT-COMPOUND-PUSH-V1")
        self.assertEqual(catalog.choose_template("NEX-000118", "ISOLATION")[0], "FITT-ISOLATION-STRENGTH-V1")
        self.assertEqual(catalog.choose_template("NEX-000162", "HINGE")[0], "FITT-COMPOUND-HINGE-V1")
        self.assertEqual(catalog.choose_template("NEX-000208", "HINGE")[0], "FITT-HINGE-POWER-V1")
        self.assertEqual(catalog.choose_template("NEX-000113", "PUSH")[0], "FITT-ISOMETRIC-STRENGTH-V1")
        self.assertEqual(catalog.choose_template("NEX-000208", "HINGE")[1], "NONE")
        self.assertEqual(catalog.choose_template("NEX-000113", "PUSH")[1], "NONE")

    def test_intermediate_core_dynamic_uses_10_to_15_reps(self) -> None:
        source = next(row for row in beginner.TEMPLATES if row["fitt_template_id"] == "FITT-CORE-DYNAMIC-V1")
        result = intermediate.intermediate_values(source)
        self.assertEqual(result["default_sets"], "3")
        self.assertEqual((result["min_reps"], result["max_reps"]), ("10", "15"))


if __name__ == "__main__":
    unittest.main()
