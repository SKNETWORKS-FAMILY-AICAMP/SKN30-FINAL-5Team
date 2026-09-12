from __future__ import annotations

import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.domain.agents.v3_contracts import PLAN_SPEC_SCHEMA_VERSION, PlanSpec
from backend.app.integrations.llm_agents.coordinator import LangChainCoordinatorAdapter
from backend.app.integrations.llm_agents.models import LlmAgentFailureCode, LlmAgentRoleCode
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.unit.llm_agent_test_support import (
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import OUTSIDE, envelope, pool, prescription
from backend.tests.unit.test_v3_coordinator_contracts import (
    coordinator_input,
    plan,
    proposals,
)


def _adapter(model: ToolCallingFakeChatModel) -> LangChainCoordinatorAdapter:
    return LangChainCoordinatorAdapter(
        invoker=StructuredChatInvoker(chat_model=model, model_code="fake-model-v1")
    )


def test_async_coordinator_boundary_returns_one_plan_spec() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    expected = plan(coordinator_input(current_envelope, current_pool))
    model = ToolCallingFakeChatModel(responses=[tool_response(PlanSpec, expected, 1)])

    result = asyncio.run(
        _adapter(model).acoordinate(
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
            proposals=current_proposals,
        )
    )

    assert result.output == expected
    assert model.invocation_count == 1


def test_coordinator_returns_actual_structured_validated_plan_spec() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    current_input = coordinator_input(current_envelope, current_pool)
    expected = plan(current_input)
    model = ToolCallingFakeChatModel(responses=[tool_response(PlanSpec, expected, 1)])
    adapter = _adapter(model)

    result = adapter.coordinate(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=current_proposals,
    )

    assert result.output == expected
    assert result.output.schema_version == PLAN_SPEC_SCHEMA_VERSION
    # Read the registered version rather than a literal: prompts are versioned
    # independently and a bump should not fail an unrelated behaviour test.
    assert adapter.prompt_version == ROLE_PROMPTS[LlmAgentRoleCode.COORDINATOR].version
    assert adapter.output_schema_version == PLAN_SPEC_SCHEMA_VERSION
    assert model.bound_tool_names == [("PlanSpec",)]
    assert model.invocation_count == 1
    human_message = next(
        message for message in model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    assert isinstance(human_message.content, str)
    prompt_payload = json.loads(human_message.content)
    assert prompt_payload["input"]["schema_version"] == "v3-coordinator-input-v2"
    assert prompt_payload["input"]["mode_code"] == "INITIAL"
    assert [
        item["agent_type_code"] for item in prompt_payload["input"]["specialist_proposals"]
    ] == ["TRAINING", "RECOVERY", "FEASIBILITY"]
    system_message = next(
        message for message in model.seen_messages[0] if isinstance(message, SystemMessage)
    )
    assert isinstance(system_message.content, str)
    assert "sole draft plan" in system_message.content
    assert "advisory perspectives" in system_message.content
    assert "without a fixed precedence" in system_message.content
    assert "valid advisory NEEDS_INPUT" in system_message.content
    assert "ADVISORY_UNAVAILABLE" in system_message.content
    assert "PLAN_EXERCISE_FAMILY_REPEATED" in system_message.content
    assert "family_code" in system_message.content


def test_coordinator_identity_fields_are_derived_from_server_input() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    current_input = coordinator_input(current_envelope, current_pool)
    expected = plan(current_input)
    provider_values = expected.model_dump(mode="json")
    provider_values.update(
        envelope_hash="f" * 64,
        pool_hash="e" * 64,
        requested_duration_minutes=29,
        estimated_duration_seconds=1740,
        proposal_references=list(reversed(provider_values["proposal_references"])),
        repair_attempt=1,
        plan_hash="d" * 64,
    )
    model = ToolCallingFakeChatModel(responses=[tool_response(PlanSpec, provider_values, 1)])
    adapter = _adapter(model)

    result = adapter.coordinate(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=current_proposals,
    )

    assert result.output == expected
    assert result.output.requested_duration_minutes == current_envelope.requested_duration_minutes
    assert result.output.envelope_hash == current_envelope.envelope_hash
    assert result.output.pool_hash == current_pool.pool_hash
    assert result.output.repair_attempt == 0
    assert model.invocation_count == 1


def test_server_owned_identity_does_not_weaken_plan_constraint_validation() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    current_input = coordinator_input(current_envelope, current_pool)
    outside_plan = plan(
        current_input,
        plan_prescriptions=(
            prescription(current_envelope.mandatory_exercise_ids[0], 1, phase_code="WARMUP"),
            prescription(OUTSIDE, 2),
            prescription(current_pool.exercises[-1].exercise_id, 3, phase_code="COOLDOWN"),
        ),
    )
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(PlanSpec, outside_plan, 1),
            tool_response(PlanSpec, outside_plan, 2),
        ]
    )

    result = _adapter(model).coordinate(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=current_proposals,
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.DOMAIN_INVALID
    assert result.failure.attempt_count == 2
    assert model.invocation_count == 2


def test_repair_is_one_structured_call_without_an_adapter_loop() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    repair_codes = ("DURATION_MISMATCH",)
    repair_input = coordinator_input(
        current_envelope,
        current_pool,
        repair_attempt=1,
        repair_codes=repair_codes,
    )
    expected = plan(repair_input)
    model = ToolCallingFakeChatModel(responses=[tool_response(PlanSpec, expected, 1)])
    adapter = _adapter(model)

    result = adapter.repair(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=current_proposals,
        repair_violation_codes=repair_codes,
    )

    assert result.output == expected
    assert model.invocation_count == 1
    human_message = next(
        message for message in model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    assert isinstance(human_message.content, str)
    prompt_payload = json.loads(human_message.content)
    assert prompt_payload["input"]["mode_code"] == "REPAIR"
    assert prompt_payload["input"]["repair_attempt"] == 1
    assert prompt_payload["input"]["repair_violation_codes"] == ["DURATION_MISMATCH"]


def test_coordinator_refuses_missing_specialist_without_calling_provider() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    valid_input = coordinator_input(current_envelope, current_pool)
    model = ToolCallingFakeChatModel(responses=[tool_response(PlanSpec, plan(valid_input), 1)])
    adapter = _adapter(model)

    result = adapter.coordinate(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=current_proposals[:2],
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.DOMAIN_INVALID
    assert result.failure.attempt_count == 0
    assert model.invocation_count == 0
