"""Stateless LangGraph assembly for Safety-first V3 orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.core.config import Settings
from backend.app.integrations.langgraph import nodes
from backend.app.integrations.langgraph.routing import (
    after_agents,
    after_compile,
    after_conflicts,
    after_entry,
    after_fallback,
    after_fallback_compile,
    after_fallback_validation,
    after_reviews,
    after_validation,
)
from backend.app.integrations.langgraph.state import V3GraphInput, V3GraphResult, V3GraphState


def create_v3_graph() -> CompiledStateGraph:
    """Build a stateless graph with bounded parallel and repair paths."""

    builder = StateGraph(V3GraphState)
    builder.add_node("validate_entry", nodes.validate_entry)
    builder.add_node("parallel_agents", nodes.parallel_agents)
    builder.add_node("agent_training", nodes.training_agent)
    builder.add_node("agent_recovery", nodes.recovery_agent)
    builder.add_node("agent_feasibility", nodes.feasibility_agent)
    builder.add_node("canonicalize_agents", nodes.canonicalize_agents)
    builder.add_node("detect_conflicts", nodes.detect_conflicts)
    builder.add_node("optional_reviews", nodes.optional_reviews)
    builder.add_node("review_training", nodes.review_training)
    builder.add_node("review_recovery", nodes.review_recovery)
    builder.add_node("review_feasibility", nodes.review_feasibility)
    builder.add_node("finalize_reviews", nodes.finalize_reviews)
    builder.add_node("coordinator_initial", nodes.coordinator_initial)
    builder.add_node("compile", nodes.compile_plan)
    builder.add_node("validate", nodes.validate_plan)
    builder.add_node("coordinator_repair", nodes.coordinator_repair)
    builder.add_node("compile_repair", nodes.compile_plan)
    builder.add_node("validate_repair", nodes.validate_plan)
    builder.add_node("fallback", nodes.fallback)
    builder.add_node("compile_fallback", nodes.compile_plan)
    builder.add_node("validate_fallback", nodes.validate_plan)
    builder.add_node("finalize", nodes.finalize)
    builder.add_node("terminal", nodes.terminal)

    builder.add_edge(START, "validate_entry")
    builder.add_conditional_edges("validate_entry", after_entry)
    builder.add_edge("parallel_agents", "agent_training")
    builder.add_edge("parallel_agents", "agent_recovery")
    builder.add_edge("parallel_agents", "agent_feasibility")
    builder.add_edge(
        ["agent_training", "agent_recovery", "agent_feasibility"],
        "canonicalize_agents",
    )
    builder.add_conditional_edges("canonicalize_agents", after_agents)
    builder.add_conditional_edges("detect_conflicts", after_conflicts)
    builder.add_edge("optional_reviews", "review_training")
    builder.add_edge("optional_reviews", "review_recovery")
    builder.add_edge("optional_reviews", "review_feasibility")
    builder.add_edge(
        ["review_training", "review_recovery", "review_feasibility"],
        "finalize_reviews",
    )
    builder.add_conditional_edges("finalize_reviews", after_reviews)
    builder.add_edge("coordinator_initial", "compile")
    builder.add_conditional_edges(
        "compile",
        after_compile,
        {"validate": "validate", "fallback": "fallback"},
    )
    builder.add_conditional_edges("validate", after_validation)
    builder.add_edge("coordinator_repair", "compile_repair")
    builder.add_conditional_edges(
        "compile_repair",
        after_compile,
        {"validate": "validate_repair", "fallback": "fallback"},
    )
    builder.add_conditional_edges("validate_repair", after_validation)
    builder.add_conditional_edges("fallback", after_fallback)
    builder.add_conditional_edges("compile_fallback", after_fallback_compile)
    builder.add_conditional_edges("validate_fallback", after_fallback_validation)
    builder.add_edge("finalize", END)
    builder.add_edge("terminal", END)

    # False opts out of parent checkpoint inheritance as well as persistence.
    return builder.compile(checkpointer=False)


@dataclass(frozen=True, slots=True)
class V3LangGraphRuntime:
    graph: CompiledStateGraph

    async def ainvoke(self, graph_input: V3GraphInput) -> V3GraphResult:
        final_state = await self.graph.ainvoke(
            {
                "graph_input": graph_input,
                "agent_outcomes": (),
                "review_outcomes": (),
                "invocation_audits": (),
                "integrity_validations": (),
            },
            config={"callbacks": [], "max_concurrency": 3},
        )
        result = final_state.get("result")
        if not isinstance(result, V3GraphResult):
            raise RuntimeError("V3 graph terminated without a sanitized result")
        return result


def build_v3_langgraph_runtime(settings: Settings) -> V3LangGraphRuntime | None:
    """Keep graph construction and all provider calls disabled by default."""

    if not settings.v3_langgraph_enabled:
        return None
    return V3LangGraphRuntime(graph=create_v3_graph())


__all__ = ["V3LangGraphRuntime", "build_v3_langgraph_runtime", "create_v3_graph"]
