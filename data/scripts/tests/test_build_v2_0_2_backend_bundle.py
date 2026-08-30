from __future__ import annotations

import hashlib
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

SCRIPT = SCRIPTS / "build_v2_0_2_backend_bundle.py"
spec = importlib.util.spec_from_file_location("build_v2_0_2_backend_bundle", SCRIPT)
assert spec and spec.loader
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)

PipelineError = packager.PipelineError


def _alternative_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "map_relation_id": "REL-1",
        "source_exercise_stable_code": "barbell_squat",
        "target_exercise_stable_code": "glute_bridge",
        "condition_code": "NRS_1_3",
        "service_action_code": "LOAD_REDUCED",
        "target_strategy_code": "AREA_AVOIDING_CROSS_TRAINING_WITH_REDUCED_LOAD",
        "pain_discomfort_area_code": "KNEE",
        "review_status_code": "DOMAIN_APPROVED",
        "direction_code": "A_TO_B",
        "source_difficulty_code": "INTERMEDIATE",
        "target_difficulty_code": "BEGINNER",
    }
    row.update(overrides)
    return row


class AlternativeProjectionTests(unittest.TestCase):
    def test_supplies_the_backend_relation_contract(self) -> None:
        [projected] = packager._project_alternatives([_alternative_row()])

        self.assertEqual(projected["reason_code"], "DISCOMFORT")
        self.assertEqual(projected["goal_preservation_code"], "SAME_GOAL")
        self.assertEqual(projected["alternative_exercise_stable_code"], "glute_bridge")
        self.assertEqual(projected["rule_version"], packager.ALTERNATIVE_RULE_VERSION)
        # INTERMEDIATE -> BEGINNER is one step easier.
        self.assertEqual(projected["difficulty_delta"], -1)
        # The reviewed selectors travel through untouched.
        self.assertEqual(projected["pain_discomfort_area_code"], "KNEE")
        self.assertEqual(projected["condition_code"], "NRS_1_3")

    def test_recovery_band_does_not_claim_to_preserve_the_goal(self) -> None:
        row = _alternative_row(
            condition_code="NRS_4_6",
            service_action_code="SKIP_AFFECTED_AREA",
            target_strategy_code="AREA_AVOIDING_LOW_LOAD_ACTIVE_RECOVERY",
        )

        [projected] = packager._project_alternatives([row])

        self.assertEqual(projected["goal_preservation_code"], "ACTIVE_RECOVERY")

    def test_rejects_a_service_action_that_contradicts_the_band(self) -> None:
        row = _alternative_row(service_action_code="SKIP_AFFECTED_AREA")

        with self.assertRaises(PipelineError):
            packager._project_alternatives([row])

    def test_rejects_an_alternative_that_is_harder_than_its_source(self) -> None:
        row = _alternative_row(
            source_difficulty_code="BEGINNER", target_difficulty_code="INTERMEDIATE"
        )

        with self.assertRaises(PipelineError):
            packager._project_alternatives([row])


class MediaProjectionTests(unittest.TestCase):
    """Decision B1: a record with no asset is left out rather than faked."""

    def test_withholds_rows_without_an_asset(self) -> None:
        rows = [
            {"media_status": "AVAILABLE", "s3_key": "catalog-media/a.gif"},
            {"media_status": "UNAVAILABLE", "s3_key": ""},
            {"media_status": "AVAILABLE", "s3_key": ""},
        ]

        projected, withheld = packager._project_media(rows)

        self.assertEqual(len(projected), 1)
        self.assertEqual(withheld, 2)
        self.assertEqual(projected[0]["s3_key"], "catalog-media/a.gif")


class CatalogContentGateTests(unittest.TestCase):
    """The packager moves reviewed content; it never invents it."""

    def _record(self, **overrides: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "stable_code": "glute_bridge",
            "form_cues_ko": ["엉덩이를 조입니다"],
            "instruction_summary_ko": "누워서 엉덩이를 들어올립니다.",
            "default_rest_seconds": 60,
            "default_transition_seconds": 15,
        }
        record.update(overrides)
        return record

    def test_accepts_a_complete_record(self) -> None:
        packager._require_catalog_content([self._record()])

    def test_refuses_a_record_without_form_cues(self) -> None:
        with self.assertRaises(PipelineError) as caught:
            packager._require_catalog_content([self._record(form_cues_ko=[])])

        self.assertIn("form_cues_ko=1", str(caught.exception))

    def test_refuses_a_record_without_dosage_defaults(self) -> None:
        with self.assertRaises(PipelineError) as caught:
            packager._require_catalog_content([self._record(default_rest_seconds=None)])

        self.assertIn("default_rest_seconds=1", str(caught.exception))


class CanonicalPayloadVerificationTests(unittest.TestCase):
    def _final(self, directory: Path, *, payload: bytes, sealed: bytes | None = None) -> Path:
        final = directory / "final"
        for kind, relative in _PAYLOAD_PATHS.items():
            path = final / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload if kind == "catalog" else b"{}\n")
        recorded = {
            relative: hashlib.sha256(
                (sealed if kind == "catalog" and sealed is not None else payload)
                if kind == "catalog"
                else b"{}\n"
            ).hexdigest()
            for kind, relative in _PAYLOAD_PATHS.items()
        }
        (final / "manifest.json").write_text(
            json.dumps(
                {
                    "catalog_version_code": packager.CATALOG_VERSION_CODE,
                    "artifact_sha256": recorded,
                    "import_contract": {"canonical_payloads": _PAYLOAD_PATHS},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return final

    def test_accepts_payloads_that_match_their_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            final = self._final(Path(directory), payload=b'{"a": 1}\n')
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))

            resolved = packager._verify_canonical_payloads(final, manifest)

            self.assertEqual(set(resolved), set(_PAYLOAD_PATHS))

    def test_refuses_a_payload_that_drifted_from_its_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            final = self._final(Path(directory), payload=b'{"a": 2}\n', sealed=b'{"a": 1}\n')
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))

            with self.assertRaises(PipelineError) as caught:
                packager._verify_canonical_payloads(final, manifest)

            self.assertIn("does not match the manifest", str(caught.exception))


_PAYLOAD_PATHS = {
    "catalog": "catalog/exercises.jsonl",
    "safety": "runtime/safety_rules.jsonl",
    "alternatives": "alternatives/map.jsonl",
    "goals": "prescriptions/goal_tag_links.jsonl",
    "fitt": "prescriptions/prescription_profiles.jsonl",
    "media": "media/media_assets.csv",
}


if __name__ == "__main__":
    unittest.main()
