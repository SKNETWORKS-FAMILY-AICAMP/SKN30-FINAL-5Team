"""PHASE 2: everything a machine can decide, decided before any judge is asked.

The twelve checks the master specification lists map onto the tests below.  The
adversarial ones matter most: they script the provider into answering badly and
assert that the service still refuses to hand the user something unsafe.  A
safety claim backed only by a well-behaved model is not evidence.
"""

from __future__ import annotations

import pytest

from backend.app.domain.agents.v3_contracts import SpecialistAgentTypeCode
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE
from backend.tests.evaluation.dataset import CaseCategory, EvaluationCase, ExpectedOutcome
from backend.tests.evaluation.evaluators import Severity, evaluate_case
from backend.tests.evaluation.harness import EXCLUSION_CASES, GRAPH_CASES, run_case
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode

# Ways a model can answer that would put an unsafe or invalid plan in front of a
# user if nothing downstream stopped it.
ADVERSARIAL_TRAINING_SCRIPTS = (
    ScriptCode.SAFETY_VIOLATING,
    ScriptCode.POOL_ESCAPE,
    ScriptCode.DURATION_VIOLATING,
    ScriptCode.PHASE_MISSING,
)

# The same, but from the coordinator, which is the last model in the path.
ADVERSARIAL_COORDINATOR_SCRIPTS = ADVERSARIAL_TRAINING_SCRIPTS

PROVIDER_FAILURE_SCRIPTS = (
    ScriptCode.SCHEMA_INVALID,
    ScriptCode.PARSE_ERROR,
    ScriptCode.PROVIDER_TIMEOUT,
    ScriptCode.PROVIDER_EXCEPTION,
    ScriptCode.HANG,
    ScriptCode.NOT_READY,
)


def _ids(case: EvaluationCase) -> str:
    return case.case_id


# --------------------------------------------------------------------------
# 1. Structured output schema validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", GRAPH_CASES, ids=_ids)
def test_compliant_run_produces_a_self_consistent_structured_result(
    case: EvaluationCase,
) -> None:
    """Every contract re-derives its own hash, so a valid run proves its own integrity."""

    run = run_case(case)
    evaluation = evaluate_case(run)
    assert evaluation.passed, [finding.check_code for finding in evaluation.failures]

    for proposal in run.graph_result.round_one_proposals:
        assert proposal.envelope_hash == run.scenario.constraint_envelope.envelope_hash
        assert proposal.pool_hash == run.scenario.exercise_pool.pool_hash

    plan = run.compiled_plan
    if plan is not None:
        assert plan.envelope_hash == run.scenario.constraint_envelope.envelope_hash
        assert plan.pool_hash == run.scenario.exercise_pool.pool_hash


@pytest.mark.parametrize("role", ["training", "recovery", "feasibility", "coordinator"])
def test_malformed_provider_output_never_reaches_the_user(role: str) -> None:
    """A schema-invalid answer is a failed answer, not a plan with a bad field."""

    case = GRAPH_CASES[0]
    run = run_case(case, Script(**{role: ScriptCode.SCHEMA_INVALID}))
    if run.has_plan:
        # The deterministic fallback may still answer. What it may not do is
        # carry the malformed content forward.
        assert run.used_fallback
    assert evaluate_case(run).critical_failures == ()


# --------------------------------------------------------------------------
# 2. Requested duration is never exceeded
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", GRAPH_CASES, ids=_ids)
def test_plan_duration_stays_inside_the_approved_window(case: EvaluationCase) -> None:
    run = run_case(case)
    plan = run.compiled_plan
    if plan is None:
        return
    target = case.expected_constraints.requested_duration_minutes
    assert target is not None
    delta = abs(plan.estimated_duration_seconds - target * SECONDS_PER_MINUTE)
    assert delta <= DURATION_TOLERANCE_SECONDS, (
        f"{case.case_id}: {plan.estimated_duration_seconds}s against {target}min"
    )
    assert plan.requested_duration_minutes == target


def test_a_model_cannot_stretch_the_session_past_the_window() -> None:
    """The coordinator asks for triple the requested time; the plan must not ship."""

    case = GRAPH_CASES[0]
    run = run_case(
        case,
        Script(
            coordinator=ScriptCode.DURATION_VIOLATING,
            coordinator_repair=ScriptCode.DURATION_VIOLATING,
        ),
    )
    target = case.expected_constraints.requested_duration_minutes
    assert target is not None
    plan = run.compiled_plan
    if plan is not None:
        delta = abs(plan.estimated_duration_seconds - target * SECONDS_PER_MINUTE)
        assert delta <= DURATION_TOLERANCE_SECONDS
    assert evaluate_case(run).critical_failures == ()


# --------------------------------------------------------------------------
# 3-5. Safety: excluded, prohibited and pain-conflicting exercises
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", EXCLUSION_CASES, ids=_ids)
@pytest.mark.parametrize("script_code", ADVERSARIAL_TRAINING_SCRIPTS)
def test_training_cannot_reintroduce_an_excluded_exercise(
    case: EvaluationCase, script_code: ScriptCode
) -> None:
    """The plan's author is Training. It still cannot relax a Safety exclusion."""

    run = run_case(case, Script(training=script_code))
    _assert_no_excluded_exercise(run)


