"""Collect and verify immutable wger exercise-catalog metadata snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
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
SOURCE_ID = "wger_exercise_catalog"
SOURCE_TITLE = "wger exercise catalog"
SOURCE_PROVIDER = "wger project and community contributors"
SOURCE_URL = "https://wger.de/"
API_BASE_URL = "https://wger.de/api/v2"
API_DOCUMENTATION_URL = "https://wger.readthedocs.io/en/latest/api/api.html"
SOURCE_REPOSITORY_URL = "https://github.com/wger-project/wger"
RESOURCES = (
    "exerciseinfo",
    "equipment",
    "exercisecategory",
    "language",
    "license",
    "muscle",
)
DEFAULT_OUTPUT_ROOT = (
    Path(__file__).resolve().parents[1] / "raw" / SOURCE_ID / "snapshots"
)
USER_AGENT = "SKN30-wger-exercise-collector/0.1"


class PipelineError(RuntimeError):
    """A fail-closed collection or validation error safe to show to users."""


@dataclass(frozen=True)
class ParsedPage:
    total_count: int
    results: list[dict[str, object]]
    next_url: str | None
    previous_url: str | None


FetchBytes = Callable[[str, float], bytes]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _integer(value: object, field_name: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise PipelineError(f"{field_name} must not be negative")
    return parsed


def build_request_url(*, resource: str, limit: int, offset: int) -> str:
    if resource not in RESOURCES:
        raise PipelineError(f"unsupported wger resource: {resource}")
    if not 1 <= limit <= 1000:
        raise PipelineError("limit must be between 1 and 1000")
    if offset < 0:
        raise PipelineError("offset must not be negative")
    query = urlencode({"limit": limit, "offset": offset})
    return f"{API_BASE_URL}/{resource}/?{query}"


def fetch_with_retries(url: str, timeout: float) -> bytes:
    attempts = 3
    detail = "unknown error"
    for attempt in range(1, attempts + 1):
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
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
    raise PipelineError(f"wger API request failed {attempts} times ({detail})")


def parse_page(raw: bytes) -> ParsedPage:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("wger response is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise PipelineError("wger response root must be an object")
    total_count = _integer(payload.get("count"), "response.count")
    results = payload.get("results")
    if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
        raise PipelineError("wger response.results must be a list of objects")
    next_url = payload.get("next")
    previous_url = payload.get("previous")
    if next_url is not None and not isinstance(next_url, str):
        raise PipelineError("wger response.next must be a string or null")
    if previous_url is not None and not isinstance(previous_url, str):
        raise PipelineError("wger response.previous must be a string or null")
    return ParsedPage(total_count, results, next_url, previous_url)


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PipelineError(f"{field_name} must be an object")
    return value


def validate_exercise_item(item: dict[str, object]) -> None:
    exercise_id = _integer(item.get("id"), "exerciseinfo.id")
    if exercise_id < 1:
        raise PipelineError("exerciseinfo.id must be positive")
    uuid = item.get("uuid")
    if not isinstance(uuid, str) or not uuid.strip():
        raise PipelineError("exerciseinfo.uuid is missing")
    _mapping(item.get("category"), "exerciseinfo.category")
    license_info = _mapping(item.get("license"), "exerciseinfo.license")
    if not isinstance(license_info.get("id"), int):
        raise PipelineError("exerciseinfo.license.id is missing")
    if not isinstance(license_info.get("short_name"), str) or not license_info.get(
        "short_name"
    ):
        raise PipelineError("exerciseinfo.license.short_name is missing")
    for field in (
        "muscles",
        "muscles_secondary",
        "equipment",
        "images",
        "translations",
        "videos",
    ):
        value = item.get(field)
        if not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value):
            raise PipelineError(f"exerciseinfo.{field} must be a list of objects")
    for translation in item["translations"]:
        if not isinstance(translation.get("name"), str) or not translation["name"].strip():
            raise PipelineError("exercise translation name is missing")
        if not isinstance(translation.get("language"), int):
            raise PipelineError("exercise translation language is missing")
        if not isinstance(translation.get("license"), int):
            raise PipelineError("exercise translation license is missing")


def _manifest(
    *,
    snapshot_id: str,
    retrieved_at: str,
    page_size: int,
    resources: dict[str, dict[str, int]],
    files: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "source": {
            "source_id": SOURCE_ID,
            "title": SOURCE_TITLE,
            "provider": SOURCE_PROVIDER,
            "source_url": SOURCE_URL,
            "api_base_url": API_BASE_URL,
            "api_documentation_url": API_DOCUMENTATION_URL,
            "source_repository_url": SOURCE_REPOSITORY_URL,
            "data_license": {
                "mode": "PER_ENTRY_LICENSE",
                "attribution_metadata_required": True,
                "share_alike_may_apply": True,
                "license_reference_resource": "license",
            },
            "media_policy": {
                "metadata_urls_only": True,
                "image_binary_collected": False,
                "video_binary_collected": False,
            },
        },
        "retrieval": {
            "retrieved_at": retrieved_at,
            "result_type": "JSON",
            "page_size": page_size,
            "page_count": len(files),
        },
        "resources": resources,
        "pipeline": {
            "collector": "data/scripts/wger_exercise_pipeline.py",
            "version": PIPELINE_VERSION,
        },
        "review": {"status": "DRAFT", "production_eligible": False},
        "files": files,
    }


def collect_snapshot(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    page_size: int = 100,
    timeout: float = 30.0,
    fetcher: FetchBytes = fetch_with_retries,
    now: datetime | None = None,
) -> Path:
    if timeout <= 0:
        raise PipelineError("timeout must be positive")
    if not 1 <= page_size <= 1000:
        raise PipelineError("page_size must be between 1 and 1000")
    collected_at = now or datetime.now(timezone.utc)
    if collected_at.tzinfo is None:
        raise PipelineError("collection time must include timezone information")
    collected_at = collected_at.astimezone(timezone.utc).replace(microsecond=0)
    snapshot_id = f"{collected_at.strftime('%Y%m%dT%H%M%SZ')}-wger-exercise-catalog"
    retrieved_at = collected_at.isoformat().replace("+00:00", "Z")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    final_dir = output_root / snapshot_id
    partial_dir = output_root / f".{snapshot_id}.partial"
    if final_dir.exists():
        raise PipelineError(f"snapshot already exists: {snapshot_id}")
    try:
        partial_dir.mkdir()
    except FileExistsError as exc:
        raise PipelineError(f"partial snapshot already exists: {partial_dir.name}") from exc

    files: list[dict[str, object]] = []
    resource_summaries: dict[str, dict[str, int]] = {}
    try:
        for resource in RESOURCES:
            resource_dir = partial_dir / resource
            resource_dir.mkdir()
            total_count: int | None = None
            record_count = 0
            page_no = 1
            offset = 0
            while True:
                raw = fetcher(
                    build_request_url(resource=resource, limit=page_size, offset=offset),
                    timeout,
                )
                parsed = parse_page(raw)
                if total_count is None:
                    total_count = parsed.total_count
                elif parsed.total_count != total_count:
                    raise PipelineError(f"{resource} count changed between pages")
                if resource == "exerciseinfo":
                    for item in parsed.results:
                        validate_exercise_item(item)

                relative_path = Path(resource) / f"page-{page_no:05d}.json"
                page_path = partial_dir / relative_path
                page_path.write_bytes(raw)
                files.append(
                    {
                        "resource": resource,
                        "page": page_no,
                        "path": relative_path.as_posix(),
                        "sha256": sha256_bytes(raw),
                        "bytes": len(raw),
                        "records": len(parsed.results),
                    }
                )
                record_count += len(parsed.results)
                offset += len(parsed.results)
                if offset >= total_count:
                    break
                if not parsed.results:
                    raise PipelineError(f"{resource} returned an empty page before completion")
                page_no += 1

            if total_count is None or record_count != total_count:
                raise PipelineError(
                    f"{resource} collected {record_count} rows but API reported {total_count}"
                )
            if total_count < 1:
                raise PipelineError(f"required reference resource is empty: {resource}")
            resource_summaries[resource] = {
                "records": record_count,
                "pages": page_no,
            }

        manifest = _manifest(
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            page_size=page_size,
            resources=resource_summaries,
            files=files,
        )
        (partial_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        validate_snapshot(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def validate_snapshot(snapshot_dir: Path) -> dict[str, int | str]:
    snapshot_dir = snapshot_dir.resolve()
    manifest_path = snapshot_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError("manifest.json is missing") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("manifest.json is not valid UTF-8 JSON") from exc
    root = _mapping(manifest, "manifest")
    source = _mapping(root.get("source"), "manifest.source")
    retrieval = _mapping(root.get("retrieval"), "manifest.retrieval")
    pipeline = _mapping(root.get("pipeline"), "manifest.pipeline")
    review = _mapping(root.get("review"), "manifest.review")
    media_policy = _mapping(source.get("media_policy"), "manifest.source.media_policy")
    data_license = _mapping(source.get("data_license"), "manifest.source.data_license")

    if root.get("schema_version") != "1.0":
        raise PipelineError("unsupported manifest schema")
    if source.get("source_id") != SOURCE_ID or source.get("api_base_url") != API_BASE_URL:
        raise PipelineError("manifest source does not match wger allowlist")
    if data_license.get("mode") != "PER_ENTRY_LICENSE":
        raise PipelineError("wger data must preserve per-entry licenses")
    if media_policy != {
        "metadata_urls_only": True,
        "image_binary_collected": False,
        "video_binary_collected": False,
    }:
        raise PipelineError("wger media collection policy is invalid")
    if pipeline.get("version") != PIPELINE_VERSION:
        raise PipelineError("manifest pipeline version does not match verifier")
    if review != {"status": "DRAFT", "production_eligible": False}:
        raise PipelineError("wger snapshot must remain DRAFT and production-ineligible")

    resources = root.get("resources")
    if not isinstance(resources, dict) or set(resources) != set(RESOURCES):
        raise PipelineError("manifest resources do not match the allowlist")
    files = root.get("files")
    page_count = _integer(retrieval.get("page_count"), "retrieval.page_count")
    if not isinstance(files, list) or len(files) != page_count or page_count < len(RESOURCES):
        raise PipelineError("manifest file count is invalid")

    observed: dict[str, dict[str, int]] = {
        resource: {"records": 0, "pages": 0} for resource in RESOURCES
    }
    for entry_index, entry_value in enumerate(files):
        entry = _mapping(entry_value, f"files[{entry_index}]")
        resource = entry.get("resource")
        if not isinstance(resource, str) or resource not in RESOURCES:
            raise PipelineError("manifest file resource is not allowlisted")
        page = _integer(entry.get("page"), f"files[{entry_index}].page")
        expected_page = observed[resource]["pages"] + 1
        if page != expected_page:
            raise PipelineError(f"{resource} page sequence is not contiguous")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("manifest contains an unsafe file path")
        if relative.parts[0] != resource:
            raise PipelineError("manifest file path does not match its resource")
        try:
            raw = (snapshot_dir / relative).read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"raw page is missing: {relative.as_posix()}") from exc
        if sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"raw page hash mismatch: {relative.as_posix()}")
        if len(raw) != _integer(entry.get("bytes"), f"files[{entry_index}].bytes"):
            raise PipelineError(f"raw page size mismatch: {relative.as_posix()}")
        parsed = parse_page(raw)
        expected_records = _integer(
            entry.get("records"), f"files[{entry_index}].records"
        )
        if len(parsed.results) != expected_records:
            raise PipelineError(f"raw page record count mismatch: {relative.as_posix()}")
        if resource == "exerciseinfo":
            for item in parsed.results:
                validate_exercise_item(item)
        observed[resource]["records"] += len(parsed.results)
        observed[resource]["pages"] += 1

    for resource in RESOURCES:
        expected = _mapping(resources.get(resource), f"resources.{resource}")
        if observed[resource] != {
            "records": _integer(expected.get("records"), f"resources.{resource}.records"),
            "pages": _integer(expected.get("pages"), f"resources.{resource}.pages"),
        }:
            raise PipelineError(f"manifest summary mismatch for {resource}")
        if observed[resource]["records"] < 1:
            raise PipelineError(f"required resource is empty: {resource}")

    return {
        "snapshot_id": str(root.get("snapshot_id", "")),
        "pages": page_count,
        "exercises": observed["exerciseinfo"]["records"],
        "status": "valid",
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect", help="collect a raw wger snapshot")
    collect.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    collect.add_argument("--page-size", type=int, default=100)
    collect.add_argument("--timeout", type=float, default=30.0)
    validate = subparsers.add_parser("validate", help="validate a raw wger snapshot")
    validate.add_argument("snapshot", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "collect":
            snapshot = collect_snapshot(
                output_root=args.output_root,
                page_size=args.page_size,
                timeout=args.timeout,
            )
            result: dict[str, object] = {"status": "collected", "snapshot": str(snapshot)}
        else:
            result = validate_snapshot(args.snapshot)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
