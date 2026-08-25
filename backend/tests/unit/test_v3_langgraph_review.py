import asyncio

from backend.app.domain.agents.v3_contracts import SPECIALIST_AGENT_ORDER
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.tests.unit.v3_langgraph_test_support import (
    Conflict,
    ConflictDetector,
    Coordinator,
    Specialist,
    graph_input,
)


def test_no_conflict_does_not_call_review() -> None:
    current_input = graph_input()

    asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert all(port.review_calls == 0 for port in current_input.specialists.values())


def test_only_affected_specialist_is_reviewed_once() -> None:
    affected = SPECIALIST_AGENT_ORDER[1]
    detector = ConflictDetector(
        [
            Conflict(("LOAD_CONFLICT",), (affected,)),
            Conflict(),
        ]
    )
    coordinator = Coordinator()
    current_input = graph_input(detector=detector, coordinator=coordinator)

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "SUCCEEDED"
    assert current_input.specialists[affected].review_calls == 1
    assert sum(port.review_calls for port in current_input.specialists.values()) == 1
    assert detector.calls == 2
    assert coordinator.initial_calls == 1


def test_review_timeout_prevents_coordinator() -> None:
    affected = SPECIALIST_AGENT_ORDER[0]
    detector = ConflictDetector([Conflict(("GOAL_CONFLICT",), (affected,))])
    coordinator = Coordinator()
    current_input = graph_input(detector=detector, coordinator=coordinator, timeout=0.01)
    original = current_input.specialists[affected]
    current_input.specialists[affected] = Specialist(
        affected,
        original.output,
        review_timeout=True,
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.used_fallback
    assert coordinator.initial_calls == 0
