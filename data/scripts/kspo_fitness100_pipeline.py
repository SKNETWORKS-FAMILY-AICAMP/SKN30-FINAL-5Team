"""Collect and verify immutable National Fitness 100 OpenAPI snapshots.

Only public exercise metadata is collected. The script deliberately does not
download media, normalize safety rules, or produce application seeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PIPELINE_VERSION = "0.1.0"
SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"
SOURCE_ID = "kspo_fitness100_video"
SOURCE_TITLE = "서울올림픽기념국민체육진흥공단_국민체력100 동영상 정보"
SOURCE_PROVIDER = "서울올림픽기념국민체육진흥공단"
DATASET_ID = "15108846"
DATASET_URL = "https://www.data.go.kr/data/15108846/openapi.do"
API_BASE_URL = "https://apis.data.go.kr/B551014/SRVC_TODZ_VDO_PKG"
DEFAULT_OUTPUT_ROOT = (
    Path(__file__).resolve().parents[1] / "raw" / "kspo_fitness100_video" / "snapshots"
)

ENDPOINTS = {
    "training-video": "TODZ_VDO_TRNG_VIDEO_I",
    "standard-fitness": "TODZ_VDO_STD_FTNS_I",
    "routine": "TODZ_VDO_ROUTINE_I",
}
SUCCESS_CODES = {"0", "00", "NORMAL_SERVICE"}


class PipelineError(RuntimeError):
    """A fail-closed collection or validation error safe to show to users."""


@dataclass(frozen=True)
class ParsedPage:
    total_count: int
    items: list[dict[str, object]]


FetchBytes = Callable[[str, float], bytes]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_request_url(
    *, service_key: str, endpoint: str, page_no: int, page_size: int
) -> str:
    if endpoint not in ENDPOINTS:
        raise PipelineError(f"지원하지 않는 endpoint입니다: {endpoint}")
    if not service_key.strip():
        raise PipelineError(f"{SERVICE_KEY_ENV}가 비어 있습니다.")
    if page_no < 1:
        raise PipelineError("page_no는 1 이상이어야 합니다.")
    if not 1 <= page_size <= 1000:
        raise PipelineError("page_size는 1~1000이어야 합니다.")

    query = urlencode(
        {
            "serviceKey": service_key,
            "pageNo": page_no,
            "numOfRows": page_size,
            "resultType": "JSON",
        }
    )
    return f"{API_BASE_URL}/{ENDPOINTS[endpoint]}?{query}"


def fetch_with_retries(url: str, timeout: float) -> bytes:
    """Fetch bytes without echoing the credential-bearing URL on failure."""
    attempts = 3
    for attempt in range(1, attempts + 1):
        request = Request(
            url,
            headers={"User-Agent": "SKN30-exercise-catalog-collector/0.1"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError as exc:
            detail = f"HTTP {exc.code}"
        except URLError:
            detail = "network error"
        except TimeoutError:
            detail = "timeout"
        except OSError:
            detail = "OS/network error"

        if attempt < attempts:
            time.sleep(2 ** (attempt - 1))

    raise PipelineError(f"공공 API 요청이 {attempts}회 실패했습니다 ({detail}).")


def _integer(value: object, field_name: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"응답의 {field_name}가 정수가 아닙니다.") from exc
    if parsed < 0:
        raise PipelineError(f"응답의 {field_name}가 음수입니다.")
    return parsed


def parse_page(raw: bytes, *, expected_page_no: int | None = None) -> ParsedPage:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("API 응답이 유효한 UTF-8 JSON이 아닙니다.") from exc
    if not isinstance(payload, dict):
        raise PipelineError("API 응답 최상위 값이 객체가 아닙니다.")

    response = payload.get("response", payload)
    if not isinstance(response, dict):
        raise PipelineError("API 응답의 response 객체가 없습니다.")
    header = response.get("header")
    body = response.get("body")
    if not isinstance(header, dict) or not isinstance(body, dict):
        raise PipelineError("API 응답의 header 또는 body 객체가 없습니다.")

    result_code = str(header.get("resultCode", "")).strip()
    if result_code not in SUCCESS_CODES:
        raise PipelineError(f"API가 성공 코드가 아닌 값을 반환했습니다: {result_code or 'missing'}")

    total_count = _integer(body.get("totalCount"), "totalCount")
    if expected_page_no is not None and body.get("pageNo") is not None:
        actual_page_no = _integer(body.get("pageNo"), "pageNo")
        if actual_page_no != expected_page_no:
            raise PipelineError(
                f"요청 페이지({expected_page_no})와 응답 페이지({actual_page_no})가 다릅니다."
            )

    items_container = body.get("items")
    if items_container in (None, ""):
        items_value: object = []
    elif isinstance(items_container, dict):
        items_value = items_container.get("item", [])
    elif isinstance(items_container, list):
        items_value = items_container
    else:
        raise PipelineError("API 응답의 items 형식을 해석할 수 없습니다.")

    if items_value in (None, ""):
        items: list[dict[str, object]] = []
    elif isinstance(items_value, dict):
        items = [items_value]
    elif isinstance(items_value, list) and all(
        isinstance(item, dict) for item in items_value
    ):
        items = items_value
    else:
        raise PipelineError("API 응답의 item 목록 형식을 해석할 수 없습니다.")

    return ParsedPage(total_count=total_count, items=items)


def _manifest(
    *,
    snapshot_id: str,
    retrieved_at: str,
    endpoint: str,
    page_size: int,
    total_count: int,
    files: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "source": {
            "source_id": SOURCE_ID,
            "title": SOURCE_TITLE,
            "provider": SOURCE_PROVIDER,
            "dataset_id": DATASET_ID,
            "dataset_url": DATASET_URL,
            "api_base_url": API_BASE_URL,
            "endpoint": endpoint,
            "operation": ENDPOINTS[endpoint],
            "license": {
                "code": "KOGL_TYPE_1",
                "name": "공공누리 제1유형",
                "attribution_required": True,
                "third_party_rights_included": True,
            },
        },
        "retrieval": {
            "retrieved_at": retrieved_at,
            "result_type": "JSON",
            "page_size": page_size,
            "page_count": len(files),
            "total_count": total_count,
        },
        "pipeline": {
            "collector": "data/scripts/kspo_fitness100_pipeline.py",
            "version": PIPELINE_VERSION,
        },
        "review": {"status": "DRAFT", "production_eligible": False},
        "files": files,
    }


def collect_snapshot(
    *,
    service_key: str,
    endpoint: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    page_size: int = 100,
    timeout: float = 30.0,
    fetcher: FetchBytes = fetch_with_retries,
    now: datetime | None = None,
) -> Path:
    if timeout <= 0:
        raise PipelineError("timeout은 0보다 커야 합니다.")
    if endpoint not in ENDPOINTS:
        raise PipelineError(f"지원하지 않는 endpoint입니다: {endpoint}")

    collected_at = now or datetime.now(timezone.utc)
    if collected_at.tzinfo is None:
        raise PipelineError("수집 시각에는 timezone 정보가 필요합니다.")
    collected_at = collected_at.astimezone(timezone.utc).replace(microsecond=0)
    snapshot_id = f"{collected_at.strftime('%Y%m%dT%H%M%SZ')}-{endpoint}"
    retrieved_at = collected_at.isoformat().replace("+00:00", "Z")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    final_dir = output_root / snapshot_id
    if final_dir.exists():
        raise PipelineError(f"동일한 snapshot이 이미 존재합니다: {snapshot_id}")

    temp_dir = output_root / f".{snapshot_id}.partial"
    try:
        temp_dir.mkdir()
    except FileExistsError as exc:
        raise PipelineError(
            f"미완료 snapshot 작업 디렉터리가 이미 존재합니다: {temp_dir.name}"
        ) from exc
    pages_dir = temp_dir / "pages"
    pages_dir.mkdir()
    files: list[dict[str, object]] = []
    total_count: int | None = None
    total_records = 0

    try:
        page_no = 1
        while True:
            request_url = build_request_url(
                service_key=service_key,
                endpoint=endpoint,
                page_no=page_no,
                page_size=page_size,
            )
            raw = fetcher(request_url, timeout)
            parsed = parse_page(raw, expected_page_no=page_no)

            if total_count is None:
                total_count = parsed.total_count
            elif parsed.total_count != total_count:
                raise PipelineError("페이지 사이에서 totalCount가 변경되었습니다.")

            relative_path = Path("pages") / f"page-{page_no:05d}.json"
            page_path = temp_dir / relative_path
            page_path.write_bytes(raw)
            files.append(
                {
                    "path": relative_path.as_posix(),
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "records": len(parsed.items),
                }
            )
            total_records += len(parsed.items)

            expected_pages = max(1, math.ceil(total_count / page_size))
            if page_no >= expected_pages:
                break
            page_no += 1

        if total_count is None or total_records != total_count:
            raise PipelineError(
                f"수집 레코드 수({total_records})와 totalCount({total_count})가 다릅니다."
            )

        manifest = _manifest(
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            endpoint=endpoint,
            page_size=page_size,
            total_count=total_count,
            files=files,
        )
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        validate_snapshot(temp_dir)
        temp_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _required_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PipelineError(f"manifest의 {name} 객체가 없습니다.")
    return value


def validate_snapshot(snapshot_dir: Path) -> dict[str, int | str]:
    snapshot_dir = snapshot_dir.resolve()
    manifest_path = snapshot_dir / "manifest.json"
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
    except FileNotFoundError as exc:
        raise PipelineError("manifest.json이 없습니다.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("manifest.json이 유효한 UTF-8 JSON이 아닙니다.") from exc

    if "serviceKey=" in manifest_text or SERVICE_KEY_ENV in manifest_text:
        raise PipelineError("manifest에 서비스키 정보가 포함되어 있습니다.")
    root = _required_mapping(manifest, "root")
    source = _required_mapping(root.get("source"), "source")
    retrieval = _required_mapping(root.get("retrieval"), "retrieval")
    pipeline = _required_mapping(root.get("pipeline"), "pipeline")
    review = _required_mapping(root.get("review"), "review")
    license_info = _required_mapping(source.get("license"), "source.license")

    if root.get("schema_version") != "1.0":
        raise PipelineError("지원하지 않는 manifest schema_version입니다.")
    if source.get("source_id") != SOURCE_ID or source.get("dataset_id") != DATASET_ID:
        raise PipelineError("manifest의 출처 식별자가 예상 값과 다릅니다.")
    endpoint = source.get("endpoint")
    if (
        not isinstance(endpoint, str)
        or endpoint not in ENDPOINTS
        or source.get("operation") != ENDPOINTS[endpoint]
    ):
        raise PipelineError("manifest의 endpoint가 allowlist와 일치하지 않습니다.")
    if license_info.get("code") != "KOGL_TYPE_1":
        raise PipelineError("manifest의 라이선스가 공공누리 제1유형이 아닙니다.")
    if pipeline.get("version") != PIPELINE_VERSION:
        raise PipelineError("manifest의 pipeline version이 현재 검증기와 다릅니다.")
    if review.get("status") != "DRAFT" or review.get("production_eligible") is not False:
        raise PipelineError("raw snapshot은 DRAFT/production_eligible=false여야 합니다.")

    total_count = _integer(retrieval.get("total_count"), "retrieval.total_count")
    page_count = _integer(retrieval.get("page_count"), "retrieval.page_count")
    files = root.get("files")
    if not isinstance(files, list) or len(files) != page_count or page_count < 1:
        raise PipelineError("manifest의 files 수와 page_count가 일치하지 않습니다.")

    record_count = 0
    observed_total: int | None = None
    for index, entry_value in enumerate(files, start=1):
        entry = _required_mapping(entry_value, f"files[{index - 1}]")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("manifest에 안전하지 않은 파일 경로가 있습니다.")
        page_path = snapshot_dir / relative
        try:
            raw = page_path.read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"원문 페이지가 없습니다: {relative.as_posix()}") from exc
        if sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"원문 페이지 해시가 다릅니다: {relative.as_posix()}")
        if len(raw) != _integer(entry.get("bytes"), f"files[{index - 1}].bytes"):
            raise PipelineError(f"원문 페이지 크기가 다릅니다: {relative.as_posix()}")

        parsed = parse_page(raw, expected_page_no=index)
        if observed_total is None:
            observed_total = parsed.total_count
        elif parsed.total_count != observed_total:
            raise PipelineError("원문 페이지 사이에서 totalCount가 다릅니다.")
        expected_records = _integer(
            entry.get("records"), f"files[{index - 1}].records"
        )
        if len(parsed.items) != expected_records:
            raise PipelineError(f"원문 페이지 레코드 수가 다릅니다: {relative.as_posix()}")
        record_count += len(parsed.items)

    if observed_total != total_count or record_count != total_count:
        raise PipelineError("manifest와 원문 페이지의 전체 레코드 수가 다릅니다.")

    return {
        "snapshot_id": str(root.get("snapshot_id", "")),
        "pages": page_count,
        "records": record_count,
        "status": "valid",
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="새 raw snapshot 수집")
    collect.add_argument("--endpoint", choices=sorted(ENDPOINTS), default="training-video")
    collect.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    collect.add_argument("--page-size", type=int, default=100)
    collect.add_argument("--timeout", type=float, default=30.0)

    validate = subparsers.add_parser("validate", help="기존 raw snapshot 재검증")
    validate.add_argument("snapshot", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "collect":
            service_key = os.environ.get(SERVICE_KEY_ENV, "")
            snapshot = collect_snapshot(
                service_key=service_key,
                endpoint=args.endpoint,
                output_root=args.output_root,
                page_size=args.page_size,
                timeout=args.timeout,
            )
            result: dict[str, object] = {
                "status": "collected",
                "snapshot": str(snapshot),
            }
        else:
            result = validate_snapshot(args.snapshot)
    except (PipelineError, OSError) as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
