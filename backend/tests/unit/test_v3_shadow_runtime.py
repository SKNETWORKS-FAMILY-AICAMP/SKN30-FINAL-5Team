from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from backend.app.core.config import Settings
from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec
from backend.app.domain.agents.v3_contracts import (
    PlanActionCode,
    PlanSpec,
    SpecialistAgentProposal,
)
from backend.app.domain.agents.v3_orchestration import FallbackRequest, GraphTerminalStatusCode
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.integrations.langgraph.shadow_runtime import (
    V3ShadowPricingReference,
    build_v3_shadow_runtime,
    write_shadow_results_jsonl,
)
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowCase,
    V3ShadowExecutionError,
    V3ShadowExecutionRequest,
    V3ShadowFailureCode,
    V3ShadowUsageStatusCode,
)
from backend.tests.unit.llm_agent_test_support import (
    RaisingStructuredChatModel,
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import envelope, pool
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan, proposals


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_agents_enabled=True,
        llm_agents_provider_code="OPENAI",
        llm_agents_model_code="fake-model-v1",
        llm_agents_approved_model_codes=("fake-model-v1",),
        v3_langgraph_enabled=True,
        v3_shadow_evaluation_enabled=True,
    )


def _request(current_envelope) -> V3ShadowExecutionRequest:
    case = V3ShadowCase.create(
        scenario_code="HEALTHY_SYNTHETIC",
        fixture_version="golden-v1",
        fixture_hash="a" * 64,
    )
    return V3ShadowExecutionRequest(
        case=case,
        graph_version="v3-langgraph-shadow-v2",
        policy_version=current_envelope.policy_version,
        catalog_version=current_envelope.catalog_version,
        prompt_version="v3-prompts-v1",
        provider_code="OPENAI",
        model_version="fake-model-v1",
        snapshot_is_fresh=True,
    )


def _with_usage(message: AIMessage, input_tokens: int, output_tokens: int) -> AIMessage:
    return message.model_copy(
        update={
            "usage_metadata": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
        }
    )


def _successful_model(current_envelope, current_pool) -> ToolCallingFakeChatModel:
    specialist_proposals = proposals(current_envelope, current_pool)
    expected_plan = plan(coordinator_input(current_envelope, current_pool))
    # LangGraph schedules the three fan-out branches in reverse edge order while
    # the result reducer canonicalizes them back to TRAINING/RECOVERY/FEASIBILITY.
    responses = [
        _with_usage(
            tool_response(SpecialistAgentProposal, proposal, index),
            10 + index,
            5,
        )
        for index, proposal in enumerate(reversed(specialist_proposals), start=1)
    ]
    responses.append(_with_usage(tool_response(PlanSpec, expected_plan, 4), 20, 7))
    return ToolCallingFakeChatModel(responses=responses)


