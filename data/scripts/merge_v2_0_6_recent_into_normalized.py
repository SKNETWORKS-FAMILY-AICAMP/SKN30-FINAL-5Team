#!/usr/bin/env python3
"""Merge the latest v2.0.6 catalog snapshot into the canonical CSV.

This is a controlled recovery/synchronization step for the case where the
canonical normalized CSV is behind the latest 240-row catalog review output.
The incoming snapshot wins for duplicate ``stable_code`` values.  MET columns
are overlaid separately from the latest MET provenance report and are checked
against the designated Adult Compendium JSONL before the canonical CSV is
written.

The generated snapshot is read-only input to this operation; the normalized
CSV remains the only human-editable source after synchronization. Both
DIRECT and SIMILAR_ACTIVITY mappings are accepted; unresolved rows keep their
MET provenance fields blank. No rank fields are accepted or generated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import OrderedDict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_LATEST_CATALOG = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/review_catalog/"
    "exercise_catalog_merged_draft.json"
)
DEFAULT_MET_PROVENANCE = PROJECT_ROOT / "data/reports/v2_0_6_met/met_provenance.csv"
DEFAULT_COMPENDIUM = PROJECT_ROOT / (
    "data/raw/physical_activity_guidelines/"
    "adult_compendium_mvp_reference_subset.jsonl"
)
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge"
SOURCE_RELATIVE_PATH = (
    "data/raw/physical_activity_guidelines/"
    "adult_compendium_mvp_reference_subset.jsonl"
)
EXPECTED_RECORD_COUNT = 240
MET_FIELDS = (
    "met_value",
    "met_source_code",
    "met_source_activity_code",
    "met_mapping_method_code",
    "met_review_status_code",
    "met_policy_version",
)
REQUIRED_FIELDS = (
    "stable_code",
    "source_identity",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    *MET_FIELDS,
)
FORBIDDEN_RANK_FIELDS = {"rank", "variant_difficulty_rank"}
AMBIGUOUS_METHODS = {
    "MULTIPLE_CANDIDATES_UNRESOLVED",
    "DIRECT_ACTIVITY_UNCLEAR_VARIANT_OR_CONDITION",
}
MET_MAPPING_METHODS = {"DIRECT", "SIMILAR_ACTIVITY"}


class CatalogMergeError(ValueError):
    """Raised when a catalog or MET merge cannot be proven safe."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogMergeError(f"cannot read JSON input: {path}") from exc
    if not isinstance(value, list):
        raise CatalogMergeError(f"latest catalog JSON must be a list: {path}")
    return value


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                {key: (value or "").strip() for key, value in row.items()}
                for row in reader
            ]
    except OSError as exc:
        raise CatalogMergeError(f"cannot read CSV input: {path}") from exc
    if not fields or any(key is None for key in fields):
        raise CatalogMergeError(f"CSV input has no valid header: {path}")
    if any(None in row for row in rows):
        raise CatalogMergeError(f"CSV row does not match its header: {path}")
    return rows, fields


