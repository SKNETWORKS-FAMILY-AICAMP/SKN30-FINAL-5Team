"""Align KSPO and wger review rows to the Gym Visual candidate vocabulary.

The source-specific CSV files remain immutable inputs.  This module creates a
review-only projection with the same column names and machine values used by
the Gym Visual review batches.  Missing or ambiguous source evidence is never
guessed; it is represented by ``REVIEW_REQUIRED``.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WGER_INVENTORY = (
    REPO_ROOT
    / "data/validation/profiles/20260810T063833Z-wger-exercise-catalog-profile-v0.1.0/gym_candidate_inventory.jsonl"
)
DEFAULT_KSPO_INVENTORY = (
    REPO_ROOT
    / "data/validation/profiles/20260810T053458Z-training-video-profile-v0.2.0/candidate_inventory.jsonl"
)
DEFAULT_WGER_REVIEW = REPO_ROOT / "data/validation/review_results/wger_mapping_results.csv"
DEFAULT_KSPO_REVIEW = REPO_ROOT / "data/validation/review_results/kspo_mapping_results.csv"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data/validation/review_batches/gymvisual-source-alignment-v0.4.0"
DEFAULT_PROFILE = REPO_ROOT / "data/validation/profiles/gymvisual_source_alignment-v0.4.0.json"
ALIGNMENT_VERSION = "gymvisual-source-alignment-v0.4.0"

# These columns intentionally mirror the common candidate concepts in the
# Gym Visual strength/cardio/mobility review batches.
COMMON_COLUMNS = [
    "source_track",
    "source_identity",
    "candidate_id",
    "source_name",
    "source_display_name_ko",
    "source_body_part",
    "source_category",
    "source_location",
    "source_scope_status",
    "source_target",
    "source_equipment",
    "source_media_reference",
    "source_media_id",
    "source_image",
    "source_gif_url",
    "target",
    "mobility_goal_code",
    "body_area_codes_candidate",
    "movement_pattern_candidate",
    "movement_pattern_code_candidate",
    "exercise_family_candidate",
    "variant_group_candidate",
    "equipment_code_candidate",
    "equipment_label_candidate",
    "location_code_candidates",
    "training_type_code_candidate",
    "difficulty_code_candidate",
    "beginner_suitability_candidate",
    "impact_level_candidate",
    "exercise_mode_candidates",
    "space_noise_level_candidate",
    "intensity_level_candidate",
    "met_value",
    "load_profile_candidate",
    "screening_decision",
    "screening_reason_code",
    "screening_reason",
    "selection_rank",
    "selection_recommendation",
    "review_required",
    "review_required_codes",
    "alternative_relation_status",
    "visual_reference_status",
    "review_decision",
    "review_reason_code",
    "review_note",
    "review_family_code",
    "review_variant_group",
    "reviewer",
    "reviewed_at",
    "review_normalized_exercise_id",
    "alignment_required_codes",
    "alignment_status",
    "review_status",
    "production_eligible",
    "source_license",
    "source_license_author",
]

GYMVISUAL_TARGETS = {
    "lats",
    "upper back",
    "spine",
    "traps",
    "pectorals",
    "forearms",
    "calves",
    "delts",
    "biceps",
    "triceps",
    "glutes",
    "hamstrings",
    "quads",
    "abs",
    "REVIEW_REQUIRED",
}
GYMVISUAL_MOVEMENTS = {
    "GAIT",
    "HIP_DOMINANT",
    "KNEE_DOMINANT",
    "KNEE_FLEXION",
    "HORIZONTAL_PUSH",
    "HORIZONTAL_PULL",
    "VERTICAL_PUSH",
    "VERTICAL_PULL",
    "CORE_BRACE",
    "ISOLATION",
    "MOBILITY_STRETCH",
    "REVIEW_REQUIRED",
}
GYMVISUAL_EQUIPMENT = {
    "BODYWEIGHT",
    "BARBELL",
    "CABLE_MACHINE",
    "DUMBBELL",
    "RESISTANCE_BAND",
    "KETTLEBELL",
    "MAT",
    "BENCH",
    "CHAIR",
    "MACHINE",
    "ROPE",
    "STABILITY_BALL",
    "MEDICINE_BALL",
    "FOAM_ROLLER",
    "SUSPENSION_STRAPS",
    "STEP_BOX",
    "REVIEW_REQUIRED",
}
GYMVISUAL_LOCATIONS = {"HOME", "GYM", "OUTDOOR", "REVIEW_REQUIRED"}
GYMVISUAL_DIFFICULTIES = {"BEGINNER", "INTERMEDIATE", "ADVANCED", "REVIEW_REQUIRED"}
GYMVISUAL_BEGINNER_VALUES = {"SUITABLE", "CONDITIONAL", "NOT_PRIORITY", "REVIEW_REQUIRED"}
GYMVISUAL_TRAINING_TYPES = {"STRENGTH", "CARDIO", "MOBILITY", "REVIEW_REQUIRED"}


def canonical(value: object) -> str:
    return str(value or "").strip()


def split_values(value: object) -> list[str]:
    text = canonical(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*[|,]\s*", text) if part.strip()]


def joined(values: Iterable[str]) -> str:
    return "|".join(dict.fromkeys(value for value in values if value))


def first_code(value: object, allowed: set[str]) -> str:
    for part in split_values(value):
        upper = part.upper()
        if upper in allowed and upper != "REVIEW_REQUIRED":
            return upper
    return "REVIEW_REQUIRED"


def map_target(value: object) -> str:
    text = canonical(value).lower()
    rules = (
        ("latissimus", "lats"),
        ("lats", "lats"),
        ("upper back", "upper back"),
        ("trapezius", "traps"),
        ("traps", "traps"),
        ("pector", "pectorals"),
        ("chest", "pectorals"),
        ("forearm", "forearms"),
        ("wrist", "forearms"),
        ("calf", "calves"),
        ("gastrocnemius", "calves"),
        ("soleus", "calves"),
        ("deltoid", "delts"),
        ("shoulder", "delts"),
        ("biceps", "biceps"),
        ("brachialis", "biceps"),
        ("triceps", "triceps"),
        ("glute", "glutes"),
        ("quadriceps", "quads"),
        ("quads", "quads"),
        ("hamstring", "hamstrings"),
        ("biceps femoris", "hamstrings"),
        ("abdomen", "abs"),
        ("rectus abdominis", "abs"),
        ("abs", "abs"),
        ("spine", "spine"),
        ("lower back", "spine"),
        ("등", "upper back"),
        ("광배", "lats"),
        ("승모", "traps"),
        ("가슴", "pectorals"),
        ("전완", "forearms"),
        ("손목", "forearms"),
        ("종아리", "calves"),
        ("어깨", "delts"),
        ("이두", "biceps"),
        ("상완이두", "biceps"),
        ("삼두", "triceps"),
        ("상완삼두", "triceps"),
        ("둔근", "glutes"),
        ("엉덩", "glutes"),
        ("대퇴사두", "quads"),
        ("허벅지 앞", "quads"),
        ("햄스트링", "hamstrings"),
        ("허벅지 뒤", "hamstrings"),
        ("복부", "abs"),
        ("배", "abs"),
        ("허리", "spine"),
        ("목", "spine"),
    )
    for token, target in rules:
        if token in text:
            return target
    return "REVIEW_REQUIRED"


def map_equipment(value: object) -> str:
    text = canonical(value).lower()
    rules = (
        ("ez bar", "EZ_BAR"),
        ("sz-bar", "EZ_BAR"),
        ("body weight", "BODYWEIGHT"),
        ("bodyweight", "BODYWEIGHT"),
        ("맨몸", "BODYWEIGHT"),
        ("barbell", "BARBELL"),
        ("바벨", "BARBELL"),
        ("cable", "CABLE_MACHINE"),
        ("케이블", "CABLE_MACHINE"),
        ("dumbbell", "DUMBBELL"),
        ("덤벨", "DUMBBELL"),
        ("band", "RESISTANCE_BAND"),
        ("elastic", "RESISTANCE_BAND"),
        ("밴드", "RESISTANCE_BAND"),
        ("kettlebell", "KETTLEBELL"),
        ("케틀벨", "KETTLEBELL"),
        ("mat", "MAT"),
        ("매트", "MAT"),
        ("bench", "BENCH"),
        ("벤치", "BENCH"),
        ("chair", "CHAIR"),
        ("의자", "CHAIR"),
        ("machine", "MACHINE"),
        ("머신", "MACHINE"),
        ("rope", "ROPE"),
        ("줄넘기", "ROPE"),
        ("stability ball", "STABILITY_BALL"),
        ("swiss ball", "STABILITY_BALL"),
        ("짐볼", "STABILITY_BALL"),
        ("medicine ball", "MEDICINE_BALL"),
        ("메디신볼", "MEDICINE_BALL"),
        ("roller", "FOAM_ROLLER"),
        ("폼롤러", "FOAM_ROLLER"),
        ("strap", "SUSPENSION_STRAPS"),
        ("suspension", "SUSPENSION_STRAPS"),
        ("스트랩", "SUSPENSION_STRAPS"),
        ("step box", "STEP_BOX"),
        ("stepbox", "STEP_BOX"),
        ("스텝박스", "STEP_BOX"),
        ("rope", "ROPE"),
        ("수건", "ROPE"),
        ("stationary bike", "MACHINE"),
        ("elliptical", "MACHINE"),
        ("stepmill", "MACHINE"),
        ("treadmill", "MACHINE"),
        ("leverage machine", "MACHINE"),
        ("smith machine", "MACHINE"),
        ("weighted", "HOUSEHOLD_WEIGHT"),
    )
    for token, code in rules:
        if token in text:
            return code
    return "REVIEW_REQUIRED"


def map_locations(value: object) -> str:
    text = canonical(value).lower()
    values: list[str] = []
    if any(token in text for token in ("home", "indoor", "실내", "가정", "집", "홈")):
        values.append("HOME")
    if any(token in text for token in ("gym", "fitness", "헬스", "체육관")):
        values.append("GYM")
    if any(token in text for token in ("outdoor", "야외", "공원")):
        values.append("OUTDOOR")
    return joined(values) or "REVIEW_REQUIRED"


def map_beginner(value: object) -> str:
    text = canonical(value).upper()
    if text in {"YES", "SUITABLE", "적합"}:
        return "SUITABLE"
    if text in {"CONDITIONAL", "조건부"}:
        return "CONDITIONAL"
    if text in {"NO", "NOT_PRIORITY", "부적합"}:
        return "NOT_PRIORITY"
    return "REVIEW_REQUIRED"


def map_movement(value: object) -> str:
    code = first_code(value, GYMVISUAL_MOVEMENTS)
    return code


def map_training_type(movement: str, source_track: str) -> str:
    if movement == "MOBILITY_STRETCH":
        return "MOBILITY"
    if movement == "GAIT":
        return "CARDIO"
    if source_track == "wger":
        return "STRENGTH"
    return "REVIEW_REQUIRED"


def equipment_label(code: str, source_value: object) -> str:
    labels = {
        "BODYWEIGHT": "맨몸",
        "BARBELL": "바벨",
        "CABLE_MACHINE": "케이블 머신",
        "DUMBBELL": "덤벨",
        "RESISTANCE_BAND": "저항 밴드",
        "KETTLEBELL": "케틀벨",
        "MAT": "매트",
        "BENCH": "벤치",
        "CHAIR": "의자",
        "MACHINE": "머신",
        "ROPE": "줄넘기",
        "STABILITY_BALL": "짐볼",
    }
    return labels.get(code, canonical(source_value) or "REVIEW_REQUIRED")


def decision_code(value: object) -> str:
    decision = canonical(value).upper()
    if decision in {"INCLUDE", "MERGE"}:
        return "INCLUDE"
    if decision == "EXCLUDE":
        return "EXCLUDE"
    return "HOLD"


def alignment_status(row: dict[str, str]) -> tuple[str, str]:
    checks = {
        "TARGET_MAPPING_REVIEW_REQUIRED": row["target"] == "REVIEW_REQUIRED",
        "MOVEMENT_PATTERN_REVIEW_REQUIRED": row["movement_pattern_code_candidate"]
        == "REVIEW_REQUIRED",
        "EQUIPMENT_MAPPING_REVIEW_REQUIRED": row["equipment_code_candidate"] == "REVIEW_REQUIRED",
        "LOCATION_MAPPING_REVIEW_REQUIRED": row["location_code_candidates"] == "REVIEW_REQUIRED",
        "DIFFICULTY_REVIEW_REQUIRED": row["difficulty_code_candidate"] == "REVIEW_REQUIRED",
        "EXERCISE_FAMILY_REVIEW_REQUIRED": row["exercise_family_candidate"] == "REVIEW_REQUIRED",
        "VARIANT_GROUP_REVIEW_REQUIRED": row["variant_group_candidate"] == "REVIEW_REQUIRED",
    }
    required = [code for code, missing in checks.items() if missing]
    return ("ALIGNED" if not required else "REVIEW_REQUIRED", "|".join(required))


def _base_row(
    *,
    track: str,
    identity: str,
    name: str,
    category: str,
    location_source: str,
    scope_source: str,
    target_source: str,
    equipment_source: str,
    media: str,
    beginner: str,
    movement: str,
    equipment: str,
    locations: str,
    training: str,
    source_license: str,
    author: str,
    raw: dict[str, str],
) -> dict[str, str]:
    row = {column: "" for column in COMMON_COLUMNS}
    row.update(
        {
            "source_track": track,
            "candidate_id": identity,
            "source_identity": identity,
            "source_name": name,
            "source_display_name_ko": raw.get("review_display_name_ko", ""),
            "source_body_part": category.lower(),
            "source_category": category.lower(),
            "source_location": location_source,
            "source_scope_status": scope_source,
            "source_target": target_source,
            "source_equipment": equipment_source,
            "source_media_reference": media,
            "source_media_id": identity,
            "source_image": "",
            "source_gif_url": "",
            "target": map_target(target_source),
            "mobility_goal_code": "REVIEW_REQUIRED",
            "body_area_codes_candidate": "REVIEW_REQUIRED",
            "movement_pattern_candidate": movement,
            "movement_pattern_code_candidate": movement,
            "exercise_family_candidate": "REVIEW_REQUIRED",
            "variant_group_candidate": "REVIEW_REQUIRED",
            "equipment_code_candidate": equipment,
            "equipment_label_candidate": equipment_label(equipment, equipment_source),
            "location_code_candidates": locations,
            "training_type_code_candidate": training,
            "difficulty_code_candidate": "REVIEW_REQUIRED",
            "beginner_suitability_candidate": beginner,
            "impact_level_candidate": "REVIEW_REQUIRED",
            "exercise_mode_candidates": "REVIEW_REQUIRED",
            "space_noise_level_candidate": "REVIEW_REQUIRED",
            "intensity_level_candidate": "REVIEW_REQUIRED",
            "met_value": "",
            "load_profile_candidate": "REVIEW_REQUIRED",
            "screening_decision": decision_code(raw.get("review_decision")),
            "screening_reason_code": canonical(raw.get("selection_reason_codes"))
            or "SOURCE_REVIEW_RESULT",
            "screening_reason": "REVIEW_REQUIRED",
            "selection_rank": "",
            "selection_recommendation": "REVIEW_REQUIRED",
            "review_required": "true",
            "review_decision": canonical(raw.get("review_decision")),
            "alternative_relation_status": "NOT_CREATED_BY_DESIGN",
            "visual_reference_status": "REVIEW_REQUIRED",
            "review_reason_code": "",
            "review_note": canonical(raw.get("reviewer_notes")),
            "review_family_code": "",
            "review_variant_group": "",
            "reviewer": "",
            "reviewed_at": "",
            "review_normalized_exercise_id": canonical(raw.get("review_normalized_exercise_id")),
            "review_required_codes": canonical(raw.get("required_review_codes")),
            "review_status": canonical(raw.get("review_status")) or "DRAFT",
            "production_eligible": "false",
            "source_license": source_license,
            "source_license_author": author,
        }
    )
    status, required = alignment_status(row)
    row["alignment_status"] = status
    row["alignment_required_codes"] = required
    return row


def align_wger(raw: dict[str, str]) -> dict[str, str]:
    movement = map_movement(raw.get("review_taxonomy_code"))
    return _base_row(
        track="wger",
        identity=canonical(raw.get("source_exercise_id")),
        name=canonical(raw.get("primary_source_name_en")),
        category=canonical(raw.get("source_category_name")),
        location_source="",
        scope_source="GYM_CANDIDATE",
        target_source=canonical(raw.get("source_primary_muscle_names")),
        equipment_source=canonical(raw.get("source_equipment_names")),
        media=f"image:{canonical(raw.get('source_image_reference_count'))};video:{canonical(raw.get('source_video_reference_count'))}",
        beginner=map_beginner(raw.get("review_beginner_suitability")),
        movement=movement,
        equipment=map_equipment(raw.get("source_equipment_names")),
        locations=map_locations(""),
        training=map_training_type(movement, "wger"),
        source_license=canonical(raw.get("source_base_license")),
        author=canonical(raw.get("source_license_author")),
        raw=raw,
    )


def align_kspo(raw: dict[str, str]) -> dict[str, str]:
    movement = map_movement(raw.get("review_taxonomy_code"))
    return _base_row(
        track="kspo",
        identity=canonical(raw.get("source_candidate_id")),
        name=canonical(raw.get("source_training_name")),
        category="training_video",
        location_source=canonical(raw.get("places")),
        scope_source=canonical(raw.get("review_bucket")),
        target_source=canonical(raw.get("muscle_parts")),
        equipment_source=canonical(raw.get("tools")),
        media=f"file:{canonical(raw.get('source_file_name'))};frames:{canonical(raw.get('source_frame_rows'))}",
        beginner=map_beginner(raw.get("review_beginner_suitability")),
        movement=movement,
        equipment=map_equipment(raw.get("tools")),
        locations=map_locations(raw.get("places")),
        training=map_training_type(movement, "kspo"),
        source_license="KOGL_TYPE_1",
        author="",
        raw=raw,
    )


def align_rows(
    wger_rows: Iterable[dict[str, str]], kspo_rows: Iterable[dict[str, str]]
) -> list[dict[str, str]]:
    rows = [align_wger(row) for row in wger_rows]
    rows.extend(align_kspo(row) for row in kspo_rows)
    rows.sort(key=lambda row: (row["source_track"], row["source_identity"]))
    identities = [(row["source_track"], row["source_identity"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("source_track + source_identity 중복이 있습니다.")
    return rows


def validate_rows(rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    materialized = list(rows)
    errors: list[str] = []
    for index, row in enumerate(materialized, start=1):
        if set(row) != set(COMMON_COLUMNS):
            errors.append(f"row {index}: common column set mismatch")
        if row.get("target") not in GYMVISUAL_TARGETS:
            errors.append(f"row {index}: invalid target")
        if row.get("movement_pattern_code_candidate") not in GYMVISUAL_MOVEMENTS:
            errors.append(f"row {index}: invalid movement pattern")
        if row.get("equipment_code_candidate") not in GYMVISUAL_EQUIPMENT:
            errors.append(f"row {index}: invalid equipment")
        if any(
            value not in GYMVISUAL_LOCATIONS
            for value in split_values(row.get("location_code_candidates"))
        ):
            errors.append(f"row {index}: invalid location")
        if row.get("difficulty_code_candidate") not in GYMVISUAL_DIFFICULTIES:
            errors.append(f"row {index}: invalid difficulty")
        if row.get("beginner_suitability_candidate") not in GYMVISUAL_BEGINNER_VALUES:
            errors.append(f"row {index}: invalid beginner suitability")
        if row.get("training_type_code_candidate") not in GYMVISUAL_TRAINING_TYPES:
            errors.append(f"row {index}: invalid training type")
        if row.get("production_eligible") != "false":
            errors.append(f"row {index}: production eligibility must remain false")
    return {
        "status": "PASS" if not errors else "FAIL",
        "row_count": len(materialized),
        "errors": errors,
    }


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object: {path}")
            rows.append(value)
    return rows


def _names(values: object, field: str = "name") -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            text = canonical(value.get(field))
        else:
            text = canonical(value)
        if text:
            result.append(text)
    return result


def _review_index(rows: Iterable[dict[str, str]], identity_field: str) -> dict[str, dict[str, str]]:
    return {
        canonical(row.get(identity_field)): row
        for row in rows
        if canonical(row.get(identity_field))
    }


def align_wger_inventory(
    raw: dict[str, Any], review: dict[str, str] | None = None
) -> dict[str, str]:
    license_data = raw.get("source_base_license")
    license_name = license_data.get("short_name", "") if isinstance(license_data, dict) else ""
    license_author = (
        license_data.get("license_author", "") if isinstance(license_data, dict) else ""
    )
    flat = {
        "source_exercise_id": canonical(raw.get("source_exercise_id")),
        "primary_source_name_en": joined(_names(raw.get("source_names_en"))),
        "source_category_name": canonical((raw.get("source_category") or {}).get("name"))
        if isinstance(raw.get("source_category"), dict)
        else "",
        "source_primary_muscle_names": joined(_names(raw.get("source_primary_muscles"))),
        "source_equipment_names": joined(_names(raw.get("source_equipment"))),
        "source_image_reference_count": canonical(raw.get("source_image_reference_count")),
        "source_video_reference_count": canonical(raw.get("source_video_reference_count")),
        "source_base_license": license_name,
        "source_license_author": license_author,
        "required_review_codes": joined(raw.get("required_review_codes", [])),
        "review_bucket": canonical(raw.get("review_bucket")),
        "review_status": canonical(raw.get("review_status")) or "DRAFT",
        "review_decision": "PENDING",
    }
    if review:
        flat.update(review)
    return align_wger(flat)


def align_kspo_inventory(
    raw: dict[str, Any], review: dict[str, str] | None = None
) -> dict[str, str]:
    flat = {
        "source_candidate_id": canonical(raw.get("source_candidate_id")),
        "source_training_name": canonical(raw.get("source_training_name")),
        "source_file_name": canonical(raw.get("source_file_name")),
        "places": joined(raw.get("places", [])),
        "tools": joined(raw.get("tools", [])),
        "muscle_parts": joined(raw.get("muscle_parts", [])),
        "source_frame_rows": canonical(raw.get("source_frame_rows")),
        "required_review_codes": joined(raw.get("required_review_codes", [])),
        "review_bucket": canonical(raw.get("review_bucket")),
        "review_status": canonical(raw.get("review_status")) or "DRAFT",
        "review_decision": "PENDING",
    }
    if review:
        flat.update(review)
    return align_kspo(flat)


def align_inventory_rows(
    wger_inventory: Iterable[dict[str, Any]],
    kspo_inventory: Iterable[dict[str, Any]],
    wger_reviews: Iterable[dict[str, str]] = (),
    kspo_reviews: Iterable[dict[str, str]] = (),
) -> list[dict[str, str]]:
    wger_index = _review_index(wger_reviews, "source_exercise_id")
    kspo_index = _review_index(kspo_reviews, "source_candidate_id")
    rows = [
        align_wger_inventory(raw, wger_index.get(canonical(raw.get("source_exercise_id"))))
        for raw in wger_inventory
    ]
    rows.extend(
        align_kspo_inventory(raw, kspo_index.get(canonical(raw.get("source_candidate_id"))))
        for raw in kspo_inventory
    )
    rows.sort(key=lambda row: (row["source_track"], row["source_identity"]))
    identities = [(row["source_track"], row["source_identity"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("source_track + source_identity 중복이 있습니다.")
    return rows


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def write_outputs(
    rows: list[dict[str, str]], *, output_root: Path, profile_path: Path, inputs: list[Path]
) -> dict[str, Any]:
    validation = validate_rows(rows)
    if validation["status"] != "PASS":
        raise ValueError(json.dumps(validation, ensure_ascii=False))
    output_root = output_root.resolve()
    profile_path = profile_path.resolve()
    if output_root.exists() or profile_path.exists():
        raise FileExistsError("기존 정렬 산출물을 덮어쓰지 않기 위해 새 출력 경로가 필요합니다.")
    output_root.mkdir(parents=True)
    csv_path = output_root / "aligned_review_batch.csv"
    jsonl_path = output_root / "aligned_review_batch.jsonl"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "alignment_version": ALIGNMENT_VERSION,
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "inputs": [{"path": manifest_path(path), "sha256": sha256_file(path)} for path in inputs],
        "outputs": {
            "csv": {"path": manifest_path(csv_path), "sha256": sha256_file(csv_path)},
            "jsonl": {"path": manifest_path(jsonl_path), "sha256": sha256_file(jsonl_path)},
        },
        "validation": validation,
        "value_policy": {
            "reference": "Gym Visual review batch candidate vocabulary",
            "unknown_value": "REVIEW_REQUIRED",
            "raw_inputs_unchanged": True,
            "generated_catalog_created": False,
        },
        "source_track_counts": {
            track: sum(row["source_track"] == track for row in rows) for track in ("kspo", "wger")
        },
    }
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wger-input", type=Path, default=DEFAULT_WGER_INVENTORY)
    parser.add_argument("--kspo-input", type=Path, default=DEFAULT_KSPO_INVENTORY)
    parser.add_argument("--wger-review-input", type=Path, default=DEFAULT_WGER_REVIEW)
    parser.add_argument("--kspo-review-input", type=Path, default=DEFAULT_KSPO_REVIEW)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = align_inventory_rows(
        load_jsonl(args.wger_input),
        load_jsonl(args.kspo_input),
        load_csv(args.wger_review_input),
        load_csv(args.kspo_review_input),
    )
    manifest = write_outputs(
        rows,
        output_root=args.output_root,
        profile_path=args.profile,
        inputs=[args.wger_input, args.kspo_input, args.wger_review_input, args.kspo_review_input],
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
