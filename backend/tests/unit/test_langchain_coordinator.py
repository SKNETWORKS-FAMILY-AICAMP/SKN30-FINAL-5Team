from __future__ import annotations

import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.domain.agents.v3_contracts import PLAN_SPEC_SCHEMA_VERSION, PlanSpec
from backend.app.integrations.llm_agents.coordinator import LangChainCoordinatorAdapter
from backend.app.integrations.llm_agents.models import LlmAgentFailureCode
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.unit.llm_agent_test_support import (
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import envelope, pool
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
    assert adapter.prompt_version == "v3-coordinator-prompt-v4"
    assert adapter.output_schema_version == PLAN_SPEC_SCHEMA_VERSION
    assert model.bound_tool_names == [("PlanSpec",)]
    assert model.invocation_count == 1
    human_message = next(
        message for message in model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    assert isinstance(human_message.content, str)
    prompt_payload = json.loads(human_message.content)
    assert prompt_payload["input"]["schema_version"] == "v3-coordinator-input-v1"
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


def test_coordinator_cannot_relax_envelope_constraints() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    current_input = coordinator_input(current_envelope, current_pool)
    changed = plan(current_input, requested_duration_minutes=29)
    model = ToolCallingFakeChatModel(responses=[tool_response(PlanSpec, changed, 1)])
    adapter = _adapter(model)

    result = adapter.coordinate(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        proposals=current_proposals,
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.DOMAIN_INVALID
    assert result.failure.attempt_count == 1
    assert model.invocation_count == 1


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
