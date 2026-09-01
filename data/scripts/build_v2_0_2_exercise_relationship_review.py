"""Build a conservative v2.0.2 exercise duplicate/relationship review batch.

The existing v2.0.2 combined catalog CSV is the only exercise-record source of
truth for this generator.  ``EXERCISE`` rows are canonical catalog records and
``V1_ALIAS`` rows are retained compatibility identities.  Alias rows create
identity/relationship candidates after comparing their names and method
proxies; canonical pairs are only candidates and are never merged or assigned
a new stable code.

This module intentionally does not rebuild V1/V2 integration, change catalog
rows, or edit existing alternative relationships.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "generated/exercise-catalog-v2.0.2-draft/catalog/exercises_v1_v2.csv"
DEFAULT_ALTERNATIVES = (
    ROOT / "generated/exercise-catalog-v2.0.2-draft/alternatives/alternatives.jsonl"
)
DEFAULT_PROFILE_DIR = ROOT / "validation/profiles/exercise-relationship-v2.0.2"
DEFAULT_BATCH_DIR = (
    ROOT / "validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0"
)

RELATION_CODES = {
    "SAME_EXERCISE",
    "PRIMARY_VARIANT",
    "SECONDARY_VARIANT",
    "SEPARATE_EXERCISE",
    "EXCLUDED",
    "REVIEW_REQUIRED",
}

# The source catalog has already removed the 94 V1 aliases whose normalized
# names duplicate their canonical exercise.  Keep the post-dedup shape as an
# explicit input guard so regeneration cannot silently drift from the review
# batch that this workflow routes.
EXPECTED_CANONICAL_COUNT = 102
EXPECTED_ALIAS_COUNT = 114

REVIEW_STATUS = "REVIEW_REQUIRED"
PRODUCTION_ELIGIBLE = "false"

VARIANT_TOKENS = {
    "alternating",
    "arm",
    "arms",
    "against",
    "back",
    "barbell",
    "band",
    "bench",
    "bilateral",
    "bike",
    "bodyweight",
    "cable",
    "chair",
    "close",
    "decline",
    "dumbbell",
    "elliptical",
    "ez",
    "female",
    "floor",
    "full",
    "grip",
    "incline",
    "kettlebell",
    "kneeling",
    "lying",
    "machine",
    "male",
    "mat",
    "neutral",
    "one",
    "partial",
    "prone",
    "raised",
    "rope",
    "seated",
    "single",
    "standing",
    "step",
    "strap",
    "stability",
    "straight",
    "stiff",
    "sumo",
    "supinated",
    "underhand",
    "version",
    "v",
    "wide",
    "wall",
}

DIMENSION_TOKENS = {
    "EQUIPMENT": {
        "barbell",
        "band",
        "bodyweight",
        "cable",
        "dumbbell",
        "elliptical",
        "kettlebell",
        "machine",
        "mat",
        "rope",
        "stability",
        "step",
        "strap",
        "weight",
    },
    "POSTURE": {
        "chair",
        "decline",
        "floor",
        "incline",
        "kneeling",
        "lying",
        "prone",
        "seated",
        "standing",
        "wall",
    },
    "GRIP": {
        "close",
        "grip",
        "neutral",
        "supinated",
        "underhand",
        "wide",
    },
    "STANCE": {"alternating", "bilateral", "one", "single", "split", "staggered", "sumo"},
    "ROM": {"full", "partial", "raised", "straight", "stiff", "twist", "rotation"},
}

CSV_FIELDS = [
    "batch_id",
    "candidate_pair_id",
    "left_record_type",
    "left_record_id",
    "left_representative_exercise_id",
    "left_stable_code",
    "left_source_track",
    "left_source_identity",
    "left_name_ko",
    "left_name_en",
    "left_normalized_name",
    "left_movement_pattern_code",
    "left_primary_body_area_codes",
    "left_secondary_body_area_codes",
    "left_equipment_codes",
    "left_location_codes",
    "left_difficulty_code",
    "left_v1_exercise_ids",
    "right_record_type",
    "right_record_id",
    "right_representative_exercise_id",
    "right_stable_code",
    "right_source_track",
    "right_source_identity",
    "right_name_ko",
    "right_name_en",
    "right_normalized_name",
    "right_movement_pattern_code",
    "right_primary_body_area_codes",
    "right_secondary_body_area_codes",
    "right_equipment_codes",
    "right_location_codes",
    "right_difficulty_code",
    "right_v1_exercise_ids",
    "candidate_relation_code",
    "candidate_relation_basis",
    "comparison_dimensions",
    "source_identity_match",
    "stable_code_match",
    "normalized_name_match",
    "movement_pattern_match",
    "primary_body_area_overlap",
    "secondary_body_area_overlap",
    "actual_method_evidence_level",
    "equipment_comparison",
    "posture_grip_stance_rom_evidence",
    "existing_alternative_relation_reference",
    "existing_alternative_relation_direction",
    "candidate_confidence_code",
    "review_decision",
    "review_status_code",
    "review_note",
    "production_eligible",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"input catalog is empty: {path}")
    return rows


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record must be an object at {path}:{line_number}")
            rows.append(value)
    return rows


def parse_json_list(value: str) -> list[str]:
    if not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [item.strip() for item in value.split("|") if item.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def compact_json(value: Iterable[str]) -> str:
    return json.dumps(list(value), ensure_ascii=False, separators=(",", ":"))


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"\bv\.?\s*\d+\b", " ", value)
    value = re.sub(r"\b(?:male|female)\b", " ", value)
    value = re.sub(r"[^\w가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def token_set(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token}


def infer_equipment_from_name(value: str) -> list[str]:
    tokens = token_set(value)
    equipment_by_token = (
        ("barbell", "BARBELL"),
        ("dumbbell", "DUMBBELL"),
        ("kettlebell", "KETTLEBELL"),
        ("cable", "CABLE_MACHINE"),
        ("machine", "MACHINE"),
        ("band", "RESISTANCE_BAND"),
        ("strap", "STRETCH_STRAP"),
        ("rope", "JUMP_ROPE"),
        ("elliptical", "ELLIPTICAL_MACHINE"),
        ("bike", "STATIONARY_BIKE"),
        ("mat", "MAT"),
        ("step", "STEP_BOX"),
        ("stability", "STABILITY_BALL"),
        ("roller", "FOAM_ROLLER"),
        ("weight", "HOUSEHOLD_WEIGHT"),
    )
    return [code for token, code in equipment_by_token if token in tokens]


def name_for(row: dict[str, str]) -> str:
    return row.get("name_en", "").strip() or row.get("name_ko", "").strip()


def normalized_name_for(row: dict[str, str]) -> str:
    return normalize_text(name_for(row))


def core_name_tokens(row: dict[str, str]) -> set[str]:
    stable_tokens = set(row.get("stable_code", "").casefold().split("_"))
    name_tokens = token_set(name_for(row))
    all_tokens = name_tokens | stable_tokens
    return {
        token
        for token in all_tokens
        if token not in VARIANT_TOKENS and len(token) > 1 and not token.isdigit()
    }


def json_fields(row: dict[str, str]) -> dict[str, list[str]]:
    return {
        "primary": parse_json_list(row.get("primary_body_area_codes", "")),
        "secondary": parse_json_list(row.get("secondary_body_area_codes", "")),
        "equipment": parse_json_list(row.get("equipment_codes", "")),
        "location": parse_json_list(row.get("location_codes", "")),
        "v1": parse_json_list(row.get("v1_exercise_ids", "")),
    }


def method_dimensions(row: dict[str, str]) -> dict[str, set[str]]:
    tokens = token_set(name_for(row)) | set(row.get("stable_code", "").casefold().split("_"))
    return {dimension: tokens & values for dimension, values in DIMENSION_TOKENS.items()}


def overlap(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def overlap_code(value: float) -> str:
    return f"{value:.3f}"


def validate_input(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    required = {
        "record_type",
        "stable_code",
        "representative_exercise_id",
        "name_ko",
        "name_en",
        "primary_movement_pattern_code",
        "primary_body_area_codes",
        "secondary_body_area_codes",
        "equipment_codes",
        "location_codes",
        "difficulty_code",
        "source_track",
        "source_identity",
        "v1_exercise_ids",
        "v1_exercise_id",
        "exercise_stable_code",
    }
    missing = sorted(required.difference(rows[0]))
    if missing:
        raise ValueError(f"combined catalog is missing required fields: {missing}")
    canonical = [row for row in rows if row["record_type"] == "EXERCISE"]
    aliases = [row for row in rows if row["record_type"] == "V1_ALIAS"]
    unknown = [
        row["record_type"] for row in rows if row["record_type"] not in {"EXERCISE", "V1_ALIAS"}
    ]
    if unknown:
        raise ValueError(f"unexpected record types: {sorted(set(unknown))}")
    if len(canonical) != EXPECTED_CANONICAL_COUNT or len(aliases) != EXPECTED_ALIAS_COUNT:
        raise ValueError(
            "v2.0.2 combined catalog shape changed: "
            f"expected {EXPECTED_CANONICAL_COUNT} EXERCISE + "
            f"{EXPECTED_ALIAS_COUNT} V1_ALIAS, got {len(canonical)} + {len(aliases)}"
        )
    stable_codes = [row["stable_code"] for row in canonical]
    if any(not code for code in stable_codes) or len(stable_codes) != len(set(stable_codes)):
        raise ValueError("canonical stable_code values must be present and unique")
    source_keys = [(row["source_track"], row["source_identity"]) for row in canonical]
    if any(not track or not identity for track, identity in source_keys):
        raise ValueError("canonical source identity values must be present")
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("canonical source_track/source_identity values must be unique")
    stable_set = set(stable_codes)
    for row in aliases:
        if not row["v1_exercise_id"] or row["exercise_stable_code"] not in stable_set:
            raise ValueError(f"alias is not mapped to a canonical stable code: {row}")
    return canonical, aliases


def alternative_reference(
    rows: list[dict[str, Any]], canonical_by_stable: dict[str, dict[str, str]]
) -> tuple[dict[tuple[str, str], list[str]], int]:
    references: dict[tuple[str, str], list[str]] = {}
    unmapped = 0
    for row in rows:
        left = str(row.get("source_exercise_stable_code", "")).strip()
        right = str(row.get("alternative_exercise_stable_code", "")).strip()
        if not left or not right or left == right:
            continue
        if left not in canonical_by_stable or right not in canonical_by_stable:
            unmapped += 1
            continue
        key: tuple[str, str] = (left, right) if left < right else (right, left)
        direction = f"{left}>{right}"
        if direction not in references.setdefault(key, []):
            references[key].append(direction)
    return references, unmapped


def compact_record(row: dict[str, str], record_type: str | None = None) -> dict[str, Any]:
    fields = json_fields(row)
    if record_type == "V1_ALIAS":
        stable = row["exercise_stable_code"]
        record_id = row["v1_exercise_id"]
        name_ko = row.get("v1_exercise_name_ko", "")
        name_en = row.get("v1_name_en", "") or row.get("v1_source_name_en", "")
        source_track = "v1"
        source_identity = f"v1:{record_id}"
        representative_id = ""
        movement = ""
        primary = parse_json_list(row.get("v1_primary_body_area_codes", ""))
        secondary = parse_json_list(row.get("v1_secondary_body_area_codes", ""))
        equipment = infer_equipment_from_name(name_en or name_ko)
        location = []
        difficulty = row.get("difficulty_code", "")
        v1_ids = [record_id]
    else:
        stable = row["stable_code"]
        record_id = row["representative_exercise_id"]
        name_ko = row.get("name_ko", "")
        name_en = row.get("name_en", "")
        source_track = row.get("source_track", "")
        source_identity = row.get("source_identity", "")
        representative_id = row.get("representative_exercise_id", "")
        movement = row.get("primary_movement_pattern_code", "")
        primary = fields["primary"]
        secondary = fields["secondary"]
        equipment = fields["equipment"]
        location = fields["location"]
        difficulty = row.get("difficulty_code", "")
        v1_ids = fields["v1"]
    return {
        "record_type": record_type or row["record_type"],
        "record_id": record_id,
        "representative_exercise_id": representative_id,
        "stable_code": stable,
        "source_track": source_track,
        "source_identity": source_identity,
        "name_ko": name_ko,
        "name_en": name_en,
        "normalized_name": normalize_text(name_en or name_ko),
        "movement_pattern_code": movement,
        "primary_body_area_codes": primary,
        "secondary_body_area_codes": secondary,
        "equipment_codes": equipment,
        "location_codes": location,
        "difficulty_code": difficulty,
        "v1_exercise_ids": v1_ids,
        "core_name_tokens": sorted(
            core_name_tokens({**row, "name_en": name_en, "stable_code": stable})
        ),
        "method_dimensions": method_dimensions({**row, "name_en": name_en, "stable_code": stable}),
    }


def record_fields(prefix: str, record: dict[str, Any]) -> dict[str, str]:
    return {
        f"{prefix}_record_type": record["record_type"],
        f"{prefix}_record_id": record["record_id"],
        f"{prefix}_representative_exercise_id": record["representative_exercise_id"],
        f"{prefix}_stable_code": record["stable_code"],
        f"{prefix}_source_track": record["source_track"],
        f"{prefix}_source_identity": record["source_identity"],
        f"{prefix}_name_ko": record["name_ko"],
        f"{prefix}_name_en": record["name_en"],
        f"{prefix}_normalized_name": record["normalized_name"],
        f"{prefix}_movement_pattern_code": record["movement_pattern_code"],
        f"{prefix}_primary_body_area_codes": compact_json(record["primary_body_area_codes"]),
        f"{prefix}_secondary_body_area_codes": compact_json(record["secondary_body_area_codes"]),
        f"{prefix}_equipment_codes": compact_json(record["equipment_codes"]),
        f"{prefix}_location_codes": compact_json(record["location_codes"]),
        f"{prefix}_difficulty_code": record["difficulty_code"],
        f"{prefix}_v1_exercise_ids": compact_json(record["v1_exercise_ids"]),
    }


def dimension_evidence(left: dict[str, Any], right: dict[str, Any]) -> tuple[list[str], str]:
    dimensions: list[str] = []
    evidence: list[str] = []
    # An alias name often omits the canonical equipment.  An empty inferred
    # value is unknown, not evidence that the exercise uses different gear.
    if (
        left["equipment_codes"]
        and right["equipment_codes"]
        and set(left["equipment_codes"]) != set(right["equipment_codes"])
    ):
        dimensions.append("EQUIPMENT")
        evidence.append(
            f"equipment:{'|'.join(left['equipment_codes']) or 'UNKNOWN'}->"
            f"{'|'.join(right['equipment_codes']) or 'UNKNOWN'}"
        )
    for dimension in ("POSTURE", "GRIP", "STANCE", "ROM"):
        left_values = set(left["method_dimensions"][dimension])
        right_values = set(right["method_dimensions"][dimension])
        if left_values != right_values:
            dimensions.append(dimension)
            evidence.append(
                f"{dimension.lower()}:{'|'.join(sorted(left_values)) or 'NONE'}->"
                f"{'|'.join(sorted(right_values)) or 'NONE'}"
            )
    left_core, right_core = set(left["core_name_tokens"]), set(right["core_name_tokens"])
    if left_core != right_core:
        dimensions.append("ACTUAL_METHOD")
        evidence.append(
            f"method_tokens:{'|'.join(sorted(left_core)) or 'NONE'}->"
            f"{'|'.join(sorted(right_core)) or 'NONE'}"
        )
    return dimensions, ";".join(evidence)


def classify_canonical_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    alternative_directions: list[str],
) -> tuple[str, str, list[str], str, str, str, str]:
    primary_overlap = overlap(left["primary_body_area_codes"], right["primary_body_area_codes"])
    secondary_overlap = overlap(
        left["secondary_body_area_codes"], right["secondary_body_area_codes"]
    )
    pattern_match = bool(
        left["movement_pattern_code"]
        and left["movement_pattern_code"] == right["movement_pattern_code"]
    )
    name_match = bool(
        left["normalized_name"] and left["normalized_name"] == right["normalized_name"]
    )
    core_similarity = overlap(left["core_name_tokens"], right["core_name_tokens"])
    dimensions, evidence = dimension_evidence(left, right)
    has_method_proxy = bool(left["name_en"] and right["name_en"])
    alt_reference = bool(alternative_directions)

    if name_match and pattern_match and primary_overlap > 0 and not dimensions:
        relation = "REVIEW_REQUIRED"
        basis = "NORMALIZED_NAME_MATCH_BUT_CANONICAL_STABLE_CODES_DIFFER"
        confidence = "MEDIUM"
    elif pattern_match and primary_overlap > 0 and core_similarity >= 0.75:
        if not dimensions:
            relation = "REVIEW_REQUIRED"
            basis = "SAME_METHOD_PROXY_WITH_DIFFERENT_CANONICAL_STABLE_CODES"
            confidence = "LOW"
        elif set(dimensions).issubset({"GRIP", "STANCE", "ROM"}):
            relation = "SECONDARY_VARIANT"
            basis = "SAME_PATTERN_PRIMARY_AREA_AND_GRIP_STANCE_OR_ROM_DIFFERENCE"
            confidence = "MEDIUM"
        else:
            relation = "PRIMARY_VARIANT"
            basis = "SAME_PATTERN_PRIMARY_AREA_AND_MATERIAL_EXECUTION_DIMENSION_DIFFERENCE"
            confidence = "MEDIUM"
    elif pattern_match and primary_overlap > 0:
        relation = "SEPARATE_EXERCISE" if core_similarity < 0.25 else "REVIEW_REQUIRED"
        basis = "SAME_PATTERN_OR_PRIMARY_AREA_WITH_INSUFFICIENT_METHOD_IDENTITY"
        confidence = "LOW"
    elif alt_reference:
        relation = "REVIEW_REQUIRED"
        basis = "EXISTING_ALTERNATIVE_REFERENCE_REQUIRES_DUPLICATE_BOUNDARY_RECHECK"
        confidence = "LOW"
    else:
        relation = "REVIEW_REQUIRED"
        basis = "NAME_OR_TAXONOMY_PROXIMITY_WITHOUT_EXECUTION_STEP_EVIDENCE"
        confidence = "LOW"

    if not has_method_proxy:
        relation = "REVIEW_REQUIRED"
        basis = f"{basis}_AND_METHOD_EVIDENCE_INCOMPLETE"
        confidence = "LOW"
    return (
        relation,
        basis,
        dimensions,
        evidence,
        overlap_code(primary_overlap),
        overlap_code(secondary_overlap),
        confidence,
    )


def make_row(
    batch_id: str,
    pair_number: int,
    left: dict[str, Any],
    right: dict[str, Any],
    relation: str,
    basis: str,
    dimensions: list[str],
    evidence: str,
    primary_overlap: str,
    secondary_overlap: str,
    confidence: str,
    alternative_directions: list[str],
    *,
    method_level: str,
    identity_match: bool,
    stable_match: bool,
    review_note: str,
) -> dict[str, str]:
    if relation not in RELATION_CODES:
        raise ValueError(f"invalid relation code: {relation}")
    left, right = sorted((left, right), key=lambda item: (item["stable_code"], item["record_id"]))
    name_match = bool(
        left["normalized_name"] and left["normalized_name"] == right["normalized_name"]
    )
    row: dict[str, str] = {
        "batch_id": batch_id,
        "candidate_pair_id": f"ERP-20260827-{pair_number:05d}",
        "candidate_relation_code": relation,
        "candidate_relation_basis": basis,
        "comparison_dimensions": "|".join(dimensions) or "NONE",
        "source_identity_match": str(identity_match).lower(),
        "stable_code_match": str(stable_match).lower(),
        "normalized_name_match": str(name_match).lower(),
        "movement_pattern_match": str(
            bool(
                left["movement_pattern_code"]
                and left["movement_pattern_code"] == right["movement_pattern_code"]
            )
        ).lower(),
        "primary_body_area_overlap": primary_overlap,
        "secondary_body_area_overlap": secondary_overlap,
        "actual_method_evidence_level": method_level,
        "equipment_comparison": (
            "SAME"
            if left["equipment_codes"]
            and right["equipment_codes"]
            and set(left["equipment_codes"]) == set(right["equipment_codes"])
            else "DIFFERENT"
            if left["equipment_codes"] and right["equipment_codes"]
            else "UNKNOWN"
        ),
        "posture_grip_stance_rom_evidence": evidence,
        "existing_alternative_relation_reference": str(bool(alternative_directions)).lower(),
        "existing_alternative_relation_direction": "|".join(sorted(alternative_directions)),
        "candidate_confidence_code": confidence,
        "review_decision": "PENDING",
        "review_status_code": REVIEW_STATUS,
        "review_note": review_note,
        "production_eligible": PRODUCTION_ELIGIBLE,
    }
    row.update(record_fields("left", left))
    row.update(record_fields("right", right))
    return {field: row.get(field, "") for field in CSV_FIELDS}


def classify_alias_pair(
    alias: dict[str, Any], target: dict[str, Any]
) -> tuple[str, str, list[str], str, str, str, str, str]:
    alias["movement_pattern_code"] = target["movement_pattern_code"]
    dimensions, evidence = dimension_evidence(alias, target)
    name_match = bool(
        alias["normalized_name"] and alias["normalized_name"] == target["normalized_name"]
    )
    core_similarity = overlap(alias["core_name_tokens"], target["core_name_tokens"])
    primary_overlap = overlap_code(
        overlap(alias["primary_body_area_codes"], target["primary_body_area_codes"])
    )
    secondary_overlap = overlap_code(
        overlap(alias["secondary_body_area_codes"], target["secondary_body_area_codes"])
    )

    if name_match and not dimensions:
        return (
            "SAME_EXERCISE",
            "SAME_STABLE_CODE_AND_NORMALIZED_NAME_WITHOUT_METHOD_DIMENSION_CONFLICT",
            dimensions,
            evidence,
            primary_overlap,
            secondary_overlap,
            "HIGH",
            "ALIAS_NAME_AND_STABLE_CODE_IDENTITY",
        )
    if core_similarity >= 0.75 and dimensions:
        if set(dimensions).issubset({"GRIP", "STANCE", "ROM"}):
            return (
                "SECONDARY_VARIANT",
                "SAME_STABLE_CODE_AND_METHOD_CORE_WITH_GRIP_STANCE_OR_ROM_DIFFERENCE",
                dimensions,
                evidence,
                primary_overlap,
                secondary_overlap,
                "MEDIUM",
                "ALIAS_NAME_METHOD_PROXY",
            )
        if "ACTUAL_METHOD" not in dimensions or core_similarity >= 0.75:
            return (
                "PRIMARY_VARIANT",
                "SAME_STABLE_CODE_AND_METHOD_CORE_WITH_EQUIPMENT_OR_POSTURE_DIFFERENCE",
                dimensions,
                evidence,
                primary_overlap,
                secondary_overlap,
                "MEDIUM",
                "ALIAS_NAME_METHOD_PROXY",
            )
    return (
        "REVIEW_REQUIRED",
        "SAME_STABLE_CODE_BUT_ALIAS_METHOD_OR_TAXONOMY_EVIDENCE_CONFLICTS",
        dimensions,
        evidence,
        primary_overlap,
        secondary_overlap,
        "LOW",
        "ALIAS_NAME_OR_SOURCE_METHOD_REVIEW_REQUIRED",
    )


def candidate_pool(
    canonical: list[dict[str, Any]], alternative_refs: dict[tuple[str, str], list[str]]
) -> list[tuple[dict[str, Any], dict[str, Any], list[str]]]:
    candidates: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
    for index, left in enumerate(canonical):
        for right in canonical[index + 1 :]:
            key = tuple(sorted((left["stable_code"], right["stable_code"])))
            directions = alternative_refs.get(key, [])
            same_pattern = bool(
                left["movement_pattern_code"]
                and left["movement_pattern_code"] == right["movement_pattern_code"]
            )
            same_primary = (
                overlap(left["primary_body_area_codes"], right["primary_body_area_codes"]) > 0
            )
            same_secondary = (
                overlap(left["secondary_body_area_codes"], right["secondary_body_area_codes"]) > 0
            )
            core_similarity = overlap(left["core_name_tokens"], right["core_name_tokens"])
            if (
                directions
                or (same_pattern and same_primary)
                or (same_pattern and same_secondary and core_similarity >= 0.25)
                or core_similarity >= 0.5
            ):
                candidates.append((left, right, directions))
    return candidates


def build(
    input_path: Path,
    alternatives_path: Path,
    profile_dir: Path,
    batch_dir: Path,
    batch_id: str,
) -> dict[str, Any]:
    source_rows = read_csv(input_path)
    canonical_rows, alias_rows = validate_input(source_rows)
    canonical_by_stable = {row["stable_code"]: row for row in canonical_rows}
    alternative_rows = read_jsonl(alternatives_path)
    alternative_refs, unmapped_alternatives = alternative_reference(
        alternative_rows, canonical_by_stable
    )

    canonical = [compact_record(row, "EXERCISE") for row in canonical_rows]
    aliases = [compact_record(row, "V1_ALIAS") for row in alias_rows]
    canonical_by_stable_compact = {row["stable_code"]: row for row in canonical}
    batch_rows: list[dict[str, str]] = []
    pair_number = 1

    for alias in aliases:
        target = canonical_by_stable_compact[alias["stable_code"]]
        (
            relation,
            basis,
            dimensions,
            evidence,
            primary_overlap,
            secondary_overlap,
            confidence,
            method_level,
        ) = classify_alias_pair(alias, target)
        batch_rows.append(
            make_row(
                batch_id,
                pair_number,
                alias,
                target,
                relation,
                basis,
                ["SOURCE_IDENTITY", "STABLE_CODE", *dimensions],
                evidence,
                primary_overlap,
                secondary_overlap,
                confidence,
                [],
                method_level=method_level,
                identity_match=False,
                stable_match=True,
                review_note=(
                    "기존 V1_ALIAS가 동일 stable_code를 가리키지만 원천명·장비·실제 수행 차이를 "
                    "함께 "
                    "비교한 관계 후보. 사람 검토 전 병합·삭제·stable code 변경을 하지 않는다."
                ),
            )
        )
        pair_number += 1

    canonical_candidates = candidate_pool(canonical, alternative_refs)
    for left, right, directions in canonical_candidates:
        relation, basis, dimensions, evidence, primary, secondary, confidence = (
            classify_canonical_pair(left, right, directions)
        )
        batch_rows.append(
            make_row(
                batch_id,
                pair_number,
                left,
                right,
                relation,
                basis,
                dimensions,
                evidence,
                primary,
                secondary,
                confidence,
                directions,
                method_level="PARTIAL_NAME_AND_TAXONOMY_PROXY",
                identity_match=left["source_identity"] == right["source_identity"],
                stable_match=left["stable_code"] == right["stable_code"],
                review_note=(
                    "후보 관계만 생성함. 통합 CSV에는 원천 수행 단계·자세 영상의 구조화 증거가 "
                    "없어 "
                    "실제 수행 방법, 자세·그립·스탠스·ROM을 사람이 확인해야 한다. "
                    "기존 Alternative 참고값은 중복 판정의 보조 근거이며 수정하지 않는다."
                ),
            )
        )
        pair_number += 1

    relation_order = {
        "SAME_EXERCISE": 0,
        "PRIMARY_VARIANT": 1,
        "SECONDARY_VARIANT": 2,
        "SEPARATE_EXERCISE": 3,
        "EXCLUDED": 4,
        "REVIEW_REQUIRED": 5,
    }
    batch_rows.sort(
        key=lambda row: (
            relation_order[row["candidate_relation_code"]],
            row["left_stable_code"],
            row["right_stable_code"],
            row["candidate_pair_id"],
        )
    )
    for index, row in enumerate(batch_rows, 1):
        row["candidate_pair_id"] = f"ERP-20260827-{index:05d}"

    profile_dir.mkdir(parents=True, exist_ok=True)
    batch_dir.mkdir(parents=True, exist_ok=True)
    csv_path = batch_dir / "review_batch.csv"
    jsonl_path = batch_dir / "review_batch.jsonl"
    profile_path = profile_dir / "profile.json"
    manifest_path = batch_dir / "review_manifest.json"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(batch_rows)
    with jsonl_path.open("w", encoding="utf-8", newline="") as handle:
        for row in batch_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    relation_counts = Counter(row["candidate_relation_code"] for row in batch_rows)
    canonical_relation_counts = Counter(
        row["candidate_relation_code"]
        for row in batch_rows
        if row["left_record_type"] == "EXERCISE" and row["right_record_type"] == "EXERCISE"
    )
    profile = {
        "profile_version": "exercise-relationship-profile-v2.0.2-v0.1.0",
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "source_of_truth": {
            "path": str(input_path.relative_to(ROOT.parent)),
            "sha256": sha256_file(input_path),
            "catalog_version_code": "exercise-catalog-v2.0.2-draft",
            "record_count": len(source_rows),
            "canonical_exercise_count": len(canonical_rows),
            "v1_alias_record_count": len(alias_rows),
            "v1_v2_reintegration_performed": False,
        },
        "reference_only_inputs": {
            "existing_alternatives_path": str(alternatives_path.relative_to(ROOT.parent))
            if alternatives_path.exists()
            else str(alternatives_path),
            "existing_alternatives_sha256": sha256_file(alternatives_path)
            if alternatives_path.exists()
            else None,
            "existing_alternative_record_count": len(alternative_rows),
            "unmapped_alternative_reference_count": unmapped_alternatives,
            "existing_alternatives_modified": False,
        },
        "comparison_policy": {
            "dimensions": [
                "source_identity",
                "existing_stable_code",
                "movement_pattern",
                "primary_body_area",
                "secondary_body_area",
                "actual_method",
                "equipment",
                "posture",
                "grip",
                "stance",
                "range_of_motion",
                "normalized_name",
            ],
            "canonical_pair_selection": [
                "existing alternative reference",
                "same movement pattern + primary/secondary body-area overlap",
                "normalized-name/core-token proximity",
            ],
            "actual_method_evidence_limit": (
                "combined catalog exposes names and generic cues; "
                "source execution steps/video review remains human work"
            ),
            "ambiguous_pair_handling": (
                "candidate_relation_code may be REVIEW_REQUIRED; "
                "every row remains PENDING human review"
            ),
            "stable_code_policy": "preserve existing codes; do not issue, rename, merge, or delete",
        },
        "summary": {
            "total_combined_records": len(source_rows),
            "total_exercise_count": len(canonical_rows),
            "v1_alias_count": len(alias_rows),
            "candidate_pair_count": len(batch_rows),
            "same_exercise_candidate_count": relation_counts["SAME_EXERCISE"],
            "variant_candidate_count": relation_counts["PRIMARY_VARIANT"]
            + relation_counts["SECONDARY_VARIANT"],
            "primary_variant_candidate_count": relation_counts["PRIMARY_VARIANT"],
            "secondary_variant_candidate_count": relation_counts["SECONDARY_VARIANT"],
            "separate_exercise_candidate_count": relation_counts["SEPARATE_EXERCISE"],
            "excluded_candidate_count": relation_counts["EXCLUDED"],
            "review_required_candidate_count": relation_counts["REVIEW_REQUIRED"],
            "canonical_pair_count": len(canonical_candidates),
            "canonical_pair_relation_counts": dict(sorted(canonical_relation_counts.items())),
            "auto_finalized_count": 0,
            "pending_human_review_count": len(batch_rows),
        },
        "quality_checks": {
            "stable_code_unique_in_canonical_input": len({row["stable_code"] for row in canonical})
            == len(canonical),
            "canonical_source_identity_unique": len(
                {(row["source_track"], row["source_identity"]) for row in canonical}
            )
            == len(canonical),
            "all_relation_codes_allowed": all(
                row["candidate_relation_code"] in RELATION_CODES for row in batch_rows
            ),
            "all_rows_pending": all(row["review_decision"] == "PENDING" for row in batch_rows),
            "all_rows_non_production": all(
                row["production_eligible"] == "false" for row in batch_rows
            ),
            "alias_pairs_preserve_stable_code": all(
                row["stable_code_match"] == "true"
                for row in batch_rows
                if row["candidate_relation_code"] == "SAME_EXERCISE"
            ),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "schema_version": "exercise-relationship-review-v0.1.0",
        "review_batch_version": "exercise-catalog-v2.0.2-relationship-review-v0.1.0",
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "source": profile["source_of_truth"],
        "summary": profile["summary"],
        "files": [
            {
                "path": "review_batch.csv",
                "records": len(batch_rows),
                "sha256": sha256_file(csv_path),
            },
            {
                "path": "review_batch.jsonl",
                "records": len(batch_rows),
                "sha256": sha256_file(jsonl_path),
            },
        ],
        "profile": {
            "path": str(profile_path.relative_to(ROOT.parent)),
            "sha256": sha256_file(profile_path),
        },
        "selection": {
            "alias_pairs": (
                "one V1_ALIAS to its existing canonical stable_code with "
                "name/method-proxy comparison; alias-alias cartesian pairs omitted"
            ),
            "canonical_pairs": "pairwise candidate generation on 102 EXERCISE rows",
            "decision_policy": "no automatic merge or final relationship decision",
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--alternatives", type=Path, default=DEFAULT_ALTERNATIVES)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--batch-id", default="exercise-catalog-v2.0.2-relationship-review-v0.1.0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = build(args.input, args.alternatives, args.profile_dir, args.batch_dir, args.batch_id)
    print(json.dumps(profile["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
