# ruff: noqa: E501

"""Build the Gym Visual exercise-family/variant human-review batch.

This is a catalog-boundary step.  It reads the immutable Gym Visual snapshot and
the strength representative profile, then emits candidate variant edges only.
It never edits raw data, normalizes an exercise, creates an alternative edge, or
changes an existing catalog, safety-rule, or alternative artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data/raw/gym_visual"
DEFAULT_PROFILE = REPO_ROOT / "data/validation/profiles/gymvisual_strength_profile.json"
DEFAULT_REVIEW_BATCH = REPO_ROOT / "data/validation/review_batches/gymvisual_variant_review.csv"
DEFAULT_REVIEWED = REPO_ROOT / "data/validation/review_results/gymvisual_variant_reviewed.csv"

VARIANT_PROFILE_VERSION = "gymvisual-variant-profile-v0.2.0"
REVIEW_BATCH_VERSION = "gymvisual-variant-review-v0.2.0"
MAX_VARIANTS_PER_REPRESENTATIVE = 5

REVIEW_COLUMNS = [
    "representative_id",
    "representative_target",
    "representative_name",
    "exercise_family_candidate",
    "movement_pattern_candidate",
    "variant_candidate_id",
    "variant_target",
    "variant_name",
    "variant_equipment",
    "location_code_candidates",
    "variant_priority_rank",
    "home_priority",
    "beginner_tool_priority",
    "popularity_priority_proxy",
    "complexity_penalty",
    "priority_reason",
    "variant_media_id",
    "variant_image",
    "variant_gif_url",
    "same_primary_target_candidate",
    "same_movement_pattern_candidate",
    "meaningful_difference_dimensions",
    "difference_evidence",
    "auto_candidate_decision",
    "auto_candidate_reason_code",
    "auto_candidate_reason",
    "alternative_relation_status",
    "review_decision",
    "review_reason_code",
    "review_note",
    "reviewer",
    "reviewed_at",
]

# Family matching is intentionally explicit.  A broad target-only match would
# collapse different exercises into one family and would violate the catalog
# boundary being reviewed here.
FAMILY_MATCHERS: dict[str, tuple[str, ...]] = {
    "LAT_PULLDOWN_CANDIDATE": ("pulldown", "pull down"),
    "BARBELL_PULLOVER_CANDIDATE": ("pullover",),
    "INVERTED_ROW_CANDIDATE": ("inverted row",),
    "SEATED_CABLE_ROW_CANDIDATE": ("cable", "row"),
    "INCLINE_Y_RAISE_CANDIDATE": ("y-raise", "y raise"),
    "BODYWEIGHT_BACK_EXTENSION_CANDIDATE": ("hyperextension", "back extension"),
    "LOWER_BACK_CURL_CANDIDATE": ("lower back curl",),
    "DUMBBELL_SHRUG_CANDIDATE": ("shrug",),
    "SCAPULAR_PULL_UP_CANDIDATE": ("scapular pull-up", "scapular pull up"),
    "CABLE_FLY_CANDIDATE": ("cable", "fly"),
    "PUSH_UP_CANDIDATE": ("push-up", "push up"),
    "WRIST_CURL_CANDIDATE": ("wrist curl",),
    "REVERSE_WRIST_CURL_CANDIDATE": ("reverse wrist curl", "revers wrist curl"),
    "HAND_GRIP_SQUEEZE_CANDIDATE": ("hand squeeze", "gripper"),
    "SEATED_CALF_RAISE_CANDIDATE": ("seated calf",),
    "REVERSE_CALF_RAISE_CANDIDATE": ("reverse calf",),
    "BODYWEIGHT_STANDING_CALF_RAISE_CANDIDATE": ("calf raise",),
    "BARBELL_FRONT_RAISE_CANDIDATE": ("front raise",),
    "DUMBBELL_LATERAL_RAISE_CANDIDATE": ("lateral raise",),
    "DUMBBELL_REAR_FLY_CANDIDATE": ("rear fly", "rear delt fly"),
    "SEATED_SHOULDER_PRESS_CANDIDATE": ("shoulder press",),
    "BODYWEIGHT_PULL_UP_BICEPS_CANDIDATE": ("pull-up", "pull up", "chin-up", "chin up"),
    "DUMBBELL_PREACHER_CURL_CANDIDATE": ("preacher curl",),
    "DUMBBELL_STANDING_CURL_CANDIDATE": ("biceps curl", "bicep curl"),
    "OVERHEAD_TRICEPS_EXTENSION_CANDIDATE": (
        "triceps extension",
        "tricep extension",
        "french press",
    ),
    "CABLE_TRICEPS_PUSHDOWN_CANDIDATE": ("pushdown", "push down"),
    "CLOSE_GRIP_PUSH_UP_CANDIDATE": (
        "close-grip push-up",
        "close grip push-up",
        "close grip push up",
    ),
    "BARBELL_DEADLIFT_CANDIDATE": ("deadlift",),
    "BODYWEIGHT_GLUTE_BRIDGE_CANDIDATE": ("bridge", "hip thrust"),
    "BODYWEIGHT_FORWARD_LUNGE_CANDIDATE": ("lunge",),
    "BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE": (
        "straight leg deadlift",
        "stiff leg deadlift",
        "romanian deadlift",
    ),
    "SEATED_LEG_CURL_CANDIDATE": ("leg curl",),
    "MACHINE_LEG_EXTENSION_CANDIDATE": ("leg extension",),
    "DUMBBELL_GOBLET_SQUAT_CANDIDATE": ("goblet squat",),
    "BODYWEIGHT_SPLIT_SQUAT_CANDIDATE": ("split squat", "split squats"),
    "DUMBBELL_STEP_UP_LUNGE_CANDIDATE": ("step-up", "step up"),
    "BODYWEIGHT_CRUNCH_CANDIDATE": ("crunch",),
    "PLANK_ROTATION_CANDIDATE": ("plank", "twist"),
    "BODYWEIGHT_RUSSIAN_TWIST_CANDIDATE": ("russian twist",),
    "BODYWEIGHT_REVERSE_CRUNCH_CANDIDATE": ("reverse crunch",),
}

# Values are deliberately coarse.  They explain why a human should inspect a
# row; they are not approved taxonomy or safety assignments.
DIFFERENCE_MARKERS: dict[str, tuple[str, ...]] = {
    "GRIP": (
        "wide grip",
        "wide-grip",
        "close grip",
        "close-grip",
        "narrow grip",
        "narrow-grip",
        "neutral grip",
        "neutral-grip",
        "reverse grip",
        "reverse-grip",
        "underhand",
        "overhand",
        "v-bar",
        "rope",
        "parallel grip",
        "palms up",
        "palms down",
        "palm-in",
    ),
    "STANCE": (
        "sumo",
        "split",
        "single leg",
        "one leg",
        "one-arm",
        "one arm",
        "unilateral",
        "alternating",
        "alternate",
        "walking",
        "rear",
        "forward",
        "side",
    ),
    "POSTURE": (
        "seated",
        "standing",
        "lying",
        "incline",
        "decline",
        "kneeling",
        "floor",
        "bench",
        "wall",
        "on exercise ball",
        "on stability ball",
        "on bosu",
        "supported",
    ),
    "SUPPORT": (
        "assisted",
        "suspended",
        "with straps",
        "on bench",
        "on dip cage",
        "on pull-up cage",
    ),
    "RANGE_OR_EXECUTION": (
        "full range",
        "depth",
        "partial",
        "twist",
        "rotation",
        "with rotation",
        "straight arm",
    ),
}

EQUIPMENT_CODES = {
    "body weight": "BODYWEIGHT",
    "dumbbell": "DUMBBELL",
    "barbell": "BARBELL",
    "cable": "CABLE_MACHINE",
    "leverage machine": "MACHINE",
    "band": "RESISTANCE_BAND",
    "resistance band": "RESISTANCE_BAND",
    "kettlebell": "KETTLEBELL",
    "weighted": "WEIGHTED_LOAD_REVIEW_REQUIRED",
    "ez barbell": "EZ_BARBELL",
    "smith machine": "SMITH_MACHINE",
    "sled machine": "SLED_MACHINE",
    "stability ball": "STABILITY_BALL",
    "roller": "ROLLER",
    "medicine ball": "MEDICINE_BALL",
    "trap bar": "TRAP_BAR",
}

HOME_EQUIPMENT = {
    "body weight",
    "dumbbell",
    "band",
    "resistance band",
    "kettlebell",
    "stability ball",
    "roller",
    "medicine ball",
}

GYM_ONLY_EQUIPMENT = {
    "cable",
    "barbell",
    "leverage machine",
    "smith machine",
    "sled machine",
}

NON_STRENGTH_TOKENS = (
    "stretch",
    "circle",
    "pelvic tilt",
    "sphinx",
    "yoga",
)

BEGINNER_TOOL_PRIORITY = {
    "BODYWEIGHT": (0, "BODYWEIGHT"),
    "RESISTANCE_BAND": (1, "RESISTANCE_BAND"),
    "DUMBBELL": (2, "DUMBBELL"),
    "KETTLEBELL": (3, "KETTLEBELL"),
    "STABILITY_BALL": (4, "STABILITY_BALL"),
    "ROLLER": (4, "ROLLER"),
    "WEIGHTED_LOAD_REVIEW_REQUIRED": (5, "WEIGHTED_REVIEW_REQUIRED"),
    "CABLE_MACHINE": (6, "CABLE_MACHINE"),
    "MACHINE": (6, "MACHINE"),
    "BARBELL": (7, "BARBELL"),
    "EZ_BARBELL": (7, "EZ_BARBELL"),
    "SMITH_MACHINE": (7, "SMITH_MACHINE"),
    "SLED_MACHINE": (7, "SLED_MACHINE"),
}

# Gym Visual has no usage/popularity field.  This is therefore an explicit
# lexical proxy for familiar, widely taught exercise names, not a popularity
# claim or a domain approval.
POPULARITY_PROXY_TOKENS = (
    "push-up",
    "push up",
    "squat",
    "lunge",
    "crunch",
    "deadlift",
    "pulldown",
    "pull down",
    "row",
    "curl",
    "calf raise",
    "shoulder press",
    "shrug",
    "fly",
    "leg extension",
    "leg curl",
    "reverse crunch",
    "russian twist",
)

COMPLEXITY_PENALTY_TOKENS = (
    "advanced",
    "assisted",
    "clap",
    "exercise ball",
    "handstand",
    "jump",
    "kipping",
    "muscle up",
    "one arm",
    "one-arm",
    "one leg",
    "one-leg",
    "pistol",
    "plyo",
    "suspended",
    "turkish",
    "weighted",
    "windmill",
    "with straps",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("–", "-").replace("—", "-")).strip()


def equipment_code(value: str) -> str:
    return EQUIPMENT_CODES.get(value, f"UNMAPPED:{value}")


def location_candidates(source_equipment: str) -> list[str]:
    if source_equipment in HOME_EQUIPMENT:
        return ["HOME", "GYM"]
    if source_equipment in GYM_ONLY_EQUIPMENT:
        return ["GYM"]
    return ["GYM"]


def priority_details(variant: dict[str, Any]) -> dict[str, str | int]:
    equipment = equipment_code(str(variant["equipment"]))
    locations = location_candidates(str(variant["equipment"]))
    home_priority = 0 if "HOME" in locations else 1
    beginner_tool_priority, tool_label = BEGINNER_TOOL_PRIORITY.get(
        equipment,
        (8, f"UNMAPPED:{variant['equipment']}"),
    )
    normalized_name = normalize_name(str(variant["name"]))
    popularity_priority = (
        0 if any(token in normalized_name for token in POPULARITY_PROXY_TOKENS) else 1
    )
    complexity_penalty = sum(token in normalized_name for token in COMPLEXITY_PENALTY_TOKENS)
    return {
        "home_priority": home_priority,
        "beginner_tool_priority": beginner_tool_priority,
        "popularity_priority_proxy": popularity_priority,
        "complexity_penalty": complexity_penalty,
        "tool_label": tool_label,
        "priority_reason": (
            f"HOME_FIRST={home_priority}; BEGINNER_TOOL={tool_label}; "
            f"POPULARITY_PROXY={popularity_priority}; COMPLEXITY_PENALTY={complexity_penalty}"
        ),
    }


def marker_values(name: str) -> dict[str, tuple[str, ...]]:
    normalized = normalize_name(name)
    return {
        dimension: tuple(marker for marker in markers if marker in normalized)
        for dimension, markers in DIFFERENCE_MARKERS.items()
    }


def family_matches(family: str, name: str) -> bool:
    normalized = normalize_name(name)
    required = FAMILY_MATCHERS.get(family)
    if required is None:
        return False
    return all(token in normalized for token in required)


def difference_dimensions(
    representative: dict[str, Any], variant: dict[str, Any]
) -> tuple[list[str], list[str]]:
    dimensions: list[str] = []
    evidence: list[str] = []
    rep_equipment = equipment_code(str(representative["equipment"]))
    variant_equipment = equipment_code(str(variant["equipment"]))
    if rep_equipment != variant_equipment:
        dimensions.append("EQUIPMENT")
        evidence.append(f"equipment:{rep_equipment}->{variant_equipment}")

    rep_markers = marker_values(str(representative["name"]))
    variant_markers = marker_values(str(variant["name"]))
    for dimension in DIFFERENCE_MARKERS:
        # An omitted marker in the source name is unknown, not evidence that
        # the posture or grip changed.  Only an explicitly named variant
        # marker can establish a difference at this automated stage.
        if variant_markers[dimension] and rep_markers[dimension] != variant_markers[dimension]:
            dimensions.append(dimension)
            evidence.append(
                f"{dimension.lower()}:{'|'.join(rep_markers[dimension]) or '-'}"
                f"->{'|'.join(variant_markers[dimension]) or '-'}"
            )
    return dimensions, evidence


def validate_inputs(
    raw_dir: Path, profile_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    raw_path = raw_dir / "exercises.json"
    source_path = raw_dir / "source.json"
    profile = load_json(profile_path)
    source = load_json(source_path)
    records = load_json(raw_path)
    expected_hash = profile.get("source", {}).get("raw_sha256", {}).get("exercises.json")
    if expected_hash and expected_hash != sha256_file(raw_path):
        raise ValueError("Gym Visual raw snapshot hash differs from the selected profile")
    if source.get("record_count") != len(records):
        raise ValueError("Gym Visual source record_count does not match exercises.json")
    by_id = {str(record["id"]): record for record in records}
    selected = [
        candidate
        for candidate in profile.get("candidates", [])
        if candidate.get("screening", {}).get("decision") == "INCLUDE"
    ]
    if not selected:
        raise ValueError("strength profile contains no INCLUDE representatives")
    for candidate in selected:
        candidate_id = str(candidate["candidate_id"])
        source_record = by_id.get(candidate_id)
        if source_record is None or source_record.get("target") != candidate.get("target"):
            raise ValueError(
                f"profile representative is not present in the immutable source: {candidate_id}"
            )
    return records, profile, by_id


def build_rows(
    raw_dir: Path = DEFAULT_RAW_DIR, profile_path: Path = DEFAULT_PROFILE
) -> list[dict[str, str]]:
    records, profile, by_id = validate_inputs(raw_dir, profile_path)
    selected = [
        candidate
        for candidate in profile["candidates"]
        if candidate["screening"]["decision"] == "INCLUDE"
    ]
    selected_ids = {str(candidate["candidate_id"]) for candidate in selected}
    rows: list[dict[str, str]] = []
    for candidate in sorted(selected, key=lambda item: (item["target"], item["candidate_id"])):
        representative = by_id[str(candidate["candidate_id"])]
        family = str(candidate["candidate_attributes"]["exercise_family_candidate"])
        for variant in sorted(records, key=lambda item: str(item["id"])):
            variant_id = str(variant["id"])
            if variant_id in selected_ids or variant_id == str(representative["id"]):
                continue
            if variant.get("target") != representative.get("target"):
                continue
            normalized_variant_name = normalize_name(str(variant["name"]))
            if any(token in normalized_variant_name for token in NON_STRENGTH_TOKENS):
                continue
            if not family_matches(family, str(variant["name"])):
                continue
            duplicate_key = (
                str(representative["id"]),
                normalized_variant_name,
                equipment_code(str(variant["equipment"])),
            )
            if any(
                row["representative_id"] == duplicate_key[0]
                and normalize_name(row["variant_name"]) == duplicate_key[1]
                and equipment_code(row["variant_equipment"]) == duplicate_key[2]
                for row in rows
            ):
                continue
            dimensions, evidence = difference_dimensions(representative, variant)
            # This is the key guard against treating spelling or a source
            # version suffix as a meaningful catalog variant.
            if not dimensions:
                continue
            priority = priority_details(variant)
            rows.append(
                {
                    "representative_id": str(representative["id"]),
                    "representative_target": str(representative["target"]),
                    "representative_name": str(representative["name"]),
                    "exercise_family_candidate": family,
                    "movement_pattern_candidate": str(
                        candidate["candidate_attributes"]["movement_pattern_candidate"]
                    ),
                    "variant_candidate_id": variant_id,
                    "variant_target": str(variant["target"]),
                    "variant_name": str(variant["name"]),
                    "variant_equipment": str(variant["equipment"]),
                    "location_code_candidates": "|".join(
                        location_candidates(str(variant["equipment"]))
                    ),
                    "variant_priority_rank": "",
                    "home_priority": str(priority["home_priority"]),
                    "beginner_tool_priority": str(priority["beginner_tool_priority"]),
                    "popularity_priority_proxy": str(priority["popularity_priority_proxy"]),
                    "complexity_penalty": str(priority["complexity_penalty"]),
                    "priority_reason": str(priority["priority_reason"]),
                    "variant_media_id": str(variant["media_id"]),
                    "variant_image": str(variant["image"]),
                    "variant_gif_url": str(variant["gif_url"]),
                    "same_primary_target_candidate": "true",
                    "same_movement_pattern_candidate": "REVIEW_REQUIRED_SAME_FAMILY_RULE",
                    "meaningful_difference_dimensions": "|".join(dimensions),
                    "difference_evidence": " | ".join(evidence),
                    "auto_candidate_decision": "REVIEW_REQUIRED",
                    "auto_candidate_reason_code": "MEANINGFUL_VARIANT_DIMENSION_FOUND",
                    "auto_candidate_reason": "동일 target·family 어휘를 통과했고 장비·그립·자세·지지·스탠스·실행 중 하나 이상의 차이가 있어 사람 검토 대상으로 생성함.",
                    "alternative_relation_status": "NOT_CREATED_BY_DESIGN",
                    "review_decision": "",
                    "review_reason_code": "",
                    "review_note": "",
                    "reviewer": "",
                    "reviewed_at": "",
                }
            )
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["representative_id"], []).append(row)

    selected_rows: list[dict[str, str]] = []
    for representative_id in sorted(grouped):
        candidates = sorted(
            grouped[representative_id],
            key=lambda row: (
                int(row["home_priority"]),
                int(row["beginner_tool_priority"]),
                int(row["popularity_priority_proxy"]),
                int(row["complexity_penalty"]),
                row["variant_candidate_id"],
            ),
        )
        for rank, row in enumerate(candidates[:MAX_VARIANTS_PER_REPRESENTATIVE], start=1):
            row["variant_priority_rank"] = str(rank)
            selected_rows.append(row)
    return sorted(
        selected_rows,
        key=lambda row: (row["representative_id"], int(row["variant_priority_rank"])),
    )


def write_csv(path: Path, rows: list[dict[str, str]], *, pending: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_rows = []
    for row in rows:
        copied = dict(row)
        if pending:
            copied["review_decision"] = "PENDING"
        output_rows.append(copied)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)


def build_manifest(rows: list[dict[str, str]], raw_dir: Path, profile_path: Path) -> dict[str, Any]:
    raw_path = raw_dir / "exercises.json"
    return {
        "review_batch_version": REVIEW_BATCH_VERSION,
        "profile_version": VARIANT_PROFILE_VERSION,
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "purpose": "Gym Visual representative exercise_family_candidate and variant relationship review only",
        "source": {
            "profile": str(profile_path.relative_to(REPO_ROOT)),
            "profile_sha256": sha256_file(profile_path),
            "raw_exercises": str(raw_path.relative_to(REPO_ROOT)),
            "raw_exercises_sha256": sha256_file(raw_path),
        },
        "candidate_count": len(rows),
        "representative_count": len({row["representative_id"] for row in rows}),
        "dimension_counts": dict(
            sorted(
                Counter(
                    dimension
                    for row in rows
                    for dimension in row["meaningful_difference_dimensions"].split("|")
                ).items()
            )
        ),
        "alternative_relation_policy": "No alternative relations are created at the family/variant review stage.",
        "review_columns": REVIEW_COLUMNS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--review-batch", type=Path, default=DEFAULT_REVIEW_BATCH)
    parser.add_argument("--reviewed", type=Path, default=DEFAULT_REVIEWED)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    rows = build_rows(args.raw_dir, args.profile)
    write_csv(args.review_batch, rows)
    write_csv(args.reviewed, rows, pending=True)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(
                build_manifest(rows, args.raw_dir, args.profile), ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "review_batch": str(args.review_batch),
                "reviewed": str(args.reviewed),
                "candidate_count": len(rows),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
