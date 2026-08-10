from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "wger_exercise_pipeline.py"
SPEC = importlib.util.spec_from_file_location("wger_exercise_pipeline", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
wger_pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wger_pipeline
SPEC.loader.exec_module(wger_pipeline)


@contextmanager
def workspace_directory() -> Iterator[Path]:
    path = Path.cwd() / f"test-work-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def exercise_item(exercise_id: int) -> dict[str, object]:
    return {
        "id": exercise_id,
        "uuid": f"00000000-0000-0000-0000-{exercise_id:012d}",
        "category": {"id": 8, "name": "Arms"},
        "muscles": [],
        "muscles_secondary": [],
        "equipment": [{"id": 3, "name": "Dumbbell"}],
        "license": {
            "id": 2,
            "full_name": "Creative Commons Attribution Share Alike 4",
            "short_name": "CC-BY-SA 4",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/deed.en",
        },
        "license_author": "tester",
        "images": [],
        "videos": [],
        "translations": [
            {
                "id": exercise_id,
                "name": f"Exercise {exercise_id}",
                "language": 2,
                "license": 2,
                "aliases": [],
            }
        ],
    }


def page_bytes(results: list[dict[str, object]], count: int, next_url: str | None) -> bytes:
    return json.dumps(
        {"count": count, "next": next_url, "previous": None, "results": results},
        ensure_ascii=False,
    ).encode("utf-8")


def reference_item(resource: str) -> dict[str, object]:
    return {"id": 1, "name": resource}


class WgerExercisePipelineTests(unittest.TestCase):
    def fake_fetcher(self, url: str, timeout: float) -> bytes:
        self.assertEqual(timeout, 5.0)
        parsed = urlparse(url)
        resource = parsed.path.rstrip("/").split("/")[-1]
        query = parse_qs(parsed.query)
        offset = int(query["offset"][0])
        if resource == "exerciseinfo":
            if offset == 0:
                return page_bytes(
                    [exercise_item(1), exercise_item(2)],
                    3,
                    "https://wger.de/api/v2/exerciseinfo/?limit=2&offset=2",
                )
            return page_bytes([exercise_item(3)], 3, None)
        return page_bytes([reference_item(resource)], 1, None)

    def test_collects_all_allowlisted_resources_and_preserves_licenses(self) -> None:
        with workspace_directory() as output_root:
            snapshot = wger_pipeline.collect_snapshot(
                output_root=output_root,
                page_size=2,
                timeout=5.0,
                fetcher=self.fake_fetcher,
                now=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            )

            result = wger_pipeline.validate_snapshot(snapshot)

            self.assertEqual(result["exercises"], 3)
            self.assertEqual(result["pages"], 7)
            manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"]["data_license"]["mode"], "PER_ENTRY_LICENSE")
            self.assertFalse(manifest["source"]["media_policy"]["image_binary_collected"])
            self.assertEqual(manifest["review"]["status"], "DRAFT")
            self.assertFalse(manifest["review"]["production_eligible"])

    def test_missing_exercise_license_does_not_complete_snapshot(self) -> None:
        def missing_license_fetcher(url: str, _timeout: float) -> bytes:
            parsed = urlparse(url)
            resource = parsed.path.rstrip("/").split("/")[-1]
            if resource == "exerciseinfo":
                item = exercise_item(1)
                item["license"] = None
                return page_bytes([item], 1, None)
            return page_bytes([reference_item(resource)], 1, None)

        with workspace_directory() as output_root:
            with self.assertRaisesRegex(wger_pipeline.PipelineError, "license"):
                wger_pipeline.collect_snapshot(
                    output_root=output_root,
                    fetcher=missing_license_fetcher,
                    now=datetime(2026, 8, 10, 8, 1, tzinfo=UTC),
                )
            self.assertEqual(list(output_root.iterdir()), [])

    def test_empty_translation_is_preserved_for_profile_quality_screening(self) -> None:
        def empty_translation_fetcher(url: str, _timeout: float) -> bytes:
            parsed = urlparse(url)
            resource = parsed.path.rstrip("/").split("/")[-1]
            if resource == "exerciseinfo":
                item = exercise_item(1)
                item["translations"] = []
                return page_bytes([item], 1, None)
            return page_bytes([reference_item(resource)], 1, None)

        with workspace_directory() as output_root:
            snapshot = wger_pipeline.collect_snapshot(
                output_root=output_root,
                fetcher=empty_translation_fetcher,
                now=datetime(2026, 8, 10, 8, 4, tzinfo=UTC),
            )

            self.assertEqual(wger_pipeline.validate_snapshot(snapshot)["exercises"], 1)

    def test_record_count_mismatch_does_not_complete_snapshot(self) -> None:
        def incomplete_fetcher(url: str, _timeout: float) -> bytes:
            parsed = urlparse(url)
            resource = parsed.path.rstrip("/").split("/")[-1]
            if resource == "exerciseinfo":
                return page_bytes([], 2, "next")
            return page_bytes([reference_item(resource)], 1, None)

        with workspace_directory() as output_root:
            with self.assertRaisesRegex(wger_pipeline.PipelineError, "empty page"):
                wger_pipeline.collect_snapshot(
                    output_root=output_root,
                    fetcher=incomplete_fetcher,
                    now=datetime(2026, 8, 10, 8, 2, tzinfo=UTC),
                )
            self.assertEqual(list(output_root.iterdir()), [])

    def test_validation_detects_tampered_raw_page(self) -> None:
        with workspace_directory() as output_root:
            snapshot = wger_pipeline.collect_snapshot(
                output_root=output_root,
                page_size=2,
                timeout=5.0,
                fetcher=self.fake_fetcher,
                now=datetime(2026, 8, 10, 8, 3, tzinfo=UTC),
            )
            page = snapshot / "exerciseinfo" / "page-00001.json"
            page.write_bytes(page.read_bytes() + b" ")

            with self.assertRaisesRegex(wger_pipeline.PipelineError, "hash mismatch"):
                wger_pipeline.validate_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
