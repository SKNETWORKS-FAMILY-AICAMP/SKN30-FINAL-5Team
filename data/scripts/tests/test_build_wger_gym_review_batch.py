from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


SCRIPT_DIR = Path(__file__).resolve().parents[1]


def load_script(module_name: str, file_name: str):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wger_pipeline = load_script("wger_exercise_pipeline", "wger_exercise_pipeline.py")
wger_profile = load_script("profile_wger_exercises", "profile_wger_exercises.py")
gym_batch = load_script(
    "build_wger_gym_review_batch", "build_wger_gym_review_batch.py"
)


@contextmanager
def workspace_directory():
    path = Path.cwd() / f"test-work-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def translation(translation_id: int, name: str) -> dict[str, object]:
    return {
        "id": translation_id,
        "name": name,
        "language": 2,
        "license": 2,
        "license_author": "test contributor",
        "aliases": [],
    }


def exercise_item(
    exercise_id: int,
    name: str,
    equipment_names: list[str],
    category: str = "Back",
) -> dict[str, object]:
    return {
        "id": exercise_id,
        "uuid": f"00000000-0000-0000-0000-{exercise_id:012d}",
        "category": {"id": 12, "name": category},
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
        "images": [],
        "videos": [],
        "translations": [translation(exercise_id, name)],
    }


def page_bytes(results: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"count": len(results), "next": None, "previous": None, "results": results},
        ensure_ascii=False,
    ).encode("utf-8")


def source_exercises() -> list[dict[str, object]]:
    return [
        exercise_item(1, "Neutral Grip Lat Pulldown", ["Cable machine"]),
        exercise_item(2, "Incline Dumbbell Row", ["Dumbbell", "Incline bench"]),
        exercise_item(3, "Seated Cable Row", ["Cable machine"]),
        exercise_item(4, "Bench Press", ["Barbell", "Bench"], "Chest"),
        exercise_item(5, "Dumbbell Shoulder Press", ["Dumbbell"], "Shoulders"),
        exercise_item(6, "Leg Press", [], "Legs"),
        exercise_item(7, "Romanian Deadlift", ["Barbell"], "Legs"),
        exercise_item(8, "Cable Biceps Curl", ["Cable machine"], "Arms"),
    ]


def fake_fetcher(url: str, _timeout: float) -> bytes:
    resource = urlparse(url).path.rstrip("/").split("/")[-1]
    if resource == "exerciseinfo":
        return page_bytes(source_exercises())
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


def make_profile(root: Path) -> Path:
    snapshot = wger_pipeline.collect_snapshot(
        output_root=root / "snapshots",
        fetcher=fake_fetcher,
        now=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
    )
    return wger_profile.create_profile(snapshot, root / "profiles")


def direct_candidate(
    exercise_id: int,
    name: str,
    target_code: str,
    equipment: list[str],
) -> dict[str, object]:
    return {
        "source_exercise_id": exercise_id,
        "source_exercise_uuid": f"00000000-0000-0000-0000-{exercise_id:012d}",
        "source_names_en": [name],
        "source_aliases_en": [],
        "source_names_ko": [],
        "source_category": {"id": 12, "name": "Back"},
        "source_equipment": [
            {"id": index, "name": equipment_name}
            for index, equipment_name in enumerate(equipment, start=1)
        ],
        "source_primary_muscles": [{"id": 12, "name": "Latissimus dorsi"}],
        "source_secondary_muscles": [],
        "source_base_license": {
            "id": 2,
            "short_name": "CC-BY-SA 4",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/deed.en",
            "license_author": "test contributor",
        },
        "source_translation_licenses": [],
        "source_image_reference_count": 0,
        "source_video_reference_count": 0,
        "target_name_match_codes": [target_code],
        "gym_candidate_reason_codes": ["TARGET_NAME_SOURCE_EVIDENCE"],
        "required_review_codes": sorted(gym_batch.REQUIRED_REVIEW_CODES),
        "review_status": "DRAFT",
        "production_eligible": False,
    }


