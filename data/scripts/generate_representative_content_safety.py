#!/usr/bin/env python3
"""Generate draft user-facing content and safety records for representative exercises.

The input taxonomy is copied by key fields without mutation.  Safety text is derived
only from an approved movement-pattern/equipment signal.  Rows whose taxonomy does
not provide enough evidence receive a fail-closed review marker instead of an
invented risk rule.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

CONTENT_COLUMNS = [
    "representative_id",
    "exercise_name_ko",
    "short_description",
    "target_muscle",
    "difficulty",
    "how_to_steps",
    "common_mistakes",
    "source_ids",
    "taxonomy_review_status",
    "generation_basis_code",
    "content_review_status",
]

SAFETY_COLUMNS = [
    "representative_id",
    "exercise_name_ko",
    "risk_area",
    "safety_rule",
    "avoid_condition",
    "alternative_reason",
    "source_ids",
    "taxonomy_review_status",
    "generation_basis_code",
    "safety_review_status",
]

LOG_COLUMNS = [
    "representative_id",
    "exercise_name_ko",
    "taxonomy_review_status",
    "review_required_codes",
    "content_description_required_present",
    "content_description_resolution",
    "safety_rule_required_present",
    "safety_rule_resolution",
    "content_review_status",
    "safety_review_status",
    "unresolved_review_required_codes",
    "source_ids",
]

TARGET_LABELS = {
    "ADDUCTORS": "허벅지 안쪽",
    "BACK": "등",
    "BICEPS": "팔 앞쪽",
    "CALVES": "종아리",
    "CARDIO": "전신",
    "CHEST": "가슴",
    "CORE": "몸통 주변",
    "GLUTES": "엉덩이",
    "HAMSTRINGS": "허벅지 뒤쪽",
    "LATS": "등 옆쪽",
    "QUADRICEPS": "허벅지 앞쪽",
    "SHOULDERS": "어깨",
    "SPINE": "등과 몸통",
    "TRICEPS": "팔 뒤쪽",
    "UPPER_BACK": "등 위쪽",
    "FOREARMS": "팔뚝",
    "FULL_BODY": "전신",
    "MOBILITY": "해당 관절",
    "UNSPECIFIED": "전신",
}

BODY_AREA_LABELS = {
    "ABDOMEN": "복부",
    "ANKLE_FOOT": "발목과 발",
    "CHEST": "가슴",
    "ELBOW": "팔꿈치",
    "HIP": "고관절",
    "KNEE": "무릎",
    "LOWER_BACK": "허리",
    "NECK": "목",
    "SHOULDER": "어깨",
    "UPPER_BACK": "상부 등",
    "WRIST_HAND": "손목과 손",
}

KNOWN_PATTERNS = {
    "BALANCE",
    "CORE_BRACE",
    "CYCLING",
    "ELLIPTICAL",
    "GAIT",
    "HIP_DOMINANT",
    "HORIZONTAL_PULL",
    "HORIZONTAL_PUSH",
    "ISOLATION",
    "KNEE_DOMINANT",
    "KNEE_FLEXION",
    "JUMP_PLYOMETRIC",
    "MOBILITY_STRETCH",
    "VERTICAL_PULL",
    "VERTICAL_PUSH",
}

CONTENT_BANNED_TERMS = ("진단", "치료", "처방", "질환", "재활", "염증")


def json_cell(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def target_label(raw: str) -> str:
    if raw in TARGET_LABELS:
        return TARGET_LABELS[raw]
    if raw in {"앞쪽 골반", "복부", "안쪽 넓적다리", "앞쪽 넓적다리", "뒤쪽 넓적다리"}:
        return raw
    return "해당 부위"


def primary_area_label(row: dict[str, str]) -> str:
    raw = row.get("primary_body_area_codes", "")
    if raw:
        try:
            areas = json.loads(raw)
        except json.JSONDecodeError:
            areas = []
        labels = [BODY_AREA_LABELS.get(area, "") for area in areas if isinstance(area, str)]
        labels = [label for label in labels if label]
        if labels:
            return "·".join(labels)
    return target_label(row["target_muscle"])


def object_with_particle(label: str) -> str:
    last = label[-1]
    if "가" <= last <= "힣":
        has_final_consonant = (ord(last) - ord("가")) % 28 != 0
        return label + ("을" if has_final_consonant else "를")
    return label + "을"


def is_mobility(row: dict[str, str]) -> bool:
    return (
        row["movement_pattern"] == "MOBILITY_STRETCH"
        or row["exercise_family"] == "MOBILITY_STRETCH"
    )


def is_cardio(row: dict[str, str]) -> bool:
    return row["training_type"] == "CARDIO" or row["movement_pattern"] == "GAIT"


def content_for(row: dict[str, str]) -> dict[str, str]:
    name = row["representative_name_ko"]
    pattern = row["movement_pattern"]
    target = primary_area_label(row) if is_mobility(row) else target_label(row["target_muscle"])
    target_object = object_with_particle(target)

    if pattern == "BALANCE":
        description = f"{name} 운동은 한 발로 서서 몸의 균형을 확인하는 운동입니다."
        steps = [
            "주변을 정리하고 필요하면 벽이나 의자 가까이에 선다.",
            "한 발을 바닥에 두고 다른 발을 천천히 들어 올린다.",
            "시선을 앞에 두고 몸이 흔들리지 않는 범위에서 유지한다.",
            "발을 천천히 내려 양발로 돌아온 뒤 반대쪽도 수행한다.",
        ]
        mistakes = [
            "주변을 확인하지 않고 시작한다.",
            "균형이 무너질 때까지 버틴다.",
            "발을 바닥에 세게 내딛거나 몸을 급하게 돌린다.",
        ]
    elif pattern == "JUMP_PLYOMETRIC":
        description = (
            f"{name} 운동은 팔과 다리를 함께 움직이며 반복해서 가볍게 뛰는 유산소 운동입니다."
        )
        steps = [
            "주변 공간을 확인하고 발을 편하게 모아 선다.",
            "무릎을 살짝 굽힌 채 팔과 다리를 함께 벌리며 가볍게 뛴다.",
            "발 앞쪽부터 부드럽게 착지하고 같은 리듬으로 반복한다.",
            "속도를 낮추며 발을 모으고 호흡을 정리한다.",
        ]
        mistakes = [
            "주변 공간을 확인하지 않고 크게 움직인다.",
            "무릎을 굳힌 채 세게 착지한다.",
            "리듬이 무너졌는데도 속도를 계속 높인다.",
        ]
    elif pattern == "CYCLING":
        description = f"{name} 운동은 고정된 자전거 페달을 일정한 리듬으로 밟는 유산소 운동입니다."
        steps = [
            "안장과 손잡이 위치를 편하게 맞춘다.",
            "페달에 발을 안정적으로 올리고 천천히 시작한다.",
            "상체를 편안히 유지하며 일정한 리듬으로 페달을 밟는다.",
            "저항과 속도를 낮추며 천천히 마무리한다.",
        ]
        mistakes = [
            "안장 위치를 확인하지 않고 시작한다.",
            "상체를 과하게 숙이거나 손잡이를 세게 누른다.",
            "처음부터 저항과 속도를 높인다.",
        ]
    elif pattern == "ELLIPTICAL":
        description = (
            f"{name} 운동은 발판과 손잡이를 함께 사용해 일정한 리듬으로 움직이는 유산소 운동입니다."
        )
        steps = [
            "발판과 손잡이를 확인하고 양발을 안정적으로 올린다.",
            "천천히 페달을 움직이며 편한 리듬을 찾는다.",
            "시선을 앞에 두고 손잡이는 가볍게 잡는다.",
            "속도와 저항을 낮추며 발판에서 안전하게 내린다.",
        ]
        mistakes = [
            "발판에 발을 안정적으로 올리기 전에 시작한다.",
            "손잡이를 세게 당기거나 몸을 크게 흔든다.",
            "속도와 저항을 한 번에 높인다.",
        ]
    elif is_mobility(row):
        description = (
            f"{name} 운동은 {target} 주변을 천천히 움직이며 범위를 확인하는 스트레칭입니다."
        )
        steps = [
            "편안한 시작 자세를 잡고 주변 공간을 확인한다.",
            "숨을 고르게 쉬며 안내된 방향으로 천천히 움직인다.",
            "당김이 느껴지는 범위에서 잠시 멈춘다.",
            "반동 없이 시작 자세로 천천히 돌아온다.",
        ]
        mistakes = [
            "반동을 주며 빠르게 흔든다.",
            "당김이 큰 범위까지 억지로 늘린다.",
            "숨을 참은 채 오래 버틴다.",
        ]
    elif is_cardio(row):
        description = f"{name} 운동은 일정한 리듬으로 몸을 움직이는 유산소 운동입니다."
        steps = [
            "주변 공간과 발을 디딜 곳을 확인한다.",
            "천천히 시작해 편안한 리듬을 찾는다.",
            "시선을 앞에 두고 발을 안정적으로 디딘다.",
            "속도와 움직임을 낮추며 마무리한다.",
        ]
        mistakes = [
            "처음부터 속도를 너무 높인다.",
            "발밑과 주변을 확인하지 않는다.",
            "균형이 흔들리는데도 계속한다.",
        ]
    elif pattern == "CORE_BRACE":
        description = f"{name} 운동은 몸통을 유지하며 {target}에 힘을 쓰는 운동입니다."
        steps = [
            "안내된 시작 자세를 안정적으로 잡는다.",
            "배 주변에 가볍게 힘을 주고 숨을 쉰다.",
            "몸통이 흔들리지 않는 범위에서 팔이나 다리를 움직인다.",
            "천천히 시작 자세로 돌아온다.",
        ]
        mistakes = [
            "허리나 몸통이 크게 흔들린다.",
            "호흡을 멈춘 채 힘을 준다.",
            "속도를 높여 움직임 범위를 과하게 넓힌다.",
        ]
    elif pattern == "KNEE_DOMINANT":
        description = f"{name} 운동은 다리를 굽혔다 펴며 {target_object} 사용하는 운동입니다."
        steps = [
            "발을 편하게 벌리고 양발에 무게를 나눈다.",
            "엉덩이를 뒤로 보내며 무릎을 천천히 굽힌다.",
            "발바닥을 바닥에 두고 편한 범위까지만 내려간다.",
            "발로 바닥을 밀며 천천히 시작 자세로 돌아온다.",
        ]
        mistakes = [
            "발바닥이 들리거나 무릎이 안쪽으로 무너진다.",
            "반동으로 빠르게 내려갔다 올라온다.",
            "자신이 조절하기 어려운 깊이까지 내려간다.",
        ]
    elif pattern == "HIP_DOMINANT":
        description = f"{name} 운동은 엉덩이를 뒤로 보내며 {target_object} 사용하는 운동입니다."
        steps = [
            "발을 편하게 두고 기구나 주변을 안정적으로 준비한다.",
            "엉덩이를 뒤로 보내며 상체를 천천히 기울인다.",
            "등과 목을 편안히 두고 엉덩이로 힘을 낸다.",
            "천천히 시작 자세로 돌아온다.",
        ]
        mistakes = [
            "등을 둥글게 말거나 목을 과하게 든다.",
            "허리를 꺾어 끝 범위를 만든다.",
            "기구를 흔들거나 반동으로 들어 올린다.",
        ]
    elif pattern == "HORIZONTAL_PUSH":
        description = f"{name} 운동은 팔을 앞으로 밀어 {target_object} 사용하는 운동입니다."
        steps = [
            "손과 발 또는 기구를 안정적으로 준비한다.",
            "어깨가 으쓱하지 않게 팔을 천천히 밀어낸다.",
            "팔꿈치를 조절할 수 있는 범위에서 굽힌다.",
            "천천히 처음 위치로 돌아온다.",
        ]
        mistakes = [
            "어깨를 귀 쪽으로 올린다.",
            "팔꿈치를 갑자기 잠그거나 크게 벌린다.",
            "몸통이 흔들리는데도 반복을 이어간다.",
        ]
    elif pattern == "VERTICAL_PUSH":
        description = f"{name} 운동은 팔을 위로 밀어 {target_object} 사용하는 운동입니다."
        steps = [
            "등과 발 또는 엉덩이를 안정적으로 둔다.",
            "손잡이나 기구를 어깨 가까이에 준비한다.",
            "허리를 꺾지 않고 편한 범위에서 위로 밀어낸다.",
            "천천히 시작 위치로 내려온다.",
        ]
        mistakes = [
            "허리를 꺾어 팔을 더 높이 올린다.",
            "어깨를 으쓱한 채 반복한다.",
            "기구를 빠르게 내린다.",
        ]
    elif pattern == "HORIZONTAL_PULL":
        description = f"{name} 운동은 팔꿈치를 뒤로 보내며 {target_object} 사용하는 운동입니다."
        steps = [
            "가슴을 편안히 열고 손잡이나 기구를 잡는다.",
            "어깨를 끌어올리지 않고 팔꿈치를 뒤로 보낸다.",
            "손잡이를 몸 가까이 가져온 뒤 잠시 멈춘다.",
            "팔을 천천히 펴며 처음 위치로 돌아온다.",
        ]
        mistakes = [
            "어깨를 으쓱하며 당긴다.",
            "몸을 뒤로 젖혀 반동을 만든다.",
            "기구를 놓듯 팔을 빠르게 편다.",
        ]
    elif pattern == "VERTICAL_PULL":
        description = f"{name} 운동은 팔꿈치를 아래로 당기며 {target_object} 사용하는 운동입니다."
        steps = [
            "손잡이를 안정적으로 잡고 몸을 준비한다.",
            "어깨를 내린 채 팔꿈치를 아래로 당긴다.",
            "조절할 수 있는 범위까지만 당긴다.",
            "팔을 천천히 펴며 시작 위치로 돌아온다.",
        ]
        mistakes = [
            "몸을 크게 흔들어 당긴다.",
            "어깨를 귀 쪽으로 올린다.",
            "팔을 갑자기 놓아 기구가 튕긴다.",
        ]
    elif pattern == "KNEE_FLEXION":
        description = f"{name} 운동은 다리를 굽혔다 펴며 {target_object} 사용하는 운동입니다."
        steps = [
            "기구에 앉아 몸과 기구의 위치를 맞춘다.",
            "다리를 천천히 굽힌다.",
            "조절할 수 있는 범위에서 잠시 멈춘다.",
            "천천히 다리를 되돌린다.",
        ]
        mistakes = [
            "기구의 시작 위치를 확인하지 않는다.",
            "다리를 반동으로 빠르게 움직인다.",
            "기구를 놓듯 다리를 갑자기 편다.",
        ]
    elif pattern == "ISOLATION":
        description = (
            f"{name} 운동은 다른 부위의 움직임을 줄이고 {target_object} 집중해 사용하는 운동입니다."
        )
        steps = [
            "시작 자세와 기구를 안정적으로 준비한다.",
            "안내된 부위를 중심으로 천천히 움직인다.",
            "끝 범위에서 힘을 잠시 유지한다.",
            "반동 없이 시작 자세로 돌아온다.",
        ]
        mistakes = [
            "몸을 흔들어 반동을 만든다.",
            "다른 부위까지 크게 움직인다.",
            "기구를 빠르게 내려놓는다.",
        ]
    else:
        description = f"{name} 운동은 안내된 범위에서 천천히 움직이는 운동입니다."
        steps = [
            "시작 자세와 주변 공간을 확인한다.",
            "안내된 범위에서 천천히 움직인다.",
            "호흡을 멈추지 않고 편한 리듬을 유지한다.",
            "불편하면 속도와 범위를 낮춰 마무리한다.",
        ]
        mistakes = [
            "설명되지 않은 범위까지 임의로 크게 움직인다.",
            "장비를 확인하지 않고 시작한다.",
            "불편함을 무시하고 계속한다.",
        ]

    return {
        "short_description": description,
        "how_to_steps": json_cell(steps),
        "common_mistakes": json_cell(mistakes),
    }


def isolation_risk_area(row: dict[str, str]) -> str:
    target = row["target_muscle"]
    if target in {"SHOULDERS", "UPPER_BACK"}:
        return "어깨·팔꿈치"
    if target in {"BICEPS", "TRICEPS"}:
        return "팔꿈치·손목"
    if target == "FOREARMS":
        return "손목·팔꿈치"
    if target == "CHEST":
        return "어깨·팔꿈치·손목"
    if target in {"QUADRICEPS", "GLUTES", "CALVES", "HAMSTRINGS", "ADDUCTORS"}:
        return "무릎·발목·고관절"
    return "사용 부위와 인접 관절"


def safety_for(row: dict[str, str]) -> dict[str, str]:
    pattern = row["movement_pattern"]
    if pattern not in KNOWN_PATTERNS:
        return {
            "risk_area": "동작·장비 확인 필요",
            "safety_rule": (
                "세부 동작과 장비 정보가 확인되기 전에는 사용자 노출용 안전 규칙으로 "
                "사용하지 않는다."
            ),
            "avoid_condition": "검수되지 않은 동작 정보로 운동을 시작하지 않는다.",
            "alternative_reason": (
                "근거 없는 위험 규칙을 만들지 않고, 동작 근거가 확인된 대체 운동을 우선하기 위해."
            ),
            "generation_basis_code": "INSUFFICIENT_TAXONOMY_EVIDENCE",
            "safety_review_status": "REVIEW_REQUIRED",
        }

    if pattern == "BALANCE":
        risk_area = "발목·무릎·고관절"
        rule = "주변을 정리하고 벽이나 의자 가까이에서 천천히 균형을 확인한다."
        avoid = "균형이 크게 흔들리거나 발목·무릎의 불편이 커지면 발을 내려 멈춘다."
    elif pattern == "JUMP_PLYOMETRIC":
        risk_area = "발목·무릎·고관절"
        rule = (
            "주변 공간을 확보하고 무릎을 살짝 굽혀 부드럽게 착지하며 조절 가능한 리듬으로 수행한다."
        )
        avoid = "착지가 불안정하거나 발목·무릎·고관절의 불편이 커지면 점프를 멈춘다."
    elif pattern == "CYCLING":
        risk_area = "무릎·고관절·허리"
        rule = "안장과 손잡이를 편하게 맞추고 낮은 저항에서 천천히 페달을 밟는다."
        avoid = "무릎·고관절·허리의 불편이 커지거나 기구를 안정적으로 조절하기 어려우면 멈춘다."
    elif pattern == "ELLIPTICAL":
        risk_area = "발목·무릎·고관절"
        rule = "발판과 손잡이를 안정적으로 확인한 뒤 낮은 속도와 저항에서 시작한다."
        avoid = "발판에서 균형을 잃거나 발목·무릎·고관절의 불편이 커지면 즉시 멈춘다."
    elif is_mobility(row):
        risk_area = f"{primary_area_label(row)} 주변과 인접 관절"
        rule = "반동 없이 천천히 움직이고, 당김이 커지기 전의 범위에서 멈춘다."
        avoid = "해당 부위에 통증이 있거나 움직일수록 불편이 커지면 동작을 멈춘다."
    elif is_cardio(row):
        risk_area = "발목·무릎·고관절"
        rule = "주변 공간과 발을 디딜 곳을 확인하고, 조절 가능한 속도와 리듬으로 수행한다."
        avoid = "균형이 흔들리거나 어지럽고 숨이 지나치게 차면 즉시 멈추고 쉬어간다."
    elif pattern == "CORE_BRACE":
        risk_area = "허리·목"
        rule = "호흡을 멈추지 않고 몸통이 흔들리지 않는 범위에서 천천히 수행한다."
        avoid = "허리나 목의 불편이 커지거나 호흡을 유지하기 어려우면 멈춘다."
    elif pattern == "KNEE_DOMINANT":
        risk_area = "무릎·발목"
        rule = "발바닥을 안정적으로 두고 조절할 수 있는 깊이와 속도로 수행한다."
        avoid = "무릎이나 발목의 불편이 커지거나 발을 안정적으로 딛기 어려우면 멈춘다."
    elif pattern == "HIP_DOMINANT":
        risk_area = "허리·엉덩이·뒤쪽 다리"
        rule = "등과 목을 편안히 두고 엉덩이를 뒤로 보내며 조절 가능한 범위에서 수행한다."
        avoid = "허리나 뒤쪽 다리의 불편이 커지거나 등을 유지하기 어려우면 멈춘다."
    elif pattern in {"HORIZONTAL_PUSH", "VERTICAL_PUSH"}:
        risk_area = "어깨·팔꿈치·손목"
        rule = "기구와 손목을 안정적으로 준비하고, 어깨를 으쓱하지 않는 범위에서 천천히 밀어낸다."
        avoid = "어깨·팔꿈치·손목의 불편이 커지거나 기구를 조절하기 어려우면 멈춘다."
    elif pattern in {"HORIZONTAL_PULL", "VERTICAL_PULL"}:
        risk_area = "어깨·팔꿈치·손목"
        rule = "몸을 흔들지 않고 어깨를 내린 상태에서 조절 가능한 범위로 당긴다."
        avoid = "어깨·팔꿈치·손목의 불편이 커지거나 기구가 튕기면 멈춘다."
    elif pattern == "KNEE_FLEXION":
        risk_area = "무릎·뒤쪽 다리"
        rule = "기구의 위치를 맞춘 뒤 다리를 반동 없이 천천히 굽혔다 편다."
        avoid = "무릎이나 뒤쪽 다리의 불편이 커지거나 기구 위치가 맞지 않으면 멈춘다."
    elif pattern == "ISOLATION":
        risk_area = isolation_risk_area(row)
        rule = "기구를 안정적으로 잡고 다른 부위의 반동을 줄인 채 조절 가능한 범위에서 수행한다."
        avoid = "사용 부위나 인접 관절의 불편이 커지거나 기구를 조절하기 어려우면 멈춘다."
    else:
        risk_area = "동작과 관련된 부위"
        rule = "호흡을 멈추지 않고 조절 가능한 범위에서 천천히 수행한다."
        avoid = "해당 부위의 불편이 커지면 동작을 멈추고 쉬어간다."

    return {
        "risk_area": risk_area,
        "safety_rule": rule,
        "avoid_condition": avoid,
        "alternative_reason": "부담을 낮춘 동작으로 같은 움직임 목표를 이어가기 위해.",
        "generation_basis_code": f"MOVEMENT_PATTERN:{pattern}",
        "safety_review_status": "DOMAIN_REVIEW_REQUIRED",
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty input: {path}")
    required = {
        "representative_id",
        "representative_name_ko",
        "movement_pattern",
        "training_type",
        "target_muscle",
        "difficulty",
        "exercise_family",
        "source_ids",
        "taxonomy_review_status",
        "review_required_codes",
    }
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"input missing columns: {sorted(missing)}")
    ids = [row["representative_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate representative_id in input")
    return rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(input_path: Path, output_dir: Path) -> dict[str, Any]:
    taxonomy = read_rows(input_path)
    content_rows: list[dict[str, str]] = []
    safety_rows: list[dict[str, str]] = []
    log_rows: list[dict[str, str]] = []

    for row in taxonomy:
        content = content_for(row)
        safety = safety_for(row)
        for value in content.values():
            if any(term in value for term in CONTENT_BANNED_TERMS):
                raise ValueError(f"banned medical term in content: {row['representative_id']}")

        codes = {code for code in row["review_required_codes"].split("|") if code}
        content_present = "CONTENT_DESCRIPTION_REQUIRED" in codes
        safety_present = "SAFETY_RULE_REQUIRED" in codes
        content_resolution = "RESOLVED_GENERATED" if content_present else "NOT_PRESENT"
        safety_resolution = (
            "RESOLVED_GENERATED"
            if safety_present and safety["safety_review_status"] == "DOMAIN_APPROVED"
            else "UNRESOLVED_REVIEW_REQUIRED"
            if safety_present
            else "NOT_PRESENT"
        )

        content_rows.append(
            {
                "representative_id": row["representative_id"],
                "exercise_name_ko": row["representative_name_ko"],
                **content,
                "target_muscle": row["target_muscle"],
                "difficulty": row["difficulty"],
                "source_ids": row["source_ids"],
                "taxonomy_review_status": row["taxonomy_review_status"],
                "generation_basis_code": (
                    f"TAXONOMY:{row['movement_pattern']}|NAME:{row['exercise_family']}"
                ),
                "content_review_status": "GENERATED_CONTENT_REVIEW_REQUIRED",
            }
        )
        safety_rows.append(
            {
                "representative_id": row["representative_id"],
                "exercise_name_ko": row["representative_name_ko"],
                **safety,
                "source_ids": row["source_ids"],
                "taxonomy_review_status": row["taxonomy_review_status"],
            }
        )
        unresolved = sorted(codes)
        log_rows.append(
            {
                "representative_id": row["representative_id"],
                "exercise_name_ko": row["representative_name_ko"],
                "taxonomy_review_status": row["taxonomy_review_status"],
                "review_required_codes": row["review_required_codes"],
                "content_description_required_present": str(content_present).lower(),
                "content_description_resolution": content_resolution,
                "safety_rule_required_present": str(safety_present).lower(),
                "safety_rule_resolution": safety_resolution,
                "content_review_status": "GENERATED_CONTENT_REVIEW_REQUIRED",
                "safety_review_status": safety["safety_review_status"],
                "unresolved_review_required_codes": "|".join(unresolved),
                "source_ids": row["source_ids"],
            }
        )

    write_csv(output_dir / "representative_exercise_content.csv", CONTENT_COLUMNS, content_rows)
    write_csv(output_dir / "exercise_safety_rules.csv", SAFETY_COLUMNS, safety_rows)
    write_csv(output_dir / "content_safety_review_log.csv", LOG_COLUMNS, log_rows)

    # Fail closed: output IDs and taxonomy-derived values must exactly match input.
    by_id = {row["representative_id"]: row for row in taxonomy}
    for row in content_rows:
        source = by_id[row["representative_id"]]
        for field in (
            "exercise_name_ko",
            "target_muscle",
            "difficulty",
            "source_ids",
            "taxonomy_review_status",
        ):
            input_field = "representative_name_ko" if field == "exercise_name_ko" else field
            if row[field] != source[input_field]:
                raise ValueError(
                    f"taxonomy value changed in content: {row['representative_id']} {field}"
                )
    for row in safety_rows:
        source = by_id[row["representative_id"]]
        for field in ("exercise_name_ko", "source_ids", "taxonomy_review_status"):
            input_field = "representative_name_ko" if field == "exercise_name_ko" else field
            if row[field] != source[input_field]:
                raise ValueError(
                    f"taxonomy value changed in safety: {row['representative_id']} {field}"
                )

    return {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "representative_count": len(taxonomy),
        "content_count": len(content_rows),
        "safety_count": len(safety_rows),
        "review_log_count": len(log_rows),
        "exact_content_code_present": sum(
            row["content_description_required_present"] == "true" for row in log_rows
        ),
        "exact_safety_code_present": sum(
            row["safety_rule_required_present"] == "true" for row in log_rows
        ),
        "safety_rows_needing_domain_review": sum(
            row["safety_review_status"] != "DOMAIN_APPROVED" for row in safety_rows
        ),
        "insufficient_taxonomy_evidence_rows": sum(
            row["generation_basis_code"] == "INSUFFICIENT_TAXONOMY_EVIDENCE" for row in safety_rows
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = build(args.input, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
