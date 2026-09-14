"""Publish v2.0.5 from v2.0.4 with exact Gymvisual media coverage.

The catalog, safety, alternatives and prescriptions remain unchanged. Media is
rebuilt only for catalog exercises whose ``source_track`` is ``gymvisual`` and
whose four-digit ``source_identity`` has an AVAILABLE, VERIFIED and APPROVED
review row. Cross-source name similarity is deliberately not accepted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_VERSION = "exercise-catalog-v2.0.4-final"
TARGET_VERSION = "exercise-catalog-v2.0.5-final"
SOURCE_SUFFIX = "v2.0.4"
TARGET_SUFFIX = "v2.0.5"
GENERATOR_VERSION = "v2-0-5-media-gap-packager-1.0.0"
BUNDLE_VERSION = "v2-0-5-backend-bundle-2026-09-02"

DEFAULT_SOURCE = PROJECT_ROOT / f"data/generated/{SOURCE_VERSION}/backend_bundle"
DEFAULT_TARGET = PROJECT_ROOT / f"data/generated/{TARGET_VERSION}/backend_bundle"
DEFAULT_REVIEW = PROJECT_ROOT / "data/validation/review_results/gymvisual_media_reviewed.csv"

SUB_MANIFESTS = (
    "catalog/seed_manifest.json",
    "alternatives/alternatives_manifest.json",
    "safety/rules_manifest.json",
    "prescriptions/prescription_manifest.json",
)


class BundleBuildError(RuntimeError):
    """Raised when exact reviewed media coverage cannot be proven."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return len(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retarget(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace(SOURCE_VERSION, TARGET_VERSION).replace(SOURCE_SUFFIX, TARGET_SUFFIX)
    if isinstance(value, list):
        return [_retarget(item) for item in value]
    if isinstance(value, dict):
        return {key: _retarget(item) for key, item in value.items()}
    return value


