"""Async LLM nodes and deterministic port delegation for V3 orchestration."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    SpecialistAgentInput,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.integrations.langgraph.state import (
    AgentOutcome,
    InvocationAudit,
    V3GraphResult,
    V3GraphState,
)
from backend.app.integrations.llm_agents.models import (
    LlmInvocationTelemetry,
    StructuredAgentResult,
)


def _append_failure(state: V3GraphState, code: str) -> tuple[str, ...]:
    return tuple(sorted({*state.get("failure_codes", ()), code}))


def _invocation_audit(
    *,
    role_code: str,
    phase_code: str,
    result: StructuredAgentResult[Any],
) -> InvocationAudit:
    telemetry = result.telemetry
    failure = result.failure
    if failure is None:
        status = "SUCCEEDED"
        failure_code = None
        attempt_count = telemetry.attempt_count if telemetry is not None else 1
    else:
        if failure.code.value.endswith("TIMEOUT"):
            status = "TIMEOUT"
        elif failure.code.value.endswith(("SCHEMA_INVALID", "DOMAIN_INVALID")):
            status = "INVALID_OUTPUT"
        else:
            status = "FAILED"
        failure_code = failure.code.value
        attempt_count = failure.attempt_count
    return InvocationAudit(
        role_code=role_code,
        phase_code=phase_code,
        status_code=status,
        attempt_count=attempt_count,
        latency_ms=telemetry.latency_ms if telemetry is not None else 0,
        input_token_count=telemetry.input_token_count if telemetry is not None else None,
        output_token_count=telemetry.output_token_count if telemetry is not None else None,
        provider_usage_present=(
            telemetry.provider_usage_present if telemetry is not None else False
        ),
        failure_code=failure_code,
    )


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
        outcome = AgentOutcome(
            agent_type,
            failure_code=f"V3_{agent_type.value}_TIMEOUT",
            telemetry=LlmInvocationTelemetry(
                attempt_count=1,
                latency_ms=max(0, int(graph_input.node_timeout_seconds * 1000)),
            ),
        )
    except Exception:
        outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_FAILED")
    else:
        if result.failure is not None:
            outcome = AgentOutcome(
                agent_type, failure_code=result.failure.code.value, telemetry=result.telemetry
            )
        elif (
            result.output is None
            or result.output.proposal_status_code is not V3ProposalStatusCode.READY
            or not _proposal_is_valid(state, agent_type, result.output)
        ):
            outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_NOT_READY")
        else:
            outcome = AgentOutcome(agent_type, proposal=result.output, telemetry=result.telemetry)
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
    audits = tuple(
        InvocationAudit(
            role_code=outcome.agent_type.value,
            phase_code="PROPOSE",
            status_code=(
                "SUCCEEDED"
                if outcome.proposal is not None
                else ("TIMEOUT" if (outcome.failure_code or "").endswith("TIMEOUT") else "FAILED")
            ),
            attempt_count=(outcome.telemetry.attempt_count if outcome.telemetry else 0),
            latency_ms=(outcome.telemetry.latency_ms if outcome.telemetry else 0),
            input_token_count=(outcome.telemetry.input_token_count if outcome.telemetry else None),
            output_token_count=(
                outcome.telemetry.output_token_count if outcome.telemetry else None
            ),
            provider_usage_present=(
                outcome.telemetry.provider_usage_present if outcome.telemetry else False
            ),
            failure_code=outcome.failure_code,
        )
        for outcome in (by_role[role] for role in SPECIALIST_AGENT_ORDER if role in by_role)
    )
    return {
        "proposals": tuple(proposals),
        "round_one_proposals": tuple(proposals),
        "failure_codes": tuple(sorted(set(failures))),
        "invocation_audits": audits,
    }


def detect_conflicts(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    try:
        report = graph_input.conflict_detector.detect(state["proposals"])
    except Exception:
        return {"failure_codes": _append_failure(state, "V3_CONFLICT_DETECTION_FAILED")}
    return {"conflict_report": report, "initial_conflict_report": report}


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
        outcome = AgentOutcome(
            agent_type,
            failure_code=f"V3_{agent_type.value}_REVIEW_TIMEOUT",
            telemetry=LlmInvocationTelemetry(
                attempt_count=1,
                latency_ms=max(0, int(graph_input.node_timeout_seconds * 1000)),
            ),
        )
    except Exception:
        outcome = AgentOutcome(agent_type, failure_code=f"V3_{agent_type.value}_REVIEW_FAILED")
    else:
        if result.failure is not None:
            outcome = AgentOutcome(
                agent_type, failure_code=result.failure.code.value, telemetry=result.telemetry
            )
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
            outcome = AgentOutcome(agent_type, proposal=result.output, telemetry=result.telemetry)
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
    audits = tuple(
        InvocationAudit(
            role_code=outcome.agent_type.value,
            phase_code="REVIEW",
            status_code=(
                "SUCCEEDED"
                if outcome.proposal is not None
                else ("TIMEOUT" if (outcome.failure_code or "").endswith("TIMEOUT") else "FAILED")
            ),
            attempt_count=(outcome.telemetry.attempt_count if outcome.telemetry else 0),
            latency_ms=(outcome.telemetry.latency_ms if outcome.telemetry else 0),
            input_token_count=(outcome.telemetry.input_token_count if outcome.telemetry else None),
            output_token_count=(
                outcome.telemetry.output_token_count if outcome.telemetry else None
            ),
            provider_usage_present=(
                outcome.telemetry.provider_usage_present if outcome.telemetry else False
            ),
            failure_code=outcome.failure_code,
        )
        for outcome in sorted(
            state.get("review_outcomes", ()),
            key=lambda item: SPECIALIST_AGENT_ORDER.index(item.agent_type),
        )
    )
    if failures:
        return {"failure_codes": tuple(sorted(set(failures))), "invocation_audits": audits}
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
        "invocation_audits": audits,
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
        return {
            "failure_codes": ("V3_COORDINATOR_TIMEOUT",),
            "plan_spec": None,
            "invocation_audits": (
                InvocationAudit(
                    role_code="COORDINATOR",
                    phase_code="COORDINATE",
                    status_code="TIMEOUT",
                    attempt_count=1,
                    latency_ms=max(0, int(graph_input.node_timeout_seconds * 1000)),
                    failure_code="V3_COORDINATOR_TIMEOUT",
                ),
            ),
        }
    except Exception:
        return {"failure_codes": ("V3_COORDINATOR_FAILED",), "plan_spec": None}
    audit = _invocation_audit(role_code="COORDINATOR", phase_code="COORDINATE", result=result)
    if result.failure is not None:
        return {
            "failure_codes": (result.failure.code.value,),
            "plan_spec": None,
            "invocation_audits": (audit,),
        }
    return {
        "plan_spec": result.output,
        "coordinator_initial_plan": result.output,
        "invocation_audits": (audit,),
    }


def compile_plan(state: V3GraphState) -> dict[str, object]:
    plan_spec = state.get("plan_spec") or state.get("fallback_plan_spec")
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
    return {
        "integrity_validation": validation,
        "integrity_validations": (validation,),
        "compiled_plans": (compiled_plan,),
    }


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
            "invocation_audits": (
                InvocationAudit(
                    role_code="COORDINATOR",
                    phase_code="REPAIR",
                    status_code="TIMEOUT",
                    attempt_count=1,
                    latency_ms=max(0, int(graph_input.node_timeout_seconds * 1000)),
                    failure_code="V3_COORDINATOR_REPAIR_TIMEOUT",
                ),
            ),
        }
    except Exception:
        return {
            "failure_codes": ("V3_COORDINATOR_REPAIR_FAILED",),
            "plan_spec": None,
            "repair_attempts": 1,
        }
    audit = _invocation_audit(role_code="COORDINATOR", phase_code="REPAIR", result=result)
    if result.failure is not None:
        return {
            "failure_codes": (result.failure.code.value,),
            "plan_spec": None,
            "repair_attempts": 1,
            "invocation_audits": (audit,),
        }
    return {
        "plan_spec": result.output,
        "compiled_plan": None,
        "repair_attempts": 1,
        "coordinator_repair_plan": result.output,
        "invocation_audits": (audit,),
    }


def fallback(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    action = graph_input.constraint_envelope.safety_required_action_code
    if action in {SafetyRequiredActionCode.REST, SafetyRequiredActionCode.STOP_AND_SEEK_HELP}:
        return {"plan_spec": None}
    try:
        fallback_plan_spec = graph_input.fallback.build(
            constraint_envelope=graph_input.constraint_envelope,
            exercise_pool=graph_input.exercise_pool,
            failure_codes=state.get("failure_codes", ()),
        )
    except Exception:
        return {
            "plan_spec": None,
            "fallback_plan_spec": None,
            "failure_codes": _append_failure(state, "V3_FALLBACK_FAILED"),
            "used_fallback": True,
        }
    return {
        "plan_spec": None,
        "fallback_plan_spec": fallback_plan_spec,
        "compiled_plan": None,
        "used_fallback": True,
    }


def finalize(state: V3GraphState) -> dict[str, object]:
    graph_input = state["graph_input"]
    plan_spec = state.get("plan_spec")
    compiled_plan = state.get("compiled_plan")
    failure_codes = state.get("failure_codes", ())
    fallback_plan_spec = state.get("fallback_plan_spec")
    if (plan_spec is None and fallback_plan_spec is None) or compiled_plan is None:
        return terminal(state)
    context = graph_input.regeneration_context
    if context is not None and plan_spec is None:
        return terminal(
            {
                **state,
                "failure_codes": _append_failure(state, "V3_REGENERATION_FALLBACK_NOT_DIFFERENT"),
            }
        )
    if context is not None and plan_spec is not None:
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
                round_one_proposals=state.get("round_one_proposals", ()),
                conflict_report=state.get("initial_conflict_report"),
                review_outcomes=state.get("review_outcomes", ()),
                coordinator_initial_plan=state.get("coordinator_initial_plan"),
                coordinator_repair_plan=state.get("coordinator_repair_plan"),
                integrity_validations=state.get("integrity_validations", ()),
                compiled_plans=state.get("compiled_plans", ()),
                invocation_audits=state.get("invocation_audits", ()),
                fallback_plan_spec=state.get("fallback_plan_spec"),
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
        round_one_proposals=state.get("round_one_proposals", ()),
        conflict_report=state.get("initial_conflict_report"),
        review_outcomes=state.get("review_outcomes", ()),
        coordinator_initial_plan=state.get("coordinator_initial_plan"),
        coordinator_repair_plan=state.get("coordinator_repair_plan"),
        integrity_validations=state.get("integrity_validations", ()),
        compiled_plans=state.get("compiled_plans", ()),
        invocation_audits=state.get("invocation_audits", ()),
        fallback_plan_spec=state.get("fallback_plan_spec"),
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
        round_one_proposals=state.get("round_one_proposals", ()),
        conflict_report=state.get("initial_conflict_report"),
        review_outcomes=state.get("review_outcomes", ()),
        coordinator_initial_plan=state.get("coordinator_initial_plan"),
        coordinator_repair_plan=state.get("coordinator_repair_plan"),
        integrity_validations=state.get("integrity_validations", ()),
        compiled_plans=state.get("compiled_plans", ()),
        invocation_audits=state.get("invocation_audits", ()),
        fallback_plan_spec=state.get("fallback_plan_spec"),
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
