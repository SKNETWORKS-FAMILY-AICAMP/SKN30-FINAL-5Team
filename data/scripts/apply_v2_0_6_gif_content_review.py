#!/usr/bin/env python3
"""Apply the direct-GIF review to the v2.0.6 canonical catalog.

The review result is the auditable human-editable source for this content
revision.  This script deliberately changes only review-approved display,
instruction, form-cue, equipment, and deletion fields; all generated catalog
artifacts must be rebuilt afterwards from the normalized CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REVIEW = (
    PROJECT_ROOT / "data/validation/review_results/v2_0_6_gif_content_review.json"
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/gif_content_review_apply_report.json"
)
EDITABLE_FIELDS = {
    "name_ko",
    "instruction_summary_ko",
    "form_cues_ko",
    "equipment_codes",
}
DERIVED_FIELDS = {
    "instruction_content_version",
    "form_cues_review_status",
    "form_cues_source",
}


class GifReviewApplyError(ValueError):
    """Raised when the review or canonical catalog cannot be proven safe."""


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
        raise GifReviewApplyError(f"cannot read catalog: {path}") from exc
    required = {"source_identity", "stable_code", *EDITABLE_FIELDS, *DERIVED_FIELDS}
    missing = sorted(required - set(fields))
    if missing:
        raise GifReviewApplyError("catalog is missing columns: " + ", ".join(missing))
    if not rows:
        raise GifReviewApplyError("catalog is empty")
    identities = [row.get("source_identity", "") for row in rows]
    if not all(identities) or len(identities) != len(set(identities)):
        raise GifReviewApplyError("catalog source_identity values must be unique and non-empty")
    return rows, fields


def read_review(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GifReviewApplyError(f"cannot read GIF review: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise GifReviewApplyError("GIF review must contain a records array")
    review_version = payload.get("review_version")
    content_version = payload.get("content_version")
    video_root = payload.get("video_root")
    if not all(isinstance(value, str) and value for value in (review_version, content_version, video_root)):
        raise GifReviewApplyError("GIF review metadata is incomplete")
    seen: set[str] = set()
    for record in payload["records"]:
        if not isinstance(record, dict):
            raise GifReviewApplyError("GIF review records must be objects")
        identity = record.get("source_identity")
        stable_code = record.get("stable_code")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise GifReviewApplyError("GIF review source_identity values must be unique")
        if not isinstance(stable_code, str) or not stable_code:
            raise GifReviewApplyError(f"GIF review has no stable_code: {identity}")
        seen.add(identity)
        action = record.get("action", "UPDATE")
        if action == "DELETE":
            if not isinstance(record.get("reason"), str) or not record["reason"]:
                raise GifReviewApplyError(f"delete reason is missing: {identity}")
            continue
        if action != "UPDATE":
            raise GifReviewApplyError(f"unsupported GIF review action: {action}")
        if not isinstance(record.get("video_filename"), str) or not record["video_filename"]:
            raise GifReviewApplyError(f"GIF filename is missing: {identity}")
        fields = record.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise GifReviewApplyError(f"GIF review fields are missing: {identity}")
        unsupported = set(fields) - EDITABLE_FIELDS
        if unsupported:
            raise GifReviewApplyError(
                f"GIF review changes unsupported fields for {identity}: {sorted(unsupported)}"
            )
        for field, value in fields.items():
            if field == "form_cues_ko":
                if not isinstance(value, list) or len(value) < 2 or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    raise GifReviewApplyError(f"invalid form cues: {identity}")
            elif not isinstance(value, str) or not value.strip():
                raise GifReviewApplyError(f"invalid {field}: {identity}")
    return payload, payload["records"]


def _encode_value(field: str, value: Any) -> str:
    if field == "form_cues_ko":
        return "|".join(value)
    return str(value)


def apply_review(
    rows: list[dict[str, str]], review: dict[str, Any], records: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    by_identity = {row["source_identity"]: row for row in rows}
    changed_by_field: dict[str, list[str]] = {field: [] for field in EDITABLE_FIELDS}
    deleted: list[dict[str, str]] = []
    already_deleted: list[dict[str, str]] = []
    deleted_ids: set[str] = set()
    for record in records:
        identity = record["source_identity"]
        row = by_identity.get(identity)
        if row is None:
            if record.get("action", "UPDATE") == "DELETE":
                already_deleted.append(
                    {
                        "source_identity": identity,
                        "stable_code": record["stable_code"],
                        "reason": record["reason"],
                    }
                )
                continue
            raise GifReviewApplyError(f"GIF review target does not exist: {identity}")
        if row["stable_code"] != record["stable_code"]:
            raise GifReviewApplyError(
                f"stable_code does not match GIF review: {identity}"
            )
        if record.get("action", "UPDATE") == "DELETE":
            deleted_ids.add(identity)
            deleted.append(
                {
                    "source_identity": identity,
                    "stable_code": row["stable_code"],
                    "name_ko": row["name_ko"],
                    "reason": record["reason"],
                }
            )
            continue
        for field, value in record["fields"].items():
            encoded = _encode_value(field, value)
            if row[field] != encoded:
                row[field] = encoded
                changed_by_field[field].append(identity)
        derived = {
            "instruction_content_version": review["content_version"],
            "form_cues_review_status": "REVIEW_REQUIRED",
            "form_cues_source": f"{review['video_root']}/{record['video_filename']}",
        }
        for field, value in derived.items():
            if row[field] != value:
                row[field] = value
                changed_by_field.setdefault(field, []).append(identity)
    retained = [row for row in rows if row["source_identity"] not in deleted_ids]
    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "review_version": review["review_version"],
        "review_method": review["review_method"],
        "content_version": review["content_version"],
        "input_record_count": len(rows),
        "output_record_count": len(retained),
        "updated_record_count": sum(
            record.get("action", "UPDATE") == "UPDATE" for record in records
        ),
        "changed_record_count": len(
            set(identity for values in changed_by_field.values() for identity in values)
        ),
        "changed_by_field": {field: sorted(values) for field, values in changed_by_field.items()},
        "deleted_records": deleted,
        "already_deleted_records": already_deleted,
        "unresolved_records": [],
    }
    return retained, report


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
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, fields = read_catalog(args.catalog)
    review, records = read_review(args.review)
    retained, report = apply_review(rows, review, records)
    if not args.dry_run:
        write_catalog(args.catalog, retained, fields)
        write_report(args.report, report)
    print(
        json.dumps(
            {
                "updated_records": report["updated_record_count"],
                "deleted_records": len(report["deleted_records"]),
                "output_records": report["output_record_count"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
