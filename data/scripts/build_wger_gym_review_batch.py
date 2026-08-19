"""Build a reproducible DRAFT gym-core review batch from a verified wger profile."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from manifest_values import require_int
from profile_wger_exercises import canonical_text, verify_profile
from wger_exercise_pipeline import PipelineError, sha256_bytes

REVIEW_BATCH_VERSION = "0.2.0"
DEFAULT_BATCH_SIZE = 60
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "validation" / "review_batches"

TARGET_QUOTAS: tuple[tuple[str, int], ...] = (
    ("LAT_PULLDOWN", 6),
    ("DUMBBELL_ROW", 5),
    ("SEATED_OR_CABLE_ROW", 5),
    ("CHEST_OR_BENCH_PRESS", 8),
    ("SHOULDER_PRESS", 6),
    ("LEG_PRESS", 4),
    ("LEG_EXTENSION", 2),
    ("LEG_CURL", 3),
    ("SQUAT", 8),
    ("DEADLIFT", 6),
)

USER_REQUESTED_SOURCE_NAME_SEEDS = (
    "Neutral Grip Lat Pulldown",
    "Incline Dumbbell Row",
    "Seated Cable Row",
)

SELECTION_METHOD_CODES = (
    "DRAFT_GYM_CANDIDATES_WITH_ENGLISH_NAME_ONLY",
    "UNIQUE_PRIMARY_SOURCE_NAME_REPRESENTATIVE",
    "USER_REQUESTED_SOURCE_NAME_SEEDS_FIRST",
    "TARGET_FAMILY_QUOTA_ROUND_ROBIN",
    "CATEGORY_EQUIPMENT_COVERAGE_FILL",
    "SOURCE_METADATA_COMPLETENESS_TIE_BREAK",
)

INTERPRETATION_GUARDS = (
    "REVIEW_BATCH_IS_NOT_FINAL_CATALOG",
    "SOURCE_NAME_MATCH_IS_NOT_NORMALIZED_TAXONOMY",
    "SELECTION_IS_NOT_BEGINNER_SUITABILITY_APPROVAL",
    "SELECTION_IS_NOT_DOMAIN_SAFETY_APPROVAL",
    "SOURCE_MUSCLE_METADATA_IS_NOT_CONTRAINDICATION_DATA",
    "SOURCE_DESCRIPTION_IS_NOT_APPROVED_EXECUTION_GUIDANCE",
    "MEDIA_REFERENCE_IS_NOT_REDISTRIBUTION_PERMISSION",
    "ALTERNATIVE_RELATION_REQUIRES_SEPARATE_REVIEW",
)

REQUIRED_REVIEW_CODES = {
    "BEGINNER_SUITABILITY_REVIEW_REQUIRED",
    "DOMAIN_SAFETY_REVIEW_REQUIRED",
    "EXERCISE_TAXONOMY_MAPPING_REQUIRED",
    "KOREAN_LOCALIZATION_REVIEW_REQUIRED",
    "SOURCE_LICENSE_REVIEW_REQUIRED",
}

PENDING_REVIEW_FIELDS = {
    "review_normalized_exercise_id": "",
    "review_display_name_ko": "",
    "review_taxonomy_code": "",
    "review_beginner_suitability": "PENDING",
    "review_execution_guidance_status": "PENDING",
    "review_license_status": "PENDING",
    "review_domain_safety_status": "PENDING",
    "review_decision": "PENDING",
    "reviewer_notes": "",
}

REVIEWER_ROLE_CODES = (
    "DATA_OWNER",
    "BACKEND_REVIEWER",
    "PM_REVIEWER",
    "DOMAIN_REVIEWER",
)

REVIEW_EVIDENCE_FIELDS = [
    "evidence_position",
    "source_exercise_id",
    "source_exercise_uuid",
    "primary_source_name_en",
    "target_type_code",
    "target_reference",
    "reviewer_role_code",
    "review_status_code",
    "reviewer_reference",
    "evidence_reference",
    "reviewed_at",
]


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PipelineError(f"{field_name} must be an object")
    return value


def list_of_strings(candidate: dict[str, object], field: str) -> list[str]:
    value = candidate.get(field, [])
    if not isinstance(value, list):
        raise PipelineError(f"candidate field {field} must be a list")
    return sorted(
        {canonical_text(item) for item in value if canonical_text(item)}, key=str.casefold
    )


def named_items(candidate: dict[str, object], field: str) -> list[dict[str, object]]:
    value = candidate.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PipelineError(f"candidate field {field} must be a list of objects")
    return value


def primary_name(candidate: dict[str, object]) -> str:
    names = list_of_strings(candidate, "source_names_en")
    return names[0] if names else ""


def source_equipment_names(candidate: dict[str, object]) -> list[str]:
    return sorted(
        {
            canonical_text(item.get("name"))
            for item in named_items(candidate, "source_equipment")
            if canonical_text(item.get("name"))
        },
        key=str.casefold,
    )


def source_muscle_names(candidate: dict[str, object], field: str) -> list[str]:
    return sorted(
        {
            canonical_text(item.get("name"))
            for item in named_items(candidate, field)
            if canonical_text(item.get("name"))
        },
        key=str.casefold,
    )


def load_candidates(profile_dir: Path) -> list[dict[str, object]]:
    profile_dir = profile_dir.resolve()
    verify_profile(profile_dir)
    inventory_path = profile_dir / "gym_candidate_inventory.jsonl"
    candidates: list[dict[str, object]] = []
    for line_number, line in enumerate(
        inventory_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        candidate = json.loads(line)
        if not isinstance(candidate, dict):
            raise PipelineError(f"gym inventory line {line_number} is not an object")
        candidates.append(candidate)
    return candidates


def validate_candidate(candidate: dict[str, object]) -> None:
    exercise_id = candidate.get("source_exercise_id")
    exercise_uuid = canonical_text(candidate.get("source_exercise_uuid"))
    if not isinstance(exercise_id, int) or exercise_id < 1 or not exercise_uuid:
        raise PipelineError("gym candidate source identity is invalid")
    if (
        candidate.get("review_status") != "DRAFT"
        or candidate.get("production_eligible") is not False
    ):
        raise PipelineError("gym candidate must remain DRAFT and production-ineligible")
    required = set(list_of_strings(candidate, "required_review_codes"))
    if not REQUIRED_REVIEW_CODES.issubset(required):
        raise PipelineError("gym candidate is missing required human review codes")
    base_license = _mapping(candidate.get("source_base_license"), "source_base_license")
    if not canonical_text(base_license.get("short_name")):
        raise PipelineError("gym candidate base license is missing")


def metadata_rank(candidate: dict[str, object]) -> tuple[Any, ...]:
    """Prefer reviewable source evidence without inferring quality or safety."""

    equipment = source_equipment_names(candidate)
    primary_muscles = source_muscle_names(candidate, "source_primary_muscles")
    aliases = list_of_strings(candidate, "source_aliases_en")
    base_license = _mapping(candidate.get("source_base_license"), "source_base_license")
    return (
        -int(bool(equipment)),
        -int(bool(primary_muscles)),
        -int(bool(canonical_text(base_license.get("license_author")))),
        -int(bool(aliases)),
        primary_name(candidate).casefold(),
        require_int(candidate["source_exercise_id"], "source_exercise_id"),
    )


def representative_candidates(
    candidates: Iterable[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen_ids: set[int] = set()
    for candidate in candidates:
        validate_candidate(candidate)
        name = primary_name(candidate)
        if not name:
            continue
        exercise_id = require_int(candidate["source_exercise_id"], "source_exercise_id")
        if exercise_id in seen_ids:
            raise PipelineError(f"duplicate source_exercise_id: {exercise_id}")
        seen_ids.add(exercise_id)
        grouped[name.casefold()].append(candidate)

    representatives: list[dict[str, object]] = []
    duplicate_groups = 0
    for group in grouped.values():
        if len(group) > 1:
            duplicate_groups += 1
        representative = dict(sorted(group, key=metadata_rank)[0])
        representative["duplicate_primary_name_count"] = len(group)
        representatives.append(representative)
    representatives.sort(key=metadata_rank)
    return representatives, duplicate_groups


def equipment_signature(candidate: dict[str, object]) -> str:
    equipment = source_equipment_names(candidate)
    return " | ".join(equipment) if equipment else "SOURCE_EQUIPMENT_UNSPECIFIED"


def category_name(candidate: dict[str, object]) -> str:
    category = _mapping(candidate.get("source_category"), "source_category")
    return canonical_text(category.get("name")) or "SOURCE_CATEGORY_UNSPECIFIED"


def round_robin(
    candidates: Iterable[dict[str, object]],
    group_key: Callable[[dict[str, object]], object],
) -> Iterable[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        groups[str(group_key(candidate))].append(candidate)
    for group in groups.values():
        group.sort(key=metadata_rank)
    keys = sorted(groups, key=str.casefold)
    while True:
        progressed = False
        for key in keys:
            if not groups[key]:
                continue
            progressed = True
            yield groups[key].pop(0)
        if not progressed:
            return


def select_review_batch(
    candidates: Iterable[dict[str, object]], size: int = DEFAULT_BATCH_SIZE
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if size < 1:
        raise PipelineError("review batch size must be at least 1")
    candidate_list = list(candidates)
    representatives, duplicate_groups = representative_candidates(candidate_list)
    if size > len(representatives):
        raise PipelineError(
            f"requested {size} rows but only {len(representatives)} eligible names are available"
        )

    selected: list[dict[str, object]] = []
    selected_ids: set[int] = set()
    reasons: dict[int, set[str]] = defaultdict(set)

    def add(candidate: dict[str, object], reason: str) -> bool:
        exercise_id = require_int(candidate["source_exercise_id"], "source_exercise_id")
        if exercise_id in selected_ids or len(selected) >= size:
            if exercise_id in selected_ids:
                reasons[exercise_id].add(reason)
            return False
        selected.append(candidate)
        selected_ids.add(exercise_id)
        reasons[exercise_id].add(reason)
        return True

    by_name = {primary_name(candidate).casefold(): candidate for candidate in representatives}
    for requested_name in USER_REQUESTED_SOURCE_NAME_SEEDS:
        candidate = by_name.get(requested_name.casefold())
        if candidate is not None:
            add(candidate, "USER_REQUESTED_SOURCE_NAME_SEED")

    target_counts: Counter[str] = Counter()
    for candidate in selected:
        target_counts.update(list_of_strings(candidate, "target_name_match_codes"))

    for target_code, quota in TARGET_QUOTAS:
        pool = [
            candidate
            for candidate in representatives
            if target_code in list_of_strings(candidate, "target_name_match_codes")
            and require_int(candidate["source_exercise_id"], "source_exercise_id")
            not in selected_ids
        ]
        for candidate in round_robin(pool, equipment_signature):
            if target_counts[target_code] >= quota or len(selected) >= size:
                break
            if add(candidate, "TARGET_FAMILY_QUOTA"):
                target_counts.update(list_of_strings(candidate, "target_name_match_codes"))

    remaining = [
        candidate
        for candidate in representatives
        if require_int(candidate["source_exercise_id"], "source_exercise_id") not in selected_ids
    ]
    for candidate in round_robin(
        remaining, lambda item: f"{category_name(item)}\x1f{equipment_signature(item)}"
    ):
        if len(selected) >= size:
            break
        add(candidate, "CATEGORY_EQUIPMENT_COVERAGE_FILL")

    if len(selected) != size:
        raise PipelineError("gym review batch selection stopped before requested size")

    rows: list[dict[str, object]] = []
    for position, candidate in enumerate(selected, start=1):
        row = dict(candidate)
        exercise_id = require_int(candidate["source_exercise_id"], "source_exercise_id")
        row.update(
            {
                "batch_position": position,
                "primary_source_name_en": primary_name(candidate),
                "source_equipment_names": source_equipment_names(candidate),
                "source_primary_muscle_names": source_muscle_names(
                    candidate, "source_primary_muscles"
                ),
                "source_secondary_muscle_names": source_muscle_names(
                    candidate, "source_secondary_muscles"
                ),
                "selection_reason_codes": sorted(reasons[exercise_id]),
                "batch_status": "DRAFT_REVIEW_QUEUE",
                **PENDING_REVIEW_FIELDS,
                "review_status": "DRAFT",
                "production_eligible": False,
            }
        )
        rows.append(row)

    selected_target_counts: Counter[str] = Counter()
    selected_category_counts: Counter[str] = Counter()
    selected_equipment_counts: Counter[str] = Counter()
    selection_reason_counts: Counter[str] = Counter()
    for row in rows:
        selected_target_counts.update(list_of_strings(row, "target_name_match_codes"))
        selected_category_counts[category_name(row)] += 1
        selected_equipment_counts.update(source_equipment_names(row))
        selection_reason_counts.update(list_of_strings(row, "selection_reason_codes"))

    summary: dict[str, object] = {
        "input_gym_candidates": len(candidate_list),
        "eligible_candidates_with_english_primary_name": sum(
            bool(primary_name(candidate)) for candidate in candidate_list
        ),
        "excluded_missing_english_primary_name": sum(
            not bool(primary_name(candidate)) for candidate in candidate_list
        ),
        "eligible_unique_primary_names": len(representatives),
        "duplicate_primary_name_groups": duplicate_groups,
        "requested_batch_size": size,
        "selected_batch_size": len(rows),
        "target_quotas": dict(TARGET_QUOTAS),
        "selected_target_counts": dict(sorted(selected_target_counts.items())),
        "selected_category_counts": dict(sorted(selected_category_counts.items())),
        "selected_equipment_counts": dict(sorted(selected_equipment_counts.items())),
        "selection_reason_counts": dict(sorted(selection_reason_counts.items())),
    }
    return rows, summary


def joined(row: dict[str, object], field: str) -> str:
    return " | ".join(list_of_strings(row, field))


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


CSV_FIELDS = [
    "batch_position",
    "source_exercise_id",
    "source_exercise_uuid",
    "primary_source_name_en",
    "source_aliases_en",
    "source_category_name",
    "source_equipment_names",
    "source_primary_muscle_names",
    "source_secondary_muscle_names",
    "target_name_match_codes",
    "source_base_license",
    "source_license_author",
    "source_image_reference_count",
    "source_video_reference_count",
    "selection_reason_codes",
    "required_review_codes",
    "review_normalized_exercise_id",
    "review_display_name_ko",
    "review_taxonomy_code",
    "review_beginner_suitability",
    "review_execution_guidance_status",
    "review_license_status",
    "review_domain_safety_status",
    "review_decision",
    "reviewer_notes",
    "batch_status",
    "review_status",
    "production_eligible",
]


def csv_row(row: dict[str, object]) -> dict[str, object]:
    category = _mapping(row.get("source_category"), "source_category")
    base_license = _mapping(row.get("source_base_license"), "source_base_license")
    return {
        "batch_position": row["batch_position"],
        "source_exercise_id": row["source_exercise_id"],
        "source_exercise_uuid": row["source_exercise_uuid"],
        "primary_source_name_en": row["primary_source_name_en"],
        "source_aliases_en": joined(row, "source_aliases_en"),
        "source_category_name": category.get("name", ""),
        "source_equipment_names": joined(row, "source_equipment_names"),
        "source_primary_muscle_names": joined(row, "source_primary_muscle_names"),
        "source_secondary_muscle_names": joined(row, "source_secondary_muscle_names"),
        "target_name_match_codes": joined(row, "target_name_match_codes"),
        "source_base_license": base_license.get("short_name", ""),
        "source_license_author": base_license.get("license_author", ""),
        "source_image_reference_count": row["source_image_reference_count"],
        "source_video_reference_count": row["source_video_reference_count"],
        "selection_reason_codes": joined(row, "selection_reason_codes"),
        "required_review_codes": joined(row, "required_review_codes"),
        **{field: row[field] for field in PENDING_REVIEW_FIELDS},
        "batch_status": row["batch_status"],
        "review_status": row["review_status"],
        "production_eligible": "false",
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_row(row))


def build_review_evidence_rows(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    evidence_rows: list[dict[str, object]] = []
    for row in rows:
        for role_code in REVIEWER_ROLE_CODES:
            evidence_rows.append(
                {
                    "evidence_position": len(evidence_rows) + 1,
                    "source_exercise_id": row["source_exercise_id"],
                    "source_exercise_uuid": row["source_exercise_uuid"],
                    "primary_source_name_en": row["primary_source_name_en"],
                    "target_type_code": "EXERCISE",
                    "target_reference": f"wger:{row['source_exercise_uuid']}",
                    "reviewer_role_code": role_code,
                    "review_status_code": "DRAFT",
                    "reviewer_reference": "",
                    "evidence_reference": "",
                    "reviewed_at": "",
                }
            )
    return evidence_rows


def write_review_evidence_jsonl(path: Path, evidence_rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in evidence_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_review_evidence_csv(path: Path, evidence_rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(evidence_rows)


def file_entry(path: Path, root: Path, records: int) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "records": records,
    }


def create_review_batch(
    profile_dir: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    size: int = DEFAULT_BATCH_SIZE,
) -> Path:
    profile_dir = profile_dir.resolve()
    candidates = load_candidates(profile_dir)
    rows, summary = select_review_batch(candidates, size=size)
    evidence_rows = build_review_evidence_rows(rows)
    summary["review_evidence_template_records"] = len(evidence_rows)
    profile_manifest_path = profile_dir / "profile_manifest.json"

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"{profile_dir.name}-gym-core-review-v{REVIEW_BATCH_VERSION}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists():
        raise PipelineError(f"gym review batch already exists: {directory_name}")
    if partial_dir.exists():
        raise PipelineError(f"partial gym review batch already exists: {partial_dir.name}")

    partial_dir.mkdir()
    try:
        jsonl_path = partial_dir / "gym_core_review_batch.jsonl"
        csv_path = partial_dir / "gym_core_review_batch.csv"
        evidence_jsonl_path = partial_dir / "catalog_review_records_template.jsonl"
        evidence_csv_path = partial_dir / "catalog_review_records_template.csv"
        write_jsonl(jsonl_path, rows)
        write_csv(csv_path, rows)
        write_review_evidence_jsonl(evidence_jsonl_path, evidence_rows)
        write_review_evidence_csv(evidence_csv_path, evidence_rows)
        manifest = {
            "schema_version": "1.0",
            "review_batch_version": REVIEW_BATCH_VERSION,
            "source": {
                "profile_directory": profile_dir.name,
                "profile_manifest_sha256": sha256_bytes(profile_manifest_path.read_bytes()),
            },
            "selection": {
                "status": "DRAFT_REVIEW_QUEUE",
                "method_codes": list(SELECTION_METHOD_CODES),
                "target_quotas": dict(TARGET_QUOTAS),
                "user_requested_source_name_seeds": list(USER_REQUESTED_SOURCE_NAME_SEEDS),
                "interpretation_guards": list(INTERPRETATION_GUARDS),
            },
            "review": {"status": "DRAFT", "production_eligible": False},
            "summary": summary,
            "files": [
                file_entry(jsonl_path, partial_dir, len(rows)),
                file_entry(csv_path, partial_dir, len(rows)),
                file_entry(evidence_jsonl_path, partial_dir, len(evidence_rows)),
                file_entry(evidence_csv_path, partial_dir, len(evidence_rows)),
            ],
        }
        write_json(partial_dir / "review_manifest.json", manifest)
        verify_review_batch(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_review_batch(batch_dir: Path) -> dict[str, object]:
    batch_dir = batch_dir.resolve()
    manifest_path = batch_dir / "review_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError("review_manifest.json is missing") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("review_manifest.json is not valid UTF-8 JSON") from exc

    if manifest.get("schema_version") != "1.0":
        raise PipelineError("unsupported gym review manifest schema")
    if manifest.get("review_batch_version") != REVIEW_BATCH_VERSION:
        raise PipelineError("gym review batch version does not match verifier")
    if manifest.get("review") != {"status": "DRAFT", "production_eligible": False}:
        raise PipelineError("gym review batch must remain DRAFT and production-ineligible")
    selection = _mapping(manifest.get("selection"), "manifest.selection")
    if selection.get("status") != "DRAFT_REVIEW_QUEUE":
        raise PipelineError("gym review batch selection status is invalid")
    if selection.get("method_codes") != list(SELECTION_METHOD_CODES):
        raise PipelineError("gym review batch selection method codes are invalid")
    guards = selection.get("interpretation_guards")
    if not isinstance(guards, list) or "SELECTION_IS_NOT_DOMAIN_SAFETY_APPROVAL" not in guards:
        raise PipelineError("gym review batch is missing its safety guard")
    source = _mapping(manifest.get("source"), "manifest.source")
    if not canonical_text(source.get("profile_directory")) or not re.fullmatch(
        r"[0-9a-f]{64}", canonical_text(source.get("profile_manifest_sha256"))
    ):
        raise PipelineError("gym review batch source profile reference is invalid")

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 4:
        raise PipelineError("gym review manifest must list mapping and evidence files")
    jsonl_rows: list[dict[str, object]] | None = None
    csv_rows: list[dict[str, str]] | None = None
    evidence_jsonl_rows: list[dict[str, object]] | None = None
    evidence_csv_rows: list[dict[str, str]] | None = None
    for entry_value in files:
        entry = _mapping(entry_value, "manifest file entry")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("gym review manifest contains an unsafe file path")
        path = batch_dir / relative
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"gym review file is missing: {relative.as_posix()}") from exc
        if sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"gym review batch hash mismatch: {relative.as_posix()}")
        if len(raw) != require_int(entry.get("bytes", -1), "manifest bytes"):
            raise PipelineError(f"gym review batch size mismatch: {relative.as_posix()}")
        expected_records = require_int(entry.get("records", -1), "manifest records")
        if relative.name == "gym_core_review_batch.jsonl":
            jsonl_rows = [
                json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
            ]
            if len(jsonl_rows) != expected_records:
                raise PipelineError("gym review JSONL record count mismatch")
        elif relative.name == "gym_core_review_batch.csv":
            csv_rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
            if len(csv_rows) != expected_records:
                raise PipelineError("gym review CSV record count mismatch")
        elif relative.name == "catalog_review_records_template.jsonl":
            evidence_jsonl_rows = [
                json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
            ]
            if len(evidence_jsonl_rows) != expected_records:
                raise PipelineError("review evidence JSONL record count mismatch")
        elif relative.name == "catalog_review_records_template.csv":
            evidence_csv_rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
            if len(evidence_csv_rows) != expected_records:
                raise PipelineError("review evidence CSV record count mismatch")

    if jsonl_rows is None or csv_rows is None or len(jsonl_rows) != len(csv_rows):
        raise PipelineError("gym review JSONL and CSV content is incomplete")
    if (
        evidence_jsonl_rows is None
        or evidence_csv_rows is None
        or len(evidence_jsonl_rows) != len(evidence_csv_rows)
        or len(evidence_jsonl_rows) != len(jsonl_rows) * len(REVIEWER_ROLE_CODES)
    ):
        raise PipelineError("review evidence template content is incomplete")
    positions: list[int] = []
    source_ids: set[int] = set()
    source_names: set[str] = set()
    for jsonl_row, csv_record in zip(jsonl_rows, csv_rows, strict=True):
        if jsonl_row.get("batch_status") != "DRAFT_REVIEW_QUEUE":
            raise PipelineError("gym review row batch status is invalid")
        if (
            jsonl_row.get("review_status") != "DRAFT"
            or jsonl_row.get("production_eligible") is not False
        ):
            raise PipelineError("gym review row was promoted without approval")
        required = set(list_of_strings(jsonl_row, "required_review_codes"))
        if not REQUIRED_REVIEW_CODES.issubset(required):
            raise PipelineError("gym review row is missing required reviews")
        for field, pending_value in PENDING_REVIEW_FIELDS.items():
            if jsonl_row.get(field) != pending_value:
                raise PipelineError(f"generated gym review field must remain pending: {field}")
            if csv_record.get(field, "") != pending_value:
                raise PipelineError(f"generated CSV review field must remain pending: {field}")
        position = require_int(jsonl_row.get("batch_position", 0), "batch_position")
        exercise_id = require_int(jsonl_row.get("source_exercise_id", 0), "source_exercise_id")
        name = canonical_text(jsonl_row.get("primary_source_name_en")).casefold()
        if exercise_id in source_ids or not name or name in source_names:
            raise PipelineError("gym review source identities and names must be unique")
        source_ids.add(exercise_id)
        source_names.add(name)
        positions.append(position)
        if (
            csv_record.get("batch_position") != str(position)
            or csv_record.get("source_exercise_id") != str(exercise_id)
            or csv_record.get("primary_source_name_en") != jsonl_row.get("primary_source_name_en")
        ):
            raise PipelineError("gym review JSONL and CSV identity mismatch")
        if (
            csv_record.get("batch_status") != "DRAFT_REVIEW_QUEUE"
            or csv_record.get("review_status") != "DRAFT"
            or csv_record.get("production_eligible") != "false"
        ):
            raise PipelineError("gym review CSV contains an invalid state")

    if positions != list(range(1, len(jsonl_rows) + 1)):
        raise PipelineError("gym review batch positions are not contiguous")
    expected_evidence_position = 1
    evidence_keys: set[tuple[int, str]] = set()
    for jsonl_record, csv_record in zip(evidence_jsonl_rows, evidence_csv_rows, strict=True):
        position = require_int(jsonl_record.get("evidence_position", 0), "evidence_position")
        exercise_id = require_int(jsonl_record.get("source_exercise_id", 0), "source_exercise_id")
        role_code = canonical_text(jsonl_record.get("reviewer_role_code"))
        if position != expected_evidence_position:
            raise PipelineError("review evidence positions are not contiguous")
        expected_evidence_position += 1
        if exercise_id not in source_ids or role_code not in REVIEWER_ROLE_CODES:
            raise PipelineError("review evidence source or role is invalid")
        key = (exercise_id, role_code)
        if key in evidence_keys:
            raise PipelineError("review evidence source and role must be unique")
        evidence_keys.add(key)
        if (
            jsonl_record.get("target_type_code") != "EXERCISE"
            or jsonl_record.get("review_status_code") != "DRAFT"
            or jsonl_record.get("reviewer_reference") != ""
            or jsonl_record.get("evidence_reference") != ""
            or jsonl_record.get("reviewed_at") != ""
        ):
            raise PipelineError("generated review evidence must remain DRAFT and blank")
        for field in REVIEW_EVIDENCE_FIELDS:
            if csv_record.get(field, "") != str(jsonl_record.get(field, "")):
                raise PipelineError("review evidence JSONL and CSV identity mismatch")
    summary = _mapping(manifest.get("summary"), "manifest.summary")
    if summary.get("selected_batch_size") != len(jsonl_rows) or summary.get(
        "requested_batch_size"
    ) != len(jsonl_rows):
        raise PipelineError("gym review manifest summary does not match batch size")
    return {"batch": batch_dir.name, "records": len(jsonl_rows), "status": "valid"}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a DRAFT gym-core review batch")
    build.add_argument("profile", type=Path)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--size", type=int, default=DEFAULT_BATCH_SIZE)
    verify = subparsers.add_parser("verify", help="verify a generated gym review batch")
    verify.add_argument("batch", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            batch_dir = create_review_batch(args.profile, args.output_root, args.size)
            result: dict[str, object] = {"status": "built", "batch": str(batch_dir)}
        else:
            result = verify_review_batch(args.batch)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
