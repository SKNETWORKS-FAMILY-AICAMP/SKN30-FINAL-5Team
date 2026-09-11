from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.app.core.config import Settings
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
)
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS
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


def test_async_specialist_boundary_preserves_structured_contract() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    expected = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(
        responses=[tool_response(SpecialistAgentProposal, expected, 1)]
    )
    adapter = TrainingAgentAdapter(
        invoker=StructuredChatInvoker(chat_model=model, model_code="fake-model-v1")
    )

    result = asyncio.run(
        adapter.apropose(
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    assert result.output == expected
    assert model.invocation_count == 1


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
    # Read the registered version rather than a literal pattern: prompts are
    # versioned independently, and pinning the shape here only asserts that they
    # were all bumped together.
    assert adapter.prompt_version == ROLE_PROMPTS[LlmAgentRoleCode(agent_type.value)].version
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


@pytest.mark.parametrize(
    "adapter_type",
    (RecoveryAgentAdapter, FeasibilityAgentAdapter),
)
def test_advisory_specialist_prompt_forbids_exercise_plans(adapter_type: type) -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    expected_role = (
        SpecialistAgentTypeCode.RECOVERY
        if adapter_type is RecoveryAgentAdapter
        else SpecialistAgentTypeCode.FEASIBILITY
    )
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(
                SpecialistAgentProposal,
                proposal(expected_role, current_envelope, current_pool),
                1,
            )
        ]
    )

    result = _adapter(adapter_type, model).propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.succeeded
    system_message = next(
        message for message in model.seen_messages[0] if isinstance(message, SystemMessage)
    )
    assert isinstance(system_message.content, str)
    assert "adjustment_codes" in system_message.content
    assert "always leave exercise_prescriptions empty" in system_message.content
    assert "advisory" in system_message.content
    assert "Use NEEDS_INPUT only" in system_message.content


def test_advisory_specialists_receive_role_minimized_pool_payloads() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    recovery_model = ToolCallingFakeChatModel(
        responses=[
            tool_response(
                SpecialistAgentProposal,
                proposal(SpecialistAgentTypeCode.RECOVERY, current_envelope, current_pool),
                1,
            )
        ]
    )
    feasibility_model = ToolCallingFakeChatModel(
        responses=[
            tool_response(
                SpecialistAgentProposal,
                proposal(SpecialistAgentTypeCode.FEASIBILITY, current_envelope, current_pool),
                1,
            )
        ]
    )

    _adapter(RecoveryAgentAdapter, recovery_model).propose(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )
    _adapter(FeasibilityAgentAdapter, feasibility_model).propose(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    recovery_message = next(
        message for message in recovery_model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    feasibility_message = next(
        message
        for message in feasibility_model.seen_messages[0]
        if isinstance(message, HumanMessage)
    )
    assert isinstance(recovery_message.content, str)
    assert isinstance(feasibility_message.content, str)
    recovery_pool = json.loads(recovery_message.content)["input"]["exercise_pool"]
    feasibility_pool = json.loads(feasibility_message.content)["input"]["exercise_pool"]

    assert "exercises" not in recovery_pool
    assert recovery_pool["exercise_id_allowlist"]
    assert feasibility_pool["exercises"]
    feasibility_fields = set(feasibility_pool["exercises"][0])
    assert "location_codes" in feasibility_fields
    assert "default_rest_seconds" in feasibility_fields
    assert "fitt_context" not in feasibility_fields
    assert "body_focus_code" not in feasibility_fields


def test_training_receives_structured_fitt_ranges_and_non_maximum_guidance() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    expected = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(
        responses=[tool_response(SpecialistAgentProposal, expected, 1)]
    )

    result = _adapter(TrainingAgentAdapter, model).propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.succeeded
    system_message = next(
        message for message in model.seen_messages[0] if isinstance(message, SystemMessage)
    )
    human_message = next(
        message for message in model.seen_messages[0] if isinstance(message, HumanMessage)
    )
    assert isinstance(system_message.content, str)
    assert "Never always select the maximum" in system_message.content
    assert "REVIEW_REQUIRED" in system_message.content
    assert isinstance(human_message.content, str)
    payload = json.loads(human_message.content)["input"]
    fitt = payload["exercise_pool"]["exercises"][0]["fitt_context"]
    assert fitt["review_status_code"] == "DOMAIN_APPROVED"
    assert fitt["volume"] == {
        "default_reps": 8,
        "default_sets": 3,
        "max_reps": 12,
        "max_sets": 3,
        "min_reps": 8,
        "min_sets": 2,
    }


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


def test_specialist_retries_domain_invalid_output_once_then_fails_closed() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    outside = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(OUTSIDE, 1),),
    )
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(SpecialistAgentProposal, outside, 1),
            tool_response(SpecialistAgentProposal, outside, 2),
        ]
    )
    adapter = _adapter(TrainingAgentAdapter, model)

    result = adapter.propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.output is None
    assert result.failure is not None
    assert result.failure.code is LlmAgentFailureCode.DOMAIN_INVALID
    assert result.failure.attempt_count == 2
    assert model.invocation_count == 2


