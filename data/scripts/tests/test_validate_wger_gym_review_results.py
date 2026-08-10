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
result_validator = load_script(
    "validate_wger_gym_review_results", "validate_wger_gym_review_results.py"
)


@contextmanager
def workspace_directory():
    path = Path.cwd() / f"test-work-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def page_bytes(results: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"count": len(results), "next": None, "previous": None, "results": results},
        ensure_ascii=False,
    ).encode("utf-8")


def exercise_item(exercise_id: int, name: str, equipment: str) -> dict[str, object]:
    return {
        "id": exercise_id,
        "uuid": f"00000000-0000-0000-0000-{exercise_id:012d}",
        "category": {"id": 12, "name": "Back"},
        "muscles": [{"id": 12, "name": "Latissimus dorsi"}],
        "muscles_secondary": [],
        "equipment": [{"id": 1, "name": equipment}],
        "license": {
            "id": 2,
            "full_name": "Creative Commons Attribution Share Alike 4",
            "short_name": "CC-BY-SA 4",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/deed.en",
        },
        "license_author": "test contributor",
        "images": [],
        "videos": [],
        "translations": [
            {
                "id": exercise_id,
                "name": name,
                "language": 2,
                "license": 2,
                "license_author": "test contributor",
                "aliases": [],
            }
        ],
    }


def fake_fetcher(url: str, _timeout: float) -> bytes:
    resource = urlparse(url).path.rstrip("/").split("/")[-1]
    if resource == "exerciseinfo":
        return page_bytes(
            [
                exercise_item(1, "Neutral Grip Lat Pulldown", "Cable machine"),
                exercise_item(2, "Incline Dumbbell Row", "Dumbbell"),
                exercise_item(3, "Seated Cable Row", "Cable machine"),
                exercise_item(4, "Bench Press", "Barbell"),
                exercise_item(5, "Leg Press", "Cable machine"),
                exercise_item(6, "Romanian Deadlift", "Barbell"),
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


def make_batch(root: Path) -> Path:
    snapshot = wger_pipeline.collect_snapshot(
        output_root=root / "snapshots",
        fetcher=fake_fetcher,
        now=datetime(2026, 8, 10, 11, 0, tzinfo=timezone.utc),
    )
    profile = wger_profile.create_profile(snapshot, root / "profiles")
    return gym_batch.create_review_batch(profile, root / "review_batches", size=6)


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        return reader.fieldnames, list(reader)


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def result_copies(batch: Path, root: Path) -> tuple[Path, Path]:
    mapping = root / "mapping_results.csv"
    evidence = root / "evidence_results.csv"
    shutil.copyfile(batch / "gym_core_review_batch.csv", mapping)
    shutil.copyfile(batch / "catalog_review_records_template.csv", evidence)
    return mapping, evidence


class ValidateWgerGymReviewResultsTests(unittest.TestCase):
    def test_untouched_draft_templates_validate_as_pending_and_not_production_ready(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)

            result = result_validator.validate_review_results(
                batch, mapping, evidence
            )

            self.assertEqual(result["decision_counts"]["PENDING"], 6)
            self.assertEqual(result["evidence_status_counts"]["DRAFT"], 24)
            self.assertEqual(result["review_complete_rows"], 0)
            self.assertFalse(result["production_eligible"])

    def test_immutable_source_identity_change_is_rejected(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            fields, rows = read_rows(mapping)
            rows[0]["primary_source_name_en"] = "Changed source name"
            write_rows(mapping, fields, rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "immutable mapping field changed"
            ):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_non_draft_evidence_requires_opaque_reference_and_timestamp(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            fields, rows = read_rows(evidence)
            rows[0]["review_status_code"] = "TECH_REVIEWED"
            write_rows(evidence, fields, rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "opaque internal code"
            ):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_include_without_domain_evidence_fails_closed(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            self.complete_mapping_row(mapping_rows[0])
            write_rows(mapping, mapping_fields, mapping_rows)
            evidence_fields, evidence_rows = read_rows(evidence)
            self.complete_evidence_for_exercise(
                evidence_rows,
                mapping_rows[0]["source_exercise_id"],
                omit_role="DOMAIN_REVIEWER",
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "DOMAIN_REVIEWER evidence"
            ):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_fully_evidenced_include_is_structurally_valid_but_not_production_eligible(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            self.complete_mapping_row(mapping_rows[0])
            write_rows(mapping, mapping_fields, mapping_rows)
            evidence_fields, evidence_rows = read_rows(evidence)
            self.complete_evidence_for_exercise(
                evidence_rows, mapping_rows[0]["source_exercise_id"]
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            result = result_validator.validate_review_results(
                batch, mapping, evidence
            )

            self.assertEqual(result["decision_counts"]["INCLUDE"], 1)
            self.assertEqual(result["review_complete_rows"], 1)
            self.assertFalse(result["production_eligible"])

    @staticmethod
    def complete_mapping_row(row: dict[str, str]) -> None:
        row.update(
            {
                "review_normalized_exercise_id": "neutral_grip_lat_pulldown",
                "review_display_name_ko": "뉴트럴 그립 랫풀다운",
                "review_taxonomy_code": "vertical_pull",
                "review_beginner_suitability": "YES",
                "review_execution_guidance_status": "APPROVED",
                "review_license_status": "APPROVED",
                "review_domain_safety_status": "APPROVED",
                "review_decision": "INCLUDE",
                "reviewer_notes": "synthetic reviewed row",
            }
        )

    @staticmethod
    def complete_evidence_for_exercise(
        rows: list[dict[str, str]],
        exercise_id: str,
        omit_role: str | None = None,
    ) -> None:
        for row in rows:
            if row["source_exercise_id"] != exercise_id:
                continue
            role = row["reviewer_role_code"]
            if role == omit_role:
                continue
            row.update(
                {
                    "review_status_code": "DOMAIN_APPROVED"
                    if role == "DOMAIN_REVIEWER"
                    else "TECH_REVIEWED",
                    "reviewer_reference": f"{role}:reviewer001",
                    "evidence_reference": "docs/reviews/TEST-001",
                    "reviewed_at": "2026-08-10T12:00:00+09:00",
                }
            )


if __name__ == "__main__":
    unittest.main()
