from __future__ import annotations

import asyncio
import inspect
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.domain.agents.retrieval import (
    ExercisePoolSnapshot,
    ExerciseRetrievalRequest,
)
from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    ExercisePrescription,
    PlanActionCode,
    PlanSpec,
    RegenerationContext,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.domain.agents.v3_orchestration import FallbackRequest, GraphTerminalStatusCode
from backend.app.domain.agents.v3_persistence import V3RootSnapshotPersistence
from backend.app.domain.rules.safety import SafetyRequiredActionCode
from backend.app.integrations.langgraph.demo_runtime import (
    BoundV3DemoIdentityProvider,
    build_v3_demo_runtime,
)
from backend.app.integrations.v3_demo_factory import V3DemoRuntimePort
from backend.tests.unit.llm_agent_test_support import (
    RaisingStructuredChatModel,
    ToolCallingFakeChatModel,
    tool_response,
)
from backend.tests.unit.test_v3_agent_contracts import A, B, D, prescription, proposal
from backend.tests.unit.test_v3_coordinator_contracts import coordinator_input, plan, proposals
from backend.tests.unit.test_v3_persistence_service import make_bundle


class FallbackProvider:
    def __init__(self, fallback: DeterministicFallbackPlanSpec) -> None:
        self.fallback = fallback
        self.calls = 0

    def generate(self, request: FallbackRequest) -> DeterministicFallbackPlanSpec:
        self.calls += 1
        assert request.fallback_version == self.fallback.fallback_version
        return self.fallback


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "staging",
        "llm_agents_enabled": True,
        "llm_agents_provider_code": "OPENAI",
        "llm_agents_model_code": "fake-model-v1",
        "llm_agents_approved_model_codes": ("fake-model-v1",),
        "v3_langgraph_enabled": True,
        "openai_api_key": SecretStr("demo-key-sentinel"),
    }
    values.update(overrides)
    return Settings(**values)


def _successful_model(root_snapshot, *, coordinator_plan=None) -> ToolCallingFakeChatModel:
    envelope = root_snapshot.constraint_envelope
    pool = root_snapshot.exercise_pool
    if {A, B}.issubset({record.exercise_id for record in pool.exercises}):
        specialist_proposals = proposals(envelope, pool)
        expected_plan = coordinator_plan or plan(coordinator_input(envelope, pool))
        return ToolCallingFakeChatModel(
            responses=[
                *(
                    tool_response(SpecialistAgentProposal, item, index)
                    for index, item in enumerate(reversed(specialist_proposals), start=1)
                ),
                tool_response(PlanSpec, expected_plan, 4),
            ]
        )
    prescriptions = tuple(
        ExercisePrescription(
            exercise_id=record.exercise_id,
            sequence=index,
            sets=min(envelope.recovery_ceiling.maximum_sets_per_exercise or 1, 3),
            repetitions_per_set=(
                min(envelope.recovery_ceiling.maximum_repetitions_per_set or 1, 10)
                if record.timing_mode_code == "REPS"
                else None
            ),
            work_seconds_per_set=(
                min(envelope.recovery_ceiling.maximum_work_seconds_per_set or 1, 30)
                if record.timing_mode_code != "REPS"
                else None
            ),
            rest_seconds_between_sets=(
                envelope.recovery_ceiling.minimum_rest_seconds_between_sets or 0
            ),
            transition_seconds=15,
            intensity_code=(envelope.recovery_ceiling.allowed_intensity_codes or ("LOW",))[0],
            load_code=(envelope.recovery_ceiling.allowed_load_codes or (None,))[0],
            location_code=next(
                code for code in record.location_codes if code in envelope.allowed_location_codes
            ),
            equipment_codes=record.equipment_codes,
        )
        for index, record in enumerate(pool.exercises[:2], start=1)
    )
    specialist_proposals = tuple(
        proposal(
            agent_type,
            envelope,
            pool,
            prescriptions=(prescriptions if agent_type is SpecialistAgentTypeCode.TRAINING else ()),
            requested_duration_minutes=envelope.requested_duration_minutes,
        )
        for agent_type in SPECIALIST_AGENT_ORDER
    )
    expected_plan = coordinator_plan or plan(
        coordinator_input(
            envelope,
            pool,
            current_proposals=specialist_proposals,
        ),
        requested_duration_minutes=envelope.requested_duration_minutes,
        plan_prescriptions=prescriptions,
    )
    responses = [
        tool_response(SpecialistAgentProposal, proposal, index)
        for index, proposal in enumerate(reversed(specialist_proposals), start=1)
    ]
    responses.append(tool_response(PlanSpec, expected_plan, 4))
    return ToolCallingFakeChatModel(responses=responses)


