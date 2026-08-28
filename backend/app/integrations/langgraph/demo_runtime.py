"""Staging-only V3 demo composition root with identifier-free graph input."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, cast
from uuid import UUID, uuid4

from langchain_core.language_models import BaseChatModel

from backend.app.core.config import Settings
from backend.app.domain.agents.v3_compiler import CompiledPlan
from backend.app.domain.agents.v3_contracts import (
    PlanSpec,
    RegenerationContext,
    SpecialistAgentTypeCode,
)
from backend.app.domain.agents.v3_orchestration import (
    DeterministicFallbackProvider,
    GraphTerminalStatusCode,
    TerminalResult,
)
from backend.app.domain.agents.v3_orchestration import (
    V3GraphResult as DomainGraphResult,
)
from backend.app.domain.agents.v3_persistence import (
    V3CoordinatorAttemptPersistence,
    V3DecisionPersistenceBundle,
    V3RootSnapshotPersistence,
    V3ValidationPersistence,
    map_v3_graph_result_to_persistence_bundle,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationResult,
    IntegrityViolationCode,
)
from backend.app.integrations.langgraph.fallback import DeterministicGraphFallbackProvider
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.app.integrations.langgraph.shadow_runtime import (
    _Compiler,
    _ExecutionContext,
    _Fallback,
    _IntegrityReport,
    _IntegrityValidator,
    _MeaningfulDifference,
)
from backend.app.integrations.langgraph.state import (
    IntegrityValidatorPort,
    SpecialistPort,
    V3GraphInput,
    V3GraphResult,
)
from backend.app.integrations.llm_agents.coordinator import LangChainCoordinatorAdapter
from backend.app.integrations.llm_agents.openai import (
    build_openai_demo_chat_model,
    openai_demo_gates_ready,
)
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.app.integrations.llm_agents.specialists import (
    FeasibilityAgentAdapter,
    RecoveryAgentAdapter,
    TrainingAgentAdapter,
)


class V3DemoRuntimeError(RuntimeError):
    """Sanitized runtime error carrying only a stable machine code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class V3DemoDecisionIdentity:
    decision_execution_id: UUID
    root_decision_execution_id: UUID
    parent_decision_execution_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.parent_decision_execution_id is None:
            if self.decision_execution_id != self.root_decision_execution_id:
                raise ValueError("initial decision identity must be its own root")
        elif self.decision_execution_id in {
            self.root_decision_execution_id,
            self.parent_decision_execution_id,
        }:
            raise ValueError("regeneration identity must create a new decision")


class V3DemoIdentityProvider(Protocol):
    def initial(self) -> V3DemoDecisionIdentity: ...

    def regeneration(
        self,
        root_snapshot: V3RootSnapshotPersistence,
        regeneration_context: RegenerationContext,
    ) -> V3DemoDecisionIdentity: ...


@dataclass(frozen=True, slots=True)
class BoundV3DemoIdentityProvider:
    """Request-scoped identity provider used by application composition."""

    root_decision_execution_id: UUID | None = None
    parent_decision_execution_id: UUID | None = None

    def initial(self) -> V3DemoDecisionIdentity:
        decision_id = uuid4()
        return V3DemoDecisionIdentity(decision_id, decision_id)

    def regeneration(
        self,
        root_snapshot: V3RootSnapshotPersistence,
        regeneration_context: RegenerationContext,
    ) -> V3DemoDecisionIdentity:
        del root_snapshot, regeneration_context
        if self.root_decision_execution_id is None or self.parent_decision_execution_id is None:
            raise V3DemoRuntimeError("V3_REGENERATION_LINEAGE_REQUIRED")
        return V3DemoDecisionIdentity(
            decision_execution_id=uuid4(),
            root_decision_execution_id=self.root_decision_execution_id,
            parent_decision_execution_id=self.parent_decision_execution_id,
        )


@dataclass(frozen=True, slots=True)
class V3DemoRuntimeVersions:
    graph_version: str = "v3-langgraph-demo-v2"
    prompt_version: str = "v3-prompts-v1"
    compiler_version: str = "v3-plan-compiler-v1"
    validator_version: str = "v3-integrity-validator-v1"
    fallback_version: str = "v3-deterministic-fallback-v1"
    provider_code: str = "OPENAI"


@dataclass(frozen=True, slots=True)
class V3DemoRuntimeMetadata:
    execution_profile: str
    graph_version: str
    prompt_version: str
    model_version: str
    provider_code: str


def _terminal_status(code: str) -> GraphTerminalStatusCode:
    if code == "SUCCEEDED":
        return GraphTerminalStatusCode.COMPLETED
    try:
        return GraphTerminalStatusCode(code)
    except ValueError:
        return GraphTerminalStatusCode.FAILED


