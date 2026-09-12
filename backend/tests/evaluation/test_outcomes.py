"""The plan-rate decomposition, and the property that makes it worth having.

`llm_plan_rate` stays exactly as pre-registered. What these assert is that the
split reproduces it, that a decline is never counted as a rejected plan, and
that the class only the multi-agent contract can reach stays separable.
"""

from __future__ import annotations

import pytest

from backend.tests.evaluation.outcomes import OutcomeClass, breakdown, classify


def test_a_plan_that_survived_every_gate_is_a_plan() -> None:
    assert classify(has_plan=True, used_fallback=False, failure_codes=()) is OutcomeClass.PLAN


def test_a_fallback_plan_is_not_a_model_plan() -> None:
    """The user still got a plan; the architecture did not author it."""

    assert (
        classify(has_plan=True, used_fallback=True, failure_codes=("V3_COMPILATION_FAILED",))
        is not OutcomeClass.PLAN
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("V3_TRAINING_NOT_READY", OutcomeClass.DECLINED),
        ("V3_TRAINING_FAILED", OutcomeClass.DECLINED),
        ("V3_TRAINING_PROPOSAL_INVALID", OutcomeClass.CONTRACT),
        ("V3_TRAINING_NO_PROPOSAL", OutcomeClass.CONTRACT),
        ("LLM_AGENT_SCHEMA_INVALID", OutcomeClass.CONTRACT),
        ("LLM_AGENT_DOMAIN_INVALID", OutcomeClass.CONTRACT),
        ("V3_COMPILATION_FAILED", OutcomeClass.GATE),
        ("PLAN_EXERCISE_FAMILY_REPEATED", OutcomeClass.GATE),
        ("LLM_AGENT_PROVIDER_UNAVAILABLE", OutcomeClass.PROVIDER),
        ("V3_TRAINING_TIMEOUT", OutcomeClass.PROVIDER),
    ],
)
def test_every_code_the_paid_runs_produced_has_a_class(code: str, expected: OutcomeClass) -> None:
    assert classify(has_plan=False, used_fallback=True, failure_codes=(code,)) is expected


def test_a_decline_explains_the_missing_plan_spec_that_follows_it() -> None:
    """Ordering matters: one run carries the cause and its consequence.

    A declining Training leaves the Coordinator with nothing, so the run also
    reports V3_PLAN_SPEC_MISSING. Counting that as a contract breach would
    hide the decline behind its own side effect.
    """

    assert (
        classify(
            has_plan=False,
            used_fallback=True,
            failure_codes=("V3_TRAINING_NOT_READY", "V3_PLAN_SPEC_MISSING"),
        )
        is OutcomeClass.DECLINED
    )


def test_a_provider_failure_outranks_the_codes_it_causes() -> None:
    assert (
        classify(
            has_plan=False,
            used_fallback=True,
            failure_codes=("V3_TRAINING_TIMEOUT", "V3_PLAN_SPEC_MISSING"),
        )
        is OutcomeClass.PROVIDER
    )


def test_a_run_with_no_recorded_reason_is_still_classified() -> None:
    """Artefacts from before `CaseEvaluation` carried failure codes."""

    assert classify(has_plan=False, used_fallback=True, failure_codes=()) is OutcomeClass.GATE


def test_the_split_reproduces_the_pre_registered_rate() -> None:
    """The decomposition may add a view; it may not move the number."""

    items = (
        [OutcomeClass.PLAN] * 22
        + [OutcomeClass.DECLINED] * 5
        + [OutcomeClass.GATE] * 2
        + [OutcomeClass.CONTRACT]
    )
    result = breakdown(items)

    assert result.run_count == 30
    assert result.plan_rate == round(22 / 30, 4)
    assert result.decline_rate == round(5 / 30, 4)
    assert result.rejected_rate == round(3 / 30, 4)
    total = result.plan_rate + result.decline_rate + result.rejected_rate
    assert total == pytest.approx(1.0, abs=1e-4)


def test_an_architecture_that_cannot_decline_reports_a_zero_decline_rate() -> None:
    """The baselines' schema has no status field, so this is structural.

    It is the reason the split exists: a zero here is not the baseline being
    more willing, it is the baseline having no way to refuse.
    """

    result = breakdown([OutcomeClass.PLAN] * 25 + [OutcomeClass.GATE] * 4)

    assert result.decline_rate == 0.0
    assert result.rejected_rate == round(4 / 29, 4)


def test_the_json_names_the_asymmetry_it_exists_to_expose() -> None:
    payload = breakdown([OutcomeClass.PLAN]).to_json()

    counts = payload["counts"]
    assert isinstance(counts, dict)
    assert "multi-agent" in str(payload["note"])
    assert set(counts) == {item.value for item in OutcomeClass}
