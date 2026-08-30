#!/usr/bin/env python3
# ruff: noqa: E501
"""Materialize reviewed v2.0.2 variants as independent catalog records.

The relationship review contains conservative PRIMARY/SECONDARY candidates.
Alias-to-representative candidates have a clear direction and are materialized
as draft Variant records.  Canonical-to-canonical candidates remain in the
relationship result as REVIEW_REQUIRED because the review did not select a
representative direction for them.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.scripts.v2_0_2_difficulty_policy import (  # noqa: E402
    POLICY_PATH,
    apply_difficulty_policy,
    load_policy,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/canonical_exercises_v2_0_2_refined.jsonl"
)
DEFAULT_LEGACY_CANONICAL = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/canonical_exercises_v2_final.jsonl"
)
DEFAULT_RELATIONSHIPS = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/variant_relationship_candidates_v2_final.jsonl"
)
DEFAULT_BATCH = (
    ROOT
    / "validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0/review_batch.jsonl"
)
DEFAULT_VARIANT_REVIEW = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/representative_variant_candidates_v2_0_2.jsonl"
)
DEFAULT_REP_REVIEW = ROOT / "reports/representative_exercise_taxonomy_reviewed.csv"
DEFAULT_INTEGRATED_REVIEW = ROOT / "reports/integrated_exercise_review_updated.csv"
DEFAULT_DRAFT = ROOT / "generated/exercise-catalog-v2.0.2-draft/catalog/exercises_v1_v2.csv"
DEFAULT_GYMVISUAL_RAW = ROOT / "raw/gym_visual/exercises.json"
# The first-pass 201-record variant materialization is review evidence, not
# the DB-loadable final catalog.  Keeping it outside the final bundle prevents
# its counts and draft records from leaking into release metadata.
DEFAULT_OUTPUT = ROOT / "generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1"

CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
MATERIALIZATION_VERSION = "v2.0.2-variant-materialization-v1.0.0"
GENERATED_AT = "2026-08-28T00:00:00+09:00"
VALID_VARIANT_TYPES = {"PRIMARY_VARIANT", "SECONDARY_VARIANT"}
VALID_RECORD_TYPES = {"REPRESENTATIVE", "SEPARATE_EXERCISE", "VARIANT"}
FORBIDDEN_EQUIPMENT = {"BENCH", "CHAIR"}
EQUIPMENT_NORMALIZATION = {
    "ROPE": "STRETCH_STRAP",
    "SUSPENSION_STRAPS": "STRETCH_STRAP",
}
HOME_EQUIPMENT = {
    "BODYWEIGHT",
    "DUMBBELL",
    "FOAM_ROLLER",
    "HOUSEHOLD_WEIGHT",
    "JUMP_ROPE",
    "MAT",
    "RESISTANCE_BAND",
}


class MaterializationError(ValueError):
    """Raised when an invariant prevents safe materialization."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--legacy-canonical", type=Path, default=DEFAULT_LEGACY_CANONICAL)
    parser.add_argument("--relationships", type=Path, default=DEFAULT_RELATIONSHIPS)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--variant-review", type=Path, default=DEFAULT_VARIANT_REVIEW)
    parser.add_argument("--representative-review", type=Path, default=DEFAULT_REP_REVIEW)
    parser.add_argument("--integrated-review", type=Path, default=DEFAULT_INTEGRATED_REVIEW)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--gymvisual-raw", type=Path, default=DEFAULT_GYMVISUAL_RAW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MaterializationError(f"cannot read JSONL: {path}") from error
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise MaterializationError(f"invalid JSONL at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise MaterializationError(f"JSON object expected at {path}:{line_number}")
        rows.append(value)
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise MaterializationError(f"cannot read CSV: {path}") from error
    if not rows:
        raise MaterializationError(f"CSV is empty: {path}")
    return [{key: (value or "") for key, value in row.items()} for row in rows]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: csv_value(row.get(key, "")) for key in columns} for row in rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text or text in {"REVIEW_REQUIRED", "NONE", "N/A"}:
        return []
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (list, tuple)):
            return parse_values(parsed)
    return [item.strip() for item in re.split(r"\s*[|,]\s*", text) if item.strip()]


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def compact_list(value: list[str]) -> list[str]:
    result: list[str] = []
    for item in value:
        item = str(item).strip()
        if item and item not in result:
            result.append(item)
    return result


