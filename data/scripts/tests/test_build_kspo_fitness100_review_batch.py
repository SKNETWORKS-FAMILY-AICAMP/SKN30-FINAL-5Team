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


def load_module(name: str, path: Path) -> ModuleType:
    # 캐시를 확인하지 않으면 같은 모듈이 두 번 실행되어 PipelineError 같은 클래스가
    # 서로 다른 객체로 두 개 생긴다. 그러면 except/assertRaises가 빗나간다.
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


kspo_fitness100_pipeline = load_module(
    "kspo_fitness100_pipeline", SCRIPT_DIR / "kspo_fitness100_pipeline.py"
)
profile_kspo_fitness100 = load_module(
    "profile_kspo_fitness100", SCRIPT_DIR / "profile_kspo_fitness100.py"
)
build_review_batch = load_module(
    "build_kspo_fitness100_review_batch",
    SCRIPT_DIR / "build_kspo_fitness100_review_batch.py",
)


@contextmanager
def workspace_directory() -> Iterator[Path]:
    path = Path.cwd() / f"test-work-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def candidate(
    candidate_id: str,
    name: str,
    file_name: str,
    place: str,
    tool: str | None,
    *,
    frame_rows: int = 1,
    missing_codes: tuple[str, ...] = (),
) -> dict[str, object]:
    required = [
        "DOMAIN_SAFETY_REVIEW_REQUIRED",
        "EXERCISE_TAXONOMY_MAPPING_REQUIRED",
        *missing_codes,
    ]
    return {
        "source_candidate_id": candidate_id,
        "source_file_name": file_name,
        "source_training_name": name,
        "source_descriptions": ["source description"],
        "age_groups": ["ADULT"],
        "places": [place],
        "tools": [tool] if tool else [],
        "muscle_parts": ["TRUNK"],
        "source_frame_rows": frame_rows,
        "review_bucket": "MVP_SCOPE_REVIEW",
        "required_review_codes": required,
        "review_status": "DRAFT",
        "production_eligible": False,
    }


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
        "aggrp_nm": "ADULT",
        "trng_plc_nm": "INDOOR",
        "tool_nm": "MAT",
        "trng_mscl_part": "TRUNK",
        "set_cnt_nm": "",
        "rptt_tcnt_nm": "",
        "trng_hr_nm": "",
        "ecrg_cycl_nm": "",
        "vdo_desc": "source description",
        "vdo_ttl_nm": "source title",
    }
    return [
        {**base, "file_nm": "video-a.mp4", "trng_nm": "alpha", "img_file_nm": "1.jpg"},
        {**base, "file_nm": "video-a.mp4", "trng_nm": "alpha", "img_file_nm": "2.jpg"},
        {
            **base,
            "file_nm": "video-b.mp4",
            "trng_nm": "beta",
            "tool_nm": "BAND",
            "img_file_nm": "3.jpg",
        },
        {
            **base,
            "file_nm": "video-c.mp4",
            "trng_nm": "gamma",
            "trng_plc_nm": "GYM",
            "img_file_nm": "4.jpg",
        },
        {
            **base,
            "file_nm": "video-d.mp4",
            "trng_nm": "alpha",
            "tool_nm": "",
            "img_file_nm": "5.jpg",
        },
    ]


def make_profile(root: Path) -> Path:
    items = source_items()
    snapshot = kspo_fitness100_pipeline.collect_snapshot(
        service_key="test-secret",
        endpoint="training-video",
        output_root=root / "snapshots",
        page_size=100,
        fetcher=lambda _url, _timeout: response_bytes(items),
        now=datetime(2026, 8, 10, 7, 0, tzinfo=UTC),
    )
    return profile_kspo_fitness100.create_profile(snapshot, root / "profiles")


