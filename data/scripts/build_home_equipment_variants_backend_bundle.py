#!/usr/bin/env python3
"""Build the approved home-equipment guide and variant importer bundle.

This is a separate, additive importer contract.  It deliberately does not
modify the v2.0.6 catalog bundle or convert equipment relations into catalog
alternatives: a backend adapter must keep applying the catalog safety rules
when it uses these advisory equipment relations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "data/generated/home-equipment-variants-v1-final/backend_bundle"
CATALOG = ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
GUIDES = ROOT / "data/normalized/home_equipment_substitution_guides_v1.jsonl"
VARIANT_SOURCES = {
    "dumbbell": ROOT / "data/normalized/dumbbell_bodyweight_variant_candidates_v1.jsonl",
    "foam_roller": ROOT / "data/normalized/foam_roller_bodyweight_variant_candidates_v1.jsonl",
    "resistance_band": ROOT
    / "data/normalized/resistance_band_bodyweight_variant_candidates_v1.jsonl",
}
STRETCH = ROOT / "data/normalized/stretch_strap_home_suitability_review_v1.jsonl"
VALIDATION_EVIDENCE = ROOT / "data/reports/home_equipment_substitution_guides_v1_validation.json"
GAP_EVIDENCE = ROOT / "data/reports/resistance_band_bodyweight_variant_gap_report_v1.json"

BUNDLE_VERSION = "home-equipment-variants-v1-final-2026-09-04"
GENERATOR_VERSION = "home-equipment-variants-backend-bundle-1.0.0"
SCHEMA_VERSION = "home-equipment-importer-v1"
GENERATED_AT = "2026-09-04T00:00:00+09:00"
APPROVED = "DOMAIN_APPROVED"
EQUIPMENT_CODES = {"DUMBBELL", "FOAM_ROLLER", "RESISTANCE_BAND"}
STABLE_CODE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


class BundleBuildError(RuntimeError):
    """Raised when an input cannot be safely promoted to this bundle."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleBuildError(f"invalid JSONL input: {_relative(path)}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise BundleBuildError(f"JSONL rows must be objects: {_relative(path)}")
    return rows


def _catalog_rows() -> dict[str, dict[str, str]]:
    with CATALOG.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["stable_code"]: row for row in csv.DictReader(handle)}
    if not rows or any(not code for code in rows):
        raise BundleBuildError("catalog stable_code set is invalid")
    return rows


