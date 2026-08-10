from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import uuid4

SCRIPT_DIR = Path(__file__).resolve().parents[1]

# 스크립트끼리 형제 모듈을 import하므로 로더가 경로를 알아야 한다. 이 줄이 없으면
# 테스트 모듈이 먼저 로드한 순서에 우연히 의존하게 된다.
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
result_validator = load_script(
    "validate_kspo_fitness100_review_results",
    "validate_kspo_fitness100_review_results.py",
)


@contextmanager
def workspace_directory() -> Iterator[Path]:
    path = Path.cwd() / f"test-work-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def response_bytes(items: list[dict[str, object]]) -> bytes:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {
                "pageNo": 1,
                "totalCount": len(items),
                "items": {"item": items},
            },
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
        {
            **base,
            "file_nm": f"video-{index}.mp4",
            "trng_nm": name,
            "img_file_nm": f"{index}.jpg",
        }
        for index, name in enumerate(names, start=1)
    ]


def make_batch(root: Path) -> Path:
    snapshot = kspo_pipeline.collect_snapshot(
        service_key="test-secret",
        endpoint="training-video",
        output_root=root / "snapshots",
        page_size=100,
        fetcher=lambda _url, _timeout: response_bytes(source_items()),
        now=datetime(2026, 8, 10, 7, 0, tzinfo=UTC),
    )
    profile = kspo_profile.create_profile(snapshot, root / "profiles")
    return kspo_batch.create_review_batch(profile, root / "review_batches", size=3)


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        return list(reader.fieldnames), list(reader)


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def result_copies(batch: Path, root: Path) -> tuple[Path, Path]:
    mapping = root / "mapping_results.csv"
    evidence = root / "evidence_results.csv"
    shutil.copyfile(batch / "review_batch.csv", mapping)
    shutil.copyfile(batch / "catalog_review_records_template.csv", evidence)
    return mapping, evidence