@pytest.mark.parametrize("case", EXCLUSION_CASES, ids=_ids)
@pytest.mark.parametrize("script_code", ADVERSARIAL_COORDINATOR_SCRIPTS)
def test_coordinator_cannot_reintroduce_an_excluded_exercise(
    case: EvaluationCase, script_code: ScriptCode
) -> None:
    """Golden scenario 6: the coordinator is not the last word, validation is.

    The enforcement point is downstream of the coordinator (ADR-0015), so the
    repair round is scripted to misbehave too; otherwise a compliant repair
    would mask whether anything actually stopped the first answer.
    """

    run = run_case(case, Script(coordinator=script_code, coordinator_repair=script_code))
    _assert_no_excluded_exercise(run)


@pytest.mark.parametrize("case", GRAPH_CASES, ids=_ids)
def test_prohibited_exercises_never_appear(case: EvaluationCase) -> None:
    run = run_case(case)
    evaluation = evaluate_case(run)
    offending = [
        finding
        for finding in evaluation.findings
        if finding.check_code == "PROHIBITED_EXERCISE_IN_FINAL_PLAN"
    ]
    assert offending == [], offending


def _assert_no_excluded_exercise(run: object) -> None:
    from backend.tests.evaluation.runners.run_multi_agent import CaseRunResult

    assert isinstance(run, CaseRunResult)
    leaked = run.scenario.excluded_exercise_ids & set(run.prescribed_exercise_ids)
    assert leaked == set(), f"{run.case.case_id}: excluded exercise reached the plan"
    evaluation = evaluate_case(run)
    assert evaluation.critical_failures == (), [
        finding.check_code for finding in evaluation.critical_failures
    ]


# --------------------------------------------------------------------------
# 6. A safety block cannot be ignored
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [case for case in GRAPH_CASES if not case.expected_constraints.plan_generation_allowed],
    ids=_ids,
)
@pytest.mark.parametrize(
    "script",
    [
        Script(),
        Script(training=ScriptCode.SAFETY_VIOLATING),
        Script(coordinator=ScriptCode.SAFETY_VIOLATING),
    ],
    ids=["compliant", "training-violating", "coordinator-violating"],
)
def test_blocked_safety_never_yields_a_plan(case: EvaluationCase, script: Script) -> None:
    """REST and STOP_AND_SEEK_HELP mean no session, whatever any model answers."""

    run = run_case(case, script)
    assert not run.has_plan
    assert run.status_code == case.expected_safety_result.required_action_code.value
    assert run.invocations == (), "a blocked envelope must not reach any model"


# --------------------------------------------------------------------------
# 7-8. Missing and invalid input
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [case for case in GRAPH_CASES if case.category is CaseCategory.INVALID_INPUT],
    ids=_ids,
)
def test_invalid_input_fails_closed(case: EvaluationCase) -> None:
    """An unsatisfiable request fails rather than producing an unperformable plan."""

    run = run_case(case)
    if case.expected_outcome is ExpectedOutcome.NO_PLAN:
        assert not run.has_plan
        assert run.failure_codes
    assert evaluate_case(run).critical_failures == ()


# --------------------------------------------------------------------------
# 9. State is not lost between agents
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", GRAPH_CASES, ids=_ids)
def test_proposals_reach_the_coordinator_in_canonical_role_order(
    case: EvaluationCase,
) -> None:
    """The three branches finish in any order; the coordinator must not see that.

    `collect_proposals` re-reads outcomes by role rather than by arrival, which
    is what makes a run reproducible from stored inputs.
    """

    run = run_case(case)
    proposals = run.graph_result.round_one_proposals
    if len(proposals) != 3:
        return
    assert tuple(proposal.agent_type_code for proposal in proposals) == (
        SpecialistAgentTypeCode.TRAINING,
        SpecialistAgentTypeCode.RECOVERY,
        SpecialistAgentTypeCode.FEASIBILITY,
    )


def test_repeated_runs_of_one_case_agree() -> None:
    """Same input, same scripted answers, same plan. Parallel fan-in included."""

    case = GRAPH_CASES[0]
    first = run_case(case)
    second = run_case(case)
    assert first.status_code == second.status_code
    assert first.prescribed_exercise_ids == second.prescribed_exercise_ids
    assert first.failure_codes == second.failure_codes
    if first.plan_spec is not None and second.plan_spec is not None:
        assert first.plan_spec.plan_hash == second.plan_spec.plan_hash


# --------------------------------------------------------------------------
# ADR-0015 role separation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["recovery", "feasibility"])
def test_an_advisory_specialist_cannot_submit_a_plan(role: str) -> None:
    """Only Training owns an exercise plan. The contract, not the prompt, enforces it."""

    case = GRAPH_CASES[0]
    run = run_case(case, Script(**{role: ScriptCode.ROLE_VIOLATING}))
    for proposal in run.graph_result.round_one_proposals:
        if proposal.agent_type_code is not SpecialistAgentTypeCode.TRAINING:
            assert proposal.exercise_prescriptions == ()
    assert evaluate_case(run).critical_failures == ()


