"""PHASE 7: prove the bias detector works before trusting anything it reports.

A pairwise win rate is only evidence if the harness can tell a content-driven
preference from a positional one. These tests feed it a judge that is *purely*
positional and require it to be caught, then feed it a content-driven one and
require the win to survive. Without the first test, a clean-looking bias rate of
0.0 could simply mean the detector never fires.

Everything here is deterministic and costs nothing.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.tests.evaluation.architectures import (
    ARCHITECTURE_MULTI_AGENT,
    ARCHITECTURE_SINGLE_AGENT_RAG,
)
from backend.tests.evaluation.judge.mock_pairwise import (
    AlwaysFirstPairwiseJudge,
    LongerPlanPairwiseJudge,
)
from backend.tests.evaluation.judge.pairwise import (
    PairResult,
    PairwiseChoice,
    compare_pair,
    first_slot_holder,
    redact_revealing_codes,
)
from backend.tests.evaluation.judge.rubric import JudgeCriterion

LEFT = ARCHITECTURE_SINGLE_AGENT_RAG
RIGHT = ARCHITECTURE_MULTI_AGENT


def _payload(block_count: int, *, decision_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "service-quality-judge-output-v1",
        "user_context": {"primary_goal_code": "GENERAL_FITNESS", "requested_duration_minutes": 20},
        "plan": {
            "action_code": "KEEP",
            "estimated_duration_seconds": 1200,
            "exercises": [{"sequence": index} for index in range(block_count)],
        },
        "decision_codes": decision_codes if decision_codes is not None else ["EVAL_PLAN"],
        "used_deterministic_fallback": False,
    }


def _compare(model: Any, *, left_blocks: int, right_blocks: int, case_id: str = "SQ-SIMPLE-001"):
    return compare_pair(
        model,
        case_id=case_id,
        category="simple",
        left=LEFT,
        right=RIGHT,
        payloads={LEFT: _payload(left_blocks), RIGHT: _payload(right_blocks)},
    )


# -- the detector fires --------------------------------------------------


def test_a_purely_positional_judge_is_caught() -> None:
    """The whole point of judging twice.

    `AlwaysFirstPairwiseJudge` picks slot one every time, so it names a
    different architecture in each order. That must register as position bias
    and must not be counted as a win for anyone.
    """

    outcome = _compare(AlwaysFirstPairwiseJudge(), left_blocks=9, right_blocks=4)

    assert outcome.followed_position is True
    assert outcome.agreed is False
    assert outcome.consensus_winner is None
    assert outcome.winner_order_one != outcome.winner_order_two


def test_a_positional_judge_produces_no_wins_in_the_tally() -> None:
    result = PairResult(left=LEFT, right=RIGHT)
    model = AlwaysFirstPairwiseJudge()
    for index in range(4):
        result.outcomes.append(
            _compare(model, left_blocks=9, right_blocks=4, case_id=f"SQ-CASE-{index}")
        )

    tally = result.tally()
    assert tally[LEFT] == 0
    assert tally[RIGHT] == 0
    assert tally["DISAGREED"] == 4
    assert result.position_bias_rate == 1.0
    assert result.agreement_rate == 0.0


# -- a real preference survives -----------------------------------------


def test_a_content_driven_judge_agrees_across_both_orders() -> None:
    """The same plan wins whichever slot it is in."""

    outcome = _compare(LongerPlanPairwiseJudge(), left_blocks=9, right_blocks=4)

    assert outcome.agreed is True
    assert outcome.followed_position is False
    assert outcome.consensus_winner == LEFT
    for criterion in JudgeCriterion:
        assert outcome.criterion_consensus(criterion) == LEFT


def test_an_even_comparison_is_recorded_as_a_tie_not_a_win() -> None:
    outcome = _compare(LongerPlanPairwiseJudge(), left_blocks=6, right_blocks=6)

    assert outcome.verdict_order_one.overall_choice is PairwiseChoice.TIE
    assert outcome.agreed is True
    assert outcome.consensus_winner is None
    assert outcome.followed_position is False

    result = PairResult(left=LEFT, right=RIGHT, outcomes=[outcome])
    assert result.tally()["TIE"] == 1


# -- blinding -----------------------------------------------------------


def test_codes_that_name_the_pipeline_are_redacted() -> None:
    payload = _payload(6, decision_codes=["COORDINATOR_BALANCED", "DOWNSHIFT_APPLIED"])
    cleaned, removed = redact_revealing_codes(payload)

    assert removed == 1
    assert cleaned["decision_codes"] == ["DOWNSHIFT_APPLIED"]
    # The original is left alone; the caller decides what to send.
    assert payload["decision_codes"] == ["COORDINATOR_BALANCED", "DOWNSHIFT_APPLIED"]


def test_harmless_codes_are_left_alone() -> None:
    payload = _payload(6, decision_codes=["DOWNSHIFT_APPLIED", "REST_PRESERVED"])
    cleaned, removed = redact_revealing_codes(payload)

    assert removed == 0
    assert cleaned is payload


@pytest.mark.parametrize(
    "code", ["MULTI_AGENT_CONSENSUS", "SINGLE_PASS_PLAN", "SPECIALIST_MERGED", "ORCHESTRATED_PLAN"]
)
def test_every_revealing_shape_is_caught(code: str) -> None:
    _, removed = redact_revealing_codes(_payload(6, decision_codes=[code]))
    assert removed == 1


def test_redaction_count_reaches_the_outcome() -> None:
    outcome = compare_pair(
        LongerPlanPairwiseJudge(),
        case_id="SQ-SIMPLE-001",
        category="simple",
        left=LEFT,
        right=RIGHT,
        payloads={
            LEFT: _payload(9, decision_codes=["COORDINATOR_X"]),
            RIGHT: _payload(4, decision_codes=["AGENT_Y", "PLAIN"]),
        },
    )
    assert outcome.redacted_code_count == 2


# -- position assignment -------------------------------------------------


def test_first_slot_is_reproducible_and_not_always_the_same_side() -> None:
    """Randomised across cases, identical on a re-run.

    A shuffle that changed between runs would make two runs incomparable; one
    that never changed would leave the ordering confounded with the pair.
    """

    case_ids = [f"SQ-CASE-{index:03d}" for index in range(40)]
    first = [first_slot_holder(case_id, LEFT, RIGHT) for case_id in case_ids]

    assert first == [first_slot_holder(case_id, LEFT, RIGHT) for case_id in case_ids]
    assert set(first) == {LEFT, RIGHT}


def test_slot_choices_map_back_to_the_right_architecture() -> None:
    """Order two swaps the plans, so slot one holds the other architecture."""

    outcome = _compare(LongerPlanPairwiseJudge(), left_blocks=9, right_blocks=4)

    assert outcome.second_presented != outcome.first_presented
    assert {outcome.first_presented, outcome.second_presented} == {LEFT, RIGHT}
    # The longer plan is LEFT's, so whichever slot it occupied, LEFT wins.
    assert outcome.winner_order_one == LEFT
    assert outcome.winner_order_two == LEFT


# -- a missing plan is not a tie -----------------------------------------


def test_a_pair_with_one_missing_plan_is_excluded_not_tied() -> None:
    """An architecture that produced nothing must not score a draw for it."""

    result = PairResult(left=LEFT, right=RIGHT)
    result.unjudgeable.append({"case_id": "SQ-SAFETY-001", "no_plan_from": RIGHT})

    assert result.judged == 0
    assert result.tally() == {LEFT: 0, RIGHT: 0, "TIE": 0, "DISAGREED": 0}
    assert result.to_json()["unjudgeable"] == [{"case_id": "SQ-SAFETY-001", "no_plan_from": RIGHT}]
