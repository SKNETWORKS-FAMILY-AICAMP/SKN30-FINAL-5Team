from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SCRIPT = SCRIPTS / "build_v2_0_2_content_review_queue.py"
spec = importlib.util.spec_from_file_location("build_v2_0_2_content_review_queue", SCRIPT)
assert spec and spec.loader
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)

FINAL = SCRIPTS.parent / "generated/exercise-catalog-v2.0.2-final"


class ContentReviewQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.summary = queue.build_queue(FINAL)

    def test_queues_every_record_the_backend_cannot_accept(self) -> None:
        self.assertEqual(self.summary["catalog_records"], 170)
        self.assertEqual(
            self.summary["importable_records"] + self.summary["queued_records"],
            self.summary["catalog_records"],
        )

    def test_only_derived_records_are_queued(self) -> None:
        """The representatives are complete once their dropped cues are recovered."""
        queued_types = {row["record_type"] for row in self.rows}

        self.assertEqual(queued_types, {"SEPARATE_EXERCISE", "VARIANT"})

    def test_every_queued_row_names_what_it_is_missing(self) -> None:
        for row in self.rows:
            missing = str(row["missing_fields"]).split("|")
            self.assertTrue(missing, row["stable_code"])
            for field in missing:
                self.assertIn(field, queue._REQUIRED_FIELDS)
                # A queued field is blank so a reviewer fills it in; a recovered
                # one is pre-filled and must not be listed as missing.
                self.assertFalse(row[field], f"{row['stable_code']}:{field}")

    def test_recovered_cues_are_carried_into_the_queue(self) -> None:
        recovered = [row for row in self.rows if row["form_cues_ko"]]

        self.assertTrue(recovered)
        for row in recovered:
            self.assertNotIn("form_cues_ko", str(row["missing_fields"]))
            self.assertTrue(row["recovered_form_cues_source"])

    def test_recovery_only_reports_the_declared_audit_sources(self) -> None:
        """Every recovered cue is traceable to one of the two named artifacts."""
        recovered = queue.recover_form_cues(FINAL)
        allowed = {queue.REPRESENTATIVE_SOURCE, queue.SAFE_VARIANT_SOURCE}

        self.assertTrue(recovered)
        for cues, source in recovered.values():
            self.assertTrue(cues)
            self.assertIn(source, allowed)

    def test_safe_variant_cues_are_not_inherited_from_the_base_exercise(self) -> None:
        """The safe variants replaced their posture, so base cues would mislead."""
        recovered = queue.recover_form_cues(FINAL)
        safe_variant_codes = {
            code for code, (_, source) in recovered.items() if source == queue.SAFE_VARIANT_SOURCE
        }

        self.assertTrue(safe_variant_codes)
        for code in safe_variant_codes:
            base = code.split("__")[0]
            if base in recovered and base != code:
                self.assertNotEqual(recovered[code][0], recovered[base][0], code)


if __name__ == "__main__":
    unittest.main()
