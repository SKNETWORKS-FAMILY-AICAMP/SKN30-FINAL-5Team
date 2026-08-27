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
    "experience_level_code",
    "fitt_template_id",
    "template_name",
    "movement_pattern",
    "training_category",
    "prescription_unit",
    "default_sets",
    "min_sets",
    "max_sets",
    "default_reps",
    "min_reps",
    "max_reps",
    "default_work_seconds",
    "min_work_seconds",
    "max_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "default_intensity",
    "fitt_basis",
]

COMPOUND_BASIS = (
    "운동 전공 검수 반영 기본값. 초급은 2–3세트·8–12회 범위에서 기본 2세트·10회, "
    "중급은 2–3세트·8–12회 범위에서 기본 3세트·10회를 사용한다. 개인별 부하·진행은 Agent가 결정."
)
ISOLATION_BASIS = (
    "운동 전공 검수 반영 고립 기본값. 장비가 아니라 운동 특성으로 구분하며, "
    "초급은 2세트·10–15회에서 기본 12회, 중급은 2–3세트·10–15회에서 기본 3세트·12회를 사용한다."
)
CORE_BASIS = (
    "운동 전공 검수 반영 코어 기본값. 동적 코어는 횟수형, 정적 코어는 시간형으로 분리하며 "
    "통증·재활 처방이 아님; 개인별 자세·진행은 Agent가 조정."
)
MOBILITY_BASIS = (
    "운동 전공 검수 반영 가동성 기본값. 초급·중급 모두 2회·15–30초이며, ROM과 상태에 따라 "
    "필요시 반복 횟수나 총 시간을 조정한다. 치료 또는 재활 처방이 아님."
)
CARDIO_BASIS = (
    "운동 전공 검수 반영 중강도 유산소 기본값. 초급 20–30분, 중급 30–45분이며 실제 처방은 "
    "강도와 주당 총량을 함께 보고 결정한다."
)

TEMPLATES = [
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-COMPOUND-SQUAT-V1",
        "template_name": "Compound Strength — Squat",
        "movement_pattern": "SQUAT",
        "training_category": "COMPOUND_STRENGTH",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "3",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "min_work_seconds": "", "max_work_seconds": "",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-COMPOUND-HINGE-V1",
        "template_name": "Compound Strength — Hinge",
        "movement_pattern": "HINGE",
        "training_category": "COMPOUND_STRENGTH",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "3",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "min_work_seconds": "", "max_work_seconds": "",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-COMPOUND-PUSH-V1",
        "template_name": "Compound Strength — Push",
        "movement_pattern": "PUSH",
        "training_category": "COMPOUND_STRENGTH",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "3",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "min_work_seconds": "", "max_work_seconds": "",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-COMPOUND-PULL-V1",
        "template_name": "Compound Strength — Pull",
        "movement_pattern": "PULL",
        "training_category": "COMPOUND_STRENGTH",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "3",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "min_work_seconds": "", "max_work_seconds": "",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-COMPOUND-LUNGE-V1",
        "template_name": "Compound Strength — Lunge",
        "movement_pattern": "LUNGE",
        "training_category": "COMPOUND_STRENGTH",
        "prescription_unit": "REPS_PER_SIDE",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "min_work_seconds": "", "max_work_seconds": "",
        "default_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": COMPOUND_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-ISOLATION-STRENGTH-V1",
        "template_name": "Isolation Strength",
        "movement_pattern": "ANY",
        "training_category": "ISOLATION_STRENGTH",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "12", "min_reps": "10", "max_reps": "15",
        "min_work_seconds": "", "max_work_seconds": "",
        "default_work_seconds": "",
        "default_rest_seconds": "60-90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": ISOLATION_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-ISOMETRIC-STRENGTH-V1",
        "template_name": "Isometric Strength",
        "movement_pattern": "ANY",
        "training_category": "ISOMETRIC_STRENGTH",
        "prescription_unit": "SECONDS",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "", "min_reps": "", "max_reps": "",
        "default_work_seconds": "5", "min_work_seconds": "5", "max_work_seconds": "10",
        "default_rest_seconds": "60",
        "default_transition_seconds": "",
        "default_intensity": "LIGHT_MODERATE",
        "fitt_basis": "전문가 검수 완료. 벽을 미는 등척성 광배근 활성화 운동에 5–10초 유지시간 범위를 적용한다.",
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-HINGE-POWER-V1",
        "template_name": "Hinge Power",
        "movement_pattern": "HINGE",
        "training_category": "POWER",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "3",
        "default_reps": "8", "min_reps": "6", "max_reps": "10",
        "default_work_seconds": "", "min_work_seconds": "", "max_work_seconds": "",
        "default_rest_seconds": "90",
        "default_transition_seconds": "",
        "default_intensity": "MODERATE",
        "fitt_basis": "전문가 검수 완료. 케틀벨 스윙은 일반 HINGE와 분리한 ballistic/power 동작이며, 빠른 concentric 수행과 보수적 반복 범위를 적용한다. 개별 부하·속도·기술은 Agent가 결정한다.",
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-CORE-DYNAMIC-V1",
        "template_name": "Core Dynamic",
        "movement_pattern": "CORE",
        "training_category": "CORE_DYNAMIC",
        "prescription_unit": "REPS",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "default_work_seconds": "", "min_work_seconds": "", "max_work_seconds": "",
        "default_rest_seconds": "45-60",
        "default_transition_seconds": "",
        "default_intensity": "LIGHT_MODERATE",
        "fitt_basis": CORE_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-CORE-DYNAMIC-PER-SIDE-V1",
        "template_name": "Core Dynamic — Per Side",
        "movement_pattern": "CORE",
        "training_category": "CORE_DYNAMIC",
        "prescription_unit": "REPS_PER_SIDE",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "10", "min_reps": "8", "max_reps": "12",
        "default_work_seconds": "", "min_work_seconds": "", "max_work_seconds": "",
        "default_rest_seconds": "45-60",
        "default_transition_seconds": "",
        "default_intensity": "LIGHT_MODERATE",
        "fitt_basis": CORE_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-CORE-ISOMETRIC-V1",
        "template_name": "Core Isometric",
        "movement_pattern": "CORE",
        "training_category": "CORE_ISOMETRIC",
        "prescription_unit": "SECONDS",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "", "min_reps": "", "max_reps": "",
        "default_work_seconds": "25", "min_work_seconds": "20", "max_work_seconds": "30",
        "default_rest_seconds": "45-60",
        "default_transition_seconds": "",
        "default_intensity": "LIGHT_MODERATE",
        "fitt_basis": CORE_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-MOBILITY-V1",
        "template_name": "Mobility",
        "movement_pattern": "MOBILITY",
        "training_category": "MOBILITY",
        "prescription_unit": "SECONDS",
        "default_sets": "2", "min_sets": "2", "max_sets": "2",
        "default_reps": "",
        "min_reps": "", "max_reps": "",
        "default_work_seconds": "15", "min_work_seconds": "15", "max_work_seconds": "30",
        "default_rest_seconds": "",
        "default_transition_seconds": "15-30",
        "default_intensity": "LIGHT",
        "fitt_basis": MOBILITY_BASIS,
    },
    {
        "experience_level_code": "BEGINNER",
        "fitt_template_id": "FITT-CARDIO-V1",
        "template_name": "Cardio",
        "movement_pattern": "CARDIO",
        "training_category": "CARDIO",
        "prescription_unit": "SECONDS",
        "default_sets": "",
        "default_reps": "",
        "default_work_seconds": "1200", "min_work_seconds": "1200", "max_work_seconds": "1800",
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
