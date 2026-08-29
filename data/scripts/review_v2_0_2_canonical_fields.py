#!/usr/bin/env python3
# ruff: noqa: E501
"""Review and refine the v2.0.2 canonical exercise fields.

The relationship-finalized catalog is evidence for this pass, not a license to
silently rewrite approved taxonomy.  This exporter applies only deterministic
corrections backed by the integrated source and the existing v2 policies.  It
keeps old values in an explicit alias/migration table and emits unresolved
ambiguities as review findings.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.scripts.v2_0_2_difficulty_policy import apply_difficulty_policy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL = (
    ROOT / "generated/exercise-catalog-v2.0.2-final/canonical_exercises_v2_final.jsonl"
)
DEFAULT_V201 = (
    ROOT / "generated/exercise-catalog-v2.0.1-final/representative_exercises_v2_final.csv"
)
DEFAULT_INTEGRATED = ROOT / "reports/integrated_exercise_review_updated.csv"
DEFAULT_TAXONOMY = ROOT / "normalized/exercise_taxonomy_codes.json"
DEFAULT_OUTPUT = ROOT / "generated/exercise-catalog-v2.0.2-final"
DEFAULT_REPORT = ROOT / "reports/V2_0_2_CANONICAL_FIELD_REVIEW.md"

CATALOG_VERSION = "exercise-catalog-v2.0.2-final"
REVIEW_VERSION = "v2.0.2-canonical-field-review-v1.1.0"
GENERATED_AT = "2026-08-28T00:00:00+09:00"

VALID_TRAINING_TYPES = {"STRENGTH", "CARDIO", "MOBILITY"}
VALID_BODY_FOCUS = {
    "CHEST",
    "BACK",
    "SHOULDERS",
    "BICEPS",
    "TRICEPS",
    "FOREARMS",
    "GLUTES",
    "QUADRICEPS",
    "HAMSTRINGS",
    "CALVES",
    "CORE",
    "FULL_BODY",
    "CARDIO",
    "MOBILITY",
}
VALID_MOVEMENT_PATTERNS = {
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
    "BALANCE",
    "CYCLING",
    "ELLIPTICAL",
    "JUMP_PLYOMETRIC",
}
VALID_EQUIPMENT = {
    "BODYWEIGHT",
    "DUMBBELL",
    "BARBELL",
    "EZ_BAR",
    "KETTLEBELL",
    "CABLE_MACHINE",
    "MACHINE",
    "HOUSEHOLD_WEIGHT",
    "PULL_UP_BAR",
    "RESISTANCE_BAND",
    "STRETCH_STRAP",
    "MAT",
    "STABILITY_BALL",
    "ELLIPTICAL_MACHINE",
    "JUMP_ROPE",
    "FOAM_ROLLER",
    "ROLLER",
    "STATIONARY_BIKE",
    "STEP_BOX",
    "WEIGHTED",
}
VALID_LOCATIONS = {"HOME", "GYM"}
VALID_DIFFICULTY = {"BEGINNER", "INTERMEDIATE"}
VALID_TIMING = {"REPS", "DURATION"}
VALID_PHASES = {"WARMUP", "MAIN", "COOLDOWN"}
VALID_SOURCE_TRACKS = {"wger", "kspo", "gymvisual"}
VALID_BODY_AREAS = {
    "NECK",
    "SHOULDER",
    "ELBOW",
    "WRIST_HAND",
    "UPPER_BACK",
    "LOWER_BACK",
    "HIP",
    "KNEE",
    "ANKLE_FOOT",
    "CHEST",
    "ABDOMEN",
    "GENERALIZED",
    "OTHER",
}
FORBIDDEN_V2_EQUIPMENT = {"BENCH", "CHAIR"}

# HOME policy is limited to equipment the service explicitly supports.  A
# household weight is included as a supported HOME execution form.
HOME_SUPPORTED_EQUIPMENT = {
    "BODYWEIGHT",
    "DUMBBELL",
    "FOAM_ROLLER",
    "HOUSEHOLD_WEIGHT",
    "JUMP_ROPE",
    "MAT",
    "RESISTANCE_BAND",
}
BODY_FOCUS_ALLOWED_AREAS = {
    "CHEST": {"CHEST", "SHOULDER"},
    "BACK": {"UPPER_BACK", "LOWER_BACK"},
    "SHOULDERS": {"SHOULDER"},
    "BICEPS": {"ELBOW"},
    "TRICEPS": {"CHEST", "ELBOW"},
    "FOREARMS": {"WRIST_HAND"},
    "GLUTES": {"HIP", "KNEE"},
    "QUADRICEPS": {"HIP", "KNEE"},
    "HAMSTRINGS": {"HIP", "KNEE"},
    "CALVES": {"ANKLE_FOOT", "KNEE"},
    "CORE": {"ABDOMEN"},
}
PATTERN_REQUIRED_EQUIPMENT = {
    "CYCLING": {"STATIONARY_BIKE"},
    "ELLIPTICAL": {"ELLIPTICAL_MACHINE"},
}

FIRST_PASS_REVIEW_IDS = {"REX-000002", *{f"REX-{index:06d}" for index in range(103, 138)}}
EXCLUDED_REPRESENTATIVE_IDS = {
    "REX-000107",
    "REX-000116",
    "REX-000129",
    "REX-000132",
}
DELETION_DECISION_CODES = {
    "REX-000107": "USER_REQUESTED_DELETE_ADVANCED_OUT_OF_SCOPE",
    "REX-000116": "USER_REQUESTED_DELETE_ADVANCED_OUT_OF_SCOPE",
    "REX-000129": "USER_REQUESTED_DELETE_BEGINNER_UNSUITABLE",
    "REX-000132": "USER_REQUESTED_DELETE_SOURCE_EXECUTION_UNCLEAR",
}
VARIANT_CANDIDATE_IDS = {"REX-000105"}
VARIANT_PARENT_IDS = {"REX-000105": "REX-000006"}

DISPLAY_NAME_OVERRIDES = {
    "REX-000002": "네발기기 대퇴사두근 스트레칭",
    "REX-000104": "케이블 인클라인 플라이(짐볼)",
    "REX-000112": "덤벨 리어 레터럴 레이즈(머리 지지)",
    "REX-000113": "덤벨 리어 레터럴 레이즈",
    "REX-000114": "인버스 레그 컬(벤치 지지)",
    "REX-000118": "셀프 어시스트 인버스 레그 컬",
    "REX-000127": "머신 풀오버",
    "REX-000121": "바이시클 크런치",
    "REX-000134": "인클라인 체스트 서포티드 덤벨 로우",
}
NAME_EN_OVERRIDES = {
    "REX-000002": "quadruped quadriceps stretch",
    "REX-000121": "bicycle crunch",
}
EQUIPMENT_OVERRIDES = {
    "REX-000111": ["DUMBBELL"],
    "REX-000114": ["BODYWEIGHT"],
    "REX-000120": ["HOUSEHOLD_WEIGHT"],
    "REX-000121": ["BODYWEIGHT"],
    "REX-000131": ["EZ_BAR"],
}
STABLE_CODE_OVERRIDES = {
    "REX-000002": "quadruped_quadriceps_stretch_mobility_stretch_bodyweight",
    "REX-000114": "inverse_leg_curl_bench_support_isolation_bodyweight",
    "REX-000120": "weighted_russian_twist_legs_up_isolation_household_weight",
    "REX-000121": "bicycle_crunch_core_brace_bodyweight",
    "REX-000131": "ez_bar_lying_bent_arms_pullover_isolation_ez_bar",
}
SETUP_CONDITION_OVERRIDES = {
    "REX-000002": "손과 무릎을 지지할 안정적인 바닥 공간을 확보한다.",
    "REX-000103": "디클라인 벤치와 바벨을 준비하고 발 고정 상태를 확인한다.",
    "REX-000104": "인클라인으로 고정한 짐볼과 케이블 머신을 준비한다.",
    "REX-000105": "케이블 머신 상단 풀리에 로프 핸들을 연결하고 벤치를 준비한다.",
    "REX-000106": "케이블 머신 시트를 안정적으로 조정한다.",
    "REX-000107": "케이블 머신과 짐볼을 준비한다.",
    "REX-000108": "45도로 조절한 인클라인 벤치를 준비한다.",
    "REX-000110": "안정적인 플랫 벤치를 준비한다.",
    "REX-000111": "안정적인 지지물(벤치 또는 의자 등)을 준비한다.",
    "REX-000112": "이마를 가볍게 댈 수 있는 안정적인 벤치를 준비한다.",
    "REX-000114": "안정적인 지지물(벤치 또는 의자 등)을 준비한다.",
    "REX-000115": "서스펜션 트레이너 또는 스트랩을 가슴 높이에 고정한다.",
    "REX-000119": "스미스 머신과 발을 올릴 수 있는 안정적인 스텝 또는 플랫폼을 준비한다.",
    "REX-000123": "디클라인 벤치와 케이블 머신의 로우 풀리·D형 손잡이를 준비한다.",
    "REX-000124": "저항 밴드를 준비한다.",
    "REX-000125": "균형을 잡을 수 있는 안정적인 지지물을 준비한다.",
    "REX-000126": "프리처 벤치와 덤벨을 준비한다.",
    "REX-000127": "레버리지 풀오버 머신의 시트와 손잡이를 조정한다.",
    "REX-000128": "시티드 카프 프레스 머신의 시트와 레버 패드를 조정한다.",
    "REX-000130": "저항 밴드를 안정적인 고정 지점에 연결한다.",
    "REX-000131": "플랫 벤치와 EZ 바를 준비한다.",
    "REX-000134": "안정적인 지지물(벤치 또는 의자 등)을 준비한다.",
    "REX-000137": "안정적인 뒤쪽 벤치와 덤벨을 준비한다.",
}
LOCATION_OVERRIDES = {
    "REX-000132": ["HOME"],
    "REX-000137": ["GYM"],
}
DIFFICULTY_OVERRIDES = {
    "REX-000104": "INTERMEDIATE",
    "REX-000109": "INTERMEDIATE",
    "REX-000120": "INTERMEDIATE",
    "REX-000125": "INTERMEDIATE",
    "REX-000133": "INTERMEDIATE",
    "REX-000134": "INTERMEDIATE",
}
BODY_AREA_OVERRIDES = {
    "REX-000133": {
        "primary": ["SHOULDER", "UPPER_BACK"],
        "secondary": ["ELBOW", "WRIST_HAND", "LOWER_BACK"],
    },
    "REX-000134": {
        "primary": ["UPPER_BACK", "SHOULDER"],
        "secondary": ["ELBOW", "CHEST"],
    },
}
TIMING_MODE_OVERRIDES = {
    "REX-000107": "REPS",
    "REX-000120": "REPS",
    "REX-000121": "REPS",
    "REX-000122": "REPS",
}

INSTRUCTION_OVERRIDES: dict[str, dict[str, Any]] = {
    "REX-000002": {
        "summary": "네발기기 자세에서 한쪽 다리를 뒤로 뻗고 무릎을 굽힌 채 엉덩이를 낮춰 허벅지 앞쪽을 스트레칭합니다.",
        "cues": [
            "손은 어깨 아래, 무릎은 고관절 아래에 둔다.",
            "한쪽 다리를 뒤로 뻗되 무릎을 굽히고 발을 세운다.",
            "엉덩이를 천천히 낮춰 허벅지 앞쪽이 당기는 범위를 찾는다.",
            "20~30초 유지한 뒤 반대쪽도 같은 방법으로 진행한다.",
        ],
    },
    "REX-000103": {
        "summary": "디클라인 벤치에 누워 발을 고정하고 바벨을 가슴 위에서 머리 뒤로 천천히 내렸다가 시작 위치로 돌아옵니다.",
        "cues": [
            "머리가 엉덩이보다 낮은 디클라인 벤치에 누워 발을 고정한다.",
            "바벨을 손바닥이 앞을 향하도록 잡고 가슴 위에서 팔을 편다.",
            "팔꿈치를 약간 굽힌 채 바벨을 머리 뒤로 천천히 내린다.",
            "반동 없이 광배근으로 바벨을 시작 위치까지 되돌린다.",
        ],
    },
    "REX-000104": {
        "summary": "인클라인으로 고정한 짐볼에 앉아 케이블 손잡이를 양손으로 잡고 팔을 벌렸다가 통제하며 돌아옵니다.",
        "cues": [
            "인클라인으로 고정한 짐볼에 발을 바닥에 두고 안정적으로 앉는다.",
            "케이블 손잡이를 손바닥이 앞을 향하도록 잡고 등을 곧게 편다.",
            "팔꿈치를 약간 굽힌 채 양팔을 옆으로 벌린다.",
            "몸통이 흔들리지 않는 범위에서 천천히 시작 위치로 돌아온다.",
        ],
    },
    "REX-000105": {
        "summary": "벤치에 누워 케이블 머신의 로프를 가슴 위로 들어 올리고, 팔꿈치를 약간 굽힌 채 로프를 머리 뒤로 천천히 내렸다가 돌아옵니다.",
        "cues": [
            "케이블 머신 상단 풀리에 로프 핸들을 연결하고 벤치에 눕는다.",
            "로프를 양손으로 잡아 가슴 위에서 팔을 편다.",
            "팔꿈치 각도를 유지하며 로프를 머리 뒤로 천천히 내린다.",
            "통제된 속도로 로프를 가슴 위 시작 위치로 되돌린다.",
        ],
    },
    "REX-000106": {
        "summary": "케이블 머신에 앉아 손바닥이 위를 향하도록 손잡이를 잡고 등을 곧게 편 채 팔꿈치를 뒤로 당겼다가 천천히 돌아옵니다.",
        "cues": [
            "케이블 머신 시트에 앉아 발바닥을 바닥에 둔다.",
            "손바닥이 위를 향하는 언더핸드 그립으로 손잡이를 잡는다.",
            "등을 곧게 유지하며 견갑골을 모아 손잡이를 몸통 쪽으로 당긴다.",
            "정점에서 잠시 멈춘 뒤 케이블을 천천히 놓는다.",
        ],
    },
    "REX-000107": {
        "summary": "짐볼에 앉아 케이블 손잡이를 양손으로 잡고 몸통을 좌우로 회전하며 손잡이를 양쪽 엉덩이 쪽으로 보냅니다.",
        "cues": [
            "짐볼에 앉아 무릎을 굽히고 발을 바닥에 안정적으로 둔다.",
            "케이블 손잡이를 양손으로 잡고 팔을 앞으로 뻗는다.",
            "몸통을 오른쪽으로 회전해 손잡이를 오른쪽 엉덩이 쪽으로 보낸다.",
            "중앙으로 돌아온 뒤 반대쪽도 번갈아 진행한다.",
        ],
    },
    "REX-000108": {
        "summary": "45도 인클라인 벤치에 가슴을 대고 덤벨을 양손에 든 뒤 팔을 양옆으로 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "인클라인 벤치를 45도로 조정하고 가슴을 등받이에 댄다.",
            "덤벨을 손바닥이 서로 마주 보게 잡고 팔을 아래로 늘어뜨린다.",
            "팔꿈치를 약간 굽힌 채 팔을 바닥과 평행한 높이까지 벌린다.",
            "정점에서 잠시 멈춘 뒤 덤벨을 천천히 내린다.",
        ],
    },
    "REX-000109": {
        "summary": "덤벨을 양손에 들고 팔을 양옆으로 들어 올렸다가 내린 다음, 같은 방식으로 몸 앞까지 들어 올립니다.",
        "cues": [
            "발을 어깨너비로 두고 덤벨을 몸 옆에서 잡는다.",
            "등을 곧게 세우고 팔을 양옆으로 어깨 높이까지 들어 올린다.",
            "팔을 천천히 내린 뒤 몸 앞쪽으로 어깨 높이까지 들어 올린다.",
            "각 동작에서 팔꿈치를 약간 굽히고 반동을 사용하지 않는다.",
        ],
    },
    "REX-000110": {
        "summary": "플랫 벤치에 엎드려 덤벨을 양손에 들고 팔을 양옆으로 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "플랫 벤치에 엎드려 가슴을 지지하고 덤벨을 손바닥이 서로 마주 보게 잡는다.",
            "팔을 바닥 쪽으로 늘어뜨리되 팔꿈치를 약간 굽힌다.",
            "어깨 뒤쪽을 사용해 팔을 바닥과 평행한 높이까지 벌린다.",
            "정점에서 멈춘 뒤 덤벨을 천천히 시작 위치로 내린다.",
        ],
    },
    "REX-000111": {
        "summary": "벤치에 팔뚝을 올리고 손바닥이 아래를 향하게 덤벨을 잡은 뒤 손목을 위로 말아 올렸다가 천천히 내립니다.",
        "cues": [
            "벤치에 앉아 팔뚝을 벤치 위에 두고 손목을 가장자리 밖으로 뺀다.",
            "손바닥이 아래를 향하도록 양손에 덤벨을 잡는다.",
            "팔뚝을 고정한 채 손목만 몸 쪽으로 천천히 굽힌다.",
            "정점에서 잠시 멈춘 뒤 덤벨을 천천히 내린다.",
        ],
    },
    "REX-000112": {
        "summary": "안정적인 벤치에 이마를 가볍게 대어 머리를 지지한 상태에서 상체를 기울여 덤벨을 양옆으로 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "안정적인 벤치에 이마를 가볍게 대어 머리를 지지하고 덤벨을 양손에 잡는다.",
            "무릎을 약간 굽히고 등을 곧게 유지한 채 고관절에서 상체를 기울인다.",
            "팔꿈치를 약간 굽힌 채 팔을 양옆으로 들어 올린다.",
            "반동 없이 덤벨을 천천히 시작 위치로 내린다.",
        ],
    },
    "REX-000113": {
        "summary": "상체를 고관절에서 앞으로 기울여 덤벨을 양손에 들고 팔을 양옆으로 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "발을 어깨너비로 두고 손바닥이 몸을 향하도록 덤벨을 잡는다.",
            "무릎을 약간 굽히고 등을 곧게 유지한 채 상체를 기울인다.",
            "팔꿈치를 약간 굽힌 채 팔을 바닥과 평행한 높이까지 벌린다.",
            "어깨를 으쓱하지 말고 덤벨을 천천히 내린다.",
        ],
    },
    "REX-000114": {
        "summary": "벤치에 엎드려 엉덩이를 가장자리에 두고 다리를 뒤로 뻗은 뒤 무릎을 굽혀 발을 엉덩이 쪽으로 당겼다가 폅니다.",
        "cues": [
            "벤치에 엎드려 엉덩이를 가장자리에 두고 벤치를 잡아 몸을 지지한다.",
            "상체를 고정한 채 양쪽 무릎을 천천히 굽힌다.",
            "발을 엉덩이 쪽으로 당긴 지점에서 잠시 멈춘다.",
            "다리를 통제하며 시작 위치까지 천천히 편다.",
        ],
    },
    "REX-000115": {
        "summary": "가슴 높이에 고정한 스트랩을 잡고 몸을 기울여 가슴을 손잡이 쪽으로 당겼다가 천천히 돌아옵니다.",
        "cues": [
            "스트랩 또는 서스펜션 트레이너를 가슴 높이에 고정한다.",
            "손잡이를 오버핸드 그립으로 잡고 발을 앞으로 걸어 몸을 기울인다.",
            "몸통을 일직선으로 유지하며 가슴을 손잡이 쪽으로 당긴다.",
            "견갑골을 모은 뒤 몸을 천천히 시작 위치로 되돌린다.",
        ],
    },
    "REX-000116": {
        "summary": "케틀벨을 가슴 앞에서 잡고 앞으로 런지하면서 앞다리 아래로 통과시킨 뒤 반대손으로 넘기며 좌우를 번갈아 진행합니다.",
        "cues": [
            "케틀벨을 양손으로 가슴 앞에서 잡고 발을 어깨너비로 둔다.",
            "한 발을 앞으로 내딛어 런지 자세로 내려간다.",
            "내려가는 동안 케틀벨을 앞다리 아래로 통과시켜 반대손으로 넘긴다.",
            "앞발로 밀어 돌아오며 반대쪽도 같은 방법으로 진행한다.",
        ],
    },
    "REX-000117": {
        "summary": "바닥에 누워 무릎을 굽히고 엉덩이를 들어 올린 상태에서 발을 엉덩이 쪽으로 당겼다가 다리를 펴고 엉덩이를 내립니다.",
        "cues": [
            "등을 대고 누워 무릎을 굽혀 발을 골반 너비로 둔다.",
            "엉덩이를 들어 올려 둔근과 허벅지 뒤쪽에 힘을 준다.",
            "엉덩이를 든 상태에서 발을 천천히 몸 쪽으로 당긴다.",
            "다리를 펴고 엉덩이를 바닥에 내린 뒤 반복한다.",
        ],
    },
    "REX-000118": {
        "summary": "바닥이나 매트에 누워 손을 엉덩이 아래에 두고 무릎을 굽혀 허벅지를 가슴 쪽으로 당겼다가 천천히 내립니다.",
        "cues": [
            "바닥이나 매트에 등을 대고 누워 다리를 뻗는다.",
            "손을 옆이나 엉덩이 아래에 두어 몸을 보조한다.",
            "무릎을 굽혀 발을 들어 허벅지를 가슴 쪽으로 당긴다.",
            "허리가 과하게 뜨지 않도록 다리를 천천히 내린다.",
        ],
    },
    "REX-000119": {
        "summary": "스미스 머신 바를 지지하고 발 앞꿈치를 플랫폼에 올린 뒤 뒤꿈치를 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "스미스 머신 바를 어깨 바로 아래 높이로 조정한다.",
            "발 앞꿈치를 스텝 또는 플랫폼 가장자리에 두고 뒤꿈치를 밖으로 뺀다.",
            "등을 곧게 편 채 뒤꿈치를 가능한 높이까지 들어 올린다.",
            "정점에서 멈춘 뒤 뒤꿈치를 천천히 내린다.",
        ],
    },
    "REX-000120": {
        "summary": "다리를 들어 올린 채 바닥에 앉아 중량을 양손으로 잡고 몸통을 좌우로 회전합니다.",
        "cues": [
            "무릎을 굽히고 발을 바닥에서 들어 다리를 모은다.",
            "중량을 양손으로 가슴 앞에서 잡고 상체를 약간 뒤로 기울인다.",
            "몸통을 오른쪽으로 회전해 중량을 오른쪽 바닥 쪽으로 보낸다.",
            "중앙을 거쳐 왼쪽으로 회전하며 좌우를 번갈아 진행한다.",
        ],
    },
    "REX-000121": {
        "summary": "등을 대고 누워 양쪽 무릎과 팔꿈치를 번갈아 가까이 가져오는 바이시클 크런치를 수행합니다.",
        "cues": [
            "등을 대고 누워 손을 머리 뒤에 두고 무릎을 굽힌다.",
            "발을 들어 오른쪽 무릎을 가슴 쪽으로 당긴다.",
            "몸통을 회전해 왼쪽 팔꿈치를 오른쪽 무릎 쪽으로 가져간다.",
            "반대쪽도 번갈아 진행하며 허리를 과하게 꺾지 않는다.",
        ],
    },
    "REX-000122": {
        "summary": "허리 높이에 고정한 밴드를 잡고 무릎을 꿇은 채 몸통을 좌우로 회전하며 손을 반대쪽 엉덩이로 보냅니다.",
        "cues": [
            "밴드를 허리 높이의 안정적인 고정 지점에 연결한다.",
            "고정 지점을 등지고 무릎을 꿇어 밴드를 양손으로 잡는다.",
            "팔꿈치를 가까이 둔 채 복부에 힘을 주고 몸통을 한쪽으로 회전한다.",
            "천천히 중앙으로 돌아온 뒤 반대쪽도 번갈아 진행한다.",
        ],
    },
    "REX-000123": {
        "summary": "디클라인 벤치에 누워 낮은 위치의 케이블을 한 손으로 잡고 팔을 가슴 위로 모았다가 천천히 벌립니다.",
        "cues": [
            "케이블 머신의 낮은 풀리에 D형 손잡이를 연결하고 벤치를 디클라인으로 조정한다.",
            "머리가 머신 쪽을 향하도록 벤치에 누워 한 손으로 손잡이를 잡는다.",
            "팔꿈치를 약간 굽힌 채 손잡이를 가슴 위로 모은다.",
            "가슴이 늘어나는 범위까지 손잡이를 천천히 되돌린다.",
        ],
    },
    "REX-000124": {
        "summary": "저항 밴드를 양발 아래에 두고 양손으로 끝을 잡은 채 두 뒤꿈치를 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "저항 밴드를 양발 아래에 두고 양손으로 끝을 잡는다.",
            "발을 어깨너비로 두고 몸통을 안정적으로 세운다.",
            "종아리를 사용해 두 뒤꿈치를 가능한 높이까지 들어 올린다.",
            "정점에서 멈춘 뒤 뒤꿈치를 천천히 내린다.",
        ],
    },
    "REX-000125": {
        "summary": "안정적인 지지물을 잡고 한쪽 발로 선 뒤 뒤꿈치를 들어 올렸다가 내리고 반대쪽도 반복합니다.",
        "cues": [
            "벽이나 바 등 안정적인 지지물을 잡고 한쪽 발을 들어 올린다.",
            "지지하는 무릎을 약간 굽힌 채 몸통을 세운다.",
            "지지하는 발의 뒤꿈치를 가능한 높이까지 들어 올린다.",
            "천천히 내린 뒤 정해진 횟수를 마치고 반대쪽을 진행한다.",
        ],
    },
    "REX-000126": {
        "summary": "프리처 벤치에 앉아 덤벨을 잡고 팔꿈치를 고정한 채 팔을 한쪽씩 굽혀 이두근을 수축합니다.",
        "cues": [
            "프리처 벤치에 앉아 양손에 덤벨을 들고 팔을 패드 위에 편다.",
            "위팔을 고정하고 한쪽 덤벨을 어깨 높이까지 천천히 올린다.",
            "정점에서 이두근을 잠시 수축한 뒤 덤벨을 내린다.",
            "반대쪽도 같은 방법으로 번갈아 진행한다.",
        ],
    },
    "REX-000127": {
        "summary": "풀오버 머신에 앉아 손잡이를 잡고 팔꿈치를 약간 굽힌 채 손잡이를 가슴 쪽으로 당겼다가 천천히 돌아옵니다.",
        "cues": [
            "레버리지 머신의 시트와 손잡이를 편안한 위치로 조정한다.",
            "등을 패드에 대고 손잡이를 오버핸드 그립으로 잡는다.",
            "팔꿈치를 약간 굽히고 광배근을 사용해 손잡이를 가슴 쪽으로 당긴다.",
            "정점에서 잠시 멈춘 뒤 손잡이를 천천히 되돌린다.",
        ],
    },
    "REX-000128": {
        "summary": "시티드 카프 프레스 머신에 앉아 발 앞꿈치로 플랫폼을 밀어 뒤꿈치를 들어 올렸다가 천천히 내립니다.",
        "cues": [
            "어깨가 레버 패드 아래에 오도록 머신 시트를 조정한다.",
            "발 앞꿈치를 플랫폼 아래쪽에 두고 무릎을 레버 패드 아래에 둔다.",
            "손잡이를 잡아 몸을 안정시키고 발목을 펴 뒤꿈치를 들어 올린다.",
            "뒤꿈치를 천천히 내리며 발목 가동 범위 안에서 반복한다.",
        ],
    },
    "REX-000130": {
        "summary": "밴드를 발목에 연결하고 고정 지점을 향해 선 뒤 다리를 앞으로 뻗었다가 천천히 되돌립니다.",
        "cues": [
            "밴드를 안정적인 고정 지점에 연결하고 발목에 건다.",
            "고정 지점을 향해 서서 발을 어깨너비로 두고 몸통을 세운다.",
            "몸통을 고정한 채 한쪽 다리를 앞으로 곧게 뻗는다.",
            "정점에서 잠시 멈춘 뒤 다리를 천천히 되돌리고 반대쪽을 진행한다.",
        ],
    },
    "REX-000131": {
        "summary": "벤치에 누워 EZ 바를 가슴 위에서 잡고 팔꿈치를 약간 굽힌 채 바를 머리 뒤로 호를 그리며 내렸다가 돌아옵니다.",
        "cues": [
            "플랫 벤치에 누워 발을 바닥에 두고 EZ 바를 어깨너비로 잡는다.",
            "팔을 가슴 위로 뻗되 팔꿈치를 약간 굽힌다.",
            "팔꿈치 각도를 유지하며 EZ 바를 머리 뒤로 호를 그려 천천히 내린다.",
            "반동 없이 같은 호를 따라 바를 시작 위치로 되돌린다.",
        ],
    },
    "REX-000132": {
        "summary": "서서 의자를 잡고 한쪽 무릎을 뒤로 굽혀 발을 엉덩이 쪽으로 들었다가 천천히 내립니다.",
        "cues": [
            "안정적인 의자를 잡고 서서 몸통을 곧게 세운다.",
            "한쪽 무릎을 굽혀 발뒤꿈치를 엉덩이 쪽으로 들어 올린다.",
            "허벅지가 앞으로 움직이지 않도록 무릎 굽힘에 집중한다.",
            "발을 천천히 내린 뒤 반대쪽도 같은 방법으로 진행한다.",
        ],
    },
    "REX-000133": {
        "summary": "고관절에서 상체를 기울이고 팔꿈치를 바깥쪽으로 벌리며 덤벨을 몸통 쪽으로 당겼다가 천천히 내립니다.",
        "cues": [
            "고관절을 접어 상체를 기울이고 허리의 자연스러운 곡선을 유지한다.",
            "목을 길게 두고 덤벨을 양손에 잡는다.",
            "팔꿈치를 과하게 높이지 않으며 덤벨을 몸통 쪽으로 당긴다.",
            "반동 없이 덤벨을 천천히 내려 시작 위치로 돌아온다.",
        ],
    },
    "REX-000134": {
        "summary": "30~45도 벤치에 가슴을 대고 엎드려 덤벨을 몸통 옆으로 당겨 올린 뒤 팔이 늘어질 때까지 천천히 내립니다.",
        "cues": [
            "벤치를 30~45도로 세우고 가슴을 벤치에 댄다.",
            "팔꿈치가 몸통에서 과하게 벌어지지 않도록 덤벨을 잡는다.",
            "어깨를 으쓱하지 않고 등으로 덤벨을 몸통 옆까지 당긴다.",
            "가슴과 목을 안정적으로 유지하며 덤벨을 천천히 내린다.",
        ],
    },
    "REX-000135": {
        "summary": "레그프레스 발판에 앞꿈치를 대고 발목을 펴 발판을 밀어 뒤꿈치를 올렸다가 천천히 내립니다.",
        "cues": [
            "레그프레스 발판에 발 앞꿈치를 두고 뒤꿈치를 자유롭게 움직일 공간을 둔다.",
            "발 앞꿈치가 발판에서 떨어지지 않도록 유지한다.",
            "무릎 각도를 일정하게 두고 발목을 펴 뒤꿈치를 들어 올린다.",
            "반동 없이 발목 가동 범위 안에서 뒤꿈치를 내린다.",
        ],
    },
    "REX-000136": {
        "summary": "밴드를 발목에 걸고 허벅지를 고정한 채 무릎을 굽혀 뒤꿈치를 엉덩이 쪽으로 당겼다가 천천히 폅니다.",
        "cues": [
            "밴드를 단단한 지점에 고정하고 발목에 건다.",
            "허벅지와 몸통이 들리지 않도록 위치를 고정한다.",
            "발목을 과하게 꺾지 않고 무릎을 굽힌다.",
            "밴드 장력을 유지하며 다리를 천천히 편다.",
        ],
    },
    "REX-000137": {
        "summary": "한 발을 뒤 벤치에 올리고 앞다리에 체중을 두어 몸을 낮췄다가 앞발로 바닥을 밀며 일어납니다.",
        "cues": [
            "처음에는 덤벨 없이 균형을 익힌 뒤 양손에 덤벨을 든다.",
            "한 발을 뒤 벤치에 올리고 앞발을 충분히 앞으로 둔다.",
            "골반이 한쪽으로 기울지 않게 앞다리 중심으로 몸을 낮춘다.",
            "앞발로 바닥을 밀어 일어나고 좌우를 같은 횟수로 진행한다.",
        ],
    },
}

SOURCE_REVIEW_CODES = {
    "REX-000002": "INSTRUCTION_SOURCE_REFINED_FROM_IMAGE_AND_TEXT_REVIEW",
    "REX-000105": "EQUIPMENT_ATTACHMENT_SOURCE_CONFLICT_REVIEW_REQUIRED",
    "REX-000121": "SOURCE_MEDIA_EQUIPMENT_IDENTITY_REVIEW_REQUIRED",
    "REX-000132": "SOURCE_INSTRUCTION_TEXT_MISSING_REVIEW_REQUIRED",
}
DATA_REVIEW_NOTES = {
    "REX-000002": "원천 제목의 squad는 수행법·첨부 이미지와 맞지 않는 오기로 보고 canonical을 quadruped quadriceps stretch로 정제했다. 기존 원천 표기는 source_name_en과 alias에 보존한다.",
    "REX-000104": "짐볼의 불안정성과 케이블 제어가 필요하지만 이번 catalog 난이도 범위는 BEGINNER/INTERMEDIATE이므로 INTERMEDIATE로 정제했다.",
    "REX-000105": "바벨 풀오버와 수행법이 같은 케이블·로프·벤치 변형이다. 활성 대표운동은 REX-000006으로 유지하고 이 행은 장비·부착물 변형 후보로 이동했다.",
    "REX-000107": "원천 난이도가 ADVANCED이고 이번 catalog는 BEGINNER/INTERMEDIATE만 허용하므로 사용자 요청으로 활성 집합에서 삭제했다.",
    "REX-000109": "좌우 레이즈 후 전면 레이즈를 연속 수행하는 원천 동작 기준으로 INTERMEDIATE로 정제했다.",
    "REX-000112": "머리를 벤치에 지지하는 수행 정체성을 한국어 단계에 명시하고, 이마를 가볍게 대는 setup을 추가했다.",
    "REX-000116": "원천 난이도가 ADVANCED이고 이번 catalog는 BEGINNER/INTERMEDIATE만 허용하므로 사용자 요청으로 활성 집합에서 삭제했다.",
    "REX-000120": "발을 든 상태의 중량 러시안 트위스트는 제어가 필요하지만 이번 catalog 난이도 범위에 맞춰 INTERMEDIATE로 정제하고, 원천의 반복 수행에 맞춰 REPS로 변경했다.",
    "REX-000121": "원천 제목·이미지는 band지만 단계는 맨몸 바이시클 크런치다. canonical은 bodyweight bicycle crunch로 정리하고 band 표기는 source media/provenance review로 남겼다.",
    "REX-000125": "한 발 지지와 균형 요구가 있어 BEGINNER가 아니라 INTERMEDIATE로 정제했다.",
    "REX-000129": "사용자 요청으로 초보자가 수행하기 어려운 변형을 활성 canonical에서 삭제했다.",
    "REX-000132": "KSPO 원천은 영상 후보이며 텍스트 단계가 없어 수행 정합성을 확정할 수 없으므로 사용자 요청으로 삭제했다.",
    "REX-000133": "wger 원천의 승인된 attribute difficulty가 INTERMEDIATE이므로 기존 BEGINNER를 정제했다.",
    "REX-000134": "wger 원천의 승인된 attribute difficulty가 INTERMEDIATE이며 chest-supported 정체성을 한국어 명칭에 반영했다.",
    "REX-000137": "뒤 벤치 지지가 필요한 불가리안 스플릿 스쿼트이므로 실제 장소 기본값은 GYM으로 정제하고 BENCH는 setup에 보존했다.",
}
AMBIGUOUS_REVIEW_CODES = {
    "REX-000121": "SOURCE_MEDIA_EQUIPMENT_IDENTITY_REVIEW_REQUIRED",
}
SOURCE_PROVENANCE_FIELDS = (
    "source_system",
    "source_record_id",
    "source_name",
    "source_name_en",
    "source_name_ko",
    "source_url",
    "source_author",
    "source_license",
    "source_license_author",
    "license_id",
    "license_name",
    "license_version",
    "license_url",
    "attribution_text",
    "accessed_at",
    "license_review_status",
    "source_media_reference",
    "source_media_id",
    "source_instruction_en",
    "source_instruction_steps_en",
)


class ReviewError(ValueError):
    """Raised when required source evidence or output invariants are absent."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--v2-0-1", type=Path, default=DEFAULT_V201)
    parser.add_argument("--integrated", type=Path, default=DEFAULT_INTEGRATED)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise ReviewError(f"cannot read CSV: {path}") from error
    if not rows:
        raise ReviewError(f"CSV is empty: {path}")
    return [{key: (value or "") for key, value in row.items()} for row in rows]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ReviewError(f"JSONL object expected at {path}:{line_number}")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"invalid JSONL: {path}") from error
    if not rows:
        raise ReviewError(f"JSONL is empty: {path}")
    return rows


