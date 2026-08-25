"""Build an integrated review CSV from the selected exercise source files."""

# Korean catalog explanations and controlled-vocabulary labels are intentionally long.
# ruff: noqa: E501

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from align_source_candidates import COMMON_COLUMNS, map_equipment, map_locations, map_target
from integrated_catalog_registry import (
    DUPLICATE_CANDIDATE_GROUPS,
    REGISTRY_PATH,
    RegistryError,
    load_registry,
    lookup,
)
from integrated_catalog_schema import LICENSES, write_schema

DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
GYMVISUAL_CARDIO = DATA_ROOT / "validation/review_batches/gymvisual_cardio_review.csv"
GYMVISUAL_STRENGTH = (
    DATA_ROOT / "validation/review_batches/gymvisual_strength_representative_review.csv"
)
GYMVISUAL_VARIANTS = DATA_ROOT / "validation/review_batches/gymvisual_variant_review.csv"
GYMVISUAL_MOBILITY = DATA_ROOT / "validation/review_results/gymvisual_mobility_reviewed.csv"
KSPO = (
    DATA_ROOT
    / "validation/review_batches/kspo-beginner-supplement-v0.1.0/kspo_beginner_supplement.csv"
)
WGER_ATTRS = DATA_ROOT / "validation/review_results/wger_attributes.csv"
ALIGNED = (
    DATA_ROOT
    / "validation/review_batches/gymvisual-source-alignment-v0.4.0/aligned_review_batch.csv"
)
OUTPUT_DIR = DATA_ROOT / "validation/review_batches/gymvisual-integrated-review-v0.1.0"
OUTPUT_CSV = OUTPUT_DIR / "integrated_exercise_review.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "review_manifest.json"
OUTPUT_ALIASES = OUTPUT_DIR / "integrated_exercise_aliases.csv"
GYMVISUAL_RAW = DATA_ROOT / "raw/gym_visual/exercises.json"
GYMVISUAL_SOURCE_META = DATA_ROOT / "raw/gym_visual/source.json"
WGER_SOURCE_META = DATA_ROOT / "raw/wger_exercise_catalog/source.json"
KSPO_SOURCE_META = DATA_ROOT / "raw/kspo_fitness100_video/source.json"

ALLOWED_TRAINING_TYPES = {"STRENGTH", "CARDIO", "MOBILITY"}
LEGACY_ROW_COUNT = 173
MOBILITY_ROW_COUNT = 35
INTEGRATED_ROW_COUNT = LEGACY_ROW_COUNT + MOBILITY_ROW_COUNT

# 0014 can be performed as the selected BODYWEIGHT representative, so its
# medicine-ball-only variant is excluded. Tool-dependent variants remain.
BODYWEIGHT_SUBSTITUTABLE_VARIANT_IDS = {"0014"}
BODYWEIGHT_ONLY_IDENTITIES = {("gymvisual", "0687")}

# These codes are used only in this DRAFT review artifact.  The current public
# API enum intentionally remains unchanged until the equipment taxonomy is
# separately approved.  Fixed cardio machines use the existing MACHINE code.
DRAFT_EQUIPMENT_CODES = {
    "BODYWEIGHT",
    "DUMBBELL",
    "BARBELL",
    "EZ_BAR",
    "KETTLEBELL",
    "CABLE_MACHINE",
    "MACHINE",
    "HOUSEHOLD_WEIGHT",
    "BENCH",
    "PULL_UP_BAR",
    "RESISTANCE_BAND",
    "MAT",
    "STABILITY_BALL",
    "CHAIR",
    "MEDICINE_BALL",
    "FOAM_ROLLER",
    "SUSPENSION_STRAPS",
    "STEP_BOX",
    "ROPE",
}

EQUIPMENT_LABELS = {
    "BODYWEIGHT": "맨몸",
    "DUMBBELL": "덤벨",
    "BARBELL": "바벨",
    "EZ_BAR": "이지바",
    "KETTLEBELL": "케틀벨",
    "CABLE_MACHINE": "케이블 머신",
    "MACHINE": "고정 머신",
    "HOUSEHOLD_WEIGHT": "외부 부하(종류 미지정)",
    "BENCH": "벤치",
    "PULL_UP_BAR": "풀업바",
    "RESISTANCE_BAND": "밴드",
    "MAT": "매트",
    "STABILITY_BALL": "짐볼",
    "CHAIR": "의자",
    "MEDICINE_BALL": "메디신볼",
    "FOAM_ROLLER": "폼롤러",
    "SUSPENSION_STRAPS": "서스펜션 스트랩",
    "STEP_BOX": "스텝박스",
    "ROPE": "로프·스트랩",
}
EQUIPMENT_ORDER = tuple(EQUIPMENT_LABELS)

EQUIPMENT_MAP_RULES = (
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
    ("pull-up bar", "PULL_UP_BAR"),
    ("풀업바", "PULL_UP_BAR"),
    ("chair", "CHAIR"),
    ("의자", "CHAIR"),
    ("machine", "MACHINE"),
    ("머신", "MACHINE"),
    ("leverage", "MACHINE"),
    ("stationary bike", "MACHINE"),
    ("elliptical", "MACHINE"),
    ("stepmill", "MACHINE"),
    ("treadmill", "MACHINE"),
    ("rope", "ROPE"),
    ("로프", "ROPE"),
    ("strap", "SUSPENSION_STRAPS"),
    ("suspension", "SUSPENSION_STRAPS"),
    ("stability ball", "STABILITY_BALL"),
    ("swiss ball", "STABILITY_BALL"),
    ("짐볼", "STABILITY_BALL"),
    ("medicine ball", "MEDICINE_BALL"),
    ("메디신볼", "MEDICINE_BALL"),
    ("roller", "FOAM_ROLLER"),
    ("폼롤러", "FOAM_ROLLER"),
    ("step box", "STEP_BOX"),
    ("stepbox", "STEP_BOX"),
    ("스텝박스", "STEP_BOX"),
    ("weighted", "HOUSEHOLD_WEIGHT"),
)

# Name-based additions are limited to equipment without which the named
# variation cannot be performed.  Walls and floors are intentionally absent.
EQUIPMENT_NAME_ADDITIONS = {
    "incline": ("BENCH",),
    "decline": ("BENCH",),
    "on bench": ("BENCH",),
    "bench support": ("BENCH",),
    "over bench": ("BENCH",),
    "preacher": ("BENCH",),
    "barbell pullover": ("BENCH",),
    "cable lying extension pullover": ("BENCH",),
    "ez bar lying bent arms pullover": ("BENCH",),
    "seated calf raise": ("BENCH",),
    "hyperextension": ("BENCH",),
    "scapular pull-up": ("PULL_UP_BAR",),
    "biceps pull-up": ("PULL_UP_BAR",),
    "inverse leg curl (on pull-up cable machine)": ("PULL_UP_BAR",),
    "inverted row with straps": ("SUSPENSION_STRAPS",),
    "suspended reverse crunch": ("SUSPENSION_STRAPS",),
    "step-up": ("STEP_BOX",),
    "stepbox": ("STEP_BOX",),
    "스텝박스": ("STEP_BOX",),
    "chair leg extended stretch": ("CHAIR",),
    "on stability ball": ("STABILITY_BALL",),
    "with rope attachment": ("ROPE",),
}

GYMVISUAL_TARGETS = {
    "abs",
    "biceps",
    "calves",
    "delts",
    "forearms",
    "glutes",
    "hamstrings",
    "lats",
    "pectorals",
    "quads",
    "spine",
    "traps",
    "triceps",
    "upper back",
}

KSPO_TARGET_OVERRIDES = {
    "스텝박스 오르내리기": "quads",
    "한발 서서 균형잡기": "glutes",
    "의자잡고 전방으로 무릎 굽혀 들기": "quads",
    "의자에 앉아 다리로 짐볼 쥐기": "quads",
    "밴드 잡고 누워서 다리 밀기": "quads",
    "누워서 배가로근 수축1": "abs",
    "의자에 앉아 밴드 양옆으로 늘이기": "upper back",
    "네발기기 자세에서 팔 다리 들기": "spine",
    "의자잡고 후방으로 무릎 굽혀 들기": "hamstrings",
    "앉아서 엉덩관절 굽히기": "quads",
}

WGER_TARGET_OVERRIDES = {
    "1227": "delts",
    "1370": "glutes",
    "145": "abs",
    "1603": "hamstrings",
    "1612": "glutes",
    "1652": "hamstrings",
    "1706": "quads",
    "1801": "quads",
    "364": "hamstrings",
    "371": "quads",
    "507": "hamstrings",
    "9": "glutes",
}

DIFFICULTY_CODES = {"BEGINNER", "INTERMEDIATE", "ADVANCED"}
DIFFICULTY_CANDIDATE_CODES = {*DIFFICULTY_CODES, "REVIEW_REQUIRED"}

# ``CONDITIONAL`` is a beginner-suitability value that was copied into a few
# Gym Visual difficulty candidates.  It is intentionally not coerced into a
# difficulty level: the raw source remains unchanged and the integrated
# candidate is marked for review before the independent review value is set.
DIFFICULTY_CANDIDATE_NORMALIZATION = {
    "CONDITIONAL": "REVIEW_REQUIRED",
    "REVIEW_REQUIRED": "REVIEW_REQUIRED",
}