def _read_compendium(path: Path) -> dict[str, dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CatalogMergeError(f"cannot read designated Compendium: {path}") from exc
    activities: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CatalogMergeError(
                f"invalid Compendium JSONL at line {line_number}: {path}"
            ) from exc
        if not isinstance(row, dict):
            raise CatalogMergeError(f"Compendium row {line_number} is not an object")
        code = str(row.get("activity_code", "")).strip()
        if not code or code in activities:
            raise CatalogMergeError(f"Compendium activity_code is blank or duplicated: {code}")
        if "met_value" not in row or not isinstance(row["met_value"], (int, float)):
            raise CatalogMergeError(f"Compendium MET value is missing or invalid: {code}")
        if not math.isfinite(float(row["met_value"])):
            raise CatalogMergeError(f"Compendium MET value is not finite: {code}")
        activities[code] = row
    if not activities:
        raise CatalogMergeError("designated Compendium JSONL is empty")
    return activities


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(_text(item) for item in value)
    return str(value)


def _dedupe_last(
    rows: list[dict[str, Any]], *, path: Path, key: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep the latest occurrence and report keys that were replaced."""

    unique: OrderedDict[str, dict[str, Any]] = OrderedDict()
    duplicate_keys: list[str] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise CatalogMergeError(f"row {index} is not an object: {path}")
        value = str(row.get(key, "")).strip()
        if not value:
            raise CatalogMergeError(f"{key} is blank at row {index}: {path}")
        if value in unique:
            duplicate_keys.append(value)
            del unique[value]
        unique[value] = row
    return list(unique.values()), duplicate_keys


def _validate_catalog_rows(
    rows: list[dict[str, Any]], path: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    if not rows:
        raise CatalogMergeError(f"latest catalog is empty: {path}")
    deduped, duplicate_stable_codes = _dedupe_last(rows, path=path, key="stable_code")
    fields = list(deduped[0])
    missing = sorted(set(REQUIRED_FIELDS) - set(fields))
    if missing:
        raise CatalogMergeError(
            f"latest catalog is missing required fields: {', '.join(missing)}"
        )
    forbidden = sorted(FORBIDDEN_RANK_FIELDS.intersection(fields))
    if forbidden:
        raise CatalogMergeError("rank fields are forbidden: " + ", ".join(forbidden))
    identities: set[str] = set()
    for index, row in enumerate(deduped, 1):
        if any(field not in row for field in fields):
            raise CatalogMergeError(f"latest catalog row {index} has a schema mismatch")
        identity = str(row.get("source_identity", "")).strip()
        if not identity or identity in identities:
            raise CatalogMergeError(f"source_identity is blank or duplicated: {identity}")
        identities.add(identity)
    return deduped, duplicate_stable_codes


def _validate_met_rows(
    rows: list[dict[str, str]],
    catalog_rows: list[dict[str, Any]],
    compendium: dict[str, dict[str, Any]],
    path: Path,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    if not rows:
        raise CatalogMergeError(f"MET provenance is empty: {path}")
    deduped, duplicate_codes = _dedupe_last(rows, path=path, key="stable_code")
    met_by_code = {str(row["stable_code"]).strip(): row for row in deduped}
    catalog_codes = {str(row["stable_code"]).strip() for row in catalog_rows}
    if set(met_by_code) != catalog_codes:
        missing = sorted(catalog_codes - set(met_by_code))
        extra = sorted(set(met_by_code) - catalog_codes)
        raise CatalogMergeError(
            "MET provenance stable_code set differs from latest catalog; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )
    for code, row in met_by_code.items():
        catalog_identity = str(
            next(item["source_identity"] for item in catalog_rows if item["stable_code"] == code)
        ).strip()
        if row.get("source_identity", "").strip() != catalog_identity:
            raise CatalogMergeError(
                f"MET source_identity does not match latest catalog: {code}"
            )
        missing = [field for field in MET_FIELDS if field not in row]
        if missing:
            raise CatalogMergeError(
                f"MET provenance is missing fields for {code}: {', '.join(missing)}"
            )
        if row["met_review_status_code"] != "REVIEW_REQUIRED":
            raise CatalogMergeError(
                f"unreviewed MET data cannot be approval status: {code}"
            )
        value = row["met_value"]
        activity_code = row["met_source_activity_code"]
        if value:
            if not activity_code or activity_code not in compendium:
                raise CatalogMergeError(
                    f"MET activity code is not in designated source: {code}"
                )
            try:
                numeric_value = float(value)
            except ValueError as exc:
                raise CatalogMergeError(f"MET value is not numeric: {code}") from exc
            if not math.isfinite(numeric_value) or numeric_value != float(
                compendium[activity_code]["met_value"]
            ):
                raise CatalogMergeError(
                    f"MET value does not match designated source activity: {code}"
                )
            if row["met_source_code"] != str(compendium[activity_code]["source_id"]):
                raise CatalogMergeError(
                    f"MET source_code does not match designated source: {code}"
                )
            if row["met_mapping_method_code"] not in MET_MAPPING_METHODS or not row[
                "met_policy_version"
            ]:
                raise CatalogMergeError(f"MET provenance is incomplete: {code}")
        elif activity_code or row["met_source_code"]:
            raise CatalogMergeError(
                f"blank MET value cannot retain activity provenance: {code}"
            )
        elif row["met_mapping_method_code"]:
            raise CatalogMergeError(
                f"blank MET value cannot retain a mapping method: {code}"
            )
        if not row["met_policy_version"]:
            raise CatalogMergeError(f"MET review provenance is incomplete: {code}")
    return met_by_code, duplicate_codes


def _write_catalog(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _text(row.get(field, "")) for field in fields})


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _text(row.get(field, "")) for field in fields})


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _existing_by_code(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    rows, fields = _read_csv(path)
    if not rows:
        raise CatalogMergeError(f"existing canonical catalog is empty: {path}")
    if sorted(FORBIDDEN_RANK_FIELDS.intersection(fields)):
        raise CatalogMergeError("rank fields are forbidden in canonical catalog")
    deduped, duplicate_codes = _dedupe_last(rows, path=path, key="stable_code")
    return {row["stable_code"]: row for row in deduped}, duplicate_codes


def merge(
    catalog_path: Path = DEFAULT_CATALOG,
    latest_catalog_path: Path = DEFAULT_LATEST_CATALOG,
    met_provenance_path: Path = DEFAULT_MET_PROVENANCE,
    compendium_path: Path = DEFAULT_COMPENDIUM,
    report_dir: Path = DEFAULT_REPORT_DIR,
    expected_record_count: int = EXPECTED_RECORD_COUNT,
) -> dict[str, Any]:
    latest_raw = _read_json(latest_catalog_path)
    latest_rows, latest_duplicate_codes = _validate_catalog_rows(
        latest_raw, latest_catalog_path
    )
    if len(latest_rows) != expected_record_count:
        raise CatalogMergeError(
            f"latest catalog must contain {expected_record_count} unique rows; "
            f"found {len(latest_rows)}"
        )
    met_rows, _ = _read_csv(met_provenance_path)
    compendium = _read_compendium(compendium_path)
    met_by_code, met_duplicate_codes = _validate_met_rows(
        met_rows, latest_rows, compendium, met_provenance_path
    )
    existing, existing_duplicate_codes = _existing_by_code(catalog_path)

    fields = list(latest_rows[0])
    for field in MET_FIELDS:
        if field not in fields:
            fields.append(field)
    merged_rows: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    added = replaced = unchanged = 0
    for latest in latest_rows:
        code = str(latest["stable_code"]).strip()
        merged = dict(latest)
        merged.update({field: met_by_code[code][field] for field in MET_FIELDS})
        old = existing.get(code)
        old_projection = {field: _text(old.get(field, "")) for field in fields} if old else None
        new_projection = {field: _text(merged.get(field, "")) for field in fields}
        if old is None:
            change = "ADDED"
            added += 1
        elif old_projection != new_projection:
            change = "REPLACED"
            replaced += 1
        else:
            change = "UNCHANGED"
            unchanged += 1
        merged_rows.append(merged)
        changes.append(
            {
                "stable_code": code,
                "source_identity": merged.get("source_identity", ""),
                "change_type": change,
                "met_value": merged.get("met_value", ""),
                "met_source_activity_code": merged.get("met_source_activity_code", ""),
            }
        )

    dropped = sorted(set(existing) - {str(row["stable_code"]).strip() for row in latest_rows})
    _write_catalog(catalog_path, merged_rows, fields)
    _write_csv(
        report_dir / "merge_changes.csv",
        ("stable_code", "source_identity", "change_type", "met_value", "met_source_activity_code"),
        changes,
    )
    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy": {
            "canonical_normalized_catalog_is_output": True,
            "latest_snapshot_wins_for_duplicate_stable_code": True,
            "met_provenance_overlays_latest_catalog_values": True,
            "met_source_only": True,
            "met_unresolved_values_remain_blank": True,
            "rank_not_generated_or_used": True,
            "generated_snapshot_is_not_human_editable": True,
        },
        "inputs": {
            "existing_canonical_catalog": {
                "path": str(catalog_path),
                "records_before_merge": len(existing),
                "duplicate_stable_codes_last_wins": sorted(set(existing_duplicate_codes)),
            },
            "latest_catalog_snapshot": {
                "path": str(latest_catalog_path),
                "sha256": _sha256(latest_catalog_path),
                "records_after_last_wins": len(latest_rows),
                "duplicate_stable_codes_last_wins": sorted(set(latest_duplicate_codes)),
            },
            "met_provenance": {
                "path": str(met_provenance_path),
                "sha256": _sha256(met_provenance_path),
                "records_after_last_wins": len(met_by_code),
                "duplicate_stable_codes_last_wins": sorted(set(met_duplicate_codes)),
            },
            "compendium_subset": {
                "path": SOURCE_RELATIVE_PATH,
                "sha256": _sha256(compendium_path),
                "activity_records": len(compendium),
            },
        },
        "counts": {
            "expected_records": expected_record_count,
            "records_written": len(merged_rows),
            "added": added,
            "replaced": replaced,
            "unchanged": unchanged,
            "dropped_existing_not_in_latest": len(dropped),
            "met_mapping_success": sum(bool(row["met_value"]) for row in met_by_code.values()),
            "met_unmapped": sum(not bool(row["met_value"]) for row in met_by_code.values()),
            "met_ambiguous_or_unclear": sum(
                row["met_mapping_method_code"] in AMBIGUOUS_METHODS
                for row in met_by_code.values()
            ),
            "met_review_required": sum(
                row["met_review_status_code"] == "REVIEW_REQUIRED"
                for row in met_by_code.values()
            ),
        },
        "dropped_existing_stable_codes": dropped,
        "outputs": {
            "normalized_catalog": str(catalog_path),
            "merge_changes": str(report_dir / "merge_changes.csv"),
        },
    }
    _write_json(report_dir / "merge_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--latest-catalog", type=Path, default=DEFAULT_LATEST_CATALOG)
    parser.add_argument("--met-provenance", type=Path, default=DEFAULT_MET_PROVENANCE)
    parser.add_argument("--compendium", type=Path, default=DEFAULT_COMPENDIUM)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--expected-record-count", type=int, default=EXPECTED_RECORD_COUNT)
    args = parser.parse_args()
    report = merge(
        args.catalog,
        args.latest_catalog,
        args.met_provenance,
        args.compendium,
        args.report_dir,
        args.expected_record_count,
    )
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
