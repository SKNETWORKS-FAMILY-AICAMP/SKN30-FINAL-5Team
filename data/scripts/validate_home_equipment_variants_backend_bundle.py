#!/usr/bin/env python3
"""Fail-closed validation for a home-equipment importer bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = ROOT / "data/generated/home-equipment-variants-v1-final/backend_bundle"
APPROVED = "DOMAIN_APPROVED"
CODE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


class BundleValidationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleValidationError(f"invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise BundleValidationError(f"JSON object required: {path}")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleValidationError(f"invalid JSONL: {path}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise BundleValidationError(f"JSONL objects required: {path}")
    return rows


def _code(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and set(value) <= CODE_CHARS


def validate(bundle: Path = DEFAULT_BUNDLE) -> dict[str, int | str]:
    manifest = _read_json(bundle / "bundle_manifest.json")
    if (
        manifest.get("schema_version") != "home-equipment-importer-v1"
        or manifest.get("importer_entry_path") != "bundle_manifest.json"
    ):
        raise BundleValidationError("bundle contract is invalid")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise BundleValidationError("manifest file entries are missing")
    for entry in entries:
        path = bundle / entry["path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or _sha256(path) != entry["sha256"]
        ):
            raise BundleValidationError(f"hash/count mismatch: {entry['path']}")
        if "records" in entry and len(_read_jsonl(path)) != entry["records"]:
            raise BundleValidationError(f"record count mismatch: {entry['path']}")
    registry = _read_json(bundle / manifest["approval_registry_path"])
    if registry.get("status_code") != APPROVED or registry.get("production_eligible") is not True:
        raise BundleValidationError("production approval registry is not approved")
    if any(item.get("status_code") != APPROVED for item in registry.get("datasets", [])):
        raise BundleValidationError("registry includes a dataset without DOMAIN_APPROVED status")
    paths = manifest.get("importer_paths")
    if set(paths or {}) != {"substitution_guides", "variant_candidates"}:
        raise BundleValidationError("importer paths must include only approved datasets")
    guide_manifest = _read_json(bundle / paths["substitution_guides"])
    variant_manifest = _read_json(bundle / paths["variant_candidates"])
    guides = _read_jsonl(bundle / guide_manifest["data_path"])
    variants = _read_jsonl(bundle / variant_manifest["data_path"])
    for meta, rows in ((guide_manifest, guides), (variant_manifest, variants)):
        data = bundle / meta["data_path"]
        if (
            meta.get("review_status_code") != APPROVED
            or meta.get("record_count") != len(rows)
            or meta.get("data_sha256") != _sha256(data)
        ):
            raise BundleValidationError("dataset manifest hash/count/approval mismatch")
    guide_keys: set[tuple[str, str]] = set()
    for row in guides:
        required = {
            "exercise_stable_code",
            "equipment_code",
            "proposal_ko",
            "examples_ko",
            "cautions_ko",
            "review_status_code",
            "content_version",
        }
        if (
            not required <= row.keys()
            or row["review_status_code"] != APPROVED
            or not _code(row["exercise_stable_code"])
        ):
            raise BundleValidationError("invalid substitution guide record")
        key = (row["exercise_stable_code"], row["equipment_code"])
        if key in guide_keys:
            raise BundleValidationError("duplicate substitution guide")
        guide_keys.add(key)
    variant_keys: set[tuple[str, str, str]] = set()
    for row in variants:
        required = {
            "source_exercise_stable_code",
            "candidate_exercise_stable_code",
            "missing_equipment_code",
            "reason_code",
            "selection_rationale_ko",
            "review_status_code",
            "source_dataset_code",
        }
        if (
            not required <= row.keys()
            or row["review_status_code"] != APPROVED
            or row["reason_code"] != "EQUIPMENT"
        ):
            raise BundleValidationError("invalid variant record")
        source, target = row["source_exercise_stable_code"], row["candidate_exercise_stable_code"]
        if not _code(source) or not _code(target) or source == target:
            raise BundleValidationError("variant stable code or self-reference is invalid")
        if any(key in row for key in ("condition_code", "pain_discomfort_area_code")):
            raise BundleValidationError("equipment relation must not bypass pain safety selectors")
        key = (source, target, row["missing_equipment_code"])
        if key in variant_keys:
            raise BundleValidationError("duplicate variant relation")
        variant_keys.add(key)
    excluded = registry.get("excluded_candidates", [])
    if not any(item.get("dataset_code") == "STRETCH_STRAP_HOME_SUITABILITY" for item in excluded):
        raise BundleValidationError("unapproved stretch-strap records need an exclusion reason")
    return {
        "status": "valid",
        "substitution_guide_records": len(guides),
        "variant_candidate_records": len(variants),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.bundle), ensure_ascii=False, sort_keys=True))
    except BundleValidationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