def _valid_code(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and set(value) <= STABLE_CODE_CHARS


def _require(row: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(field for field in fields if field not in row or row[field] in (None, ""))
    if missing:
        raise BundleBuildError(f"{label} missing required fields: {', '.join(missing)}")


def _approved_guides(catalog: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], int]:
    required = {
        "exercise_stable_code",
        "equipment_code",
        "examples_ko",
        "cautions_ko",
        "review_status_code",
        "content_version",
    }
    approved: list[dict[str, Any]] = []
    excluded = 0
    keys: set[tuple[str, str]] = set()
    for index, row in enumerate(_read_jsonl(GUIDES), 1):
        if row.get("review_status_code") != APPROVED:
            excluded += 1
            continue
        _require(row, required, f"guide {index}")
        if "proposal_ko" not in row or not isinstance(row["proposal_ko"], str):
            raise BundleBuildError(f"guide {index} proposal_ko must be a string")
        code, equipment = row["exercise_stable_code"], row["equipment_code"]
        if not _valid_code(code) or code not in catalog or equipment not in EQUIPMENT_CODES:
            raise BundleBuildError(f"guide {index} has an invalid exercise or equipment code")
        if equipment not in set(catalog[code]["equipment_codes"].split("|")):
            raise BundleBuildError(f"guide {index} equipment does not match catalog")
        if not isinstance(row["examples_ko"], list) or not isinstance(row["cautions_ko"], list):
            raise BundleBuildError(f"guide {index} examples/cautions must be arrays")
        if (code, equipment) in keys:
            raise BundleBuildError(f"duplicate guide relation: {code}/{equipment}")
        keys.add((code, equipment))
        approved.append(row)
    return sorted(
        approved, key=lambda row: (row["equipment_code"], row["exercise_stable_code"])
    ), excluded


def _approved_variants(catalog: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], int]:
    required = {
        "source_exercise_stable_code",
        "missing_equipment_code",
        "candidate_exercise_stable_code",
        "reason_code",
        "selection_rationale_ko",
        "review_status_code",
    }
    approved: list[dict[str, Any]] = []
    excluded = 0
    keys: set[tuple[str, str, str]] = set()
    for source_name, path in VARIANT_SOURCES.items():
        for index, row in enumerate(_read_jsonl(path), 1):
            if row.get("review_status_code") != APPROVED:
                excluded += 1
                continue
            _require(row, required, f"{source_name} variant {index}")
            source, target, equipment = (
                row["source_exercise_stable_code"],
                row["candidate_exercise_stable_code"],
                row["missing_equipment_code"],
            )
            if not all(_valid_code(code) and code in catalog for code in (source, target)):
                raise BundleBuildError(
                    f"{source_name} variant {index} references an unknown exercise"
                )
            if (
                source == target
                or equipment not in EQUIPMENT_CODES
                or row["reason_code"] != "EQUIPMENT"
            ):
                raise BundleBuildError(f"{source_name} variant {index} violates relation policy")
            if equipment not in set(catalog[source]["equipment_codes"].split("|")):
                raise BundleBuildError(
                    f"{source_name} variant {index} source equipment does not match catalog"
                )
            if set(catalog[target]["equipment_codes"].split("|")) != {"BODYWEIGHT"}:
                raise BundleBuildError(
                    f"{source_name} variant {index} target is not bodyweight-only"
                )
            if (
                catalog[source]["review_status_code"] != APPROVED
                or catalog[target]["review_status_code"] != APPROVED
            ):
                raise BundleBuildError(
                    f"{source_name} variant {index} references an unapproved catalog row"
                )
            key = (source, target, equipment)
            if key in keys:
                raise BundleBuildError(f"duplicate variant relation: {key}")
            keys.add(key)
            approved.append({**row, "source_dataset_code": source_name})
    return sorted(
        approved,
        key=lambda row: (row["missing_equipment_code"], row["source_exercise_stable_code"]),
    ), excluded


def _approved_stretch() -> tuple[list[dict[str, Any]], int]:
    rows = _read_jsonl(STRETCH)
    approved = [
        row
        for row in rows
        if row.get("review_status_code") == APPROVED
        and row.get("home_suitability_decision") == "APPROVED"
    ]
    return approved, len(rows) - len(approved)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _file(path: Path, records: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }
    if records is not None:
        entry["records"] = records
    return entry