# Difficulty is about execution demand, not whether a beginner may use a
# scaled or supervised version.  These family defaults use technical
# complexity, balance/control, equipment handling, and joint/load demand.
DIFFICULTY_FAMILY_DEFAULTS = {
    "BARBELL_DEADLIFT_CANDIDATE": "INTERMEDIATE",
    "BARBELL_PULLOVER_CANDIDATE": "INTERMEDIATE",
    "BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE": "INTERMEDIATE",
    "BODYWEIGHT_BACK_EXTENSION_CANDIDATE": "INTERMEDIATE",
    "BODYWEIGHT_FORWARD_LUNGE_CANDIDATE": "INTERMEDIATE",
    "BODYWEIGHT_GLUTE_BRIDGE_CANDIDATE": "BEGINNER",
    "BODYWEIGHT_PULL_UP_BICEPS_CANDIDATE": "ADVANCED",
    "BODYWEIGHT_REVERSE_CRUNCH_CANDIDATE": "BEGINNER",
    "BODYWEIGHT_RUSSIAN_TWIST_CANDIDATE": "INTERMEDIATE",
    "BODYWEIGHT_SPLIT_SQUAT_CANDIDATE": "INTERMEDIATE",
    "BODYWEIGHT_STANDING_CALF_RAISE_CANDIDATE": "BEGINNER",
    "CABLE_FLY_CANDIDATE": "BEGINNER",
    "CLOSE_GRIP_PUSH_UP_CANDIDATE": "BEGINNER",
    "DUMBBELL_GOBLET_SQUAT_CANDIDATE": "BEGINNER",
    "DUMBBELL_LATERAL_RAISE_CANDIDATE": "BEGINNER",
    "DUMBBELL_PREACHER_CURL_CANDIDATE": "BEGINNER",
    "DUMBBELL_REAR_FLY_CANDIDATE": "BEGINNER",
    "DUMBBELL_SHRUG_CANDIDATE": "BEGINNER",
    "DUMBBELL_STEP_UP_LUNGE_CANDIDATE": "INTERMEDIATE",
    "INCLINE_Y_RAISE_CANDIDATE": "INTERMEDIATE",
    "INVERTED_ROW_CANDIDATE": "INTERMEDIATE",
    "LOWER_BACK_CURL_CANDIDATE": "INTERMEDIATE",
    "MACHINE_LEG_EXTENSION_CANDIDATE": "BEGINNER",
    "ONE_ARM_WALL_LATS_CANDIDATE": "BEGINNER",
    "OVERHEAD_TRICEPS_EXTENSION_CANDIDATE": "BEGINNER",
    "PLANK_ROTATION_CANDIDATE": "INTERMEDIATE",
    "PUSH_UP_CANDIDATE": "BEGINNER",
    "REVERSE_CALF_RAISE_CANDIDATE": "INTERMEDIATE",
    "REVERSE_WRIST_CURL_CANDIDATE": "BEGINNER",
    "SEATED_CABLE_ROW_CANDIDATE": "BEGINNER",
    "SEATED_CALF_RAISE_CANDIDATE": "BEGINNER",
    "SEATED_LEG_CURL_CANDIDATE": "BEGINNER",
    "SEATED_SHOULDER_PRESS_CANDIDATE": "INTERMEDIATE",
    "WRIST_CURL_CANDIDATE": "BEGINNER",
}

# Cross-source conflicts are resolved by the common movement and variation,
# not by source preference.  The IDs are stable source identities.
DIFFICULTY_CROSS_SOURCE_OVERRIDES = {
    ("wger", "1370"): "INTERMEDIATE",  # dumbbell deadlift ~= Gym Visual 0300
    ("wger", "1652"): "INTERMEDIATE",  # dumbbell RDL ~= Gym Visual 0432/0434
    ("wger", "1927"): "INTERMEDIATE",  # inverted row ~= Gym Visual 0499/2298
    ("wger", "203"): "BEGINNER",  # goblet squat ~= Gym Visual 1760
    ("wger", "1706"): "INTERMEDIATE",  # Bulgarian/split squat ~= Gym Visual 2368
}


def normalize_difficulty_candidate(value: object) -> str:
    """Keep raw candidate evidence visible while enforcing candidate codes."""

    code = text(value).upper()
    if code in DIFFICULTY_CODES:
        return code
    return DIFFICULTY_CANDIDATE_NORMALIZATION.get(code, "REVIEW_REQUIRED")


def reviewed_difficulty_code(row: dict[str, str], *, source_difficulty: object = "") -> str:
    """Return a deterministic review code from exercise-demand evidence."""

    identity = (text(row.get("source_track")), text(row.get("source_identity")))
    if identity in DIFFICULTY_CROSS_SOURCE_OVERRIDES:
        return DIFFICULTY_CROSS_SOURCE_OVERRIDES[identity]

    name = text(row.get("source_name")).lower()
    family = text(row.get("exercise_family_candidate"))

    # High-demand balance/coordination or equipment-control variations.
    if "biceps pull-up" in name or name == "pull-up":
        return "ADVANCED"
    if "inverse leg curl (on pull-up" in name:
        return "ADVANCED"
    if "kettlebell lunge pass through" in name or "contralateral" in name:
        return "ADVANCED"
    if "stability ball" in name and ("fly" in name or "russian" in name or "pullover" in name):
        return "ADVANCED"
    if "weighted russian twist" in name and "legs up" in name:
        return "ADVANCED"

    # These variations add unilateral control, rotation, or a more demanding
    # position while retaining the same exercise family.
    if "single leg" in name or "one leg" in name or "walking lunge" in name:
        if "calf" in name or "lunge" in name or "curl" in name:
            return "INTERMEDIATE"
    if "pass through" in name or "lateral to front raise" in name:
        return "INTERMEDIATE"
    if "dumbbell one arm shoulder press" in name:
        return "INTERMEDIATE"
    if family == "SEATED_SHOULDER_PRESS_CANDIDATE" and "band" in name:
        return "BEGINNER"
    if family == "BODYWEIGHT_CRUNCH_CANDIDATE" and ("decline" in name or "suspended" in name):
        return "INTERMEDIATE"
    if family == "BODYWEIGHT_REVERSE_CRUNCH_CANDIDATE" and ("cable" in name or "roller" in name):
        return "INTERMEDIATE"
    if family == "DUMBBELL_PREACHER_CURL_CANDIDATE" and "zottman" in name:
        return "INTERMEDIATE"

    if row.get("source_scope_status") == "GYMVISUAL_MOBILITY_REVIEW_BATCH":
        candidate = normalize_difficulty_candidate(row.get("difficulty_code_candidate"))
        return candidate if candidate in DIFFICULTY_CODES else "BEGINNER"

    if family in DIFFICULTY_FAMILY_DEFAULTS:
        return DIFFICULTY_FAMILY_DEFAULTS[family]

    source_code = normalize_difficulty_candidate(source_difficulty)
    if source_code in DIFFICULTY_CODES:
        return source_code
    candidate = normalize_difficulty_candidate(row.get("difficulty_code_candidate"))
    return candidate if candidate in DIFFICULTY_CODES else "BEGINNER"


KSPO_TARGET_REVIEW_NOTES = {
    "의자잡고 전방으로 무릎 굽혀 들기": (
        "고관절 굽힘 운동. hip_flexors 코드가 없어 임시로 quads 사용."
    ),
    "의자에 앉아 다리로 짐볼 쥐기": ("고관절 내전 운동. adductors 코드가 없어 임시로 quads 사용."),
    "앉아서 엉덩관절 굽히기": ("고관절 굽힘 운동. hip_flexors 코드가 없어 임시로 quads 사용."),
}

KSPO_TRAINING_TYPE_OVERRIDES = {
    "스텝박스 오르내리기": "CARDIO",
    "앉아서 엉덩관절 굽히기": "STRENGTH",
    "의자잡고 전방으로 무릎 굽혀 들기": "STRENGTH",
    "의자잡고 후방으로 무릎 굽혀 들기": "STRENGTH",
    "한발 서서 균형잡기": "STRENGTH",
    "의자에 앉아 밴드 양옆으로 늘이기": "STRENGTH",
    "의자에 앉아 다리로 짐볼 쥐기": "STRENGTH",
    "네발기기 자세에서 팔 다리 들기": "STRENGTH",
    "누워서 배가로근 수축1": "STRENGTH",
    "밴드 잡고 누워서 다리 밀기": "STRENGTH",
}

