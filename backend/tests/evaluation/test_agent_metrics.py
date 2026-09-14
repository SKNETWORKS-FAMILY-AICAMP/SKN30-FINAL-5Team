"""PHASE 4: multi-agent workflow metrics and the four named conflict scenarios.

The master specification lists conflicts A-D.  Two of them are deterministic and
are asserted; two are advisory and are only observed.  That split is not a
convenience -- ADR-0015 gives Recovery and Feasibility no enforcement, so scoring
"did the coordinator obey Recovery" would test a rule the system does not have,
and a green result would mean nothing.

    A. Training raises intensity / Recovery lowers it   -> observed
    B. Training proposes work / Safety BLOCKED it        -> asserted
    C. Training proposes 60 min / Feasibility says 20    -> asserted
    D. User preference vs pain restriction              -> asserted (via Safety)
"""

from __future__ import annotations

import pytest

from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE
from backend.tests.evaluation.dataset import EvaluationCase, ExpectedOutcome
from backend.tests.evaluation.evaluators.agent_metrics import (
    COORDINATOR_ROLE_CODE,
    SPECIALIST_ROLE_CODES,
    build_report,
    collect_run_metrics,
)
from backend.tests.evaluation.harness import EXCLUSION_CASES, GRAPH_CASES, run_case
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode
from backend.tests.evaluation.runners.run_multi_agent import ARCHITECTURE_CODE

BLOCKED_CASES = tuple(
    case for case in GRAPH_CASES if not case.expected_constraints.plan_generation_allowed
)
PLANNING_CASES = tuple(
    case for case in GRAPH_CASES if case.expected_constraints.plan_generation_allowed
)

# Cases whose input a correct service can actually satisfy. SQ-INVALID-002 asks
# for a gym session from a home-only pool, so it is expected to fail closed; it
# is excluded from "a good run looks like this" assertions and asserted on its
# own below, which is also what keeps these metrics from being vacuous.
SATISFIABLE_CASES = tuple(
    case for case in PLANNING_CASES if case.expected_outcome is not ExpectedOutcome.NO_PLAN
)
UNSATISFIABLE_CASES = tuple(
    case for case in PLANNING_CASES if case.expected_outcome is ExpectedOutcome.NO_PLAN
)


def _ids(case: EvaluationCase) -> str:
    return case.case_id


# --------------------------------------------------------------------------
# The seven metrics
# --------------------------------------------------------------------------


def test_the_seven_metrics_are_all_computable_offline() -> None:
    """No LangSmith needed: every metric comes from InvocationAudit and the result."""

    runs = [run_case(case) for case in GRAPH_CASES]
    report = build_report(
        runs, architecture_code=ARCHITECTURE_CODE, provider_label="scripted-offline"
    )
    body = report.to_json()
    for metric in (
        "agent_invocation_accuracy",
        "agent_role_consistency",
        "state_consistency",
        "workflow_completion_rate",
        "coordinator_conflict_resolution_accuracy",
        "safety_compliance_rate",
        "structured_output_success_rate",
    ):
        assert body[metric] is not None, metric


def test_a_compliant_run_scores_perfectly_on_every_deterministic_metric() -> None:
    """Every satisfiable case, with a working model, scores 1.0 across the board."""

    runs = [run_case(case) for case in (*SATISFIABLE_CASES, *BLOCKED_CASES)]
    body = build_report(
        runs, architecture_code=ARCHITECTURE_CODE, provider_label="scripted-offline"
    ).to_json()
    assert body["agent_invocation_accuracy"] == 1.0
    assert body["agent_role_consistency"] == 1.0
    assert body["state_consistency"] == 1.0
    assert body["workflow_completion_rate"] == 1.0
    assert body["safety_compliance_rate"] == 1.0
    assert body["structured_output_success_rate"] == 1.0


@pytest.mark.parametrize("case", SATISFIABLE_CASES, ids=_ids)
def test_a_planning_run_invokes_exactly_the_four_roles(case: EvaluationCase) -> None:
    metrics = collect_run_metrics(run_case(case))
    assert metrics.invoked_roles == {*SPECIALIST_ROLE_CODES, COORDINATOR_ROLE_CODE}
    assert metrics.invocation_accuracy


@pytest.mark.parametrize("case", BLOCKED_CASES, ids=_ids)
def test_a_blocked_run_invokes_no_role_at_all(case: EvaluationCase) -> None:
    """Both a cost property and a privacy one: nothing is sent to a provider."""

    metrics = collect_run_metrics(run_case(case))
    assert metrics.invoked_roles == frozenset()
    assert metrics.invocation_accuracy
    assert metrics.workflow_completed


def test_safety_compliance_stays_perfect_under_adversarial_scripts() -> None:
    """The metric that must not move, whatever the model does."""

    scripts = (
        Script(training=ScriptCode.SAFETY_VIOLATING),
        Script(
            coordinator=ScriptCode.SAFETY_VIOLATING, coordinator_repair=ScriptCode.SAFETY_VIOLATING
        ),
        Script(training=ScriptCode.POOL_ESCAPE),
    )
    runs = [run_case(case, script) for case in EXCLUSION_CASES for script in scripts]
    body = build_report(
        runs, architecture_code=ARCHITECTURE_CODE, provider_label="scripted-adversarial"
    ).to_json()
    assert body["safety_compliance_rate"] == 1.0


