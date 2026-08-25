import asyncio

from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.tests.unit.v3_langgraph_test_support import (
    Coordinator,
    Validation,
    Validator,
    graph_input,
)


def test_repairable_violation_repairs_exactly_once() -> None:
    validator = Validator([Validation(False, True, ("DURATION_MISMATCH",)), Validation(True)])
    coordinator = Coordinator()
    current_input = graph_input(validator=validator, coordinator=coordinator)

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "SUCCEEDED"
    assert result.repair_attempts == 1
    assert coordinator.repair_calls == 1
    assert validator.calls == 2


def test_repair_failure_does_not_start_second_repair() -> None:
    validator = Validator([Validation(False, True, ("DURATION_MISMATCH",))])
    coordinator = Coordinator()
    current_input = graph_input(validator=validator, coordinator=coordinator)

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.used_fallback
    assert coordinator.repair_calls == 1


def test_non_repairable_violation_skips_repair() -> None:
    validator = Validator([Validation(False, False, ("SAFETY_EXCLUSION_VIOLATED",))])
    coordinator = Coordinator()
    current_input = graph_input(validator=validator, coordinator=coordinator)

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.used_fallback
    assert coordinator.repair_calls == 0