def _blocked_root_snapshot() -> V3RootSnapshotPersistence:
    source = make_bundle().root_snapshot
    envelope_values = source.constraint_envelope.model_dump(exclude={"envelope_hash"})
    envelope_values.update(
        plan_generation_allowed=False,
        safety_required_action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
    )
    blocked_envelope = type(source.constraint_envelope).create(**envelope_values)
    source_pool = source.exercise_pool
    blocked_pool = ExercisePoolSnapshot.create(
        catalog_version=source_pool.catalog_version,
        constraint_envelope_hash=blocked_envelope.envelope_hash,
        exercises=source_pool.exercises,
        mandatory_exercise_ids=source_pool.mandatory_exercise_ids,
        vector_ranked_exercise_ids=source_pool.vector_ranked_exercise_ids,
        retrieval_metadata=source_pool.retrieval_metadata,
        created_at=source_pool.created_at,
    )
    request_values = source.retrieval_request.model_dump()
    request_values["constraint_envelope_hash"] = blocked_envelope.envelope_hash
    return V3RootSnapshotPersistence(
        constraint_envelope=blocked_envelope,
        exercise_pool=blocked_pool,
        retrieval_request=ExerciseRetrievalRequest.model_validate(request_values),
        retrieval_result=source.retrieval_result,
    )


def test_initial_create_returns_complete_persistence_bundle() -> None:
    root_snapshot = make_bundle().root_snapshot
    model = _successful_model(root_snapshot)
    runtime = build_v3_demo_runtime(
        _settings(),
        execution_profile="DEMO",
        chat_model=model,
    )
    assert runtime is not None

    bundle = asyncio.run(runtime.create(root_snapshot=root_snapshot))

    assert bundle.root_snapshot is root_snapshot
    assert bundle.terminal_status_code is GraphTerminalStatusCode.COMPLETED
    assert bundle.final_plan is not None
    assert tuple(item.agent_type_code for item in bundle.agent_proposals) == SPECIALIST_AGENT_ORDER
    assert len(bundle.agent_proposals) == 3
    assert len(bundle.coordinator_attempts) == 1
    assert len(bundle.validations) == 1
    assert model.invocation_count == 4
    assert all(
        root_snapshot.exercise_pool.pool_hash in repr(messages)
        for messages in model.seen_messages[:3]
    )
    assert bundle.root_snapshot.exercise_pool.retrieval_metadata.deterministic_pool_fallback_used
    assert set(bundle.root_snapshot.exercise_pool.mandatory_exercise_ids).issubset(
        item.exercise_id for item in bundle.root_snapshot.exercise_pool.exercises
    )
    assert runtime.metadata.execution_profile == "DEMO"
    assert runtime.metadata.graph_version == "v3-langgraph-demo-v2"
    assert runtime.metadata.provider_code == "OPENAI"


def test_runtime_matches_initial_and_regeneration_structural_contracts() -> None:
    runtime_type = V3DemoRuntimePort

    assert runtime_type is not None
    assert tuple(inspect.signature(runtime_type.create).parameters) == (
        "self",
        "root_snapshot",
    )
    assert tuple(inspect.signature(runtime_type.regenerate).parameters) == (
        "self",
        "root_snapshot",
        "regeneration_context",
    )


def test_runtime_factory_rejects_production_without_constructing_runtime() -> None:
    root_snapshot = make_bundle().root_snapshot
    model = _successful_model(root_snapshot)

    runtime = build_v3_demo_runtime(
        _settings(app_env="production"),
        execution_profile="DEMO",
        chat_model=model,
    )

    assert runtime is None
    assert model.invocation_count == 0


def test_safety_terminal_returns_planless_bundle_with_provider_zero_call() -> None:
    root_snapshot = _blocked_root_snapshot()
    model = ToolCallingFakeChatModel(responses=[AIMessage(content="unused")])
    runtime = build_v3_demo_runtime(
        _settings(),
        execution_profile="DEMO",
        chat_model=model,
    )
    assert runtime is not None

    bundle = asyncio.run(runtime.create(root_snapshot=root_snapshot))

    assert bundle.terminal_status_code is GraphTerminalStatusCode.STOP_AND_SEEK_HELP
    assert bundle.final_plan is None
    assert bundle.agent_proposals == ()
    assert bundle.coordinator_attempts == ()
    assert model.invocation_count == 0