def build(target: Path = TARGET) -> dict[str, Any]:
    catalog = _catalog_rows()
    guides, excluded_guides = _approved_guides(catalog)
    variants, excluded_variants = _approved_variants(catalog)
    stretch, excluded_stretch = _approved_stretch()
    if stretch:
        raise BundleBuildError(
            "stretch-strap import schema is not approved; leave it out of this bundle"
        )

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    guide_data = target / "guides/substitution_guides.jsonl"
    variant_data = target / "variants/bodyweight_variant_candidates.jsonl"
    _write_jsonl(guide_data, guides)
    _write_jsonl(variant_data, variants)
    guide_manifest = target / "guides/substitution_guides_manifest.json"
    variant_manifest = target / "variants/bodyweight_variant_candidates_manifest.json"
    _write_json(
        guide_manifest,
        {
            "schema_version": SCHEMA_VERSION,
            "bundle_version": BUNDLE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "generated_at": GENERATED_AT,
            "importer_entry_path": "guides/substitution_guides_manifest.json",
            "dataset_version": "home-equipment-substitution-v1",
            "record_count": len(guides),
            "data_path": "guides/substitution_guides.jsonl",
            "data_sha256": _sha256(guide_data),
            "review_status_code": APPROVED,
        },
    )
    _write_json(
        variant_manifest,
        {
            "schema_version": SCHEMA_VERSION,
            "bundle_version": BUNDLE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "generated_at": GENERATED_AT,
            "importer_entry_path": "variants/bodyweight_variant_candidates_manifest.json",
            "dataset_version": "bodyweight-variant-candidates-v1",
            "record_count": len(variants),
            "data_path": "variants/bodyweight_variant_candidates.jsonl",
            "data_sha256": _sha256(variant_data),
            "review_status_code": APPROVED,
            "safety_contract": (
                "EQUIPMENT-only relations; catalog safety rules remain authoritative"
            ),
        },
    )

    registry_path = target / "approval/production_approval_registry.json"
    _write_json(
        registry_path,
        {
            "schema_version": "production-approval-registry-v1",
            "bundle_version": BUNDLE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "generated_at": GENERATED_AT,
            "importer_entry_path": "approval/production_approval_registry.json",
            "status_code": APPROVED,
            "approval_date": "2026-09-04",
            "approval_owner_role": "PM_DIRECT_REVIEW",
            "review_method_code": "USER_CONFIRMED",
            "production_eligible": True,
            "datasets": [
                {
                    "dataset_code": "HOME_EQUIPMENT_SUBSTITUTION_GUIDES",
                    "status_code": APPROVED,
                    "approved_version": "home-equipment-substitution-v1",
                    "manifest_path": "guides/substitution_guides_manifest.json",
                    "review_artifact_paths": [_relative(VALIDATION_EVIDENCE)],
                    "record_count": len(guides),
                },
                {
                    "dataset_code": "HOME_EQUIPMENT_BODYWEIGHT_VARIANTS",
                    "status_code": APPROVED,
                    "approved_version": "bodyweight-variant-candidates-v1",
                    "manifest_path": "variants/bodyweight_variant_candidates_manifest.json",
                    "review_artifact_paths": [
                        _relative(VALIDATION_EVIDENCE),
                        _relative(GAP_EVIDENCE),
                    ],
                    "record_count": len(variants),
                },
            ],
            "excluded_candidates": [
                {
                    "dataset_code": "STRETCH_STRAP_HOME_SUITABILITY",
                    "source_path": _relative(STRETCH),
                    "excluded_record_count": excluded_stretch,
                    "reason_code": "NO_DOMAIN_APPROVED_IMPORTABLE_RECORD",
                    "reason": (
                        "No row has both DOMAIN_APPROVED and "
                        "home_suitability_decision=APPROVED."
                    ),
                },
                {
                    "dataset_code": "NON_DOMAIN_APPROVED_GUIDES",
                    "excluded_record_count": excluded_guides,
                    "reason_code": "REVIEW_STATUS_NOT_DOMAIN_APPROVED",
                },
                {
                    "dataset_code": "NON_DOMAIN_APPROVED_VARIANTS",
                    "excluded_record_count": excluded_variants,
                    "reason_code": "REVIEW_STATUS_NOT_DOMAIN_APPROVED",
                },
                {
                    "dataset_code": "VALIDATION_EVIDENCE",
                    "source_path": _relative(VALIDATION_EVIDENCE),
                    "reason_code": "EVIDENCE_ONLY_NOT_DB_IMPORT",
                },
                {
                    "dataset_code": "GAP_REPORT",
                    "source_path": _relative(GAP_EVIDENCE),
                    "reason_code": "EVIDENCE_ONLY_NOT_DB_IMPORT",
                },
            ],
        },
    )
    files = []
    for path, count in [
        (guide_data, len(guides)),
        (guide_manifest, None),
        (variant_data, len(variants)),
        (variant_manifest, None),
        (registry_path, None),
    ]:
        entry = {
            "path": str(path.relative_to(target)),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        if count is not None:
            entry["records"] = count
        files.append(entry)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "bundle_version": BUNDLE_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": GENERATED_AT,
        "importer_entry_path": "bundle_manifest.json",
        "importer_paths": {
            "substitution_guides": "guides/substitution_guides_manifest.json",
            "variant_candidates": "variants/bodyweight_variant_candidates_manifest.json",
        },
        "approval_registry_path": "approval/production_approval_registry.json",
        "files": sorted(files, key=lambda entry: entry["path"]),
        "summary": {
            "substitution_guide_records": len(guides),
            "variant_candidate_records": len(variants),
            "stretch_strap_records": 0,
        },
    }
    _write_json(target / "bundle_manifest.json", manifest)
    return manifest["summary"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.target), ensure_ascii=False, sort_keys=True))
    except BundleBuildError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
