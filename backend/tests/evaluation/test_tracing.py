"""Pin what a LangSmith trace of the shipped graph does and does not contain.

The gap these tests describe is not a bug to be fixed here: `provider.py`
disables provider tracing on purpose, to stop prompt content reaching a SaaS.
Pinning it means the report can state the limit precisely, and that a future
change to it becomes visible rather than silent.
"""

from __future__ import annotations

import os

from backend.tests.evaluation.harness import GRAPH_CASES, run_case
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode
from backend.tests.evaluation.tracing import (
    EXPECTED_TRACED_NODES,
    LANGSMITH_API_KEY_ENV,
    TracingUnavailableError,
    langsmith_configured,
    langsmith_run,
    record_runs,
)


def test_the_whole_workflow_is_visible_to_a_tracer() -> None:
    """Every graph node appears, so a trace explains which path a run took."""

    with record_runs() as recorder:
        run = run_case(GRAPH_CASES[0])
    assert run.status_code == "SUCCEEDED"

    observed = set(recorder.node_names)
    missing = [name for name in EXPECTED_TRACED_NODES if name not in observed]
    assert missing == [], f"a trace would not show: {missing}"


def test_the_three_specialists_each_appear_as_their_own_span() -> None:
    """Role-level visibility is what makes a multi-agent trace worth reading."""

    with record_runs() as recorder:
        run_case(GRAPH_CASES[0])
    names = recorder.node_names
    for node in ("agent_training", "agent_recovery", "agent_feasibility"):
        assert node in names


def test_the_provider_calls_are_not_traced() -> None:
    """The documented limit, measured.

    Four LLM calls are made and none of them produces an LLM span, because
    `provider.py` wraps each invocation in `tracing_context(enabled=False)`.
    Prompts and raw model output therefore never reach LangSmith.
    """

    with record_runs() as recorder:
        run = run_case(GRAPH_CASES[0])

    assert run.llm_call_count == 4, "this case should invoke all four roles"
    assert recorder.llm_run_count == 0, (
        "a provider span appeared; provider.py's tracing_context(enabled=False) "
        "may have been removed, which is a privacy policy change"
    )


def test_token_usage_is_still_recoverable_from_the_invocation_audit() -> None:
    """What the trace cannot give, the graph's own audit still can."""

    run = run_case(GRAPH_CASES[0])
    input_tokens, output_tokens = run.token_usage
    assert input_tokens > 0 and output_tokens > 0
    assert len(run.graph_result.invocation_audits) == 4


def test_a_failure_path_is_visible_in_the_trace() -> None:
    """A trace has to explain a bad run, not only a good one."""

    with record_runs() as recorder:
        run = run_case(GRAPH_CASES[0], Script(training=ScriptCode.PROVIDER_EXCEPTION))
    assert run.status_code in {"SUCCEEDED", "FAILED"}
    names = set(recorder.node_names)
    assert "agent_training" in names
    assert "fallback" in names or "terminal" in names


def test_a_blocked_run_shows_its_early_termination() -> None:
    blocked = [
        case for case in GRAPH_CASES if not case.expected_constraints.plan_generation_allowed
    ]
    assert blocked
    with record_runs() as recorder:
        run = run_case(blocked[0])
    names = set(recorder.node_names)
    assert "validate_entry" in names
    assert "terminal" in names
    assert "coordinator_agent" not in names
    assert run.llm_call_count == 0


def test_tracing_is_off_without_a_key_and_the_run_still_works() -> None:
    """The master specification requires local evaluation to work without LangSmith."""

    previous = os.environ.pop(LANGSMITH_API_KEY_ENV, None)
    try:
        assert not langsmith_configured()
        with langsmith_run("multi-agent-test") as status:
            assert not status.enabled
            assert status.reason is not None
            run = run_case(GRAPH_CASES[0])
        assert run.status_code == "SUCCEEDED"
    finally:
        if previous is not None:
            os.environ[LANGSMITH_API_KEY_ENV] = previous


def test_a_required_trace_fails_loudly_when_no_key_is_configured() -> None:
    """The run whose purpose is a trace must not silently produce none."""

    previous = os.environ.pop(LANGSMITH_API_KEY_ENV, None)
    try:
        raised = False
        try:
            with langsmith_run("multi-agent-test", required=True):
                pass
        except TracingUnavailableError:
            raised = True
        assert raised
    finally:
        if previous is not None:
            os.environ[LANGSMITH_API_KEY_ENV] = previous
