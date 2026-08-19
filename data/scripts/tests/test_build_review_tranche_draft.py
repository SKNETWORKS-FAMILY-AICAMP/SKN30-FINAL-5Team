from __future__ import annotations

import csv
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

SCRIPT_DIR = Path(__file__).resolve().parents[1]

# 스크립트끼리 형제 모듈을 import하므로 로더가 경로를 알아야 한다.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_script(module_name: str, file_name: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


kspo_pipeline = load_script("kspo_fitness100_pipeline", "kspo_fitness100_pipeline.py")
kspo_profile = load_script("profile_kspo_fitness100", "profile_kspo_fitness100.py")
kspo_batch = load_script(
    "build_kspo_fitness100_review_batch", "build_kspo_fitness100_review_batch.py"
)
seed = load_script("build_exercise_catalog_seed", "build_exercise_catalog_seed.py")
tranche = load_script("build_review_tranche_draft", "build_review_tranche_draft.py")

TRACK = seed.TRACKS["kspo"]


@contextmanager
def workspace_directory() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="helkki-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def response_bytes(items: list[dict[str, object]]) -> bytes:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {"pageNo": 1, "totalCount": len(items), "items": {"item": items}},
        }
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def source_items() -> list[dict[str, object]]:
    base: dict[str, object] = {
        "aggrp_nm": "성인기",
        "trng_plc_nm": "실내",
        "tool_nm": "매트",
        "trng_mscl_part": "복부",
        "set_cnt_nm": "",
        "rptt_tcnt_nm": "",
        "trng_hr_nm": "",
        "ecrg_cycl_nm": "",
        "vdo_desc": "원천 설명",
        "vdo_ttl_nm": "원천 제목",
    }
    names = ["가슴펴기", "무릎 굽히기", "팔 들어올리기"]
    return [
        {**base, "file_nm": f"v-{i}.mp4", "trng_nm": n, "img_file_nm": f"{i}.jpg"}
        for i, n in enumerate(names, start=1)
    ]


def row_spec(position: int, code: str, name_ko: str) -> dict[str, object]:
    return {
        "batch_position": position,
        "stable_code": code,
        "name_ko": name_ko,
        "training_type_code": "MOBILITY",
        "body_focus_code": "CORE",
        "movement_pattern_code": "MOBILITY_STRETCH",
        "equipment_codes": "MAT",
        "location_codes": "HOME",
        "difficulty_code": "BEGINNER",
        "timing_mode_code": "DURATION",
        "default_work_seconds": 30,
        "default_rest_seconds": 20,
        "recovery_eligible": "TRUE",
    }


class BuildReviewTrancheDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = workspace_directory()
        self.root = self.stack.__enter__()
        snapshot = kspo_pipeline.collect_snapshot(
            service_key="test-secret",
            endpoint="training-video",
            output_root=self.root / "snapshots",
            page_size=100,
            fetcher=lambda _u, _t: response_bytes(source_items()),
            now=datetime(2026, 8, 11, 7, 0, tzinfo=UTC),
        )
        profile = kspo_profile.create_profile(snapshot, self.root / "profiles")
        self.batch_root = self.root / "review_batches"
        self.batch = kspo_batch.create_review_batch(profile, self.batch_root, size=3)
        self.mapping_out = self.root / "mapping_draft.csv"
        self.attributes_out = self.root / "attributes_draft.csv"

    def tearDown(self) -> None:
        self.stack.__exit__(None, None, None)

    def write_tranche(self, rows: list[dict[str, object]]) -> Path:
        path = self.root / "tranche.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "DRAFT",
                    "production_eligible": False,
                    "tranches": [
                        {
                            "track": "kspo",
                            "batch_directory": self.batch.name,
                            "rows": rows,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def render(self, rows: list[dict[str, object]]) -> dict[str, object]:
        return tranche.render_drafts(
            TRACK,
            self.write_tranche(rows),
            self.mapping_out,
            self.attributes_out,
            self.batch_root,
        )

    def read(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_draft_fills_content_but_never_raises_approval(self) -> None:
        result = self.render(
            [
                row_spec(1, "chest_opening", "가슴 펴고 천장 보기"),
                row_spec(2, "knee_bend", "무릎 굽히기 동작"),
            ]
        )

        self.assertEqual(result["drafted_rows"], 2)
        self.assertEqual(result["left_pending_rows"], 1)
        mapping = self.read(self.mapping_out)
        self.assertEqual(len(mapping), 3)
        for row in mapping:
            self.assertEqual(row["review_decision"], "PENDING")
            self.assertEqual(row["review_domain_safety_status"], "PENDING")
            self.assertEqual(row["review_media_rights_status"], "PENDING")
            self.assertEqual(row["review_beginner_suitability"], "PENDING")
            self.assertEqual(row["review_status"], "DRAFT")
            self.assertEqual(row["production_eligible"], "false")

        drafted = [row for row in mapping if row["review_normalized_exercise_id"]]
        self.assertEqual(len(drafted), 2)
        self.assertEqual(drafted[0]["review_display_name_ko"], "가슴 펴고 천장 보기")

    def test_draft_leaves_body_area_and_form_cues_for_the_expert(self) -> None:
        self.render([row_spec(1, "chest_opening", "가슴 펴고 천장 보기")])

        attributes = self.read(self.attributes_out)
        self.assertEqual(len(attributes), 1)
        row = attributes[0]
        for field in (
            "primary_body_area_codes",
            "secondary_body_area_codes",
            "instruction_summary_ko",
            "form_cues_ko",
            "instruction_content_version",
        ):
            self.assertEqual(row[field], "", f"{field} must stay blank")
        self.assertEqual(row["attribute_status"], "PENDING")
        self.assertEqual(row["draft_source"], tranche.DRAFT_SOURCE_MARK)
        self.assertEqual(row["default_transition_seconds"], "15")

    def test_drafted_rows_are_marked_so_reviewers_can_tell(self) -> None:
        self.render([row_spec(1, "chest_opening", "가슴 펴고 천장 보기")])

        mapping = self.read(self.mapping_out)
        drafted = [row for row in mapping if row["review_normalized_exercise_id"]]
        self.assertIn(tranche.DRAFT_SOURCE_MARK, drafted[0]["reviewer_notes"])
        untouched = [row for row in mapping if not row["review_normalized_exercise_id"]]
        self.assertTrue(all(row["reviewer_notes"] == "" for row in untouched))

    def test_duplicate_draft_display_names_are_rejected(self) -> None:
        with self.assertRaisesRegex(tranche.PipelineError, "duplicated"):
            self.render(
                [
                    row_spec(1, "code_a", "같은 이름"),
                    row_spec(2, "code_b", "같은 이름"),
                ]
            )

    def test_draft_display_name_must_follow_korean_rules(self) -> None:
        with self.assertRaisesRegex(tranche.PipelineError, "no Hangul"):
            self.render([row_spec(1, "code_a", "Chest Opening Stretch")])

    def test_medical_claim_in_draft_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(tranche.PipelineError, "medical claim"):
            self.render([row_spec(1, "code_a", "허리 통증 치료 스트레칭")])

    def test_unknown_batch_position_is_rejected(self) -> None:
        with self.assertRaisesRegex(tranche.PipelineError, "is not in"):
            self.render([row_spec(99, "code_a", "없는 위치")])

    def test_draft_output_still_passes_the_result_gate_as_pending(self) -> None:
        from validate_kspo_fitness100_review_results import validate_review_results

        self.render([row_spec(1, "chest_opening", "가슴 펴고 천장 보기")])

        result = validate_review_results(
            self.batch, self.mapping_out, self.batch / "catalog_review_records_template.csv"
        )

        decision_counts = result["decision_counts"]
        assert isinstance(decision_counts, dict)
        self.assertEqual(decision_counts["PENDING"], 3)
        self.assertEqual(result["review_complete_rows"], 0)
        self.assertFalse(result["production_eligible"])


if __name__ == "__main__":
    unittest.main()