def test_specialist_recovers_when_domain_retry_returns_a_valid_proposal() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    outside = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(OUTSIDE, 1),),
    )
    expected = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(SpecialistAgentProposal, outside, 1),
            tool_response(SpecialistAgentProposal, expected, 2),
        ]
    )

    result = _adapter(TrainingAgentAdapter, model).propose(  # type: ignore[attr-defined]
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
    )

    assert result.output == expected
    assert result.failure is None
    assert model.invocation_count == 2


def test_async_specialist_recovers_when_domain_retry_returns_a_valid_proposal() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    outside = proposal(
        SpecialistAgentTypeCode.TRAINING,
        current_envelope,
        current_pool,
        prescriptions=(prescription(OUTSIDE, 1),),
    )
    expected = proposal(SpecialistAgentTypeCode.TRAINING, current_envelope, current_pool)
    model = ToolCallingFakeChatModel(
        responses=[
            tool_response(SpecialistAgentProposal, outside, 1),
            tool_response(SpecialistAgentProposal, expected, 2),
        ]
    )

    result = asyncio.run(
        _adapter(TrainingAgentAdapter, model).apropose(  # type: ignore[attr-defined]
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    assert result.output == expected
    assert result.failure is None
    assert model.invocation_count == 2


def test_training_prompt_explains_that_repeated_blocks_share_the_sets_ceiling() -> None:
    instruction = ROLE_PROMPTS[LlmAgentRoleCode.TRAINING].instruction

    assert "all blocks for that exercise share one cumulative" in instruction
    assert "Do not repeat an exercise" in instruction


def test_training_prompt_distinguishes_fitt_reference_from_plan_intensity() -> None:
    instruction = ROLE_PROMPTS[LlmAgentRoleCode.TRAINING].instruction

    assert "not an exercise eligibility filter" in instruction
    assert "prescription's intensity_code" in instruction
    assert "never reject an exercise solely because its FITT intensity differs" in instruction


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
        # A provider SDK raises its own timeout type. Reading that as an outage
        # hid a bound that was set too low: staging reported
        # LLM_AGENT_PROVIDER_UNAVAILABLE at exactly the configured 30 seconds.
        ("sdk_timeout", LlmAgentFailureCode.PROVIDER_TIMEOUT),
        ("wrapped_sdk_timeout", LlmAgentFailureCode.PROVIDER_TIMEOUT),
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


def test_specialist_adapter_accepts_codes_the_model_did_not_sort() -> None:
    # The staging failure: RECOVERY answered with adjustment codes in the order
    # it reasoned about them, the contract requires canonical sorted order, and
    # every proposal was rejected as LLM_AGENT_SCHEMA_INVALID.
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    expected = proposal(SpecialistAgentTypeCode.RECOVERY, current_envelope, current_pool)
    payload = expected.model_dump(mode="json")
    payload["adjustment_codes"] = [
        "RECOVERY_ELIGIBLE_ONLY",
        "INTENSITY_REDUCED",
        "ALLOW_ADDITIONAL_REST",
    ]
    payload["evidence_reference_codes"] = ["POOL", "ENVELOPE"]
    model = ToolCallingFakeChatModel(responses=[tool_response(SpecialistAgentProposal, payload, 1)])

    result = asyncio.run(
        _adapter(RecoveryAgentAdapter, model).apropose(
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    assert result.failure is None
    assert result.output is not None
    assert result.output.adjustment_codes == (
        "ALLOW_ADDITIONAL_REST",
        "INTENSITY_REDUCED",
        "RECOVERY_ELIGIBLE_ONLY",
    )
    assert result.output.evidence_reference_codes == ("ENVELOPE", "POOL")
