"""Build conservative, pattern-aware FITT catalog defaults.

This artifact is a DRAFT template library for the decision agent. It does not
assign FITT values directly to exercises and is not a clinical prescription.
"""

from __future__ import annotations

import csv
from pathlib import Path

PATTERN_REVIEW_PATH = Path("data/validation/review_results/movement_pattern_review.csv")
OUTPUT_PATH = Path("data/normalized/fitt_template_v1.csv")
REQUIRED_PATTERNS = {"SQUAT", "HINGE", "LUNGE", "PUSH", "PULL", "CORE", "MOBILITY", "CARDIO"}
FIELDNAMES = [
    "fitt_template_id",
    "template_name",
    "movement_pattern",
    "training_category",
    "default_sets",
    "default_reps",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "default_intensity",
    "fitt_basis",
]

COMPOUND_BASIS = (
    "작업 요청의 보수적 카탈로그 기본값. ACSM 2009 Position Stand의 초보자 8–12 RM 및 "
    "초보·중급 저항운동 1–2분 휴식 원칙, NSCA의 다관절 운동 우선 원칙을 반영; "
    "개인별 부하·진행은 Agent가 결정."
)
ISOLATION_BASIS = (
    "작업 요청의 보수적 카탈로그 기본값. ACSM 2009 Position Stand의 초보자 8–12 RM과 "
    "보조운동 1–2분 휴식 원칙을 참고해 반복 수를 10–15회, 휴식을 60–90초로 설정; "
    "단일관절 여부와 개인별 부하는 Agent가 확인."
)
BODYWEIGHT_BASIS = (
    "작업 요청의 초보자용 맨몸 기본값. 외부 부하를 전제하지 않으며, 반복 상한·난이도·휴식은 "
    "Agent가 수행 품질과 개인 상태에 따라 조정."
)
CORE_BASIS = (
    "작업 요청의 보수적 코어 안정화 기본값. 시간·휴식 범위는 일반 수행 템플릿이며 "
    "통증·재활 처방이 아님; 개인별 자세·진행은 Agent가 조정."
)
MOBILITY_BASIS = (
    "작업 요청의 보수적 가동성 기본값. 유지 시간과 전환 시간은 일반 준비·회복 목적의 "
    "카탈로그 값이며 치료 또는 재활 처방이 아님."
)
CARDIO_BASIS = (
    "작업 요청의 중강도 유산소 카탈로그 기본값(20–40분). ACSM 일반 성인 유산소 활동 지침의 "
    "중강도 활동 원칙을 참고하며, 세부 강도·시간은 Agent가 조정."
)

TEMPLATES = [
    {
        "fitt_template_id": "FITT-COMPOUND-SQUAT-V1",
        "template_name": "Compound Strength — Squat",
        "movement_pattern": "SQUAT",
        "training_category": "COMPOUND_STRENGTH",
        "default_sets": "3",
        "default_reps": "8-12",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "fitt_template_id": "FITT-COMPOUND-HINGE-V1",
        "template_name": "Compound Strength — Hinge",
        "movement_pattern": "HINGE",
        "training_category": "COMPOUND_STRENGTH",
        "default_sets": "3",
        "default_reps": "8-12",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "fitt_template_id": "FITT-COMPOUND-PUSH-V1",
        "template_name": "Compound Strength — Push",
        "movement_pattern": "PUSH",
        "training_category": "COMPOUND_STRENGTH",
        "default_sets": "3",
        "default_reps": "8-12",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "fitt_template_id": "FITT-COMPOUND-PULL-V1",
        "template_name": "Compound Strength — Pull",
        "movement_pattern": "PULL",
        "training_category": "COMPOUND_STRENGTH",
        "default_sets": "3",
        "default_reps": "8-12",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "fitt_template_id": "FITT-COMPOUND-LUNGE-V1",
        "template_name": "Compound Strength — Lunge",
        "movement_pattern": "LUNGE",
        "training_category": "COMPOUND_STRENGTH",
        "default_sets": "3",
        "default_reps": "8-12",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "fitt_template_id": "FITT-ISOLATION-STRENGTH-V1",
        "template_name": "Isolation Strength",
        "movement_pattern": "ANY",
        "training_category": "ISOLATION_STRENGTH",
        "default_sets": "3",
        "default_reps": "10-15",
        "default_work_seconds": "",
        "default_rest_seconds": "60-90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": ISOLATION_BASIS,
    },
    {
        "fitt_template_id": "FITT-BODYWEIGHT-BEGINNER-V1",
        "template_name": "Bodyweight Beginner",
        "movement_pattern": "ANY",
        "training_category": "BODYWEIGHT_BEGINNER",
        "default_sets": "2",
        "default_reps": "8-15",
        "default_work_seconds": "",
        "default_rest_seconds": "60",
        "default_transition_seconds": "",
        "default_intensity": "LIGHT_MODERATE",
        "fitt_basis": BODYWEIGHT_BASIS,
    },
    {
        "fitt_template_id": "FITT-CORE-STABILITY-V1",
        "template_name": "Core Stability",
        "movement_pattern": "CORE",
        "training_category": "CORE_STABILITY",
        "default_sets": "2-3",
        "default_reps": "",
        "default_work_seconds": "30-45",
        "default_rest_seconds": "45-60",
        "default_transition_seconds": "",
        "default_intensity": "LIGHT_MODERATE",
        "fitt_basis": CORE_BASIS,
    },
    {
        "fitt_template_id": "FITT-MOBILITY-V1",
        "template_name": "Mobility",
        "movement_pattern": "MOBILITY",
        "training_category": "MOBILITY",
        "default_sets": "",
        "default_reps": "",
        "default_work_seconds": "30-60",
        "default_rest_seconds": "",
        "default_transition_seconds": "15-30",
        "default_intensity": "LIGHT",
        "fitt_basis": MOBILITY_BASIS,
    },
    {
        "fitt_template_id": "FITT-CARDIO-V1",
        "template_name": "Cardio",
        "movement_pattern": "CARDIO",
        "training_category": "CARDIO",
        "default_sets": "",
        "default_reps": "",
        "default_work_seconds": "1200-2400",
        "default_rest_seconds": "",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": CARDIO_BASIS,
    },
]


def main() -> None:
    with PATTERN_REVIEW_PATH.open(encoding="utf-8", newline="") as review_file:
        pattern_rows = list(csv.DictReader(review_file))

    found_patterns = {row["suggested_movement_pattern"] for row in pattern_rows}
    if not REQUIRED_PATTERNS <= found_patterns:
        raise ValueError(
            "Movement-pattern review is incomplete: "
            f"missing={sorted(REQUIRED_PATTERNS - found_patterns)}"
        )

    template_ids = [template["fitt_template_id"] for template in TEMPLATES]
    if len(template_ids) != len(set(template_ids)):
        raise ValueError("FITT template IDs must be unique")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(TEMPLATES)


if __name__ == "__main__":
    main()
