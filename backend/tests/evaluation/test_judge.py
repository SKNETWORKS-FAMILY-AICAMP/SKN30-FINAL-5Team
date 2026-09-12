"""PHASE 5: judge plumbing, and the rule that a score cannot overrule safety.

These tests use mock judges. That is not a shortcut around the real one -- the
properties worth testing here are ordering, payload privacy, schema strictness
and reproducibility, and none of them are properties of any particular model.
Scoring with the real judge costs money and is run separately, by
`report_judge_cli`, once a key and a budget are approved.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.evaluators import evaluate_case
from backend.tests.evaluation.harness import EXCLUSION_CASES, GRAPH_CASES, run_case
from backend.tests.evaluation.judge.judge import (
    JUDGE_SKIPPED_REASON_NO_PLAN,
    JUDGE_SKIPPED_REASON_SAFETY,
    CriterionScore,
    JudgeOutput,
    JudgeVerdict,
    build_judge_payload,
    judge_request_text,
    judge_run,
)
from backend.tests.evaluation.judge.mock_judge import ConstantMockJudge, StructuralMockJudge
from backend.tests.evaluation.judge.rubric import (
    JUDGE_PROMPT_VERSION,
    JUDGE_RUBRIC_VERSION,
    MAX_SCORE,
    JudgeCriterion,
    rubric_text,
)
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode

PLANNING_CASES = tuple(
    case for case in GRAPH_CASES if case.expected_constraints.plan_generation_allowed
)


def _ids(case: EvaluationCase) -> str:
    return case.case_id


# --------------------------------------------------------------------------
# Rubric and output contract
# --------------------------------------------------------------------------


def test_the_rubric_covers_every_required_criterion() -> None:
    """The master specification names six criteria; the rubric must define all six."""

    text = rubric_text()
    for criterion in JudgeCriterion:
        assert criterion.value in text
    assert len(list(JudgeCriterion)) == 6


def test_the_rubric_anchors_are_all_present() -> None:
    """A judge without anchors scores on vibes and cannot be reproduced."""

    text = rubric_text()
    assert text.count("5점:") == 6
    assert text.count("3점:") == 6
    assert text.count("1점:") == 6


def test_judge_output_requires_every_criterion_exactly_once() -> None:
    partial = tuple(
        CriterionScore(criterion=criterion, score=4, rationale="x")
        for criterion in list(JudgeCriterion)[:5]
    )
    with pytest.raises(ValidationError):
        JudgeOutput(scores=partial)


def test_judge_output_rejects_a_duplicated_criterion() -> None:
    duplicated = tuple(
        CriterionScore(criterion=JudgeCriterion.PERSONALIZATION, score=4, rationale="x")
        for _ in range(6)
    )
    with pytest.raises(ValidationError):
        JudgeOutput(scores=duplicated)


@pytest.mark.parametrize("score", [0, 6, -1])
def test_judge_output_rejects_an_out_of_range_score(score: int) -> None:
    with pytest.raises(ValidationError):
        CriterionScore(criterion=JudgeCriterion.FEASIBILITY, score=score, rationale="x")


# --------------------------------------------------------------------------
# The ordering rule: safety first, judgement second
# --------------------------------------------------------------------------


def test_a_safety_failure_fails_the_case_even_with_a_perfect_judge() -> None:
    """The rule the master specification is most explicit about.

    A judge that awards 5 on every criterion still cannot turn a deterministic
    failure into a pass, and is never even asked.
    """

    run = run_case(GRAPH_CASES[0])
    evaluation = evaluate_case(run)

    # Force a deterministic failure without touching the service: report the
    # evaluation as failed and confirm the judge is bypassed entirely.
    failed = evaluation.__class__(
        **{
            **{
                field: getattr(evaluation, field)
                for field in evaluation.__dataclass_fields__
                if field != "findings"
            },
            "findings": (
                *evaluation.findings,
                _critical_finding(),
            ),
        }
    )
    assert not failed.passed

    result = judge_run(run, ConstantMockJudge(fixed_score=MAX_SCORE), evaluation=failed)
    assert result.verdict is JudgeVerdict.FAIL
    assert result.output is None
    assert result.skipped_reason == JUDGE_SKIPPED_REASON_SAFETY
    assert result.mean_score is None


def _critical_finding():  # type: ignore[no-untyped-def]
    from backend.tests.evaluation.evaluators.findings import DefectClass, Finding, Severity

    return Finding(
        check_code="SAFETY_EXCLUDED_EXERCISE_IN_FINAL_PLAN",
        severity=Severity.CRITICAL,
        expected="no excluded exercise",
        observed="one excluded exercise",
        defect_class=DefectClass.SERVICE,
    )


def test_a_run_without_a_plan_is_not_judged() -> None:
    """There is nothing to rate, so no call is made and no score is invented."""

    case = EXCLUSION_CASES[0]
    run = run_case(
        case,
        Script(
            training=ScriptCode.PROVIDER_EXCEPTION,
            recovery=ScriptCode.PROVIDER_EXCEPTION,
            feasibility=ScriptCode.PROVIDER_EXCEPTION,
            coordinator=ScriptCode.PROVIDER_EXCEPTION,
        ),
    )
    if run.has_plan:
        pytest.skip("the deterministic fallback answered this case")
    result = judge_run(run, ConstantMockJudge())
    assert result.verdict is JudgeVerdict.NOT_JUDGED
    assert result.skipped_reason == JUDGE_SKIPPED_REASON_NO_PLAN
    assert result.output is None


# --------------------------------------------------------------------------
# Payload privacy and reproducibility
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", PLANNING_CASES, ids=_ids)
def test_the_judge_payload_passes_the_service_privacy_guard(case: EvaluationCase) -> None:
    """A judge is an external model and gets no wider a view than an agent does."""

    run = run_case(case)
    if run.compiled_plan is None:
        pytest.skip("no plan to judge")
    payload = build_judge_payload(run)  # raises if the guard rejects it
    body = str(payload)
    for forbidden in ("birth", "email", "user_id", "name_ko"):
        assert forbidden not in body


def test_the_judge_request_is_byte_stable_for_one_run() -> None:
    """Same run, same request bytes: a stored score stays reproducible."""

    run = run_case(GRAPH_CASES[0])
    first = judge_request_text(build_judge_payload(run))
    second = judge_request_text(build_judge_payload(run))
    assert first == second
    assert JUDGE_PROMPT_VERSION in first
    assert JUDGE_RUBRIC_VERSION in first


def test_the_request_carries_the_rubric_the_score_was_produced_under() -> None:
    run = run_case(GRAPH_CASES[0])
    text = judge_request_text(build_judge_payload(run))
    for criterion in JudgeCriterion:
        assert criterion.value in text


def test_a_result_records_the_versions_needed_to_replay_it() -> None:
    run = run_case(GRAPH_CASES[0])
    result = judge_run(run, StructuralMockJudge())
    body = result.to_json()
    assert body["rubric_version"] == JUDGE_RUBRIC_VERSION
    assert body["prompt_version"] == JUDGE_PROMPT_VERSION
    assert body["model_label"] == "mock-structural-judge-v1"


# --------------------------------------------------------------------------
# Scoring pipeline
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", PLANNING_CASES, ids=_ids)
def test_every_passing_case_receives_six_scores(case: EvaluationCase) -> None:
    run = run_case(case)
    if run.compiled_plan is None:
        pytest.skip("no plan to judge")
    result = judge_run(run, StructuralMockJudge())
    assert result.verdict is JudgeVerdict.PASS
    assert result.output is not None
    assert len(result.output.scores) == 6
    assert 1.0 <= result.output.mean_score <= 5.0


def test_the_mock_judge_is_reproducible() -> None:
    run = run_case(GRAPH_CASES[0])
    first = judge_run(run, StructuralMockJudge())
    second = judge_run(run, StructuralMockJudge())
    assert first.to_json() == second.to_json()
