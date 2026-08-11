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


@contextmanager
def workspace_directory() -> Iterator[Path]:
    # 저장소 안에 만들면 Windows 백신·인덱서가 새 파일을 스캔하며 핸들을 잡아
    # partial 디렉터리 rename이 WinError 5로 실패한다. OS 임시 디렉터리를 쓴다.
    path = Path(tempfile.mkdtemp(prefix="helkki-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def response_bytes(items: list[dict]) -> bytes:
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


def source_items() -> list[dict]:
    common = {
        "aggrp_nm": "공통",
        "trng_plc_nm": "실내",
        "tool_nm": "매트",
        "trng_mscl_part": "몸통",
        "set_cnt_nm": "",
        "rptt_tcnt_nm": "",
        "trng_hr_nm": "",
        "ecrg_cycl_nm": "",
        "vdo_desc": "원천 설명",
        "vdo_ttl_nm": "공통 영상",
    }
    return [
        {**common, "file_nm": "video-a.mp4", "trng_nm": "브릿지", "img_file_nm": "1.jpg"},
        {**common, "file_nm": "video-a.mp4", "trng_nm": "브릿지", "img_file_nm": "2.jpg"},
        {**common, "file_nm": "video-a.mp4", "trng_nm": "플랭크", "img_file_nm": "3.jpg"},
        {
            **common,
            "file_nm": "video-b.mp4",
            "trng_nm": "물에 뜨기",
            "aggrp_nm": "유아기",
            "trng_plc_nm": "수영장",
            "img_file_nm": "4.jpg",
        },
        {**common, "file_nm": "video-c.mp4", "trng_nm": "", "img_file_nm": "5.jpg"},
    ]


def make_snapshot(root: Path) -> Path:
    items = source_items()
    return kspo_fitness100_pipeline.collect_snapshot(
        service_key="test-secret",
        endpoint="training-video",
        output_root=root,
        page_size=100,
        fetcher=lambda _url, _timeout: response_bytes(items),
        now=datetime(2026, 8, 10, 6, 0, tzinfo=UTC),
    )


class ProfileKspoFitness100Tests(unittest.TestCase):
    def test_profiles_frame_rows_and_builds_draft_candidates(self) -> None:
        with workspace_directory() as work:
            snapshot = make_snapshot(work / "snapshots")
            profile_dir = profile_kspo_fitness100.create_profile(snapshot, work / "profiles")

            report = profile_kspo_fitness100.verify_profile(profile_dir)
            self.assertEqual(report["candidates"], 3)
            profile = json.loads((profile_dir / "profile.json").read_text(encoding="utf-8"))
            units = profile["unit_analysis"]
            self.assertEqual(units["raw_frame_rows"], 5)
            self.assertEqual(units["unique_video_files"], 3)
            self.assertEqual(units["named_candidate_pairs"], 3)
            self.assertEqual(units["unnamed_source_rows_excluded"], 1)
            self.assertEqual(units["mvp_scope_review_candidates"], 2)
            self.assertEqual(units["out_of_scope_review_candidates"], 1)

            candidates = [
                json.loads(line)
                for line in (profile_dir / "candidate_inventory.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            bridge = next(item for item in candidates if item["source_training_name"] == "브릿지")
            self.assertEqual(bridge["source_frame_rows"], 2)
            self.assertFalse(bridge["production_eligible"])
            self.assertIn("DOMAIN_SAFETY_REVIEW_REQUIRED", bridge["required_review_codes"])
            self.assertIn(
                "VIDEO_LENGTH_IS_NOT_EXERCISE_DURATION",
                profile["interpretation_guards"],
            )

    def test_child_pool_candidate_is_only_marked_out_of_scope(self) -> None:
        profile, candidates = profile_kspo_fitness100.build_profile(
            {
                "snapshot_id": "test",
                "source": {"source_id": "kspo_fitness100_video", "dataset_id": "15108846"},
                "retrieval": {"retrieved_at": "2026-08-10T06:00:00Z"},
            },
            source_items(),
        )
        candidate = next(item for item in candidates if item["source_training_name"] == "물에 뜨기")
        self.assertEqual(candidate["review_bucket"], "OUT_OF_SCOPE_REVIEW")
        self.assertIn("AGE_CHILD_ONLY", candidate["scope_reason_codes"])
        self.assertIn("PLACE_POOL_ONLY", candidate["scope_reason_codes"])
        self.assertEqual(profile["review"]["status"], "DRAFT")

    def test_verify_detects_tampered_inventory(self) -> None:
        with workspace_directory() as work:
            snapshot = make_snapshot(work / "snapshots")
            profile_dir = profile_kspo_fitness100.create_profile(snapshot, work / "profiles")
            inventory = profile_dir / "candidate_inventory.jsonl"
            inventory.write_bytes(inventory.read_bytes() + b" ")

            with self.assertRaisesRegex(profile_kspo_fitness100.PipelineError, "해시"):
                profile_kspo_fitness100.verify_profile(profile_dir)

    def test_verify_checks_csv_candidate_state_after_manifest_rehash(self) -> None:
        with workspace_directory() as work:
            snapshot = make_snapshot(work / "snapshots")
            profile_dir = profile_kspo_fitness100.create_profile(snapshot, work / "profiles")
            review_csv = profile_dir / "candidate_review.csv"
            content = review_csv.read_text(encoding="utf-8-sig").replace(
                ",DRAFT,false", ",DOMAIN_APPROVED,true", 1
            )
            review_csv.write_text(content, encoding="utf-8-sig", newline="")

            manifest_path = profile_dir / "profile_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            csv_entry = next(
                entry for entry in manifest["files"] if entry["path"] == "candidate_review.csv"
            )
            raw = review_csv.read_bytes()
            csv_entry["sha256"] = profile_kspo_fitness100.sha256_bytes(raw)
            csv_entry["bytes"] = len(raw)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(profile_kspo_fitness100.PipelineError, "승인되지 않은"):
                profile_kspo_fitness100.verify_profile(profile_dir)


if __name__ == "__main__":
    unittest.main()