def _canonical_validations(
    graph: V3GraphResult,
) -> tuple[tuple[V3CoordinatorAttemptPersistence, ...], tuple[V3ValidationPersistence, ...]]:
    canonical = tuple(
        item.canonical
        for item in graph.integrity_validations
        if isinstance(item, _IntegrityReport)
        and isinstance(item.canonical, IntegrityValidationResult)
    )
    if not canonical:
        return (), ()
    # The persistence v1 contract has coordinator attempt slots 0 and 1. A
    # fallback reuses slot 0, so retain its authoritative final validation.
    compiled_candidates = tuple(
        item for item in graph.compiled_plans if isinstance(item, CompiledPlan)
    )
    plans: tuple[PlanSpec | None, ...]
    if graph.used_fallback:
        canonical = (canonical[-1],)
        compiled_candidates = (compiled_candidates[-1],)
        plans = (None,)
    else:
        canonical = canonical[-2:]
        compiled_candidates = compiled_candidates[-len(canonical) :]
        plans = (
            (graph.coordinator_initial_plan, graph.coordinator_repair_plan)
            if len(canonical) == 2
            else (graph.coordinator_repair_plan or graph.coordinator_initial_plan,)
        )
    attempts = tuple(
        V3CoordinatorAttemptPersistence(
            attempt_number=index,
            plan_spec=plans[index],
            repair_codes=(
                tuple(sorted(item.code.value for item in canonical[0].violations))
                if index == 1
                else ()
            ),
            prompt_version="v3-prompts-v1",
            model_version="placeholder-model-v1",
        )
        for index in range(len(canonical))
    )
    validations = tuple(
        V3ValidationPersistence(
            attempt_number=index,
            compiled_plan_candidate=(compiled_candidates[index]),
            integrity_validation=value,
        )
        for index, value in enumerate(canonical)
    )
    return attempts, validations


