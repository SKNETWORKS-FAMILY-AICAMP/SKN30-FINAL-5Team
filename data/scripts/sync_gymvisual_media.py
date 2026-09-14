#!/usr/bin/env python3
"""Validate Gymvisual media and create canonical S3 aliases.

This script deliberately uses the installed AWS CLI rather than adding a
runtime SDK dependency. It performs every source and destination preflight
before copying, preserves the original ``images/`` and ``videos/`` objects,
and writes the rights-review input only after all canonical objects verify.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
REPRESENTATIVE_PATH = (
    REPO_ROOT / "data/generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv"
)
CURRENT_CATALOG_PATH = (
    REPO_ROOT
    / "data/generated/exercise-catalog-v2.0.4-final/backend_bundle/catalog/exercises.jsonl"
)
CURRENT_REGISTRY_PATH = (
    REPO_ROOT
    / "data/generated/exercise-catalog-v2.0.4-final"
    / "backend_bundle/catalog/input/representative_exercises.csv"
)
RAW_EXERCISES_PATH = REPO_ROOT / "data/raw/gym_visual/exercises.json"
RAW_SOURCE_PATH = REPO_ROOT / "data/raw/gym_visual/source.json"
IMAGE_DIR = REPO_ROOT / "data/media/images"
VIDEO_DIR = REPO_ROOT / "data/media/videos"
REVIEW_PATH = REPO_ROOT / "data/validation/review_results/gymvisual_media_reviewed.csv"
MAPPING_MANIFEST_PATH = (
    REPO_ROOT / "data/generated/exercise-catalog-v2.0.0-final/gymvisual_media_mapping_manifest.csv"
)
BUCKET = "exercise-app-media-343953861875-ap-northeast-2-an"
REGION = "ap-northeast-2"
# The original reviewed set has 87 rows. v2.0.4 carries four additional
# Gymvisual-origin SEPARATE_EXERCISE records with exact source identities, so
# the sync inventory is the union rather than either catalog in isolation.
EXPECTED_COUNT = 91
# Keep AWS CLI authentication refreshes below the account's OAuth rate limit.
S3_WORKERS = 4
MAPPING_MANIFEST_COLUMNS = (
    "representative_exercise_id",
    "source_identity",
    "stable_code",
    "source_image_s3_key",
    "source_gif_s3_key",
)
REVIEW_COLUMNS = (
    "representative_exercise_id",
    "source_identity",
    "source_image_s3_key",
    "source_gif_s3_key",
    "gif_s3_key",
    "thumbnail_s3_key",
    "media_status",
    "source_gif_content_type",
    "source_gif_content_length",
    "source_gif_etag",
    "source_gif_checksum_algorithm",
    "source_gif_checksum",
    "source_image_content_type",
    "source_image_content_length",
    "source_image_etag",
    "source_image_checksum_algorithm",
    "source_image_checksum",
    "gif_content_type",
    "gif_content_length",
    "gif_etag",
    "gif_checksum_algorithm",
    "gif_checksum",
    "thumbnail_content_type",
    "thumbnail_content_length",
    "thumbnail_etag",
    "thumbnail_checksum_algorithm",
    "thumbnail_checksum",
    "s3_technical_status",
    "verified_at",
    "rights_review_status",
    "rights_reviewer",
    "rights_reviewed_at",
    "rights_evidence_reference",
    "production_eligibility",
    "backend_visibility",
)
_MEDIA_NAME = re.compile(r"^(?P<source_identity>[0-9]+)-[^/]+\.(?P<extension>jpg|gif)$")


class SyncError(RuntimeError):
    """Raised when media validation cannot prove a safe result."""


class S3Client(Protocol):
    def head_object(self, bucket: str, key: str) -> dict[str, Any] | None: ...

    def put_object(self, bucket: str, key: str, body: Path, content_type: str) -> None: ...

    def copy_object(self, bucket: str, source_key: str, destination_key: str) -> None: ...


class MediaPair(NamedTuple):
    representative_exercise_id: str
    source_identity: str
    stable_code: str
    image_path: Path | None
    video_path: Path | None
    image_key: str
    video_key: str
    gif_s3_key: str
    thumbnail_s3_key: str


class AwsCliS3Client:
    def __init__(self, region: str) -> None:
        self.region = region

    def _run(self, args: list[str]) -> dict[str, Any] | None:
        command = ["aws", "s3api", *args, "--region", self.region, "--output", "json"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            try:
                return json.loads(result.stdout or "{}")
            except json.JSONDecodeError as error:
                raise SyncError("AWS CLI returned invalid JSON") from error
        error_text = result.stderr.strip()
        if "Not Found" in error_text or "404" in error_text or "NoSuchKey" in error_text:
            return None
        raise SyncError(f"AWS CLI failed: {error_text[-500:]}")

    def head_object(self, bucket: str, key: str) -> dict[str, Any] | None:
        return self._run(["head-object", "--bucket", bucket, "--key", key])

    def put_object(self, bucket: str, key: str, body: Path, content_type: str) -> None:
        result = self._run(
            [
                "put-object",
                "--bucket",
                bucket,
                "--key",
                key,
                "--body",
                str(body),
                "--content-type",
                content_type,
            ]
        )
        if result is None:
            raise SyncError(f"S3 upload returned no result: {key}")

    def copy_object(self, bucket: str, source_key: str, destination_key: str) -> None:
        result = self._run(
            [
                "copy-object",
                "--copy-source",
                f"{bucket}/{source_key}",
                "--bucket",
                bucket,
                "--key",
                destination_key,
                "--metadata-directive",
                "COPY",
            ]
        )
        if result is None:
            raise SyncError(f"S3 copy returned no result: {source_key} -> {destination_key}")


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise SyncError(f"CSV header missing: {path}")
            return [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    except OSError as error:
        raise SyncError(f"cannot read {path}") from error


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"invalid JSON: {path}") from error


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"invalid JSONL: {path}") from error


def _unique_index(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    values = [str(row.get(key, "")) for row in rows]
    if any(not value for value in values) or len(values) != len(set(values)):
        raise SyncError(f"{label} must have unique non-empty {key}")
    return {str(row[key]): row for row in rows}


def _media_files(directory: Path, extension: str) -> dict[str, list[Path]]:
    if not directory.is_dir():
        return {}
    result: dict[str, list[Path]] = {}
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() != f".{extension}":
            continue
        match = _MEDIA_NAME.fullmatch(path.name)
        if match is None or match.group("extension") != extension:
            raise SyncError(f"invalid Gymvisual media filename: {path.name}")
        result.setdefault(match.group("source_identity"), []).append(path)
    return result


def gymvisual_candidates() -> list[dict[str, str]]:
    """Return every exact Gymvisual identity needed by reviewed/current catalogs."""

    legacy = [
        row for row in read_csv(REPRESENTATIVE_PATH) if row.get("source_track") == "gymvisual"
    ]
    registry = _unique_index(
        read_csv(CURRENT_REGISTRY_PATH), "stable_code", "current representative registry"
    )
    current: list[dict[str, str]] = []
    for row in read_jsonl(CURRENT_CATALOG_PATH):
        if row.get("source_track") != "gymvisual":
            continue
        stable_code = str(row.get("stable_code", ""))
        registered = registry.get(stable_code)
        if registered is None:
            raise SyncError(f"current Gymvisual exercise is absent from registry: {stable_code}")
        current.append(
            {
                "representative_exercise_id": registered["representative_exercise_id"],
                "source_track": "gymvisual",
                "source_identity": str(row.get("source_identity", "")),
                "stable_code": stable_code,
            }
        )

    combined: dict[str, dict[str, str]] = {}
    for row in [*legacy, *current]:
        representative_id = row.get("representative_exercise_id", "")
        normalized = {
            "representative_exercise_id": representative_id,
            "source_track": "gymvisual",
            "source_identity": row.get("source_identity", ""),
            "stable_code": row.get("stable_code", ""),
        }
        source_identity = normalized["source_identity"]
        prior = combined.get(source_identity)
        if prior is not None:
            # Current catalogs may rename a stable code while preserving the
            # same Gymvisual source identity. Keep the already-reviewed alias
            # rather than copying identical bytes to a second canonical key.
            continue
        combined[source_identity] = normalized
    return sorted(combined.values(), key=lambda row: row["representative_exercise_id"])


def validate_local_media() -> list[MediaPair]:
    gymvisual = gymvisual_candidates()
    if len(gymvisual) != EXPECTED_COUNT:
        raise SyncError(
            f"expected {EXPECTED_COUNT} Gymvisual representatives, got {len(gymvisual)}"
        )
    _unique_index(gymvisual, "representative_exercise_id", "representatives")
    identities = [row.get("source_identity", "") for row in gymvisual]
    if any(not identity for identity in identities) or len(identities) != len(set(identities)):
        raise SyncError("Gymvisual source_identity values must be unique and non-empty")

    raw_rows = read_json(RAW_EXERCISES_PATH)
    if not isinstance(raw_rows, list):
        raise SyncError("Gymvisual exercises.json must be an array")
    source_manifest = read_json(RAW_SOURCE_PATH)
    if source_manifest.get("record_count") != len(raw_rows):
        raise SyncError("Gymvisual source manifest record_count mismatch")
    raw_by_id = _unique_index(raw_rows, "id", "Gymvisual raw exercises")
    image_files = _media_files(IMAGE_DIR, "jpg")
    video_files = _media_files(VIDEO_DIR, "gif")
    expected_identities = set(identities)
    if IMAGE_DIR.is_dir() and set(image_files) != expected_identities:
        raise SyncError("Gymvisual local JPG files have missing or extra source identities")
    if VIDEO_DIR.is_dir() and set(video_files) != expected_identities:
        raise SyncError("Gymvisual local GIF files have missing or extra source identities")
    if any(len(paths) != 1 for paths in image_files.values()) or any(
        len(paths) != 1 for paths in video_files.values()
    ):
        raise SyncError("each Gymvisual source_identity must have exactly one JPG and one GIF")

    pairs: list[MediaPair] = []
    for row in sorted(gymvisual, key=lambda item: item["representative_exercise_id"]):
        representative_id = row["representative_exercise_id"]
        source_identity = row["source_identity"]
        raw = raw_by_id.get(source_identity)
        if raw is None:
            raise SyncError(f"Gymvisual raw exercise missing: {source_identity}")
        image_name = Path(str(raw.get("image", ""))).name
        gif_name = Path(str(raw.get("gif_url", ""))).name
        image_path = image_files.get(source_identity, [None])[0]
        video_path = video_files.get(source_identity, [None])[0]
        if image_path is not None and image_path.name != image_name:
            raise SyncError(f"raw/local image basename mismatch: {source_identity}")
        if video_path is not None and video_path.name != gif_name:
            raise SyncError(f"raw/local media basename mismatch: {source_identity}")
        if not str(raw.get("image", "")).startswith("images/") or not str(
            raw.get("gif_url", "")
        ).startswith("videos/"):
            raise SyncError(f"unexpected raw Gymvisual media key: {source_identity}")
        pairs.append(
            MediaPair(
                representative_exercise_id=representative_id,
                source_identity=source_identity,
                stable_code=row["stable_code"],
                image_path=image_path,
                video_path=video_path,
                # The raw source references are the source S3 keys. Their
                # basenames were checked against the source_identity-prefixed
                # local files above; no exercise-name matching is involved.
                image_key=str(raw["image"]).strip(),
                video_key=str(raw["gif_url"]).strip(),
                gif_s3_key=f"catalog-media/gymvisual/{row['stable_code']}/demo.gif",
                thumbnail_s3_key=f"catalog-media/gymvisual/{row['stable_code']}/thumbnail.jpg",
            )
        )
    if len({pair.stable_code for pair in pairs}) != EXPECTED_COUNT:
        raise SyncError("Gymvisual stable_code values must be unique")
    return pairs


def write_mapping_manifest(pairs: list[MediaPair], path: Path = MAPPING_MANIFEST_PATH) -> None:
    """Write the source-to-catalog traceability manifest.

    Source S3 keys intentionally live only in this manifest. The public final
    media artifact is projected separately and contains the canonical GIF key.
    """
    if len(pairs) != EXPECTED_COUNT:
        raise SyncError("cannot write an incomplete Gymvisual mapping manifest")
    rows = [
        {
            "representative_exercise_id": pair.representative_exercise_id,
            "source_identity": pair.source_identity,
            "stable_code": pair.stable_code,
            "source_image_s3_key": pair.image_key,
            "source_gif_s3_key": pair.video_key,
        }
        for pair in sorted(pairs, key=lambda item: item.representative_exercise_id)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        writer = csv.DictWriter(
            handle,
            fieldnames=MAPPING_MANIFEST_COLUMNS,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def _content_type(head: dict[str, Any]) -> str:
    return str(head.get("ContentType", "")).lower()


def _same_object(source: dict[str, Any], destination: dict[str, Any]) -> bool:
    if source.get("ContentLength") != destination.get("ContentLength"):
        return False
    source_checksums = {
        key: value for key, value in source.items() if key.startswith("Checksum") and value
    }
    destination_checksums = {
        key: value for key, value in destination.items() if key.startswith("Checksum") and value
    }
    common = set(source_checksums) & set(destination_checksums)
    if common and any(source_checksums[key] == destination_checksums[key] for key in common):
        return True
    # ETag equality is only used as an S3 object identity signal here; it is
    # never interpreted as a file hash, including for multipart uploads.
    return bool(source.get("ETag") and source.get("ETag") == destination.get("ETag"))


def _head_many(client: S3Client, bucket: str, keys: list[str]) -> dict[str, dict[str, Any] | None]:
    """Read S3 metadata concurrently while preserving deterministic callers."""
    if not keys:
        return {}
    results: dict[str, dict[str, Any] | None] = {}
    with ThreadPoolExecutor(max_workers=min(S3_WORKERS, len(keys))) as executor:
        futures = {executor.submit(client.head_object, bucket, key): key for key in keys}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _source_specs(pairs: list[MediaPair]) -> dict[str, tuple[Path | None, str]]:
    return {
        key: (path, expected_type)
        for pair in pairs
        for key, path, expected_type in (
            (pair.image_key, pair.image_path, "image/jpeg"),
            (pair.video_key, pair.video_path, "image/gif"),
        )
    }


def _validate_source_heads(
    source_specs: dict[str, tuple[Path | None, str]],
    source_heads: dict[str, dict[str, Any] | None],
) -> None:
    for key, (path, expected_type) in source_specs.items():
        head = source_heads[key]
        if head is None:
            raise SyncError(f"S3 source object missing: {key}")
        if _content_type(head) != expected_type:
            raise SyncError(f"S3 source Content-Type mismatch: {key}")
        content_length = head.get("ContentLength")
        if not isinstance(content_length, int) or content_length <= 0:
            raise SyncError(f"S3 source Content-Length must be > 0: {key}")
        if path is not None and content_length != path.stat().st_size:
            raise SyncError(f"S3 source size mismatch: {key}")


def validate_source_objects(
    pairs: list[MediaPair], client: S3Client, bucket: str
) -> dict[str, dict[str, Any]]:
    source_specs = _source_specs(pairs)
    source_heads = _head_many(client, bucket, list(source_specs))
    _validate_source_heads(source_specs, source_heads)
    return {key: head for key, head in source_heads.items() if head is not None}


def ensure_source_objects(
    pairs: list[MediaPair], client: S3Client, bucket: str
) -> tuple[int, int, dict[str, dict[str, Any]]]:
    """Reuse valid sources or upload missing local sources without overwriting."""
    source_specs = _source_specs(pairs)
    source_heads = _head_many(client, bucket, list(source_specs))
    uploaded = 0
    for key, (path, expected_type) in source_specs.items():
        if source_heads[key] is not None:
            continue
        if path is None:
            raise SyncError(f"S3 source object missing and no local bytes available: {key}")
        client.put_object(bucket, key, path, expected_type)
        uploaded += 1
    source_heads = _head_many(client, bucket, list(source_specs))
    _validate_source_heads(source_specs, source_heads)
    return (
        uploaded,
        len(source_specs) - uploaded,
        {key: head for key, head in source_heads.items() if head is not None},
    )


def copy_canonical_aliases(
    pairs: list[MediaPair], client: S3Client, bucket: str
) -> tuple[int, int]:
    for pair in pairs:
        expected = {
            f"catalog-media/gymvisual/{pair.stable_code}/demo.gif",
            f"catalog-media/gymvisual/{pair.stable_code}/thumbnail.jpg",
        }
        if {pair.gif_s3_key, pair.thumbnail_s3_key} != expected:
            raise SyncError(f"canonical key does not match stable_code: {pair.stable_code}")
    alias_specs = [
        (source_key, destination_key, expected_type)
        for pair in pairs
        for source_key, destination_key, expected_type in (
            (pair.video_key, pair.gif_s3_key, "image/gif"),
            (pair.image_key, pair.thumbnail_s3_key, "image/jpeg"),
        )
    ]
    source_keys = list(dict.fromkeys(spec[0] for spec in alias_specs))
    destination_keys = [spec[1] for spec in alias_specs]
    source_heads = _head_many(client, bucket, source_keys)
    destination_heads = _head_many(client, bucket, destination_keys)
    for source_key, destination_key, expected_type in alias_specs:
        source = source_heads[source_key]
        if source is None:
            raise SyncError(f"S3 source object missing during copy preflight: {source_key}")
        destination = destination_heads[destination_key]
        if destination is not None:
            if _content_type(destination) != expected_type:
                raise SyncError(f"canonical Content-Type conflict: {destination_key}")
            if not _same_object(source, destination):
                raise SyncError(f"canonical object conflict; refusing overwrite: {destination_key}")

    to_copy = [spec for spec in alias_specs if destination_heads[spec[1]] is None]
    with ThreadPoolExecutor(max_workers=min(S3_WORKERS, len(to_copy) or 1)) as executor:
        futures = {
            executor.submit(client.copy_object, bucket, source_key, destination_key): (
                source_key,
                destination_key,
            )
            for source_key, destination_key, _ in to_copy
        }
        for future in as_completed(futures):
            future.result()

    copied = len(to_copy)
    reused = len(alias_specs) - copied
    verified_heads = _head_many(client, bucket, destination_keys)
    for source_key, destination_key, expected_type in alias_specs:
        verified = verified_heads[destination_key]
        if (
            verified is None
            or _content_type(verified) != expected_type
            or not isinstance(verified.get("ContentLength"), int)
            or verified["ContentLength"] <= 0
        ):
            raise SyncError(f"canonical object verification failed: {destination_key}")
        source = source_heads[source_key]
        if source is None or not _same_object(source, verified):
            raise SyncError(f"canonical object content verification failed: {destination_key}")
    return copied, reused


def _checksum_metadata(head: dict[str, Any]) -> tuple[str, str]:
    for key in ("ChecksumSHA256", "ChecksumSHA1", "ChecksumCRC32C", "ChecksumCRC32"):
        if head.get(key):
            return key.removeprefix("Checksum"), str(head[key])
    return "", ""


def _metadata_fields(head: dict[str, Any], prefix: str) -> dict[str, str]:
    algorithm, checksum = _checksum_metadata(head)
    return {
        f"{prefix}_content_type": _content_type(head),
        f"{prefix}_content_length": str(head.get("ContentLength", "")),
        f"{prefix}_etag": str(head.get("ETag", "")),
        f"{prefix}_checksum_algorithm": algorithm,
        f"{prefix}_checksum": checksum,
    }


def write_review_csv(
    pairs: list[MediaPair],
    path: Path = REVIEW_PATH,
    media_status: str = "AVAILABLE",
    source_heads: dict[str, dict[str, Any]] | None = None,
    canonical_heads: dict[str, dict[str, Any]] | None = None,
    verified_at: str = "",
    rights_review_status: str = "PENDING",
    rights_reviewer: str = "",
    rights_reviewed_at: str = "",
    rights_evidence_reference: str = "",
) -> None:
    if len(pairs) != EXPECTED_COUNT:
        raise SyncError("cannot write an incomplete Gymvisual media review")
    if media_status not in {"AVAILABLE", "UNAVAILABLE"}:
        raise SyncError(f"unsupported media_status: {media_status}")
    if rights_review_status not in {"APPROVED", "PENDING", "REJECTED"}:
        raise SyncError(f"unsupported rights_review_status: {rights_review_status}")
    if rights_review_status == "APPROVED" and not all(
        (rights_reviewer, rights_reviewed_at, rights_evidence_reference)
    ):
        raise SyncError("approved media requires reviewer, reviewed_at, and evidence reference")
    if rights_review_status != "APPROVED" and any((rights_reviewer, rights_reviewed_at)):
        raise SyncError("non-approved media must not contain reviewer or reviewed_at")
    source_heads = source_heads or {}
    canonical_heads = canonical_heads or {}
    technical_verified = bool(canonical_heads) and media_status == "AVAILABLE"
    production_eligible = technical_verified and rights_review_status == "APPROVED"
    rows = []
    for pair in sorted(pairs, key=lambda item: item.representative_exercise_id):
        gif_head = canonical_heads.get(pair.gif_s3_key, {})
        thumbnail_head = canonical_heads.get(pair.thumbnail_s3_key, {})
        source_gif_head = source_heads.get(pair.video_key, {})
        source_image_head = source_heads.get(pair.image_key, {})
        row = {
            "representative_exercise_id": pair.representative_exercise_id,
            "source_identity": pair.source_identity,
            "source_image_s3_key": pair.image_key,
            "source_gif_s3_key": pair.video_key,
            "gif_s3_key": pair.gif_s3_key,
            "thumbnail_s3_key": pair.thumbnail_s3_key,
            "media_status": media_status,
            "s3_technical_status": "VERIFIED" if technical_verified else "NOT_EXECUTED",
            "verified_at": verified_at,
            "rights_review_status": rights_review_status,
            "rights_reviewer": rights_reviewer,
            "rights_reviewed_at": rights_reviewed_at,
            "rights_evidence_reference": rights_evidence_reference
            or (
                "data/raw/gym_visual/source.json;"
                f"data/raw/gym_visual/exercises.json#id={pair.source_identity}"
            ),
            "production_eligibility": str(production_eligible).lower(),
            "backend_visibility": "VISIBLE" if production_eligible else "HIDDEN",
        }
        row.update(_metadata_fields(source_gif_head, "source_gif"))
        row.update(_metadata_fields(source_image_head, "source_image"))
        row.update(_metadata_fields(gif_head, "gif"))
        row.update(_metadata_fields(thumbnail_head, "thumbnail"))
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        writer = csv.DictWriter(
            handle,
            fieldnames=REVIEW_COLUMNS,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def approved_review_evidence(path: Path = REVIEW_PATH) -> tuple[str, str, str]:
    """Reuse one uniform dataset-wide approval without inventing review metadata."""

    rows = read_csv(path)
    if not rows:
        raise SyncError("approved Gymvisual review evidence is empty")
    if any(row.get("rights_review_status") != "APPROVED" for row in rows):
        raise SyncError("existing Gymvisual review is not uniformly APPROVED")
    fields = ("rights_reviewer", "rights_reviewed_at", "rights_evidence_reference")
    values = {tuple(row.get(field, "") for field in fields) for row in rows}
    if len(values) != 1 or not all(next(iter(values))):
        raise SyncError("existing Gymvisual review does not carry one complete approval evidence")
    return next(iter(values))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--region", default=REGION)
    parser.add_argument(
        "--mapping-only",
        action="store_true",
        help="write the local filename mapping without calling S3; status remains UNAVAILABLE",
    )
    parser.add_argument(
        "--rights-review-status",
        choices=("APPROVED", "PENDING", "REJECTED"),
        default="PENDING",
    )
    parser.add_argument("--rights-reviewer", default="")
    parser.add_argument("--rights-reviewed-at", default="")
    parser.add_argument("--rights-evidence-reference", default="")
    parser.add_argument(
        "--reuse-approved-review-evidence",
        action="store_true",
        help=(
            "reuse the existing uniform dataset-wide Gymvisual approval metadata; "
            "fails closed unless every existing row is APPROVED with identical evidence"
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.reuse_approved_review_evidence:
            if args.rights_review_status != "PENDING" or any(
                (args.rights_reviewer, args.rights_reviewed_at, args.rights_evidence_reference)
            ):
                raise SyncError(
                    "--reuse-approved-review-evidence cannot be combined with explicit review args"
                )
            (
                args.rights_reviewer,
                args.rights_reviewed_at,
                args.rights_evidence_reference,
            ) = approved_review_evidence()
            args.rights_review_status = "APPROVED"
        pairs = validate_local_media()
        if args.mapping_only:
            write_mapping_manifest(pairs)
            write_review_csv(
                pairs,
                media_status="UNAVAILABLE",
                rights_review_status=args.rights_review_status,
                rights_reviewer=args.rights_reviewer,
                rights_reviewed_at=args.rights_reviewed_at,
                rights_evidence_reference=args.rights_evidence_reference,
            )
            copied = reused = 0
        else:
            client = AwsCliS3Client(args.region)
            uploaded, reused_sources, source_heads = ensure_source_objects(
                pairs, client, args.bucket
            )
            copied, reused = copy_canonical_aliases(pairs, client, args.bucket)
            canonical_keys = [
                key for pair in pairs for key in (pair.gif_s3_key, pair.thumbnail_s3_key)
            ]
            canonical_heads = _head_many(client, args.bucket, canonical_keys)
            write_mapping_manifest(pairs)
            write_review_csv(
                pairs,
                source_heads=source_heads,
                canonical_heads={
                    key: head for key, head in canonical_heads.items() if head is not None
                },
                verified_at=datetime.now(UTC).isoformat(),
                rights_review_status=args.rights_review_status,
                rights_reviewer=args.rights_reviewer,
                rights_reviewed_at=args.rights_reviewed_at,
                rights_evidence_reference=args.rights_evidence_reference,
            )
    except (OSError, SyncError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "gymvisual_representative_count": len(pairs),
                "local_jpg_count": len(pairs),
                "local_gif_count": len(pairs),
                "s3_source_object_count": 0 if args.mapping_only else len(pairs) * 2,
                "expected_s3_source_object_count": len(pairs) * 2,
                "s3_source_upload_count": 0 if args.mapping_only else uploaded,
                "s3_source_reuse_count": 0 if args.mapping_only else reused_sources,
                "canonical_alias_copy_count": copied,
                "canonical_alias_reuse_count": reused,
                "mapping_manifest_path": str(MAPPING_MANIFEST_PATH.relative_to(REPO_ROOT)),
                "mapping_manifest_row_count": len(pairs),
                "review_input_path": str(REVIEW_PATH.relative_to(REPO_ROOT)),
                "review_input_row_count": len(pairs),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
