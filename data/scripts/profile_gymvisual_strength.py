# ruff: noqa: E501

"""Profile and screen Gym Visual strength representatives.

This is stage 2 only.  It preserves the raw record and source provenance,
records candidate taxonomy/family labels, and creates a human review queue.
It intentionally does not create normalized exercises, safety rules,
alternatives, or a catalog seed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data/raw/gym_visual"
DEFAULT_PROFILE = REPO_ROOT / "data/validation/profiles/gymvisual_strength_profile.json"
DEFAULT_REVIEW_BATCH = (
    REPO_ROOT / "data/validation/review_batches/gymvisual_strength_representative_review.csv"
)

PROFILE_VERSION = "gymvisual-strength-profile-v0.1.0"
REVIEW_BATCH_VERSION = "gymvisual-strength-representative-review-v0.1.0"

TARGETS = [
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
]

# These are representative candidates, not final exercise_family_code values.
# IDs are stable only within the immutable Gym Visual snapshot.
INCLUDE_SPECS: dict[str, dict[str, dict[str, Any]]] = {
    "lats": {
        "0198": {
            "family": "LAT_PULLDOWN_CANDIDATE",
            "movement": "VERTICAL_PULL",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "케이블 랫풀다운은 target을 직접 대표하고 부하 조절이 쉬운 초보·복귀용 수직 당기기 대표군임.",
        },
        "0073": {
            "family": "BARBELL_PULLOVER_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "바벨 풀오버는 수직 당기기와 다른 어깨 폄 계열의 랫 보조 대표군으로 장비·자세 다양성을 보완함.",
        },
        "1355": {
            "family": "ONE_ARM_WALL_LATS_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "REVIEW_REQUIRED",
            "beginner": "REVIEW_REQUIRED",
            "rank": 3,
            "reason": "기존 HOLD 후보를 대표 후보로 포함하되, 원천 명칭과 lats target의 실제 동작 관계는 사람 검토를 유지함.",
        },
    },
    "upper back": {
        "0861": {
            "family": "SEATED_CABLE_ROW_CANDIDATE",
            "movement": "HORIZONTAL_PULL",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "시티드 케이블 로우는 상부 등 target을 대표하는 수평 당기기이며 안정된 자세와 부하 조절이 가능함.",
        },
        "0499": {
            "family": "INVERTED_ROW_CANDIDATE",
            "movement": "HORIZONTAL_PULL",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "인버티드 로우는 케이블·프리웨이트와 다른 체중 수평 당기기 대표군임.",
        },
        "3541": {
            "family": "INCLINE_Y_RAISE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 3,
            "reason": "인클라인 Y 레이즈는 로우와 다른 견갑·상부 등 보조 패턴을 대표함.",
        },
    },
    "spine": {
        "0489": {
            "family": "BODYWEIGHT_BACK_EXTENSION_CANDIDATE",
            "movement": "HIP_DOMINANT",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 1,
            "reason": "기본 하이퍼익스텐션은 spine target에서 명확한 신전 계열 대표군이며 원천 동작명이 분명함.",
        },
        "1352": {
            "family": "LOWER_BACK_CURL_CANDIDATE",
            "movement": "CORE_BRACE",
            "difficulty": "REVIEW_REQUIRED",
            "beginner": "REVIEW_REQUIRED",
            "rank": 2,
            "reason": "기존 HOLD 후보를 대표 후보로 포함하되, lower back curl의 실제 척추 움직임과 근력 범위는 사람 검토를 유지함.",
        },
    },
    "traps": {
        "0406": {
            "family": "DUMBBELL_SHRUG_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "덤벨 슈러그는 traps를 직접 겨냥하는 단순하고 접근성 높은 대표군임.",
        },
        "0688": {
            "family": "SCAPULAR_PULL_UP_CANDIDATE",
            "movement": "VERTICAL_PULL",
            "difficulty": "INTERMEDIATE",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "기존 HOLD 후보를 대표 후보로 포함하되, 초보·복귀 적합성과 수직 당기기 패턴 경계는 사람 검토를 유지함.",
        },
    },
    "pectorals": {
        "0662": {
            "family": "PUSH_UP_CANDIDATE",
            "movement": "HORIZONTAL_PUSH",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "푸시업은 홈·헬스장 모두 활용 가능한 수평 밀기 대표군이며 초보 회귀가 쉬움.",
        },
        "0227": {
            "family": "CABLE_FLY_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "케이블 플라이는 푸시업·벤치프레스와 다른 가슴 모음/고립 대표군으로 장비 활용도를 보완함.",
        },
    },
    "forearms": {
        "0126": {
            "family": "WRIST_CURL_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "바벨 손목 컬은 전완 굴곡 대표군으로 동작과 목적이 명확함.",
        },
        "0082": {
            "family": "REVERSE_WRIST_CURL_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 2,
            "reason": "리버스 손목 컬은 손목 컬과 반대 방향의 전완 신전 대표군임.",
        },
        "0854": {
            "family": "HAND_GRIP_SQUEEZE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 3,
            "reason": "손 쥐기 동작은 손목 컬과 다른 악력·그립 대표군으로 홈 활용도가 높음.",
        },
    },
    "calves": {
        "1373": {
            "family": "BODYWEIGHT_STANDING_CALF_RAISE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "맨몸 스탠딩 카프 레이즈는 장비 없이 종아리의 기본 발바닥 굽힘 대표군임.",
        },
        "0088": {
            "family": "SEATED_CALF_RAISE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "시티드 카프 레이즈는 서서 하는 종목과 다른 무릎 자세의 종아리 대표군임.",
        },
        "1000": {
            "family": "REVERSE_CALF_RAISE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 3,
            "reason": "리버스 카프 레이즈는 일반 카프 레이즈와 반대 발목 동작 후보로 방향성 다양성을 보완함.",
        },
    },
    "delts": {
        "0334": {
            "family": "DUMBBELL_LATERAL_RAISE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "덤벨 레터럴 레이즈는 어깨 측면 고립 대표군으로 단순하고 조절 가능함.",
        },
        "0405": {
            "family": "SEATED_SHOULDER_PRESS_CANDIDATE",
            "movement": "VERTICAL_PUSH",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "시티드 숄더 프레스는 레이즈와 다른 수직 밀기 대표군임.",
        },
        "0378": {
            "family": "DUMBBELL_REAR_FLY_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 3,
            "reason": "덤벨 리어 플라이는 전면·측면 레이즈와 다른 후면 어깨 대표군임.",
        },
        "0041": {
            "family": "BARBELL_FRONT_RAISE_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 4,
            "reason": "바벨 프론트 레이즈는 레터럴·프레스와 다른 전면 어깨 고립 패턴 후보임.",
        },
    },
    "biceps": {
        "0416": {
            "family": "DUMBBELL_STANDING_CURL_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "기본 스탠딩 컬은 이두 target의 가장 명확한 초보 대표군임.",
        },
        "0372": {
            "family": "DUMBBELL_PREACHER_CURL_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "프리처 컬은 기본 컬과 다른 팔꿈치 지지·고립 대표군임.",
        },
        "0140": {
            "family": "BODYWEIGHT_PULL_UP_BICEPS_CANDIDATE",
            "movement": "VERTICAL_PULL",
            "difficulty": "INTERMEDIATE",
            "beginner": "NOT_PRIORITY",
            "rank": 3,
            "reason": "친업은 컬 계열과 다른 복합 수직 당기기로 이두 대표성을 보완하지만 초보 접근성은 제한됨.",
        },
    },
    "triceps": {
        "0201": {
            "family": "CABLE_TRICEPS_PUSHDOWN_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "케이블 푸시다운은 부하 조절이 쉬운 삼두 고립 대표군임.",
        },
        "0109": {
            "family": "OVERHEAD_TRICEPS_EXTENSION_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "오버헤드 삼두 익스텐션은 푸시다운과 다른 어깨 위치의 팔꿈치 폄 대표군임.",
        },
        "0259": {
            "family": "CLOSE_GRIP_PUSH_UP_CANDIDATE",
            "movement": "HORIZONTAL_PUSH",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 3,
            "reason": "클로즈그립 푸시업은 고립 운동과 다른 맨몸 수평 밀기 대표군임.",
        },
    },
    "glutes": {
        "3013": {
            "family": "BODYWEIGHT_GLUTE_BRIDGE_CANDIDATE",
            "movement": "HIP_DOMINANT",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "맨몸 글루트 브리지는 홈에서 가능한 초보 친화적 엉덩관절 폄 대표군임.",
        },
        "3470": {
            "family": "BODYWEIGHT_FORWARD_LUNGE_CANDIDATE",
            "movement": "KNEE_DOMINANT",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "포워드 런지는 브리지와 다른 한쪽 다리 중심 하체 대표군임.",
        },
        "0032": {
            "family": "BARBELL_DEADLIFT_CANDIDATE",
            "movement": "HIP_DOMINANT",
            "difficulty": "INTERMEDIATE",
            "beginner": "NOT_PRIORITY",
            "rank": 3,
            "reason": "바벨 데드리프트는 브리지와 다른 전신 힙힌지 대표군이나 초보·복귀 우선도는 낮아 조건부 후보임.",
        },
    },
    "hamstrings": {
        "0599": {
            "family": "SEATED_LEG_CURL_CANDIDATE",
            "movement": "KNEE_FLEXION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "시티드 레그 컬은 햄스트링 무릎 굽힘을 직접 대표하고 기구로 부하 조절이 가능함.",
        },
        "0116": {
            "family": "BARBELL_STRAIGHT_LEG_DEADLIFT_CANDIDATE",
            "movement": "HIP_DOMINANT",
            "difficulty": "INTERMEDIATE",
            "beginner": "CONDITIONAL",
            "rank": 2,
            "reason": "스트레이트 레그 데드리프트는 레그 컬과 다른 힙힌지 대표군임.",
        },
    },
    "quads": {
        "2368": {
            "family": "BODYWEIGHT_SPLIT_SQUAT_CANDIDATE",
            "movement": "KNEE_DOMINANT",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 1,
            "reason": "맨몸 스플릿 스쿼트는 홈·헬스장 활용이 가능한 한쪽 다리 무릎 중심 대표군임.",
        },
        "0585": {
            "family": "MACHINE_LEG_EXTENSION_CANDIDATE",
            "movement": "ISOLATION",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 2,
            "reason": "레그 익스텐션은 스쿼트류와 다른 대퇴사두근 고립 대표군임.",
        },
        "1760": {
            "family": "DUMBBELL_GOBLET_SQUAT_CANDIDATE",
            "movement": "KNEE_DOMINANT",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 3,
            "reason": "고블릿 스쿼트는 스플릿 스쿼트와 다른 양발 무릎 중심 대표군이며 홈 활용도가 높음.",
        },
        "2796": {
            "family": "DUMBBELL_STEP_UP_LUNGE_CANDIDATE",
            "movement": "KNEE_DOMINANT",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 4,
            "reason": "스텝업 런지는 스쿼트·스플릿 스쿼트와 다른 높이 올라가기 패턴 후보임.",
        },
    },
    "abs": {
        "0274": {
            "family": "BODYWEIGHT_CRUNCH_CANDIDATE",
            "movement": "CORE_BRACE",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 1,
            "reason": "기본 크런치는 복부 굴곡 대표군으로 설명과 회귀가 쉬움.",
        },
        "0276": {
            "family": "DEAD_BUG_CANDIDATE",
            "movement": "CORE_BRACE",
            "difficulty": "BEGINNER",
            "beginner": "SUITABLE",
            "rank": 2,
            "reason": "데드버그는 크런치와 다른 누운 자세의 체간 안정화 대표군임.",
        },
        "0464": {
            "family": "PLANK_ROTATION_CANDIDATE",
            "movement": "CORE_BRACE",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 3,
            "reason": "플랭크 트위스트는 굴곡 운동과 다른 지지·회전 제어 대표군임.",
        },
        "0687": {
            "family": "BODYWEIGHT_RUSSIAN_TWIST_CANDIDATE",
            "movement": "CORE_BRACE",
            "difficulty": "CONDITIONAL",
            "beginner": "CONDITIONAL",
            "rank": 4,
            "reason": "러시안 트위스트는 크런치·플랭크와 다른 회전 대표군임.",
        },
        "0872": {
            "family": "BODYWEIGHT_REVERSE_CRUNCH_CANDIDATE",
            "movement": "CORE_BRACE",
            "difficulty": "BEGINNER",
            "beginner": "CONDITIONAL",
            "rank": 5,
            "reason": "리버스 크런치는 기본 크런치와 다른 골반 말아올리기 대표군임.",
        },
    },
}

HOLD_SPECS: dict[str, dict[str, dict[str, str]]] = {}

EXCLUDE_SPECS: dict[str, dict[str, dict[str, str]]] = {
    "forearms": {
        "0859": {
            "reason_code": "SOURCE_NAME_SEMANTICS_UNRESOLVED",
            "reason": "wrist rollerer는 원천 명칭이 비표준적이어서 실제 운동 도구·동작을 확정할 수 없어 이번 대표 선정에서 제외함.",
        }
    }
}

REVIEW_COLUMNS = [
    "candidate_id",
    "target",
    "source_name",
    "source_equipment",
    "source_category",
    "source_target",
    "exercise_family_candidate",
    "movement_pattern_candidate",
    "equipment_code_candidate",
    "equipment_label_candidate",
    "location_code_candidates",
    "difficulty_code_candidate",
    "beginner_suitability_candidate",
    "selection_rank",
    "selection_recommendation",
    "screening_decision",
    "screening_reason_code",
    "screening_reason",
    "review_required",
    "review_required_codes",
    "source_media_id",
    "source_image",
    "source_gif_url",
    "review_decision",
    "review_reason_code",
    "review_note",
    "reviewer",
    "reviewed_at",
]

EQUIPMENT_MAP: dict[str, tuple[str, str]] = {
    "body weight": ("BODYWEIGHT", "맨몸"),
    "dumbbell": ("DUMBBELL", "덤벨"),
    "barbell": ("BARBELL", "바벨"),
    "cable": ("CABLE_MACHINE", "케이블 머신"),
    "leverage machine": ("MACHINE", "웨이트 머신"),
    "band": ("RESISTANCE_BAND", "밴드"),
    "resistance band": ("RESISTANCE_BAND", "밴드"),
    "kettlebell": ("KETTLEBELL", "케틀벨"),
    "weighted": ("WEIGHTED_LOAD_REVIEW_REQUIRED", "외부 부하(세부 장비 검토 필요)"),
    "assisted": ("ASSISTED_SUPPORT_REVIEW_REQUIRED", "보조 기구/지지(검토 필요)"),
    "stability ball": ("STABILITY_BALL_REVIEW_REQUIRED", "짐볼(기존 코드 확인 필요)"),
    "roller": ("ROLLER_REVIEW_REQUIRED", "롤러(기존 코드 확인 필요)"),
    "wheel roller": ("ROLLER_REVIEW_REQUIRED", "휠 롤러(기존 코드 확인 필요)"),
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def equipment_candidate(source_equipment: str) -> tuple[str | None, str]:
    return EQUIPMENT_MAP.get(source_equipment, (None, f"{source_equipment}(검토 필요)"))


def location_candidates(source_equipment: str) -> list[str]:
    if source_equipment in {
        "cable",
        "barbell",
        "leverage machine",
        "smith machine",
        "sled machine",
    }:
        return ["GYM"]
    return ["HOME", "GYM"]


def infer_movement(target: str, name: str) -> str:
    n = name.lower()
    if any(
        token in n for token in ("stretch", "circle", "pelvic tilt", "sphinx", "upward facing dog")
    ):
        return "MOBILITY_STRETCH"
    if target in {"lats"}:
        return (
            "VERTICAL_PULL"
            if any(token in n for token in ("pull", "chin", "pulldown"))
            else "ISOLATION"
        )
    if target == "upper back":
        return (
            "HORIZONTAL_PULL"
            if any(token in n for token in ("row", "pull-up", "chin"))
            else "ISOLATION"
        )
    if target in {"pectorals", "triceps"}:
        return (
            "HORIZONTAL_PUSH"
            if any(token in n for token in ("push", "press", "dip"))
            else "ISOLATION"
        )
    if target == "delts":
        return (
            "VERTICAL_PUSH"
            if any(token in n for token in ("press", "jerk", "snatch", "push press"))
            else "ISOLATION"
        )
    if target in {"glutes", "quads"}:
        if any(
            token in n
            for token in (
                "deadlift",
                "good morning",
                "bridge",
                "hip extension",
                "pull through",
                "swing",
            )
        ):
            return "HIP_DOMINANT"
        return (
            "KNEE_DOMINANT"
            if any(token in n for token in ("squat", "lunge", "leg press", "step-up", "split"))
            else "ISOLATION"
        )
    if target == "hamstrings":
        if any(token in n for token in ("curl", "leg curl")):
            return "KNEE_FLEXION"
        return (
            "HIP_DOMINANT"
            if any(token in n for token in ("deadlift", "good morning", "raise"))
            else "ISOLATION"
        )
    if target in {"abs", "spine"}:
        return (
            "CORE_BRACE"
            if target == "abs" and not any(token in n for token in ("stretch", "twist"))
            else ("MOBILITY_STRETCH" if "stretch" in n else "CORE_BRACE")
        )
    return "ISOLATION"


def infer_difficulty(name: str, equipment: str) -> str:
    n = name.lower()
    if any(
        token in n
        for token in (
            "muscle up",
            "planche",
            "handstand",
            "pistol",
            "one arm",
            "weighted",
            "jump",
            "snatch",
            "jerk",
            "turkish",
            "windmill",
            "flag",
        )
    ):
        return "ADVANCED"
    if any(
        token in n
        for token in (
            "deadlift",
            "good morning",
            "lunge",
            "split squat",
            "dip",
            "hanging",
            "inverted row",
            "overhead press",
            "stability ball",
            "barbell",
        )
    ):
        return "INTERMEDIATE"
    if equipment in {"cable", "leverage machine", "body weight"} or any(
        token in n for token in ("crunch", "bridge", "curl", "raise", "squat", "push-up")
    ):
        return "BEGINNER"
    return "REVIEW_REQUIRED"


def infer_family(target: str, name: str, movement: str) -> str:
    n = name.lower()
    if "stretch" in n:
        return "MOBILITY_STRETCH_OUT_OF_SCOPE_CANDIDATE"
    for token, family in (
        ("pulldown", "PULLDOWN_VARIANT_CANDIDATE"),
        ("pull-up", "PULL_UP_VARIANT_CANDIDATE"),
        ("chin-up", "CHIN_UP_VARIANT_CANDIDATE"),
        ("row", "ROW_VARIANT_CANDIDATE"),
        ("shrug", "SHRUG_VARIANT_CANDIDATE"),
        ("press", "PRESS_VARIANT_CANDIDATE"),
        ("push-up", "PUSH_UP_VARIANT_CANDIDATE"),
        ("dip", "DIP_VARIANT_CANDIDATE"),
        ("squat", "SQUAT_VARIANT_CANDIDATE"),
        ("lunge", "LUNGE_VARIANT_CANDIDATE"),
        ("deadlift", "DEADLIFT_VARIANT_CANDIDATE"),
        ("curl", "CURL_VARIANT_CANDIDATE"),
        ("crunch", "CRUNCH_VARIANT_CANDIDATE"),
        ("twist", "ROTATION_VARIANT_CANDIDATE"),
        ("raise", "RAISE_VARIANT_CANDIDATE"),
    ):
        if token in n:
            return family
    return f"{target.upper().replace(' ', '_')}_{movement}_CANDIDATE"


def screening_for(target: str, raw: dict[str, Any]) -> dict[str, Any]:
    candidate_id = raw["id"]
    equipment_code, equipment_label = equipment_candidate(raw["equipment"])
    movement = infer_movement(target, raw["name"])
    difficulty = infer_difficulty(raw["name"], raw["equipment"])
    family = infer_family(target, raw["name"], movement)
    base = {
        "family": family,
        "movement": movement,
        "equipment_code": equipment_code,
        "equipment_label": equipment_label,
        "locations": location_candidates(raw["equipment"]),
        "difficulty": difficulty,
        "beginner": "CONDITIONAL"
        if difficulty == "INTERMEDIATE"
        else ("NOT_PRIORITY" if difficulty == "ADVANCED" else "REVIEW_REQUIRED"),
        "rank": None,
    }
    if candidate_id in INCLUDE_SPECS.get(target, {}):
        spec = INCLUDE_SPECS[target][candidate_id]
        base.update(spec)
        return {
            **base,
            "decision": "INCLUDE",
            "reason_code": "REPRESENTATIVE_FAMILY_SELECTED",
            "reason": spec["reason"],
        }
    if candidate_id in HOLD_SPECS.get(target, {}):
        spec = HOLD_SPECS[target][candidate_id]
        base["beginner"] = "REVIEW_REQUIRED"
        return {
            **base,
            "decision": "HOLD",
            "reason_code": spec["reason_code"],
            "reason": spec["reason"],
        }
    if candidate_id in EXCLUDE_SPECS.get(target, {}):
        spec = EXCLUDE_SPECS[target][candidate_id]
        return {
            **base,
            "decision": "EXCLUDE",
            "reason_code": spec["reason_code"],
            "reason": spec["reason"],
        }
    if base["movement"] == "MOBILITY_STRETCH":
        return {
            **base,
            "decision": "EXCLUDE",
            "reason_code": "MOBILITY_OR_STRETCH_OUT_OF_SCOPE",
            "reason": "근력 대표 운동 선정 범위가 아닌 스트레칭·가동성 후보임.",
        }
    if difficulty == "ADVANCED":
        return {
            **base,
            "decision": "EXCLUDE",
            "reason_code": "HIGH_COMPLEXITY_NOT_BEGINNER_PRIORITY",
            "reason": "고난도·복합 또는 고부하 후보로 초보·복귀 우선 대표군에 포함하지 않음.",
        }
    return {
        **base,
        "decision": "EXCLUDE",
        "reason_code": "DUPLICATE_OR_VARIANT_NOT_REPRESENTATIVE",
        "reason": "선정된 대표 운동군과 기능적으로 중복되거나 장비·자세 변형에 해당해 이번 단계에서 대표 후보로 중복 선정하지 않음.",
    }


def review_codes(screening: dict[str, Any]) -> list[str]:
    if screening["decision"] == "EXCLUDE":
        return []
    codes = [
        "HUMAN_REPRESENTATIVE_SELECTION_REVIEW",
        "EXERCISE_FAMILY_BOUNDARY_REVIEW",
        "MOVEMENT_PATTERN_REVIEW",
        "EQUIPMENT_TAXONOMY_CANDIDATE_REVIEW",
        "BEGINNER_SUITABILITY_REVIEW",
    ]
    if screening["decision"] == "HOLD":
        codes.append(screening["reason_code"])
    return codes


def build_candidate(
    target: str, raw: dict[str, Any], screening: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    review_required_codes = review_codes(screening)
    return {
        "candidate_id": raw["id"],
        "target": target,
        "source_record": raw,
        "source_provenance": {
            "source_name": source["source_name"],
            "source_license": source["license"],
            "retrieved_at": source["retrieved_at"],
            "raw_status": source["status"],
            "raw_files": source["files"],
        },
        "candidate_attributes": {
            "exercise_family_candidate": screening["family"],
            "movement_pattern_candidate": screening["movement"],
            "equipment_code_candidate": screening["equipment_code"],
            "equipment_label_candidate": screening["equipment_label"],
            "location_code_candidates": screening["locations"],
            "difficulty_code_candidate": screening["difficulty"],
            "beginner_suitability_candidate": screening["beginner"],
        },
        "screening": {
            "decision": screening["decision"],
            "reason_code": screening["reason_code"],
            "reason": screening["reason"],
            "selection_rank": screening["rank"],
        },
        "evidence": [
            {"source": "raw.target", "type": "RAW_FIELD"},
            {"source": "raw.name", "type": "RAW_FIELD"},
            {"source": "raw.equipment", "type": "RAW_FIELD"},
            {"source": "selection_policy.stage_2_strength_representative", "type": "PIPELINE_RULE"},
        ],
        "review_required": bool(review_required_codes),
        "review_required_codes": review_required_codes,
        "visual_evidence": {
            "image_reference": raw["image"],
            "gif_reference": raw["gif_url"],
            "binary_in_raw_snapshot": False,
            "status": "REFERENCE_ONLY_NOT_USED_FOR_SELECTION",
            "attribution": raw["attribution"],
        },
        "production_eligible": False,
    }


def coverage(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_target: dict[str, list[dict[str, Any]]] = {target: [] for target in TARGETS}
    for candidate in candidates:
        by_target[candidate["target"]].append(candidate)
    target_coverage: dict[str, Any] = {}
    gaps: list[dict[str, Any]] = []
    for target in TARGETS:
        rows = by_target[target]
        included = [row for row in rows if row["screening"]["decision"] == "INCLUDE"]
        families = sorted(
            {row["candidate_attributes"]["exercise_family_candidate"] for row in included}
        )
        movements = sorted(
            {row["candidate_attributes"]["movement_pattern_candidate"] for row in included}
        )
        equipment = sorted(
            {
                row["candidate_attributes"]["equipment_code_candidate"]
                or row["candidate_attributes"]["equipment_label_candidate"]
                for row in included
            }
        )
        locations = sorted(
            {
                location
                for row in included
                for location in row["candidate_attributes"]["location_code_candidates"]
            }
        )
        hold_count = sum(row["screening"]["decision"] == "HOLD" for row in rows)
        item = {
            "raw_candidate_count": len(rows),
            "include_count": len(included),
            "exclude_count": sum(row["screening"]["decision"] == "EXCLUDE" for row in rows),
            "hold_count": hold_count,
            "selected_candidate_ids": [
                row["candidate_id"]
                for row in sorted(
                    included, key=lambda row: row["screening"]["selection_rank"] or 999
                )
            ],
            "exercise_family_candidate_coverage": families,
            "movement_pattern_candidate_coverage": movements,
            "equipment_candidate_coverage": equipment,
            "location_candidate_coverage": locations,
            "coverage_gap": None,
        }
        if target == "spine" and len(included) < 2:
            item["coverage_gap"] = (
                "명확한 근력 대표군이 2종 미만이며, 나머지는 스트레칭·가동성 또는 동작 의미 확인이 필요함."
            )
        elif target == "traps" and len(included) < 2:
            item["coverage_gap"] = (
                "초보 우선 대표군이 2종 미만이며, 추가 후보는 적합성과 패턴 경계 확인이 필요함."
            )
        target_coverage[target] = item
        if item["coverage_gap"]:
            gaps.append({"target": target, "coverage_gap": item["coverage_gap"]})
    selected = [row for row in candidates if row["screening"]["decision"] == "INCLUDE"]
    return {
        "selected_count": len(selected),
        "selected_family_count": len(
            {
                (row["target"], row["candidate_attributes"]["exercise_family_candidate"])
                for row in selected
            }
        ),
        "target_coverage": target_coverage,
        "global_selected_movement_patterns": dict(
            sorted(
                Counter(
                    row["candidate_attributes"]["movement_pattern_candidate"] for row in selected
                ).items()
            )
        ),
        "global_selected_equipment": dict(
            sorted(
                Counter(
                    row["candidate_attributes"]["equipment_code_candidate"]
                    or row["candidate_attributes"]["equipment_label_candidate"]
                    for row in selected
                ).items()
            )
        ),
        "global_selected_locations": dict(
            sorted(
                Counter(
                    location
                    for row in selected
                    for location in row["candidate_attributes"]["location_code_candidates"]
                ).items()
            )
        ),
        "coverage_gaps": gaps,
    }


def create_profile(raw_dir: Path = DEFAULT_RAW_DIR) -> dict[str, Any]:
    raw_path = raw_dir / "exercises.json"
    source_path = raw_dir / "source.json"
    records = load_json(raw_path)
    source = load_json(source_path)
    target_records = [record for record in records if record.get("target") in TARGETS]
    candidates: list[dict[str, Any]] = []
    for target in TARGETS:
        for raw in sorted(
            (record for record in target_records if record["target"] == target),
            key=lambda record: record["id"],
        ):
            screening = screening_for(target, raw)
            candidates.append(build_candidate(target, raw, screening, source))
    decision_counts = Counter(candidate["screening"]["decision"] for candidate in candidates)
    return {
        "profile_version": PROFILE_VERSION,
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "scope": {
            "stage": "2_STRENGTH_REPRESENTATIVE_SELECTION",
            "source_filter": {"field": "target", "values": TARGETS},
            "selection_target": "target별 서로 다른 대표 운동군 최대 5개, 억지로 채우지 않음",
            "raw_candidate_count": len(target_records),
            "target_count": len(TARGETS),
        },
        "source": {
            "directory": str(raw_dir.relative_to(REPO_ROOT)),
            "source_manifest": source,
            "raw_sha256": {
                "exercises.json": sha256_file(raw_path),
                "source.json": sha256_file(source_path),
            },
        },
        "selection_policy": {
            "priority_order": [
                "BEGINNER_RETURNING_USER_FIT",
                "TARGET_REPRESENTATIVENESS",
                "MOVEMENT_AND_FAMILY_DIVERSITY",
                "HOME_GYM_UTILITY",
                "EQUIPMENT_DIVERSITY",
                "FUNCTIONAL_DUPLICATE_MINIMIZATION",
                "CLEAR_REVIEWABLE_MOVEMENT",
            ],
            "family_code_policy": "exercise_family_candidate만 기록하고 최종 exercise_family_code는 확정하지 않음.",
            "visual_policy": "GIF/image 존재·품질은 이번 단계의 선정·제외 근거로 사용하지 않고 참조 경로만 보존.",
            "deferred_work": [
                "장비·자세 변형 최종 선정",
                "wger·KSPO 보충",
                "통합 카탈로그",
                "안전 규칙",
                "대체 관계",
            ],
        },
        "decision_counts": dict(sorted(decision_counts.items())),
        "screening_disposition_counts": dict(sorted(decision_counts.items())),
        "taxonomy_policy": {
            "source": "data/normalized/exercise_taxonomy_codes.json",
            "status": "CANDIDATE_LABELS_ONLY",
            "note": "기존 코드셋은 후보 패턴·장비 표현 확인에만 사용하며 exercise_family_code와 개별 최종 taxonomy 승인은 하지 않음.",
        },
        "coverage": coverage(candidates),
        "candidates": candidates,
    }


def review_row(candidate: dict[str, Any]) -> dict[str, Any]:
    attrs = candidate["candidate_attributes"]
    screening = candidate["screening"]
    raw = candidate["source_record"]
    return {
        "candidate_id": candidate["candidate_id"],
        "target": candidate["target"],
        "source_name": raw["name"],
        "source_equipment": raw["equipment"],
        "source_category": raw["category"],
        "source_target": raw["target"],
        "exercise_family_candidate": attrs["exercise_family_candidate"],
        "movement_pattern_candidate": attrs["movement_pattern_candidate"],
        "equipment_code_candidate": attrs["equipment_code_candidate"] or "",
        "equipment_label_candidate": attrs["equipment_label_candidate"],
        "location_code_candidates": "|".join(attrs["location_code_candidates"]),
        "difficulty_code_candidate": attrs["difficulty_code_candidate"],
        "beginner_suitability_candidate": attrs["beginner_suitability_candidate"],
        "selection_rank": screening["selection_rank"] or "",
        "selection_recommendation": "RECOMMENDED"
        if screening["decision"] == "INCLUDE"
        else "NOT_RECOMMENDED",
        "screening_decision": screening["decision"],
        "screening_reason_code": screening["reason_code"],
        "screening_reason": screening["reason"],
        "review_required": "true" if candidate["review_required"] else "false",
        "review_required_codes": "|".join(candidate["review_required_codes"]),
        "source_media_id": raw["media_id"],
        "source_image": raw["image"],
        "source_gif_url": raw["gif_url"],
        "review_decision": "",
        "review_reason_code": "",
        "review_note": "",
        "reviewer": "",
        "reviewed_at": "",
    }


def write_outputs(
    profile: dict[str, Any],
    profile_path: Path = DEFAULT_PROFILE,
    review_path: Path = DEFAULT_REVIEW_BATCH,
) -> None:
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    candidates = profile["candidates"]
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(review_row(candidate) for candidate in candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--review-batch", type=Path, default=DEFAULT_REVIEW_BATCH)
    args = parser.parse_args()
    profile = create_profile(args.raw_dir)
    write_outputs(profile, args.profile, args.review_batch)
    print(
        json.dumps(
            {
                "profile": str(args.profile),
                "review_batch": str(args.review_batch),
                "decision_counts": profile["decision_counts"],
                "selected_count": profile["coverage"]["selected_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
