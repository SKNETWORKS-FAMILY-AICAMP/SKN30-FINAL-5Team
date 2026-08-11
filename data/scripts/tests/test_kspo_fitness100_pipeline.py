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
from urllib.parse import parse_qs, urlparse

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "kspo_fitness100_pipeline.py"
# 이미 로드된 모듈을 다시 실행하면 PipelineError 같은 클래스가 서로 다른 객체로
# 두 개 생겨 다른 테스트의 except/assertRaises가 빗나간다.
if "kspo_fitness100_pipeline" in sys.modules:
    kspo_fitness100_pipeline = sys.modules["kspo_fitness100_pipeline"]
else:
    SPEC = importlib.util.spec_from_file_location("kspo_fitness100_pipeline", SCRIPT_PATH)
    assert SPEC is not None and SPEC.loader is not None
    kspo_fitness100_pipeline = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = kspo_fitness100_pipeline
    SPEC.loader.exec_module(kspo_fitness100_pipeline)


@contextmanager
def workspace_directory() -> Iterator[Path]:
    # 저장소 안에 만들면 Windows 백신·인덱서가 새 파일을 스캔하며 핸들을 잡아
    # partial 디렉터리 rename이 WinError 5로 실패한다. OS 임시 디렉터리를 쓴다.
    path = Path(tempfile.mkdtemp(prefix="helkki-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def response_bytes(*, page_no: int, total_count: int, items: list[dict]) -> bytes:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {
                "pageNo": page_no,
                "totalCount": total_count,
                "items": {"item": items},
            },
        }
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class KspoFitness100PipelineTests(unittest.TestCase):
    def test_collects_two_pages_and_writes_secret_free_manifest(self) -> None:
        secret = "decoding-secret-value"

        def fake_fetcher(url: str, timeout: float) -> bytes:
            self.assertEqual(timeout, 5.0)
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query["serviceKey"], [secret])
            page_no = int(query["pageNo"][0])
            if page_no == 1:
                return response_bytes(
                    page_no=1,
                    total_count=3,
                    items=[{"id": "a"}, {"id": "b"}],
                )
            return response_bytes(page_no=2, total_count=3, items=[{"id": "c"}])

        with workspace_directory() as output_root:
            snapshot = kspo_fitness100_pipeline.collect_snapshot(
                service_key=secret,
                endpoint="training-video",
                output_root=output_root,
                page_size=2,
                timeout=5.0,
                fetcher=fake_fetcher,
                now=datetime(2026, 8, 10, 4, 5, tzinfo=UTC),
            )

            report = kspo_fitness100_pipeline.validate_snapshot(snapshot)
            self.assertEqual(report["pages"], 2)
            self.assertEqual(report["records"], 3)
            manifest_text = (snapshot / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn(secret, manifest_text)
            self.assertEqual(
                (snapshot / "pages" / "page-00001.json").read_bytes(),
                response_bytes(
                    page_no=1,
                    total_count=3,
                    items=[{"id": "a"}, {"id": "b"}],
                ),
            )

    def test_failed_api_response_does_not_complete_snapshot(self) -> None:
        failure = {
            "response": {
                "header": {"resultCode": "20", "resultMsg": "DENIED"},
                "body": {"totalCount": 0, "items": {"item": []}},
            }
        }

        with workspace_directory() as output_root:
            with self.assertRaises(kspo_fitness100_pipeline.PipelineError):
                kspo_fitness100_pipeline.collect_snapshot(
                    service_key="secret",
                    endpoint="training-video",
                    output_root=output_root,
                    fetcher=lambda _url, _timeout: json.dumps(failure).encode("utf-8"),
                    now=datetime(2026, 8, 10, 4, 6, tzinfo=UTC),
                )
            self.assertEqual(list(output_root.iterdir()), [])

    def test_record_count_mismatch_does_not_complete_snapshot(self) -> None:
        with workspace_directory() as output_root:
            with self.assertRaisesRegex(kspo_fitness100_pipeline.PipelineError, "수집 레코드 수"):
                kspo_fitness100_pipeline.collect_snapshot(
                    service_key="secret",
                    endpoint="training-video",
                    output_root=output_root,
                    page_size=10,
                    fetcher=lambda _url, _timeout: response_bytes(
                        page_no=1, total_count=2, items=[{"id": "only-one"}]
                    ),
                    now=datetime(2026, 8, 10, 4, 7, tzinfo=UTC),
                )
            self.assertEqual(list(output_root.iterdir()), [])

    def test_validation_detects_tampered_raw_page(self) -> None:
        with workspace_directory() as output_root:
            snapshot = kspo_fitness100_pipeline.collect_snapshot(
                service_key="secret",
                endpoint="routine",
                output_root=output_root,
                fetcher=lambda _url, _timeout: response_bytes(
                    page_no=1, total_count=1, items=[{"id": "routine-1"}]
                ),
                now=datetime(2026, 8, 10, 4, 8, tzinfo=UTC),
            )
            page = snapshot / "pages" / "page-00001.json"
            page.write_bytes(page.read_bytes() + b" ")

            with self.assertRaisesRegex(kspo_fitness100_pipeline.PipelineError, "해시"):
                kspo_fitness100_pipeline.validate_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
