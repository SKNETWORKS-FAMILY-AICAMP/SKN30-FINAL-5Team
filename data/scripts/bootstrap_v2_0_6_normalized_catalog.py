"""Create the single editable v2.0.6 normalized catalog from a draft export.

This is a one-time bootstrap. After the normalized CSV exists, human review
must edit that CSV only; the final builder does not read raw, additions, or
review-batch files.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / (
    "data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog/"
    "exercise_catalog_merged_draft.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
ARRAY_FIELDS = {
    "equipment_codes",
    "location_codes",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "safety_relevant_body_area_codes",
    "form_cues_ko",
}
REQUIRED_FIELDS = {
    "stable_code",
    "name_ko",
    "name_en",
    "training_type_code",
    "body_focus_code",
    "primary_movement_pattern_code",
    "difficulty_code",
    "timing_mode_code",
    "default_work_seconds",
    "default_seconds_per_rep",
    "default_rest_seconds",
    "default_transition_seconds",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "safety_relevant_body_area_codes",
    "equipment_codes",
    "location_codes",
    "form_cues_ko",
    "review_status_code",
    "source_identity",
    "source_track",
    "met_value",
    "met_source_code",
    "met_source_activity_code",
    "met_mapping_method_code",
    "met_review_status_code",
    "met_policy_version",
}


class BootstrapError(ValueError):
    """Raised when the draft cannot initialize the canonical CSV."""


def _read_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"cannot read draft catalog: {path}") from exc
    if not isinstance(value, list) or not value or any(not isinstance(row, dict) for row in value):
        raise BootstrapError("draft catalog must be a non-empty array of objects")
    field_order = list(value[0])
    if not REQUIRED_FIELDS.issubset(field_order):
        missing = sorted(REQUIRED_FIELDS - set(field_order))
        raise BootstrapError(f"draft catalog is missing required fields: {', '.join(missing)}")
    if any(set(row) != set(field_order) for row in value):
        raise BootstrapError("draft catalog rows do not share one schema")
    identities = [str(row.get("source_identity") or "") for row in value]
    if any(not identity for identity in identities) or len(set(identities)) != len(identities):
        raise BootstrapError("source_identity must be non-empty and unique")
    return value


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if any(item is None for item in value):
            raise BootstrapError("catalog arrays must not contain null values")
        return "|".join(str(item) for item in value)
    if isinstance(value, (dict, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def write_catalog(path: Path, catalog: list[dict[str, Any]]) -> None:
    field_order = list(catalog[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_order, lineterminator="\n")
        writer.writeheader()
        for row in catalog:
            writer.writerow({field: _csv_value(row.get(field)) for field in field_order})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        raise SystemExit(
            f"output exists; use --force only for an intentional re-bootstrap: {args.output}"
        )
    catalog = _read_catalog(args.input)
    write_catalog(args.output, catalog)
    print(f"wrote {len(catalog)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
