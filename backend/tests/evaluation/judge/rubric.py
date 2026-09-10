"""PHASE 5: the judge rubric, versioned so a score can be reproduced.

A judge is asked only about what a rule cannot settle.  Everything deterministic
-- exclusions, duration, pool membership, session shape, recovery ceilings -- is
already decided by PHASE 2 and is *not* re-litigated here.  The judge sees a plan
that has already passed those gates and rates how well it serves this user.

The rubric is stored rather than embedded in a prompt string so that the exact
wording behind any stored score can be recovered later, which is what makes the
PHASE 10 human calibration comparison meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

JUDGE_RUBRIC_VERSION: Final = "service-quality-judge-rubric-v1"
JUDGE_PROMPT_VERSION: Final = "service-quality-judge-prompt-v1"
JUDGE_OUTPUT_SCHEMA_VERSION: Final = "service-quality-judge-output-v1"

MIN_SCORE: Final = 1
MAX_SCORE: Final = 5


class JudgeCriterion(StrEnum):
    PERSONALIZATION = "PERSONALIZATION"
    FEASIBILITY = "FEASIBILITY"
    CONSISTENCY = "CONSISTENCY"
    EXPLANATION_QUALITY = "EXPLANATION_QUALITY"
    GROUNDEDNESS = "GROUNDEDNESS"
    OVERALL_QUALITY = "OVERALL_QUALITY"


@dataclass(frozen=True, slots=True)
class CriterionRubric:
    criterion: JudgeCriterion
    question: str
    score_5: str
    score_3: str
    score_1: str


RUBRIC: Final[tuple[CriterionRubric, ...]] = (
    CriterionRubric(
        criterion=JudgeCriterion.PERSONALIZATION,
        question="이 계획이 이 사용자의 조건을 실제로 반영하는가?",
        score_5=(
            "목표, 요청 시간, 컨디션, 불편 부위, 장소를 모두 반영했고 "
            "각 선택이 사용자 조건과 연결된다."
        ),
        score_3="대부분 반영했으나 일부 조건이 계획에 드러나지 않는다.",
        score_1="사용자 조건과 무관한 일반적인 계획이다.",
    ),
    CriterionRubric(
        criterion=JudgeCriterion.FEASIBILITY,
        question="초보자가 이 계획을 실제로 수행할 수 있는가?",
        score_5="난이도, 볼륨, 순서, 휴식이 모두 현실적이며 중간에 무리가 없다.",
        score_3="대체로 수행 가능하나 일부 구간이 과하거나 부자연스럽다.",
        score_1="제시된 조건에서 수행하기 어렵다.",
    ),
    CriterionRubric(
        criterion=JudgeCriterion.CONSISTENCY,
        question="계획 내부에 모순이 없는가?",
        score_5="준비-본운동-마무리 흐름과 강도 배분이 일관되고 서로 충돌하지 않는다.",
        score_3="대체로 일관되나 한두 지점이 어긋난다.",
        score_1="계획 안에서 서로 모순되는 선택이 있다.",
    ),
    CriterionRubric(
        criterion=JudgeCriterion.EXPLANATION_QUALITY,
        question="왜 이 계획인지가 근거 코드로 설명되는가?",
        score_5="결정 근거가 사용자 조건과 명확히 연결되며 진단·처방 표현이 없다.",
        score_3="근거가 있으나 일부 조정의 이유가 불충분하다.",
        score_1="근거가 없거나 계획과 어긋난다.",
    ),
    CriterionRubric(
        criterion=JudgeCriterion.GROUNDEDNESS,
        question="계획이 제공된 승인 후보 안에만 근거하는가?",
        score_5="모든 운동과 수치가 제공된 후보와 승인 범위 안에 있다.",
        score_3="대부분 근거하나 일부 수치의 출처가 불명확하다.",
        score_1="제공되지 않은 운동이나 수치를 지어냈다.",
    ),
    CriterionRubric(
        criterion=JudgeCriterion.OVERALL_QUALITY,
        question="전체적으로 이 사용자에게 좋은 추천인가?",
        score_5="이 조건의 사용자에게 그대로 제공할 수 있는 수준이다.",
        score_3="제공은 가능하나 개선 여지가 뚜렷하다.",
        score_1="이 사용자에게 제공해서는 안 되는 수준이다.",
    ),
)

SYSTEM_INSTRUCTION: Final = (
    "당신은 운동 추천 품질을 평가하는 심사자다. "
    "제공된 구조화 데이터만 사용하고 추가 정보를 가정하지 마라. "
    "안전성은 이미 결정적 규칙이 판정했으므로 다시 판정하지 마라. "
    "의학적 진단이나 처방 표현을 쓰지 마라. "
    "각 항목을 1~5 정수로만 평가하고, 근거는 짧은 한국어 문장 하나로 쓴다. "
    "요청된 스키마 외의 내용을 반환하지 마라."
)


def rubric_text() -> str:
    """Render the rubric the judge is shown, in a stable order."""

    lines: list[str] = []
    for item in RUBRIC:
        lines.append(f"[{item.criterion.value}] {item.question}")
        lines.append(f"  5점: {item.score_5}")
        lines.append(f"  3점: {item.score_3}")
        lines.append(f"  1점: {item.score_1}")
    return "\n".join(lines)


__all__ = [
    "JUDGE_OUTPUT_SCHEMA_VERSION",
    "JUDGE_PROMPT_VERSION",
    "JUDGE_RUBRIC_VERSION",
    "MAX_SCORE",
    "MIN_SCORE",
    "RUBRIC",
    "SYSTEM_INSTRUCTION",
    "CriterionRubric",
    "JudgeCriterion",
    "rubric_text",
]