@dataclass(slots=True)
class V3DemoRuntime:
    settings: Settings
    graph_runtime: V3LangGraphRuntime
    invoker: StructuredChatInvoker
    identity_provider: V3DemoIdentityProvider = field(default_factory=BoundV3DemoIdentityProvider)
    fallback_provider: DeterministicFallbackProvider = field(
        default_factory=DeterministicGraphFallbackProvider
    )
    versions: V3DemoRuntimeVersions = field(default_factory=V3DemoRuntimeVersions)
    execution_profile: str = "DEMO"

    @property
    def metadata(self) -> V3DemoRuntimeMetadata:
        return V3DemoRuntimeMetadata(
            execution_profile=self.execution_profile,
            graph_version=self.versions.graph_version,
            prompt_version=self.versions.prompt_version,
            model_version=self.settings.llm_agents_model_code,
            provider_code=self.versions.provider_code,
        )

    async def create(
        self,
        *,
        root_snapshot: V3RootSnapshotPersistence,
    ) -> V3DecisionPersistenceBundle:
        identity = self.identity_provider.initial()
        return await self._execute(root_snapshot, identity=identity)

    async def regenerate(
        self,
        *,
        root_snapshot: V3RootSnapshotPersistence,
        regeneration_context: RegenerationContext,
    ) -> V3DecisionPersistenceBundle:
        identity = self.identity_provider.regeneration(root_snapshot, regeneration_context)
        return await self._execute(
            root_snapshot,
            identity=identity,
            regeneration_context=regeneration_context,
        )

    async def _execute(
        self,
        root_snapshot: V3RootSnapshotPersistence,
        *,
        identity: V3DemoDecisionIdentity,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3DecisionPersistenceBundle:
        envelope = root_snapshot.constraint_envelope
        pool = root_snapshot.exercise_pool
        context = _ExecutionContext()
        graph_input = V3GraphInput(
            constraint_envelope=envelope,
            exercise_pool=pool,
            graph_version=self.versions.graph_version,
            prompt_version=self.versions.prompt_version,
            model_version=self.settings.llm_agents_model_code,
            policy_version=envelope.policy_version,
            catalog_version=envelope.catalog_version,
            snapshot_is_fresh=True,
            specialists={
                SpecialistAgentTypeCode.TRAINING: cast(
                    SpecialistPort, TrainingAgentAdapter(invoker=self.invoker)
                ),
                SpecialistAgentTypeCode.RECOVERY: cast(
                    SpecialistPort, RecoveryAgentAdapter(invoker=self.invoker)
                ),
                SpecialistAgentTypeCode.FEASIBILITY: cast(
                    SpecialistPort, FeasibilityAgentAdapter(invoker=self.invoker)
                ),
            },
            coordinator=LangChainCoordinatorAdapter(invoker=self.invoker),
            compiler=_Compiler(envelope, pool, context, self.versions.compiler_version),
            validator=cast(
                IntegrityValidatorPort,
                _IntegrityValidator(context, self.versions.validator_version),
            ),
            fallback=_Fallback(self.fallback_provider, self.versions.fallback_version),
            meaningful_difference_validator=_MeaningfulDifference(),
            regeneration_context=regeneration_context,
            node_timeout_seconds=self.settings.llm_agents_timeout_seconds,
        )
        graph = await self.graph_runtime.ainvoke(graph_input)
        return self._bundle(graph, root_snapshot=root_snapshot, identity=identity)

    def _bundle(
        self,
        graph: V3GraphResult,
        *,
        root_snapshot: V3RootSnapshotPersistence,
        identity: V3DemoDecisionIdentity,
    ) -> V3DecisionPersistenceBundle:
        envelope = root_snapshot.constraint_envelope
        terminal_status = _terminal_status(graph.status_code)
        compiled = graph.compiled_plan if isinstance(graph.compiled_plan, CompiledPlan) else None
        final_plan = compiled if terminal_status is GraphTerminalStatusCode.COMPLETED else None
        terminal_result = None
        if terminal_status is not GraphTerminalStatusCode.COMPLETED:
            reasons = tuple(sorted(set(graph.failure_codes))) or (f"V3_{terminal_status.value}",)
            terminal_result = TerminalResult(
                status_code=terminal_status,
                reason_codes=reasons,
            )
        integrity_codes = {
            code
            for item in graph.integrity_validations
            for value in item.violation_codes
            if (code := IntegrityViolationCode._value2member_map_.get(value)) is not None
        }
        domain_graph = DomainGraphResult.create(
            graph_version=self.versions.graph_version,
            terminal_status_code=terminal_status,
            envelope_hash=envelope.envelope_hash,
            pool_hash=root_snapshot.exercise_pool.pool_hash,
            round_one_proposals=graph.round_one_proposals,
            coordinator_initial_plan=graph.coordinator_initial_plan,
            coordinator_repair_plan=graph.coordinator_repair_plan,
            compiled_plan=compiled,
            integrity_violation_codes=(
                ()
                if terminal_status is GraphTerminalStatusCode.COMPLETED
                else tuple(code for code in IntegrityViolationCode if code in integrity_codes)
            ),
            fallback_used=graph.used_fallback,
            fallback_version=(self.versions.fallback_version if graph.used_fallback else None),
            final_plan=final_plan,
            terminal_result=terminal_result,
        )
        attempts, validations = _canonical_validations(graph)
        attempts = tuple(
            item.model_copy(
                update={
                    "prompt_version": self.versions.prompt_version,
                    "model_version": self.settings.llm_agents_model_code,
                }
            )
            for item in attempts
        )
        return map_v3_graph_result_to_persistence_bundle(
            domain_graph,
            decision_execution_id=identity.decision_execution_id,
            root_decision_execution_id=identity.root_decision_execution_id,
            parent_decision_execution_id=identity.parent_decision_execution_id,
            root_snapshot=root_snapshot,
            coordinator_attempts=attempts,
            validations=validations,
            policy_version=envelope.policy_version,
            prompt_version=self.versions.prompt_version,
            model_version=self.settings.llm_agents_model_code,
            failure_codes=tuple(sorted(set(graph.failure_codes))),
        )


def build_v3_demo_runtime(
    settings: Settings,
    *,
    execution_profile: str,
    chat_model: BaseChatModel | None = None,
    fallback_provider: DeterministicFallbackProvider | None = None,
    identity_provider: V3DemoIdentityProvider | None = None,
    versions: V3DemoRuntimeVersions | None = None,
) -> V3DemoRuntime | None:
    """Compose the staging demo runtime only after every server-owned gate."""

    if not openai_demo_gates_ready(settings, execution_profile=execution_profile):
        return None
    model = chat_model or build_openai_demo_chat_model(
        settings, execution_profile=execution_profile
    )
    if model is None:
        return None
    resolved_versions = versions or V3DemoRuntimeVersions()
    return V3DemoRuntime(
        settings=settings,
        graph_runtime=V3LangGraphRuntime(create_v3_graph()),
        invoker=StructuredChatInvoker(
            chat_model=model,
            model_code=settings.llm_agents_model_code,
            max_attempts=min(settings.llm_agents_max_attempts, 2),
            use_native_json_schema=chat_model is None,
        ),
        identity_provider=identity_provider or BoundV3DemoIdentityProvider(),
        fallback_provider=fallback_provider
        or DeterministicGraphFallbackProvider(fallback_version=resolved_versions.fallback_version),
        versions=resolved_versions,
        execution_profile=execution_profile,
    )


__all__ = [
    "BoundV3DemoIdentityProvider",
    "V3DemoDecisionIdentity",
    "V3DemoIdentityProvider",
    "V3DemoRuntime",
    "V3DemoRuntimeError",
    "V3DemoRuntimeMetadata",
    "V3DemoRuntimeVersions",
    "build_v3_demo_runtime",
]
