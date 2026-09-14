#!/usr/bin/env python3
"""Fill canonical v2.0.6 training types from the body-focus review batch.

The canonical CSV remains the only edited catalog source.  Non-empty
``body_focus_code`` values determine the training type using the documented
rule.  Rows whose body focus is still unresolved may receive STRENGTH only
when the completed review batch explicitly records STRENGTH for that exact
source identity; their body focus remains blank.
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
DEFAULT_REPORT = PROJECT_ROOT / (
    "data/reports/v2_0_6_catalog_merge/training_type_apply_report.json"
)


class TrainingTypeApplyError(ValueError):
    """Raised when training type cannot be safely derived."""


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    except OSError as exc:
        raise TrainingTypeApplyError(f"cannot read CSV: {path}") from exc
    if not fields or any(key is None for key in fields) or any(None in row for row in rows):
        raise TrainingTypeApplyError(f"CSV schema is invalid: {path}")
    return rows, fields


def index_by_identity(rows: list[dict[str, str]], path: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        identity = row.get("source_identity", "").strip()
        if not identity or identity in indexed:
            raise TrainingTypeApplyError(f"source_identity is blank or duplicated: {path}")
        indexed[identity] = row
    return indexed


def training_type_from_body_focus(body_focus_code: str) -> str:
    code = body_focus_code.strip().upper()
    if code == "CARDIO":
        return "CARDIO"
    if code == "MOBILITY":
        return "MOBILITY"
    if code:
        return "STRENGTH"
    return ""


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def apply_training_type(
    catalog_path: Path = DEFAULT_CATALOG,
    review_path: Path = DEFAULT_REVIEW,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    catalog_rows, fields = read_csv(catalog_path)
    review_rows, review_fields = read_csv(review_path)
    if "source_identity" not in fields or "training_type_code" not in fields:
        raise TrainingTypeApplyError(
            "canonical CSV is missing source_identity or training_type_code"
        )
    if not {"source_identity", "body_focus_code", "training_type_code"}.issubset(review_fields):
        raise TrainingTypeApplyError("review CSV is missing training type fields")
    catalog = index_by_identity(catalog_rows, catalog_path)
    review = index_by_identity(review_rows, review_path)
    if set(catalog) != set(review):
        raise TrainingTypeApplyError("review and canonical source_identity sets differ")

    changes: list[dict[str, str]] = []
    filled = unchanged = 0
    unresolved_body_focus_filled_as_strength: list[str] = []
    for identity, row in catalog.items():
        current_body_focus = row.get("body_focus_code", "").strip().upper()
        reviewed_body_focus = review[identity]["body_focus_code"].strip().upper()
        reviewed_training_type = review[identity]["training_type_code"].strip().upper()
        expected = training_type_from_body_focus(current_body_focus)
        if not expected:
            if reviewed_training_type != "STRENGTH":
                raise TrainingTypeApplyError(
                    f"blank body focus has no explicit STRENGTH review for {identity}"
                )
            expected = "STRENGTH"
            unresolved_body_focus_filled_as_strength.append(identity)
        if reviewed_body_focus and training_type_from_body_focus(reviewed_body_focus) != expected:
            raise TrainingTypeApplyError(
                f"reviewed training type conflicts with body focus for {identity}"
            )
        current = row.get("training_type_code", "").strip().upper()
        if current and current != expected:
            raise TrainingTypeApplyError(
                f"training_type_code conflict for {identity}: {current} != {expected}"
            )
        change_type = "FILLED" if not current else "UNCHANGED"
        if change_type == "FILLED":
            row["training_type_code"] = expected
            filled += 1
        else:
            unchanged += 1
        changes.append(
            {
                "source_identity": identity,
                "stable_code": row.get("stable_code", ""),
                "previous_training_type_code": current,
                "new_training_type_code": expected,
                "body_focus_code": current_body_focus,
                "change_type": change_type,
            }
        )

    write_csv(catalog_path, catalog_rows, fields)
    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy": {
            "join_key": "source_identity_exact_match",
            "derivation": "CARDIO->CARDIO, MOBILITY->MOBILITY, other nonblank body focus->STRENGTH",
            "blank_body_focus_exception": "explicit review batch STRENGTH only",
            "body_focus_column_changed": False,
            "review_status_not_promoted": True,
        },
        "inputs": {
            "canonical_catalog": {"path": str(catalog_path), "records": len(catalog_rows)},
            "review_batch": {"path": str(review_path), "records": len(review_rows)},
        },
        "counts": {
            "catalog_records": len(catalog_rows),
            "filled": filled,
            "unchanged": unchanged,
            "conflicts": 0,
            "blank_body_focus_filled_as_strength": len(unresolved_body_focus_filled_as_strength),
        },
        "blank_body_focus_stable_codes_filled_as_strength": (
            unresolved_body_focus_filled_as_strength
        ),
        "outputs": {"normalized_catalog": str(catalog_path), "report": str(report_path)},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_csv(
        report_path.with_name("training_type_apply_changes.csv"),
        changes,
        [
            "source_identity",
            "stable_code",
            "previous_training_type_code",
            "new_training_type_code",
            "body_focus_code",
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
    report = apply_training_type(args.catalog, args.review, args.report)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