class BuildWgerGymReviewBatchTests(unittest.TestCase):
    def test_requested_source_names_are_seeded_and_review_fields_remain_pending(self) -> None:
        candidates = [
            direct_candidate(1, "Neutral Grip Lat Pulldown", "LAT_PULLDOWN", ["Cable machine"]),
            direct_candidate(2, "Incline Dumbbell Row", "DUMBBELL_ROW", ["Dumbbell"]),
            direct_candidate(3, "Seated Cable Row", "SEATED_OR_CABLE_ROW", ["Cable machine"]),
            direct_candidate(4, "Bench Press", "CHEST_OR_BENCH_PRESS", ["Barbell"]),
            direct_candidate(5, "Leg Press", "LEG_PRESS", []),
            direct_candidate(6, "Romanian Deadlift", "DEADLIFT", ["Barbell"]),
        ]

        rows, summary = gym_batch.select_review_batch(candidates, size=6)

        self.assertEqual(
            [row["primary_source_name_en"] for row in rows[:3]],
            list(gym_batch.USER_REQUESTED_SOURCE_NAME_SEEDS),
        )
        self.assertTrue(
            all(row["review_domain_safety_status"] == "PENDING" for row in rows)
        )
        self.assertTrue(all(row["review_display_name_ko"] == "" for row in rows))
        self.assertTrue(all(row["production_eligible"] is False for row in rows))
        self.assertEqual(summary["selected_batch_size"], 6)

    def test_duplicate_primary_name_prefers_source_complete_record(self) -> None:
        incomplete = direct_candidate(1, "Incline Dumbbell Row", "DUMBBELL_ROW", [])
        incomplete["source_primary_muscles"] = []
        complete = direct_candidate(
            2, "Incline Dumbbell Row", "DUMBBELL_ROW", ["Dumbbell", "Incline bench"]
        )
        fillers = [
            direct_candidate(3, "Neutral Grip Lat Pulldown", "LAT_PULLDOWN", ["Cable machine"]),
            direct_candidate(4, "Seated Cable Row", "SEATED_OR_CABLE_ROW", ["Cable machine"]),
        ]

        rows, summary = gym_batch.select_review_batch(
            [incomplete, complete, *fillers], size=3
        )

        selected = next(
            row for row in rows if row["primary_source_name_en"] == "Incline Dumbbell Row"
        )
        self.assertEqual(selected["source_exercise_id"], 2)
        self.assertEqual(selected["duplicate_primary_name_count"], 2)
        self.assertEqual(summary["duplicate_primary_name_groups"], 1)

    def test_builds_and_verifies_batch_from_wger_profile(self) -> None:
        with workspace_directory() as root:
            profile = make_profile(root)
            batch = gym_batch.create_review_batch(
                profile, root / "review_batches", size=6
            )

            result = gym_batch.verify_review_batch(batch)

            self.assertEqual(result["records"], 6)
            rows = list(
                csv.DictReader(
                    (batch / "gym_core_review_batch.csv")
                    .read_text(encoding="utf-8-sig")
                    .splitlines()
                )
            )
            self.assertEqual(rows[0]["primary_source_name_en"], "Neutral Grip Lat Pulldown")
            self.assertTrue(all(row["review_decision"] == "PENDING" for row in rows))
            evidence_rows = list(
                csv.DictReader(
                    (batch / "catalog_review_records_template.csv")
                    .read_text(encoding="utf-8-sig")
                    .splitlines()
                )
            )
            self.assertEqual(len(evidence_rows), 24)
            self.assertEqual(
                {row["reviewer_role_code"] for row in evidence_rows},
                set(gym_batch.REVIEWER_ROLE_CODES),
            )
            self.assertTrue(
                all(row["review_status_code"] == "DRAFT" for row in evidence_rows)
            )

    def test_verify_rejects_review_approval_inserted_into_generated_csv(self) -> None:
        with workspace_directory() as root:
            profile = make_profile(root)
            batch = gym_batch.create_review_batch(
                profile, root / "review_batches", size=6
            )
            csv_path = batch / "gym_core_review_batch.csv"
            csv_text = csv_path.read_text(encoding="utf-8-sig").replace(
                "PENDING", "APPROVED", 1
            )
            csv_path.write_text(csv_text, encoding="utf-8-sig", newline="")

            manifest_path = batch / "review_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = next(
                item
                for item in manifest["files"]
                if item["path"] == "gym_core_review_batch.csv"
            )
            raw = csv_path.read_bytes()
            entry["sha256"] = gym_batch.sha256_bytes(raw)
            entry["bytes"] = len(raw)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(gym_batch.PipelineError, "must remain pending"):
                gym_batch.verify_review_batch(batch)


if __name__ == "__main__":
    unittest.main()
