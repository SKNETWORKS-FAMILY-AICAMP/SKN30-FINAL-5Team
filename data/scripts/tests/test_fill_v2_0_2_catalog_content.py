from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SCRIPT = SCRIPTS / "fill_v2_0_2_catalog_content.py"
spec = importlib.util.spec_from_file_location("fill_v2_0_2_catalog_content", SCRIPT)
assert spec and spec.loader
fill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fill)

ContentFillError = fill.ContentFillError


class PainAreaFromStableCodeTests(unittest.TestCase):
    def test_reads_the_area_a_safe_variant_is_named_for(self) -> None:
        code = "one_arm_wall_lats_isolation_bodyweight__knee_no_load_safe_v1"

        self.assertEqual(fill.pain_area_from_stable_code(code), "KNEE")

    def test_reads_a_multi_word_area(self) -> None:
        code = "peroneal_stretch_mobility_stretch_stretch_strap__upper_back_no_load_safe_v1"

        self.assertEqual(fill.pain_area_from_stable_code(code), "UPPER_BACK")

    def test_returns_none_for_an_ordinary_exercise(self) -> None:
        self.assertIsNone(fill.pain_area_from_stable_code("barbell_full_squat"))


class SafeVariantCueTemplateTests(unittest.TestCase):
    def test_renders_the_four_cues_the_reviewed_variants_use(self) -> None:
        cues = fill.render_safe_variant_cues(
            posture_code="SUPPORTED_SUPINE_NEUTRAL_SPINE",
            support_code="FULL_BACK_AND_PELVIS_MAT_SUPPORT",
            pain_area_code="LOWER_BACK",
            base_name_ko="버터플라이 스트레칭",
        )

        self.assertEqual(len(cues), 4)
        self.assertIn("SUPPORTED_SUPINE_NEUTRAL_SPINE", cues[0])
        self.assertIn("FULL_BACK_AND_PELVIS_MAT_SUPPORT", cues[0])
        self.assertIn("LOWER_BACK", cues[1])
        self.assertIn("버터플라이 스트레칭", cues[2])
        self.assertIn("중단", cues[3])

    def test_refuses_to_render_without_every_input(self) -> None:
        with self.assertRaises(ContentFillError):
            fill.render_safe_variant_cues(
                posture_code="",
                support_code="FULL_BACK_AND_PELVIS_MAT_SUPPORT",
                pain_area_code="LOWER_BACK",
                base_name_ko="버터플라이 스트레칭",
            )


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "stable_code": "barbell_full_squat",
        "name_ko": "바벨 풀 스쿼트",
        "training_type_code": "STRENGTH",
        "timing_mode_code": "REPS",
        "record_type": "REPRESENTATIVE",
        "form_cues_ko": ["무릎이 발끝을 넘지 않게 한다"],
        "default_rest_seconds": 90,
        "default_transition_seconds": 15,
    }
    record.update(overrides)
    return record


class DosagePolicyTests(unittest.TestCase):
    """The rest table is v2.0.1's, applied per class rather than per exercise."""

    def _fill(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        with tempfile.TemporaryDirectory() as directory:
            final = Path(directory)
            (final / "catalog").mkdir(parents=True)
            (final / "audit/alternatives").mkdir(parents=True)
            (final / "catalog/exercises.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
                encoding="utf-8",
            )
            (final / "audit/alternatives/discomfort_safe_variants_v2_0_2.jsonl").write_text(
                "", encoding="utf-8"
            )
            (final / "audit/canonical_exercises_v2_0_2_refined.csv").write_text(
                "stable_code,form_cues_ko\n", encoding="utf-8"
            )
            return fill.fill(final)

    def test_applies_the_class_rest_interval(self) -> None:
        records, summary = self._fill(
            [
                _record(
                    stable_code="seated_hamstring_stretch",
                    training_type_code="MOBILITY",
                    timing_mode_code="DURATION",
                    default_rest_seconds=None,
                )
            ]
        )

        self.assertEqual(records[0]["default_rest_seconds"], 30)
        self.assertEqual(records[0]["default_rest_seconds_source"], fill.DOSAGE_POLICY_VERSION)
        self.assertEqual(summary["filled"]["rest"], 1)

    def test_never_overwrites_a_value_the_catalog_already_states(self) -> None:
        records, summary = self._fill([_record(default_rest_seconds=45)])

        self.assertEqual(records[0]["default_rest_seconds"], 45)
        self.assertNotIn("default_rest_seconds_source", records[0])
        self.assertEqual(summary["filled"]["rest"], 0)

    def test_refuses_a_class_the_approved_table_does_not_cover(self) -> None:
        with self.assertRaises(ContentFillError):
            self._fill(
                [
                    _record(
                        training_type_code="CARDIO",
                        timing_mode_code="REPS",
                        default_rest_seconds=None,
                    )
                ]
            )

    def test_defers_a_record_no_template_can_serve(self) -> None:
        records, summary = self._fill(
            [_record(stable_code="dumbbell_front_raise", form_cues_ko=[])]
        )

        self.assertEqual(summary["deferred_records"], 1)
        self.assertEqual(summary["deferred_stable_codes"], ["dumbbell_front_raise"])
        self.assertFalse(records[0]["form_cues_ko"])


if __name__ == "__main__":
    unittest.main()
