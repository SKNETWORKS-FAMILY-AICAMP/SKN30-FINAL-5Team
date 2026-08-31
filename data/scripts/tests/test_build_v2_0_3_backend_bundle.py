from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_v2_0_3_backend_bundle import (  # noqa: E402
    SOURCE_VERSION,
    TARGET_VERSION,
    _retarget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_BUNDLE = PROJECT_ROOT / f"data/generated/{SOURCE_VERSION}/backend_bundle"
TARGET_BUNDLE = PROJECT_ROOT / f"data/generated/{TARGET_VERSION}/backend_bundle"
PROMOTE_SCRIPT = PROJECT_ROOT / "backend/scripts/catalog_promote_v2_0_3.py"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class PublishedV203BundleTests(unittest.TestCase):
    """Guards on the published artifact, not on a synthetic fixture."""

    def test_source_version_is_untouched_by_the_expansion(self) -> None:
        profiles = _read_jsonl(SOURCE_BUNDLE / "prescriptions/prescription_profiles.jsonl")

        self.assertEqual({row["goal_code"] for row in profiles}, {"GENERAL_FITNESS"})

    def test_target_version_covers_every_onboarding_goal(self) -> None:
        profiles = _read_jsonl(TARGET_BUNDLE / "prescriptions/prescription_profiles.jsonl")

        self.assertEqual(
            {row["goal_code"] for row in profiles},
            {"GENERAL_FITNESS", "FAT_LOSS", "MUSCLE_GAIN"},
        )

    def test_every_phase_is_reachable_for_every_goal_and_level(self) -> None:
        profiles = _read_jsonl(TARGET_BUNDLE / "prescriptions/prescription_profiles.jsonl")

        combinations = {
            (row["goal_code"], row["experience_level_code"], row["phase_code"]) for row in profiles
        }
        for goal in ("GENERAL_FITNESS", "FAT_LOSS", "MUSCLE_GAIN"):
            for level in ("BEGINNER", "INTERMEDIATE"):
                for phase in ("WARMUP", "MAIN", "COOLDOWN"):
                    self.assertIn((goal, level, phase), combinations)

    def test_no_record_still_points_at_the_source_version(self) -> None:
        for jsonl in sorted(TARGET_BUNDLE.rglob("*.jsonl")):
            for row in _read_jsonl(jsonl):
                self.assertNotIn(SOURCE_VERSION, json.dumps(row, ensure_ascii=False))

    def test_derivation_is_recorded_and_verifiable(self) -> None:
        manifest = json.loads((TARGET_BUNDLE / "bundle_manifest.json").read_text("utf-8"))
        derived = manifest["derived_from"]

        self.assertEqual(derived["catalog_version_code"], SOURCE_VERSION)
        source_hash = hashlib.sha256(
            (SOURCE_BUNDLE / "bundle_manifest.json").read_bytes()
        ).hexdigest()
        self.assertEqual(derived["bundle_manifest_sha256"], source_hash)

    def test_manifest_hashes_match_the_files_on_disk(self) -> None:
        manifest = json.loads((TARGET_BUNDLE / "bundle_manifest.json").read_text("utf-8"))

        for entry in manifest["files"]:
            path = TARGET_BUNDLE / entry["path"]
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(entry["bytes"], path.stat().st_size)

    def test_promotion_script_pins_the_published_manifest_hash(self) -> None:
        # A stale pin would fail the import at deploy time instead of here.
        published = hashlib.sha256(
            (TARGET_BUNDLE / "bundle_manifest.json").read_bytes()
        ).hexdigest()

        self.assertIn(published, PROMOTE_SCRIPT.read_text(encoding="utf-8"))

    def test_retarget_moves_versions_without_touching_other_text(self) -> None:
        payload = {
            "catalog_version_code": SOURCE_VERSION,
            "carried_over_source": "exercise-catalog-v2.0.1-final/runtime",
            "note": "unrelated text",
        }

        moved = _retarget(payload)

        self.assertEqual(moved["catalog_version_code"], TARGET_VERSION)
        self.assertEqual(moved["carried_over_source"], "exercise-catalog-v2.0.1-final/runtime")
        self.assertEqual(moved["note"], "unrelated text")


if __name__ == "__main__":
    unittest.main()
