#!/usr/bin/env python3
"""Record the PM's direct approval for the v2.0.6 normalized catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_MANIFEST = PROJECT_ROOT / "data/reports/v2_0_6_catalog/catalog_approval_manifest.json"
REVIEW_STATUS = "DOMAIN_APPROVED"
REVIEW_METHOD = "DOMAIN_REVIEWER"
REVIEWER = "PM_DIRECT_REVIEW"
REVIEWED_AT = "2026-09-04T00:00:00+09:00"


class CatalogApprovalError(ValueError):
    """Raised when the approval scope is not the expected canonical catalog."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approve(
    input_path: Path = DEFAULT_INPUT, manifest_path: Path = DEFAULT_MANIFEST
) -> dict[str, object]:
    try:
        with input_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        raise CatalogApprovalError(f"cannot read canonical catalog: {input_path}") from exc
    if "review_status_code" not in fields:
        raise CatalogApprovalError("canonical catalog lacks review_status_code")
    if len(rows) != 237:
        raise CatalogApprovalError(f"expected 237 catalog rows, got {len(rows)}")
    before = sum((row.get("review_status_code") or "").strip() == "" for row in rows)
    if before != 165:
        raise CatalogApprovalError(f"expected 165 blank review statuses, got {before}")
    if any(
        (row.get("review_status_code") or "").strip() not in {"", REVIEW_STATUS} for row in rows
    ):
        raise CatalogApprovalError("catalog contains an unsupported review status")

    for row in rows:
        row["review_status_code"] = REVIEW_STATUS
    try:
        with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise CatalogApprovalError(f"cannot write canonical catalog: {input_path}") from exc

    manifest = {
        "schema_version": "1.0",
        "catalog_version_code": "exercise-catalog-v2.0.6-draft",
        "status": REVIEW_STATUS,
        "review_status_code": REVIEW_STATUS,
        "review_method_code": REVIEW_METHOD,
        "reviewer_code": REVIEWER,
        "reviewed_at": REVIEWED_AT,
        "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
        "production_eligible": False,
        "scope": (
            "All 237 v2.0.6 catalog rows; PM confirmed beginner suitability and catalog values."
        ),
        "source_catalog_path": "data/normalized/v2_0_6_exercise_catalog.csv",
        "source_catalog_sha256": _sha256(input_path),
        "record_count": len(rows),
        "before_review_status_counts": {"blank": before, REVIEW_STATUS: len(rows) - before},
        "after_review_status_counts": {REVIEW_STATUS: len(rows)},
        "evidence": [
            {
                "type": "PM_DIRECT_REVIEW",
                "reviewer_code": REVIEWER,
                "reviewed_at": REVIEWED_AT,
                "basis": "beginner suitability and catalog values confirmed by PM",
            },
            {
                "type": "MET_APPROVAL_MANIFEST",
                "path": "data/reports/v2_0_6_met/met_review_approval_manifest.json",
                "scope": "MET values and provenance only",
            },
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "records": len(rows),
        "review_status_code": REVIEW_STATUS,
        "source_catalog_sha256": manifest["source_catalog_sha256"],
        "manifest": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    print(json.dumps(approve(args.input, args.manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