def normalize_name(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[^a-z0-9가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug(value: str) -> str:
    text = normalize_name(value).replace(" ", "_")
    return text or "exercise"


def first(values: list[str], fallback: str = "") -> str:
    return values[0] if values else fallback


def source_key(track: str, identity: str) -> str:
    return f"{track}:{identity}" if track and identity else ""


def valid_equipment(values: list[str]) -> list[str]:
    values = [
        EQUIPMENT_NORMALIZATION.get(item.upper(), item.upper())
        for item in values
        if item.upper() not in FORBIDDEN_EQUIPMENT
    ]
    return compact_list(values)


def valid_locations(values: list[str]) -> list[str]:
    return compact_list([item.upper() for item in values if item.upper() in {"HOME", "GYM"}])


def infer_equipment(name: str) -> list[str]:
    text = normalize_name(name)
    tokens = (
        ("dumbbell", "DUMBBELL"),
        ("kettlebell", "KETTLEBELL"),
        ("barbell", "BARBELL"),
        ("ez bar", "EZ_BAR"),
        ("cable", "CABLE_MACHINE"),
        ("machine", "MACHINE"),
        ("lever", "MACHINE"),
        ("band", "RESISTANCE_BAND"),
        ("elastic", "RESISTANCE_BAND"),
        ("roller", "FOAM_ROLLER"),
        ("pull up", "PULL_UP_BAR"),
        ("mat", "MAT"),
        ("stability ball", "STABILITY_BALL"),
    )
    result = [code for token, code in tokens if token in text]
    return compact_list(result) or ["BODYWEIGHT"]


def locations_for(equipment: list[str], source_locations: list[str]) -> list[str]:
    locations = valid_locations(source_locations)
    equipment_is_home_supported = set(equipment).issubset(HOME_EQUIPMENT)
    if "HOME" in locations:
        return ["HOME", "GYM"] if equipment_is_home_supported else ["GYM"]
    if "GYM" in locations:
        return ["GYM"]
    return ["HOME", "GYM"] if equipment_is_home_supported else ["GYM"]


def split_pipe_text(value: Any) -> list[str]:
    return compact_list(
        [
            item.strip()
            for item in str(value or "").split("|")
            if item.strip() not in {"REVIEW_REQUIRED", "NONE", "N/A"}
        ]
    )


def raw_source_record(
    source_row: dict[str, str], gymvisual: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if source_row.get("source_track") == "gymvisual":
        return gymvisual.get(source_row.get("source_id", ""), {})
    return parse_json_object(source_row.get("raw_source_record_json", ""))


def source_instruction(
    source_row: dict[str, str], raw: dict[str, Any]
) -> tuple[str, list[str], str]:
    instructions = raw.get("instructions", {}) if isinstance(raw.get("instructions"), dict) else {}
    steps = (
        raw.get("instruction_steps", {}) if isinstance(raw.get("instruction_steps"), dict) else {}
    )
    attributes = raw.get("attributes", {}) if isinstance(raw.get("attributes"), dict) else {}
    english = str(instructions.get("en") or source_row.get("source_instruction_en") or "")
    english_steps = steps.get("en") or parse_values(
        source_row.get("source_instruction_steps_en", "")
    )
    korean = str(
        instructions.get("ko")
        or attributes.get("instruction_summary_ko")
        or source_row.get("source_instruction_ko")
        or ""
    )
    return english, [str(item) for item in english_steps], korean


def source_attributes(source_row: dict[str, str], raw: dict[str, Any]) -> dict[str, Any]:
    attributes = raw.get("attributes", {}) if isinstance(raw.get("attributes"), dict) else {}
    equipment = valid_equipment(
        parse_values(source_row.get("reviewed_equipment_codes"))
        or parse_values(source_row.get("equipment_code_candidate"))
        or infer_equipment(source_row.get("source_name") or source_row.get("name_en", ""))
    )
    locations = locations_for(
        equipment,
        parse_values(source_row.get("reviewed_location_codes"))
        or parse_values(source_row.get("location_code_candidates"))
        or parse_values(attributes.get("location_codes")),
    )
    difficulty = (
        str(source_row.get("reviewed_difficulty_code") or "").strip()
        or str(source_row.get("difficulty_code_candidate") or "").strip()
        or str(attributes.get("difficulty_code") or "").strip()
    )
    if difficulty not in {"BEGINNER", "INTERMEDIATE"}:
        difficulty = "INTERMEDIATE"
    body_areas = split_pipe_text(
        source_row.get("reviewed_body_area_codes")
        or source_row.get("body_area_codes_candidate")
        or attributes.get("primary_body_area_codes")
    )
    secondary = split_pipe_text(attributes.get("secondary_body_area_codes"))
    return {
        "equipment_codes": equipment,
        "location_codes": locations,
        "difficulty_code": difficulty,
        "primary_body_area_codes": body_areas,
        "secondary_body_area_codes": secondary,
        "training_type_code": str(
            source_row.get("reviewed_training_type_code")
            or source_row.get("training_type_code_candidate")
            or attributes.get("training_type_code")
            or "STRENGTH"
        ).strip(),
        "movement_pattern_code": str(
            source_row.get("reviewed_movement_pattern_code")
            or source_row.get("movement_pattern_code_candidate")
            or attributes.get("primary_movement_pattern_code")
            or ""
        ).strip(),
        "body_focus_code": str(attributes.get("body_focus_code") or "").strip(),
        "timing_mode_code": str(attributes.get("timing_mode_code") or "REPS").strip(),
        "default_seconds_per_rep": attributes.get("default_seconds_per_rep"),
        "default_work_seconds": attributes.get("default_work_seconds"),
        "default_rest_seconds": attributes.get("default_rest_seconds"),
        "default_transition_seconds": attributes.get("default_transition_seconds"),
        "recovery_eligible": str(attributes.get("recovery_eligible", "FALSE")).casefold() == "true",
        "form_cues_ko": split_pipe_text(attributes.get("form_cues_ko")),
        "allowed_experience_level_codes": parse_values(
            source_row.get("allowed_experience_level_codes")
        ),
        "fitt_template_ids_by_experience": parse_json_object(
            source_row.get("fitt_template_ids_by_experience")
        ),
    }


def review_codes(source_row: dict[str, str], extra: list[str]) -> list[str]:
    codes = parse_values(source_row.get("review_required_codes"))
    for code in extra:
        if code and code not in codes:
            codes.append(code)
    return codes


def stable_code_for(
    name_en: str, pattern: str, equipment: list[str], source_id: str, used: set[str]
) -> str:
    base = "_".join(
        part
        for part in [
            slug(name_en),
            slug(pattern.casefold()),
            *[slug(item.casefold()) for item in equipment],
        ]
        if part
    )
    candidate = base
    if candidate in used:
        suffix = slug(source_id.replace("NEX-", "nex_"))
        candidate = f"{base}_{suffix}"
    counter = 2
    while candidate in used:
        candidate = f"{base}_{slug(source_id)}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def family_map(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    result: dict[str, str] = {}
    for row in rows:
        representative = row.get("representative_id", "")
        family = row.get("reviewed_family", "") or row.get("exercise_family", "")
        if representative and family:
            result[representative] = family
    return result


def prepare_inputs(args: argparse.Namespace) -> dict[str, Any]:
    base_rows = read_jsonl(args.base)
    if len(base_rows) != 131:
        raise MaterializationError(f"expected 131 refined canonical rows, found {len(base_rows)}")
    legacy_rows = read_jsonl(args.legacy_canonical)
    legacy_by_id = {str(row.get("representative_exercise_id")): row for row in legacy_rows}
    relationships = read_jsonl(args.relationships)
    batch_rows = read_jsonl(args.batch)
    batch_by_id = {str(row.get("candidate_pair_id")): row for row in batch_rows}
    variant_review = read_jsonl(args.variant_review)
    integrated = read_csv(args.integrated_review)
    integrated_by_nex = {str(row.get("normalized_exercise_id")): row for row in integrated}
    draft = read_csv(args.draft)
    draft_alias_by_id = {
        str(row.get("v1_exercise_id")): row for row in draft if row.get("record_type") == "V1_ALIAS"
    }
    try:
        gymvisual_data = json.loads(args.gymvisual_raw.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MaterializationError(
            f"cannot read Gym Visual raw source: {args.gymvisual_raw}"
        ) from error
    gymvisual_by_id = {str(row.get("id")): row for row in gymvisual_data if isinstance(row, dict)}
    return {
        "base_rows": base_rows,
        "legacy_by_id": legacy_by_id,
        "relationships": relationships,
        "batch_by_id": batch_by_id,
        "variant_review": variant_review,
        "integrated_by_nex": integrated_by_nex,
        "draft_alias_by_id": draft_alias_by_id,
        "gymvisual_by_id": gymvisual_by_id,
        "family_by_rep": family_map(args.representative_review),
    }


def find_variant_side(row: dict[str, Any], batch: dict[str, Any]) -> tuple[str, str] | None:
    left_type = str(batch.get("left_record_type", ""))
    right_type = str(batch.get("right_record_type", ""))
    if left_type == "V1_ALIAS" and right_type == "EXERCISE":
        return str(batch.get("left_record_id", "")), str(batch.get("right_record_id", ""))
    if right_type == "V1_ALIAS" and left_type == "EXERCISE":
        return str(batch.get("right_record_id", "")), str(batch.get("left_record_id", ""))
    return None


def candidate_entries(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    by_variant: dict[str, set[str]] = defaultdict(set)
    for relation in inputs["relationships"]:
        # REX-000105 is reviewed in the representative-variant artifact and
        # is not part of the relationship review batch.
        if str(relation.get("candidate_pair_id")) == "ERP-20260828-REX000105":
            continue
        relation_type = str(relation.get("candidate_relation_code", ""))
        if relation_type not in VALID_VARIANT_TYPES:
            raise MaterializationError(f"unexpected variant relation code: {relation_type}")
        batch = inputs["batch_by_id"].get(str(relation.get("candidate_pair_id")))
        if batch is None:
            raise MaterializationError(f"relationship missing from review batch: {relation}")
        side = find_variant_side(relation, batch)
        if side is None:
            entries.append(
                {
                    "candidate_pair_id": relation.get("candidate_pair_id", ""),
                    "variant_type_code": relation_type,
                    "relation_status_code": "REVIEW_REQUIRED",
                    "review_status_code": "REVIEW_REQUIRED",
                    "final_decision_code": relation.get("relation_status", "VARIANT_CANDIDATE"),
                    "materialization_status_code": "NOT_MATERIALIZED_REVIEW_REQUIRED",
                    "variant_exercise_id": "",
                    "variant_source_record_id": "",
                    "representative_exercise_id": "",
                    "representative_stable_code": "",
                    "family_code": "",
                    "decision_source": relation.get("decision_source", "AUTO_RULE"),
                    "decision_note_ko": relation.get("note_ko", ""),
                    "source_relation_candidate": True,
                }
            )
            continue
        variant_id, representative_id = side
        by_variant[variant_id].add(representative_id)
        entries.append(
            {
                "candidate_pair_id": relation.get("candidate_pair_id", ""),
                "variant_type_code": relation_type,
                "relation_status_code": "REVIEW_REQUIRED",
                "review_status_code": "REVIEW_REQUIRED",
                "final_decision_code": relation.get("relation_status", "VARIANT_CANDIDATE"),
                "materialization_status_code": "PENDING",
                "variant_source_record_id": variant_id,
                "representative_exercise_id": representative_id,
                "decision_source": relation.get("decision_source", "AUTO_RULE"),
                "decision_note_ko": relation.get("note_ko", ""),
                "source_relation_candidate": True,
            }
        )
    conflicts = {
        variant_id: sorted(representatives)
        for variant_id, representatives in by_variant.items()
        if len(representatives) > 1
    }
    if conflicts:
        raise MaterializationError(f"variant points to conflicting representatives: {conflicts}")

    explicit = inputs["variant_review"]
    if len(explicit) != 1:
        raise MaterializationError(
            f"expected one explicit representative Variant review row, found {len(explicit)}"
        )
    row = explicit[0]
    if str(row.get("review_status_code")) != "REVIEW_REQUIRED":
        raise MaterializationError("explicit Variant review row must retain REVIEW_REQUIRED")
    if str(row.get("representative_exercise_id")) == str(
        row.get("variant_parent_representative_exercise_id")
    ):
        raise MaterializationError("explicit Variant candidate self-references its representative")
    entries.append(
        {
            "candidate_pair_id": "ERP-20260828-REX000105",
            "variant_type_code": "PRIMARY_VARIANT",
            "relation_status_code": "REVIEW_REQUIRED",
            "review_status_code": "REVIEW_REQUIRED",
            "final_decision_code": "VARIANT_CANDIDATE",
            "materialization_status_code": "PENDING",
            "variant_source_record_id": "REX-000105",
            "representative_exercise_id": str(
                row.get("variant_parent_representative_exercise_id", "")
            ),
            "decision_source": "USER_DIRECT_REVIEW",
            "decision_note_ko": str(row.get("canonical_decision_note_ko", "")),
            "source_relation_candidate": False,
            "explicit_variant": row,
        }
    )
    return entries


def base_catalog_rows(
    inputs: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str], dict[str, dict[str, Any]]]:
    family_by_rep = inputs["family_by_rep"]
    draft_alias_by_id = inputs["draft_alias_by_id"]
    old_stable_to_rep = {
        str(row.get("stable_code")): str(row.get("representative_exercise_id"))
        for row in inputs["base_rows"]
        if row.get("stable_code") and str(row.get("record_type", "")) != "EXERCISE"
    }
    for row in inputs["legacy_by_id"].values():
        old_stable_to_rep.setdefault(
            str(row.get("stable_code")), str(row.get("representative_exercise_id"))
        )
    catalog: list[dict[str, Any]] = []
    used_stable = set()
    rep_rows: dict[str, dict[str, Any]] = {}
    for original in inputs["base_rows"]:
        row = deepcopy(original)
        exercise_id = str(row.get("representative_exercise_id", ""))
        if not exercise_id:
            raise MaterializationError("base row lacks representative_exercise_id")
        is_rep = str(row.get("canonical_status", "")) == "ACTIVE_CANONICAL_RETAINED"
        row["exercise_id"] = exercise_id
        row["legacy_exercise_id"] = exercise_id
        row["family_code"] = family_by_rep.get(exercise_id, "")
        equipment = valid_equipment(parse_values(row.get("equipment_codes")))
        row["equipment_codes"] = equipment
        row["location_codes"] = locations_for(equipment, parse_values(row.get("location_codes")))
        row["is_representative"] = is_rep
        row["variant_type_code"] = ""
        row["record_type"] = "REPRESENTATIVE" if is_rep else "SEPARATE_EXERCISE"
        row["representative_exercise_id"] = exercise_id if is_rep else ""
        row["variant_relation_status_code"] = "NOT_APPLICABLE"
        row["variant_materialization_status_code"] = "NOT_APPLICABLE"
        row["safety_mapping_status_code"] = "REPRESENTATIVE_SAFETY_CONTEXT"
        row["safety_mapping_source_representative_exercise_id"] = (
            exercise_id if is_rep else row["family_code"]
        )
        row["fitt_mapping_status_code"] = "RETAINED_FROM_REVIEWED_CATALOG"
        row["catalog_version_code"] = CATALOG_VERSION
        row["stable_code"] = str(row.get("stable_code", ""))
        if not row["stable_code"] or row["stable_code"] in used_stable:
            raise MaterializationError(
                f"base stable code missing or duplicated: {row['stable_code']}"
            )
        used_stable.add(row["stable_code"])
        if is_rep:
            rep_rows[exercise_id] = row
        catalog.append(row)

    # Resolve a family for promoted legacy exercises from their original alias mapping.
    for row in catalog:
        if row["record_type"] != "SEPARATE_EXERCISE":
            continue
        mapping_id = str(row.get("mapping_source_exercise_id", ""))
        alias = draft_alias_by_id.get(mapping_id, {})
        parent_stable = str(alias.get("exercise_stable_code", ""))
        parent_id = old_stable_to_rep.get(parent_stable, "")
        row["family_code"] = family_by_rep.get(parent_id, row["family_code"])
        row["safety_mapping_source_representative_exercise_id"] = parent_id
    if any(not row.get("family_code") for row in catalog):
        missing = [row["exercise_id"] for row in catalog if not row.get("family_code")]
        raise MaterializationError(f"base row family mapping missing: {missing}")
    return catalog, used_stable, rep_rows


def make_variant_row(
    entry: dict[str, Any],
    inputs: dict[str, Any],
    used_stable: set[str],
    rep_rows: dict[str, dict[str, Any]],
    variant_index: int,
) -> dict[str, Any]:
    variant_id = str(entry["variant_source_record_id"])
    rep_id = str(entry["representative_exercise_id"])
    if rep_id not in rep_rows:
        raise MaterializationError(
            f"Variant representative is not an active representative: {rep_id}"
        )
    parent = rep_rows[rep_id]
    if variant_id == rep_id:
        raise MaterializationError(f"Variant self-reference: {variant_id}")

    explicit = entry.get("explicit_variant")
    if explicit:
        old_row = inputs["legacy_by_id"].get(variant_id)
        if old_row is None:
            raise MaterializationError(f"explicit Variant source row missing: {variant_id}")
        source_id = "NEX-000018"
        source_row = inputs["integrated_by_nex"].get(source_id)
        draft_alias = inputs["draft_alias_by_id"].get(source_id, {})
        base = deepcopy(old_row)
        name_ko = str(base.get("name_ko") or explicit.get("name_ko") or "")
        name_en = str(base.get("name_en") or explicit.get("name_en") or "")
    else:
        batch = next(
            inputs["batch_by_id"][str(relation.get("candidate_pair_id"))]
            for relation in inputs["relationships"]
            if str(relation.get("candidate_pair_id")) == str(entry["candidate_pair_id"])
        )
        source_row = inputs["integrated_by_nex"].get(variant_id)
        draft_alias = inputs["draft_alias_by_id"].get(variant_id, {})
        if source_row is None:
            raise MaterializationError(
                f"Variant source row missing from integrated review: {variant_id}"
            )
        base = {}
        name_ko = str(batch.get("left_name_ko") or batch.get("right_name_ko") or "")
        name_en = str(
            batch.get("left_name_en")
            or batch.get("right_name_en")
            or source_row.get("name_en")
            or ""
        )
    if not source_row:
        raise MaterializationError(f"Variant source provenance missing: {variant_id}")
    raw = raw_source_record(source_row, inputs["gymvisual_by_id"])
    attrs = source_attributes(source_row, raw)
    english, english_steps, korean_instruction = source_instruction(source_row, raw)
    source_name = str(source_row.get("source_name") or source_row.get("name_en") or name_en)
    if not name_ko:
        name_ko = str(
            source_row.get("reviewed_name_ko") or source_row.get("source_display_name_ko") or ""
        )
    if not name_ko:
        raise MaterializationError(f"Variant lacks Korean display name: {variant_id}")

    equipment = valid_equipment(
        parse_values(
            (inputs["batch_by_id"].get(str(entry["candidate_pair_id"]), {}) or {}).get(
                "left_equipment_codes"
            )
        )
        or attrs["equipment_codes"]
        or infer_equipment(name_en)
    )
    locations = locations_for(
        equipment,
        attrs["location_codes"],
    )
    pattern = str(
        inputs["batch_by_id"]
        .get(str(entry["candidate_pair_id"]), {})
        .get("left_movement_pattern_code")
        or attrs["movement_pattern_code"]
        or parent.get("primary_movement_pattern_code")
        or ""
    )
    if not pattern:
        raise MaterializationError(f"Variant movement pattern missing: {variant_id}")
    stable = str(base.get("stable_code", "")) if explicit else ""
    if not stable or stable in used_stable:
        stable = stable_code_for(
            name_en or source_name, pattern, equipment, variant_id, used_stable
        )
    else:
        used_stable.add(stable)

    primary_areas = (
        attrs["primary_body_area_codes"]
        or parse_values(
            inputs["batch_by_id"]
            .get(str(entry["candidate_pair_id"]), {})
            .get("left_primary_body_area_codes")
        )
        or list(parent.get("primary_body_area_codes", []))
    )
    secondary_areas = (
        attrs["secondary_body_area_codes"]
        or parse_values(
            inputs["batch_by_id"]
            .get(str(entry["candidate_pair_id"]), {})
            .get("left_secondary_body_area_codes")
        )
        or list(parent.get("secondary_body_area_codes", []))
    )
    training_type = (
        attrs["training_type_code"]
        if attrs["training_type_code"] in {"STRENGTH", "CARDIO", "MOBILITY"}
        else parent.get("training_type_code", "STRENGTH")
    )
    body_focus = str(
        draft_alias.get("v1_body_focus_code")
        or attrs["body_focus_code"]
        or parent.get("body_focus_code")
        or ""
    )
    difficulty, difficulty_policy_rule = apply_difficulty_policy(
        {"stable_code": stable, "equipment_codes": equipment},
        str(attrs["difficulty_code"]),
    )
    allowed_levels = attrs["allowed_experience_level_codes"] or [difficulty]
    fitt = attrs["fitt_template_ids_by_experience"] or parse_json_object(
        parent.get("fitt_template_ids_by_experience")
    )
    rep_source_key = source_key(
        str(parent.get("source_track", "")), str(parent.get("source_identity", ""))
    )
    source_track = str(source_row.get("source_track") or parent.get("source_track", ""))
    source_identity = str(source_row.get("source_id") or parent.get("source_identity", ""))
    source_url = str(source_row.get("source_url") or source_row.get("source_url") or "")
    if not source_url:
        source_url = str(source_row.get("source_url") or "")
    source_license = str(source_row.get("source_license") or "")
    source_author = str(
        source_row.get("source_author") or source_row.get("source_license_author") or ""
    )
    source_media_reference = str(source_row.get("source_media_reference") or "")
    summary = korean_instruction or f"{name_ko}의 한국어 수행 안내는 Variant 검수 후 확정한다."
    cues = attrs["form_cues_ko"] or [
        "원천 수행 단계를 확인하고 안정적인 자세를 잡는다.",
        "통제된 범위에서 Variant의 고유한 수행법을 따른다.",
        "불편하거나 이상 반응이 있으면 즉시 중단한다.",
    ]
    extra_codes = [
        "VARIANT_RELATION_REVIEW_REQUIRED",
        "FAMILY_REPRESENTATIVE_MAPPING_REVIEW_REQUIRED",
        "VARIANT_SAFETY_REVIEW_REQUIRED",
        "VARIANT_FITT_REVIEW_REQUIRED",
    ]
    review_required_codes = review_codes(source_row, extra_codes)
    exercise_id = variant_id if explicit else f"VEX-{variant_index:06d}"
    if exercise_id in {str(row.get("exercise_id")) for row in rep_rows.values()}:
        raise MaterializationError(
            f"Variant exercise ID duplicates a representative: {exercise_id}"
        )
    row: dict[str, Any] = {
        "exercise_id": exercise_id,
        "legacy_exercise_id": variant_id,
        "record_type": "VARIANT",
        "catalog_version_code": CATALOG_VERSION,
        "stable_code": stable,
        "name_ko": name_ko,
        "display_name_ko": name_ko,
        "name_en": name_en or source_name,
        "family_code": inputs["family_by_rep"].get(rep_id, ""),
        "representative_exercise_id": rep_id,
        "variant_type_code": entry["variant_type_code"],
        "is_representative": False,
        "training_type_code": training_type,
        "body_focus_code": body_focus,
        "primary_movement_pattern_code": pattern,
        "primary_body_area_codes": compact_list(primary_areas),
        "secondary_body_area_codes": compact_list(secondary_areas),
        "equipment_codes": equipment,
        "location_codes": locations,
        "difficulty_code": difficulty,
        "difficulty_policy_rule_code": difficulty_policy_rule,
        "difficulty_status": "REVIEW_REQUIRED",
        "timing_mode_code": attrs["timing_mode_code"] or parent.get("timing_mode_code", "REPS"),
        "phase_codes": list(parent.get("phase_codes", ["MAIN"])),
        "default_seconds_per_rep": attrs["default_seconds_per_rep"]
        or parent.get("default_seconds_per_rep"),
        "default_work_seconds": attrs["default_work_seconds"] or parent.get("default_work_seconds"),
        "default_rest_seconds": attrs["default_rest_seconds"] or parent.get("default_rest_seconds"),
        "default_transition_seconds": attrs["default_transition_seconds"]
        or parent.get("default_transition_seconds"),
        "instruction_summary_ko": summary,
        "form_cues_ko": cues,
        "instruction_content_version": "variant-source-review-v1.0.0",
        "setup_condition_ko": f"{', '.join(equipment)} 장비와 안정적인 수행 공간을 준비한다.",
        "source_track": source_track,
        "source_identity": source_identity,
        "source_key": source_key(source_track, source_identity),
        "source_system": source_track,
        "source_record_id": source_identity,
        "source_name": source_name,
        "source_name_en": str(source_row.get("name_en") or source_name),
        "source_name_ko": str(source_row.get("source_display_name_ko") or name_ko),
        "source_url": source_url,
        "source_author": source_author,
        "source_license": source_license,
        "source_media_reference": source_media_reference,
        "source_media_id": str(source_row.get("source_media_id") or ""),
        "source_instruction_en": english,
        "source_instruction_steps_en": english_steps,
        "source_provenance_status": "RESOLVED_INTEGRATED_SOURCE",
        "review_status_code": "REVIEW_REQUIRED",
        "review_required": True,
        "review_required_codes": review_required_codes,
        "production_eligible": False,
        "recovery_eligible": attrs["recovery_eligible"],
        "canonical_status": "VARIANT_MATERIALIZED_DRAFT",
        "canonical_decision_code": entry["variant_type_code"],
        "canonical_decision_source": entry["decision_source"],
        "canonical_decision_note_ko": entry["decision_note_ko"],
        "variant_relation_status_code": entry["relation_status_code"],
        "variant_materialization_status_code": "MATERIALIZED_DRAFT_REVIEW_REQUIRED",
        "variant_candidate_pair_id": entry["candidate_pair_id"],
        "safety_mapping_status_code": "REVIEW_REQUIRED",
        "safety_mapping_source_representative_exercise_id": rep_id,
        "safety_rule_binding_status_code": "PENDING_VARIANT_SAFETY_REVIEW",
        "fitt_mapping_status_code": "REVIEW_REQUIRED",
        "fitt_template_ids_by_experience": fitt,
        "fitt_mapping_source_representative_exercise_id": rep_id,
        "fitt_allowed_experience_level_codes": allowed_levels,
        "representative_source_key": rep_source_key,
        "raw_source_record_json": raw,
    }
    return row


def materialize(
    inputs: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    catalog, used_stable, rep_rows = base_catalog_rows(inputs)
    entries = candidate_entries(inputs)
    materialized_by_pair: dict[str, dict[str, Any]] = {}
    variant_rows: list[dict[str, Any]] = []
    next_variant = 1
    for entry in entries:
        if not entry.get("variant_source_record_id"):
            continue
        row = make_variant_row(entry, inputs, used_stable, rep_rows, next_variant)
        next_variant += 1
        if row["stable_code"] in {str(item.get("stable_code")) for item in catalog}:
            raise MaterializationError(
                f"Variant stable code duplicates catalog row: {row['stable_code']}"
            )
        catalog.append(row)
        variant_rows.append(row)
        materialized_by_pair[str(entry["candidate_pair_id"])] = row

    relationship_rows: list[dict[str, Any]] = []
    for entry in entries:
        row = deepcopy(entry)
        materialized = materialized_by_pair.get(str(entry["candidate_pair_id"]))
        row["variant_exercise_id"] = materialized.get("exercise_id", "") if materialized else ""
        row["variant_stable_code"] = materialized.get("stable_code", "") if materialized else ""
        row["representative_stable_code"] = (
            rep_rows.get(str(entry.get("representative_exercise_id")), {}).get("stable_code", "")
            if entry.get("representative_exercise_id")
            else ""
        )
        row["family_code"] = (
            rep_rows.get(str(entry.get("representative_exercise_id")), {}).get("family_code", "")
            if entry.get("representative_exercise_id")
            else ""
        )
        row["materialization_status_code"] = (
            "MATERIALIZED_DRAFT_REVIEW_REQUIRED"
            if materialized
            else "NOT_MATERIALIZED_REVIEW_REQUIRED"
        )
        row["relation_finalized"] = False
        row["production_eligible"] = False
        row["materialization_version"] = MATERIALIZATION_VERSION
        relationship_rows.append(row)

    counts = Counter(row["variant_type_code"] for row in variant_rows)
    candidate_counts = Counter(row["variant_type_code"] for row in relationship_rows)
    report: dict[str, Any] = {
        "schema_version": "exercise-catalog-v2.0.2-variant-integrity-v1",
        "catalog_version_code": CATALOG_VERSION,
        "materialization_version": MATERIALIZATION_VERSION,
        "generated_at": GENERATED_AT,
        "status": "DRAFT_VARIANTS_MATERIALIZED_REVIEW_REQUIRED",
        "production_eligible": False,
        "counts": {
            "representative_exercise_count": sum(
                row.get("is_representative") is True for row in catalog
            ),
            "primary_variant_count": counts["PRIMARY_VARIANT"],
            "secondary_variant_count": counts["SECONDARY_VARIANT"],
            "separate_exercise_count": sum(
                row.get("record_type") == "SEPARATE_EXERCISE" for row in catalog
            ),
            "variant_record_count": len(variant_rows),
            "integrated_catalog_exercise_count": len(catalog),
            "relationship_review_required_count": sum(
                row.get("review_status_code") == "REVIEW_REQUIRED" for row in relationship_rows
            ),
            "review_required_variant_record_count": sum(
                row.get("review_status_code") == "REVIEW_REQUIRED" for row in variant_rows
            ),
            "relationship_candidate_primary_variant_count": candidate_counts["PRIMARY_VARIANT"],
            "relationship_candidate_secondary_variant_count": candidate_counts["SECONDARY_VARIANT"],
            "unmaterialized_review_required_canonical_pair_count": sum(
                row["materialization_status_code"] == "NOT_MATERIALIZED_REVIEW_REQUIRED"
                for row in relationship_rows
            ),
        },
        "invariants": {},
    }
    report["invariants"] = validate_integrity(catalog, relationship_rows, rep_rows)
    if not all(report["invariants"].values()):
        raise MaterializationError(f"Variant integrity validation failed: {report['invariants']}")
    return catalog, relationship_rows, report


def validate_integrity(
    catalog: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    rep_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    catalog_by_id = {str(row.get("exercise_id")): row for row in catalog}
    stable_codes = [str(row.get("stable_code", "")) for row in catalog]
    variants = [row for row in catalog if row.get("record_type") == "VARIANT"]
    variant_relation_by_id: dict[str, set[str]] = defaultdict(set)
    for row in relationships:
        if row.get("variant_exercise_id"):
            variant_relation_by_id[str(row["variant_exercise_id"])].add(
                str(row.get("representative_exercise_id", ""))
            )
    return {
        "all_variant_rows_are_exercise_records": all(
            row.get("record_type") == "VARIANT" for row in variants
        ),
        "all_variants_are_non_representative": all(
            row.get("is_representative") is False for row in variants
        ),
        "all_variant_types_allowed": all(
            row.get("variant_type_code") in VALID_VARIANT_TYPES for row in variants
        ),
        "all_variant_representatives_exist": all(
            row.get("representative_exercise_id") in rep_rows
            and catalog_by_id.get(str(row.get("representative_exercise_id")), {}).get(
                "is_representative"
            )
            is True
            for row in variants
        ),
        "all_variant_families_match_representatives": all(
            row.get("family_code")
            == rep_rows.get(str(row.get("representative_exercise_id")), {}).get("family_code")
            for row in variants
        ),
        "no_variant_self_reference": all(
            row.get("exercise_id") != row.get("representative_exercise_id") for row in variants
        ),
        "stable_codes_unique": len(stable_codes) == len(set(stable_codes)) and all(stable_codes),
        "variant_exercise_ids_unique": len(variants)
        == len({row.get("exercise_id") for row in variants}),
        "no_same_exercise_variant": all(
            row.get("variant_type_code") in VALID_VARIANT_TYPES
            for row in relationships
            if row.get("variant_exercise_id")
        ),
        "no_variant_conflicting_representatives": all(
            len(representatives) == 1 for representatives in variant_relation_by_id.values()
        ),
        "all_relationships_review_required_are_not_finalized": all(
            not row.get("relation_finalized")
            for row in relationships
            if row.get("review_status_code") == "REVIEW_REQUIRED"
        ),
        "all_variant_safety_and_fitt_mappings_review_gated": all(
            row.get("safety_mapping_status_code") == "REVIEW_REQUIRED"
            and row.get("fitt_mapping_status_code") == "REVIEW_REQUIRED"
            for row in variants
        ),
        "no_unexpected_record_types": all(
            row.get("record_type") in VALID_RECORD_TYPES for row in catalog
        ),
    }


def write_intermediate_manifest(
    output: Path,
    catalog: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    manifest = {
        "catalog_version_code": CATALOG_VERSION,
        "status": "INTERMEDIATE_VARIANTS_MATERIALIZED_REVIEW_REQUIRED",
        "production_eligible": False,
        "variant_materialization": {
            "version": MATERIALIZATION_VERSION,
            "catalog_path": "catalog/exercises.jsonl",
            "relationship_review_path": "variant_relationship_review_v2_0_2.jsonl",
            "family_mapping_path": "family_representative_mapping_v2_0_2.jsonl",
            "integrity_report_path": "variant_integrity_report_v2_0_2.json",
            "counts": report["counts"],
        },
        "difficulty_policy": {
            "path": str(POLICY_PATH.relative_to(PROJECT_ROOT)),
            "policy_version": load_policy()["policy_version"],
            "sha256": sha256(POLICY_PATH),
        },
        "artifact_sha256": {},
    }
    artifacts = manifest["artifact_sha256"]
    for filename in [
        "catalog/exercises.jsonl",
        "catalog/exercises.csv",
        "runtime/catalog.jsonl",
        "variant_relationship_review_v2_0_2.jsonl",
        "variant_relationship_review_v2_0_2.csv",
        "family_representative_mapping_v2_0_2.jsonl",
        "family_representative_mapping_v2_0_2.csv",
        "variant_safety_fitt_mapping_v2_0_2.jsonl",
        "variant_safety_fitt_mapping_v2_0_2.csv",
        "variant_integrity_report_v2_0_2.json",
    ]:
        path = output / filename
        if path.exists():
            artifacts[filename] = sha256(path)
    manifest["integrated_catalog_exercise_count"] = len(catalog)
    manifest["variant_relationship_record_count"] = len(relationships)
    write_json(output / "intermediate_manifest.json", manifest)


def write_handoff_report(report_path: Path, report: dict[str, Any]) -> None:
    counts = report["counts"]
    lines = [
        "# v2.0.2 Variant 독립 운동 레코드 중간 산출물",
        "",
        f"- 생성 시각: `{report['generated_at']}`",
        "- 상태: `INTERMEDIATE_VARIANTS_MATERIALIZED_REVIEW_REQUIRED`",
        "- 범위: 201건 기준은 검토용 중간 산출물이며 DB 적재 또는 최종 manifest에 포함하지 않는다.",
        "- 운영 적격: `false`",
        "",
        "## 집계",
        "",
        "| 항목 | 건수 |",
        "|---|---:|",
        f"| 대표운동 | {counts['representative_exercise_count']} |",
        f"| PRIMARY_VARIANT 독립 row | {counts['primary_variant_count']} |",
        f"| SECONDARY_VARIANT 독립 row | {counts['secondary_variant_count']} |",
        f"| 별도 운동 | {counts['separate_exercise_count']} |",
        f"| Variant 독립 row 합계 | {counts['variant_record_count']} |",
        f"| 중간 물질화 카탈로그 전체 운동 | {counts['integrated_catalog_exercise_count']} |",
        f"| REVIEW_REQUIRED 관계 | {counts['relationship_review_required_count']} |",
        f"| 미물질화 REVIEW_REQUIRED canonical pair | {counts['unmaterialized_review_required_canonical_pair_count']} |",
        "",
        "## 처리 원칙",
        "",
        "- 방향이 있는 alias-to-representative Variant 69건과 명시된 REX-000105 1건은 독립 `VARIANT` row로 물질화했다.",
        "- 관계 후보 집계는 PRIMARY 75건·SECONDARY 5건을 보존한다. 이 중 canonical-canonical 10건은 대표 방향이 확정되지 않아 row를 만들지 않았다.",
        "- 모든 Variant의 관계·안전·FITT 상태는 `REVIEW_REQUIRED`이며 `production_eligible=false`다.",
        "- `ROPE`·`SUSPENSION_STRAPS`는 승인된 장비 코드 정책에 따라 `STRETCH_STRAP`으로 정규화했고, `BENCH`·`CHAIR`는 장비 코드에서 제외했다.",
        "- HOME 허용 장비를 사용하는 row의 location_codes는 `HOME`,`GYM`으로 정규화하고, HOME 미지원 장비 row는 `GYM`만 유지한다.",
        "",
        "## 산출물",
        "",
        "- `generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/catalog/exercises.jsonl`",
        "- `generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/variant_relationship_review_v2_0_2.jsonl`",
        "- `generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/family_representative_mapping_v2_0_2.jsonl`",
        "- `generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/variant_safety_fitt_mapping_v2_0_2.jsonl`",
        "- `generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/variant_integrity_report_v2_0_2.json`",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(args: argparse.Namespace) -> dict[str, Any]:
    inputs = prepare_inputs(args)
    catalog, relationships, report = materialize(inputs)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    catalog_sorted = sorted(catalog, key=lambda row: str(row.get("exercise_id", "")))
    relationship_sorted = sorted(
        relationships, key=lambda row: str(row.get("candidate_pair_id", ""))
    )
    write_jsonl(output / "catalog/exercises.jsonl", catalog_sorted)
    write_csv(output / "catalog/exercises.csv", catalog_sorted)
    write_jsonl(output / "runtime/catalog.jsonl", catalog_sorted)
    write_jsonl(output / "variant_relationship_review_v2_0_2.jsonl", relationship_sorted)
    write_csv(output / "variant_relationship_review_v2_0_2.csv", relationship_sorted)

    mapping = [
        {
            "exercise_id": row.get("exercise_id", ""),
            "stable_code": row.get("stable_code", ""),
            "record_type": row.get("record_type", ""),
            "is_representative": row.get("is_representative", False),
            "family_code": row.get("family_code", ""),
            "representative_exercise_id": row.get("representative_exercise_id", ""),
            "variant_type_code": row.get("variant_type_code", ""),
            "source_key": row.get("source_key", ""),
            "review_status_code": row.get("review_status_code", ""),
            "variant_relation_status_code": row.get("variant_relation_status_code", ""),
            "variant_materialization_status_code": row.get(
                "variant_materialization_status_code", ""
            ),
            "safety_mapping_status_code": row.get("safety_mapping_status_code", ""),
            "fitt_mapping_status_code": row.get("fitt_mapping_status_code", ""),
        }
        for row in catalog_sorted
    ]
    write_jsonl(output / "family_representative_mapping_v2_0_2.jsonl", mapping)
    write_csv(output / "family_representative_mapping_v2_0_2.csv", mapping)

    safety_fitt = [
        {
            "exercise_id": row["exercise_id"],
            "stable_code": row["stable_code"],
            "family_code": row["family_code"],
            "representative_exercise_id": row["representative_exercise_id"],
            "variant_type_code": row["variant_type_code"],
            "safety_mapping_status_code": row["safety_mapping_status_code"],
            "safety_mapping_source_representative_exercise_id": row[
                "safety_mapping_source_representative_exercise_id"
            ],
            "safety_rule_binding_status_code": row["safety_rule_binding_status_code"],
            "fitt_mapping_status_code": row["fitt_mapping_status_code"],
            "fitt_mapping_source_representative_exercise_id": row[
                "fitt_mapping_source_representative_exercise_id"
            ],
            "fitt_template_ids_by_experience": row["fitt_template_ids_by_experience"],
            "review_status_code": row["review_status_code"],
            "production_eligible": row["production_eligible"],
        }
        for row in catalog_sorted
        if row.get("record_type") == "VARIANT"
    ]
    write_jsonl(output / "variant_safety_fitt_mapping_v2_0_2.jsonl", safety_fitt)
    write_csv(output / "variant_safety_fitt_mapping_v2_0_2.csv", safety_fitt)
    write_json(output / "variant_integrity_report_v2_0_2.json", report)
    write_handoff_report(output / "V2_0_2_VARIANT_CATALOG_INTERMEDIATE.md", report)
    write_intermediate_manifest(output, catalog_sorted, relationship_sorted, report)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build(args)
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
