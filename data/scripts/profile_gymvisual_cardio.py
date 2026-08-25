# ruff: noqa: E501

"""Profile and screen the Gym Visual cardio candidates.

This is a stage-1 validation artifact only.  It never edits the raw snapshot,
does not create catalog/alternative/safety data, and deliberately leaves
intensity and MET values unresolved.
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
DEFAULT_RAW = REPO_ROOT / "data/raw/gym_visual"
DEFAULT_PROFILE = REPO_ROOT / "data/validation/profiles/gymvisual_cardio_profile.json"
DEFAULT_REVIEW_BATCH = REPO_ROOT / "data/validation/review_batches/gymvisual_cardio_review.csv"
PROFILE_VERSION = "gymvisual-cardio-profile-v0.1.0"
REVIEW_BATCH_VERSION = "gymvisual-cardio-review-v0.1.0"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(*items: str) -> list[dict[str, str]]:
    return [{"source": item, "type": "RAW_FIELD_OR_PIPELINE_RULE"} for item in items]


# The screening values are candidate proposals, not approved taxonomy or safety
# assignments.  They are intentionally explicit so a reviewer can audit the
# reason for every decision without relying on a name-to-MET mapping.
SCREENING: dict[str, dict[str, Any]] = {
    "3220": {
        "decision": "EXCLUDE",
        "reason_code": "HIGH_IMPACT_VARIANT_DUPLICATE",
        "reason": "잭 점프와 기능적으로 유사한 고충격 점프 변형이며 1단계 대표 운동으로 중복 선정하지 않음.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL", "CONTINUOUS"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "CONDITIONAL",
        "space_noise": "LARGE_LOUD",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.name", "raw.instruction_steps.en", "screening.high_impact_variant"
        ),
    },
    "3672": {
        "decision": "INCLUDE",
        "reason_code": "HOME_LOW_IMPACT_STEPPING",
        "reason": "홈에서 가능한 전후 스텝 대표 후보로, 지속형·인터벌 모두 확장 가능하고 저충격 커버리지를 보강함.",
        "locations": ["HOME"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "BEGINNER",
        "beginner": "CONDITIONAL",
        "space_noise": "MEDIUM_QUIET",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.equipment", "raw.instruction_steps.en", "screening.home_low_impact"
        ),
    },
    "3360": {
        "decision": "EXCLUDE",
        "reason_code": "FLOOR_COMPLEXITY_NOT_BEGINNER_PRIORITY",
        "reason": "바닥 지지·체간 안정성이 필요한 복합 동작으로 초보·복귀 우선 1단계 대표 유산소에서 제외함.",
        "locations": ["HOME"],
        "impact": "MODERATE",
        "mode": ["INTERVAL", "CONTINUOUS"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "MEDIUM_QUIET",
        "movement": "CORE_BRACE",
        "body_focus": "FULL_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.floor_complexity"),
    },
    "1160": {
        "decision": "EXCLUDE",
        "reason_code": "COMPLEX_HIGH_INTENSITY_NOT_BEGINNER_PRIORITY",
        "reason": "스쿼트·플랭크·점프가 결합된 고복잡도 변형으로 대표 고강도 2종을 넘는 중복을 피함.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": "CORE_BRACE",
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.name", "raw.instruction_steps.en", "screening.complex_high_intensity"
        ),
    },
    "2331": {
        "decision": "HOLD",
        "reason_code": "EQUIPMENT_SEMANTICS_UNCERTAIN",
        "reason": "원천 장비명이 leverage machine인 cycle cross trainer라 고정식 자전거와의 기구 경계가 불명확함.",
        "locations": ["GYM"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "사이클/크로스 트레이너(검토 필요)",
        "difficulty": "BEGINNER",
        "beginner": "REVIEW_REQUIRED",
        "space_noise": "MEDIUM_NOISE",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.name", "raw.equipment", "screening.equipment_semantics"),
    },
    "1201": {
        "decision": "EXCLUDE",
        "reason_code": "LOADED_BURPEE_NOT_BEGINNER_PRIORITY",
        "reason": "덤벨을 들고 수행하는 버피 변형으로 복합성·부하가 커 초보 우선 대표 목록에서 제외함.",
        "locations": ["HOME", "GYM"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "DUMBBELL",
        "equipment_label": "덤벨",
        "difficulty": "ADVANCED",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": "CORE_BRACE",
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.equipment", "raw.instruction_steps.en", "screening.loaded_burpee"
        ),
    },
    "3221": {
        "decision": "HOLD",
        "reason_code": "CARDIO_SCOPE_UNCERTAIN",
        "reason": "하프 니 벤드는 반복 스쿼트에 가까워 지속형 유산소인지 근력성 동작인지 추가 검토가 필요함.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "LOW",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "BEGINNER",
        "beginner": "REVIEW_REQUIRED",
        "space_noise": "MEDIUM_QUIET",
        "movement": "KNEE_DOMINANT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.name", "raw.instruction_steps.en", "screening.cardio_scope"),
    },
    "3636": {
        "decision": "INCLUDE",
        "reason_code": "HOME_SUPPORTED_LOW_IMPACT",
        "reason": "벽 지지로 균형 부담을 낮춘 홈 유산소 대표 후보이며 초보·복귀 사용자용 변형으로 활용 가능함.",
        "locations": ["HOME"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸(벽 지지)",
        "difficulty": "BEGINNER",
        "beginner": "CONDITIONAL",
        "space_noise": "SMALL_QUIET",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.supported_low_impact"),
    },
    "0501": {
        "decision": "EXCLUDE",
        "reason_code": "BURPEE_VARIANT_DUPLICATE",
        "reason": "기본 버피와 기능적으로 유사한 점프 변형으로 대표 고강도 운동과 중복됨.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "ADVANCED",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": "CORE_BRACE",
        "body_focus": "FULL_BODY",
        "evidence": evidence("raw.name", "raw.instruction_steps.en", "screening.burpee_variant"),
    },
    "3224": {
        "decision": "INCLUDE",
        "reason_code": "HOME_HIGH_IMPACT_REPRESENTATIVE",
        "reason": "홈 중·고강도 점프 계열의 대표 후보로 줄넘기와 다른 장비·동작 조합을 제공함.",
        "locations": ["HOME"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "BEGINNER",
        "beginner": "CONDITIONAL",
        "space_noise": "LARGE_LOUD",
        "movement": None,
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.instruction_steps.en",
            "screening.home_high_impact",
            "screening.equipment_diversity",
        ),
    },
    "2612": {
        "decision": "INCLUDE",
        "reason_code": "HOME_OUTDOOR_EQUIPMENT_DIVERSITY",
        "reason": "줄넘기 장비를 사용하는 지속형·인터벌 후보로 맨몸 점프와 장비 다양성을 보완함.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "줄넘기(기존 taxonomy 코드 검토 필요)",
        "difficulty": "INTERMEDIATE",
        "beginner": "CONDITIONAL",
        "space_noise": "MEDIUM_LOUD",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.equipment",
            "raw.instruction_steps.en",
            "screening.home_outdoor",
            "screening.unmapped_equipment",
        ),
    },
    "0630": {
        "decision": "EXCLUDE",
        "reason_code": "FLOOR_COMPLEXITY_NOT_BEGINNER_PRIORITY",
        "reason": "플랭크 기반의 체간·고관절 협응이 필요한 복합 동작으로 1단계 초보 우선 대표군에서 제외함.",
        "locations": ["HOME"],
        "impact": "MODERATE",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "SMALL_QUIET",
        "movement": "CORE_BRACE",
        "body_focus": "FULL_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.floor_complexity"),
    },
    "3638": {
        "decision": "EXCLUDE",
        "reason_code": "FLOOR_TO_STANDING_COMPLEXITY",
        "reason": "푸시업 자세에서 달리기 동작으로 전환하는 복합 변형으로 초보 우선성과 중복 커버리지 측면에서 제외함.",
        "locations": ["HOME"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "ADVANCED",
        "beginner": "NOT_PRIORITY",
        "space_noise": "MEDIUM_QUIET",
        "movement": "CORE_BRACE",
        "body_focus": "FULL_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.floor_to_standing"),
    },
    "0685": {
        "decision": "INCLUDE",
        "reason_code": "HOME_CONTINUOUS_JOG_IN_PLACE",
        "reason": "좁은 공간에서 수행하는 지속형 조깅 대표 후보로 저·중강도 홈 유산소 선택지를 보완함.",
        "locations": ["HOME"],
        "impact": "MODERATE",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "BEGINNER",
        "beginner": "CONDITIONAL",
        "space_noise": "MEDIUM_LOUD",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.home_continuous"),
    },
    "0684": {
        "decision": "EXCLUDE",
        "reason_code": "DUPLICATE_OF_RUN",
        "reason": "원천 단계 설명과 동작이 run과 동일하고 장비값도 body weight라 별도 선정하지 않음.",
        "locations": ["HOME"],
        "impact": "MODERATE",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "BEGINNER",
        "beginner": "CONDITIONAL",
        "space_noise": "MEDIUM_LOUD",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.name", "raw.instruction_steps.en", "screening.duplicate"),
    },
    "3219": {
        "decision": "EXCLUDE",
        "reason_code": "HIGH_IMPACT_VARIANT_DUPLICATE",
        "reason": "가위뛰기 점프 변형으로 잭 점프와 고충격 커버리지가 중복됨.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": None,
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.name", "raw.instruction_steps.en", "screening.high_impact_variant"
        ),
    },
    "3222": {
        "decision": "EXCLUDE",
        "reason_code": "HIGH_IMPACT_VARIANT_DUPLICATE",
        "reason": "반 스쿼트 점프 변형으로 잭 점프와 기능적 커버리지가 중복되고 무릎 중심 부담이 더 불명확함.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": "KNEE_DOMINANT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.name", "raw.instruction_steps.en", "screening.high_impact_variant"
        ),
    },
    "3656": {
        "decision": "INCLUDE",
        "reason_code": "OUTDOOR_SPACE_BASED_RUNNING",
        "reason": "실외 또는 트레드밀의 공간 기반 달리기 후보로, 제자리 조깅과 장소·공간 요구가 다른 야외 선택지를 제공함.",
        "locations": ["OUTDOOR", "GYM"],
        "impact": "MODERATE",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "개방 공간 또는 트레드밀(검토 필요)",
        "difficulty": "BEGINNER",
        "beginner": "CONDITIONAL",
        "space_noise": "LARGE_NOISE",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.instruction_steps.en", "screening.outdoor_space", "screening.unmapped_equipment"
        ),
    },
    "3361": {
        "decision": "EXCLUDE",
        "reason_code": "LATERAL_JUMP_VARIANT_NOT_BEGINNER_PRIORITY",
        "reason": "좌우 홉과 균형 조절이 필요한 고충격 민첩성 변형으로 대표 고강도군과 중복됨.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.lateral_jump"),
    },
    "3671": {
        "decision": "EXCLUDE",
        "reason_code": "LATERAL_JUMP_VARIANT_NOT_BEGINNER_PRIORITY",
        "reason": "스키 동작을 모사하는 좌우 점프 변형으로 잭 점프·줄넘기와 고충격 커버리지가 중복됨.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.lateral_jump"),
    },
    "3223": {
        "decision": "EXCLUDE",
        "reason_code": "HIGH_IMPACT_VARIANT_DUPLICATE",
        "reason": "스타 점프 변형으로 잭 점프와 고충격 커버리지가 중복됨.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "HIGH",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "LARGE_LOUD",
        "movement": None,
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.name", "raw.instruction_steps.en", "screening.high_impact_variant"
        ),
    },
    "2138": {
        "decision": "INCLUDE",
        "reason_code": "GYM_STATIONARY_BIKE",
        "reason": "헬스장 기구 기반 저충격 지속형 대표 후보로, 앉은 자세와 저소음 장비 선택지를 제공함.",
        "locations": ["GYM"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "고정식 자전거(기존 taxonomy 코드 검토 필요)",
        "difficulty": "BEGINNER",
        "beginner": "SUITABLE",
        "space_noise": "MEDIUM_NOISE",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.equipment",
            "raw.instruction_steps.en",
            "screening.gym_equipment",
            "screening.unmapped_equipment",
        ),
    },
    "0798": {
        "decision": "EXCLUDE",
        "reason_code": "DUPLICATE_OF_STATIONARY_BIKE",
        "reason": "stationary bike run v.3와 동일한 고정식 자전거 계열로 대표 기구 운동과 중복됨.",
        "locations": ["GYM"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "고정식 자전거(기존 taxonomy 코드 검토 필요)",
        "difficulty": "BEGINNER",
        "beginner": "SUITABLE",
        "space_noise": "MEDIUM_NOISE",
        "movement": None,
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.name", "raw.equipment", "raw.instruction_steps.en", "screening.duplicate"
        ),
    },
    "3318": {
        "decision": "HOLD",
        "reason_code": "MOVEMENT_SEMANTICS_UNCERTAIN",
        "reason": "swing 360의 실제 동작 궤적·공간 요구를 이름과 텍스트만으로 안정적으로 분류하기 어려움.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "REVIEW_REQUIRED",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "REVIEW_REQUIRED",
        "beginner": "REVIEW_REQUIRED",
        "space_noise": "REVIEW_REQUIRED",
        "movement": None,
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.name",
            "raw.instruction_steps.en",
            "screening.visual_deferred",
            "screening.movement_semantics",
        ),
    },
    "2141": {
        "decision": "INCLUDE",
        "reason_code": "GYM_LOW_IMPACT_ELLIPTICAL",
        "reason": "헬스장 저충격 크로스 트레이너 대표 후보로 자전거·트레드밀과 다른 전신성 기구 선택지를 보완함.",
        "locations": ["GYM"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "일립티컬/크로스 트레이너(기존 taxonomy 코드 검토 필요)",
        "difficulty": "BEGINNER",
        "beginner": "SUITABLE",
        "space_noise": "MEDIUM_NOISE",
        "movement": None,
        "body_focus": "FULL_BODY",
        "evidence": evidence(
            "raw.equipment",
            "raw.instruction_steps.en",
            "screening.gym_equipment",
            "screening.unmapped_equipment",
        ),
    },
    "3655": {
        "decision": "EXCLUDE",
        "reason_code": "LUNGE_VARIANT_NOT_BEGINNER_PRIORITY",
        "reason": "걷기·하이니·런지가 결합된 복합 하체 변형으로 전후 스텝과 조깅 대표군보다 복잡함.",
        "locations": ["HOME", "OUTDOOR"],
        "impact": "MODERATE",
        "mode": ["INTERVAL"],
        "equipment_code": "BODYWEIGHT",
        "equipment_label": "맨몸",
        "difficulty": "INTERMEDIATE",
        "beginner": "NOT_PRIORITY",
        "space_noise": "MEDIUM_QUIET",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence("raw.instruction_steps.en", "screening.lunge_complexity"),
    },
    "3666": {
        "decision": "INCLUDE",
        "reason_code": "GYM_TREADMILL_CONTINUOUS",
        "reason": "헬스장 저충격 지속형 걷기 대표 후보로 기구·강도 조절 선택지를 제공함. 강도 자체는 별도 검토함.",
        "locations": ["GYM"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "트레드밀(기존 taxonomy 코드 검토 필요)",
        "difficulty": "BEGINNER",
        "beginner": "SUITABLE",
        "space_noise": "MEDIUM_NOISE",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.equipment",
            "raw.instruction_steps.en",
            "screening.gym_equipment",
            "screening.unmapped_equipment",
        ),
    },
    "2311": {
        "decision": "INCLUDE",
        "reason_code": "GYM_STEPMILL_INTENSITY_VARIETY",
        "reason": "헬스장 계단형 기구로 3종의 저충격 기구와 다른 중·고강도 지속형 선택지를 보완함.",
        "locations": ["GYM"],
        "impact": "LOW",
        "mode": ["CONTINUOUS", "INTERVAL"],
        "equipment_code": None,
        "equipment_label": "스텝밀(기존 taxonomy 코드 검토 필요)",
        "difficulty": "INTERMEDIATE",
        "beginner": "CONDITIONAL",
        "space_noise": "MEDIUM_NOISE",
        "movement": "GAIT",
        "body_focus": "LOWER_BODY",
        "evidence": evidence(
            "raw.equipment",
            "raw.instruction_steps.en",
            "screening.gym_equipment",
            "screening.unmapped_equipment",
        ),
    },
    "3637": {
        "decision": "EXCLUDE",
        "reason_code": "ADVANCED_CORE_DEVICE_COMPLEXITY",
        "reason": "복근 롤아웃 형태의 코어·어깨 안정성 요구가 커 초보 우선 유산소 대표군에서 제외함.",
        "locations": ["HOME"],
        "impact": "MODERATE",
        "mode": ["INTERVAL"],
        "equipment_code": None,
        "equipment_label": "복근 롤러(기존 taxonomy 코드 검토 필요)",
        "difficulty": "ADVANCED",
        "beginner": "NOT_PRIORITY",
        "space_noise": "SMALL_QUIET",
        "movement": "CORE_BRACE",
        "body_focus": "CORE",
        "evidence": evidence(
            "raw.equipment", "raw.instruction_steps.en", "screening.advanced_core"
        ),
    },
}


REVIEW_COLUMNS = [
    "candidate_id",
    "source_name",
    "source_equipment",
    "source_media_id",
    "source_image",
    "source_gif_url",
    "screening_decision",
    "screening_reason_code",
    "screening_reason",
    "location_code_candidates",
    "impact_level_candidate",
    "exercise_mode_candidates",
    "equipment_code_candidate",
    "equipment_label_candidate",
    "difficulty_code_candidate",
    "beginner_suitability_candidate",
    "space_noise_level_candidate",
    "movement_pattern_code_candidate",
    "intensity_level_candidate",
    "met_value",
    "visual_reference_status",
    "review_required",
    "review_required_codes",
    "review_decision",
    "review_reason_code",
    "review_note",
    "reviewer",
    "reviewed_at",
]


def build_candidate(
    raw: dict[str, Any], screening: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    candidate_id = raw["id"]
    review_required = screening["decision"] in {"INCLUDE", "HOLD"}
    required_codes: list[str] = []
    if review_required:
        required_codes.append("INTENSITY_AND_MET_NOT_ESTABLISHED")
        required_codes.append("HUMAN_SELECTION_REVIEW")
    if review_required:
        required_codes.append("FINAL_CATALOG_VISUAL_CHECK_DEFERRED")
        if screening["equipment_code"] is None:
            required_codes.append("CARDIO_EQUIPMENT_TAXONOMY_MAPPING")
    if screening["decision"] == "HOLD":
        required_codes.append(screening["reason_code"])

    return {
        "candidate_id": candidate_id,
        "source_record": raw,
        "source_provenance": {
            "source_name": source["source_name"],
            "source_license": source["license"],
            "retrieved_at": source["retrieved_at"],
            "raw_status": source["status"],
            "raw_files": source["files"],
        },
        "normalized_candidates": {
            "training_type_code": "CARDIO",
            "body_focus_code": screening["body_focus"],
            "location_codes": screening["locations"],
            "impact_level_code": screening["impact"],
            "exercise_mode_codes": screening["mode"],
            "equipment_code": screening["equipment_code"],
            "equipment_label": screening["equipment_label"],
            "equipment_normalization_status": "TAXONOMY_CANDIDATE"
            if screening["equipment_code"]
            else "REVIEW_REQUIRED",
            "difficulty_code": screening["difficulty"],
            "beginner_suitability_code": screening["beginner"],
            "space_noise_level_code": screening["space_noise"],
            "movement_pattern_code": screening["movement"],
            "intensity_level_code": "REVIEW_REQUIRED",
            "met": None,
        },
        "screening": {
            "decision": screening["decision"],
            "reason_code": screening["reason_code"],
            "reason": screening["reason"],
        },
        "visual_evidence": {
            "image_reference": raw["image"],
            "gif_reference": raw["gif_url"],
            "binary_in_raw_snapshot": False,
            "status": "REFERENCE_ONLY_DEFERRED_TO_FINAL_CATALOG",
            "attribution": raw["attribution"],
        },
        "evidence": screening["evidence"],
        "review_required": review_required,
        "review_required_codes": required_codes,
        "production_eligible": False,
    }


def coverage(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    included = [item for item in candidates if item["screening"]["decision"] == "INCLUDE"]

    def count_values(path: tuple[str, ...], values: list[str] | None = None) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for item in included:
            value: Any = item
            for part in path:
                value = value[part]
            if isinstance(value, list):
                counter.update(str(entry) for entry in value)
            elif value is not None:
                counter[str(value)] += 1
        if values:
            return {value: counter.get(value, 0) for value in values}
        return dict(sorted(counter.items()))

    location_counts = count_values(("normalized_candidates", "location_codes"))
    impact_counts = count_values(("normalized_candidates", "impact_level_code"))
    mode_counts = count_values(("normalized_candidates", "exercise_mode_codes"))
    equipment_labels = count_values(("normalized_candidates", "equipment_label"))
    difficulty_counts = count_values(("normalized_candidates", "difficulty_code"))
    low_home = sum(
        "HOME" in item["normalized_candidates"]["location_codes"]
        and item["normalized_candidates"]["impact_level_code"] == "LOW"
        for item in included
    )
    high_home = sum(
        "HOME" in item["normalized_candidates"]["location_codes"]
        and item["normalized_candidates"]["impact_level_code"] in {"MODERATE", "HIGH"}
        for item in included
    )
    gym = sum(
        "GYM" in item["normalized_candidates"]["location_codes"]
        and item["source_record"]["equipment"] != "body weight"
        for item in included
    )
    outdoor = sum("OUTDOOR" in item["normalized_candidates"]["location_codes"] for item in included)
    gaps: list[dict[str, Any]] = []
    if low_home < 3:
        gaps.append(
            {
                "coverage_gap": "HOME_LOW_IMPACT",
                "selected": low_home,
                "target": "3-4",
                "reason": "명확한 저충격 홈 후보가 2종이며, half knee bends는 유산소 범위가 불명확해 HOLD 처리함.",
                "next_source": "wger_or_KSPO_HOME",
            }
        )
    if not any(item["normalized_candidates"]["equipment_code"] is None for item in included):
        gaps.append(
            {
                "coverage_gap": "CARDIO_EQUIPMENT_TAXONOMY",
                "reason": "기존 taxonomy에 cardio 기구 코드가 없음.",
            }
        )
    gaps.append(
        {
            "coverage_gap": "INTENSITY_MET_EVIDENCE",
            "reason": "Gym Visual 원천에는 MET/강도 근거가 없어 INCLUDE 전부 REVIEW_REQUIRED 및 met=null.",
            "next_source": "wger_or_KSPO_OR_DOMAIN_REFERENCE",
        }
    )
    gaps.append(
        {
            "coverage_gap": "VISUAL_CONFIRMATION",
            "reason": "GIF/이미지 바이너리는 최종 카탈로그 제작 단계에서 추가 예정이며 이번 단계는 참조 경로만 보존.",
            "next_step": "final_catalog_media_review",
        }
    )
    return {
        "included_count": len(included),
        "location_counts": location_counts,
        "impact_counts": impact_counts,
        "exercise_mode_counts": mode_counts,
        "equipment_counts": equipment_labels,
        "difficulty_counts": difficulty_counts,
        "target_bands": {
            "home_low_impact": {"selected": low_home, "target": "3-4"},
            "home_moderate_high_intensity": {"selected": high_home, "target": "2-3"},
            "gym_equipment": {"selected": gym, "target": "3-4"},
            "outdoor": {"selected": outdoor, "target": "about 2"},
            "continuous_and_interval": {
                "continuous": mode_counts.get("CONTINUOUS", 0),
                "interval": mode_counts.get("INTERVAL", 0),
            },
        },
        "coverage_gaps": gaps,
    }


def create_profile(raw_dir: Path) -> dict[str, Any]:
    raw_path = raw_dir / "exercises.json"
    source_path = raw_dir / "source.json"
    records = load_json(raw_path)
    source = load_json(source_path)
    cardio = [record for record in records if record.get("body_part") == "cardio"]
    missing = sorted(record["id"] for record in cardio if record["id"] not in SCREENING)
    extra = sorted(
        identifier
        for identifier in SCREENING
        if identifier not in {record["id"] for record in cardio}
    )
    if missing or extra:
        raise ValueError(f"screening map mismatch: missing={missing}, extra={extra}")
    screened_candidates = [
        build_candidate(record, SCREENING[record["id"]], source) for record in cardio
    ]
    disposition_counts = Counter(
        item["screening"]["decision"] for item in screened_candidates
    )
    candidates = [
        item for item in screened_candidates if item["screening"]["decision"] == "INCLUDE"
    ]
    return {
        "profile_version": PROFILE_VERSION,
        "status": "DRAFT_REVIEW_QUEUE",
        "production_eligible": False,
        "scope": {
            "stage": "1_CARDIO_SELECTION",
            "source_filter": {"field": "body_part", "equals": "cardio"},
            "selection_target": "8-12 without forced count",
            "raw_candidate_count": len(cardio),
        },
        "source": {
            "directory": str(raw_dir.relative_to(REPO_ROOT)),
            "source_manifest": source,
            "raw_sha256": {
                "exercises.json": sha256_file(raw_path),
                "source.json": sha256_file(source_path),
            },
        },
        "decision_counts": {"INCLUDE": len(candidates)},
        "screening_disposition_counts": dict(sorted(disposition_counts.items())),
        "screened_candidate_count": len(screened_candidates),
        "intensity_policy": {
            "intensity_level_code": "REVIEW_REQUIRED",
            "met": None,
            "rule": "이름·원천 category만으로 강도/MET를 확정하거나 자동 매핑하지 않음.",
        },
        "visual_policy": {
            "status": "REFERENCE_ONLY_DEFERRED_TO_FINAL_CATALOG",
            "rule": "이번 단계에는 GIF/이미지 바이너리를 추가하지 않고 원천 참조·저작자만 보존.",
        },
        "coverage": coverage(candidates),
        "candidates": candidates,
        "excluded_outputs": [
            "integrated_catalog",
            "exercise_groups",
            "exercise_alternatives",
            "safety_rules",
        ],
    }


def csv_row(candidate: dict[str, Any]) -> dict[str, Any]:
    raw = candidate["source_record"]
    normalized = candidate["normalized_candidates"]
    screening = candidate["screening"]
    return {
        "candidate_id": candidate["candidate_id"],
        "source_name": raw["name"],
        "source_equipment": raw["equipment"],
        "source_media_id": raw["media_id"],
        "source_image": raw["image"],
        "source_gif_url": raw["gif_url"],
        "screening_decision": screening["decision"],
        "screening_reason_code": screening["reason_code"],
        "screening_reason": screening["reason"],
        "location_code_candidates": "|".join(normalized["location_codes"]),
        "impact_level_candidate": normalized["impact_level_code"],
        "exercise_mode_candidates": "|".join(normalized["exercise_mode_codes"]),
        "equipment_code_candidate": normalized["equipment_code"] or "",
        "equipment_label_candidate": normalized["equipment_label"],
        "difficulty_code_candidate": normalized["difficulty_code"],
        "beginner_suitability_candidate": normalized["beginner_suitability_code"],
        "space_noise_level_candidate": normalized["space_noise_level_code"],
        "movement_pattern_code_candidate": normalized["movement_pattern_code"] or "",
        "intensity_level_candidate": normalized["intensity_level_code"],
        "met_value": "",
        "visual_reference_status": candidate["visual_evidence"]["status"],
        "review_required": "true" if candidate["review_required"] else "false",
        "review_required_codes": "|".join(candidate["review_required_codes"]),
        "review_decision": "",
        "review_reason_code": "",
        "review_note": "",
        "reviewer": "",
        "reviewed_at": "",
    }


def write_outputs(profile: dict[str, Any], profile_path: Path, review_path: Path) -> None:
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for candidate in profile["candidates"]:
            writer.writerow(csv_row(candidate))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--profile-out", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--review-batch-out", type=Path, default=DEFAULT_REVIEW_BATCH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = create_profile(args.raw_dir.resolve())
    write_outputs(profile, args.profile_out.resolve(), args.review_batch_out.resolve())
    print(
        json.dumps(
            {
                "profile": str(args.profile_out),
                "review_batch": str(args.review_batch_out),
                "decision_counts": profile["decision_counts"],
                "coverage_gaps": len(profile["coverage"]["coverage_gaps"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