# The integrated artifact is a review queue, but the two taxonomy candidate
# fields below are now resolved wherever the approved movement-pattern list
# and an existing family candidate are sufficient.  Equipment, grip, and
# posture remain variants of the same family; a different joint action gets a
# separate existing family candidate.  Values intentionally left as
# REVIEW_REQUIRED are reported as taxonomy gaps instead of inventing codes.
GYMVISUAL_FAMILY_MOVEMENT_PATTERNS = {
    "BARBELL_DEADLIFT_CANDIDATE": "HIP_DOMINANT",
    "BARBELL_PULLOVER_CANDIDATE": "ISOLATION",
    "BARBELL_FRONT_RAISE_CANDIDATE": "ISOLATION",
    "REVERSE_WRIST_CURL_CANDIDATE": "ISOLATION",
    "SEATED_CALF_RAISE_CANDIDATE": "ISOLATION",
    "OVERHEAD_TRICEPS_EXTENSION_CANDIDATE": "ISOLATION",
    "BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE": "HIP_DOMINANT",
    "WRIST_CURL_CANDIDATE": "ISOLATION",
    "BODYWEIGHT_PULL_UP_BICEPS_CANDIDATE": "VERTICAL_PULL",
    "CABLE_FLY_CANDIDATE": "ISOLATION",
    "SEATED_CABLE_ROW_CANDIDATE": "HORIZONTAL_PULL",
    "LAT_PULLDOWN_CANDIDATE": "VERTICAL_PULL",
    "CABLE_TRICEPS_PUSHDOWN_CANDIDATE": "ISOLATION",
    "BODYWEIGHT_RUSSIAN_TWIST_CANDIDATE": "CORE_BRACE",
    "DUMBBELL_SHRUG_CANDIDATE": "ISOLATION",
    "BODYWEIGHT_REVERSE_CRUNCH_CANDIDATE": "CORE_BRACE",
    "CLOSE_GRIP_PUSH_UP_CANDIDATE": "HORIZONTAL_PUSH",
    "BODYWEIGHT_CRUNCH_CANDIDATE": "CORE_BRACE",
    "DEAD_BUG_CANDIDATE": "CORE_BRACE",
    "DUMBBELL_LATERAL_RAISE_CANDIDATE": "ISOLATION",
    "BODYWEIGHT_FORWARD_LUNGE_CANDIDATE": "KNEE_DOMINANT",
    "SEATED_SHOULDER_PRESS_CANDIDATE": "VERTICAL_PUSH",
    "DUMBBELL_PREACHER_CURL_CANDIDATE": "ISOLATION",
    "BODYWEIGHT_STANDING_CALF_RAISE_CANDIDATE": "ISOLATION",
    "DUMBBELL_REAR_FLY_CANDIDATE": "ISOLATION",
    "DUMBBELL_STANDING_CURL_CANDIDATE": "ISOLATION",
    "PLANK_ROTATION_CANDIDATE": "CORE_BRACE",
    "BODYWEIGHT_BACK_EXTENSION_CANDIDATE": "HIP_DOMINANT",
    "SEATED_LEG_CURL_CANDIDATE": "KNEE_FLEXION",
    "INVERTED_ROW_CANDIDATE": "HORIZONTAL_PULL",
    "MACHINE_LEG_EXTENSION_CANDIDATE": "ISOLATION",
    "PUSH_UP_CANDIDATE": "HORIZONTAL_PUSH",
    "SCAPULAR_PULL_UP_CANDIDATE": "VERTICAL_PULL",
    "HAND_GRIP_SQUEEZE_CANDIDATE": "ISOLATION",
    "LOWER_BACK_CURL_CANDIDATE": "CORE_BRACE",
    "ONE_ARM_WALL_LATS_CANDIDATE": "ISOLATION",
    "REVERSE_CALF_RAISE_CANDIDATE": "ISOLATION",
    "DUMBBELL_GOBLET_SQUAT_CANDIDATE": "KNEE_DOMINANT",
    "BODYWEIGHT_SPLIT_SQUAT_CANDIDATE": "KNEE_DOMINANT",
    "DUMBBELL_STEP_UP_LUNGE_CANDIDATE": "KNEE_DOMINANT",
    "BODYWEIGHT_GLUTE_BRIDGE_CANDIDATE": "HIP_DOMINANT",
    "INCLINE_Y_RAISE_CANDIDATE": "ISOLATION",
}