def _unique(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    values = [row.get(key, "") for row in rows]
    if any(not value for value in values) or len(values) != len(set(values)):
        raise BundleBuildError(f"{label} must have unique non-empty {key}")
    return {row[key]: row for row in rows}


def _media_records(
    catalog: list[dict[str, Any]],
    registry_rows: list[dict[str, str]],
    review_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    registry = _unique(registry_rows, "stable_code", "representative registry")
    review = _unique(review_rows, "source_identity", "Gymvisual media review")
    records: list[dict[str, Any]] = []
    for exercise in catalog:
        if exercise.get("source_track") != "gymvisual":
            continue
        stable_code = str(exercise.get("stable_code", ""))
        source_identity = str(exercise.get("source_identity", ""))
        registered = registry.get(stable_code)
        reviewed = review.get(source_identity)
        if registered is None or reviewed is None:
            raise BundleBuildError(
                f"Gymvisual exercise has no exact reviewed binding: {stable_code}"
            )
        required = {
            "media_status": "AVAILABLE",
            "s3_technical_status": "VERIFIED",
            "rights_review_status": "APPROVED",
            "production_eligibility": "true",
            "backend_visibility": "VISIBLE",
            "source_gif_content_type": "image/gif",
        }
        mismatched = [key for key, value in required.items() if reviewed.get(key) != value]
        if mismatched:
            raise BundleBuildError(
                f"Gymvisual review is not publishable for {source_identity}: {mismatched}"
            )
        source_key = reviewed.get("source_gif_s3_key", "")
        if not source_key.startswith(f"videos/{source_identity}-") or not source_key.endswith(
            ".gif"
        ):
            raise BundleBuildError(f"source GIF key does not match identity: {source_identity}")
        if not all(
            reviewed.get(field)
            for field in (
                "gif_s3_key",
                "verified_at",
                "rights_reviewer",
                "rights_reviewed_at",
                "rights_evidence_reference",
            )
        ):
            raise BundleBuildError(f"Gymvisual review evidence is incomplete: {source_identity}")
        records.append(
            {
                "media_status": "AVAILABLE",
                "representative_exercise_id": registered["representative_exercise_id"],
                "rights_evidence_reference": reviewed["rights_evidence_reference"],
                "rights_review_status": "APPROVED",
                "rights_reviewed_at": reviewed["rights_reviewed_at"],
                "rights_reviewer": reviewed["rights_reviewer"],
                "s3_key": reviewed["gif_s3_key"],
                "source_metadata": {
                    "source_object_content_type": "image/gif",
                    "source_object_key": source_key,
                    "source_object_verified_at": reviewed["verified_at"],
                },
            }
        )
    records.sort(key=lambda row: str(row["representative_exercise_id"]))
    if len(records) != 76:
        raise BundleBuildError(f"expected 76 current Gymvisual exercises, got {len(records)}")
    if len({row["s3_key"] for row in records}) != len(records):
        raise BundleBuildError("current Gymvisual exercises reuse a canonical S3 key")
    return records


def _refresh_manifest_files(manifest: dict[str, Any], root: Path) -> None:
    for entry in manifest.get("files", []):
        path = root / entry["path"]
        entry["sha256"] = _sha256(path)
        entry["bytes"] = path.stat().st_size
        if path.suffix == ".jsonl":
            entry["records"] = len(_read_jsonl(path))


def build(
    *,
    source: Path = DEFAULT_SOURCE,
    target: Path = DEFAULT_TARGET,
    review_path: Path = DEFAULT_REVIEW,
) -> dict[str, Any]:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    for path in sorted(target.rglob("*.jsonl")):
        _write_jsonl(path, [_retarget(row) for row in _read_jsonl(path)])

    catalog = _read_jsonl(target / "catalog/exercises.jsonl")
    registry = _read_csv(target / "catalog/input/representative_exercises.csv")
    review_rows = _read_csv(review_path)
    media = _media_records(catalog, registry, review_rows)
    media_path = target / "media/media_assets.jsonl"
    media_count = _write_jsonl(media_path, media)

    for relative in SUB_MANIFESTS:
        path = target / relative
        manifest = _retarget(json.loads(path.read_text(encoding="utf-8")))
        manifest["generator_version"] = GENERATOR_VERSION
        _refresh_manifest_files(manifest, path.parent)
        _write_json(path, manifest)

    media_manifest_path = target / "media/media_manifest.json"
    media_manifest = _retarget(json.loads(media_manifest_path.read_text(encoding="utf-8")))
    media_manifest["generator_version"] = GENERATOR_VERSION
    media_manifest["source"] = {
        "catalog_version_code": TARGET_VERSION,
        "input_artifacts": [
            {
                "bytes": review_path.stat().st_size,
                "path": str(review_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "role": "GYMVISUAL_MEDIA_REVIEW",
                "sha256": _sha256(review_path),
            }
        ],
        "matching_rule": "source_track=gymvisual and exact four-digit source_identity",
        "withheld_reason": "no exact approved Gymvisual source identity",
        "withheld_records": len(catalog) - media_count,
    }
    media_manifest["summary"]["media_asset_records"] = media_count
    _refresh_manifest_files(media_manifest, media_manifest_path.parent)
    _write_json(media_manifest_path, media_manifest)

    bundle_path = target / "bundle_manifest.json"
    source_bundle_hash = _sha256(source / "bundle_manifest.json")
    bundle = _retarget(json.loads(bundle_path.read_text(encoding="utf-8")))
    bundle["bundle_version"] = BUNDLE_VERSION
    bundle["derived_from"] = {
        "bundle_manifest_sha256": source_bundle_hash,
        "catalog_version_code": SOURCE_VERSION,
        "change_summary": (
            "Rebuilds media from exact Gymvisual source identities: 68 to 76 approved assets. "
            "Catalog, safety, alternatives and prescriptions are unchanged."
        ),
        "media_gap_closure": {
            "approval_input_sha256": _sha256(review_path),
            "matching_rule": "EXACT_SOURCE_IDENTITY_ONLY",
            "media_asset_records_after": media_count,
            "media_asset_records_before": 68,
        },
    }
    bundle["summary"]["media_asset_records"] = media_count
    if bundle.get("projection") is not None:
        bundle["projection"]["withheld_media_records"] = len(catalog) - media_count
    _refresh_manifest_files(bundle, target)
    _write_json(bundle_path, bundle)
    return {
        "bundle_manifest_sha256": _sha256(bundle_path),
        "catalog_records": len(catalog),
        "catalog_version_code": TARGET_VERSION,
        "media_asset_records": media_count,
        "withheld_media_records": len(catalog) - media_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()
    print(
        json.dumps(build(source=args.source, target=args.target, review_path=args.review), indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
