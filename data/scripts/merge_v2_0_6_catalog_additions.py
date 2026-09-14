"""Conservatively merge v2.0.6 exercise additions into the existing catalog.

The output is deliberately a JSON DRAFT, not an importer bundle. Required
catalog columns are always materialized, but a value is filled only when the
raw Gymvisual JSON contains a directly corresponding value or an existing
normalized catalog value is already present. Unknown taxonomy, timing, body
area, Safety, identity, and display values remain empty until review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

# The scripts directory must be on sys.path before importing the shared mapper.
# isort: off
from align_source_candidates import map_equipment  # noqa: E402
# isort: on


DEFAULT_CATALOG = (
    PROJECT_ROOT
    / "data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog/exercises.jsonl"
)
DEFAULT_ADDITIONS = DEFAULT_CATALOG.parent / "exercise_catalog_additions.json"
DEFAULT_OUTPUT = DEFAULT_CATALOG.parent / "exercise_catalog_merged_draft.json"
DEFAULT_CSV_OUTPUT = DEFAULT_OUTPUT.with_suffix(".csv")
DEFAULT_REPORT_DIR = DEFAULT_CATALOG.parent
DEFAULT_GYMVISUAL_SOURCE = PROJECT_ROOT / "data/raw/gym_visual/exercises.json"
DEFAULT_REVIEW_CSV = (
    PROJECT_ROOT / "data/validation/review_batches/v2_0_6_training_body_focus_review.csv"
)
DEFAULT_SOURCE_MAPPING_OUTPUT = PROJECT_ROOT / "data/normalized/v2_0_6_catalog_source_mapping.json"

UNMAPPED_FIELDS = (
    "category",
    "muscle_group",
    "secondary_muscles",
    "target",
    "equipment",
    "instructions_ko",
    "exercise_contraindicated_pain_regions",
)
ARRAY_FIELDS = {
    "equipment_codes",
    "location_codes",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "safety_relevant_body_area_codes",
    "form_cues_ko",
}
BOOLEAN_FIELDS = {"recovery_eligible", "general_pool_included"}
REQUIRED_CATALOG_FIELDS = (
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
)
# These are the only raw-to-catalog mappings used by this generator. The
# equipment mapping is the existing controlled vocabulary mapper; a mapping
# miss is converted to an empty value rather than REVIEW_REQUIRED text.
RAW_FIELD_SOURCES = {
    "source_identity": "raw.id",
    "name_en": "raw.name",
    "form_cues_ko": "raw.instruction_steps.ko",
    "equipment_codes": "raw.equipment -> existing equipment code mapping",
    "source_track": "raw Gymvisual ID+name identity proof",
}
REVIEW_FIELD_SOURCES = {
    "stable_code": "review_csv.stable_code",
    "name_ko": "review_csv.name_ko",
}
SAFETY_SOURCE_FIELD = "raw.exercise_contraindicated_pain_regions"
ADDITION_REQUIRED_FIELDS = (
    "id",
    "name",
    *UNMAPPED_FIELDS,
    "instructions_steps_ko",
)
SNAKE_CASE_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+\b")
SAFETY_LANGUAGE_RE = re.compile(r"(?:진단|치료|처방|질환|질병|의학적)")


class MergeError(ValueError):
    """Raised when the merge cannot be performed unambiguously."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MergeError(f"catalog cannot be read: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MergeError(f"invalid catalog JSON at line {line_number}: {path}") from exc
        if not isinstance(value, dict):
            raise MergeError(f"catalog line {line_number} is not an object: {path}")
        rows.append(value)
    return rows


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeError(f"JSON input cannot be read: {path}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any, *, preserve_record_order: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=not preserve_record_order,
    )
    path.write_text(serialized + "\n", encoding="utf-8", newline="\n")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if any(item is None for item in value):
            raise MergeError("catalog arrays must not contain null values")
        return "|".join(str(item) for item in value)
    if isinstance(value, (dict, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _write_review_csv(path: Path, records: list[dict[str, Any]], field_order: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_order, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in field_order})


def normalize_name(value: str) -> str:
    """Apply only the name normalization allowed by the merge contract."""

    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return not value
    return False


def _validate_catalog_schema(catalog: list[dict[str, Any]]) -> list[str]:
    if not catalog:
        raise MergeError("existing catalog is empty")
    field_order = list(catalog[0])
    field_set = set(field_order)
    if not field_set:
        raise MergeError("existing catalog schema is empty")
    for index, row in enumerate(catalog, 1):
        if set(row) != field_set:
            raise MergeError(f"catalog row {index} does not match the first row schema")
    # The v2.0.5 input predates safety_relevant_body_area_codes. Add missing
    # required columns in a stable position while preserving every input
    # column and its order.
    for required in REQUIRED_CATALOG_FIELDS:
        if required in field_set:
            continue
        if (
            required == "safety_relevant_body_area_codes"
            and "secondary_body_area_codes" in field_set
        ):
            index = field_order.index("secondary_body_area_codes") + 1
            field_order.insert(index, required)
        else:
            field_order.append(required)
        field_set.add(required)
    return field_order


def _validate_additions(additions: Any) -> list[dict[str, Any]]:
    if not isinstance(additions, list):
        raise MergeError("additions JSON must be an array")
    ids: set[str] = set()
    names: dict[str, str] = {}
    for index, addition in enumerate(additions, 1):
        if not isinstance(addition, dict):
            raise MergeError(f"addition {index} is not an object")
        missing = [field for field in ADDITION_REQUIRED_FIELDS if field not in addition]
        if missing:
            raise MergeError(f"addition {index} is missing fields: {', '.join(missing)}")
        source_identity = addition["id"]
        name = addition["name"]
        if not isinstance(source_identity, str) or not source_identity:
            raise MergeError(f"addition {index} has an invalid id")
        if not isinstance(name, str) or not name.strip():
            raise MergeError(f"addition {index} has an invalid name")
        if source_identity in ids:
            raise MergeError(f"duplicate addition id: {source_identity}")
        ids.add(source_identity)
        normalized = normalize_name(name)
        if normalized in names:
            raise MergeError(f"duplicate addition name: {names[normalized]} and {source_identity}")
        names[normalized] = source_identity
        steps = addition["instructions_steps_ko"]
        if not isinstance(steps, list) or any(not isinstance(step, str) for step in steps):
            raise MergeError(f"addition {source_identity} has invalid instruction steps")
    return additions


def _verified_gymvisual_ids(
    additions: Iterable[dict[str, Any]], source_rows: Any
) -> tuple[set[str], dict[str, str]]:
    """Return IDs whose ID and name are proven by the raw Gymvisual source."""

    if not isinstance(source_rows, list):
        return set(), {}
    source_by_id: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            source_by_id[row["id"]] = row
    verified: set[str] = set()
    mismatches: dict[str, str] = {}
    for addition in additions:
        identity = addition["id"]
        source = source_by_id.get(identity)
        if source is not None and source.get("name") == addition["name"]:
            verified.add(identity)
        elif source is None:
            mismatches[identity] = "ID_NOT_FOUND_IN_GYMVISUAL_SOURCE"
        else:
            mismatches[identity] = "NAME_MISMATCH_WITH_GYMVISUAL_SOURCE"
    return verified, mismatches


def _source_by_id(source_rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(source_rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        identity = row["id"]
        if identity in result:
            raise MergeError(f"duplicate Gymvisual raw source id: {identity}")
        result[identity] = row
    return result


def _read_review_identity_fields(path: Path) -> dict[str, dict[str, str]]:
    import csv

    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"source_identity", "stable_code", "name_ko"}
            if not required.issubset(reader.fieldnames or set()):
                raise MergeError("review CSV is missing stable_code/name_ko/source_identity")
            result: dict[str, dict[str, str]] = {}
            for row in reader:
                identity = (row.get("source_identity") or "").strip()
                if not identity or identity in result:
                    raise MergeError("review CSV has a blank or duplicate source_identity")
                result[identity] = {
                    field: (row.get(field) or "").strip() for field in ("stable_code", "name_ko")
                }
    except OSError as exc:
        raise MergeError(f"review CSV cannot be read: {path}") from exc
    return result


def _raw_mapping_values(source: dict[str, Any] | None) -> dict[str, Any]:
    """Return only values proven by one raw Gymvisual record."""
    if source is None:
        return {}
    values: dict[str, Any] = {
        "source_identity": source.get("id"),
        "name_en": source.get("name"),
        "source_track": "gymvisual",
    }
    steps = source.get("instruction_steps")
    if isinstance(steps, dict) and isinstance(steps.get("ko"), list):
        values["form_cues_ko"] = steps["ko"]
    equipment_code = map_equipment(source.get("equipment"))
    if equipment_code != "REVIEW_REQUIRED":
        values["equipment_codes"] = [equipment_code]
    return {field: value for field, value in values.items() if not _is_empty(value)}


def _clean_steps(steps: list[str]) -> tuple[list[str], list[str], list[str]]:
    cleaned: list[str] = []
    seen: set[str] = set()
    issues: list[str] = []
    for step in steps:
        value = step.strip()
        if not value:
            issues.append("EMPTY_STEP_REMOVED")
            continue
        if value in seen:
            issues.append("DUPLICATE_STEP_REMOVED")
            continue
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        issues.append("NO_NON_EMPTY_STEPS")
    content = " ".join(cleaned)
    tokens = sorted(set(SNAKE_CASE_RE.findall(content)))
    if tokens:
        issues.append("DEVELOPMENT_SNAKE_CASE_TOKEN_PRESENT")
    if SAFETY_LANGUAGE_RE.search(content):
        issues.append("DIAGNOSIS_TREATMENT_LANGUAGE_PRESENT")
    return cleaned, sorted(set(issues)), tokens


def _empty_value(field: str) -> Any:
    if field in ARRAY_FIELDS:
        return []
    if field in BOOLEAN_FIELDS:
        return None
    return None


def _new_draft_record(
    addition: dict[str, Any],
    field_order: list[str],
    raw_values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_steps = raw_values.get("form_cues_ko", [])
    cues, issues, snake_tokens = _clean_steps(raw_steps if isinstance(raw_steps, list) else [])
    record = {field: _empty_value(field) for field in field_order}
    for field, value in raw_values.items():
        if field in record:
            record[field] = cues if field == "form_cues_ko" else value
    audit = {
        "source_identity": addition["id"],
        "step_count_before": len(raw_steps) if isinstance(raw_steps, list) else 0,
        "step_count_after": len(cues),
        "issues": issues,
        "development_snake_case_tokens": snake_tokens,
        "safety_language_detected": "DIAGNOSIS_TREATMENT_LANGUAGE_PRESENT" in issues,
        "raw_source_fields_used": sorted(raw_values),
    }
    return record, audit


def _existing_dedup(
    catalog: list[dict[str, Any]], field_order: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    seen_stable: dict[str, int] = {}
    seen_source: dict[tuple[str, str], int] = {}
    seen_rows: dict[str, int] = {}
    removed: list[dict[str, Any]] = []
    for index, original in enumerate(catalog):
        row = {field: original.get(field) for field in field_order}
        stable = row.get("stable_code")
        source_track = row.get("source_track")
        source_identity = row.get("source_identity")
        source_key = (
            (source_track, source_identity)
            if isinstance(source_track, str) and isinstance(source_identity, str)
            else None
        )
        row_key = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        reason = None
        kept_index = None
        if isinstance(stable, str) and stable and stable in seen_stable:
            reason, kept_index = "EXISTING_STABLE_CODE_DUPLICATE", seen_stable[stable]
        elif source_key is not None and all(source_key) and source_key in seen_source:
            reason, kept_index = "EXISTING_SOURCE_IDENTITY_DUPLICATE", seen_source[source_key]
        elif row_key in seen_rows:
            reason, kept_index = "EXISTING_COMPLETE_RECORD_DUPLICATE", seen_rows[row_key]
        if reason is not None:
            removed.append(
                {
                    "catalog_row_index": index,
                    "kept_catalog_row_index": kept_index,
                    "stable_code": stable,
                    "source_track": row.get("source_track"),
                    "source_identity": row.get("source_identity"),
                    "duplicate_reason_code": reason,
                    "action": "KEEP_FIRST_EXISTING_RECORD",
                }
            )
            continue
        kept_index = len(kept)
        kept.append(row)
        if isinstance(stable, str) and stable:
            seen_stable[stable] = kept_index
        if source_key is not None and all(source_key):
            seen_source[source_key] = kept_index
        seen_rows[row_key] = kept_index
    return kept, removed


def _record_conflicts(
    existing: dict[str, Any],
    addition_id: str,
    values: dict[str, Any],
    duplicate_reason_code: str,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for field, addition_value in values.items():
        existing_value = existing.get(field)
        if _is_empty(addition_value) or _is_empty(existing_value):
            continue
        if existing_value != addition_value:
            conflicts.append(
                {
                    "addition_id": addition_id,
                    "duplicate_reason_code": duplicate_reason_code,
                    "existing_stable_code": existing.get("stable_code"),
                    "field": field,
                    "existing_value": existing_value,
                    "addition_value": addition_value,
                    "action": "KEEP_EXISTING_NON_EMPTY_VALUE",
                }
            )
    return conflicts


def _merge_direct_fields(
    existing: dict[str, Any],
    addition_id: str,
    values: dict[str, Any],
    duplicate_reason_code: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    merged = dict(existing)
    conflicts = _record_conflicts(merged, addition_id, values, duplicate_reason_code)
    updates: list[dict[str, Any]] = []
    for field, addition_value in values.items():
        if field not in merged or _is_empty(addition_value):
            continue
        if _is_empty(merged.get(field)):
            merged[field] = addition_value
            updates.append(
                {
                    "addition_id": addition_id,
                    "field": field,
                    "value": addition_value,
                    "action": "FILL_EXISTING_EMPTY_VALUE",
                }
            )
    return merged, conflicts, updates


def _duplicate_entry(
    existing: dict[str, Any], addition: dict[str, Any], reason: str, status: str
) -> dict[str, Any]:
    return {
        "existing_stable_code": existing.get("stable_code"),
        "existing_source_track": existing.get("source_track"),
        "existing_source_identity": existing.get("source_identity"),
        "addition_id": addition["id"],
        "addition_name_en": addition["name"],
        "existing_name_en": existing.get("name_en"),
        "addition_equipment": addition.get("equipment"),
        "existing_equipment_codes": existing.get("equipment_codes", []),
        "addition_target": addition.get("target"),
        "addition_muscle_group": addition.get("muscle_group"),
        "duplicate_reason_code": reason,
        "review_status": status,
    }


def merge_records(
    catalog: list[dict[str, Any]],
    additions: Any,
    gymvisual_source: Any = None,
    review_identity_fields: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    field_order = _validate_catalog_schema(catalog)
    validated_additions = _validate_additions(additions)
    source_by_id = _source_by_id(gymvisual_source)
    verified_ids, provenance_mismatches = _verified_gymvisual_ids(
        validated_additions, gymvisual_source
    )
    existing, existing_duplicates = _existing_dedup(catalog, field_order)

    by_pair: dict[tuple[Any, Any], dict[str, Any]] = {}
    by_identity: dict[Any, dict[str, Any]] = {}
    by_stable: dict[Any, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in existing:
        pair = (row.get("source_track"), row.get("source_identity"))
        if all(isinstance(value, str) and value for value in pair):
            by_pair[pair] = row
        if row.get("source_identity"):
            by_identity[row["source_identity"]] = row
        if row.get("stable_code"):
            by_stable[row["stable_code"]] = row
        name = row.get("name_en")
        if isinstance(name, str) and name.strip():
            by_name.setdefault(normalize_name(name), []).append(row)

    records = list(existing)
    exact_entries: list[dict[str, Any]] = []
    name_only_entries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    content_audits: list[dict[str, Any]] = []
    unmapped_records: list[dict[str, Any]] = []
    merged_addition_ids: set[str] = set()
    new_addition_ids: set[str] = set()
    name_only_ids: set[str] = set()
    review_updates: list[dict[str, Any]] = []

    for addition in validated_additions:
        identity = addition["id"]
        raw_source = source_by_id.get(identity) if identity in verified_ids else None
        raw_values = _raw_mapping_values(raw_source)
        cues, cue_issues, snake_tokens = _clean_steps(
            raw_values.get("form_cues_ko", [])
            if isinstance(raw_values.get("form_cues_ko", []), list)
            else []
        )
        content_audits.append(
            {
                "source_identity": identity,
                "step_count_before": len(raw_values.get("form_cues_ko", [])),
                "step_count_after": len(cues),
                "issues": cue_issues,
                "development_snake_case_tokens": snake_tokens,
                "safety_language_detected": bool(
                    "DIAGNOSIS_TREATMENT_LANGUAGE_PRESENT" in cue_issues
                ),
                "raw_source_fields_used": sorted(raw_values),
            }
        )
        unmapped_records.append(
            {
                "source_identity": identity,
                "source_track": raw_values.get("source_track"),
                "unmapped_fields": {field: addition.get(field) for field in UNMAPPED_FIELDS},
                "ignored_for_catalog": ["exercise_contraindicated_pain_regions"],
            }
        )

        existing_match = None
        reason = None
        verified_track = raw_values.get("source_track")
        pair = (verified_track, identity)
        if isinstance(verified_track, str) and pair in by_pair:
            existing_match = by_pair[pair]
            reason = "EXACT_SOURCE_TRACK_IDENTITY"
        elif isinstance(verified_track, str) and identity in by_identity:
            candidate = by_identity[identity]
            if _is_empty(candidate.get("source_track")):
                existing_match = candidate
                reason = "EXACT_VERIFIED_SOURCE_IDENTITY"
        elif addition.get("stable_code") and addition["stable_code"] in by_stable:
            existing_match = by_stable[addition["stable_code"]]
            reason = "STABLE_CODE_EXACT_MATCH"

        if existing_match is not None:
            assert reason is not None
            merged, row_conflicts, row_fills = _merge_direct_fields(
                existing_match, identity, {**raw_values, "form_cues_ko": cues}, reason
            )
            existing_match.clear()
            existing_match.update(merged)
            conflicts.extend(row_conflicts)
            fills.extend(row_fills)
            exact_entries.append(_duplicate_entry(existing_match, addition, reason, "AUTO_MERGED"))
            merged_addition_ids.add(identity)
        else:
            name_matches = by_name.get(normalize_name(addition["name"]), [])
            if name_matches:
                name_only_ids.add(identity)
                for name_match in name_matches:
                    name_only_entries.append(
                        _duplicate_entry(
                            name_match,
                            addition,
                            "NAME_EXACT_MATCH_ONLY",
                            "REVIEW_REQUIRED",
                        )
                    )
            review_values = {
                field: review_identity_fields[identity][field]
                for field in ("stable_code", "name_ko")
                if review_identity_fields
                and identity in review_identity_fields
                and not _is_empty(review_identity_fields[identity].get(field))
            }
            new_record, _ = _new_draft_record(
                addition,
                field_order,
                {**raw_values, "form_cues_ko": cues, **review_values},
            )
            for field in review_values:
                review_updates.append(
                    {
                        "source_identity": identity,
                        "field": field,
                        "value": review_values[field],
                        "source": REVIEW_FIELD_SOURCES[field],
                    }
                )
            records.append(new_record)
            new_addition_ids.add(identity)

    # Existing rows retain their original order. New DRAFT rows are sorted only
    # by the stable provenance/name tuple specified by the merge contract.
    existing_count = len(existing)
    new_records = records[existing_count:]
    new_records.sort(
        key=lambda row: (
            row.get("source_track") or "",
            row.get("source_identity") or "",
            row.get("name_en") or "",
        )
    )
    records = existing + new_records
    unmapped_field_counts = {field: len(validated_additions) for field in UNMAPPED_FIELDS}
    unmapped_non_empty_counts = {
        field: sum(not _is_empty(addition.get(field)) for addition in validated_additions)
        for field in UNMAPPED_FIELDS
    }
    stable_unconfirmed = sum(_is_empty(row.get("stable_code")) for row in new_records)
    duplicate_review_records = exact_entries + name_only_entries
    validation = _validation_summary(records, field_order, validated_additions, new_records)
    validation["direct_mapping_conflicts_overwritten"] = False
    validation["unmapped_fields_overwritten"] = False
    report = {
        "status": "DRAFT",
        "schema_fields": field_order,
        "direct_mappings": {
            "raw.id": "source_identity",
            "raw.name": "name_en",
            "raw.instruction_steps.ko": "form_cues_ko",
            "raw.equipment": "equipment_codes via existing controlled mapper",
            "source_track": "gymvisual when ID and name match the verified Gymvisual raw source",
        },
        "merge_policy": {
            "direct_mapping_conflict": "KEEP_EXISTING_NON_EMPTY_VALUE",
            "unmapped_fields": "NEVER_AUTOMATICALLY_MAPPED",
            "required_columns": "MATERIALIZE_MISSING_COLUMNS_WITH_EMPTY_VALUES",
            "blank_fill": "RAW_DIRECT_VALUE_OR_EXISTING_NORMALIZED_VALUE_ONLY",
            "stable_code": "PRESERVE_EXISTING_VALUE; FILL_NEW_FROM_REVIEW_CSV; OTHERWISE_EMPTY",
            "name_ko": "PRESERVE_EXISTING_VALUE; FILL_NEW_FROM_REVIEW_CSV; OTHERWISE_EMPTY",
            "review_identity_fields": "FILL_NEW_ROWS_ONLY_BY_EXACT_SOURCE_IDENTITY",
            "safety_relevant_body_area_codes": (
                "RAW_DIRECT_VALUE_ONLY; NEVER_COPY_PRIMARY_OR_SECONDARY"
            ),
            "pain_contraindication_fields": "IGNORE; SAFETY_RULES_REMAIN_SEPARATE",
        },
        "counts": {
            "existing_catalog_records": len(catalog),
            "existing_records_after_deduplication": len(existing),
            "existing_duplicate_rows_removed": len(existing_duplicates),
            "additions_records": len(validated_additions),
            "additions_internal_id_duplicates": 0,
            "additions_internal_name_duplicates": 0,
            "verified_gymvisual_source_records": len(verified_ids),
            "exact_duplicate_merge_count": len(merged_addition_ids),
            "new_draft_record_count": len(new_records),
            "name_exact_match_only_review_required_count": len(name_only_ids),
            "name_exact_match_review_rows": len(name_only_entries),
            "conflict_count": len(conflicts),
            "direct_field_fill_count": sum(
                update["action"] == "FILL_EXISTING_EMPTY_VALUE" for update in fills
            ),
            "direct_field_update_count": len(fills),
            "direct_field_overwrite_count": 0,
            "unmapped_field_count": sum(unmapped_field_counts.values()),
            "unmapped_non_empty_field_count": sum(unmapped_non_empty_counts.values()),
            "stable_code_unconfirmed_count": stable_unconfirmed,
            "identity_field_fill_count": len(review_updates),
            "stable_code_collision_count": 0,
            "importer_ready_count": validation["importer_ready_count"],
            "new_importer_ready_count": validation["new_importer_ready_count"],
        },
        "provenance": {
            "gymvisual_verified_ids": sorted(verified_ids),
            "gymvisual_unverified_ids": provenance_mismatches,
        },
        "validation": validation,
        "conflicts": conflicts,
        "updates": fills,
        "content_audits": content_audits,
        "identity_audits": [],
        "review_identity_updates": review_updates,
        "existing_duplicate_rows_removed": existing_duplicates,
        "importer_output_written": False,
        "source_catalog_overwritten": False,
        "merged_addition_ids": sorted(merged_addition_ids),
        "new_draft_source_identities": sorted(new_addition_ids),
        "name_only_source_identities": sorted(name_only_ids),
        "review_identity_source_identities": sorted(
            {item["source_identity"] for item in review_updates}
        ),
    }
    duplicate_review = {
        "status": "DRAFT",
        "summary": {
            "exact_duplicate_merge_count": len(exact_entries),
            "name_exact_match_only_review_required_count": len(name_only_ids),
            "review_row_count": len(duplicate_review_records),
        },
        "records": duplicate_review_records,
    }
    unmapped = {
        "status": "DRAFT",
        "unmapped_fields": list(UNMAPPED_FIELDS),
        "field_counts": unmapped_field_counts,
        "non_empty_field_counts": unmapped_non_empty_counts,
        "records": unmapped_records,
    }
    return {
        "records": records,
        "report": report,
        "duplicate_review": duplicate_review,
        "unmapped": unmapped,
    }


def _validation_summary(
    records: list[dict[str, Any]],
    field_order: list[str],
    additions: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> dict[str, Any]:
    stable_values = [
        row.get("stable_code") for row in records if not _is_empty(row.get("stable_code"))
    ]
    source_values = [
        (row.get("source_track"), row.get("source_identity"))
        for row in records
        if not _is_empty(row.get("source_track")) and not _is_empty(row.get("source_identity"))
    ]
    serialized = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in records
    ]
    required_fields = {
        "stable_code",
        "name_ko",
        "name_en",
        "training_type_code",
        "body_focus_code",
        "primary_movement_pattern_code",
        "difficulty_code",
        "timing_mode_code",
        "default_rest_seconds",
        "default_transition_seconds",
        "recovery_eligible",
        "primary_body_area_codes",
        "equipment_codes",
        "location_codes",
        "instruction_summary_ko",
        "form_cues_ko",
        "instruction_content_version",
        "review_status_code",
        "source_track",
        "source_identity",
    }

    def importer_ready(row: dict[str, Any]) -> bool:
        if not required_fields.issubset(row):
            return False
        if any(_is_empty(row.get(field)) for field in required_fields):
            return False
        if not isinstance(row.get("form_cues_ko"), list) or not row["form_cues_ko"]:
            return False
        return True

    new_ready = sum(importer_ready(row) for row in new_records)
    return {
        "output_schema_matches_existing": all(list(row) == field_order for row in records),
        "stable_code_duplicate_count": len(stable_values) - len(set(stable_values)),
        "source_track_identity_duplicate_count": len(source_values) - len(set(source_values)),
        "complete_output_record_duplicate_count": len(serialized) - len(set(serialized)),
        "additions_internal_id_duplicate_count": len(additions)
        - len({addition["id"] for addition in additions}),
        "new_records_overwrite_existing_non_empty_values": False,
        "automatic_taxonomy_inference_count": 0,
        "exactly_merged_additions_reintroduced_as_new": False,
        "name_only_items_automatically_deleted": False,
        "importer_ready_count": sum(importer_ready(row) for row in records),
        "new_importer_ready_count": new_ready,
        "new_records_have_identity_fields": all(
            not _is_empty(row.get("source_identity")) and not _is_empty(row.get("source_track"))
            for row in new_records
        ),
        "required_catalog_fields": list(REQUIRED_CATALOG_FIELDS),
        "required_catalog_fields_missing": sorted(set(REQUIRED_CATALOG_FIELDS) - set(field_order)),
        "required_catalog_field_empty_counts": {
            field: sum(_is_empty(row.get(field)) for row in records)
            for field in REQUIRED_CATALOG_FIELDS
        },
    }


def _same_value(left: Any, right: Any) -> bool:
    return left == right


def _source_mapping_report(
    records: list[dict[str, Any]],
    source_rows: Any,
    raw_source_path: Path | None,
    review_identity_fields: dict[str, dict[str, str]] | None = None,
    review_source_path: Path | None = None,
    review_applied_ids: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build auditable field provenance and raw-source gap reports."""
    source_by_id = _source_by_id(source_rows)
    raw_path = str(raw_source_path) if raw_source_path else ""
    field_counts = {
        field: {
            "raw_source_field": RAW_FIELD_SOURCES.get(field),
            "raw_value_count": 0,
            "filled_from_raw_count": 0,
            "review_value_count": 0,
            "filled_from_review_count": 0,
            "preserved_existing_count": 0,
            "unavailable_in_raw_count": len(records),
            "empty_output_count": 0,
        }
        for field in REQUIRED_CATALOG_FIELDS
    }
    mapped_records: list[dict[str, Any]] = []

    for record in records:
        identity = str(record.get("source_identity") or "")
        raw = source_by_id.get(identity) if record.get("source_track") == "gymvisual" else None
        raw_values = _raw_mapping_values(raw)
        review_values = review_identity_fields.get(identity, {}) if review_identity_fields else {}
        fields: dict[str, dict[str, Any]] = {}
        for field in REQUIRED_CATALOG_FIELDS:
            output_value = record.get(field)
            raw_value = raw_values.get(field)
            review_value = review_values.get(field)
            review_is_match = bool(
                review_identity_fields
                and review_applied_ids
                and identity in review_applied_ids
                and field in REVIEW_FIELD_SOURCES
            )
            if (
                review_is_match
                and not _is_empty(review_value)
                and _same_value(output_value, review_value)
            ):
                source = (
                    f"{review_source_path}:{REVIEW_FIELD_SOURCES[field]}"
                    if review_source_path
                    else REVIEW_FIELD_SOURCES[field]
                )
                field_counts[field]["review_value_count"] += 1
                field_counts[field]["filled_from_review_count"] += 1
            elif raw is not None and field in raw_values and _same_value(output_value, raw_value):
                source = f"{raw_path}:{RAW_FIELD_SOURCES[field]}"
                field_counts[field]["raw_value_count"] += 1
                field_counts[field]["filled_from_raw_count"] += 1
                field_counts[field]["unavailable_in_raw_count"] -= 1
            elif not _is_empty(output_value):
                source = "existing_normalized_catalog_value"
                field_counts[field]["preserved_existing_count"] += 1
                if raw is not None and field in raw_values:
                    field_counts[field]["raw_value_count"] += 1
                    field_counts[field]["unavailable_in_raw_count"] -= 1
            else:
                source = "UNAVAILABLE_IN_RAW_SOURCE"
                field_counts[field]["empty_output_count"] += 1
            fields[field] = {"source": source, "value": output_value}
        mapped_records.append(
            {
                "source_track": record.get("source_track"),
                "source_identity": record.get("source_identity"),
                "stable_code": record.get("stable_code"),
                "fields": fields,
                "ignored_source_fields": ["exercise_contraindicated_pain_regions"],
            }
        )

    mapping_report = {
        "status": "DRAFT",
        "production_eligible": False,
        "policy": {
            "raw_source_only_for_blank_fill": True,
            "non_empty_normalized_values_overwritten": False,
            "korean_labels_to_machine_codes": "UNMAPPED_VALUES_REMAIN_EMPTY",
            "safety_relevant_body_area_codes": (
                "RAW_DIRECT_VALUE_ONLY; PRIMARY_AND_SECONDARY_NEVER_COPIED"
            ),
            "pain_contraindication_fields": "NOT_COPIED; SAFETY_POLICY_DATA_NOT_DUPLICATED",
        },
        "source": {
            "path": raw_path,
            "sha256": _sha256(raw_source_path) if raw_source_path else None,
        },
        "review_source": {
            "path": str(review_source_path) if review_source_path else "",
            "sha256": _sha256(review_source_path) if review_source_path else None,
        },
        "required_fields": list(REQUIRED_CATALOG_FIELDS),
        "field_mapping": RAW_FIELD_SOURCES,
        "review_field_mapping": REVIEW_FIELD_SOURCES,
        "records": mapped_records,
    }
    gap_report = {
        "status": "DRAFT",
        "production_eligible": False,
        "record_count": len(records),
        "source": mapping_report["source"],
        "required_fields": list(REQUIRED_CATALOG_FIELDS),
        "fields": field_counts,
    }
    return mapping_report, gap_report


def run(
    catalog_path: Path,
    additions_path: Path,
    output_path: Path,
    report_dir: Path,
    gymvisual_source_path: Path | None = DEFAULT_GYMVISUAL_SOURCE,
    source_mapping_output: Path | None = DEFAULT_SOURCE_MAPPING_OUTPUT,
    review_csv_path: Path | None = None,
    csv_output_path: Path | None = None,
) -> dict[str, Any]:
    if catalog_path.resolve() == output_path.resolve():
        raise MergeError("output must not overwrite the existing exercises.jsonl")
    catalog = _read_jsonl(catalog_path)
    additions = _read_json(additions_path)
    source_rows = (
        _read_json(gymvisual_source_path)
        if gymvisual_source_path and gymvisual_source_path.is_file()
        else None
    )
    review_identity_fields = (
        _read_review_identity_fields(review_csv_path) if review_csv_path is not None else None
    )
    result = merge_records(catalog, additions, source_rows, review_identity_fields)
    _write_json(output_path, result["records"], preserve_record_order=True)
    csv_output = csv_output_path or output_path.with_suffix(".csv")
    _write_review_csv(csv_output, result["records"], result["report"]["schema_fields"])
    source_mapping, source_gaps = _source_mapping_report(
        result["records"],
        source_rows,
        gymvisual_source_path,
        review_identity_fields,
        review_csv_path,
        set(result["report"]["review_identity_source_identities"]),
    )
    if source_mapping_output is not None:
        _write_json(source_mapping_output, source_mapping)

    report = result["report"]
    report["inputs"] = {
        "catalog": {
            "path": str(catalog_path),
            "sha256": _sha256(catalog_path),
            "records": len(catalog),
        },
        "additions": {
            "path": str(additions_path),
            "sha256": _sha256(additions_path),
            "records": len(additions),
        },
        "gymvisual_source": (
            {"path": str(gymvisual_source_path), "sha256": _sha256(gymvisual_source_path)}
            if gymvisual_source_path and gymvisual_source_path.is_file()
            else None
        ),
        "review_csv": (
            {"path": str(review_csv_path), "sha256": _sha256(review_csv_path)}
            if review_csv_path is not None
            else None
        ),
    }
    report["output"] = {
        "path": str(output_path),
        "sha256": _sha256(output_path),
        "records": len(result["records"]),
    }
    report["csv_output"] = {
        "path": str(csv_output),
        "sha256": _sha256(csv_output),
        "records": len(result["records"]),
        "encoding": "UTF-8-BOM",
        "array_separator": "|",
    }
    report["source_mapping_output"] = (
        {
            "path": str(source_mapping_output),
            "sha256": _sha256(source_mapping_output),
            "records": len(source_mapping["records"]),
        }
        if source_mapping_output is not None
        else None
    )
    report["source_gap_report"] = source_gaps["fields"]
    _write_json(report_dir / "exercise_catalog_merge_report.json", report)
    _write_json(report_dir / "exercise_catalog_duplicate_review.json", result["duplicate_review"])
    _write_json(report_dir / "exercise_catalog_unmapped_fields.json", result["unmapped"])
    _write_json(report_dir / "exercise_catalog_source_gap_report.json", source_gaps)
    _write_json(report_dir / "exercise_catalog_source_mapping.json", source_mapping)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--additions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument(
        "--gymvisual-source",
        type=Path,
        default=DEFAULT_GYMVISUAL_SOURCE,
        help="raw Gymvisual JSON used only for provenance verification",
    )
    parser.add_argument(
        "--source-mapping-output",
        type=Path,
        default=DEFAULT_SOURCE_MAPPING_OUTPUT,
        help="normalized source mapping report output",
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=DEFAULT_REVIEW_CSV,
        help="review CSV used for exact new-row stable_code/name_ko mapping",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=None,
        help="full merged catalog review CSV; defaults to output JSON with .csv suffix",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = run(
            catalog_path=args.catalog,
            additions_path=args.additions,
            output_path=args.output,
            report_dir=args.report_dir,
            gymvisual_source_path=args.gymvisual_source,
            source_mapping_output=args.source_mapping_output,
            review_csv_path=args.review_csv,
            csv_output_path=args.csv_output,
        )
    except MergeError as exc:
        print(f"merge failed: {exc}")
        return 1
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
