"""Fill blank training_type_code values from the effective review body focus."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/review_catalog/"
    "exercise_catalog_merged_draft.json"
)
DEFAULT_REVIEW_CSV = (
    PROJECT_ROOT / "data/validation/review_batches/v2_0_6_training_body_focus_review.csv"
)
DEFAULT_REPORT = DEFAULT_CATALOG.parent / "exercise_catalog_merge_report.json"


class TrainingTypeApplyError(ValueError):
    """Raised when training type derivation cannot be verified."""


def read_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingTypeApplyError(f"cannot read catalog JSON: {path}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise TrainingTypeApplyError("catalog JSON must be an array of objects")
    return value


def read_review(path: Path) -> dict[str, str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"source_identity", "body_focus_code"}
            if not required.issubset(reader.fieldnames or set()):
                raise TrainingTypeApplyError("review CSV is missing required columns")
            rows = list(reader)
    except OSError as exc:
        raise TrainingTypeApplyError(f"cannot read review CSV: {path}") from exc
    review: dict[str, str] = {}
    for row in rows:
        identity = (row.get("source_identity") or "").strip()
        if not identity:
            raise TrainingTypeApplyError("review CSV has a blank source_identity")
        if identity in review:
            raise TrainingTypeApplyError(f"duplicate review source_identity: {identity}")
        review[identity] = (row.get("body_focus_code") or "").strip()
    return review


def training_type_from_body_focus(body_focus_code: str) -> str:
    code = body_focus_code.strip().upper()
    if not code:
        return ""
    if code == "CARDIO":
        return "CARDIO"
    if code == "MOBILITY":
        return "MOBILITY"
    return "STRENGTH"


def apply_training_type(catalog: list[dict[str, Any]], review: dict[str, str]) -> int:
    catalog_ids = {str(row.get("source_identity") or "") for row in catalog}
    if catalog_ids != set(review):
        raise TrainingTypeApplyError("review and catalog source_identity sets differ")
    changed = 0
    for row in catalog:
        identity = str(row["source_identity"])
        expected = training_type_from_body_focus(review[identity])
        if not expected:
            continue
        current = str(row.get("training_type_code") or "").strip()
        if current and current != expected:
            raise TrainingTypeApplyError(
                f"training_type_code conflicts with body_focus_code for {identity}: "
                f"{current} != {expected}"
            )
        if not current:
            row["training_type_code"] = expected
            changed += 1
    return changed


def write_catalog(path: Path, catalog: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def update_report(path: Path, output_path: Path, changed: int) -> None:
    if not path.is_file():
        return
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingTypeApplyError(f"cannot read merge report: {path}") from exc
    if not isinstance(report, dict):
        raise TrainingTypeApplyError("merge report must be an object")
    output = report.setdefault("output", {})
    if not isinstance(output, dict):
        raise TrainingTypeApplyError("merge report output must be an object")
    output["sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    output["records"] = len(read_catalog(output_path))
    report["training_type_derivation"] = {
        "changed_count": changed,
        "rule": "CARDIO->CARDIO, MOBILITY->MOBILITY, any other nonblank body focus->STRENGTH",
        "blank_body_focus_behavior": "LEAVE_TRAINING_TYPE_BLANK",
    }
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    catalog = read_catalog(args.catalog)
    review = read_review(args.review_csv)
    changed = apply_training_type(catalog, review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_catalog(args.output, catalog)
    update_report(args.report, args.output, changed)
    print(f"updated {changed} training_type_code values in {args.output}")


if __name__ == "__main__":
    main()
