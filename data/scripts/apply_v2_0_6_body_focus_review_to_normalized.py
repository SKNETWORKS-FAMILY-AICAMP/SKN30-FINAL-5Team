#!/usr/bin/env python3
"""Apply the completed v2.0.6 body-focus review batch to the canonical CSV.

Only ``body_focus_code`` is changed.  Rows are joined by exact
``source_identity``; existing non-empty values must agree with the review
batch.  Review status and all other blank catalog fields are preserved for
separate review, so this operation does not silently promote draft data.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REVIEW = PROJECT_ROOT / (
    "data/validation/review_batches/v2_0_6_training_body_focus_review.csv"
)
DEFAULT_REPORT = PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/body_focus_apply_report.json"
ALLOWED_BODY_FOCUS = {
    "ADDUCTORS",
    "CHEST",
    "BACK",
    "SHOULDERS",
    "BICEPS",
    "TRICEPS",
    "FOREARMS",
    "GLUTES",
    "QUADRICEPS",
    "HAMSTRINGS",
    "CALVES",
    "CORE",
    "FULL_BODY",
    "CARDIO",
    "MOBILITY",
}


class BodyFocusApplyError(ValueError):
    """Raised when the review batch cannot be applied safely."""


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    except OSError as exc:
        raise BodyFocusApplyError(f"cannot read CSV: {path}") from exc
    if not fields or any(key is None for key in fields) or any(None in row for row in rows):
        raise BodyFocusApplyError(f"CSV schema is invalid: {path}")
    return rows, fields


def _index_by_identity(rows: list[dict[str, str]], path: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        identity = row.get("source_identity", "").strip()
        if not identity or identity in indexed:
            raise BodyFocusApplyError(f"source_identity is blank or duplicated: {path}")
        indexed[identity] = row
    return indexed


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def apply_review(
    catalog_path: Path = DEFAULT_CATALOG,
    review_path: Path = DEFAULT_REVIEW,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    catalog_rows, fields = read_csv(catalog_path)
    review_rows, review_fields = read_csv(review_path)
    required_review_fields = {"source_identity", "body_focus_code"}
    if not required_review_fields.issubset(review_fields):
        raise BodyFocusApplyError("review CSV is missing source_identity or body_focus_code")
    catalog = _index_by_identity(catalog_rows, catalog_path)
    review = _index_by_identity(review_rows, review_path)
    if set(catalog) != set(review):
        raise BodyFocusApplyError("review and canonical source_identity sets differ")
    if "body_focus_code" not in fields:
        raise BodyFocusApplyError("canonical CSV is missing body_focus_code")

    changes: list[dict[str, str]] = []
    filled = unchanged = 0
    for identity, row in catalog.items():
        value = review[identity]["body_focus_code"].strip().upper()
        current = row.get("body_focus_code", "").strip()
        if value not in ALLOWED_BODY_FOCUS:
            if current:
                raise BodyFocusApplyError(
                    f"invalid reviewed body_focus_code conflicts with existing value "
                    f"for {identity}: {value}"
                )
            changes.append(
                {
                    "source_identity": identity,
                    "stable_code": row.get("stable_code", ""),
                    "previous_body_focus_code": current,
                    "new_body_focus_code": value,
                    "change_type": "UNRESOLVED_TAXONOMY_CONFLICT",
                }
            )
            continue
        if current and current != value:
            raise BodyFocusApplyError(
                f"body_focus_code conflict for {identity}: {current} != {value}"
            )
        change_type = "FILLED" if not current else "UNCHANGED"
        if change_type == "FILLED":
            row["body_focus_code"] = value
            filled += 1
        else:
            unchanged += 1
        changes.append(
            {
                "source_identity": identity,
                "stable_code": row.get("stable_code", ""),
                "previous_body_focus_code": current,
                "new_body_focus_code": value,
                "change_type": change_type,
            }
        )

    write_csv(catalog_path, catalog_rows, fields)
    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy": {
            "join_key": "source_identity_exact_match",
            "changed_columns": ["body_focus_code"],
            "other_columns_preserved": True,
            "review_status_not_promoted": True,
        },
        "inputs": {
            "canonical_catalog": {"path": str(catalog_path), "records": len(catalog_rows)},
            "review_batch": {
                "path": str(review_path),
                "records": len(review_rows),
                "review_status_fields_are_blank": all(
                    not row.get("body_focus_review_status", "").strip() for row in review_rows
                ),
            },
        },
        "counts": {
            "catalog_records": len(catalog_rows),
            "filled": filled,
            "unchanged": unchanged,
            "conflicts": 0,
            "unresolved_taxonomy_conflict": sum(
                row["change_type"] == "UNRESOLVED_TAXONOMY_CONFLICT" for row in changes
            ),
        },
        "outputs": {
            "normalized_catalog": str(catalog_path),
            "report": str(report_path),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_csv(
        report_path.with_name("body_focus_apply_changes.csv"),
        changes,
        [
            "source_identity",
            "stable_code",
            "previous_body_focus_code",
            "new_body_focus_code",
            "change_type",
        ],
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = apply_review(args.catalog, args.review, args.report)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