def test_shadow_runtime_preserves_full_audit_and_provider_reported_usage() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    model = _successful_model(current_envelope, current_pool)
    runtime = build_v3_shadow_runtime(_settings(), allow_provider_calls=False, chat_model=model)

    result = asyncio.run(
        runtime.execute(
            _request(current_envelope),
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    assert result.terminal_status_code is GraphTerminalStatusCode.COMPLETED
    assert result.plan is not None
    assert result.safety.invariant_passed
    assert len(result.invocation_metrics) == 4
    assert result.usage.status_code is V3ShadowUsageStatusCode.COMPLETE
    assert result.usage.provider_call_count == 4
    assert result.usage.input_token_count == 11 + 12 + 13 + 20
    assert result.usage.output_token_count == 22
    assert result.usage.decision_cost is None
    assert model.invocation_count == 4


def test_pricing_requires_exact_model_match() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    runtime = build_v3_shadow_runtime(
        _settings(),
        allow_provider_calls=False,
        chat_model=_successful_model(current_envelope, current_pool),
        pricing_reference=V3ShadowPricingReference(
            version="pricing-v1",
            model_version="different-model-v1",
            currency_code="USD",
            input_cost_per_token=Decimal("0.1"),
            output_cost_per_token=Decimal("0.2"),
        ),
    )

    result = asyncio.run(
        runtime.execute(
            _request(current_envelope),
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    assert result.usage.input_token_count is not None
    assert result.usage.decision_cost is None
    assert result.usage.pricing_reference_version is None


def test_safety_veto_causes_provider_zero_call() -> None:
    source = envelope()
    values = source.model_dump(exclude={"envelope_hash"})
    values.update(
        plan_generation_allowed=False,
        safety_required_action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
    )
    blocked = type(source).create(**values)
    blocked_pool = pool(blocked)
    runtime = build_v3_shadow_runtime(_settings(), allow_provider_calls=False)

    result = asyncio.run(
        runtime.execute(
            _request(blocked),
            constraint_envelope=blocked,
            exercise_pool=blocked_pool,
        )
    )

    assert result.terminal_status_code is GraphTerminalStatusCode.STOP_AND_SEEK_HELP
    assert result.invocation_metrics == ()
    assert result.usage.status_code is V3ShadowUsageStatusCode.NOT_APPLICABLE


def test_unconfigured_provider_fails_closed_without_calls() -> None:
    current_envelope = envelope()
    runtime = build_v3_shadow_runtime(_settings(), allow_provider_calls=False)

    with pytest.raises(V3ShadowExecutionError) as exc_info:
        asyncio.run(
            runtime.execute(
                _request(current_envelope),
                constraint_envelope=current_envelope,
                exercise_pool=pool(current_envelope),
            )
        )

    assert exc_info.value.code is V3ShadowFailureCode.PROVIDER_NOT_CONFIGURED


class _FallbackProvider:
    def __init__(self, fallback: DeterministicFallbackPlanSpec) -> None:
        self.fallback = fallback
        self.calls = 0

    def generate(self, request: FallbackRequest) -> DeterministicFallbackPlanSpec:
        self.calls += 1
        assert request.fallback_version == self.fallback.fallback_version
        return self.fallback


def test_provider_failure_uses_validated_deterministic_fallback_without_coordinator() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    source_proposal = proposals(current_envelope, current_pool)[0]
    fallback = DeterministicFallbackPlanSpec.create(
        fallback_version="v3-deterministic-fallback-v1",
        envelope_hash=current_envelope.envelope_hash,
        pool_hash=current_pool.pool_hash,
        action_code=PlanActionCode.KEEP,
        requested_duration_minutes=current_envelope.requested_duration_minutes,
        estimated_duration_seconds=current_envelope.requested_duration_minutes * 60,
        exercise_prescriptions=source_proposal.exercise_prescriptions,
        reason_codes=("PROVIDER_FAILURE",),
    )
    fallback_provider = _FallbackProvider(fallback)
    model = RaisingStructuredChatModel(
        responses=[AIMessage(content="unused")],
        failure_kind="unavailable",
        raw_error_text="provider-secret-response-sentinel",
    )
    runtime = build_v3_shadow_runtime(
        _settings(),
        allow_provider_calls=False,
        chat_model=model,
        fallback_provider=fallback_provider,
    )

    result = asyncio.run(
        runtime.execute(
            _request(current_envelope),
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    assert result.terminal_status_code is GraphTerminalStatusCode.COMPLETED
    assert result.fallback_used
    assert result.plan is not None
    assert fallback_provider.calls == 1
    assert all(metric.role_code.value != "COORDINATOR" for metric in result.invocation_metrics)
    assert "provider-secret-response-sentinel" not in repr(result)


def test_shadow_jsonl_is_canonical_and_identifier_free() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    runtime = build_v3_shadow_runtime(
        _settings(),
        allow_provider_calls=False,
        chat_model=_successful_model(current_envelope, current_pool),
    )
    result = asyncio.run(
        runtime.execute(
            _request(current_envelope),
            constraint_envelope=current_envelope,
            exercise_pool=current_pool,
        )
    )

    workspace_root = Path.cwd()
    path = write_shadow_results_jsonl(workspace_root, run_id="unit-run-001", results=(result,))
    text = path.read_text(encoding="utf-8")
    parsed = json.loads(text)

    assert path == workspace_root / "outputs" / "v3-shadow" / "unit-run-001" / "results.jsonl"
    assert parsed["result_hash"] == result.result_hash
    assert "user_id" not in text
    assert "prompt_text" not in text
    assert "provider_response" not in text
