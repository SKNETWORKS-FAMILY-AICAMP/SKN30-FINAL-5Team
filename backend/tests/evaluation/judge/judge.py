"""PHASE 5: run the judge, and let no score overrule a safety failure.

The ordering here is the whole point.  `judge_run` scores a plan only after the
deterministic evaluators have passed it; if they did not, the verdict is FAIL and
the judge is not called at all -- so a safety violation cannot be bought back by
a high rating, and the run costs nothing.

The payload handed to the judge is built from the same privacy allowlist the
service uses for its own agents (`llm_agents/payload.py`), so the judge sees the
identifier-free machine projection and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.integrations.llm_agents.payload import assert_private_machine_payload
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.evaluators.findings import CaseEvaluation
from backend.tests.evaluation.judge.rubric import (
    JUDGE_OUTPUT_SCHEMA_VERSION,
    JUDGE_PROMPT_VERSION,
    JUDGE_RUBRIC_VERSION,
    MAX_SCORE,
    MIN_SCORE,
    SYSTEM_INSTRUCTION,
    JudgeCriterion,
    rubric_text,
)
from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

JUDGE_SKIPPED_REASON_SAFETY: Final = "DETERMINISTIC_FAILURE_PRECEDES_JUDGEMENT"
JUDGE_SKIPPED_REASON_NO_PLAN: Final = "NO_PLAN_TO_JUDGE"


class JudgeVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_JUDGED = "NOT_JUDGED"


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    criterion: JudgeCriterion
    score: int = Field(ge=MIN_SCORE, le=MAX_SCORE)
    rationale: str = Field(min_length=1, max_length=400)


class JudgeOutput(BaseModel):
    """What the judge model is asked to return, and nothing else."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str = JUDGE_OUTPUT_SCHEMA_VERSION
    scores: tuple[CriterionScore, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_output(self) -> Self:
        criteria = tuple(item.criterion for item in self.scores)
        if len(set(criteria)) != len(criteria):
            raise ValueError("each criterion must be scored exactly once")
        if set(criteria) != set(JudgeCriterion):
            raise ValueError("every rubric criterion must be scored")
        return self

    def score_for(self, criterion: JudgeCriterion) -> int:
        return next(item.score for item in self.scores if item.criterion is criterion)

    @property
    def mean_score(self) -> float:
        return round(sum(item.score for item in self.scores) / len(self.scores), 4)


class JudgeModel(Protocol):
    """Any callable that turns a judge request into a structured verdict."""

    def score(self, *, system: str, payload: dict[str, Any]) -> JudgeOutput: ...

    @property
    def model_label(self) -> str: ...


@dataclass(frozen=True, slots=True)
class JudgeResult:
    case_id: str
    category: str
    verdict: JudgeVerdict
    deterministic_passed: bool
    output: JudgeOutput | None
    skipped_reason: str | None
    model_label: str
    rubric_version: str = JUDGE_RUBRIC_VERSION
    prompt_version: str = JUDGE_PROMPT_VERSION

    @property
    def mean_score(self) -> float | None:
        return self.output.mean_score if self.output is not None else None

    def to_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "verdict": self.verdict.value,
            "deterministic_passed": self.deterministic_passed,
            "skipped_reason": self.skipped_reason,
            "model_label": self.model_label,
            "rubric_version": self.rubric_version,
            "prompt_version": self.prompt_version,
            "mean_score": self.mean_score,
            "scores": (
                {item.criterion.value: item.score for item in self.output.scores}
                if self.output is not None
                else None
            ),
            "rationales": (
                {item.criterion.value: item.rationale for item in self.output.scores}
                if self.output is not None
                else None
            ),
        }


