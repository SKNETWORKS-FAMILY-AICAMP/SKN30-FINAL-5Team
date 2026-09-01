"""Pure conditional-edge routing for the bounded V3 graph."""

from __future__ import annotations

from typing import Literal

from backend.app.integrations.langgraph.state import V3GraphState


def after_entry(state: V3GraphState) -> Literal["parallel_agents", "terminal"]:
    return "terminal" if state.get("entry_failure_code") else "parallel_agents"


def after_agents(state: V3GraphState) -> Literal["coordinator_initial", "fallback"]:
    return "fallback" if state.get("failure_codes") else "coordinator_initial"


def after_validation(
    state: V3GraphState,
) -> Literal["finalize", "coordinator_repair", "fallback"]:
    validation = state.get("integrity_validation")
    if validation is None:
        return "fallback"
    if validation.passed:
        return "finalize"
    if validation.repairable and state.get("repair_attempts", 0) == 0:
        return "coordinator_repair"
    return "fallback"


def after_fallback(state: V3GraphState) -> Literal["compile_fallback", "terminal"]:
    return "compile_fallback" if state.get("fallback_plan_spec") is not None else "terminal"


def after_fallback_validation(state: V3GraphState) -> Literal["finalize", "terminal"]:
    validation = state.get("integrity_validation")
    return "finalize" if validation is not None and validation.passed else "terminal"


def after_compile(state: V3GraphState) -> Literal["validate", "fallback"]:
    return "validate" if state.get("compiled_plan") is not None else "fallback"


def after_fallback_compile(state: V3GraphState) -> Literal["validate_fallback", "terminal"]:
    return "validate_fallback" if state.get("compiled_plan") is not None else "terminal"


__all__ = [
    "after_agents",
    "after_entry",
    "after_compile",
    "after_fallback",
    "after_fallback_compile",
    "after_fallback_validation",
    "after_validation",
]