# Rows whose source batch grouped a different joint action under the
# representative family are corrected explicitly.  The existing candidate
# family vocabulary is intentionally reused.
GYMVISUAL_TAXONOMY_OVERRIDES = {
    # Straight/stiff-leg deadlift is a separate hinge family from a
    # conventional deadlift, although the equipment may differ.
    "0432": ("BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "0434": ("BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "1009": ("BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "1023": ("BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    # Rear-delt horizontal abduction is not a lateral/front raise.
    "0326": ("DUMBBELL_REAR_FLY_CANDIDATE", "ISOLATION"),
    "0348": ("DUMBBELL_REAR_FLY_CANDIDATE", "ISOLATION"),
    "0379": ("DUMBBELL_REAR_FLY_CANDIDATE", "ISOLATION"),
    "0380": ("DUMBBELL_REAR_FLY_CANDIDATE", "ISOLATION"),
    # Reverse wrist extension is separate from wrist flexion.
    "0368": ("REVERSE_WRIST_CURL_CANDIDATE", "ISOLATION"),
    "0385": ("REVERSE_WRIST_CURL_CANDIDATE", "ISOLATION"),
    "0994": ("REVERSE_WRIST_CURL_CANDIDATE", "ISOLATION"),
    # Reverse crunch and rotation/lateral crunch are not floor crunch
    # variants with the same joint action.
    "0807": ("BODYWEIGHT_REVERSE_CRUNCH_CANDIDATE", "CORE_BRACE"),
    "0691": ("CRUNCH_VARIANT_CANDIDATE", "CORE_BRACE"),
    "0972": ("ROTATION_VARIANT_CANDIDATE", "CORE_BRACE"),
    "0985": ("ROTATION_VARIANT_CANDIDATE", "CORE_BRACE"),
}

WGER_TAXONOMY_OVERRIDES = {
    "1094": ("PECTORALS_HORIZONTAL_PUSH_CANDIDATE", "HORIZONTAL_PUSH"),
    "1656": ("PECTORALS_HORIZONTAL_PUSH_CANDIDATE", "HORIZONTAL_PUSH"),
    "537": ("PECTORALS_HORIZONTAL_PUSH_CANDIDATE", "HORIZONTAL_PUSH"),
    "1117": ("ROW_VARIANT_CANDIDATE", "HORIZONTAL_PULL"),
    "1227": ("ROW_VARIANT_CANDIDATE", "HORIZONTAL_PULL"),
    "1283": ("ROW_VARIANT_CANDIDATE", "HORIZONTAL_PULL"),
    "1725": ("ROW_VARIANT_CANDIDATE", "HORIZONTAL_PULL"),
    "1927": ("INVERTED_ROW_CANDIDATE", "HORIZONTAL_PULL"),
    "1370": ("BARBELL_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "1612": ("BARBELL_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "1652": ("BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "507": ("BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE", "HIP_DOMINANT"),
    "145": ("ROTATION_VARIANT_CANDIDATE", "CORE_BRACE"),
    "146": ("SEATED_CALF_RAISE_CANDIDATE", "ISOLATION"),
    "1470": ("LAT_PULLDOWN_CANDIDATE", "VERTICAL_PULL"),
    "1510": ("LAT_PULLDOWN_CANDIDATE", "VERTICAL_PULL"),
    "1603": ("SEATED_LEG_CURL_CANDIDATE", "KNEE_FLEXION"),
    "364": ("SEATED_LEG_CURL_CANDIDATE", "KNEE_FLEXION"),
    "1706": ("BODYWEIGHT_SPLIT_SQUAT_CANDIDATE", "KNEE_DOMINANT"),
    "1801": ("SQUAT_VARIANT_CANDIDATE", "KNEE_DOMINANT"),
    "203": ("DUMBBELL_GOBLET_SQUAT_CANDIDATE", "KNEE_DOMINANT"),
    "369": ("MACHINE_LEG_EXTENSION_CANDIDATE", "ISOLATION"),
    "371": ("SQUAT_VARIANT_CANDIDATE", "KNEE_DOMINANT"),
    "1893": ("SEATED_SHOULDER_PRESS_CANDIDATE", "VERTICAL_PUSH"),
    "20": ("SEATED_SHOULDER_PRESS_CANDIDATE", "VERTICAL_PUSH"),
    "543": ("SEATED_SHOULDER_PRESS_CANDIDATE", "VERTICAL_PUSH"),
}

KSPO_TAXONOMY_OVERRIDES = {
    "스텝박스 오르내리기": ("REVIEW_REQUIRED", "GAIT"),
    "한발 서서 균형잡기": ("REVIEW_REQUIRED", "REVIEW_REQUIRED"),
    "의자잡고 전방으로 무릎 굽혀 들기": ("REVIEW_REQUIRED", "ISOLATION"),
    "의자에 앉아 다리로 짐볼 쥐기": ("REVIEW_REQUIRED", "ISOLATION"),
    "밴드 잡고 누워서 다리 밀기": ("REVIEW_REQUIRED", "KNEE_DOMINANT"),
    "누워서 배가로근 수축1": ("ABS_CORE_BRACE_CANDIDATE", "CORE_BRACE"),
    "의자에 앉아 밴드 양옆으로 늘이기": ("UPPER_BACK_ISOLATION_CANDIDATE", "ISOLATION"),
    "네발기기 자세에서 팔 다리 들기": ("SPINE_CORE_BRACE_CANDIDATE", "CORE_BRACE"),
    "의자잡고 후방으로 무릎 굽혀 들기": ("SEATED_LEG_CURL_CANDIDATE", "KNEE_FLEXION"),
    "앉아서 엉덩관절 굽히기": ("REVIEW_REQUIRED", "ISOLATION"),
}

GYMVISUAL_VARIANT_REFERENCE_OVERRIDES = {
    "0432": ("0116", "barbell straight leg deadlift"),
    "0434": ("0116", "barbell straight leg deadlift"),
    "1009": ("0116", "barbell straight leg deadlift"),
    "1023": ("0116", "barbell straight leg deadlift"),
    "0326": ("0378", "dumbbell rear fly"),
    "0348": ("0378", "dumbbell rear fly"),
    "0379": ("0378", "dumbbell rear fly"),
    "0380": ("0378", "dumbbell rear fly"),
    "0368": ("0082", "barbell reverse wrist curl"),
    "0385": ("0082", "barbell reverse wrist curl"),
    "0994": ("0082", "barbell reverse wrist curl"),
    "0807": ("0872", "reverse crunch"),
}

GYMVISUAL_CROSS_FAMILY_VARIANT_IDS = {"0691", "0972", "0985"}

SOURCE_COLUMNS = [
    "source_instruction_en",
    "source_instruction_ko",
    "source_muscle_group",
    "source_secondary_muscles",
    "source_attribution",
    "supplement_category",
    "selection_reason",
    "source_video_title",
    "source_description",
    "source_review_decision",
    "source_candidate_status",
]
REVIEW_COLUMNS = [
    "reviewed_name_ko",
    "reviewed_target",
    "reviewed_body_area_codes",
    "reviewed_training_type_code",
    "reviewed_movement_pattern_code",
    "reviewed_exercise_family",
    "reviewed_variant_group",
    "reviewed_equipment_codes",
    "reviewed_location_codes",
    "reviewed_difficulty_code",
    "reviewed_beginner_suitability",
    "reviewed_decision",
]
VARIANT_COLUMNS = [
    "variant_relation_representative_ids",
    "variant_relation_representative_names",
    "variant_relation_equipment_codes",
    "variant_relation_location_codes",
    "variant_relation_media_ids",
    "variant_relation_review_decision",
    "variant_relation_note",
]
IDENTITY_COLUMNS = [
    "catalog_id",
    "normalized_exercise_id",
    "source_system",
    "source_id",
    "legacy_review_normalized_exercise_id",
]
NAME_COLUMNS = ["name_en", "name_ko"]
DEDUP_COLUMNS = [
    "duplicate_candidate_group_id",
    "duplicate_review_status",
    "duplicate_review_note",
]
GUIDE_COLUMNS = [
    "setup_guide",
    "execution_steps",
    "breathing_guide",
    "finish_guide",
    "guide_source_url",
    "guide_review_status",
    "guide_review_note",
]
SAFETY_COLUMNS = [
    "safety_warning",
    "contraindications",
    "common_mistakes",
    "stop_conditions",
    "safety_source_url",
    "safety_review_status",
]
PROVENANCE_COLUMNS = [
    "source_url",
    "source_author",
    "license_id",
    "license_name",
    "license_version",
    "license_url",
    "is_modified",
    "modification_note",
    "accessed_at",
    "metadata_license_id",
    "instruction_license_id",
    "image_license_id",
    "gif_video_license_id",
    "attribution_text",
    "license_review_status",
]
MEDIA_COLUMNS = [
    "media_link_status",
    "media_link_note",
    "media_validation_status",
    "media_source_reference",
]
RAW_COLUMNS = [
    "raw_source_record_json",
    "raw_review_required",
    "raw_review_required_codes",
    "raw_review_status",
    "raw_review_decision",
    "raw_reviewed_decision",
    "raw_review_normalized_exercise_id",
    "raw_source_attribution",
    "raw_source_license",
    "raw_source_license_author",
    "raw_source_media_reference",
    "raw_source_instruction_en",
    "raw_source_instruction_steps_en",
]
OUTPUT_COLUMNS = [
    *IDENTITY_COLUMNS,
    *NAME_COLUMNS,
    *DEDUP_COLUMNS,
    *COMMON_COLUMNS,
    *SOURCE_COLUMNS,
    *VARIANT_COLUMNS,
    *REVIEW_COLUMNS,
    "review_status_interpretation",
    "production_eligibility_blockers",
    *GUIDE_COLUMNS,
    *SAFETY_COLUMNS,
    *PROVENANCE_COLUMNS,
    *MEDIA_COLUMNS,
    *RAW_COLUMNS,
]


def text(value: object) -> str:
    return "" if value is None else str(value).strip()


def pipe(value: object) -> str:
    if isinstance(value, list):
        return "|".join(text(item) for item in value if text(item))
    return text(value).replace(",", "|")


def unique_pipe(values: list[str]) -> str:
    return "|".join(dict.fromkeys(value for value in values if value))


def split_codes(value: object) -> list[str]:
    """Split source or review values without treating review markers as codes."""
    raw = text(value)
    if not raw:
        return []
    values = [part.strip() for part in re.split(r"\s*[|,]\s*", raw) if part.strip()]
    result: list[str] = []
    for value_part in values:
        upper = value_part.upper()
        if upper.endswith("_REVIEW_REQUIRED"):
            upper = upper.removesuffix("_REVIEW_REQUIRED")
        if upper in DRAFT_EQUIPMENT_CODES and upper not in result:
            result.append(upper)
    return [code for code in EQUIPMENT_ORDER if code in result]


def source_equipment_codes(value: object) -> list[str]:
    """Map every explicit source tool token, preserving multi-tool sources."""
    raw = text(value).lower()
    result: list[str] = []
    for token in re.split(r"\s*[|,]\s*", raw):
        token = token.strip()
        if not token:
            continue
        for needle, code in EQUIPMENT_MAP_RULES:
            if needle in token:
                if code not in result:
                    result.append(code)
                break
    return [code for code in EQUIPMENT_ORDER if code in result]


def equipment_codes_for_row(row: dict[str, str]) -> list[str]:
    """Resolve source, candidate, reviewed, and variation evidence together."""
    result: list[str] = []
    for code in source_equipment_codes(row.get("source_equipment")):
        if code not in result:
            result.append(code)
    for field in ("equipment_code_candidate", "reviewed_equipment_codes"):
        for code in split_codes(row.get(field)):
            if code not in result:
                result.append(code)

    name = text(row.get("source_name")).lower()
    for needle, additions in EQUIPMENT_NAME_ADDITIONS.items():
        if needle == "incline" and "treadmill" in name:
            continue
        if needle in name:
            for code in additions:
                if code not in result:
                    result.append(code)

    if not result:
        raise ValueError(
            "equipment evidence unresolved: "
            f"{row.get('source_track')}:{row.get('source_identity')}:{row.get('source_name')}"
        )
    return [code for code in EQUIPMENT_ORDER if code in result]


def location_codes_for_row(row: dict[str, str]) -> list[str]:
    """Normalize locations and treat outdoor-capable candidates as gym-capable."""
    values: list[str] = []
    for field in ("location_code_candidates", "reviewed_location_codes", "source_location"):
        raw = text(row.get(field)).upper().replace(" ", "")
        for code in raw.split("|"):
            if code in {"HOME", "GYM", "OUTDOOR"} and code not in values:
                values.append(code)
    if not values:
        mapped_source_location = map_locations(row.get("source_location"))
        for code in mapped_source_location.split("|"):
            if code in {"HOME", "GYM", "OUTDOOR"} and code not in values:
                values.append(code)
    if not values:
        raise ValueError(
            "location evidence unresolved: "
            f"{row.get('source_track')}:{row.get('source_identity')}:{row.get('source_name')}"
        )
    had_outdoor = "OUTDOOR" in values
    values = [code for code in values if code != "OUTDOOR"]
    if had_outdoor and "GYM" not in values:
        values.append("GYM")
    return values


def finalize_equipment_and_location(row: dict[str, str]) -> None:
    equipment_codes = equipment_codes_for_row(row)
    if (row.get("source_track"), row.get("source_identity")) in BODYWEIGHT_ONLY_IDENTITIES:
        equipment_codes = ["BODYWEIGHT"]
    location_codes = location_codes_for_row(row)
    equipment_value = "|".join(equipment_codes)
    location_value = "|".join(location_codes)
    row["equipment_code_candidate"] = equipment_value
    row["equipment_label_candidate"] = "|".join(EQUIPMENT_LABELS[code] for code in equipment_codes)
    row["reviewed_equipment_codes"] = equipment_value
    row["location_code_candidates"] = location_value
    row["reviewed_location_codes"] = location_value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def gymvisual_raw_by_id() -> dict[str, dict[str, object]]:
    values = json.loads(GYMVISUAL_RAW.read_text(encoding="utf-8"))
    if not isinstance(values, list):
        raise ValueError("Gym Visual raw data must be a list")
    return {str(value["id"]): value for value in values if isinstance(value, dict)}


def split_review_codes(value: object) -> list[str]:
    result: list[str] = []
    for code in re.split(r"\s*[|,]\s*", text(value)):
        if code and code not in result:
            result.append(code)
    return result


def raw_value(row: dict[str, str], key: str) -> str:
    """Read a pre-normalization value before any final field is overwritten."""
    try:
        raw = json.loads(row.get("raw_source_record_json", "{}"))
    except json.JSONDecodeError:
        raw = {}
    if isinstance(raw, dict):
        for candidate in ("source_record", "aligned"):
            value = raw.get(candidate)
            if isinstance(value, dict) and key in value:
                return text(value.get(key))
        if key in raw:
            return text(raw.get(key))
    return text(row.get(key))


def license_fields(row: dict[str, str], source_meta: dict[str, object]) -> None:
    license_id = text(row.get("source_license"))
    license_info = LICENSES.get(license_id)
    if license_info is None:
        license_id = "REVIEW_REQUIRED"
        license_info = {"name": "", "version": "", "url": ""}
    source_track = text(row.get("source_track"))
    source_author = (
        text(source_meta.get("provider"))
        or {
            "gymvisual": "Aliaksandr Makatserchyk / Gym visual",
            "wger": "wger project and community contributors",
            "kspo": "서울올림픽기념국민체육진흥공단",
        }[source_track]
    )
    row.update(
        {
            "source_url": text(source_meta.get("source_url") or source_meta.get("dataset_url"))
            or "https://github.com/hasaneyldrm/exercises-dataset",
            "source_author": source_author,
            "license_id": license_id,
            "license_name": license_info["name"] or "REVIEW_REQUIRED",
            "license_version": license_info["version"] or "REVIEW_REQUIRED",
            "license_url": license_info["url"] or "REVIEW_REQUIRED",
            "is_modified": "true",
            "modification_note": (
                "통합 식별자·통제어휘·검토 필드를 추가하고 원천값을 raw_source_record_json에 보존함."
            ),
            "accessed_at": text(source_meta.get("retrieved_at")) or "REVIEW_REQUIRED",
            "attribution_text": "",
        }
    )
    if source_track == "gymvisual":
        attribution = "© Aliaksandr Makatserchyk - Gym visual - https://gymvisual.com/"
        row.update(
            {
                "metadata_license_id": license_id,
                "instruction_license_id": license_id,
                "image_license_id": "REVIEW_REQUIRED",
                "gif_video_license_id": "REVIEW_REQUIRED",
                "license_review_status": "PARTIALLY_REVIEWED",
            }
        )
    elif source_track == "wger":
        attribution = "wger project and community contributors — https://wger.de/"
        row.update(
            {
                "metadata_license_id": license_id,
                "instruction_license_id": "REVIEW_REQUIRED",
                "image_license_id": "REVIEW_REQUIRED",
                "gif_video_license_id": "REVIEW_REQUIRED",
                "license_review_status": "REVIEW_REQUIRED",
            }
        )
    else:
        attribution = (
            "서울올림픽기념국민체육진흥공단 — https://www.data.go.kr/data/15108846/openapi.do"
        )
        row.update(
            {
                "metadata_license_id": license_id,
                "instruction_license_id": license_id,
                "image_license_id": "REVIEW_REQUIRED",
                "gif_video_license_id": "REVIEW_REQUIRED",
                "license_review_status": "REVIEW_REQUIRED",
            }
        )
    row["attribution_text"] = attribution
    row["source_attribution"] = attribution
    if not text(row.get("source_license_author")):
        row["source_license_author"] = attribution


def enrich_catalog_fields(
    row: dict[str, str], registry: dict[tuple[str, str], dict[str, str]]
) -> None:
    source_system = text(row.get("source_track"))
    source_id = text(row.get("source_identity"))
    legacy_review_values = {
        field: text(row.get(field))
        for field in (
            "review_required",
            "review_required_codes",
            "review_status",
            "review_decision",
            "reviewed_decision",
            "review_normalized_exercise_id",
        )
    }
    identity = lookup(source_system, source_id, registry)
    row.update(
        {
            "catalog_id": identity["catalog_id"],
            "normalized_exercise_id": identity["normalized_exercise_id"],
            "source_system": source_system,
            "source_id": source_id,
            "legacy_review_normalized_exercise_id": raw_value(row, "review_normalized_exercise_id"),
            "name_en": text(row.get("source_name")) if source_system != "kspo" else "",
            "name_ko": text(row.get("reviewed_name_ko")) or "REVIEW_REQUIRED",
            "duplicate_candidate_group_id": DUPLICATE_CANDIDATE_GROUPS.get(
                (source_system, source_id), ""
            ),
            "duplicate_review_status": (
                "REVIEW_REQUIRED"
                if (source_system, source_id) in DUPLICATE_CANDIDATE_GROUPS
                else "NOT_IDENTIFIED"
            ),
            "duplicate_review_note": (
                "동일 운동 후보. 원천 설명·동작·장비를 사람 검토 후에만 normalized_exercise_id를 병합함."
                if (source_system, source_id) in DUPLICATE_CANDIDATE_GROUPS
                else ""
            ),
        }
    )

    raw_codes = raw_value(row, "review_required_codes") or text(row.get("review_required_codes"))
    codes = split_review_codes(raw_codes)
    row["review_required_codes"] = "|".join(codes)
    row["review_required"] = "true" if codes else "false"
    row["review_status_interpretation"] = {
        "DRAFT": "검토 대기 또는 원천 후보 상태. 운영 사용 불가.",
        "DOMAIN_APPROVED": "통합 카탈로그 후보 포함 승인으로만 해석하며 전체 승인 아님.",
        "INCLUSION_APPROVED": "통합 카탈로그 후보로 포함 승인. 전체 분류·안전·권리·미디어 승인이 아님.",
        "PARTIALLY_APPROVED": "일부 영역만 승인. 미해결 검토 코드가 있으면 운영 사용 불가.",
        "FINAL_APPROVED": "필수 분류·안전·가이드·출처·라이선스·미디어 검토를 완료한 최종 승인.",
    }.get(text(row.get("review_status")), "검토 상태 정의 필요")
    if text(row.get("review_status")) == "DOMAIN_APPROVED":
        row["review_status"] = "INCLUSION_APPROVED"
        row["review_status_interpretation"] = (
            "통합 카탈로그 후보로 포함 승인. 전체 분류·안전·권리·미디어 승인이 아님."
        )
    if not text(row.get("reviewed_decision")) and text(row.get("review_decision")) == "INCLUDE":
        row["reviewed_decision"] = "INCLUDE"

    raw_instruction = ""
    raw_steps = ""
    if source_system == "gymvisual":
        raw = gymvisual_raw_by_id().get(source_id, {})
        instructions = raw.get("instructions", {}) if isinstance(raw, dict) else {}
        steps = raw.get("instruction_steps", {}) if isinstance(raw, dict) else {}
        if isinstance(instructions, dict):
            raw_instruction = text(instructions.get("en"))
        if isinstance(steps, dict):
            raw_steps = json.dumps(steps.get("en", []), ensure_ascii=False)
    row["raw_source_instruction_en"] = raw_instruction
    row["raw_source_instruction_steps_en"] = raw_steps
    row["setup_guide"] = "REVIEW_REQUIRED"
    row["execution_steps"] = "REVIEW_REQUIRED"
    row["breathing_guide"] = "REVIEW_REQUIRED"
    row["finish_guide"] = "REVIEW_REQUIRED"
    row["guide_source_url"] = {
        "gymvisual": "https://github.com/hasaneyldrm/exercises-dataset",
        "wger": "https://wger.de/",
        "kspo": "https://www.data.go.kr/data/15108846/openapi.do",
    }[source_system]
    row["guide_review_status"] = "REVIEW_REQUIRED" if raw_instruction else "SOURCE_REQUIRED"
    row["guide_review_note"] = (
        "원천 영어 지침과 단계는 raw 필드에 보존했으며 한국어 사용자 가이드는 사람 검토 필요."
        if raw_instruction
        else "현재 입력에 검증 가능한 실행 지침 원문이 없어 추측하지 않음."
    )

    row["safety_warning"] = "REVIEW_REQUIRED"
    row["contraindications"] = "REVIEW_REQUIRED"
    row["common_mistakes"] = "REVIEW_REQUIRED"
    row["stop_conditions"] = (
        "통증, 어지럼증, 흉통, 비정상적인 호흡곤란이 발생하면 즉시 중단하고 필요한 경우 전문가와 상담하세요."
    )
    row["safety_source_url"] = ""
    row["safety_review_status"] = "REVIEW_REQUIRED"

    metadata_path = {
        "gymvisual": GYMVISUAL_SOURCE_META,
        "wger": WGER_SOURCE_META,
        "kspo": KSPO_SOURCE_META,
    }[source_system]
    license_fields(row, load_json(metadata_path))
    row["media_link_status"] = "PENDING_POST_INTEGRATION_VALIDATION"
    row["media_link_note"] = "통합 카탈로그 검증 완료 후 이미지/GIF/영상 실물 연결 필요"
    row["media_validation_status"] = "PENDING"
    row["media_source_reference"] = text(row.get("source_media_reference")) or "REVIEW_REQUIRED"

    for field in (
        "review_required",
        "review_required_codes",
        "review_status",
        "review_decision",
        "reviewed_decision",
        "review_normalized_exercise_id",
        "source_attribution",
        "source_license",
        "source_license_author",
        "source_media_reference",
    ):
        row[f"raw_{field}"] = (
            legacy_review_values[field] if field in legacy_review_values else raw_value(row, field)
        )

    blockers: list[str] = []
    if codes:
        blockers.append("REVIEW_REQUIRED_CODES_PRESENT")
    if text(row.get("review_status")) != "FINAL_APPROVED":
        blockers.append("FINAL_APPROVAL_REQUIRED")
    if not text(row.get("reviewer")) or not text(row.get("reviewed_at")):
        blockers.append("FINAL_REVIEWER_AND_TIME_REQUIRED")
    classification_fields = (
        "name_ko",
        "reviewed_training_type_code",
        "reviewed_movement_pattern_code",
        "reviewed_exercise_family",
        "reviewed_equipment_codes",
        "reviewed_location_codes",
        "reviewed_difficulty_code",
    )
    if any(
        not text(row.get(field)) or "REVIEW_REQUIRED" in text(row.get(field))
        for field in classification_fields
    ):
        blockers.append("CLASSIFICATION_REVIEW_REQUIRED")
    if row["guide_review_status"] != "APPROVED":
        blockers.append("GUIDE_REVIEW_REQUIRED")
    if row["safety_review_status"] != "APPROVED":
        blockers.append("SAFETY_REVIEW_REQUIRED")
    if row["license_review_status"] != "APPROVED":
        blockers.append("LICENSE_REVIEW_REQUIRED")
    if row["media_validation_status"] != "VALIDATED":
        blockers.append("MEDIA_VALIDATION_REQUIRED")
    row["production_eligibility_blockers"] = "|".join(dict.fromkeys(blockers))
    row["production_eligible"] = "true" if not blockers else "false"


def aliases_for_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    aliases: list[dict[str, str]] = []
    for row in rows:
        common = {
            "normalized_exercise_id": row["normalized_exercise_id"],
            "source_system": row["source_system"],
            "source_id": row["source_id"],
            "alias_review_status": "REVIEW_REQUIRED",
        }
        if text(row.get("source_name")):
            aliases.append(
                {**common, "alias_type": "SOURCE_NAME", "alias_value": row["source_name"]}
            )
        if text(row.get("reviewed_name_ko")):
            aliases.append(
                {**common, "alias_type": "REVIEWED_NAME_KO", "alias_value": row["reviewed_name_ko"]}
            )
        if text(row.get("legacy_review_normalized_exercise_id")):
            aliases.append(
                {
                    **common,
                    "alias_type": "LEGACY_NORMALIZED_ID",
                    "alias_value": row["legacy_review_normalized_exercise_id"],
                }
            )
    aliases.sort(
        key=lambda item: (item["normalized_exercise_id"], item["alias_type"], item["alias_value"])
    )
    for index, alias in enumerate(aliases, start=1):
        alias["alias_id"] = f"ALIAS-{index:06d}"
    return aliases


def empty_row() -> dict[str, str]:
    return {column: "" for column in OUTPUT_COLUMNS}


def gymvisual_row(
    source: dict[str, str], *, training_type_code: str | None = None
) -> dict[str, str]:
    row = empty_row()
    row["raw_source_record_json"] = text(source.get("_raw_source_record_json")) or json.dumps(
        source, ensure_ascii=False, sort_keys=True
    )
    candidate_id = text(source.get("candidate_id"))
    equipment = text(source.get("equipment_code_candidate")) or map_equipment(
        source.get("source_equipment")
    )
    location = text(source.get("location_code_candidates")) or map_locations("")
    target = text(source.get("target")) or map_target(source.get("source_target"))
    movement = text(source.get("movement_pattern_code_candidate")) or "REVIEW_REQUIRED"
    row.update(
        {
            "source_track": "gymvisual",
            "source_identity": candidate_id,
            "candidate_id": candidate_id,
            "source_name": text(source.get("source_name")),
            "source_body_part": text(source.get("source_body_part")),
            "source_category": text(source.get("source_category")),
            "source_location": location,
            "source_scope_status": "GYMVISUAL_REVIEW_BATCH",
            "source_target": text(source.get("source_target")) or text(source.get("target")),
            "source_equipment": text(source.get("source_equipment")),
            "source_media_reference": (
                f"image:{text(source.get('source_image'))};gif:{text(source.get('source_gif_url'))}"
            ),
            "source_media_id": text(source.get("source_media_id")),
            "source_image": text(source.get("source_image")),
            "source_gif_url": text(source.get("source_gif_url")),
            "target": target,
            "mobility_goal_code": "REVIEW_REQUIRED",
            "body_area_codes_candidate": "REVIEW_REQUIRED",
            "movement_pattern_candidate": movement,
            "movement_pattern_code_candidate": movement,
            "exercise_family_candidate": text(source.get("exercise_family_candidate"))
            or "REVIEW_REQUIRED",
            "variant_group_candidate": "REVIEW_REQUIRED",
            "equipment_code_candidate": equipment,
            "equipment_label_candidate": text(source.get("equipment_label_candidate"))
            or "REVIEW_REQUIRED",
            "location_code_candidates": location,
            "training_type_code_candidate": training_type_code
            or ("CARDIO" if movement == "GAIT" else "STRENGTH"),
            "difficulty_code_candidate": normalize_difficulty_candidate(
                source.get("difficulty_code_candidate")
            ),
            "beginner_suitability_candidate": text(source.get("beginner_suitability_candidate"))
            or "REVIEW_REQUIRED",
            "impact_level_candidate": text(source.get("impact_level_candidate"))
            or "REVIEW_REQUIRED",
            "exercise_mode_candidates": text(source.get("exercise_mode_candidates"))
            or "REVIEW_REQUIRED",
            "space_noise_level_candidate": text(source.get("space_noise_level_candidate"))
            or "REVIEW_REQUIRED",
            "intensity_level_candidate": text(source.get("intensity_level_candidate"))
            or "REVIEW_REQUIRED",
            "met_value": text(source.get("met_value")),
            "load_profile_candidate": "REVIEW_REQUIRED",
            "screening_decision": text(source.get("screening_decision")) or "HOLD",
            "screening_reason_code": text(source.get("screening_reason_code")),
            "screening_reason": text(source.get("screening_reason")),
            "selection_rank": text(source.get("selection_rank")),
            "selection_recommendation": text(source.get("selection_recommendation"))
            or "REVIEW_REQUIRED",
            "review_required": "true",
            "review_required_codes": text(source.get("review_required_codes"))
            or "HUMAN_TAXONOMY_REVIEW_REQUIRED",
            "alternative_relation_status": "NOT_CREATED_BY_DESIGN",
            "visual_reference_status": "REFERENCE_ONLY",
            "review_decision": "PENDING",
            "review_reason_code": "INTEGRATED_REVIEW_REQUIRED",
            "review_note": "Gym Visual 선정 후보. 통합 taxonomy·중복·안전 검수 필요.",
            "alignment_required_codes": "HUMAN_TAXONOMY_REVIEW_REQUIRED",
            "alignment_status": "REVIEW_REQUIRED",
            "review_status": "DRAFT",
            "production_eligible": "false",
            "source_license": "MIT",
            "source_license_author": "© Gym visual — https://gymvisual.com/",
        }
    )
    row["reviewed_difficulty_code"] = reviewed_difficulty_code(row)
    return row


def variant_index() -> dict[str, dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in load_csv(GYMVISUAL_VARIANTS):
        if text(item.get("variant_candidate_id")) in BODYWEIGHT_SUBSTITUTABLE_VARIANT_IDS:
            continue
        grouped[text(item.get("variant_candidate_id"))].append(item)
    result = {}
    for candidate_id, items in grouped.items():
        result[candidate_id] = {
            "variant_relation_representative_ids": unique_pipe(
                [text(x.get("representative_id")) for x in items]
            ),
            "variant_relation_representative_names": unique_pipe(
                [text(x.get("representative_name")) for x in items]
            ),
            "variant_relation_equipment_codes": unique_pipe(
                [map_equipment(x.get("variant_equipment")) for x in items]
            ),
            "variant_relation_location_codes": unique_pipe(
                [pipe(x.get("location_code_candidates")) for x in items]
            ),
            "variant_relation_media_ids": unique_pipe(
                [text(x.get("variant_media_id")) for x in items]
            ),
            "variant_relation_review_decision": unique_pipe(
                [text(x.get("review_decision")) or "PENDING" for x in items]
            ),
            "variant_relation_note": "변형 관계 후보이며 대체 관계는 사람 검수 전 확정하지 않음.",
        }
    return result


def variant_source(candidate_id: str, item: dict[str, str]) -> dict[str, str]:
    """Convert one variant candidate into the common source-row shape."""
    return {
        "_raw_source_record_json": json.dumps(item, ensure_ascii=False, sort_keys=True),
        "candidate_id": candidate_id,
        "source_name": text(item.get("variant_name")),
        "source_target": text(item.get("variant_target")),
        "source_equipment": text(item.get("variant_equipment")),
        "source_media_id": text(item.get("variant_media_id")),
        "source_image": text(item.get("variant_image")),
        "source_gif_url": text(item.get("variant_gif_url")),
        "target": text(item.get("variant_target")),
        "movement_pattern_code_candidate": "REVIEW_REQUIRED",
        "exercise_family_candidate": text(item.get("exercise_family_candidate")),
        "equipment_code_candidate": map_equipment(item.get("variant_equipment")),
        "location_code_candidates": text(item.get("location_code_candidates")),
        "difficulty_code_candidate": "REVIEW_REQUIRED",
        "beginner_suitability_candidate": "REVIEW_REQUIRED",
        "screening_decision": text(item.get("auto_candidate_decision")) or "HOLD",
        "screening_reason_code": text(item.get("auto_candidate_reason_code")),
        "screening_reason": text(item.get("auto_candidate_reason")),
        "selection_recommendation": "REVIEW_REQUIRED",
    }


def mobility_row(source: dict[str, str]) -> dict[str, str]:
    """Convert a reviewed Gym Visual mobility row to the common shape."""
    row = empty_row()
    row["raw_source_record_json"] = json.dumps(source, ensure_ascii=False, sort_keys=True)
    candidate_id = text(source.get("candidate_id"))
    source_image = text(source.get("source_image"))
    source_gif_url = text(source.get("source_gif_url"))
    location = pipe(source.get("location_code_candidates"))
    training_type = text(source.get("training_type_code_candidate"))
    if training_type != "MOBILITY":
        raise ValueError(f"mobility input must use MOBILITY: {source.get('candidate_id')}")
    row.update(
        {
            "source_track": "gymvisual",
            "source_identity": candidate_id,
            "candidate_id": candidate_id,
            "source_name": text(source.get("source_name")),
            "source_body_part": text(source.get("source_body_part")),
            "source_category": "mobility",
            "source_location": location,
            "source_scope_status": "GYMVISUAL_MOBILITY_REVIEW_BATCH",
            "source_target": text(source.get("source_target")),
            "source_equipment": text(source.get("source_equipment")),
            "source_media_reference": f"image:{source_image};gif:{source_gif_url}",
            "source_media_id": text(source.get("source_media_id")),
            "source_image": source_image,
            "source_gif_url": source_gif_url,
            "target": text(source.get("source_target")),
            "mobility_goal_code": text(source.get("mobility_goal_code")),
            "body_area_codes_candidate": pipe(source.get("body_area_codes_candidate")),
            "movement_pattern_candidate": text(source.get("movement_pattern_code_candidate")),
            "movement_pattern_code_candidate": text(source.get("movement_pattern_code_candidate")),
            "exercise_family_candidate": text(source.get("exercise_family_candidate")),
            "variant_group_candidate": text(source.get("variant_group_candidate")),
            "equipment_code_candidate": text(source.get("equipment_code_candidate")),
            "equipment_label_candidate": text(source.get("source_equipment")),
            "location_code_candidates": location,
            "training_type_code_candidate": "MOBILITY",
            "difficulty_code_candidate": normalize_difficulty_candidate(
                source.get("difficulty_code_candidate")
            ),
            "beginner_suitability_candidate": text(source.get("beginner_suitability_candidate")),
            "load_profile_candidate": text(source.get("load_profile_candidate")),
            "screening_decision": text(source.get("selection_screening_decision")),
            "selection_rank": text(source.get("selection_rank")),
            "selection_recommendation": "REVIEW_REQUIRED",
            "review_required": "true",
            "review_required_codes": pipe(source.get("review_required_codes")),
            "alternative_relation_status": text(source.get("alternative_relation_status")),
            "visual_reference_status": "REFERENCE_ONLY",
            "review_decision": text(source.get("review_decision")) or "PENDING",
            "review_reason_code": "INTEGRATED_REVIEW_REQUIRED",
            "review_note": "Gym Visual 가동성 후보. family·변형·부하·안전 검수 필요.",
            "review_status": "DRAFT",
            "production_eligible": "false",
            "source_license": "MIT",
            "source_license_author": "© Gym visual — https://gymvisual.com/",
        }
    )
    row["reviewed_difficulty_code"] = reviewed_difficulty_code(row)
    return row


def overlay_wger(row: dict[str, str], attrs: dict[str, str]) -> None:
    source_identity = text(row.get("source_identity"))
    target = WGER_TARGET_OVERRIDES.get(source_identity, text(row.get("target")))
    review_note = "wger INCLUDE 속성 검수 결과를 통합 스키마에 반영."
    if source_identity == "1603":
        review_note += " 원천 데이터 불일치: 운동명은 Leg Curl이나 원본 근육은 Gastrocnemius."
    row.update(
        {
            "review_normalized_exercise_id": text(attrs.get("review_normalized_exercise_id")),
            "target": target,
            "reviewed_name_ko": text(attrs.get("review_display_name_ko")),
            "reviewed_target": text(attrs.get("body_focus_code")),
            "reviewed_body_area_codes": pipe(attrs.get("primary_body_area_codes")),
            "reviewed_training_type_code": text(attrs.get("training_type_code")),
            "reviewed_movement_pattern_code": text(attrs.get("primary_movement_pattern_code")),
            "reviewed_equipment_codes": pipe(attrs.get("equipment_codes")),
            "reviewed_location_codes": pipe(attrs.get("location_codes")),
            "reviewed_difficulty_code": reviewed_difficulty_code(
                row, source_difficulty=attrs.get("difficulty_code")
            ),
            "reviewed_decision": "INCLUDE",
            "review_status": "DOMAIN_APPROVED",
            "review_decision": "INCLUDE",
            "review_note": review_note,
        }
    )


def apply_taxonomy_review(row: dict[str, str]) -> None:
    """Apply reviewed candidate family/pattern values without inventing codes."""

    track = text(row.get("source_track"))
    identity = text(row.get("source_identity"))
    name = text(row.get("source_name"))
    override: tuple[str, str] | None = None

    if track == "gymvisual":
        if text(row.get("source_scope_status")) == "GYMVISUAL_MOBILITY_REVIEW_BATCH":
            return
        override = GYMVISUAL_TAXONOMY_OVERRIDES.get(identity)
        if override is None:
            family = text(row.get("exercise_family_candidate"))
            movement = GYMVISUAL_FAMILY_MOVEMENT_PATTERNS.get(family)
            if movement is not None:
                override = (family, movement)
    elif track == "wger":
        override = WGER_TAXONOMY_OVERRIDES.get(identity)
    elif track == "kspo":
        override = KSPO_TAXONOMY_OVERRIDES.get(name)

    if override is None:
        return
    family, movement = override
    row["exercise_family_candidate"] = family
    row["movement_pattern_candidate"] = movement
    row["movement_pattern_code_candidate"] = movement
    if track == "gymvisual":
        if identity in GYMVISUAL_CROSS_FAMILY_VARIANT_IDS:
            for field in VARIANT_COLUMNS:
                row[field] = ""
        elif identity in GYMVISUAL_VARIANT_REFERENCE_OVERRIDES:
            representative_id, representative_name = GYMVISUAL_VARIANT_REFERENCE_OVERRIDES[identity]
            row["variant_relation_representative_ids"] = representative_id
            row["variant_relation_representative_names"] = representative_name


def validate_variant_references(rows: list[dict[str, str]]) -> None:
    """Fail closed on missing or self-referencing Gym Visual representatives."""

    gymvisual_ids = {
        text(row.get("source_identity"))
        for row in rows
        if text(row.get("source_track")) == "gymvisual"
    }
    issues: list[str] = []
    for row in rows:
        if text(row.get("source_track")) != "gymvisual":
            continue
        identity = text(row.get("source_identity"))
        refs = [
            part for part in text(row.get("variant_relation_representative_ids")).split("|") if part
        ]
        names = [
            part
            for part in text(row.get("variant_relation_representative_names")).split("|")
            if part
        ]
        if len(refs) != len(names):
            issues.append(f"{identity}: representative id/name length mismatch")
        for reference in refs:
            if reference not in gymvisual_ids:
                issues.append(f"{identity}: missing representative {reference}")
            if reference == identity:
                issues.append(f"{identity}: self-referencing representative")
    if issues:
        raise ValueError("invalid variant representative references: " + "; ".join(issues))


def build(*, include_mobility: bool = True) -> list[dict[str, str]]:
    variant_by_id = variant_index()
    gymvisual: dict[str, dict[str, str]] = {}
    for path in (GYMVISUAL_CARDIO, GYMVISUAL_STRENGTH):
        for source in load_csv(path):
            if path == GYMVISUAL_STRENGTH and source.get("screening_decision") != "INCLUDE":
                continue
            training_type_code = "CARDIO" if path == GYMVISUAL_CARDIO else "STRENGTH"
            row = gymvisual_row(source, training_type_code=training_type_code)
            gymvisual.setdefault(row["candidate_id"], row)
    variant_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in load_csv(GYMVISUAL_VARIANTS):
        if text(item.get("variant_candidate_id")) in BODYWEIGHT_SUBSTITUTABLE_VARIANT_IDS:
            continue
        variant_rows[text(item.get("variant_candidate_id"))].append(item)
    for candidate_id, items in variant_rows.items():
        row = gymvisual_row(variant_source(candidate_id, items[0]), training_type_code="STRENGTH")
        row.update(variant_by_id.get(candidate_id, {}))
        row["source_scope_status"] = "GYMVISUAL_VARIANT_REVIEW_BATCH"
        row["review_note"] = (
            "Gym Visual 변형 후보. 대표 운동과의 관계·중복·초보자 적합성 검수 필요."
        )
        gymvisual.setdefault(candidate_id, row)
    rows = list(gymvisual.values())
    for source in load_csv(KSPO):
        source_name = text(source.get("source_name"))
        row = empty_row()
        row["raw_source_record_json"] = json.dumps(source, ensure_ascii=False, sort_keys=True)
        row.update(source)
        row["difficulty_code_candidate"] = normalize_difficulty_candidate(
            row.get("difficulty_code_candidate")
        )
        row["target"] = KSPO_TARGET_OVERRIDES.get(source_name, text(row.get("target")))
        row["training_type_code_candidate"] = KSPO_TRAINING_TYPE_OVERRIDES.get(
            source_name, "REVIEW_REQUIRED"
        )
        row["review_note"] = "KSPO 초보자 보충 후보. 사람 검수 전 보류."
        if source_name in KSPO_TARGET_REVIEW_NOTES:
            row["review_note"] += " " + KSPO_TARGET_REVIEW_NOTES[source_name]
        row["reviewed_difficulty_code"] = reviewed_difficulty_code(row)
        rows.append(row)
    if include_mobility:
        mobility = [mobility_row(source) for source in load_csv(GYMVISUAL_MOBILITY)]
        if len(mobility) != MOBILITY_ROW_COUNT:
            raise ValueError(f"unexpected mobility row count: {len(mobility)}")
        rows.extend(mobility)
    aligned = {(r["source_track"], r["source_identity"]): r for r in load_csv(ALIGNED)}
    for attrs in load_csv(WGER_ATTRS):
        aligned_source = aligned.get(("wger", text(attrs.get("source_identity"))))
        if aligned_source is None:
            raise ValueError(
                f"wger identity missing from aligned batch: {attrs.get('source_identity')}"
            )
        row = empty_row()
        row["raw_source_record_json"] = json.dumps(
            {"aligned": aligned_source, "attributes": attrs}, ensure_ascii=False, sort_keys=True
        )
        row.update(aligned_source)
        row["difficulty_code_candidate"] = normalize_difficulty_candidate(
            row.get("difficulty_code_candidate")
        )
        overlay_wger(row, attrs)
        rows.append(row)
    for row in rows:
        apply_taxonomy_review(row)
        finalize_equipment_and_location(row)
    try:
        registry = load_registry(REGISTRY_PATH)
    except RegistryError as exc:
        raise ValueError(
            "permanent ID registry is missing or invalid; run "
            "bootstrap_integrated_catalog_registry.py explicitly"
        ) from exc
    for row in rows:
        enrich_catalog_fields(row, registry)
    rows.sort(key=lambda r: (r["source_track"], r["source_identity"]))
    keys = [(r["source_track"], r["source_identity"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("source_track + source_identity 중복")
    expected_count = INTEGRATED_ROW_COUNT if include_mobility else LEGACY_ROW_COUNT
    if len(rows) != expected_count:
        raise ValueError(f"unexpected integrated row count: {len(rows)}")
    invalid_training_types = [
        (row["source_track"], row["source_identity"], row["training_type_code_candidate"])
        for row in rows
        if row["training_type_code_candidate"] not in ALLOWED_TRAINING_TYPES
    ]
    if invalid_training_types:
        raise ValueError(f"training_type_code_candidate is not allowed: {invalid_training_types}")
    for field in ("candidate_id", "source_media_id"):
        values = [text(row[field]) for row in rows]
        if not all(values) or len(values) != len(set(values)):
            raise ValueError(f"{field} missing or duplicated")
    invalid_targets = [
        (row["source_track"], row["source_identity"], row["target"])
        for row in rows
        if row["source_track"] in {"kspo", "wger"} and row["target"] not in GYMVISUAL_TARGETS
    ]
    if invalid_targets:
        raise ValueError(f"KSPO/wger target is not a Gym Visual value: {invalid_targets}")
    invalid_difficulties = [
        (
            row["source_track"],
            row["source_identity"],
            row["difficulty_code_candidate"],
            row["reviewed_difficulty_code"],
        )
        for row in rows
        if row["difficulty_code_candidate"] not in DIFFICULTY_CANDIDATE_CODES
        or row["reviewed_difficulty_code"] not in DIFFICULTY_CODES
    ]
    if invalid_difficulties:
        raise ValueError(f"difficulty normalization failed: {invalid_difficulties}")
    validate_variant_references(rows)
    return rows


def write_aliases(rows: list[dict[str, str]]) -> None:
    aliases = aliases_for_rows(rows)
    columns = [
        "alias_id",
        "normalized_exercise_id",
        "source_system",
        "source_id",
        "alias_type",
        "alias_value",
        "alias_review_status",
    ]
    with OUTPUT_ALIASES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(aliases)


def main() -> None:
    rows = build()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_schema(OUTPUT_COLUMNS)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    write_aliases(rows)
    inputs = [
        GYMVISUAL_CARDIO,
        GYMVISUAL_STRENGTH,
        GYMVISUAL_VARIANTS,
        GYMVISUAL_MOBILITY,
        KSPO,
        WGER_ATTRS,
        ALIGNED,
    ]
    manifest = {
        "schema_version": "1.0",
        "version_code": "gymvisual-integrated-review-v0.5.0",
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "purpose": (
            "Selected Gym Visual cardio/strength/mobility rows with variant relations, "
            "KSPO supplement, and reviewed wger attributes"
        ),
        "row_counts": {
            "gymvisual_cardio": 10,
            "gymvisual_strength_representative": 42,
            "gymvisual_variant_rows": 85,
            "gymvisual_variant_unique_ids": 84,
            "gymvisual_mobility": 35,
            "gymvisual_total_exercise_rows": 171,
            "kspo": 10,
            "wger": 27,
            "total": len(rows),
        },
        "inputs": [
            {"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256(path)} for path in inputs
        ],
        "output": {
            "path": str(OUTPUT_CSV.relative_to(REPO_ROOT)),
            "sha256": sha256(OUTPUT_CSV),
            "records": len(rows),
        },
        "value_policy": {
            "unknown_value": "REVIEW_REQUIRED",
            "raw_source_values_preserved": True,
            "variant_file_is_exercise_and_relation_input": True,
            "kspo_status": "TRAINING_TYPE_CONFIRMED; OTHER_REVIEW_FIELDS_PENDING",
            "mobility_status": "MOBILITY_TRAINING_TYPE_PRESERVED; OTHER_REVIEW_FIELDS_PENDING",
            "wger_attribute_status": "INCLUSION_APPROVED_INPUT; production_eligible remains false",
            "review_status_definitions": {
                "DOMAIN_APPROVED": "legacy input only; mapped to INCLUSION_APPROVED",
                "INCLUSION_APPROVED": "candidate inclusion only, not final approval",
                "PARTIALLY_APPROVED": "partial review only",
                "FINAL_APPROVED": "requires reviewer, reviewed_at, no unresolved review codes, and all gates",
            },
            "production_gate": {
                "requires": [
                    "required classification",
                    "review_required=false",
                    "FINAL_APPROVED with reviewer and reviewed_at",
                    "guide_review_status=APPROVED",
                    "safety_review_status=APPROVED",
                    "license_review_status=APPROVED",
                    "media_validation_status=VALIDATED",
                ],
                "default": False,
            },
            "permanent_id_registry": {
                "path": str(REGISTRY_PATH.relative_to(REPO_ROOT)),
                "key": ["source_system", "source_id"],
                "catalog_id_immutable": True,
                "normalized_exercise_id_immutable": True,
            },
            "training_type_policy": {
                "allowed_values": sorted(ALLOWED_TRAINING_TYPES),
                "kspo_overrides": KSPO_TRAINING_TYPE_OVERRIDES,
                "mobility_source": "gymvisual_mobility_reviewed.csv",
            },
            "difficulty_policy": {
                "standard_codes": sorted(DIFFICULTY_CODES),
                "candidate_invalid_values": {"CONDITIONAL": "REVIEW_REQUIRED"},
                "dimensions": [
                    "technical_complexity",
                    "balance_and_control",
                    "equipment_handling",
                    "joint_and_load_demand",
                ],
                "beginner_suitability_is_independent": True,
                "cross_source_overrides": {
                    f"{track}:{identity}": code
                    for (track, identity), code in DIFFICULTY_CROSS_SOURCE_OVERRIDES.items()
                },
            },
            "target_policy": {
                "allowed_values": sorted(GYMVISUAL_TARGETS),
                "applies_to_source_tracks": ["kspo", "wger"],
                "biceps_femoris": "hamstrings",
            },
            "exercise_taxonomy_policy": {
                "approved_movement_pattern_codes": sorted(
                    {
                        "VERTICAL_PULL",
                        "HORIZONTAL_PULL",
                        "HORIZONTAL_PUSH",
                        "VERTICAL_PUSH",
                        "KNEE_DOMINANT",
                        "HIP_DOMINANT",
                        "KNEE_FLEXION",
                        "ISOLATION",
                        "GAIT",
                        "CORE_BRACE",
                        "MOBILITY_STRETCH",
                    }
                ),
                "unresolved_value": "REVIEW_REQUIRED",
                "family_rule": (
                    "equipment_grip_posture_variants_share_a_family; "
                    "different_joint_action_is_separate"
                ),
                "unresolved_rows": [
                    f"{row['source_track']}:{row['source_identity']}"
                    for row in rows
                    if "REVIEW_REQUIRED"
                    in (
                        row["exercise_family_candidate"],
                        row["movement_pattern_code_candidate"],
                    )
                ],
            },
            "equipment_policy": {
                "source_candidate_reviewed_fields": [
                    "source_equipment",
                    "equipment_code_candidate",
                    "reviewed_equipment_codes",
                ],
                "final_fields": [
                    "equipment_code_candidate",
                    "reviewed_equipment_codes",
                    "location_code_candidates",
                    "reviewed_location_codes",
                ],
                "required_equipment_only": True,
                "fixed_cardio_machine_code": "MACHINE",
                "draft_only_codes_pending_public_taxonomy_approval": [
                    "FOAM_ROLLER",
                    "MEDICINE_BALL",
                    "ROPE",
                    "STEP_BOX",
                    "SUSPENSION_STRAPS",
                ],
                "support_equipment_inference": (
                    "Only named execution supports such as bench, pull-up bar, chair, "
                    "step box, stability ball, and suspension straps are added; walls "
                    "and floors are not equipment."
                ),
                "location_policy": {
                    "outdoor_code": "removed",
                    "outdoor_capable_candidates": "GYM added; existing HOME preserved",
                },
            },
            "media_policy": {
                "media_link_status": "PENDING_POST_INTEGRATION_VALIDATION",
                "media_link_note": "통합 카탈로그 검증 완료 후 이미지/GIF/영상 실물 연결 필요",
                "media_binary_created_by_this_pipeline": False,
            },
            "raw_preservation": {
                "raw_source_record_json": True,
                "raw_fields": RAW_COLUMNS,
            },
        },
        "registry": {
            "path": str(REGISTRY_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256(REGISTRY_PATH),
        },
        "alias_output": {
            "path": str(OUTPUT_ALIASES.relative_to(REPO_ROOT)),
            "sha256": sha256(OUTPUT_ALIASES),
            "records": len(aliases_for_rows(rows)),
        },
    }
    OUTPUT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(OUTPUT_CSV)


if __name__ == "__main__":
    main()
