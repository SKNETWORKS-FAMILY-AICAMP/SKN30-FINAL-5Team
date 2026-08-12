from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def load_script(module_name: str, file_name: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wger_pipeline = load_script("wger_exercise_pipeline", "wger_exercise_pipeline.py")
wger_profile = load_script("profile_wger_exercises", "profile_wger_exercises.py")


@contextmanager
def workspace_directory() -> Iterator[Path]:
    # 저장소 안에 만들면 Windows 백신·인덱서가 새 파일을 스캔하며 핸들을 잡아
    # partial 디렉터리 rename이 WinError 5로 실패한다. OS 임시 디렉터리를 쓴다.
    path = Path(tempfile.mkdtemp(prefix="helkki-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def translation(
    translation_id: int, name: str, aliases: list[str] | None = None
) -> dict[str, object]:
    return {
        "id": translation_id,
        "name": name,
        "language": 2,
        "license": 2,
        "license_author": "test contributor",
        "aliases": [
            {"id": translation_id * 10 + index, "alias": alias}
            for index, alias in enumerate(aliases or [], start=1)
        ],
    }


def exercise_item(
    exercise_id: int,
    name: str | None,
    equipment_names: list[str],
    *,
    image: bool = False,
) -> dict[str, object]:
    return {
        "id": exercise_id,
        "uuid": f"00000000-0000-0000-0000-{exercise_id:012d}",
        "category": {"id": 12, "name": "Back"},
        "muscles": [{"id": 12, "name": "Latissimus dorsi"}],
        "muscles_secondary": [],
        "equipment": [
            {"id": index, "name": equipment_name}
            for index, equipment_name in enumerate(equipment_names, start=1)
        ],
        "license": {
            "id": 2,
            "full_name": "Creative Commons Attribution Share Alike 4",
            "short_name": "CC-BY-SA 4",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/deed.en",
        },
        "license_author": "test contributor",
        "images": [{"id": 1, "license": 2}] if image else [],
        "videos": [],
        "translations": [translation(exercise_id, name)] if name else [],
    }


def page_bytes(results: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"count": len(results), "next": None, "previous": None, "results": results},
        ensure_ascii=False,
    ).encode("utf-8")


class WgerExerciseProfileTests(unittest.TestCase):
    def fake_fetcher(self, url: str, _timeout: float) -> bytes:
        resource = urlparse(url).path.rstrip("/").split("/")[-1]
        if resource == "exerciseinfo":
            return page_bytes(
                [
                    exercise_item(1, "Neutral Grip Lat Pulldown", ["Cable machine"]),
                    exercise_item(2, "Incline Dumbbell Row", ["Dumbbell", "Bench"]),
                    exercise_item(3, "Seated Cable Row", []),
                    exercise_item(4, "Air Squat", ["none (bodyweight exercise)"]),
                    exercise_item(5, None, ["Barbell"], image=True),
                ]
            )
        if resource == "language":
            return page_bytes(
                [
                    {"id": 2, "short_name": "en", "full_name": "English"},
                    {"id": 27, "short_name": "ko", "full_name": "한국어"},
                ]
            )
        if resource == "license":
            return page_bytes(
                [
                    {
                        "id": 2,
                        "short_name": "CC-BY-SA 4",
                        "url": "https://creativecommons.org/licenses/by-sa/4.0/deed.en",
                    }
                ]
            )
        return page_bytes([{"id": 1, "name": resource}])

    def create_snapshot_and_profile(self, root: Path) -> tuple[Path, Path]:
        snapshot = wger_pipeline.collect_snapshot(
            output_root=root / "snapshots",
            fetcher=self.fake_fetcher,
            now=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
        )
        profile = wger_profile.create_profile(snapshot, root / "profiles")
        return snapshot, profile

    def test_builds_gym_inventory_and_target_coverage_without_approving_it(self) -> None:
        with workspace_directory() as root:
            _, profile_dir = self.create_snapshot_and_profile(root)

            result = wger_profile.verify_profile(profile_dir)
            self.assertEqual(result["gym_candidates"], 4)

            profile = json.loads((profile_dir / "profile.json").read_text(encoding="utf-8"))
            coverage = profile["coverage"]
            self.assertEqual(coverage["total_exercises"], 5)
            self.assertEqual(coverage["gym_review_candidates"], 4)
            self.assertEqual(coverage["exercises_with_korean_translation"], 0)
            self.assertFalse(profile["review"]["production_eligible"])

            target_coverage = json.loads(
                (profile_dir / "target_movement_coverage.json").read_text(encoding="utf-8")
            )
            counts = {
                target["code"]: target["source_name_match_count"]
                for target in target_coverage["targets"]
            }
            self.assertEqual(counts["LAT_PULLDOWN"], 1)
            self.assertEqual(counts["DUMBBELL_ROW"], 1)
            self.assertEqual(counts["SEATED_OR_CABLE_ROW"], 1)
            self.assertEqual(counts["SQUAT"], 1)

            candidates = [
                json.loads(line)
                for line in (profile_dir / "gym_candidate_inventory.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            missing_translation = next(
                candidate for candidate in candidates if candidate["source_exercise_id"] == 5
            )
            self.assertIn(
                "SOURCE_ENGLISH_TRANSLATION_MISSING",
                missing_translation["required_review_codes"],
            )
            self.assertIn(
                "MEDIA_RIGHTS_REVIEW_REQUIRED",
                missing_translation["required_review_codes"],
            )
            self.assertIn(
                "DOMAIN_SAFETY_REVIEW_REQUIRED",
                missing_translation["required_review_codes"],
            )

    def test_text_match_can_recover_machine_candidate_with_unspecified_equipment(self) -> None:
        with workspace_directory() as root:
            _, profile_dir = self.create_snapshot_and_profile(root)
            candidates = [
                json.loads(line)
                for line in (profile_dir / "gym_candidate_inventory.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            seated_row = next(
                candidate for candidate in candidates if candidate["source_exercise_id"] == 3
            )
            self.assertEqual(
                seated_row["gym_candidate_reason_codes"],
                ["TARGET_NAME_SOURCE_EVIDENCE"],
            )
            self.assertIn("SOURCE_EQUIPMENT_UNSPECIFIED", seated_row["required_review_codes"])

    def test_profile_verification_detects_tampered_inventory(self) -> None:
        with workspace_directory() as root:
            _, profile_dir = self.create_snapshot_and_profile(root)
            inventory = profile_dir / "gym_candidate_inventory.jsonl"
            inventory.write_bytes(inventory.read_bytes() + b" ")

            with self.assertRaisesRegex(wger_profile.PipelineError, "hash mismatch"):
                wger_profile.verify_profile(profile_dir)


if __name__ == "__main__":
    unittest.main()
