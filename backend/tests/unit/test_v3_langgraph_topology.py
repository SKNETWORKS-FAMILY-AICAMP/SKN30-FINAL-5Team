import asyncio

from backend.app.core.config import Settings
from backend.app.integrations.langgraph.graph import (
    build_v3_langgraph_runtime,
    create_v3_graph,
)
from backend.tests.unit.v3_langgraph_test_support import graph_input


def test_graph_has_required_bounded_topology_without_persistence() -> None:
    graph = create_v3_graph()
    drawable = graph.get_graph()

    assert {
        "validate_entry",
        "parallel_agents",
        "detect_conflicts",
        "optional_reviews",
        "coordinator_initial",
        "compile",
        "validate",
        "coordinator_repair",
        "compile_repair",
        "validate_repair",
        "fallback",
        "finalize",
    }.issubset(drawable.nodes)
    assert graph.checkpointer is False
    assert graph.store is None


def test_runtime_is_not_built_when_feature_flag_is_false() -> None:
    settings = Settings(app_env="test", v3_langgraph_enabled=False)

    assert build_v3_langgraph_runtime(settings) is None


def test_stale_entry_terminates_before_any_llm_call() -> None:
    current_input = graph_input(snapshot_is_fresh=False)

    result = asyncio.run(create_v3_graph().ainvoke({"graph_input": current_input}))

    assert result["result"].status_code == "V3_INPUT_STALE"
    assert all(port.propose_calls == 0 for port in current_input.specialists.values())
    assert current_input.coordinator.initial_calls == 0
