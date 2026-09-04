#!/usr/bin/env python3
"""Replace v2.0.6 primary and secondary muscle fields from GymVisual raw data."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_RAW = PROJECT_ROOT / "data/raw/gym_visual/exercises.json"
DEFAULT_MAPPING = PROJECT_ROOT / "data/normalized/v2_0_6_catalog_source_mapping.json"
DEFAULT_REPORT = PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/gymvisual_muscle_sync_report.json"
PRIMARY_FIELD = "primary_body_area_codes"
SECONDARY_FIELD = "secondary_body_area_codes"
REQUIRED_CATALOG_FIELDS = {"source_identity", "stable_code", PRIMARY_FIELD, SECONDARY_FIELD}
MUSCLE_ALIASES = {
    "latissimus dorsi": "lats",
    "lats": "lats",
    "trapezius": "traps",
    "traps": "traps",
}


class GymvisualMuscleSyncError(ValueError):
    """Raised when the raw GymVisual muscle values cannot be applied exactly."""


def canonical_muscle(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    return MUSCLE_ALIASES.get(normalized, normalized)


def read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
            ]
    except OSError as exc:
        raise GymvisualMuscleSyncError(f"cannot read catalog: {path}") from exc
    missing = sorted(REQUIRED_CATALOG_FIELDS - set(fields))
    if missing:
        raise GymvisualMuscleSyncError(f"catalog is missing columns: {', '.join(missing)}")
    identities = [row["source_identity"] for row in rows]
    if not rows or not all(identities) or len(identities) != len(set(identities)):
        raise GymvisualMuscleSyncError("source_identity values must be unique and non-empty")
    return rows, fields


def read_raw(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GymvisualMuscleSyncError(f"cannot read GymVisual source: {path}") from exc
    if not isinstance(payload, list):
        raise GymvisualMuscleSyncError("GymVisual source must be a JSON array")
    result: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            raise GymvisualMuscleSyncError("GymVisual source contains a non-object row")
        identity = str(row.get("id", "")).strip()
        primary = row.get("muscle_group")
        secondary = row.get("secondary_muscles")
        if not identity or identity in result:
            raise GymvisualMuscleSyncError("GymVisual IDs must be unique and non-empty")
        if not isinstance(primary, str) or not canonical_muscle(primary):
            raise GymvisualMuscleSyncError(f"GymVisual muscle_group is blank: {identity}")
        if not isinstance(secondary, list) or not all(isinstance(item, str) for item in secondary):
            raise GymvisualMuscleSyncError(f"GymVisual secondary_muscles is invalid: {identity}")
        result[identity] = row
    return result


def source_muscles(raw_row: dict[str, Any]) -> tuple[str, list[str]]:
    primary = canonical_muscle(str(raw_row["muscle_group"]))
    secondary = list(
        dict.fromkeys(
            muscle
            for item in raw_row["secondary_muscles"]
            if (muscle := canonical_muscle(str(item))) and muscle != primary
        )
    )
    return primary, secondary


def apply_sync(
    rows: list[dict[str, str]], raw_by_identity: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    missing = [row["source_identity"] for row in rows if row["source_identity"] not in raw_by_identity]
    if missing:
        raise GymvisualMuscleSyncError(
            "catalog rows missing from GymVisual source: " + ", ".join(missing[:8])
        )
    for row in rows:
        primary, secondary = source_muscles(raw_by_identity[row["source_identity"]])
        secondary_value = "|".join(secondary)
        before = {PRIMARY_FIELD: row[PRIMARY_FIELD], SECONDARY_FIELD: row[SECONDARY_FIELD]}
        after = {PRIMARY_FIELD: primary, SECONDARY_FIELD: secondary_value}
        if before != after:
            row.update(after)
            changed.append(
                {
                    "source_identity": row["source_identity"],
                    "stable_code": row["stable_code"],
                    "before": before,
                    "after": after,
                }
            )
    return rows, {
        "status": "DRAFT",
        "production_eligible": False,
        "input_record_count": len(rows),
        "updated_record_count": len(changed),
        "unchanged_record_count": len(rows) - len(changed),
        "synonym_normalization": MUSCLE_ALIASES,
        "records": changed,
    }


def update_source_mapping(path: Path, rows: list[dict[str, str]]) -> None:
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GymvisualMuscleSyncError(f"cannot read source mapping: {path}") from exc
    records = mapping.get("records")
    if not isinstance(records, list):
        raise GymvisualMuscleSyncError("source mapping records are invalid")
    by_identity = {row["source_identity"]: row for row in rows}
    if len(by_identity) != len(rows):
        raise GymvisualMuscleSyncError("catalog source identities are not unique")
    retained_records: list[dict[str, Any]] = []
    for record in records:
        identity = str(record.get("source_identity", ""))
        row = by_identity.get(identity)
        fields = record.get("fields")
        if row is None:
            # The catalog is authoritative for user-requested removals.
            continue
        if not isinstance(fields, dict):
            raise GymvisualMuscleSyncError(f"source mapping fields are invalid: {identity}")
        fields[PRIMARY_FIELD] = {
            "source": "data/raw/gym_visual/exercises.json:raw.muscle_group",
            "value": [row[PRIMARY_FIELD]],
        }
        fields[SECONDARY_FIELD] = {
            "source": (
                "data/raw/gym_visual/exercises.json:raw.secondary_muscles "
                "excluding raw.muscle_group"
            ),
            "value": row[SECONDARY_FIELD].split("|") if row[SECONDARY_FIELD] else [],
        }
        retained_records.append(record)
    mapping["records"] = retained_records
    mapped_identities = {str(record.get("source_identity", "")) for record in retained_records}
    if mapped_identities != set(by_identity):
        raise GymvisualMuscleSyncError("source mapping and catalog record counts differ")
    policy = mapping.setdefault("policy", {})
    policy["primary_secondary_muscle_sync"] = (
        "RAW_GYMVISUAL_MUSCLE_VALUES_OVERWRITE_EXISTING_NORMALIZED_VALUES"
    )
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_catalog(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, fields = read_catalog(args.catalog)
    rows, report = apply_sync(rows, read_raw(args.raw))
    if not args.dry_run:
        write_catalog(args.catalog, rows, fields)
        update_source_mapping(args.mapping, rows)
        write_report(args.report, report)
    print(json.dumps({"updated_records": report["updated_record_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