def read_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path) if path.suffix == ".jsonl" else read_csv(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ReviewError(f"JSON object expected: {path}")
    return value


def parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not isinstance(value, str) or not value.strip():
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            return parse_list(parsed)
    return [item.strip() for item in value.split("|") if item.strip()]


def parse_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def compact(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    return str(value)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def columns(rows: list[dict[str, Any]], preferred: list[str]) -> list[str]:
    result = list(preferred)
    for row in rows:
        for key in row:
            if key not in result:
                result.append(key)
    return result


def write_csv(path: Path, rows: list[dict[str, Any]], preferred: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = columns(rows, preferred)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: compact(row.get(key, "")) for key in fieldnames})


def locations_for_equipment(equipment: list[str]) -> list[str]:
    return ["HOME", "GYM"] if set(equipment).issubset(HOME_SUPPORTED_EQUIPMENT) else ["GYM"]


def source_lookup(
    integrated_rows: list[dict[str, str]],
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, dict[str, str]]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    by_nex: dict[str, dict[str, str]] = {}
    for row in integrated_rows:
        key = (row.get("source_system", ""), row.get("source_id", ""))
        if not all(key):
            raise ReviewError("integrated source row has missing source_system/source_id")
        if key in by_key:
            raise ReviewError(f"duplicate integrated source key: {key}")
        by_key[key] = row
        nex = row.get("normalized_exercise_id", "")
        if nex:
            if nex in by_nex:
                raise ReviewError(f"duplicate normalized exercise ID: {nex}")
            by_nex[nex] = row
    return by_key, by_nex


def resolve_source(
    row: dict[str, Any],
    by_key: dict[tuple[str, str], dict[str, str]],
    by_nex: dict[str, dict[str, str]],
) -> tuple[dict[str, str], str, str]:
    old_track = str(row.get("source_track", ""))
    old_identity = str(row.get("source_identity", ""))
    if old_track == "v1":
        nex_id = str(row.get("mapping_source_exercise_id", ""))
        source = by_nex.get(nex_id)
        if source is None:
            raise ReviewError(
                "promoted row has unresolved mapping source: "
                f"{row.get('representative_exercise_id')}"
            )
        return source, old_track, old_identity
    source = by_key.get((old_track, old_identity))
    if source is None:
        raise ReviewError(f"canonical source not found: {old_track}:{old_identity}")
    return source, "", ""


def source_fields(source: dict[str, str]) -> dict[str, Any]:
    return {
        "source_system": source.get("source_system", ""),
        "source_record_id": source.get("source_id", ""),
        "source_name": source.get("source_name", "")
        or source.get("name_en", "")
        or source.get("name_ko", ""),
        "source_name_en": source.get("name_en", ""),
        "source_name_ko": source.get("source_name", "")
        if source.get("source_system") == "kspo"
        else "",
        "source_url": source.get("source_url", ""),
        "source_author": source.get("source_author", ""),
        "source_license": source.get("source_license", ""),
        "source_license_author": source.get("source_license_author", ""),
        "license_id": source.get("license_id", ""),
        "license_name": source.get("license_name", ""),
        "license_version": source.get("license_version", ""),
        "license_url": source.get("license_url", ""),
        "attribution_text": source.get("attribution_text", "")
        or source.get("source_attribution", ""),
        "accessed_at": source.get("accessed_at", ""),
        "license_review_status": source.get("license_review_status", ""),
        "source_media_reference": source.get("source_media_reference", "")
        or source.get("media_source_reference", ""),
        "source_media_id": source.get("source_media_id", ""),
        "source_instruction_en": source.get("source_instruction_en", "")
        or source.get("raw_source_instruction_en", ""),
        "source_instruction_steps_en": source.get("raw_source_instruction_steps_en", ""),
    }


def add_change(
    changes: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    row: dict[str, Any],
    field: str,
    old: Any,
    new: Any,
    reason_code: str,
    evidence: str,
    change_type: str = "FIELD_CORRECTION",
) -> None:
    if old == new:
        return
    rep_id = str(row["representative_exercise_id"])
    old_value = compact(old)
    new_value = compact(new)
    change = {
        "representative_exercise_id": rep_id,
        "stable_code_before": row.get("_stable_code_before_history", row.get("stable_code", "")),
        "field_name": field,
        "old_value": old_value,
        "new_value": new_value,
        "change_type": change_type,
        "decision_code": reason_code,
        "decision_status": "APPLIED",
        "evidence_reference": evidence,
        "note_ko": (
            "원천·승인 정책과의 정합성을 맞춘 결정적 수정이며 기존 값은 migration에 보존한다."
        ),
    }
    changes.append(change)
    if old_value and field in {
        "name_en",
        "display_name_ko",
        "source_track",
        "source_identity",
        "equipment_codes",
        "location_codes",
        "stable_code",
    }:
        aliases.append(
            {
                "alias_id": f"ALIAS-{len(aliases) + 1:04d}",
                "representative_exercise_id": rep_id,
                "stable_code_before": row.get(
                    "_stable_code_before_history", row.get("stable_code", "")
                ),
                "stable_code_after": row.get("stable_code", ""),
                "field_name": field,
                "alias_value": old_value,
                "canonical_value": new_value,
                "alias_type": "NAME_ALIAS"
                if field in {"name_en", "display_name_ko"}
                else "LEGACY_FIELD_VALUE",
                "migration_status": "PRESERVED_ACTIVE_HISTORY",
                "evidence_reference": evidence,
                "note_ko": "기존 명칭·값을 검색/이관 추적용으로 보존한다.",
            }
        )


def validation_value(value: Any) -> bool:
    return bool(str(value or "").strip())


def changed_fields_for(changes: list[dict[str, Any]], representative_id: str) -> set[str]:
    return {
        str(change["field_name"])
        for change in changes
        if change["representative_exercise_id"] == representative_id
    }


def data_review_row(
    original: dict[str, Any],
    refined: dict[str, Any],
    source: dict[str, str],
    changed_fields: set[str],
    *,
    deleted: bool = False,
    row_status_override: str | None = None,
    instruction_status_override: str | None = None,
) -> dict[str, Any]:
    rep_id = str(original["representative_exercise_id"])

    def before(field: str) -> Any:
        if field == "display_name_ko":
            return original.get("display_name_ko") or original.get("name_ko")
        return original.get(field)

    def after(field: str) -> Any:
        if deleted:
            return ""
        if field == "display_name_ko":
            return refined.get("display_name_ko") or refined.get("name_ko")
        return refined.get(field)

    def decision(field: str) -> str:
        if deleted:
            return "DELETED"
        return "CORRECTED" if field in changed_fields else "RETAINED"

    if deleted:
        status = "DELETED_FROM_ACTIVE_CATALOG"
        instruction_status = "DELETED_BY_USER_REQUEST"
    elif rep_id in SOURCE_REVIEW_CODES and rep_id in {"REX-000112", "REX-000121", "REX-000132"}:
        status = "REVIEW_REQUIRED"
        instruction_status = "SOURCE_CONFLICT_REVIEW_REQUIRED"
    elif changed_fields.intersection(
        {
            "instruction_summary_ko",
            "form_cues_ko",
            "difficulty_code",
            "timing_mode_code",
        }
    ):
        status = "CORRECTED_REVIEW_REQUIRED"
        instruction_status = "ALIGNED_AFTER_FIRST_PASS_REFINEMENT"
    else:
        status = "RETAINED_REVIEW_REQUIRED"
        instruction_status = "ALIGNED_RETAINED"

    return {
        "representative_exercise_id": rep_id,
        "source_key": f"{source.get('source_system', '')}:{source.get('source_id', '')}",
        "source_name_en": source.get("name_en", "") or source.get("source_name", ""),
        "row_status": row_status_override or status,
        "instruction_alignment_status": instruction_status_override or instruction_status,
        "training_type_decision": decision("training_type_code"),
        "training_type_before": before("training_type_code"),
        "training_type_after": after("training_type_code"),
        "movement_pattern_decision": decision("primary_movement_pattern_code"),
        "movement_pattern_before": before("primary_movement_pattern_code"),
        "movement_pattern_after": after("primary_movement_pattern_code"),
        "body_focus_decision": decision("body_focus_code"),
        "body_focus_before": before("body_focus_code"),
        "body_focus_after": after("body_focus_code"),
        "primary_body_area_decision": decision("primary_body_area_codes"),
        "primary_body_area_before": before("primary_body_area_codes"),
        "primary_body_area_after": after("primary_body_area_codes"),
        "secondary_body_area_decision": decision("secondary_body_area_codes"),
        "secondary_body_area_before": before("secondary_body_area_codes"),
        "secondary_body_area_after": after("secondary_body_area_codes"),
        "difficulty_decision": decision("difficulty_code"),
        "difficulty_before": before("difficulty_code"),
        "difficulty_after": after("difficulty_code"),
        "equipment_decision": decision("equipment_codes"),
        "equipment_before": before("equipment_codes"),
        "equipment_after": after("equipment_codes"),
        "location_decision": decision("location_codes"),
        "location_before": before("location_codes"),
        "location_after": after("location_codes"),
        "timing_decision": decision("timing_mode_code"),
        "timing_before": before("timing_mode_code"),
        "timing_after": after("timing_mode_code"),
        "instruction_summary_ko": after("instruction_summary_ko"),
        "form_cues_ko": after("form_cues_ko"),
        "review_required": False if deleted else bool(refined.get("review_required")),
        "review_required_codes": [] if deleted else refined.get("review_required_codes", []),
        "review_note_ko": DATA_REVIEW_NOTES.get(
            rep_id, "분류·수행법·장비 필드를 원천과 대조한 1차 결과."
        ),
    }


def review_and_refine(
    canonical_rows: list[dict[str, Any]],
    v201_rows: list[dict[str, str]],
    integrated_rows: list[dict[str, str]],
    taxonomy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    del taxonomy  # v2.0.2 uses the narrower approved release allowlist above.
    by_key, by_nex = source_lookup(integrated_rows)
    v201_by_id = {row["representative_exercise_id"]: row for row in v201_rows}
    refined: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    identity_reviews: list[dict[str, Any]] = []
    data_reviews: list[dict[str, Any]] = []
    deletions: list[dict[str, Any]] = []
    variant_candidates: list[dict[str, Any]] = []

    for original in sorted(
        canonical_rows, key=lambda item: str(item["representative_exercise_id"])
    ):
        row = dict(original)
        rep_id = str(row["representative_exercise_id"])
        row["_stable_code_before_history"] = str(row.get("stable_code", ""))
        source, legacy_track, legacy_identity = resolve_source(row, by_key, by_nex)
        evidence = (
            "integrated_exercise_review_updated.csv:"
            f"{source.get('source_system')}:{source.get('source_id')}"
        )
        if rep_id in EXCLUDED_REPRESENTATIVE_IDS:
            deletions.append(
                {
                    "representative_exercise_id": rep_id,
                    "stable_code_before": row.get("stable_code", ""),
                    "display_name_before": row.get("display_name_ko") or row.get("name_ko", ""),
                    "name_en_before": row.get("name_en", ""),
                    "source_key": f"{source.get('source_system', '')}:{source.get('source_id', '')}",
                    "deletion_status": "DELETED_FROM_ACTIVE_CATALOG",
                    "decision_code": DELETION_DECISION_CODES[rep_id],
                    "decision_status": "APPLIED",
                    "evidence_reference": evidence,
                    "review_required": False,
                    "note_ko": DATA_REVIEW_NOTES.get(
                        rep_id,
                        "주인님 요청으로 활성 canonical 집합에서 제외한다. 이전 정제 이력과 원천 행은 감사 추적용으로 보존한다.",
                    ),
                }
            )
            data_reviews.append(data_review_row(original, {}, source, set(), deleted=True))
            continue
        old_track = str(row.get("source_track", ""))
        old_identity = str(row.get("source_identity", ""))
        if legacy_track:
            row["legacy_source_track"] = legacy_track
            row["legacy_source_identity"] = legacy_identity
            row["legacy_source_key"] = f"{legacy_track}:{legacy_identity.removeprefix('v1:')}"
            add_change(
                changes,
                aliases,
                row,
                "source_track",
                old_track,
                source["source_system"],
                "SOURCE_PROVENANCE_RESOLVED",
                evidence,
            )
            add_change(
                changes,
                aliases,
                row,
                "source_identity",
                old_identity,
                source["source_id"],
                "SOURCE_PROVENANCE_RESOLVED",
                evidence,
            )
        else:
            row["legacy_source_track"] = ""
            row["legacy_source_identity"] = ""
            row["legacy_source_key"] = ""
        row["source_track"] = source["source_system"]
        row["source_identity"] = source["source_id"]
        row["source_key"] = f"{source['source_system']}:{source['source_id']}"
        row.update(source_fields(source))
        row["source_provenance_status"] = "RESOLVED_INTEGRATED_SOURCE"
        row["source_license_status"] = (
            "APPROVED" if source.get("license_review_status") == "APPROVED" else "REVIEW_REQUIRED"
        )

        current_name_en = str(row.get("name_en", ""))
        corrected_name_en = current_name_en
        if rep_id in NAME_EN_OVERRIDES:
            corrected_name_en = NAME_EN_OVERRIDES[rep_id]
        elif source.get("source_system") == "kspo" and not source.get("name_en", ""):
            corrected_name_en = ""
        elif rep_id == "REX-000111":
            corrected_name_en = "dumbbell over bench reverse wrist curl"
        add_change(
            changes,
            aliases,
            row,
            "name_en",
            current_name_en,
            corrected_name_en,
            "SOURCE_NAME_EN_NORMALIZED",
            evidence,
        )
        row["name_en"] = corrected_name_en

        old_display_name = str(row.get("display_name_ko", "") or row.get("name_ko", ""))
        final_display_name = DISPLAY_NAME_OVERRIDES.get(rep_id, str(row.get("name_ko", "")))
        add_change(
            changes,
            aliases,
            row,
            "display_name_ko",
            old_display_name,
            final_display_name,
            "REPRESENTATIVE_IDENTITY_LABEL_REFINED",
            evidence,
        )
        row["name_ko"] = final_display_name
        row["display_name_ko"] = final_display_name

        old_equipment = parse_list(row.get("equipment_codes", []))
        new_equipment = EQUIPMENT_OVERRIDES.get(rep_id, old_equipment)
        add_change(
            changes,
            aliases,
            row,
            "equipment_codes",
            old_equipment,
            new_equipment,
            "EQUIPMENT_TAXONOMY_NORMALIZED",
            evidence,
        )
        row["equipment_codes"] = new_equipment

        old_location = parse_list(row.get("location_codes", []))
        # Existing approved location values are retained.  Re-derive the
        # location only when this pass changed the load equipment itself.
        new_location = LOCATION_OVERRIDES.get(
            rep_id,
            locations_for_equipment(new_equipment)
            if old_equipment != new_equipment
            else old_location,
        )
        add_change(
            changes,
            aliases,
            row,
            "location_codes",
            old_location,
            new_location,
            "LOCATION_DERIVED_FROM_LOAD_EQUIPMENT",
            evidence,
        )
        row["location_codes"] = new_location

        old_stable = str(row.get("stable_code", ""))
        new_stable = STABLE_CODE_OVERRIDES.get(rep_id, old_stable)
        add_change(
            changes,
            aliases,
            row,
            "stable_code",
            old_stable,
            new_stable,
            "STABLE_CODE_IDENTITY_MIGRATION"
            if rep_id == "REX-000002"
            else "STABLE_CODE_EQUIPMENT_MIGRATION",
            evidence,
            "STABLE_CODE_MIGRATION",
        )
        row["stable_code"] = new_stable

        old_setup = str(row.get("setup_condition_ko", ""))
        prior_setup = str(v201_by_id.get(rep_id, {}).get("setup_condition_ko", ""))
        new_setup = SETUP_CONDITION_OVERRIDES.get(rep_id, old_setup or prior_setup)
        if old_setup != new_setup:
            add_change(
                changes,
                aliases,
                row,
                "setup_condition_ko",
                old_setup,
                new_setup,
                "SUPPORT_CONDITION_PRESERVED",
                evidence,
            )
        row["setup_condition_ko"] = new_setup

        old_primary_body_areas = parse_list(row.get("primary_body_area_codes", []))
        old_secondary_body_areas = parse_list(row.get("secondary_body_area_codes", []))
        body_area_override = BODY_AREA_OVERRIDES.get(rep_id)
        new_primary_body_areas = (
            body_area_override["primary"] if body_area_override else old_primary_body_areas
        )
        new_secondary_body_areas = (
            body_area_override["secondary"] if body_area_override else old_secondary_body_areas
        )
        add_change(
            changes,
            aliases,
            row,
            "primary_body_area_codes",
            old_primary_body_areas,
            new_primary_body_areas,
            "SOURCE_REVIEWED_BODY_AREA_REFINED",
            evidence,
        )
        add_change(
            changes,
            aliases,
            row,
            "secondary_body_area_codes",
            old_secondary_body_areas,
            new_secondary_body_areas,
            "SOURCE_REVIEWED_BODY_AREA_REFINED",
            evidence,
        )
        row["primary_body_area_codes"] = new_primary_body_areas
        row["secondary_body_area_codes"] = new_secondary_body_areas

        old_difficulty = str(row.get("difficulty_code", ""))
        refined_difficulty = DIFFICULTY_OVERRIDES.get(rep_id, old_difficulty)
        new_difficulty, difficulty_policy_rule = apply_difficulty_policy(
            {
                "stable_code": row.get("stable_code", ""),
                "equipment_codes": row.get("equipment_codes", []),
            },
            refined_difficulty,
        )
        add_change(
            changes,
            aliases,
            row,
            "difficulty_code",
            old_difficulty,
            new_difficulty,
            difficulty_policy_rule
            if difficulty_policy_rule != "NO_POLICY_OVERRIDE"
            else "SOURCE_REVIEWED_DIFFICULTY_REFINED",
            evidence,
        )
        row["difficulty_code"] = new_difficulty

        instruction_override = INSTRUCTION_OVERRIDES.get(rep_id)
        if instruction_override:
            old_summary = row.get("instruction_summary_ko", "")
            old_cues = parse_list(row.get("form_cues_ko", []))
            new_summary = instruction_override["summary"]
            new_cues = instruction_override["cues"]
            add_change(
                changes,
                aliases,
                row,
                "instruction_summary_ko",
                old_summary,
                new_summary,
                "SOURCE_INSTRUCTION_ALIGNMENT_REFINED",
                evidence,
            )
            add_change(
                changes,
                aliases,
                row,
                "form_cues_ko",
                old_cues,
                new_cues,
                "SOURCE_INSTRUCTION_ALIGNMENT_REFINED",
                evidence,
            )
            row["instruction_summary_ko"] = new_summary
            row["form_cues_ko"] = new_cues

        old_timing = str(row.get("timing_mode_code", ""))
        new_timing = TIMING_MODE_OVERRIDES.get(rep_id, old_timing)
        add_change(
            changes,
            aliases,
            row,
            "timing_mode_code",
            old_timing,
            new_timing,
            "SOURCE_INSTRUCTION_TIMING_REFINED",
            evidence,
        )
        row["timing_mode_code"] = new_timing
        if new_timing == "REPS":
            old_seconds_per_rep = row.get("default_seconds_per_rep")
            new_seconds_per_rep = old_seconds_per_rep or 4
            add_change(
                changes,
                aliases,
                row,
                "default_seconds_per_rep",
                old_seconds_per_rep,
                new_seconds_per_rep,
                "SOURCE_INSTRUCTION_TIMING_REFINED",
                evidence,
            )
            row["default_seconds_per_rep"] = new_seconds_per_rep
            old_work_seconds = row.get("default_work_seconds")
            if old_work_seconds:
                add_change(
                    changes,
                    aliases,
                    row,
                    "default_work_seconds",
                    old_work_seconds,
                    None,
                    "SOURCE_INSTRUCTION_TIMING_REFINED",
                    evidence,
                )
                row["default_work_seconds"] = None

        row["phase_codes"] = (
            ["WARMUP", "COOLDOWN"] if row.get("training_type_code") == "MOBILITY" else ["MAIN"]
        )
        row["timing_phase_review_status"] = "APPROVED_FROM_POLICY"
        if rep_id in FIRST_PASS_REVIEW_IDS:
            row["instruction_identity_status"] = "ALIGNED_AFTER_FIRST_PASS_REVIEW_REQUIRED"
        elif legacy_track:
            row["instruction_identity_status"] = "INHERITED_CONTENT_REVIEW_REQUIRED"
        else:
            row["instruction_identity_status"] = "CONTENT_PRESENT_REVIEWED_ARTIFACT"

        review_codes: list[str] = []
        if (
            str(row.get("review_status_code", "")) == "REVIEW_REQUIRED"
            or str(row.get("review_required", "")).lower() == "true"
        ):
            review_codes.append("EXISTING_REVIEW_REQUIRED")
        if source.get("license_review_status") != "APPROVED":
            review_codes.append("SOURCE_LICENSE_REVIEW_REQUIRED")
        if legacy_track or rep_id in FIRST_PASS_REVIEW_IDS:
            review_codes.append("INSTRUCTION_CONTENT_REVIEW_REQUIRED")
        if rep_id in SOURCE_REVIEW_CODES:
            review_codes.append(SOURCE_REVIEW_CODES[rep_id])
        row["review_required_codes"] = sorted(set(review_codes))
        row["review_required"] = bool(row["review_required_codes"])
        row["review_status_code"] = str(row.get("review_status_code", "")) or "REVIEW_REQUIRED"

        if rep_id in VARIANT_CANDIDATE_IDS:
            row["candidate_status"] = "VARIANT_CANDIDATE"
            row["production_eligible"] = False
            row["canonical_status"] = "VARIANT_CANDIDATE"
            row["canonical_decision_code"] = "EQUIPMENT_ATTACHMENT_VARIANT_CANDIDATE"
            row["canonical_decision_note_ko"] = (
                "REX-000006 바벨 풀오버와 수행법이 같은 케이블·로프 변형 후보로 분리했다."
            )
            row["variant_parent_representative_exercise_id"] = VARIANT_PARENT_IDS[rep_id]
            row["variant_relation_code"] = "EQUIPMENT_OR_ATTACHMENT"
            variant_candidates.append(dict(row))
            if rep_id in FIRST_PASS_REVIEW_IDS:
                data_reviews.append(
                    data_review_row(
                        original,
                        row,
                        source,
                        changed_fields_for(changes, rep_id),
                        row_status_override="MOVED_TO_VARIANT_CANDIDATE",
                        instruction_status_override="ALIGNED_VARIANT_CANDIDATE_REVIEW_REQUIRED",
                    )
                )
            row.pop("_stable_code_before_history", None)
            continue

        identity_codes: list[str] = []
        if rep_id in DISPLAY_NAME_OVERRIDES:
            identity_codes.append("DISPLAY_NAME_VARIANT_DESCRIPTOR_REVIEWED")
        if rep_id in AMBIGUOUS_REVIEW_CODES:
            identity_codes.append(AMBIGUOUS_REVIEW_CODES[rep_id])
        identity_unresolved = any(
            code in AMBIGUOUS_REVIEW_CODES.values() for code in identity_codes
        )
        if identity_unresolved:
            identity_status = "REVIEW_REQUIRED"
        elif old_display_name != final_display_name:
            identity_status = "REFINED_APPLIED"
        else:
            identity_status = "RETAINED"
        identity_reviews.append(
            {
                "representative_group_key": f"canonical:{row['stable_code']}",
                "representative_exercise_id": rep_id,
                "stable_code": row["stable_code"],
                "representative_role": "CANONICAL_REPRESENTATIVE",
                "representative_selection_basis": (
                    "SEPARATE_EXERCISE_HUMAN_REVIEW_PROMOTED"
                    if legacy_track
                    else "EXISTING_CANONICAL_REPRESENTATIVE_RETAINED"
                ),
                "display_name_before": old_display_name,
                "display_name_after": final_display_name,
                "identity_decision_code": "LABEL_REFINED"
                if old_display_name != final_display_name
                else "IDENTITY_RETAINED",
                "identity_review_status": identity_status,
                "identity_review_codes": identity_codes,
                "location_codes": new_location,
                "home_default_recommendation": "ELIGIBLE"
                if "HOME" in new_location
                else "NOT_ELIGIBLE",
                "gym_default_recommendation": "ELIGIBLE"
                if "GYM" in new_location
                else "NOT_ELIGIBLE",
                "representative_location_separation": (
                    "LOCATION_DEFAULT_IS_SEPARATE_FROM_REPRESENTATIVE_IDENTITY"
                ),
                "review_required": identity_unresolved,
            }
        )
        if rep_id in FIRST_PASS_REVIEW_IDS:
            data_reviews.append(
                data_review_row(
                    original,
                    row,
                    source,
                    changed_fields_for(changes, rep_id),
                )
            )
        row.pop("_stable_code_before_history", None)
        refined.append(row)

    validation = validate_refined(refined)
    validation["field_correction_count"] = len(changes)
    validation["representative_count"] = len(refined)
    validation["review_required_count"] = sum(bool(row["review_required"]) for row in refined)
    validation["ambiguous_review_required_count"] = sum(
        any(code in AMBIGUOUS_REVIEW_CODES.values() for code in row["review_required_codes"])
        for row in refined
    )
    validation["source_license_review_required_count"] = sum(
        "SOURCE_LICENSE_REVIEW_REQUIRED" in row["review_required_codes"] for row in refined
    )
    validation["instruction_review_required_count"] = sum(
        "INSTRUCTION_CONTENT_REVIEW_REQUIRED" in row["review_required_codes"] for row in refined
    )
    validation["identity_review_required_count"] = sum(
        item["review_required"] for item in identity_reviews
    )
    validation["field_correction_by_field"] = dict(Counter(item["field_name"] for item in changes))
    validation["field_correction_by_reason"] = dict(
        Counter(item["decision_code"] for item in changes)
    )
    validation["deleted_representative_count"] = len(deletions)
    validation["variant_candidate_count"] = len(variant_candidates)
    validation["variant_candidate_review_required_count"] = sum(
        bool(row["review_required"]) for row in variant_candidates
    )
    validation["variant_candidate_data_review_required_count"] = sum(
        bool(set(row["review_required_codes"]) - {"SOURCE_LICENSE_REVIEW_REQUIRED"})
        for row in variant_candidates
    )
    validation["first_pass_data_review_count"] = len(data_reviews)
    validation["source_conflict_review_required_count"] = sum(
        item["instruction_alignment_status"] == "SOURCE_CONFLICT_REVIEW_REQUIRED"
        for item in data_reviews
    )
    validation["data_review_required_count"] = sum(
        bool(set(row["review_required_codes"]) - {"SOURCE_LICENSE_REVIEW_REQUIRED"})
        for row in refined
    )
    return (
        refined,
        changes,
        aliases,
        {
            "identity_reviews": identity_reviews,
            "data_reviews": data_reviews,
            "deletions": deletions,
            "variant_candidates": variant_candidates,
            "validation": validation,
        },
    )


def validate_refined(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    invalid: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    stable_codes = [str(row.get("stable_code", "")) for row in rows]
    rep_ids = [str(row.get("representative_exercise_id", "")) for row in rows]
    for row in rows:
        rep_id = str(row.get("representative_exercise_id", ""))
        required = {
            "display_name_ko": row.get("display_name_ko") or row.get("name_ko"),
            "training_type_code": row.get("training_type_code"),
            "primary_movement_pattern_code": row.get("primary_movement_pattern_code"),
            "body_focus_code": row.get("body_focus_code"),
            "primary_body_area_codes": parse_list(row.get("primary_body_area_codes", [])),
            "equipment_codes": parse_list(row.get("equipment_codes", [])),
            "location_codes": parse_list(row.get("location_codes", [])),
            "difficulty_code": row.get("difficulty_code"),
            "timing_mode_code": row.get("timing_mode_code"),
            "phase_codes": parse_list(row.get("phase_codes", [])),
            "instruction_summary_ko": row.get("instruction_summary_ko"),
            "form_cues_ko": parse_list(row.get("form_cues_ko", [])),
            "source_system": row.get("source_system"),
            "source_record_id": row.get("source_record_id"),
            "source_url": row.get("source_url"),
            "license_id": row.get("license_id"),
            "license_name": row.get("license_name"),
            "license_review_status": row.get("license_review_status"),
        }
        for field, value in required.items():
            if not value:
                missing.append({"representative_exercise_id": rep_id, "field": field})
        if row.get("training_type_code") not in VALID_TRAINING_TYPES:
            invalid.append(
                {
                    "representative_exercise_id": rep_id,
                    "field": "training_type_code",
                    "value": row.get("training_type_code"),
                }
            )
        if row.get("body_focus_code") not in VALID_BODY_FOCUS:
            invalid.append(
                {
                    "representative_exercise_id": rep_id,
                    "field": "body_focus_code",
                    "value": row.get("body_focus_code"),
                }
            )
        if row.get("primary_movement_pattern_code") not in VALID_MOVEMENT_PATTERNS:
            invalid.append(
                {
                    "representative_exercise_id": rep_id,
                    "field": "primary_movement_pattern_code",
                    "value": row.get("primary_movement_pattern_code"),
                }
            )
        if row.get("source_track") not in VALID_SOURCE_TRACKS:
            invalid.append(
                {
                    "representative_exercise_id": rep_id,
                    "field": "source_track",
                    "value": row.get("source_track"),
                }
            )
        for field, allowed in (
            ("difficulty_code", VALID_DIFFICULTY),
            ("timing_mode_code", VALID_TIMING),
        ):
            if row.get(field) not in allowed:
                invalid.append(
                    {"representative_exercise_id": rep_id, "field": field, "value": row.get(field)}
                )
        equipment = set(parse_list(row.get("equipment_codes", [])))
        locations = set(parse_list(row.get("location_codes", [])))
        phases = parse_list(row.get("phase_codes", []))
        invalid_equipment = sorted(equipment - VALID_EQUIPMENT)
        invalid_locations = sorted(locations - VALID_LOCATIONS)
        invalid_phases = sorted(set(phases) - VALID_PHASES)
        body_areas = set(parse_list(row.get("primary_body_area_codes", []))) | set(
            parse_list(row.get("secondary_body_area_codes", []))
        )
        invalid_body_areas = sorted(body_areas - VALID_BODY_AREAS)
        for field, values in (
            ("equipment_codes", invalid_equipment),
            ("location_codes", invalid_locations),
            ("phase_codes", invalid_phases),
            ("body_area_codes", invalid_body_areas),
        ):
            for value in values:
                invalid.append(
                    {"representative_exercise_id": rep_id, "field": field, "value": value}
                )
        if equipment & FORBIDDEN_V2_EQUIPMENT:
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "V2_SUPPORT_EQUIPMENT_CODE_FORBIDDEN",
                    "values": sorted(equipment & FORBIDDEN_V2_EQUIPMENT),
                }
            )
        if "HOME" in locations and not equipment.issubset(HOME_SUPPORTED_EQUIPMENT):
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "HOME_EQUIPMENT_LOCATION_CONFLICT",
                    "values": sorted(equipment - HOME_SUPPORTED_EQUIPMENT),
                }
            )
        primary = set(parse_list(row.get("primary_body_area_codes", [])))
        secondary = set(parse_list(row.get("secondary_body_area_codes", [])))
        if primary & secondary:
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "PRIMARY_SECONDARY_BODY_AREA_OVERLAP",
                    "values": sorted(primary & secondary),
                }
            )
        body_focus = str(row.get("body_focus_code", ""))
        allowed_areas = BODY_FOCUS_ALLOWED_AREAS.get(body_focus)
        if allowed_areas and not primary.intersection(allowed_areas):
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "BODY_FOCUS_PRIMARY_AREA_CONFLICT",
                    "body_focus_code": body_focus,
                    "primary_body_area_codes": sorted(primary),
                }
            )
        movement = str(row.get("primary_movement_pattern_code", ""))
        required_equipment = PATTERN_REQUIRED_EQUIPMENT.get(movement, set())
        if required_equipment and not equipment.intersection(required_equipment):
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "MOVEMENT_PATTERN_EQUIPMENT_CONFLICT",
                    "movement_pattern_code": movement,
                    "required_equipment": sorted(required_equipment),
                    "equipment_codes": sorted(equipment),
                }
            )
        if (
            movement in {"GAIT", "CYCLING", "ELLIPTICAL"}
            and row.get("training_type_code") != "CARDIO"
        ):
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "CARDIO_MOVEMENT_TRAINING_TYPE_CONFLICT",
                    "movement_pattern_code": movement,
                }
            )
        if movement == "MOBILITY_STRETCH" and row.get("training_type_code") != "MOBILITY":
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "MOBILITY_MOVEMENT_TRAINING_TYPE_CONFLICT",
                }
            )
        if row.get("training_type_code") == "MOBILITY" and row.get("body_focus_code") != "MOBILITY":
            conflicts.append(
                {"representative_exercise_id": rep_id, "code": "MOBILITY_BODY_FOCUS_CONFLICT"}
            )
        if row.get("training_type_code") == "CARDIO" and row.get("body_focus_code") != "CARDIO":
            conflicts.append(
                {"representative_exercise_id": rep_id, "code": "CARDIO_BODY_FOCUS_CONFLICT"}
            )
        expected_phases = (
            ["WARMUP", "COOLDOWN"] if row.get("training_type_code") == "MOBILITY" else ["MAIN"]
        )
        if phases != expected_phases:
            conflicts.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "TIMING_PHASE_POLICY_CONFLICT",
                    "expected": expected_phases,
                    "actual": phases,
                }
            )
        if row.get("timing_mode_code") == "REPS" and not validation_value(
            row.get("default_seconds_per_rep")
        ):
            conflicts.append(
                {"representative_exercise_id": rep_id, "code": "REPS_SECONDS_PER_REP_MISSING"}
            )
        if row.get("timing_mode_code") == "DURATION" and not validation_value(
            row.get("default_work_seconds")
        ):
            conflicts.append(
                {"representative_exercise_id": rep_id, "code": "DURATION_WORK_SECONDS_MISSING"}
            )
    return {
        "required_field_missing_count": len(missing),
        "required_field_missing": missing,
        "invalid_taxonomy_code_count": len(invalid),
        "invalid_taxonomy_codes": invalid,
        "logical_conflict_count": len(conflicts),
        "logical_conflicts": conflicts,
        "stable_code_duplicate_count": len(stable_codes) - len(set(stable_codes)),
        "representative_id_duplicate_count": len(rep_ids) - len(set(rep_ids)),
        "hard_validation_passed": not missing
        and not invalid
        and not conflicts
        and len(stable_codes) == len(set(stable_codes))
        and len(rep_ids) == len(set(rep_ids)),
    }


