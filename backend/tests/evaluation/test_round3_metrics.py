"""Free regression tests for the Round 3 diagnostic contract."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.app.integrations.langgraph.state import InvocationAudit
from backend.tests.evaluation.outcomes import OutcomeClass
from backend.tests.evaluation.round3_metrics import (
    DeliveryOutcome,
    FailureStage,
    failure_stages,
    normalize_run,
    paired_model_plan_comparison,
    summarize_invocations,
    summarize_outcomes,
    wilson_interval,
)


def _audit(
    role: str,
    phase: str,
    *,
    latency_ms: int = 10,
    failure_code: str | None = None,
) -> InvocationAudit:
    return InvocationAudit(
        role_code=role,
        phase_code=phase,
        status_code="FAILED" if failure_code else "SUCCEEDED",
        attempt_count=1,
        latency_ms=latency_ms,
        input_token_count=100,
        output_token_count=20,
        provider_usage_present=True,
        failure_code=failure_code,
    )


@dataclass(frozen=True)
class _Case:
    case_id: str


@dataclass(frozen=True)
class _Run:
    case: _Case
    has_plan: bool
    used_fallback: bool
    failure_codes: tuple[str, ...] = ()
    violation_codes: tuple[str, ...] = ()


def test_delivery_and_model_outcomes_are_reported_separately() -> None:
    run = _Run(
        case=_Case("CASE-1"),
        has_plan=True,
        used_fallback=True,
        failure_codes=("V3_COMPILATION_FAILED",),
    )

    outcome = normalize_run(run, ())

    assert outcome.delivery is DeliveryOutcome.FALLBACK_PLAN
    assert outcome.model_outcome is OutcomeClass.GATE
    assert outcome.failure_stages == (FailureStage.COMPILER,)


def test_generic_domain_invalid_uses_audit_role_and_phase() -> None:
    stages = failure_stages(
        failure_codes=("LLM_AGENT_DOMAIN_INVALID", "V3_PLAN_SPEC_MISSING"),
        violation_codes=(),
        invocation_audits=(
            _audit(
                "COORDINATOR",
                "REPAIR",
                failure_code="LLM_AGENT_DOMAIN_INVALID",
            ),
        ),
    )

    assert stages == (FailureStage.COMPILER, FailureStage.COORDINATOR_REPAIR)


def test_integrity_violation_is_not_hidden_by_fallback_delivery() -> None:
    stages = failure_stages(
        failure_codes=("REPAIR_ATTEMPT_EXHAUSTED",),
        violation_codes=("REQUESTED_DURATION_MISMATCH",),
        invocation_audits=(),
    )

    assert FailureStage.INTEGRITY_VALIDATOR in stages


def test_outcome_summary_adds_intervals_without_changing_counts() -> None:
    runs = (
        _Run(_Case("A"), True, False),
        _Run(_Case("B"), True, True, ("V3_COMPILATION_FAILED",)),
        _Run(_Case("C"), False, False, ("LLM_AGENT_PROVIDER_UNAVAILABLE",)),
    )

    summary = summarize_outcomes(runs, ((), (), ()))

    assert summary["delivery_counts"] == {
        "MODEL_PLAN": 1,
        "FALLBACK_PLAN": 1,
        "NO_PLAN": 1,
    }
    assert summary["model_plan_rate_ci95"] is not None
    assert summary["plan_delivery_rate_ci95"] is not None


def test_wilson_interval_handles_small_and_empty_samples() -> None:
    assert wilson_interval(0, 0) is None
    interval = wilson_interval(16, 20)
    assert interval is not None
    assert interval.lower == pytest.approx(0.584, abs=0.001)
    assert interval.upper == pytest.approx(0.9193, abs=0.001)
    with pytest.raises(ValueError):
        wilson_interval(2, 1)


def test_invocation_summary_exposes_role_phase_latency_and_failures() -> None:
    summary = summarize_invocations(
        (
            _audit("TRAINING", "PROPOSE", latency_ms=10),
            _audit("TRAINING", "PROPOSE", latency_ms=30),
            _audit(
                "COORDINATOR",
                "COORDINATE",
                latency_ms=20,
                failure_code="LLM_AGENT_DOMAIN_INVALID",
            ),
        )
    )

    assert summary["TRAINING:PROPOSE"]["p50_latency_ms"] == 10
    assert summary["TRAINING:PROPOSE"]["p95_latency_ms"] == 30
    assert summary["COORDINATOR:COORDINATE"]["failed_calls"] == 1


def test_paired_plan_comparison_preserves_ties_and_uncertainty() -> None:
    left = (
        _Run(_Case("A"), True, False),
        _Run(_Case("B"), False, False),
        _Run(_Case("C"), True, True),
    )
    right = (
        _Run(_Case("A"), False, False),
        _Run(_Case("B"), True, False),
        _Run(_Case("C"), True, True),
    )

    payload = paired_model_plan_comparison(left, right).to_json()

    assert payload["left_wins"] == 1
    assert payload["right_wins"] == 1
    assert payload["ties"] == 1
    assert payload["left_win_rate_among_decisive"] == 0.5
    assert payload["left_win_rate_ci95"] is not None


def test_paired_plan_comparison_rejects_misaligned_cases() -> None:
    with pytest.raises(ValueError, match="identical case order"):
        paired_model_plan_comparison(
            (_Run(_Case("A"), True, False),),
            (_Run(_Case("B"), True, False),),
        )