@pytest.mark.parametrize("case", GRAPH_CASES, ids=_ids)
def test_only_training_carries_prescriptions_on_a_compliant_run(
    case: EvaluationCase,
) -> None:
    run = run_case(case)
    for proposal in run.graph_result.round_one_proposals:
        if proposal.agent_type_code is SpecialistAgentTypeCode.TRAINING:
            continue
        assert proposal.exercise_prescriptions == ()
        assert proposal.adjustment_codes, "an advisory role must still advise"


# --------------------------------------------------------------------------
# 12. Agent failure handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize("script_code", PROVIDER_FAILURE_SCRIPTS)
@pytest.mark.parametrize("role", ["training", "recovery", "feasibility"])
def test_a_failing_specialist_never_yields_an_unsafe_plan(
    role: str, script_code: ScriptCode
) -> None:
    case = EXCLUSION_CASES[0]
    run = run_case(case, Script(**{role: script_code}))
    _assert_no_excluded_exercise(run)
    assert run.status_code in {"SUCCEEDED", "FAILED"}
    if run.status_code == "FAILED":
        assert run.failure_codes, "a failure must say why"


@pytest.mark.parametrize("script_code", PROVIDER_FAILURE_SCRIPTS)
def test_a_failing_coordinator_never_yields_an_unsafe_plan(
    script_code: ScriptCode,
) -> None:
    case = EXCLUSION_CASES[0]
    run = run_case(case, Script(coordinator=script_code, coordinator_repair=script_code))
    _assert_no_excluded_exercise(run)


def test_total_provider_failure_falls_back_or_fails_closed() -> None:
    """Golden scenario 5 and 13: a deterministic answer, or no answer at all."""

    case = GRAPH_CASES[0]
    run = run_case(
        case,
        Script(
            training=ScriptCode.PROVIDER_EXCEPTION,
            recovery=ScriptCode.PROVIDER_EXCEPTION,
            feasibility=ScriptCode.PROVIDER_EXCEPTION,
            coordinator=ScriptCode.PROVIDER_EXCEPTION,
        ),
    )
    assert run.used_fallback
    assert run.invocations, "the run must record that the provider was attempted"
    if run.has_plan:
        assert evaluate_case(run).passed
    else:
        assert run.status_code == "FAILED"
        assert run.failure_codes


def test_no_finding_is_left_unattributed() -> None:
    """Every finding must say whether the service or the harness is at fault."""

    from backend.tests.evaluation.evaluators.findings import DefectClass

    for case in GRAPH_CASES:
        evaluation = evaluate_case(run_case(case))
        for finding in evaluation.findings:
            if finding.severity is Severity.INFO:
                assert finding.defect_class is DefectClass.NOT_A_DEFECT
            else:
                assert finding.defect_class is not DefectClass.NOT_A_DEFECT


# --------------------------------------------------------------------------
# Deterministic fallback coverage (characterisation, not a target)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [case for case in GRAPH_CASES if case.expected_constraints.plan_generation_allowed],
    ids=_ids,
)
def test_when_the_fallback_cannot_fill_the_session_it_fails_closed(
    case: EvaluationCase,
) -> None:
    """The deterministic path either answers safely or does not answer at all.

    It cannot always fill a session: the surviving pool and the Recovery sets
    ceiling bound what it can build, and both are tightest for users carrying
    exclusions or a low ceiling. Section 7 says the request must then fail
    rather than quietly hand back a shorter workout, so that is what is asserted
    here -- not a coverage number, which is a property of the catalog and would
    turn into a target nobody agreed to.
    """

    run = run_case(
        case,
        Script(
            training=ScriptCode.PROVIDER_EXCEPTION,
            recovery=ScriptCode.PROVIDER_EXCEPTION,
            feasibility=ScriptCode.PROVIDER_EXCEPTION,
            coordinator=ScriptCode.PROVIDER_EXCEPTION,
        ),
    )
    assert run.used_fallback
    if run.has_plan:
        assert evaluate_case(run).passed
        target = case.expected_constraints.requested_duration_minutes
        assert target is not None
        plan = run.compiled_plan
        assert plan is not None
        delta = abs(plan.estimated_duration_seconds - target * SECONDS_PER_MINUTE)
        assert delta <= DURATION_TOLERANCE_SECONDS, "a fallback must not silently shorten"
    else:
        assert run.status_code == "FAILED"
        assert run.failure_codes
        assert evaluate_case(run).critical_failures == ()


def test_a_fallback_records_why_it_happened() -> None:
    """`used_fallback` alone cannot be diagnosed after the run.

    The held-out comparison wrote seven multi-agent fallbacks with no reason
    attached, and recovering them meant querying LangSmith traces that an
    untraced run would never have produced.
    """

    case = GRAPH_CASES[0]
    run = run_case(case, Script(training=ScriptCode.SCHEMA_INVALID))
    evaluation = evaluate_case(run)

    assert run.used_fallback
    assert evaluation.failure_codes == run.failure_codes
    assert evaluation.failure_codes, "a fallback with no recorded cause"
    assert "failure_codes" in evaluation.to_json()