EQUIPMENT_ONLY_PAIR_DEFINITIONS = [
    {
        "left_id": "REX-000006",
        "right_id": "REX-000105",
        "status": "CONFIRMED_EQUIPMENT_OR_ATTACHMENT_ONLY",
        "difference": "BARBELL -> CABLE_MACHINE + ROPE_ATTACHMENT",
        "note_ko": "둘 다 벤치에 누워 팔을 머리 뒤로 내렸다가 되돌리는 풀오버이며 장비·부착물만 다르다.",
    },
    {
        "left_id": "REX-000016",
        "right_id": "REX-000124",
        "status": "SEPARATE_EXERCISE_RETAINED",
        "difference": "BODYWEIGHT -> RESISTANCE_BAND + RESISTANCE_PROFILE",
        "note_ko": "둘 다 카프레이즈 계열이지만 주인님 요청에 따라 맨몸과 밴드 운동을 별도 운동으로 유지한다.",
    },
    {
        "left_id": "REX-000006",
        "right_id": "REX-000131",
        "status": "NOT_EQUIPMENT_ONLY",
        "difference": "BARBELL -> EZ_BAR + ELBOW_EXECUTION",
        "note_ko": "장비뿐 아니라 REX-000131은 팔꿈치를 약간 굽힌 벤트암 수행이므로 동일 장비 변형으로 확정하지 않는다.",
    },
    {
        "left_id": "REX-000015",
        "right_id": "REX-000137",
        "status": "NOT_EQUIPMENT_ONLY",
        "difference": "BODYWEIGHT -> DUMBBELL + REAR_FOOT_ELEVATION",
        "note_ko": "REX-000137은 뒤 벤치에 발을 올리는 불가리안 자세가 추가되어 장비만 다른 변형이 아니다.",
    },
    {
        "left_id": "REX-000080",
        "right_id": "REX-000128",
        "status": "REVIEW_REQUIRED_NOT_CONFIRMED",
        "difference": "BARBELL -> MACHINE + LOAD_SUPPORT_MECHANICS",
        "note_ko": "둘 다 앉은 카프 동작이지만 바벨을 허벅지에 두는 방식과 머신 레버 패드 방식의 지지·부하 전달이 달라 장비-only 여부를 보류한다.",
    },
    {
        "left_id": "REX-000016",
        "right_id": "REX-000125",
        "status": "NOT_EQUIPMENT_ONLY",
        "difference": "BILATERAL -> UNILATERAL_STANCE",
        "note_ko": "REX-000125는 한 발 지지와 균형 요구가 추가되어 장비 차이만으로 볼 수 없다.",
    },
]
MIGRATION_FIELD_NAMES = {
    "stable_code",
    "name_en",
    "display_name_ko",
    "source_track",
    "source_identity",
    "equipment_codes",
    "location_codes",
}


