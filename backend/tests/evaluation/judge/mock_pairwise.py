"""Deterministic pairwise stand-ins, for wiring and for bias-detection tests.

Neither imitates judgement. They exist so the aggregation can be exercised at no
cost, and -- more usefully -- so a test can prove the harness actually *detects*
position bias rather than assuming it would: `AlwaysFirstPairwiseJudge` always
picks whatever it read first, which is exactly the failure pairwise judging is
supposed to expose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.tests.evaluation.judge.pairwise import (
    CriterionPreference,
    PairwiseChoice,
    PairwiseVerdict,
)
from backend.tests.evaluation.judge.rubric import JudgeCriterion


def _verdict(choice: PairwiseChoice, rationale: str) -> PairwiseVerdict:
    return PairwiseVerdict(
        criterion_preferences=tuple(
            CriterionPreference(criterion=criterion, choice=choice) for criterion in JudgeCriterion
        ),
        overall_choice=choice,
        rationale=rationale,
    )


@dataclass(frozen=True, slots=True)
class AlwaysFirstPairwiseJudge:
    """Always prefers the plan in slot one. A pure position-bias generator."""

    model_label: str = "mock-always-first-pairwise-v1"

    def compare(self, *, system: str, payload: dict[str, Any]) -> PairwiseVerdict:
        del system, payload
        return _verdict(PairwiseChoice.PLAN_ONE, "항상 첫 번째를 고르는 모의 심사자")


@dataclass(frozen=True, slots=True)
class LongerPlanPairwiseJudge:
    """Prefers the plan with more exercise blocks; ties when they match.

    Content-driven and order-independent, so the same architecture wins in both
    presentations. That makes it the counterpart to `AlwaysFirstPairwiseJudge`:
    one produces agreement, the other produces bias.
    """

    model_label: str = "mock-longer-plan-pairwise-v1"

    def compare(self, *, system: str, payload: dict[str, Any]) -> PairwiseVerdict:
        del system
        one = len(payload["plan_one"]["plan"]["exercises"])
        two = len(payload["plan_two"]["plan"]["exercises"])
        if one == two:
            return _verdict(PairwiseChoice.TIE, "두 계획의 블록 수가 같다")
        choice = PairwiseChoice.PLAN_ONE if one > two else PairwiseChoice.PLAN_TWO
        return _verdict(choice, "블록 수가 더 많은 계획을 고른다")


__all__ = ["AlwaysFirstPairwiseJudge", "LongerPlanPairwiseJudge"]
