from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from backend.app.core.config import Settings
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.llm_agents.models import LlmAgentFailureCode
from backend.app.integrations.llm_agents.provider import (
    StructuredChatInvoker,
    build_structured_chat_invoker,
)
from backend.app.integrations.llm_agents.specialists import (
    FeasibilityAgentAdapter,
    RecoveryAgentAdapter,
    TrainingAgentAdapter,
)
from backend.tests.unit.llm_agent_test_support import (
    RaisingStructuredChatModel,
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import (
    OUTSIDE,
    envelope,
    pool,
    prescription,
    proposal,
)


def _adapter(adapter_type: type, model: object) -> object:
    return adapter_type(invoker=StructuredChatInvoker(chat_model=model, model_code="fake-model-v1"))


@pytest.mark.parametrize(
    ("adapter_type", "agent_type"),
    [
        (TrainingAgentAdapter, SpecialistAgentTypeCode.TRAINING),
        (RecoveryAgentAdapter, SpecialistAgentTypeCode.RECOVERY),
        (FeasibilityAgentAdapter, SpecialistAgentTypeCode.FEASIBILITY),
    ],
)
def test_each_specialist_uses_actual_structured_contract_and_versioned_role_prompt(
    adapter_type: type,
    agent_type: SpecialistAgentTypeCode,
) -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    expected = proposal(agent_type, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(
        responses=[tool_response(SpecialistAgentProposal, expected, 1)]
    )
    adapter = _adapter(adapter_type, model)

    result = adapter.propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.succeeded
    assert result.output == expected
    assert result.output.schema_version == SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION
    assert adapter.prompt_version == f"v3-{agent_type.value.lower()}-prompt-v1"
    assert adapter.output_schema_version == SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION
    assert model.bound_tool_names == [("SpecialistAgentProposal",)]
    assert model.invocation_count == 1
    human_message = next(
        message for message in model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    assert isinstance(human_message.content, str)
    prompt_payload = json.loads(human_message.content)
    assert prompt_payload["prompt_version"] == adapter.prompt_version
    assert prompt_payload["output_schema_version"] == SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION
    assert prompt_payload["input"]["agent_type_code"] == agent_type.value
    assert prompt_payload["input"]["schema_version"] == "specialist-agent-input-v1"


def test_three_roles_can_share_one_provider_neutral_model_and_invoker() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    roles = tuple(SpecialistAgentTypeCode)
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(
                SpecialistAgentProposal,
                proposal(role, current_envelope, current_pool),
                index,
            )
            for index, role in enumerate(roles, start=1)
        ]
    )
    shared_invoker = StructuredChatInvoker(chat_model=model, model_code="fake-model-v1")
    adapters = (
        TrainingAgentAdapter(invoker=shared_invoker),
        RecoveryAgentAdapter(invoker=shared_invoker),
        FeasibilityAgentAdapter(invoker=shared_invoker),
    )

    results = tuple(
        adapter.propose(
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
        for adapter in adapters
    )

    assert all(result.succeeded for result in results)
    assert tuple(result.output.agent_type_code for result in results) == roles
    assert model.invocation_count == 3


def test_specialist_rejects_exercise_id_outside_pool_without_retry() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    outside = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(OUTSIDE, 1),),
    )
    model = ToolCallingFakeChatModel(responses=[tool_response(SpecialistAgentProposal, outside, 1)])
    adapter = _adapter(TrainingAgentAdapter, model)

    result = adapter.propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.DOMAIN_INVALID
    assert result.failure.attempt_count == 1
    assert model.invocation_count == 1


def test_schema_invalid_output_is_retried_once_then_succeeds() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    expected = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    invalid = {"schema_version": SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION}
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(SpecialistAgentProposal, invalid, 1),
            tool_response(SpecialistAgentProposal, expected, 2),
        ]
    )
    adapter = _adapter(TrainingAgentAdapter, model)

    result = adapter.propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.output == expected
    assert model.invocation_count == 2


def test_second_schema_failure_returns_canonical_failure() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    invalid = {"schema_version": SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION}
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(SpecialistAgentProposal, invalid, 1),
            tool_response(SpecialistAgentProposal, invalid, 2),
        ]
    )
    adapter = _adapter(TrainingAgentAdapter, model)

    result = adapter.propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.SCHEMA_INVALID
    assert result.failure.attempt_count == 2
    assert model.invocation_count == 2


@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [
        ("timeout", LlmAgentFailureCode.PROVIDER_TIMEOUT),
        ("unavailable", LlmAgentFailureCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_provider_failure_is_retried_once_and_mapped_without_raw_message(
    failure_kind: str,
    expected_code: LlmAgentFailureCode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_error = "provider-secret-request-body-sentinel"
    model = RaisingStructuredChatModel(
        responses=[AIMessage(content="unused")],
        failure_kind=failure_kind,
        raw_error_text=raw_error,
    )
    adapter = _adapter(TrainingAgentAdapter, model)
    current_envelope = envelope()

    result = adapter.propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=pool(current_envelope),
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is expected_code
    assert result.failure.attempt_count == 2
    assert model.invocation_count == 2
    assert raw_error not in repr(result)
    assert raw_error not in caplog.text


def test_unconfigured_feature_builds_unavailable_invoker_without_startup_failure() -> None:
    settings = Settings(
        _env_file=None,
        llm_agents_enabled=True,
        llm_agents_provider_code="UNCONFIGURED",
        llm_agents_model_code="unconfigured",
    )
    model = ToolCallingFakeChatModel(responses=[AIMessage(content="unused")])

    invoker = build_structured_chat_invoker(settings, chat_model=model)

    assert invoker.chat_model is None
    current_envelope = envelope()
    result = TrainingAgentAdapter(invoker=invoker).propose(
        constraint_envelope=current_envelope,
        exercise_pool=pool(current_envelope),
    )
    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.PROVIDER_UNAVAILABLE
    assert result.failure.attempt_count == 0
    assert model.invocation_count == 0
