"""Authored goal-tag and prescription review results for the merged catalog.

`docs/DATA_MODEL.md` 6.3.2는 `exercise_goal_tag_links`와
`exercise_prescription_profiles`를 명시적 검수 데이터로 요구하며 **운동 이름이나
training type에서 목표·처방을 추론하지 말라**고 못박는다. 그래서 아래 표는 규칙으로
생성한 값이 아니라 운동별로 직접 작성한 검수 결과다. 각 행은 개발 리드 위임 아래
도메인 검토자 역할로 작성했고 근거는
`validation/review_results/PRESCRIPTION_REVIEW_DECISION.md`에 있다.

이 모듈은 표를 CSV 검수 결과로 내보내는 역할만 한다. 게이트 검증은
`validate_exercise_prescription_review_results.py`, 산출물 생성은
`build_exercise_prescriptions.py`가 담당한다.

    python data/scripts/prescription_review_authoring.py write \
      --out ../validation/review_results/prescription_results.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

GOAL_CODE = "GENERAL_FITNESS"
EXPERIENCE_LEVEL_CODE = "BEGINNER"
PRESCRIPTION_VERSION = "1.0.0"
REVIEWER_REFERENCE = "AGENT-DOMAIN-REVIEW-PRESCRIPTION-V1"
EVIDENCE_REFERENCE = "validation/review_results/PRESCRIPTION_REVIEW_DECISION.md"
REVIEWED_AT = "2026-08-20T00:00:00+09:00"

RESULT_FIELDS = (
    "stable_code",
    "goal_code",
    "role_eligibility_code",
    "experience_level_code",
    "phase_code",
    "sets",
    "reps",
    "work_seconds_per_set",
    "rest_seconds_per_set",
    "intensity_code",
    "prescription_version",
    "reviewer_role_code",
    "reviewer_reference",
    "evidence_reference",
    "reviewed_at",
    "review_status_code",
)


@dataclass(frozen=True)
class Prescription:
    """One authored prescription row for a phase of one exercise."""

    phase_code: str
    sets: int
    reps: int | None
    work_seconds_per_set: int | None
    rest_seconds_per_set: int
    intensity_code: str


@dataclass(frozen=True)
class AuthoredExercise:
    stable_code: str
    role_eligibility_code: str
    prescriptions: tuple[Prescription, ...]


def _reps(phase: str, sets: int, reps: int, rest: int, intensity: str) -> Prescription:
    return Prescription(phase, sets, reps, None, rest, intensity)


def _seconds(phase: str, sets: int, work: int, rest: int, intensity: str) -> Prescription:
    return Prescription(phase, sets, None, work, rest, intensity)


# 가동성 4종은 준비운동과 마무리에 모두 쓴다. 헬스장 트랙의 준비·마무리 후보가
# 이 세 종목뿐이므로(seated_spinal_flexion_extension은 의자가 필요해 홈 전용)
# 준비운동 총합 60~180초와 마무리 총합 45~120초를 한 종목만으로도, 두 종목을
# 합쳐서도 만들 수 있게 값을 나눠 잡았다.
_MOBILITY: tuple[AuthoredExercise, ...] = (
    AuthoredExercise(
        "supine_chest_opening_stretch",
        "SUPPORT",
        (
            _seconds("WARMUP", 2, 30, 15, "LOW"),
            _seconds("COOLDOWN", 1, 45, 0, "LOW"),
        ),
    ),
    AuthoredExercise(
        "standing_side_stretch",
        "SUPPORT",
        (
            _seconds("WARMUP", 1, 60, 0, "LOW"),
            _seconds("COOLDOWN", 1, 30, 0, "LOW"),
        ),
    ),
    AuthoredExercise(
        "supine_ball_trunk_tilt",
        "SUPPORT",
        (
            _seconds("WARMUP", 2, 30, 15, "LOW"),
            _seconds("COOLDOWN", 1, 45, 0, "LOW"),
        ),
    ),
    AuthoredExercise(
        "seated_spinal_flexion_extension",
        "SUPPORT",
        (
            _seconds("WARMUP", 1, 60, 0, "LOW"),
            _seconds("COOLDOWN", 1, 30, 0, "LOW"),
        ),
    ),
)

# 본운동. CORE는 목표를 실제로 담는 다관절 동작에만 준다. 솔버가 CORE 없는 조합을
# 버리므로(`has_core`) 홈·헬스장 각 트랙에 CORE가 충분히 있어야 한다.
_MAIN: tuple[AuthoredExercise, ...] = (
    # --- 홈 트랙 ---
    AuthoredExercise("supported_sit_to_stand", "CORE", (_reps("MAIN", 3, 10, 45, "MODERATE"),)),
    AuthoredExercise("supine_hip_bridge", "CORE", (_reps("MAIN", 3, 12, 45, "MODERATE"),)),
    AuthoredExercise("quadruped_scapular_press", "CORE", (_reps("MAIN", 3, 10, 30, "MODERATE"),)),
    AuthoredExercise("standing_band_pulldown", "CORE", (_reps("MAIN", 3, 12, 45, "MODERATE"),)),
    AuthoredExercise(
        "supported_standing_hip_extension", "SUPPORT", (_reps("MAIN", 3, 12, 45, "LOW"),)
    ),
    AuthoredExercise("seated_leg_extension", "SUPPORT", (_reps("MAIN", 3, 12, 45, "LOW"),)),
    AuthoredExercise("quadruped_leg_raise", "SUPPORT", (_reps("MAIN", 3, 10, 45, "LOW"),)),
    AuthoredExercise("supine_leg_raise", "SUPPORT", (_reps("MAIN", 3, 10, 45, "MODERATE"),)),
    AuthoredExercise("supine_bicycle", "SUPPORT", (_seconds("MAIN", 3, 30, 45, "MODERATE"),)),
    AuthoredExercise("standing_calf_raise", "OPTIONAL", (_reps("MAIN", 3, 15, 45, "LOW"),)),
    AuthoredExercise("standing_lateral_raise", "OPTIONAL", (_reps("MAIN", 3, 12, 45, "LOW"),)),
    AuthoredExercise("diagonal_arm_raise", "OPTIONAL", (_reps("MAIN", 3, 12, 45, "LOW"),)),
    AuthoredExercise("household_biceps_curl", "OPTIONAL", (_reps("MAIN", 3, 12, 45, "LOW"),)),
    AuthoredExercise("band_leg_curl", "SUPPORT", (_reps("MAIN", 3, 12, 45, "LOW"),)),
    # --- 헬스장 트랙 ---
    AuthoredExercise("leg_press", "CORE", (_reps("MAIN", 3, 10, 90, "MODERATE"),)),
    AuthoredExercise("machine_seated_row", "CORE", (_reps("MAIN", 3, 10, 60, "MODERATE"),)),
    AuthoredExercise("seated_bench_press", "CORE", (_reps("MAIN", 3, 10, 75, "MODERATE"),)),
    AuthoredExercise("neutral_grip_lat_pulldown", "CORE", (_reps("MAIN", 3, 10, 60, "MODERATE"),)),
    AuthoredExercise("machine_shoulder_press", "SUPPORT", (_reps("MAIN", 3, 10, 60, "MODERATE"),)),
    AuthoredExercise("seated_cable_row", "SUPPORT", (_reps("MAIN", 3, 10, 60, "MODERATE"),)),
    AuthoredExercise(
        "standing_cable_chest_press", "SUPPORT", (_reps("MAIN", 3, 10, 60, "MODERATE"),)
    ),
    AuthoredExercise("leg_extension", "SUPPORT", (_reps("MAIN", 2, 12, 60, "LOW"),)),
    AuthoredExercise("leg_curl", "SUPPORT", (_reps("MAIN", 2, 12, 60, "LOW"),)),
    AuthoredExercise("machine_calf_press", "OPTIONAL", (_reps("MAIN", 2, 15, 60, "LOW"),)),
    AuthoredExercise("cable_triceps_pushdown", "OPTIONAL", (_reps("MAIN", 2, 12, 45, "LOW"),)),
    AuthoredExercise("supported_dumbbell_curl", "OPTIONAL", (_reps("MAIN", 2, 12, 45, "LOW"),)),
    # --- 걷기 (실외·트레드밀) ---
    AuthoredExercise("treadmill_walking", "CORE", (_seconds("MAIN", 1, 600, 0, "LOW"),)),
    AuthoredExercise("outdoor_walking", "CORE", (_seconds("MAIN", 1, 600, 0, "LOW"),)),
)

AUTHORED: tuple[AuthoredExercise, ...] = _MOBILITY + _MAIN


def rows() -> list[dict[str, object]]:
    written: list[dict[str, object]] = []
    for exercise in AUTHORED:
        for prescription in exercise.prescriptions:
            written.append(
                {
                    "stable_code": exercise.stable_code,
                    "goal_code": GOAL_CODE,
                    "role_eligibility_code": exercise.role_eligibility_code,
                    "experience_level_code": EXPERIENCE_LEVEL_CODE,
                    "phase_code": prescription.phase_code,
                    "sets": prescription.sets,
                    "reps": "" if prescription.reps is None else prescription.reps,
                    "work_seconds_per_set": (
                        ""
                        if prescription.work_seconds_per_set is None
                        else prescription.work_seconds_per_set
                    ),
                    "rest_seconds_per_set": prescription.rest_seconds_per_set,
                    "intensity_code": prescription.intensity_code,
                    "prescription_version": PRESCRIPTION_VERSION,
                    "reviewer_role_code": "DOMAIN_REVIEWER",
                    "reviewer_reference": REVIEWER_REFERENCE,
                    "evidence_reference": EVIDENCE_REFERENCE,
                    "reviewed_at": REVIEWED_AT,
                    "review_status_code": "DOMAIN_APPROVED",
                }
            )
    return written


def write_results(out: Path) -> int:
    written = rows()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RESULT_FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(written)
    return len(written)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write", help="write the authored review results CSV")
    write.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    count = write_results(args.out)
    print(f"wrote {count} prescription review rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
