"""Async LLM nodes and deterministic port delegation for V3 orchestration."""

from __future__ import annotations

import asyncio

from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    SpecialistAgentInput,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.integrations.langgraph.state import AgentOutcome, V3GraphResult, V3GraphState


def _append_failure(state: V3GraphState, code: str) -> tuple[str, ...]:
    return tuple(sorted({*state.get("failure_codes", ()), code}))


def _proposal_is_valid(
    state: V3GraphState,
    agent_type: SpecialistAgentTypeCode,
    proposal: SpecialistAgentProposal,
) -> bool:
    graph_input = state["graph_input"]
    try:
        agent_input = SpecialistAgentInput(
            agent_type_code=agent_type,
            constraint_envelope=graph_input.constraint_envelope,
            envelope_hash=graph_input.constraint_envelope.envelope_hash,
            exercise_pool=graph_input.exercise_pool,
            pool_hash=graph_input.exercise_pool.pool_hash,
            regeneration_context=graph_input.regeneration_context,
        )
        agent_input.validate_proposal(proposal)
    except (ValueError, TypeError):
        return False
    return True


def validate_entry(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    envelope = graph_input.constraint_envelope
    pool = graph_input.exercise_pool
    failure_code: str | None = None

    if not envelope.plan_generation_allowed:
        action = envelope.safety_required_action_code
        failure_code = action.value if action is not None else "PLAN_GENERATION_FORBIDDEN"
    elif envelope.safety_required_action_code in {
        SafetyRequiredActionCode.REST,
        SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
    }:
        failure_code = envelope.safety_required_action_code.value
    elif not graph_input.snapshot_is_fresh:
        failure_code = "V3_INPUT_STALE"
    elif pool.constraint_envelope_hash != envelope.envelope_hash:
        failure_code = "V3_ENVELOPE_POOL_HASH_MISMATCH"
    elif graph_input.catalog_version != envelope.catalog_version:
        failure_code = "V3_CATALOG_VERSION_MISMATCH"
    elif graph_input.catalog_version != pool.catalog_version:
        failure_code = "V3_POOL_CATALOG_VERSION_MISMATCH"
    elif graph_input.policy_version != envelope.policy_version:
        failure_code = "V3_POLICY_VERSION_MISMATCH"
    elif (
        graph_input.regeneration_context is not None
        and graph_input.regeneration_context.generation_sequence not in {1, 2}
    ):
        failure_code = "REGENERATION_LIMIT_REACHED"
    elif set(graph_input.specialists) != set(SPECIALIST_AGENT_ORDER):
        failure_code = "V3_SPECIALIST_PORTS_INCOMPLETE"
    elif graph_input.node_timeout_seconds <= 0:
        failure_code = "V3_TIMEOUT_CONFIG_INVALID"

    if failure_code is None:
        return {"repair_attempts": 0, "failure_codes": (), "used_fallback": False}
    return {
        "entry_failure_code": failure_code,
        "failure_codes": (failure_code,),
        "repair_attempts": 0,
        "used_fallback": False,
    }


async def _run_specialist(
    state: V3GraphState,
    agent_type: SpecialistAgentTypeCode,
) -> dict[str, object]:
    graph_input = state["graph_input"]
    try:
        async with asyncio.timeout(graph_input.node_timeout_seconds):
            result = await graph_input.specialists[agent_type].apropose(
                constraint_envelope=graph_input.constraint_envelope,
                exercise_pool=graph_input.exercise_pool,
                regeneration_context=graph_input.regeneration_context,
            )
    except TimeoutError:
        outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_TIMEOUT")
    except Exception:
        outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_FAILED")
    else:
        if result.failure is not None:
            outcome = AgentOutcome(agent_type, failure_code=result.failure.code.value)
        elif (
            result.output is None
            or result.output.proposal_status_code is not V3ProposalStatusCode.READY
            or not _proposal_is_valid(state, agent_type, result.output)
        ):
            outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_NOT_READY")
        else:
            outcome = AgentOutcome(agent_type, proposal=result.output)
    return {"agent_outcomes": (outcome,)}


async def training_agent(state: V3GraphState) -> dict[str, object]:
    return await _run_specialist(state, SpecialistAgentTypeCode.TRAINING)


async def recovery_agent(state: V3GraphState) -> dict[str, object]:
    return await _run_specialist(state, SpecialistAgentTypeCode.RECOVERY)


async def feasibility_agent(state: V3GraphState) -> dict[str, object]:
    return await _run_specialist(state, SpecialistAgentTypeCode.FEASIBILITY)


def parallel_agents(state: V3GraphState) -> dict[str, object]:
    del state
    return {"agent_outcomes": ()}


def canonicalize_agents(state: V3GraphState) -> dict[str, object]:
    by_role = {outcome.agent_type: outcome for outcome in state.get("agent_outcomes", ())}
    failures: list[str] = []
    proposals: list[SpecialistAgentProposal] = []
    for agent_type in SPECIALIST_AGENT_ORDER:
        outcome = by_role.get(agent_type)
        if outcome is None:
            failures.append(f"V3_{agent_type.value}_MISSING")
        elif outcome.failure_code is not None:
            failures.append(outcome.failure_code)
        elif outcome.proposal is not None:
            proposals.append(outcome.proposal)
    return {
        "proposals": tuple(proposals),
        "failure_codes": tuple(sorted(set(failures))),
    }


def detect_conflicts(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    try:
        report = graph_input.conflict_detector.detect(state["proposals"])
    except Exception:
        return {"failure_codes": _append_failure(state, "V3_CONFLICT_DETECTION_FAILED")}
    return {"conflict_report": report}


def optional_reviews(state: V3GraphState) -> dict[str, object]:
    del state
    return {"review_outcomes": ()}


async def _run_review(
    state: V3GraphState,
    agent_type: SpecialistAgentTypeCode,
) -> dict[str, object]:
    graph_input = state["graph_input"]
    report = state["conflict_report"]
    if agent_type not in report.affected_agent_types:
        return {"review_outcomes": ()}
    original = next(item for item in state["proposals"] if item.agent_type_code is agent_type)
    try:
        async with asyncio.timeout(graph_input.node_timeout_seconds):
            result = await graph_input.specialists[agent_type].areview(
                proposal=original,
                proposals=state["proposals"],
                conflict_codes=report.conflict_codes,
                constraint_envelope=graph_input.constraint_envelope,
                exercise_pool=graph_input.exercise_pool,
            )
    except TimeoutError:
        outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_REVIEW_TIMEOUT")
    except Exception:
        outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_REVIEW_FAILED")
    else:
        if result.failure is not None:
            outcome = AgentOutcome(agent_type, failure_code=result.failure.code.value)
        elif (
            result.output is None
            or result.output.proposal_status_code is not V3ProposalStatusCode.READY
            or not _proposal_is_valid(state, agent_type, result.output)
        ):
            outcome = AgentOutcome(
                agent_type,
                failure_code=f"V3_{agent_type.value}_REVIEW_NOT_READY",
            )
        else:
            outcome = AgentOutcome(agent_type, proposal=result.output)
    return {"review_outcomes": (outcome,)}


async def review_training(state: V3GraphState) -> dict[str, object]:
    return await _run_review(state, SpecialistAgentTypeCode.TRAINING)


async def review_recovery(state: V3GraphState) -> dict[str, object]:
    return await _run_review(state, SpecialistAgentTypeCode.RECOVERY)


async def review_feasibility(state: V3GraphState) -> dict[str, object]:
    return await _run_review(state, SpecialistAgentTypeCode.FEASIBILITY)


def finalize_reviews(state: V3GraphState) -> dict[str, object]:
    replacements: dict[SpecialistAgentTypeCode, SpecialistAgentProposal] = {}
    failures: list[str] = []
    for outcome in state.get("review_outcomes", ()):
        if outcome.failure_code is not None:
            failures.append(outcome.failure_code)
        elif outcome.proposal is not None:
            replacements[outcome.agent_type] = outcome.proposal
    if failures:
        return {"failure_codes": tuple(sorted(set(failures)))}
    proposals = tuple(replacements.get(item.agent_type_code, item) for item in state["proposals"])
    try:
        report = state["graph_input"].conflict_detector.detect(proposals)
    except Exception:
        return {"failure_codes": ("V3_CONFLICT_RECHECK_FAILED",), "proposals": proposals}
    failures = ["V3_REVIEW_HARD_CONSTRAINT_WEAKENED"] if report.hard_constraint_weakened else []
    return {
        "proposals": proposals,
        "conflict_report": report,
        "failure_codes": tuple(failures),
    }


async def coordinator_initial(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    try:
        async with asyncio.timeout(graph_input.node_timeout_seconds):
            result = await graph_input.coordinator.acoordinate(
                constraint_envelope=graph_input.constraint_envelope,
                exercise_pool=graph_input.exercise_pool,
                proposals=state["proposals"],
            )
    except TimeoutError:
        return {"failure_codes": ("V3_COORDINATOR_TIMEOUT",), "plan_spec": None}
    except Exception:
        return {"failure_codes": ("V3_COORDINATOR_FAILED",), "plan_spec": None}
    if result.failure is not None:
        return {"failure_codes": (result.failure.code.value,), "plan_spec": None}
    return {"plan_spec": result.output}


def compile_plan(state: V3GraphState) -> dict[str, object]:
    plan_spec = state.get("plan_spec")
    if plan_spec is None:
        return {"failure_codes": _append_failure(state, "V3_PLAN_SPEC_MISSING")}
    try:
        compiled = state["graph_input"].compiler.compile(plan_spec)
    except Exception:
        return {"failure_codes": _append_failure(state, "V3_COMPILATION_FAILED")}
    return {"compiled_plan": compiled}


def validate_plan(state: V3GraphState) -> dict[str, object]:
    compiled_plan = state.get("compiled_plan")
    if compiled_plan is None:
        return {"failure_codes": _append_failure(state, "V3_COMPILED_PLAN_MISSING")}
    graph_input = state["graph_input"]
    try:
        validation = graph_input.validator.validate(
            compiled_plan,
            constraint_envelope=graph_input.constraint_envelope,
            exercise_pool=graph_input.exercise_pool,
        )
    except Exception:
        return {"failure_codes": _append_failure(state, "V3_VALIDATION_FAILED")}
    return {"integrity_validation": validation}


async def coordinator_repair(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    violation_codes = tuple(sorted(state["integrity_validation"].violation_codes))
    try:
        async with asyncio.timeout(graph_input.node_timeout_seconds):
            result = await graph_input.coordinator.arepair(
                constraint_envelope=graph_input.constraint_envelope,
                exercise_pool=graph_input.exercise_pool,
                proposals=state["proposals"],
                repair_violation_codes=violation_codes,
            )
    except TimeoutError:
        return {
            "failure_codes": ("V3_COORDINATOR_REPAIR_TIMEOUT",),
            "plan_spec": None,
            "repair_attempts": 1,
        }
    except Exception:
        return {
            "failure_codes": ("V3_COORDINATOR_REPAIR_FAILED",),
            "plan_spec": None,
            "repair_attempts": 1,
        }
    if result.failure is not None:
        return {
            "failure_codes": (result.failure.code.value,),
            "plan_spec": None,
            "repair_attempts": 1,
        }
    return {"plan_spec": result.output, "compiled_plan": None, "repair_attempts": 1}


def fallback(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    action = graph_input.constraint_envelope.safety_required_action_code
    if action in {SafetyRequiredActionCode.REST, SafetyRequiredActionCode.STOP_AND_SEEK_HELP}:
        return {"plan_spec": None}
    try:
        plan_spec = graph_input.fallback.build(
            constraint_envelope=graph_input.constraint_envelope,
            exercise_pool=graph_input.exercise_pool,
            failure_codes=state.get("failure_codes", ()),
        )
    except Exception:
        return {
            "plan_spec": None,
            "failure_codes": _append_failure(state, "V3_FALLBACK_FAILED"),
            "used_fallback": True,
        }
    return {"plan_spec": plan_spec, "compiled_plan": None, "used_fallback": True}


def finalize(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    plan_spec = state.get("plan_spec")
    compiled_plan = state.get("compiled_plan")
    failure_codes = state.get("failure_codes", ())
    if plan_spec is None or compiled_plan is None:
        return terminal(state)
    context = graph_input.regeneration_context
    if context is not None:
        try:
            different = graph_input.meaningful_difference_validator.validate(plan_spec, context)
        except Exception:
            different = False
        if plan_spec.plan_hash == context.previous_plan_hash or not different:
            result = V3GraphResult(
                status_code="NO_ALTERNATIVE_AVAILABLE",
                graph_version=graph_input.graph_version,
                plan_spec=None,
                compiled_plan=None,
                failure_codes=tuple(sorted({*failure_codes, "V3_REGENERATION_DUPLICATE"})),
                used_fallback=state.get("used_fallback", False),
                repair_attempts=state.get("repair_attempts", 0),
            )
            return {"result": result}
    result = V3GraphResult(
        status_code="SUCCEEDED",
        graph_version=graph_input.graph_version,
        plan_spec=plan_spec,
        compiled_plan=compiled_plan,
        failure_codes=failure_codes,
        used_fallback=state.get("used_fallback", False),
        repair_attempts=state.get("repair_attempts", 0),
    )
    return {"result": result}


def terminal(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    action = graph_input.constraint_envelope.safety_required_action_code
    status = action.value if action is not None else state.get("entry_failure_code", "FAILED")
    result = V3GraphResult(
        status_code=status,
        graph_version=graph_input.graph_version,
        plan_spec=None,
        compiled_plan=None,
        failure_codes=state.get("failure_codes", ()),
        used_fallback=state.get("used_fallback", False),
        repair_attempts=state.get("repair_attempts", 0),
    )
    return {"result": result}


__all__ = [
    "canonicalize_agents",
    "compile_plan",
    "coordinator_initial",
    "coordinator_repair",
    "detect_conflicts",
    "fallback",
    "feasibility_agent",
    "finalize",
    "finalize_reviews",
    "optional_reviews",
    "parallel_agents",
    "recovery_agent",
    "review_feasibility",
    "review_recovery",
    "review_training",
    "terminal",
    "training_agent",
    "validate_entry",
    "validate_plan",
]