def rehash_manifest_entry(batch_dir: Path, file_name: str) -> None:
    """Re-sign one batch file so verification tests reach content checks."""

    manifest_path = batch_dir / "review_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == file_name)
    raw = (batch_dir / file_name).read_bytes()
    entry["sha256"] = build_review_batch.sha256_bytes(raw)
    entry["bytes"] = len(raw)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class BuildKspoFitness100ReviewBatchTests(unittest.TestCase):
    def test_selection_deduplicates_name_and_prefers_source_completeness(self) -> None:
        rows = [
            candidate(
                "a-incomplete",
                "alpha",
                "video-z.mp4",
                "INDOOR",
                None,
                frame_rows=10,
                missing_codes=("TOOL_METADATA_UNSPECIFIED",),
            ),
            candidate("a-complete", "alpha", "video-a.mp4", "INDOOR", "MAT"),
            candidate("b", "beta", "video-b.mp4", "INDOOR", "BAND"),
            candidate("c", "gamma", "video-c.mp4", "GYM", "MACHINE"),
        ]

        selected, summary = build_review_batch.select_review_batch(rows, size=3)

        self.assertEqual(len({row["source_training_name"] for row in selected}), 3)
        alpha = next(row for row in selected if row["source_training_name"] == "alpha")
        self.assertEqual(alpha["source_candidate_id"], "a-complete")
        self.assertEqual(alpha["duplicate_name_candidate_count"], 2)
        self.assertEqual(summary["duplicate_source_training_name_groups"], 1)
        self.assertTrue(all(row["review_status"] == "DRAFT" for row in selected))
        self.assertTrue(all(row["production_eligible"] is False for row in selected))

    def test_builds_and_verifies_review_batch(self) -> None:
        with workspace_directory() as work:
            profile_dir = make_profile(work)
            batch_dir = build_review_batch.create_review_batch(
                profile_dir, work / "review_batches", size=3
            )

            result = build_review_batch.verify_review_batch(batch_dir)

            self.assertEqual(result["records"], 3)
            manifest = json.loads((batch_dir / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["review"]["status"], "DRAFT")
            self.assertFalse(manifest["review"]["production_eligible"])
            self.assertIn(
                "REVIEW_BATCH_IS_NOT_DOMAIN_SAFETY_APPROVAL",
                manifest["selection"]["interpretation_guards"],
            )

    def test_batch_emits_pending_review_columns_and_role_evidence_template(self) -> None:
        with workspace_directory() as work:
            profile_dir = make_profile(work)
            batch_dir = build_review_batch.create_review_batch(
                profile_dir, work / "review_batches", size=3
            )

            with (batch_dir / "review_batch.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                mapping_rows = list(csv.DictReader(handle))
            with (batch_dir / "catalog_review_records_template.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                evidence_rows = list(csv.DictReader(handle))

            for field, pending_value in build_review_batch.PENDING_REVIEW_FIELDS.items():
                self.assertTrue(
                    all(row[field] == pending_value for row in mapping_rows),
                    f"{field} must be generated as pending",
                )
            self.assertEqual(len(evidence_rows), 3 * 4)
            for row in evidence_rows:
                self.assertEqual(row["review_status_code"], "DRAFT")
                self.assertEqual(row["reviewer_reference"], "")
                self.assertEqual(row["evidence_reference"], "")
                self.assertEqual(row["reviewed_at"], "")
                self.assertTrue(row["target_reference"].startswith("kspo:"))
            for candidate_id in {row["source_candidate_id"] for row in mapping_rows}:
                roles = {
                    row["reviewer_role_code"]
                    for row in evidence_rows
                    if row["source_candidate_id"] == candidate_id
                }
                self.assertEqual(roles, set(build_review_batch.REVIEWER_ROLE_CODES))

    def test_verify_rejects_generated_batch_approved_without_review(self) -> None:
        with workspace_directory() as work:
            profile_dir = make_profile(work)
            batch_dir = build_review_batch.create_review_batch(
                profile_dir, work / "review_batches", size=3
            )
            jsonl_path = batch_dir / "review_batch.jsonl"
            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            first_row = json.loads(lines[0])
            first_row["review_decision"] = "INCLUDE"
            lines[0] = json.dumps(first_row, ensure_ascii=False, sort_keys=True)
            jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            rehash_manifest_entry(batch_dir, "review_batch.jsonl")

            with self.assertRaisesRegex(build_review_batch.PipelineError, "must remain pending"):
                build_review_batch.verify_review_batch(batch_dir)

    def test_verify_rejects_evidence_template_promoted_without_review(self) -> None:
        with workspace_directory() as work:
            profile_dir = make_profile(work)
            batch_dir = build_review_batch.create_review_batch(
                profile_dir, work / "review_batches", size=3
            )
            evidence_path = batch_dir / "catalog_review_records_template.jsonl"
            lines = evidence_path.read_text(encoding="utf-8").splitlines()
            first_row = json.loads(lines[0])
            first_row["review_status_code"] = "DOMAIN_APPROVED"
            lines[0] = json.dumps(first_row, ensure_ascii=False, sort_keys=True)
            evidence_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            rehash_manifest_entry(batch_dir, "catalog_review_records_template.jsonl")

            with self.assertRaisesRegex(
                build_review_batch.PipelineError, "must remain DRAFT and blank"
            ):
                build_review_batch.verify_review_batch(batch_dir)

    def test_verify_detects_tampered_batch(self) -> None:
        with workspace_directory() as work:
            profile_dir = make_profile(work)
            batch_dir = build_review_batch.create_review_batch(
                profile_dir, work / "review_batches", size=3
            )
            batch_file = batch_dir / "review_batch.jsonl"
            batch_file.write_bytes(batch_file.read_bytes() + b" ")

            with self.assertRaisesRegex(build_review_batch.PipelineError, "hash mismatch"):
                build_review_batch.verify_review_batch(batch_dir)

    def test_verify_detects_csv_identity_change_after_manifest_rehash(self) -> None:
        with workspace_directory() as work:
            profile_dir = make_profile(work)
            batch_dir = build_review_batch.create_review_batch(
                profile_dir, work / "review_batches", size=3
            )
            batch_file = batch_dir / "review_batch.jsonl"
            first_row = json.loads(batch_file.read_text(encoding="utf-8").splitlines()[0])
            csv_path = batch_dir / "review_batch.csv"
            csv_text = csv_path.read_text(encoding="utf-8-sig").replace(
                first_row["source_candidate_id"], "0" * 64, 1
            )
            csv_path.write_text(csv_text, encoding="utf-8-sig", newline="")

            manifest_path = batch_dir / "review_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            csv_entry = next(
                entry for entry in manifest["files"] if entry["path"] == "review_batch.csv"
            )
            raw = csv_path.read_bytes()
            csv_entry["sha256"] = build_review_batch.sha256_bytes(raw)
            csv_entry["bytes"] = len(raw)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                build_review_batch.PipelineError, "JSONL and CSV identity mismatch"
            ):
                build_review_batch.verify_review_batch(batch_dir)


if __name__ == "__main__":
    unittest.main()
