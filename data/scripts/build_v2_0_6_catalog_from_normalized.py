"""Build all v2.0.6 catalog review artifacts from one normalized CSV.

The normalized CSV is the only editable catalog source. Raw JSON, additions,
and review-batch exports are not read by this builder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / ("data/generated/exercise-catalog-v2.0.6-draft/review_catalog")
DEFAULT_MET_APPROVAL_MANIFEST = PROJECT_ROOT / (
    "data/reports/v2_0_6_met/met_review_approval_manifest.json"
)
DEFAULT_CATALOG_APPROVAL_MANIFEST = PROJECT_ROOT / (
    "data/reports/v2_0_6_catalog/catalog_approval_manifest.json"
)
ARRAY_FIELDS = {
    "equipment_codes",
    "location_codes",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "safety_relevant_body_area_codes",
    "form_cues_ko",
}
INTEGER_FIELDS = {
    "default_work_seconds",
    "default_seconds_per_rep",
    "default_rest_seconds",
    "default_transition_seconds",
}
BOOLEAN_FIELDS = {"recovery_eligible", "general_pool_included"}
REQUIRED_FIELDS = (
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
)
IGNORED_SOURCE_FIELDS = ("exercise_contraindicated_pain_regions",)
FORBIDDEN_GENERATED_FIELDS = {"rank", "variant_difficulty_rank"}
MET_MAPPING_METHODS = {"DIRECT", "SIMILAR_ACTIVITY"}
MET_REVIEW_STATUS_CODES = {"REVIEW_REQUIRED", "DOMAIN_APPROVED"}


class NormalizedCatalogError(ValueError):
    """Raised when the canonical CSV is invalid."""


def _parse_value(field: str, value: str | None) -> Any:
    raw = (value or "").strip()
    if field in ARRAY_FIELDS:
        return [item.strip() for item in raw.split("|") if item.strip()] if raw else []
    if field in INTEGER_FIELDS:
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError as exc:
            raise NormalizedCatalogError(f"{field} must be an integer: {raw}") from exc
    if field in BOOLEAN_FIELDS:
        if not raw:
            return None
        if raw.lower() == "true":
            return True
        if raw.lower() == "false":
            return False
        raise NormalizedCatalogError(f"{field} must be true or false: {raw}")
    if field == "met_value":
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError as exc:
            raise NormalizedCatalogError(f"met_value must be numeric: {raw}") from exc
        if not math.isfinite(value):
            raise NormalizedCatalogError(f"met_value must be finite: {raw}")
        return value
    return raw or None


def _validate_catalog_approval(
    path: Path, catalog: list[dict[str, Any]], approval_manifest: Path | None
) -> None:
    approved_count = sum(
        str(record.get("review_status_code") or "") == "DOMAIN_APPROVED" for record in catalog
    )
    if not approved_count:
        return
    if approval_manifest is None or not approval_manifest.is_file():
        raise NormalizedCatalogError(
            "DOMAIN_APPROVED catalog rows require a catalog approval manifest"
        )
    try:
        approval = json.loads(approval_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NormalizedCatalogError("catalog approval manifest is invalid") from exc
    if (
        approval.get("review_status_code") != "DOMAIN_APPROVED"
        or approval.get("source_catalog_sha256") != _sha256(path)
        or approval.get("record_count") != len(catalog)
        or approval.get("after_review_status_counts") != {"DOMAIN_APPROVED": len(catalog)}
    ):
        raise NormalizedCatalogError("catalog approval manifest does not match CSV")


def read_catalog(
    path: Path,
    met_approval_manifest: Path | None = None,
    catalog_approval_manifest: Path | None = DEFAULT_CATALOG_APPROVAL_MANIFEST,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            field_order = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        raise NormalizedCatalogError(f"cannot read normalized catalog: {path}") from exc
    missing = sorted(set(REQUIRED_FIELDS) - set(field_order))
    if missing:
        raise NormalizedCatalogError(
            f"normalized catalog is missing required fields: {', '.join(missing)}"
        )
    forbidden = sorted(FORBIDDEN_GENERATED_FIELDS.intersection(field_order))
    if forbidden:
        raise NormalizedCatalogError(
            "rank fields must not be present in normalized/generated v2.0.6 catalog: "
            + ", ".join(forbidden)
        )
    if not rows:
        raise NormalizedCatalogError("normalized catalog must contain at least one row")
    catalog: list[dict[str, Any]] = []
    identities: set[str] = set()
    stable_codes: set[str] = set()
    for index, row in enumerate(rows, 2):
        if None in row:
            raise NormalizedCatalogError(f"row {index} has more values than the header")
        parsed = {field: _parse_value(field, row.get(field)) for field in field_order}
        identity = str(parsed.get("source_identity") or "")
        if not identity or identity in identities:
            raise NormalizedCatalogError(f"source_identity is blank or duplicated at row {index}")
        identities.add(identity)
        stable = str(parsed.get("stable_code") or "")
        if stable and stable in stable_codes:
            raise NormalizedCatalogError(f"stable_code is duplicated at row {index}: {stable}")
        if stable:
            stable_codes.add(stable)
        met_value = parsed.get("met_value")
        met_activity = str(parsed.get("met_source_activity_code") or "")
        met_source = str(parsed.get("met_source_code") or "")
        met_method = str(parsed.get("met_mapping_method_code") or "")
        met_status = str(parsed.get("met_review_status_code") or "")
        met_policy = str(parsed.get("met_policy_version") or "")
        if met_value is not None:
            if not met_activity or not met_source or met_method not in MET_MAPPING_METHODS:
                raise NormalizedCatalogError(
                    f"MET provenance is incomplete at row {index}: {identity}"
                )
        elif met_activity or met_source or met_method:
            raise NormalizedCatalogError(
                f"blank MET value cannot retain activity provenance at row {index}: {identity}"
            )
        if met_status not in MET_REVIEW_STATUS_CODES or not met_policy:
            raise NormalizedCatalogError(
                f"MET review provenance has an invalid status at row {index}: {identity}"
            )
        catalog.append(parsed)
    approved_count = sum(
        str(record.get("met_review_status_code") or "") == "DOMAIN_APPROVED" for record in catalog
    )
    if approved_count:
        if met_approval_manifest is None or not met_approval_manifest.is_file():
            raise NormalizedCatalogError("DOMAIN_APPROVED MET rows require an approval manifest")
        try:
            approval = json.loads(met_approval_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NormalizedCatalogError("MET approval manifest is invalid") from exc
        if approval.get("review_status_code") != "DOMAIN_APPROVED":
            raise NormalizedCatalogError("MET approval manifest is not DOMAIN_APPROVED")
        if approval.get("source_catalog_sha256") != _sha256(path):
            raise NormalizedCatalogError("MET approval manifest source hash does not match CSV")
        if approval.get("approved_record_count") != approved_count:
            raise NormalizedCatalogError("MET approval manifest record count does not match CSV")
    _validate_catalog_approval(path, catalog, catalog_approval_manifest)
    return catalog, field_order


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, records: list[dict[str, Any]], field_order: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_order, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in field_order})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_mapping(
    records: list[dict[str, Any]], field_order: list[str], input_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    fields: dict[str, dict[str, int | str | None]] = {}
    mapped_records: list[dict[str, Any]] = []
    for field in field_order:
        values = [record.get(field) for record in records]
        non_empty = sum(value not in (None, [], "") for value in values)
        fields[field] = {
            "source": f"normalized_catalog:{input_path}#{field}",
            "normalized_value_count": non_empty,
            "empty_output_count": len(records) - non_empty,
        }
    for record in records:
        mapped_records.append(
            {
                "source_identity": record.get("source_identity"),
                "source_track": record.get("source_track"),
                "fields": {
                    field: {
                        "source": (
                            f"normalized_catalog:{input_path}#{field}"
                            if record.get(field) not in (None, [], "")
                            else "UNAVAILABLE_IN_NORMALIZED_CATALOG"
                        ),
                        "value": record.get(field),
                    }
                    for field in field_order
                },
                "ignored_source_fields": list(IGNORED_SOURCE_FIELDS),
            }
        )
    mapping = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy": {
            "single_source_of_truth": True,
            "input_is_the_only_editable_catalog_file": True,
            "raw_json_read_by_final_builder": False,
            "review_csv_read_by_final_builder": False,
            "korean_labels_to_machine_codes": "UNMAPPED_VALUES_REMAIN_EMPTY",
            "safety_relevant_body_area_codes": "NO_PRIMARY_OR_SECONDARY_COPY",
            "pain_contraindication_fields": "NOT_COPIED",
        },
        "source": {"path": str(input_path), "sha256": _sha256(input_path)},
        "required_fields": list(REQUIRED_FIELDS),
        "forbidden_generated_fields": sorted(FORBIDDEN_GENERATED_FIELDS),
        "field_order": field_order,
        "fields": fields,
        "records": mapped_records,
    }
    gaps = {
        "status": "DRAFT",
        "production_eligible": False,
        "source": mapping["source"],
        "record_count": len(records),
        "fields": fields,
    }
    return mapping, gaps


def build(
    input_path: Path,
    output_dir: Path,
    met_approval_manifest: Path | None = DEFAULT_MET_APPROVAL_MANIFEST,
    catalog_approval_manifest: Path | None = DEFAULT_CATALOG_APPROVAL_MANIFEST,
) -> dict[str, Any]:
    records, field_order = read_catalog(
        input_path, met_approval_manifest, catalog_approval_manifest
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "exercise_catalog_merged_draft.json"
    csv_path = output_dir / "exercise_catalog_merged_draft.csv"
    _write_json(json_path, records)
    _write_csv(csv_path, records, field_order)
    mapping, gaps = _source_mapping(records, field_order, input_path)
    _write_json(output_dir / "exercise_catalog_source_mapping.json", mapping)
    _write_json(output_dir / "exercise_catalog_source_gap_report.json", gaps)
    _write_json(
        output_dir / "exercise_catalog_unmapped_fields.json",
        {
            "status": "DRAFT",
            "production_eligible": False,
            "ignored_source_fields": list(IGNORED_SOURCE_FIELDS),
            "policy": "not copied into the catalog or safety policy data",
        },
    )
    _write_json(
        output_dir / "exercise_catalog_duplicate_review.json",
        {
            "status": "DRAFT",
            "production_eligible": False,
            "stable_code_duplicate_count": 0,
            "source_identity_duplicate_count": 0,
            "records": [],
        },
    )
    report = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy": {
            "single_source_of_truth": str(input_path),
            "raw_json_read": False,
            "additions_json_read": False,
            "review_csv_read": False,
            "generated_files_are_not_editable_sources": True,
        },
        "inputs": {
            "normalized_catalog": {
                "path": str(input_path),
                "sha256": _sha256(input_path),
                "records": len(records),
            }
        },
        "catalog_approval_manifest": (
            {
                "path": str(catalog_approval_manifest),
                "sha256": _sha256(catalog_approval_manifest),
            }
            if catalog_approval_manifest and catalog_approval_manifest.is_file()
            else None
        ),
        "output": {
            "path": str(json_path),
            "sha256": _sha256(json_path),
            "records": len(records),
        },
        "csv_output": {
            "path": str(csv_path),
            "sha256": _sha256(csv_path),
            "records": len(records),
            "encoding": "UTF-8-BOM",
            "array_separator": "|",
        },
        "schema_fields": field_order,
        "required_catalog_fields": list(REQUIRED_FIELDS),
        "forbidden_generated_fields": sorted(FORBIDDEN_GENERATED_FIELDS),
        "required_catalog_fields_missing": sorted(set(REQUIRED_FIELDS) - set(field_order)),
        "required_catalog_field_empty_counts": {
            field: sum(record.get(field) in (None, [], "") for record in records)
            for field in REQUIRED_FIELDS
        },
        "source_mapping_output": str(output_dir / "exercise_catalog_source_mapping.json"),
        "source_gap_report": str(output_dir / "exercise_catalog_source_gap_report.json"),
        "rank_usage_report": {
            "rank_fields_present": sorted(FORBIDDEN_GENERATED_FIELDS.intersection(field_order)),
            "rank_fields_generated": [],
            "rank_fields_used": [],
        },
    }
    _write_json(output_dir / "exercise_catalog_merge_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--met-approval-manifest", type=Path, default=DEFAULT_MET_APPROVAL_MANIFEST)
    parser.add_argument(
        "--catalog-approval-manifest", type=Path, default=DEFAULT_CATALOG_APPROVAL_MANIFEST
    )
    args = parser.parse_args()
    report = build(
        args.input,
        args.output_dir,
        args.met_approval_manifest,
        args.catalog_approval_manifest,
    )
    print(json.dumps({"records": report["output"]["records"], "status": report["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
