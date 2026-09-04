"""Apply the reviewed body-focus column from the review CSV to the draft JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/review_catalog/exercise_catalog_merged_draft.json"
)
DEFAULT_REVIEW_CSV = (
    PROJECT_ROOT / "data/validation/review_batches/v2_0_6_training_body_focus_review.csv"
)


class ReviewApplyError(ValueError):
    """Raised when the review CSV cannot be safely applied."""


def read_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewApplyError(f"cannot read catalog JSON: {path}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ReviewApplyError("catalog JSON must be an array of objects")
    return value


def read_review(path: Path) -> dict[str, str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"source_identity", "body_focus_code"}
            if not required.issubset(reader.fieldnames or set()):
                raise ReviewApplyError("review CSV is missing required columns")
            rows = list(reader)
    except OSError as exc:
        raise ReviewApplyError(f"cannot read review CSV: {path}") from exc
    review: dict[str, str] = {}
    for row in rows:
        identity = (row.get("source_identity") or "").strip()
        if not identity:
            raise ReviewApplyError("review CSV has a blank source_identity")
        if identity in review:
            raise ReviewApplyError(f"duplicate review source_identity: {identity}")
        review[identity] = (row.get("body_focus_code") or "").strip()
    return review


def apply_review(catalog: list[dict[str, Any]], review: dict[str, str]) -> int:
    catalog_ids = {str(row.get("source_identity") or "") for row in catalog}
    if catalog_ids != set(review):
        raise ReviewApplyError("review and catalog source_identity sets differ")
    changed = 0
    for row in catalog:
        identity = str(row["source_identity"])
        value = review[identity]
        if not value:
            continue
        if row.get("body_focus_code") != value:
            row["body_focus_code"] = value
            changed += 1
    return changed


def write_catalog(path: Path, catalog: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    catalog = read_catalog(args.catalog)
    review = read_review(args.review_csv)
    changed = apply_review(catalog, review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_catalog(args.output, catalog)
    print(f"updated {changed} body_focus_code values in {args.output}")


if __name__ == "__main__":
    main()