def test_structured_output_success_rate_falls_when_the_provider_returns_junk() -> None:
    """A metric that never moves is not measuring anything."""

    runs = [run_case(GRAPH_CASES[0], Script(training=ScriptCode.SCHEMA_INVALID))]
    body = build_report(
        runs, architecture_code=ARCHITECTURE_CODE, provider_label="scripted-invalid"
    ).to_json()
    assert body["structured_output_success_rate"] == 0.0


def test_role_consistency_falls_when_an_advisory_role_submits_a_plan() -> None:
    """ADR-0015 violated at the model, caught in the metric rather than hidden."""

    run = run_case(GRAPH_CASES[0], Script(recovery=ScriptCode.ROLE_VIOLATING))
    metrics = collect_run_metrics(run)
    # The contract refuses the proposal outright, so it never becomes a
    # round-one proposal at all -- role separation holds because the offending
    # answer was discarded, not because the model behaved.
    assert metrics.role_separation_held
    assert not metrics.structured_output_succeeded


# --------------------------------------------------------------------------
# Conflict B: Safety BLOCKED beats a Training proposal
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", BLOCKED_CASES, ids=_ids)
def test_conflict_b_safety_block_beats_any_training_proposal(case: EvaluationCase) -> None:
    run = run_case(case, Script(training=ScriptCode.SAFETY_VIOLATING))
    assert not run.has_plan
    assert run.status_code == case.expected_safety_result.required_action_code.value
    assert collect_run_metrics(run).safety_respected


# --------------------------------------------------------------------------
# Conflict C: requested duration beats a longer proposal
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", SATISFIABLE_CASES, ids=_ids)
def test_conflict_c_requested_duration_beats_an_overlong_proposal(
    case: EvaluationCase,
) -> None:
    """Training asks for roughly triple the time; the session must not grow."""

    run = run_case(case, Script(training=ScriptCode.DURATION_VIOLATING))
    plan = run.compiled_plan
    if plan is None:
        assert run.status_code == "FAILED"
        return
    target = case.expected_constraints.requested_duration_minutes
    assert target is not None
    delta = abs(plan.estimated_duration_seconds - target * SECONDS_PER_MINUTE)
    assert delta <= DURATION_TOLERANCE_SECONDS


# --------------------------------------------------------------------------
# Conflict D: pain restriction beats a stated preference
# --------------------------------------------------------------------------


def test_conflict_d_pain_restriction_beats_user_preference() -> None:
    """SQ-CONFLICT-002 puts the preferred movements at the top of the ranking.

    They are also the ones Safety excluded, so preference losing is the whole
    point of the case.
    """

    case = next(item for item in GRAPH_CASES if item.case_id == "SQ-CONFLICT-002")
    preferred = set(case.user_input.preferred_exercise_codes)
    assert preferred, "the case must state a preference for this to test anything"
    assert preferred.issubset(case.expected_constraints.excluded_exercise_codes)

    for script in (Script(), Script(training=ScriptCode.SAFETY_VIOLATING)):
        run = run_case(case, script)
        leaked = run.scenario.excluded_exercise_ids & set(run.prescribed_exercise_ids)
        assert leaked == set()


# --------------------------------------------------------------------------
# Conflict A: advisory only, observed and never scored
# --------------------------------------------------------------------------


def test_conflict_a_recovery_advice_is_observed_not_enforced() -> None:
    """Recovery's codes reach the coordinator, and nothing deterministic checks them.

    Pinning this keeps the report honest: if a future change started enforcing
    advisory codes, ADR-0015 would need revisiting rather than the metric
    quietly becoming a gate.
    """

    case = next(item for item in GRAPH_CASES if item.case_id == "SQ-CONFLICT-001")
    run = run_case(case)
    metrics = collect_run_metrics(run)
    assert metrics.advisory_codes_present, "advisory roles must still advise"

    report = build_report(
        [run], architecture_code=ARCHITECTURE_CODE, provider_label="scripted-offline"
    )
    observations = report.advisory_observations
    assert observations["runs_with_advisory_codes"] == 1
    # The advisory result is reported outside the scored metrics.
    assert "coordinator_plan_within_training_draft" in observations
    assert "ADR-0015" in str(observations["note"])


def test_recovery_ceiling_is_what_actually_binds_intensity() -> None:
    """The deterministic bound, not the advice, is what the plan has to respect."""

    case = next(item for item in GRAPH_CASES if item.case_id == "SQ-CONFLICT-001")
    run = run_case(case)
    plan = run.compiled_plan
    assert plan is not None
    ceiling = run.scenario.constraint_envelope.recovery_ceiling
    for item in plan.exercises:
        assert item.prescription.intensity_code in ceiling.allowed_intensity_codes
        assert item.prescription.sets <= (
            ceiling.maximum_sets_per_exercise or item.prescription.sets
        )


def test_an_unsatisfiable_request_lowers_the_metrics_rather_than_passing_quietly() -> None:
    """A metric that cannot fall is not measuring anything.

    SQ-INVALID-002 asks for a gym session from a home-only pool. No correct plan
    exists, so Training cannot answer, the coordinator never runs, and both
    workflow completion and structured-output success drop. Safety compliance
    stays perfect, which is the property that must never move.
    """

    assert UNSATISFIABLE_CASES, "the dataset must keep an unsatisfiable case"
    runs = [run_case(case) for case in UNSATISFIABLE_CASES]
    body = build_report(
        runs, architecture_code=ARCHITECTURE_CODE, provider_label="scripted-offline"
    ).to_json()
    assert body["workflow_completion_rate"] == 0.0
    assert body["structured_output_success_rate"] == 0.0
    assert body["safety_compliance_rate"] == 1.0
    for run in runs:
        assert not run.has_plan
        assert run.failure_codes