def build_judge_payload(run: CaseRunResult, *, blind: bool = False) -> dict[str, Any]:
    """Project one run into the identifier-free body the judge is shown.

    `blind` drops `advisory_codes`, which is the one field that tells a judge
    which architecture produced the plan: only a multi-agent run has separate
    specialists to advise, so its presence or absence identifies the source.
    PHASE 6 scores every architecture blind, so the judge is comparing plans
    rather than recognising pipelines. The cost is that blind scores are not
    comparable with the PHASE 5 numbers, which were taken unblinded.
    """

    envelope = run.scenario.constraint_envelope
    plan = run.compiled_plan
    if plan is None:
        raise ValueError("a run without a compiled plan cannot be judged")

    payload: dict[str, Any] = {
        "schema_version": JUDGE_OUTPUT_SCHEMA_VERSION,
        "user_context": {
            "primary_goal_code": envelope.primary_goal_code,
            "requested_duration_minutes": envelope.requested_duration_minutes,
            "allowed_location_codes": list(envelope.allowed_location_codes),
            "excluded_exercise_count": len(envelope.excluded_exercise_ids),
            "recovery_ceiling": {
                "allowed_intensity_codes": list(envelope.recovery_ceiling.allowed_intensity_codes),
                "maximum_sets_per_exercise": envelope.recovery_ceiling.maximum_sets_per_exercise,
                "maximum_repetitions_per_set": (
                    envelope.recovery_ceiling.maximum_repetitions_per_set
                ),
                "minimum_rest_seconds_between_sets": (
                    envelope.recovery_ceiling.minimum_rest_seconds_between_sets
                ),
            },
        },
        "plan": {
            "action_code": plan.action_code.value,
            "estimated_duration_seconds": plan.estimated_duration_seconds,
            "exercises": [
                {
                    "sequence": item.prescription.sequence,
                    "phase_code": item.prescription.phase_code,
                    "stable_code": item.catalog_record.stable_code,
                    "body_focus_code": item.catalog_record.body_focus_code,
                    "role_eligibility_code": item.catalog_record.role_eligibility_code,
                    "sets": item.prescription.sets,
                    "repetitions_per_set": item.prescription.repetitions_per_set,
                    "rest_seconds_between_sets": item.prescription.rest_seconds_between_sets,
                    "intensity_code": item.prescription.intensity_code,
                    "location_code": item.prescription.location_code,
                }
                for item in plan.exercises
            ],
        },
        "decision_codes": list(run.plan_spec.decision_codes) if run.plan_spec else [],
        "used_deterministic_fallback": run.used_fallback,
    }
    if not blind:
        payload["advisory_codes"] = sorted(
            {
                code
                for proposal in run.graph_result.round_one_proposals
                for code in proposal.adjustment_codes
            }
        )
    # The same guard the service applies to its own agent payloads. A judge is
    # still an external model, so it gets no wider a view than an agent does.
    # `body_focus_code` is the movement's reviewed catalog attribute, not a body
    # area the user reported, and `project_exercise_pool` exempts it for exactly
    # that reason. The synthetic catalog happened to use codes that never
    # collided with `BodyAreaCode`; the deployed one uses CHEST and NECK, so
    # without the same exemption every judge call on a real plan is refused.
    assert_private_machine_payload(payload, body_area_exempt_fields=("body_focus_code",))
    return payload


def judge_request_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "prompt_version": JUDGE_PROMPT_VERSION,
            "rubric_version": JUDGE_RUBRIC_VERSION,
            "output_schema_version": JUDGE_OUTPUT_SCHEMA_VERSION,
            "rubric": rubric_text(),
            "input": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def judge_run(
    run: CaseRunResult,
    model: JudgeModel,
    *,
    evaluation: CaseEvaluation | None = None,
    blind: bool = False,
) -> JudgeResult:
    """Score one run, but only once the deterministic gates have passed it.

    A safety violation is a FAIL whatever a judge would have said, and the judge
    is never asked -- there is no score to weigh against the violation, and no
    reason to spend a call producing one.
    """

    resolved = evaluation or evaluate_case(run)
    if not resolved.passed:
        return JudgeResult(
            case_id=run.case.case_id,
            category=run.case.category.value,
            verdict=JudgeVerdict.FAIL,
            deterministic_passed=False,
            output=None,
            skipped_reason=JUDGE_SKIPPED_REASON_SAFETY,
            model_label=model.model_label,
        )
    if run.compiled_plan is None:
        return JudgeResult(
            case_id=run.case.case_id,
            category=run.case.category.value,
            verdict=JudgeVerdict.NOT_JUDGED,
            deterministic_passed=True,
            output=None,
            skipped_reason=JUDGE_SKIPPED_REASON_NO_PLAN,
            model_label=model.model_label,
        )

    payload = build_judge_payload(run, blind=blind)
    output = model.score(system=SYSTEM_INSTRUCTION, payload=payload)
    return JudgeResult(
        case_id=run.case.case_id,
        category=run.case.category.value,
        verdict=JudgeVerdict.PASS,
        deterministic_passed=True,
        output=output,
        skipped_reason=None,
        model_label=model.model_label,
    )


__all__ = [
    "JUDGE_SKIPPED_REASON_NO_PLAN",
    "JUDGE_SKIPPED_REASON_SAFETY",
    "CriterionScore",
    "JudgeModel",
    "JudgeOutput",
    "JudgeResult",
    "JudgeVerdict",
    "build_judge_payload",
    "judge_request_text",
    "judge_run",
]
