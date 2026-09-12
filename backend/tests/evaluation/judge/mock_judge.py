"""A deterministic stand-in judge, for wiring and for judge-independence tests.

It does not attempt to imitate judgement.  It derives a stable score from the
plan's own structure so the pipeline can be exercised, compared and replayed at
no cost -- and so a test can prove that a safety failure outranks *any* score,
including a perfect one, by handing the pipeline a judge that always answers 5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.tests.evaluation.judge.judge import CriterionScore, JudgeOutput
from backend.tests.evaluation.judge.rubric import MAX_SCORE, MIN_SCORE, JudgeCriterion


def _clamp(value: int) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, value))


@dataclass(frozen=True, slots=True)
class ConstantMockJudge:
    """Always returns the same score. Used to prove a score cannot buy a pass.

    The field is `fixed_score` rather than `score` so it does not collide with
    the `score()` method the `JudgeModel` protocol requires.
    """

    fixed_score: int = MAX_SCORE
    model_label: str = "mock-constant-judge-v1"

    def score(self, *, system: str, payload: dict[str, Any]) -> JudgeOutput:
        del system, payload
        value = _clamp(self.fixed_score)
        return JudgeOutput(
            scores=tuple(
                CriterionScore(
                    criterion=criterion,
                    score=value,
                    rationale="고정 점수 모의 심사자",
                )
                for criterion in JudgeCriterion
            )
        )


@dataclass(frozen=True, slots=True)
class StructuralMockJudge:
    """Derive a reproducible score from properties a rule can already see.

    Deliberately crude: it exists to move the pipeline, not to stand in for the
    real judge's opinion. Any report built on it must say so.
    """

    model_label: str = "mock-structural-judge-v1"

    def score(self, *, system: str, payload: dict[str, Any]) -> JudgeOutput:
        del system
        plan = payload["plan"]
        exercises = plan["exercises"]
        context = payload["user_context"]

        phases = {item["phase_code"] for item in exercises}
        distinct = {item["stable_code"] for item in exercises}
        target_seconds = int(context["requested_duration_minutes"]) * 60
        drift = abs(int(plan["estimated_duration_seconds"]) - target_seconds)

        personalization = 5 if context["excluded_exercise_count"] == 0 else 4
        feasibility = 5 if drift <= 120 else (4 if drift <= 300 else 2)
        consistency = 5 if phases == {"WARMUP", "MAIN", "COOLDOWN"} else 2
        explanation = 5 if payload["decision_codes"] else 3
        groundedness = 5  # every exercise is pool-bound by construction
        overall = _clamp(
            round((personalization + feasibility + consistency + explanation + groundedness) / 5)
        )
        if len(distinct) < 3:
            overall = _clamp(overall - 1)

        values = {
            JudgeCriterion.PERSONALIZATION: personalization,
            JudgeCriterion.FEASIBILITY: feasibility,
            JudgeCriterion.CONSISTENCY: consistency,
            JudgeCriterion.EXPLANATION_QUALITY: explanation,
            JudgeCriterion.GROUNDEDNESS: groundedness,
            JudgeCriterion.OVERALL_QUALITY: overall,
        }
        return JudgeOutput(
            scores=tuple(
                CriterionScore(
                    criterion=criterion,
                    score=_clamp(score),
                    rationale="구조 기반 모의 채점",
                )
                for criterion, score in values.items()
            )
        )


__all__ = ["ConstantMockJudge", "StructuralMockJudge"]