def test_required_specialist_provider_failure_uses_validated_fallback() -> None:
    source = make_bundle()
    root_snapshot = source.root_snapshot
    fallback = DeterministicFallbackPlanSpec.create(
        fallback_version="v3-deterministic-fallback-v1",
        envelope_hash=root_snapshot.constraint_envelope.envelope_hash,
        pool_hash=root_snapshot.exercise_pool.pool_hash,
        action_code=PlanActionCode.KEEP,
        requested_duration_minutes=(root_snapshot.constraint_envelope.requested_duration_minutes),
        estimated_duration_seconds=(
            root_snapshot.constraint_envelope.requested_duration_minutes * 60
        ),
        exercise_prescriptions=tuple(item.prescription for item in source.final_plan.exercises),
        reason_codes=("PROVIDER_FAILURE",),
    )
    fallback_provider = FallbackProvider(fallback)
    model = RaisingStructuredChatModel(
        responses=[AIMessage(content="unused")],
        failure_kind="timeout",
        raw_error_text="provider-secret-response-sentinel",
    )
    runtime = build_v3_demo_runtime(
        _settings(llm_agents_max_attempts=2),
        execution_profile="DEMO",
        chat_model=model,
        fallback_provider=fallback_provider,
    )
    assert runtime is not None

    bundle = asyncio.run(runtime.create(root_snapshot=root_snapshot))

    assert bundle.terminal_status_code is GraphTerminalStatusCode.COMPLETED
    assert bundle.fallback_used
    assert bundle.final_plan is not None
    assert bundle.agent_proposals == ()
    assert bundle.coordinator_attempts[0].plan_spec is None
    assert bundle.validations[0].integrity_validation.status_code.value == "PASS"
    assert fallback_provider.calls == 1
    assert "provider-secret-response-sentinel" not in repr(bundle)


@pytest.mark.parametrize("failure_kind", ["timeout", "unavailable"])
def test_default_graph_fallback_handles_provider_failures(failure_kind: str) -> None:
    root_snapshot = make_bundle().root_snapshot
    model = RaisingStructuredChatModel(
        responses=[AIMessage(content="unused")],
        failure_kind=failure_kind,
        raw_error_text="provider-private-error-sentinel",
    )
    runtime = build_v3_demo_runtime(
        _settings(llm_agents_max_attempts=2),
        execution_profile="DEMO",
        chat_model=model,
    )
    assert runtime is not None

    bundle = asyncio.run(runtime.create(root_snapshot=root_snapshot))

    assert bundle.fallback_used
    assert bundle.final_plan is not None
    assert model.invocation_count == 6
    assert "provider-private-error-sentinel" not in repr(bundle)


def test_default_graph_fallback_handles_invalid_structured_output() -> None:
    root_snapshot = make_bundle().root_snapshot
    model = ToolCallingFakeChatModel(responses=[AIMessage(content="invalid")])
    runtime = build_v3_demo_runtime(
        _settings(llm_agents_max_attempts=2),
        execution_profile="DEMO",
        chat_model=model,
    )
    assert runtime is not None

    bundle = asyncio.run(runtime.create(root_snapshot=root_snapshot))

    assert bundle.fallback_used
    assert bundle.final_plan is not None
    assert model.invocation_count == 6


def test_regeneration_uses_stored_root_and_requires_meaningful_sequence_change() -> None:
    source = make_bundle()
    root_snapshot = source.root_snapshot
    current_input = coordinator_input(
        root_snapshot.constraint_envelope, root_snapshot.exercise_pool
    )
    alternative = plan(
        current_input,
        plan_prescriptions=(
            prescription(B, 1, phase_code="WARMUP"),
            prescription(A, 2),
            prescription(D, 3, phase_code="COOLDOWN"),
        ),
    )
    parent_id = uuid4()
    runtime = build_v3_demo_runtime(
        _settings(),
        execution_profile="DEMO",
        chat_model=_successful_model(root_snapshot, coordinator_plan=alternative),
        identity_provider=BoundV3DemoIdentityProvider(
            root_decision_execution_id=source.root_decision_execution_id,
            parent_decision_execution_id=parent_id,
        ),
    )
    assert runtime is not None
    context = RegenerationContext(
        generation_sequence=1,
        previous_plan_hash=source.final_plan.compiled_plan_hash,
        previous_exercise_ids=tuple(
            item.prescription.exercise_id for item in source.final_plan.exercises
        ),
        variation_codes=("EXERCISE_ORDER_CHANGED",),
    )

    bundle = asyncio.run(
        runtime.regenerate(
            root_snapshot=root_snapshot,
            regeneration_context=context,
        )
    )

    assert bundle.root_snapshot == root_snapshot
    assert bundle.root_decision_execution_id == source.root_decision_execution_id
    assert bundle.parent_decision_execution_id == parent_id
    assert bundle.final_plan is not None
    assert tuple(item.prescription.exercise_id for item in bundle.final_plan.exercises) == (B, A, D)