def equipment_only_review_rows(
    refined: list[dict[str, Any]], variant_candidates: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    by_id = {str(row["representative_exercise_id"]): row for row in refined}
    by_id.update(
        {str(row["representative_exercise_id"]): row for row in (variant_candidates or [])}
    )
    result: list[dict[str, Any]] = []
    for definition in EQUIPMENT_ONLY_PAIR_DEFINITIONS:
        left = by_id.get(definition["left_id"])
        right = by_id.get(definition["right_id"])
        if left is None or right is None:
            continue
        result.append(
            {
                "pair_id": f"{definition['left_id']}__{definition['right_id']}",
                "left_representative_exercise_id": definition["left_id"],
                "right_representative_exercise_id": definition["right_id"],
                "left_stable_code": left["stable_code"],
                "right_stable_code": right["stable_code"],
                "left_display_name_ko": left["display_name_ko"],
                "right_display_name_ko": right["display_name_ko"],
                "left_equipment_codes": left["equipment_codes"],
                "right_equipment_codes": right["equipment_codes"],
                "left_movement_pattern_code": left["primary_movement_pattern_code"],
                "right_movement_pattern_code": right["primary_movement_pattern_code"],
                "left_body_focus_code": left["body_focus_code"],
                "right_body_focus_code": right["body_focus_code"],
                "equipment_only_status": definition["status"],
                "difference_evidence": definition["difference"],
                "review_required": definition["status"] == "REVIEW_REQUIRED_NOT_CONFIRMED",
                "note_ko": definition["note_ko"],
            }
        )
    return result


def migration_rows(
    changes: list[dict[str, Any]],
    refined: list[dict[str, Any]],
    deletions: list[dict[str, Any]],
    variant_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_id = {str(row["representative_exercise_id"]): row for row in refined}
    by_id.update(
        {str(row["representative_exercise_id"]): row for row in (variant_candidates or [])}
    )
    result: list[dict[str, Any]] = []
    for change in changes:
        if change["field_name"] not in MIGRATION_FIELD_NAMES:
            continue
        target = by_id[change["representative_exercise_id"]]
        item = dict(change)
        item["stable_code_after"] = target["stable_code"]
        item["migration_target"] = target["representative_exercise_id"]
        item["alias_value"] = change["old_value"]
        item["canonical_value"] = change["new_value"]
        if change["field_name"] == "stable_code":
            item["alias_type"] = "STABLE_CODE_MIGRATION"
            item["migration_status"] = "MIGRATION_REQUIRED_BEFORE_FK_CUTOVER"
        else:
            item["alias_type"] = "ALIAS_PRESERVED"
            item["migration_status"] = "PRESERVED_ACTIVE_HISTORY"
        result.append(item)
    for deletion in deletions:
        result.append(
            {
                "representative_exercise_id": deletion["representative_exercise_id"],
                "stable_code_before": deletion["stable_code_before"],
                "stable_code_after": "",
                "field_name": "record_status",
                "old_value": "ACTIVE_CANONICAL",
                "new_value": "DELETED_FROM_ACTIVE_CATALOG",
                "alias_value": deletion["stable_code_before"],
                "canonical_value": "",
                "alias_type": "CANONICAL_DELETION",
                "migration_status": "REMOVE_FROM_ACTIVE_CATALOG",
                "migration_target": deletion["representative_exercise_id"],
                "evidence_reference": deletion["evidence_reference"],
                "note_ko": deletion["note_ko"],
            }
        )
    return result


def validate_migration_history(
    changes: list[dict[str, Any]],
    migration: list[dict[str, Any]],
    refined: list[dict[str, Any]],
    deletions: list[dict[str, Any]],
    variant_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    by_id = {str(row["representative_exercise_id"]): row for row in refined}
    by_id.update(
        {str(row["representative_exercise_id"]): row for row in (variant_candidates or [])}
    )
    expected_changes = [
        change for change in changes if change["field_name"] in MIGRATION_FIELD_NAMES
    ]
    expected_count = len(expected_changes) + len(deletions)
    if len(migration) != expected_count:
        errors.append(
            {
                "code": "MIGRATION_ROW_COUNT_MISMATCH",
                "expected": expected_count,
                "actual": len(migration),
            }
        )
    grouped_stable_codes: dict[str, set[str]] = {}
    for change in changes:
        grouped_stable_codes.setdefault(str(change["representative_exercise_id"]), set()).add(
            str(change.get("stable_code_before", ""))
        )
    for rep_id, values in grouped_stable_codes.items():
        if len(values) != 1 or "" in values:
            errors.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "MIGRATION_STABLE_CODE_BEFORE_NOT_IMMUTABLE",
                    "values": sorted(values),
                }
            )
    deletion_ids = {item["representative_exercise_id"] for item in deletions}
    for item in migration:
        rep_id = str(item["representative_exercise_id"])
        if item["field_name"] == "record_status":
            if rep_id not in deletion_ids or item["stable_code_after"]:
                errors.append(
                    {
                        "representative_exercise_id": rep_id,
                        "code": "DELETION_MIGRATION_TARGET_INVALID",
                    }
                )
            continue
        target = by_id.get(rep_id)
        if target is None or item["stable_code_after"] != target["stable_code"]:
            errors.append(
                {
                    "representative_exercise_id": rep_id,
                    "code": "MIGRATION_STABLE_CODE_AFTER_TARGET_MISMATCH",
                }
            )
        if item["alias_value"] != item["old_value"] or item["canonical_value"] != item["new_value"]:
            errors.append(
                {
                    "representative_exercise_id": rep_id,
                    "field_name": item["field_name"],
                    "code": "MIGRATION_ALIAS_VALUE_MISMATCH",
                }
            )
    return errors


def write_report(path: Path, report: dict[str, Any], output_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# v2.0.2 canonical 운동 필드·대표운동 검수 보고서",
        "",
        f"- 검수 버전: `{REVIEW_VERSION}`",
        f"- 생성 시각: `{GENERATED_AT}`",
        "- 입력: 관계 중복 정리가 완료된 v2.0.2 canonical 집합",
        "- 운영 사용: `production_eligible=false` 유지",
        "",
        "## 결과",
        "",
        f"- 대표운동 수: **{report['representative_count']}**",
        f"- 변형운동 후보 수: **{report['variant_candidate_count']}**",
        f"- 변형운동 후보 review_required 수: **{report['variant_candidate_review_required_count']}**",
        f"- 필드 수정 수: **{report['field_correction_count']}**",
        f"- review_required 수: **{report['review_required_count']}**",
        f"- 데이터 review_required 수(라이선스 제외): **{report['data_review_required_count']}**",
        f"- 삭제된 대표운동 수: **{report['deleted_representative_count']}**",
        f"- 1차 데이터 검수 행 수: **{report['first_pass_data_review_count']}**",
        f"- 장비-only 확정 후보 수: **{report['equipment_only_confirmed_count']}**",
        f"- 수정 이력 정합성 오류: **{report['migration_history_error_count']}**",
        f"- 애매한 review_required 수: **{report['ambiguous_review_required_count']}**",
        f"- 필수 필드 결측: **{report['validation']['required_field_missing_count']}**",
        f"- 허용되지 않은 taxonomy code: **{report['validation']['invalid_taxonomy_code_count']}**",
        f"- 논리 충돌: **{report['validation']['logical_conflict_count']}**",
        "",
        "## 해석",
        "",
        (
            "- 대표운동은 canonical identity별 1건으로 유지했으며 HOME 가능 여부를 "
            "이유로 대표운동을 맨몸 운동으로 교체하지 않았다."
        ),
        (
            "- 장소별 기본 추천 가능 여부는 대표성 판단과 분리해 identity review "
            "산출물의 `home_default_recommendation`·`gym_default_recommendation`으로 기록했다."
        ),
        (
            "- `BENCH`·`CHAIR`는 v2 release equipment code에서 제거하고 필요한 지지는 "
            "`setup_condition_ko`에 보존했다."
        ),
        (
            "- 주인님이 라이선스 자체는 문제없다고 확인했으므로 라이선스는 추가 검수 대상에서 제외한다. "
            "다만 원천 메타데이터의 기존 review flag는 감사 추적을 위해 그대로 보존했고, "
            "데이터 검수 수치는 해당 라이선스 flag를 제외해 별도 계산했다."
        ),
        (
            "- REX-000129는 사용자 요청에 따라 활성 canonical에서 제외했으며, 삭제 이력과 "
            "기존 stable code는 migration 산출물에 남겼다."
        ),
        (
            "- 활성 catalog 난이도는 BEGINNER/INTERMEDIATE만 허용한다. REX-000107·116·129·132는 "
            "삭제했고, REX-000105는 REX-000006의 케이블·로프 변형 후보로 분리했다."
        ),
        (
            "- REX-000121은 본문 수행 단계에 맞춰 맨몸 bicycle crunch로 canonicalize했지만, "
            "원천 이미지·제목의 band 표기는 provenance와 review flag로 보존했다."
        ),
        (
            "- 장비-only 표는 동일 수행으로 확정할 수 있는 후보와, 자세·지지·부하 전달이 달라 "
            "확정하지 않은 근접 후보를 구분한다."
        ),
        "",
        "## 산출물",
        "",
        f"- 정제 canonical: `{output_dir.name}/canonical_exercises_v2_0_2_refined.csv` / `.jsonl`",
        f"- field correction: `{output_dir.name}/field_corrections_v2_0_2.csv` / `.jsonl`",
        (
            f"- representative identity review: "
            f"`{output_dir.name}/representative_identity_review_v2_0_2.csv` / `.jsonl`"
        ),
        (
            f"- 대표운동 변형 후보: "
            f"`{output_dir.name}/representative_variant_candidates_v2_0_2.csv` / `.jsonl`"
        ),
        f"- alias/migration: `{output_dir.name}/alias_migration_v2_0_2.csv` / `.jsonl`",
        (
            f"- 1차 데이터 검수: "
            f"`{output_dir.name}/canonical_data_first_pass_review_v2_0_2.csv` / `.jsonl`"
        ),
        (
            f"- 장비-only 후보: "
            f"`{output_dir.name}/equipment_only_same_method_review_v2_0_2.csv` / `.jsonl`"
        ),
        f"- 삭제 이력: `{output_dir.name}/canonical_deletions_v2_0_2.csv` / `.jsonl`",
        f"- validation JSON: `{output_dir.name}/canonical_field_validation_report_v2_0_2.json`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    canonical_rows = read_records(args.canonical)
    v201_rows = read_csv(args.v2_0_1)
    integrated_rows = read_csv(args.integrated)
    taxonomy = read_json(args.taxonomy)
    refined, changes, aliases, result = review_and_refine(
        canonical_rows, v201_rows, integrated_rows, taxonomy
    )
    identity_reviews = result["identity_reviews"]
    validation = result["validation"]
    data_reviews = result["data_reviews"]
    deletions = result["deletions"]
    variant_candidates = result["variant_candidates"]
    equipment_only_reviews = equipment_only_review_rows(refined, variant_candidates)
    migration = migration_rows(changes, refined, deletions, variant_candidates)
    migration_history_errors = validate_migration_history(
        changes, migration, refined, deletions, variant_candidates
    )
    variant_validation = validate_refined(variant_candidates)
    validation["variant_candidate_validation"] = variant_validation
    validation["migration_history_error_count"] = len(migration_history_errors)
    validation["migration_history_errors"] = migration_history_errors
    validation["hard_validation_passed"] = (
        validation["hard_validation_passed"]
        and variant_validation["hard_validation_passed"]
        and not migration_history_errors
    )
    preferred_canonical = [
        "representative_exercise_id",
        "stable_code",
        "name_ko",
        "display_name_ko",
        "name_en",
        "training_type_code",
        "primary_movement_pattern_code",
        "body_focus_code",
        "primary_body_area_codes",
        "secondary_body_area_codes",
        "equipment_codes",
        "location_codes",
        "setup_condition_ko",
        "difficulty_code",
        "timing_mode_code",
        "phase_codes",
        "default_seconds_per_rep",
        "default_work_seconds",
        "default_rest_seconds",
        "default_transition_seconds",
        "instruction_summary_ko",
        "form_cues_ko",
        "instruction_content_version",
        "source_track",
        "source_identity",
        "source_key",
        "legacy_source_track",
        "legacy_source_identity",
        "legacy_source_key",
        *SOURCE_PROVENANCE_FIELDS,
        "source_provenance_status",
        "source_license_status",
        "instruction_identity_status",
        "timing_phase_review_status",
        "review_status_code",
        "review_required",
        "review_required_codes",
    ]
    preferred_variant = [
        "representative_exercise_id",
        "variant_parent_representative_exercise_id",
        "variant_relation_code",
        "candidate_status",
        *preferred_canonical,
    ]
    preferred_change = [
        "representative_exercise_id",
        "stable_code_before",
        "field_name",
        "old_value",
        "new_value",
        "change_type",
        "decision_code",
        "decision_status",
        "evidence_reference",
        "note_ko",
    ]
    preferred_identity = [
        "representative_group_key",
        "representative_exercise_id",
        "stable_code",
        "representative_role",
        "representative_selection_basis",
        "display_name_before",
        "display_name_after",
        "identity_decision_code",
        "identity_review_status",
        "identity_review_codes",
        "location_codes",
        "home_default_recommendation",
        "gym_default_recommendation",
        "representative_location_separation",
        "review_required",
    ]
    preferred_data_review = [
        "representative_exercise_id",
        "source_key",
        "source_name_en",
        "row_status",
        "instruction_alignment_status",
        "training_type_decision",
        "training_type_before",
        "training_type_after",
        "movement_pattern_decision",
        "movement_pattern_before",
        "movement_pattern_after",
        "body_focus_decision",
        "body_focus_before",
        "body_focus_after",
        "primary_body_area_decision",
        "primary_body_area_before",
        "primary_body_area_after",
        "secondary_body_area_decision",
        "secondary_body_area_before",
        "secondary_body_area_after",
        "difficulty_decision",
        "difficulty_before",
        "difficulty_after",
        "equipment_decision",
        "equipment_before",
        "equipment_after",
        "location_decision",
        "location_before",
        "location_after",
        "timing_decision",
        "timing_before",
        "timing_after",
        "instruction_summary_ko",
        "form_cues_ko",
        "review_required",
        "review_required_codes",
        "review_note_ko",
    ]
    preferred_equipment_only = [
        "pair_id",
        "left_representative_exercise_id",
        "right_representative_exercise_id",
        "left_stable_code",
        "right_stable_code",
        "left_display_name_ko",
        "right_display_name_ko",
        "left_equipment_codes",
        "right_equipment_codes",
        "left_movement_pattern_code",
        "right_movement_pattern_code",
        "left_body_focus_code",
        "right_body_focus_code",
        "equipment_only_status",
        "difference_evidence",
        "review_required",
        "note_ko",
    ]
    preferred_deletion = [
        "representative_exercise_id",
        "stable_code_before",
        "display_name_before",
        "name_en_before",
        "source_key",
        "deletion_status",
        "decision_code",
        "decision_status",
        "evidence_reference",
        "review_required",
        "note_ko",
    ]
    preferred_migration = [
        "representative_exercise_id",
        "stable_code_before",
        "stable_code_after",
        "field_name",
        "old_value",
        "new_value",
        "alias_value",
        "canonical_value",
        "alias_type",
        "migration_status",
        "migration_target",
        "evidence_reference",
        "note_ko",
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "canonical_exercises_v2_0_2_refined.csv", refined, preferred_canonical
    )
    write_jsonl(args.output_dir / "canonical_exercises_v2_0_2_refined.jsonl", refined)
    write_csv(
        args.output_dir / "representative_variant_candidates_v2_0_2.csv",
        variant_candidates,
        preferred_variant,
    )
    write_jsonl(
        args.output_dir / "representative_variant_candidates_v2_0_2.jsonl",
        variant_candidates,
    )
    write_csv(args.output_dir / "field_corrections_v2_0_2.csv", changes, preferred_change)
    write_jsonl(args.output_dir / "field_corrections_v2_0_2.jsonl", changes)
    write_csv(
        args.output_dir / "representative_identity_review_v2_0_2.csv",
        identity_reviews,
        preferred_identity,
    )
    write_jsonl(args.output_dir / "representative_identity_review_v2_0_2.jsonl", identity_reviews)
    write_csv(args.output_dir / "alias_migration_v2_0_2.csv", migration, preferred_migration)
    write_jsonl(args.output_dir / "alias_migration_v2_0_2.jsonl", migration)
    write_csv(
        args.output_dir / "canonical_data_first_pass_review_v2_0_2.csv",
        data_reviews,
        preferred_data_review,
    )
    write_jsonl(args.output_dir / "canonical_data_first_pass_review_v2_0_2.jsonl", data_reviews)
    write_csv(
        args.output_dir / "equipment_only_same_method_review_v2_0_2.csv",
        equipment_only_reviews,
        preferred_equipment_only,
    )
    write_jsonl(
        args.output_dir / "equipment_only_same_method_review_v2_0_2.jsonl",
        equipment_only_reviews,
    )
    write_csv(args.output_dir / "canonical_deletions_v2_0_2.csv", deletions, preferred_deletion)
    write_jsonl(args.output_dir / "canonical_deletions_v2_0_2.jsonl", deletions)
    report = {
        "schema_version": REVIEW_VERSION,
        "catalog_version_code": CATALOG_VERSION,
        "generated_at": GENERATED_AT,
        "status": "VALIDATION_COMPLETE_WITH_REVIEW_REQUIRED"
        if validation["review_required_count"]
        else "VALIDATION_COMPLETE",
        "production_eligible": False,
        "representative_count": validation["representative_count"],
        "variant_candidate_count": validation["variant_candidate_count"],
        "variant_candidate_review_required_count": validation[
            "variant_candidate_review_required_count"
        ],
        "variant_candidate_data_review_required_count": validation[
            "variant_candidate_data_review_required_count"
        ],
        "field_correction_count": validation["field_correction_count"],
        "review_required_count": validation["review_required_count"],
        "data_review_required_count": validation["data_review_required_count"],
        "deleted_representative_count": validation["deleted_representative_count"],
        "first_pass_data_review_count": validation["first_pass_data_review_count"],
        "equipment_only_confirmed_count": sum(
            item["equipment_only_status"].startswith("CONFIRMED") for item in equipment_only_reviews
        ),
        "equipment_only_review_required_count": sum(
            item["review_required"] for item in equipment_only_reviews
        ),
        "migration_history_error_count": len(migration_history_errors),
        "ambiguous_review_required_count": validation["ambiguous_review_required_count"],
        "source_license_review_required_count": validation["source_license_review_required_count"],
        "instruction_review_required_count": validation["instruction_review_required_count"],
        "identity_review_required_count": validation["identity_review_required_count"],
        "field_correction_by_field": validation["field_correction_by_field"],
        "field_correction_by_reason": validation["field_correction_by_reason"],
        "validation": {
            key: value
            for key, value in validation.items()
            if key
            not in {
                "field_correction_count",
                "representative_count",
                "variant_candidate_count",
                "variant_candidate_review_required_count",
                "variant_candidate_data_review_required_count",
                "review_required_count",
                "ambiguous_review_required_count",
                "source_license_review_required_count",
                "instruction_review_required_count",
                "identity_review_required_count",
                "deleted_representative_count",
                "first_pass_data_review_count",
                "source_conflict_review_required_count",
                "data_review_required_count",
                "migration_history_error_count",
                "migration_history_errors",
                "field_correction_by_field",
                "field_correction_by_reason",
            }
        },
        "inputs": {
            "canonical": str(args.canonical.relative_to(ROOT.parent))
            if args.canonical.is_relative_to(ROOT.parent)
            else str(args.canonical),
            "v2_0_1": str(args.v2_0_1.relative_to(ROOT.parent))
            if args.v2_0_1.is_relative_to(ROOT.parent)
            else str(args.v2_0_1),
            "integrated": str(args.integrated.relative_to(ROOT.parent))
            if args.integrated.is_relative_to(ROOT.parent)
            else str(args.integrated),
            "taxonomy": str(args.taxonomy.relative_to(ROOT.parent))
            if args.taxonomy.is_relative_to(ROOT.parent)
            else str(args.taxonomy),
        },
    }
    write_json(args.output_dir / "canonical_field_validation_report_v2_0_2.json", report)
    write_report(args.report, report, args.output_dir)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "representative_count",
                    "variant_candidate_count",
                    "field_correction_count",
                    "review_required_count",
                    "ambiguous_review_required_count",
                    "deleted_representative_count",
                    "first_pass_data_review_count",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if validation["hard_validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
