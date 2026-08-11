"""Collect hashes for official physical-activity references and verify raw facts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from kspo_fitness100_pipeline import PipelineError, sha256_bytes

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = DATA_ROOT / "raw" / "physical_activity_guidelines"
DEFAULT_MANIFEST = DEFAULT_RAW_DIR / "snapshot_manifest.json"
LOCAL_SOURCE_FILES = (
    "source_registry.json",
    "general_guideline_facts.json",
    "adult_compendium_mvp_reference_subset.jsonl",
)
ALLOWED_HOSTS = frozenset(
    {
        "www.who.int",
        "iris.who.int",
        "www.cdc.gov",
        "health.kdca.go.kr",
        "pacompendium.com",
    }
)
FetchResult = dict[str, object]
Fetcher = Callable[[str], FetchResult]


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"JSON is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"JSON root must be an object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise PipelineError(f"JSONL is missing: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"JSONL line {line_number} is invalid: {path}") from exc
        if not isinstance(value, dict):
            raise PipelineError(f"JSONL line {line_number} is not an object: {path}")
        rows.append(value)
    return rows


def validate_url(url: object) -> str:
    text = str(url).strip()
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise PipelineError(f"source URL is not an allowed official HTTPS endpoint: {text}")
    return text


def validate_registry(registry: dict[str, Any]) -> list[dict[str, Any]]:
    if registry.get("status") != "DRAFT" or registry.get("production_eligible") is not False:
        raise PipelineError("source registry must remain DRAFT and production-ineligible")
    if registry.get("review_method_code") != "AGENT_ONLY":
        raise PipelineError("source registry must use AGENT_ONLY")
    guards = registry.get("interpretation_guards")
    if not isinstance(guards, list) or "MET_VALUES_MUST_NOT_BE_CHANGED" not in guards:
        raise PipelineError("source registry is missing its MET value guard")
    endpoints = registry.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise PipelineError("source registry has no endpoints")
    seen: set[str] = set()
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise PipelineError("source endpoint must be an object")
        source_id = str(endpoint.get("source_id", ""))
        if not re.fullmatch(r"[A-Z0-9_]+", source_id) or source_id in seen:
            raise PipelineError(f"source ID is invalid or duplicated: {source_id}")
        seen.add(source_id)
        validate_url(endpoint.get("url"))
        if endpoint.get("collection_method_code") not in {
            "HTTP_RESPONSE_HASH",
            "BROWSER_VERIFIED_FACT_HASH",
        }:
            raise PipelineError(f"source collection method is invalid: {source_id}")
        if not endpoint.get("license_code") or not isinstance(endpoint.get("usage_guards"), list):
            raise PipelineError(f"source license metadata is incomplete: {source_id}")
    return endpoints


def validate_facts(facts: dict[str, Any], source_ids: set[str]) -> int:
    if facts.get("population_code") != "GENERAL_ADULT":
        raise PipelineError("raw guideline facts must target GENERAL_ADULT")
    if facts.get("status") != "DRAFT" or facts.get("production_eligible") is not False:
        raise PipelineError("raw guideline facts must remain DRAFT and production-ineligible")
    values = facts.get("facts")
    if not isinstance(values, list) or not values:
        raise PipelineError("raw guideline facts are missing")
    seen: set[str] = set()
    for fact in values:
        if not isinstance(fact, dict):
            raise PipelineError("guideline fact must be an object")
        fact_id = str(fact.get("fact_id", ""))
        if not re.fullmatch(r"[A-Z0-9_]+", fact_id) or fact_id in seen:
            raise PipelineError(f"guideline fact ID is invalid or duplicated: {fact_id}")
        seen.add(fact_id)
        if fact.get("source_id") not in source_ids or not fact.get("source_locator"):
            raise PipelineError(f"guideline fact source is invalid: {fact_id}")
    return len(values)


def validate_compendium(rows: list[dict[str, Any]], source_ids: set[str]) -> int:
    seen: set[str] = set()
    allowed_headings = {"Conditioning Exercise", "Walking"}
    for row in rows:
        code = str(row.get("activity_code", ""))
        if not re.fullmatch(r"\d{5}", code) or code in seen:
            raise PipelineError(f"Compendium activity code is invalid or duplicated: {code}")
        seen.add(code)
        if row.get("source_id") not in source_ids or row.get("source_id") != (
            "ADULT_COMPENDIUM_PDF_2024"
        ):
            raise PipelineError(f"Compendium source is invalid: {code}")
        if row.get("major_heading") not in allowed_headings:
            raise PipelineError(f"Compendium heading is outside the selected subset: {code}")
        met_value = row.get("met_value")
        if not isinstance(met_value, int | float) or met_value <= 0:
            raise PipelineError(f"Compendium MET value is invalid: {code}")
        if (
            not str(row.get("activity_description", "")).strip()
            or not str(row.get("source_locator", "")).strip()
            or row.get("review_status") != "DRAFT"
            or row.get("production_eligible") is not False
            or "normalized_exercise_id" in row
        ):
            raise PipelineError(f"Compendium row state or provenance is invalid: {code}")
    if not rows:
        raise PipelineError("Compendium subset is empty")
    return len(rows)


def local_file_entry(path: Path, raw_dir: Path, records: int) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(raw_dir).as_posix(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "records": records,
    }


def validate_raw_inputs(raw_dir: Path) -> tuple[dict[str, Any], list[dict[str, object]]]:
    registry_path = raw_dir / "source_registry.json"
    facts_path = raw_dir / "general_guideline_facts.json"
    compendium_path = raw_dir / "adult_compendium_mvp_reference_subset.jsonl"
    registry = load_json(registry_path)
    endpoints = validate_registry(registry)
    source_ids = {str(endpoint["source_id"]) for endpoint in endpoints}
    facts_count = validate_facts(load_json(facts_path), source_ids)
    compendium_rows = load_jsonl(compendium_path)
    compendium_count = validate_compendium(compendium_rows, source_ids)
    files = [
        local_file_entry(registry_path, raw_dir, len(endpoints)),
        local_file_entry(facts_path, raw_dir, facts_count),
        local_file_entry(compendium_path, raw_dir, compendium_count),
    ]
    return registry, files


def fact_hash_snapshot(raw_dir: Path, source_id: str, url: str) -> FetchResult:
    facts = load_json(raw_dir / "general_guideline_facts.json").get("facts")
    if not isinstance(facts, list):
        raise PipelineError("raw guideline facts are missing")
    selected = [
        fact for fact in facts if isinstance(fact, dict) and fact.get("source_id") == source_id
    ]
    if not selected:
        raise PipelineError(f"browser-verified source has no structured facts: {source_id}")
    canonical = (json.dumps(selected, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return {
        "final_url": url,
        "http_status": None,
        "content_type": "application/json",
        "content_sha256": sha256_bytes(canonical),
        "content_bytes": len(canonical),
        "hash_scope_code": "STRUCTURED_FACTS_NOT_HTTP_RESPONSE",
    }


def fetch_url(url: str) -> FetchResult:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        },
    )
    with urlopen(request, timeout=45) as response:  # noqa: S310 - allowlisted HTTPS only
        body = response.read()
        final_url = validate_url(response.geturl())
        return {
            "final_url": final_url,
            "http_status": response.status,
            "content_type": response.headers.get_content_type(),
            "content_sha256": sha256_bytes(body),
            "content_bytes": len(body),
        }


def parse_retrieved_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PipelineError("retrieved_at must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PipelineError("retrieved_at must include timezone information")
    return value


def build_manifest(
    raw_dir: Path, retrieved_at: str, fetcher: Fetcher = fetch_url
) -> dict[str, object]:
    retrieved_at = parse_retrieved_at(retrieved_at)
    registry, local_files = validate_raw_inputs(raw_dir)
    endpoints = registry["endpoints"]
    assert isinstance(endpoints, list)
    snapshots: list[dict[str, object]] = []
    for endpoint in endpoints:
        assert isinstance(endpoint, dict)
        requested_url = validate_url(endpoint["url"])
        method = str(endpoint.get("collection_method_code"))
        if method == "BROWSER_VERIFIED_FACT_HASH":
            result = fact_hash_snapshot(raw_dir, str(endpoint["source_id"]), requested_url)
        else:
            try:
                result = fetcher(requested_url)
            except OSError as exc:
                raise PipelineError(
                    f"official source fetch failed: {endpoint['source_id']}: {exc}"
                ) from exc
            if result.get("http_status") != 200:
                raise PipelineError(
                    f"official source returned non-200 status: {endpoint['source_id']}"
                )
        digest = str(result.get("content_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise PipelineError(f"official source hash is invalid: {endpoint['source_id']}")
        snapshots.append(
            {
                "source_id": endpoint["source_id"],
                "requested_url": requested_url,
                "final_url": validate_url(result.get("final_url")),
                "retrieved_at": retrieved_at,
                "collection_method_code": method,
                "hash_scope_code": result.get(
                    "hash_scope_code",
                    "HTTP_RESPONSE_BODY",
                ),
                "http_status": result.get("http_status"),
                "content_type": result.get("content_type"),
                "content_sha256": digest,
                "content_bytes": result.get("content_bytes"),
            }
        )
    return {
        "schema_version": "1.0",
        "collection_version": registry.get("collection_version"),
        "status": "DRAFT",
        "review_method_code": "AGENT_ONLY",
        "production_eligible": False,
        "retrieved_at": retrieved_at,
        "content_retention_code": "HASH_AND_MINIMUM_FACTS_ONLY",
        "snapshots": snapshots,
        "local_files": local_files,
    }


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_manifest(raw_dir: Path, manifest_path: Path) -> dict[str, object]:
    registry, expected_files = validate_raw_inputs(raw_dir)
    manifest = load_json(manifest_path)
    if (
        manifest.get("status") != "DRAFT"
        or manifest.get("review_method_code") != "AGENT_ONLY"
        or manifest.get("production_eligible") is not False
        or manifest.get("content_retention_code") != "HASH_AND_MINIMUM_FACTS_ONLY"
    ):
        raise PipelineError("snapshot manifest review state is invalid")
    parse_retrieved_at(str(manifest.get("retrieved_at", "")))
    if manifest.get("local_files") != expected_files:
        raise PipelineError("snapshot manifest local file hashes do not match")
    endpoints = registry["endpoints"]
    snapshots = manifest.get("snapshots")
    assert isinstance(endpoints, list)
    if not isinstance(snapshots, list) or len(snapshots) != len(endpoints):
        raise PipelineError("snapshot manifest endpoint count does not match")
    expected_ids = {endpoint["source_id"] for endpoint in endpoints if isinstance(endpoint, dict)}
    actual_ids: set[object] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise PipelineError("snapshot entry must be an object")
        actual_ids.add(snapshot.get("source_id"))
        validate_url(snapshot.get("requested_url"))
        validate_url(snapshot.get("final_url"))
        method = snapshot.get("collection_method_code")
        expected_status = 200 if method == "HTTP_RESPONSE_HASH" else None
        expected_scope = (
            "HTTP_RESPONSE_BODY"
            if method == "HTTP_RESPONSE_HASH"
            else "STRUCTURED_FACTS_NOT_HTTP_RESPONSE"
        )
        if (
            method not in {"HTTP_RESPONSE_HASH", "BROWSER_VERIFIED_FACT_HASH"}
            or snapshot.get("http_status") != expected_status
            or snapshot.get("hash_scope_code") != expected_scope
            or not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("content_sha256", "")))
            or not isinstance(snapshot.get("content_bytes"), int)
            or int(snapshot["content_bytes"]) <= 0
        ):
            raise PipelineError("snapshot HTTP metadata is invalid")
    if actual_ids != expected_ids:
        raise PipelineError("snapshot source IDs do not match registry")
    return {
        "status": "valid",
        "source_count": len(snapshots),
        "guideline_fact_count": expected_files[1]["records"],
        "compendium_activity_count": expected_files[2]["records"],
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    collect.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    collect.add_argument("--retrieved-at", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    verify.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "collect":
            write_manifest(args.manifest, build_manifest(args.raw_dir, args.retrieved_at))
        result = verify_manifest(args.raw_dir, args.manifest)
    except (PipelineError, OSError, ValueError, AssertionError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
