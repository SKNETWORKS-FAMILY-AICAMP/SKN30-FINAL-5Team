"""PHASE 2, checks 10 and 11: the graph always terminates and never loops.

The compiled topology is **not** acyclic.  `validate_repair` reuses the
`after_validation` router, whose declared targets include `coordinator_repair`,
so the drawn graph contains exactly one cycle:

    coordinator_repair -> compile_repair -> validate_repair -> coordinator_repair

Loop freedom is therefore a *state* guarantee, not a structural one.
`after_validation` routes to repair only while `repair_attempts == 0`, and
`coordinator_repair` sets it to 1 on every exit path, so the cycle is entered at
most once.  These tests pin both halves: that this is the only cycle, and that
the guard which bounds it still holds.  Asserting a DAG here would be asserting
something untrue, and asserting only that runs finish quickly would prove only
the runs that happened to be taken.
"""

from __future__ import annotations

import pytest

from backend.app.integrations.langgraph.graph import create_v3_graph
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.evaluators.failure_evaluator import (
    KNOWN_STATUS_CODES,
    MAX_REPAIR_ATTEMPTS,
)
from backend.tests.evaluation.harness import GRAPH_CASES, run_case
from backend.tests.evaluation.runners.fake_chat import Script, ScriptCode

TERMINAL_NODES = {"finalize", "terminal"}

# The repair path is deliberately built from separate nodes rather than by
# routing back into the first ones, which is what keeps the graph acyclic.
REPAIR_NODES = {"coordinator_repair", "compile_repair", "validate_repair"}


def _ids(case: EvaluationCase) -> str:
    return case.case_id


def _edges() -> set[tuple[str, str]]:
    graph = create_v3_graph().get_graph()
    return {(edge.source, edge.target) for edge in graph.edges}


def _nodes() -> set[str]:
    return set(create_v3_graph().get_graph().nodes)


def _simple_cycles() -> set[frozenset[str]]:
    """Return every distinct node set that forms a cycle in the compiled graph."""

    adjacency: dict[str, set[str]] = {}
    for source, target in _edges():
        adjacency.setdefault(source, set()).add(target)

    found: set[frozenset[str]] = set()

    def walk(node: str, path: list[str], on_path: set[str]) -> None:
        for target in sorted(adjacency.get(node, set())):
            if target in on_path:
                found.add(frozenset(path[path.index(target) :]))
            elif target not in path:
                walk(target, [*path, target], on_path | {target})

    for source in sorted(adjacency):
        walk(source, [source], {source})
    return found


def test_the_repair_cycle_is_the_only_cycle() -> None:
    """One bounded cycle is the design. A second one would be an unreviewed loop."""

    assert _simple_cycles() == {frozenset(REPAIR_NODES)}


def test_repair_runs_on_dedicated_nodes() -> None:
    """The repair round must not re-enter the first compile and validate nodes."""

    assert REPAIR_NODES.issubset(_nodes())
    edges = _edges()
    assert ("coordinator_repair", "compile_repair") in edges
    assert ("coordinator_repair", "compile") not in edges
    assert ("compile_repair", "validate_repair") in edges


def test_the_repair_cycle_is_bounded_by_the_attempt_guard() -> None:
    """The router, not the topology, is what stops a second repair round.

    This pins the guard directly. If it is ever relaxed the cycle above becomes
    reachable twice, and no runtime test would necessarily catch it.
    """

    from backend.app.integrations.langgraph.routing import after_validation

    class _Validation:
        passed = False
        repairable = True
        violation_codes = ("REQUESTED_DURATION_MISMATCH",)

    first_pass = {"integrity_validation": _Validation(), "repair_attempts": 0}
    second_pass = {"integrity_validation": _Validation(), "repair_attempts": 1}
    assert after_validation(first_pass) == "coordinator_repair"  # type: ignore[arg-type]
    assert after_validation(second_pass) == "fallback"  # type: ignore[arg-type]


def test_coordinator_repair_always_records_its_attempt() -> None:
    """Every exit path from the repair node must set `repair_attempts`.

    A path that forgot to would leave the guard above reading 0 forever, which
    is the one way the bounded cycle could become unbounded.
    """

    import ast
    import inspect

    from backend.app.integrations.langgraph import nodes

    source = inspect.getsource(nodes.coordinator_repair)
    tree = ast.parse(source.strip())
    returns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    ]
    assert returns, "coordinator_repair must return state updates"
    for statement in returns:
        assert isinstance(statement.value, ast.Dict)
        keys = {key.value for key in statement.value.keys if isinstance(key, ast.Constant)}
        assert "repair_attempts" in keys, ast.dump(statement)


def test_every_terminal_node_leads_to_end() -> None:
    edges = _edges()
    for node in TERMINAL_NODES:
        assert (node, "__end__") in edges, f"{node} does not reach END"


@pytest.mark.parametrize("case", GRAPH_CASES, ids=_ids)
def test_every_case_terminates_with_an_actionable_status(case: EvaluationCase) -> None:
    run = run_case(case)
    assert run.status_code in KNOWN_STATUS_CODES


@pytest.mark.parametrize(
    "script",
    [
        Script(),
        Script(training=ScriptCode.SAFETY_VIOLATING),
        Script(coordinator=ScriptCode.PHASE_MISSING),
        Script(coordinator=ScriptCode.PHASE_MISSING, coordinator_repair=ScriptCode.PHASE_MISSING),
        Script(training=ScriptCode.HANG),
        Script(
            training=ScriptCode.PROVIDER_EXCEPTION,
            recovery=ScriptCode.PROVIDER_EXCEPTION,
            feasibility=ScriptCode.PROVIDER_EXCEPTION,
        ),
    ],
    ids=[
        "compliant",
        "training-unsafe",
        "coordinator-shape-broken",
        "coordinator-and-repair-broken",
        "training-hangs",
        "all-specialists-fail",
    ],
)
def test_repair_is_bounded_to_one_round(script: Script) -> None:
    """One repair, then the deterministic path. Never a second model round."""

    run = run_case(GRAPH_CASES[0], script)
    assert run.repair_attempts <= MAX_REPAIR_ATTEMPTS
    assert run.status_code in KNOWN_STATUS_CODES

    coordinator_repairs = [
        invocation
        for invocation in run.invocations
        if invocation.role_code == "COORDINATOR" and invocation.mode_code == "REPAIR"
    ]
    assert len(coordinator_repairs) <= MAX_REPAIR_ATTEMPTS


def test_a_hanging_provider_is_cancelled_by_the_node_deadline() -> None:
    """A model that never answers must not hold the graph open."""

    run = run_case(GRAPH_CASES[0], Script(training=ScriptCode.HANG))
    assert run.status_code in KNOWN_STATUS_CODES
    assert any("TIMEOUT" in code for code in run.failure_codes), run.failure_codes
    assert not run.has_plan or run.used_fallback


def test_a_blocked_envelope_terminates_without_calling_any_model() -> None:
    """Cost and privacy both: a blocked request must not reach a provider at all."""

    blocked = [
        case for case in GRAPH_CASES if not case.expected_constraints.plan_generation_allowed
    ]
    assert blocked, "the dataset must contain a blocked case"
    for case in blocked:
        run = run_case(case)
        assert run.invocations == ()
        assert run.llm_call_count == 0
        assert not run.has_plan
