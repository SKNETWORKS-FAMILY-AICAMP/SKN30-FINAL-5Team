"""Deterministic, non-medical public names for compiled workout plans."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

PLAN_NAMING_RULE_VERSION: Final = "1.0.0"

_FOCUS_LABELS: Final = {
    "UPPER_BODY": "상체",
    "LOWER_BODY": "하체",
    "CHEST": "가슴",
    "BACK": "등",
    "SHOULDERS": "어깨",
    "BICEPS": "이두근",
    "TRICEPS": "삼두근",
    "FOREARMS": "전완",
    "GLUTES": "둔근",
    "QUADRICEPS": "대퇴사두근",
    "HAMSTRINGS": "햄스트링",
    "CALVES": "종아리",
    "ADDUCTORS": "내전근",
    "CORE": "코어",
    "FULL_BODY": "전신",
    "CARDIO": "유산소",
    "MOBILITY": "가동성",
}
_PATTERN_LABELS: Final = {
    "VERTICAL_PULL": "수직 당기기",
    "HORIZONTAL_PULL": "수평 당기기",
    "HORIZONTAL_PUSH": "수평 밀기",
    "VERTICAL_PUSH": "수직 밀기",
    "KNEE_DOMINANT": "무릎 중심 하체",
    "HIP_DOMINANT": "엉덩관절 중심 하체",
    "KNEE_FLEXION": "무릎 굽힘",
    "ISOLATION": "보조",
    "GAIT": "걷기",
    "CORE_BRACE": "코어",
    "MOBILITY_STRETCH": "가동성",
}
_TRAINING_LABELS: Final = {"STRENGTH": "근력", "CARDIO": "유산소", "MOBILITY": "가동성"}
_DOWNSHIFT_ACTIONS: Final = frozenset({"CHANGE", "DOWNSHIFT", "RECOVERY"})


@dataclass(frozen=True, slots=True)
class PlanName:
    value: str
    reason_codes: tuple[str, ...]
    rule_version: str = PLAN_NAMING_RULE_VERSION


def _dominant(values: Iterable[str]) -> str | None:
    counts = Counter(value for value in values if value)
    if not counts:
        return None
    return min(counts, key=lambda value: (-counts[value], value))


def build_plan_name(
    *,
    action_code: str,
    main_body_focus_codes: Iterable[str],
    main_movement_pattern_codes: Iterable[str],
    main_training_type_codes: Iterable[str],
) -> PlanName:
    """Name a plan from its MAIN composition, never from an LLM or a diagnosis."""

    focus_code = _dominant(main_body_focus_codes)
    pattern_code = _dominant(main_movement_pattern_codes)
    training_code = _dominant(main_training_type_codes)
    focus_label = _FOCUS_LABELS.get(focus_code or "")
    pattern_label = _PATTERN_LABELS.get(pattern_code or "")
    training_label = _TRAINING_LABELS.get(training_code or "")
    basis_label = focus_label or pattern_label or training_label
    reason_codes: list[str] = []
    if focus_code:
        reason_codes.append(f"DOMINANT_FOCUS_{focus_code}")
    if pattern_code:
        reason_codes.append(f"DOMINANT_PATTERN_{pattern_code}")
    if training_code:
        reason_codes.append(f"DOMINANT_TRAINING_{training_code}")

    if action_code in _DOWNSHIFT_ACTIONS:
        reason_codes.append("LOAD_ADJUSTED")
        return PlanName(
            value=f"{basis_label or '오늘의'} 컨디션 조절 루틴",
            reason_codes=tuple(reason_codes) or ("FALLBACK",),
        )
    if basis_label is None:
        return PlanName(value="오늘의 운동 루틴", reason_codes=("FALLBACK",))
    if focus_label is not None and training_label is not None and focus_label != training_label:
        return PlanName(
            value=f"{focus_label} {training_label} 루틴", reason_codes=tuple(reason_codes)
        )
    return PlanName(value=f"{basis_label} 루틴", reason_codes=tuple(reason_codes))


__all__ = ["PLAN_NAMING_RULE_VERSION", "PlanName", "build_plan_name"]
