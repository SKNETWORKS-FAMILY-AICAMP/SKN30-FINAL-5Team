import asyncio

from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RegenerationContext
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.tests.unit.test_v3_agent_contracts import envelope, pool
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan
from backend.tests.unit.v3_langgraph_test_support import (
    Coordinator,
    Fallback,
    Validation,
    Validator,
    graph_input,
)


def test_coordinator_timeout_uses_validated_deterministic_fallback() -> None:
    coordinator = Coordinator(timeout=True)
    current_input = graph_input(coordinator=coordinator, timeout=0.01)

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "SUCCEEDED"
    assert result.used_fallback
    assert current_input.compiler.calls == 1
    assert current_input.validator.calls == 1


def test_stop_and_seek_help_is_terminal_and_never_becomes_fallback() -> None:
    source = envelope()
    values = source.model_dump(exclude={"envelope_hash"})
    values.update(
        plan_generation_allowed=False,
        safety_required_action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
    )
    blocked = ConstraintEnvelope.create(**values)
    current_input = graph_input(current_envelope=blocked, current_pool=pool(blocked))

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "STOP_AND_SEEK_HELP"
    assert not result.used_fallback
    assert current_input.fallback.calls == 0
    assert all(port.propose_calls == 0 for port in current_input.specialists.values())


def test_no_safe_fallback_returns_planless_terminal() -> None:
    current_input = graph_input(coordinator=Coordinator(timeout=True), fallback=Fallback(None))

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "FAILED"
    assert result.plan_spec is None
    assert result.compiled_plan is None


def test_exact_duplicate_regeneration_is_rejected_after_all_specialists_rerun() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    previous = plan(coordinator_input(current_envelope, current_pool))
    context = RegenerationContext(
        generation_sequence=1,
        previous_plan_hash=previous.plan_hash,
        previous_exercise_ids=tuple(item.exercise_id for item in previous.exercise_prescriptions),
        variation_codes=("ORDER",),
    )
    current_input = graph_input(
        current_envelope=current_envelope,
        current_pool=current_pool,
        regeneration_context=context,
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "NO_ALTERNATIVE_AVAILABLE"
    assert all(port.propose_calls == 1 for port in current_input.specialists.values())


def test_third_regeneration_is_rejected_before_llm_calls() -> None:
    context = RegenerationContext.model_construct(
        schema_version="regeneration-context-v1",
        generation_sequence=3,
        previous_plan_hash="a" * 64,
        previous_exercise_ids=(),
        variation_codes=("ORDER",),
        exact_duplicate_forbidden=True,
    )
    current_input = graph_input(regeneration_context=context)

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "REGENERATION_LIMIT_REACHED"
    assert all(port.propose_calls == 0 for port in current_input.specialists.values())


def test_failed_integrity_validation_is_named_in_the_terminal_result() -> None:
    # A terminal FAILED used to carry no failure code at all when validation
    # was what refused the plan, so the decision record said only that the run
    # failed. That is not reproducible from stored inputs, and it is what made
    # an equipment gate in the validator look like a coordinator problem.
    validator = Validator([Validation(False, violation_codes=("EQUIPMENT_NOT_AVAILABLE",))])
    current_input = graph_input(validator=validator, fallback=Fallback(None))

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "FAILED"
    assert result.failure_codes == ("V3_INTEGRITY_EQUIPMENT_NOT_AVAILABLE",)


def test_a_fallback_that_produces_no_plan_says_so() -> None:
    current_input = graph_input(coordinator=Coordinator(timeout=True), fallback=Fallback(None))

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "FAILED"
    assert "V3_COORDINATOR_TIMEOUT" in result.failure_codes