class ValidateKspoFitness100ReviewResultsTests(unittest.TestCase):
    def test_untouched_draft_templates_validate_as_pending_and_not_production_ready(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)

            result = result_validator.validate_review_results(batch, mapping, evidence)

            self.assertEqual(result["decision_counts"]["PENDING"], 3)
            self.assertEqual(result["evidence_status_counts"]["DRAFT"], 12)
            self.assertEqual(result["review_complete_rows"], 0)
            self.assertFalse(result["production_eligible"])

    def test_immutable_source_identity_change_is_rejected(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            fields, rows = read_rows(mapping)
            rows[0]["source_training_name"] = "바뀐 원천 운동명"
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

            with self.assertRaisesRegex(result_validator.PipelineError, "opaque internal code"):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_reviewer_email_is_rejected_as_reviewer_reference(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            fields, rows = read_rows(evidence)
            rows[0].update(
                {
                    "review_status_code": "TECH_REVIEWED",
                    "reviewer_reference": "reviewer@example.com",
                    "evidence_reference": "docs/reviews/TEST-001",
                    "reviewed_at": "2026-08-10T12:00:00+09:00",
                }
            )
            write_rows(evidence, fields, rows)

            with self.assertRaisesRegex(result_validator.PipelineError, "opaque internal code"):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_timestamp_without_timezone_is_rejected(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            fields, rows = read_rows(evidence)
            rows[0].update(
                {
                    "review_status_code": "TECH_REVIEWED",
                    "reviewer_reference": "DATA_OWNER:reviewer001",
                    "evidence_reference": "docs/reviews/TEST-001",
                    "reviewed_at": "2026-08-10T12:00:00",
                }
            )
            write_rows(evidence, fields, rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "must include timezone information"
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
            self.complete_evidence_for_candidate(
                evidence_rows,
                mapping_rows[0]["source_candidate_id"],
                omit_role="DOMAIN_REVIEWER",
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            with self.assertRaisesRegex(result_validator.PipelineError, "DOMAIN_REVIEWER evidence"):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_include_without_media_rights_approval_fails_closed(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            self.complete_mapping_row(mapping_rows[0])
            mapping_rows[0]["review_media_rights_status"] = "PENDING"
            write_rows(mapping, mapping_fields, mapping_rows)
            evidence_fields, evidence_rows = read_rows(evidence)
            self.complete_evidence_for_candidate(
                evidence_rows, mapping_rows[0]["source_candidate_id"]
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "review_media_rights_status is not APPROVED"
            ):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_include_with_untranslated_english_name_fails_closed(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            self.complete_mapping_row(mapping_rows[0])
            mapping_rows[0]["review_display_name_ko"] = "Chest Opening Stretch"
            write_rows(mapping, mapping_fields, mapping_rows)
            evidence_fields, evidence_rows = read_rows(evidence)
            self.complete_evidence_for_candidate(
                evidence_rows, mapping_rows[0]["source_candidate_id"]
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            with self.assertRaisesRegex(result_validator.PipelineError, "contains no Hangul"):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_include_with_medical_claim_name_fails_closed(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            self.complete_mapping_row(mapping_rows[0])
            mapping_rows[0]["review_display_name_ko"] = "허리 통증 치료 스트레칭"
            write_rows(mapping, mapping_fields, mapping_rows)
            evidence_fields, evidence_rows = read_rows(evidence)
            self.complete_evidence_for_candidate(
                evidence_rows, mapping_rows[0]["source_candidate_id"]
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            with self.assertRaisesRegex(result_validator.PipelineError, "medical claim language"):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_duplicate_korean_display_names_fail_closed(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            evidence_fields, evidence_rows = read_rows(evidence)
            for row in mapping_rows[:2]:
                self.complete_mapping_row(row)
                self.complete_evidence_for_candidate(evidence_rows, row["source_candidate_id"])
            mapping_rows[1]["review_normalized_exercise_id"] = "chest_opening_stretch_b"
            write_rows(mapping, mapping_fields, mapping_rows)
            write_rows(evidence, evidence_fields, evidence_rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "used by more than one exercise"
            ):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_exclude_requires_a_reason(self) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            mapping_rows[0]["review_decision"] = "EXCLUDE"
            write_rows(mapping, mapping_fields, mapping_rows)

            with self.assertRaisesRegex(
                result_validator.PipelineError, "exclusion reason is missing"
            ):
                result_validator.validate_review_results(batch, mapping, evidence)

    def test_fully_evidenced_include_is_structurally_valid_but_not_production_eligible(
        self,
    ) -> None:
        with workspace_directory() as root:
            batch = make_batch(root)
            mapping, evidence = result_copies(batch, root)
            mapping_fields, mapping_rows = read_rows(mapping)
            self.complete_mapping_row(mapping_rows[0])
            write_rows(mapping, mapping_fields, mapping_rows)
            evidence_fields, evidence_rows = read_rows(evidence)
            self.complete_evidence_for_candidate(
                evidence_rows, mapping_rows[0]["source_candidate_id"]
            )
            write_rows(evidence, evidence_fields, evidence_rows)

            result = result_validator.validate_review_results(batch, mapping, evidence)

            self.assertEqual(result["decision_counts"]["INCLUDE"], 1)
            self.assertEqual(result["review_complete_rows"], 1)
            self.assertFalse(result["production_eligible"])

    @staticmethod
    def complete_mapping_row(row: dict[str, str]) -> None:
        row.update(
            {
                "review_normalized_exercise_id": "chest_opening_stretch",
                "review_display_name_ko": "가슴 펴기 스트레칭",
                "review_taxonomy_code": "thoracic_mobility",
                "review_beginner_suitability": "YES",
                "review_execution_guidance_status": "APPROVED",
                "review_media_rights_status": "APPROVED",
                "review_domain_safety_status": "APPROVED",
                "review_decision": "INCLUDE",
                "reviewer_notes": "synthetic reviewed row",
            }
        )

    @staticmethod
    def complete_evidence_for_candidate(
        rows: list[dict[str, str]],
        candidate_id: str,
        omit_role: str | None = None,
    ) -> None:
        for row in rows:
            if row["source_candidate_id"] != candidate_id:
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
