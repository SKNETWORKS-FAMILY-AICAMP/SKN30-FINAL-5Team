"""Convert the merged v2.0.6 catalog JSON to a human-review CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/review_catalog/exercise_catalog_merged_draft.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data/validation/review_batches/v2_0_6_training_body_focus_review.csv"
)
DEFAULT_CANDIDATES = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/review_catalog/"
    "training_body_focus_candidates.jsonl"
)

CSV_FIELDS = (
    "stable_code",
    "source_identity",
    "name_ko",
    "name_en",
    "training_type_code",
    "body_focus_code",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "form_cues_ko",
    "training_type_review_status",
    "body_focus_review_status",
    "review_note",
)
REVIEW_INPUT_FIELDS = {
    "training_type_review_status",
    "body_focus_review_status",
    "review_note",
}

# Explicit human-review decisions for this review batch.  These affect only
# the CSV review artifact; the source catalog and candidate JSONL remain
# unchanged.  IDs are kept as source_identity strings, including leading
# zeroes.
REVIEWED_BODY_FOCUS_OVERRIDES = {
    "0168": "ADDUCTORS",
    "0710": "GLUTES",
    "0597": "ADDUCTORS",
    "0598": "GLUTES",
    "1362": "MOBILITY",
    "1366": "MOBILITY",
    "1388": "MOBILITY",
    "1389": "MOBILITY",
    "1397": "MOBILITY",
    "1407": "MOBILITY",
    "1419": "MOBILITY",
    "1564": "MOBILITY",
    "1689": "MOBILITY",
    "2203": "MOBILITY",
    "2204": "MOBILITY",
    "2205": "MOBILITY",
    "2206": "MOBILITY",
    "2207": "MOBILITY",
    "2208": "MOBILITY",
    "2209": "MOBILITY",
    "2271": "CARDIO",
    "3011": "SHOULDERS",
    "3231": "MOBILITY",
    "3006": "GLUTES",
    "3667": "ADDUCTORS",
}


class ReviewCsvBuildError(ValueError):
    """Raised when the source does not satisfy the review CSV contract."""


def read_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewCsvBuildError(f"cannot read catalog JSON: {path}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ReviewCsvBuildError("catalog JSON must be an array of objects")
    return value


def read_candidates(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        value = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewCsvBuildError(f"cannot read candidate JSONL: {path}") from exc
    if any(not isinstance(row, dict) for row in value):
        raise ReviewCsvBuildError("candidate JSONL must contain only objects")
    return value


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if any(item is None for item in value):
            raise ReviewCsvBuildError("arrays must not contain null values")
        return "|".join(str(item) for item in value)
    if isinstance(value, (dict, tuple, set)):
        raise ReviewCsvBuildError("unexpected structured value in CSV field")
    return str(value)


def training_type_from_body_focus(body_focus_code: Any) -> str:
    """Map a body-focus code to the requested training type family."""

    code = str(body_focus_code or "").strip().upper()
    if not code:
        return ""
    if code == "CARDIO":
        return "CARDIO"
    if code == "MOBILITY":
        return "MOBILITY"
    return "STRENGTH"


def build_rows(
    catalog: list[dict[str, Any]], candidates: list[dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    candidate_by_identity: dict[str, Any] = {}
    if candidates is not None:
        for candidate in candidates:
            identity = candidate.get("source_identity")
            if not isinstance(identity, str) or not identity:
                raise ReviewCsvBuildError("candidate source_identity must be non-empty")
            if identity in candidate_by_identity:
                raise ReviewCsvBuildError(f"duplicate candidate source_identity: {identity}")
            candidate_by_identity[identity] = candidate.get("body_focus_code_candidate")
        catalog_identities = {str(row.get("source_identity") or "") for row in catalog}
        if set(candidate_by_identity) != catalog_identities:
            raise ReviewCsvBuildError("candidate and catalog source_identity sets differ")
    rows: list[dict[str, str]] = []
    for row in catalog:
        identity = str(row.get("source_identity") or "")
        body_focus = row.get("body_focus_code")
        if (
            candidates is not None
            and not body_focus
            and candidate_by_identity[identity] is not None
        ):
            body_focus = candidate_by_identity[identity]
        if identity in REVIEWED_BODY_FOCUS_OVERRIDES:
            body_focus = REVIEWED_BODY_FOCUS_OVERRIDES[identity]
        result = {
            field: ""
            if field in REVIEW_INPUT_FIELDS
            else csv_value(body_focus if field == "body_focus_code" else row.get(field))
            for field in CSV_FIELDS
        }
        if not result["training_type_code"]:
            result["training_type_code"] = training_type_from_body_focus(body_focus)
        rows.append(result)
    return sorted(rows, key=lambda row: (row["source_identity"], row["name_en"]))


def validate_rows(
    rows: list[dict[str, str]],
    catalog: list[dict[str, Any]],
    candidates: list[dict[str, Any]] | None = None,
) -> None:
    if len(rows) != len(catalog):
        raise ReviewCsvBuildError("CSV row count must equal JSON row count")
    identities = [row["source_identity"] for row in rows]
    if any(not identity for identity in identities):
        raise ReviewCsvBuildError("source_identity must not be blank")
    if len(set(identities)) != len(identities):
        raise ReviewCsvBuildError("source_identity must be unique")
    source_identities = [str(row.get("source_identity") or "") for row in catalog]
    if set(identities) != set(source_identities):
        raise ReviewCsvBuildError("CSV and JSON source_identity sets differ")
    if identities != sorted(identities, key=lambda identity: identity):
        raise ReviewCsvBuildError("rows must be sorted by source_identity")
    for row in rows:
        if any(row[field] for field in REVIEW_INPUT_FIELDS):
            raise ReviewCsvBuildError("review input fields must be blank")
        expected_training_type = training_type_from_body_focus(row["body_focus_code"])
        if row["training_type_code"] != expected_training_type:
            raise ReviewCsvBuildError(
                "training_type_code must be derived from body_focus_code for "
                f"{row['source_identity']}"
            )
    if candidates is not None:
        candidate_by_identity = {
            str(candidate["source_identity"]): candidate.get("body_focus_code_candidate")
            for candidate in candidates
        }
        catalog_by_identity = {str(item.get("source_identity") or ""): item for item in catalog}
        for row in rows:
            identity = row["source_identity"]
            expected = catalog_by_identity[identity].get("body_focus_code")
            if not expected and candidate_by_identity[identity] is not None:
                expected = candidate_by_identity[identity]
            if identity in REVIEWED_BODY_FOCUS_OVERRIDES:
                expected = REVIEWED_BODY_FOCUS_OVERRIDES[identity]
            if row["body_focus_code"] != csv_value(expected):
                raise ReviewCsvBuildError(
                    f"body_focus_code does not match candidate for {identity}"
                )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    catalog = read_catalog(args.input)
    candidates = read_candidates(args.candidates)
    rows = build_rows(catalog, candidates)
    validate_rows(rows, catalog, candidates)
    write_csv(args.output, rows)
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
