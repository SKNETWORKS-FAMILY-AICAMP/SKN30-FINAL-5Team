"""Run one evaluation case through the production multi-agent graph.

Everything downstream of the provider is the real thing: the compiled LangGraph,
the three specialist adapters, the coordinator adapter, the plan compiler, the
integrity validator and the deterministic fallback.  Only the provider is
scripted, and only so the run costs nothing and repeats exactly.

The graph input is assembled the way `V3DemoRuntime._execute` assembles it, from
the same port adapters, so this runner measures the shipped composition rather
than a second one written for tests.  It stops short of the persistence bundle,
which needs a decision identity and is outside the evaluation boundary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, cast

from backend.app.domain.agents.v3_compiler import CompiledPlan
from backend.app.domain.agents.v3_contracts import PlanSpec, SpecialistAgentTypeCode
from backend.app.integrations.langgraph.demo_runtime import V3DemoRuntimeVersions
from backend.app.integrations.langgraph.fallback import DeterministicGraphFallbackProvider
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.app.integrations.langgraph.shadow_runtime import (
    _Compiler,
    _ExecutionContext,
    _Fallback,
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
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.app.integrations.llm_agents.specialists import (
    FeasibilityAgentAdapter,
    RecoveryAgentAdapter,
    TrainingAgentAdapter,
)
from backend.tests.evaluation.architectures import ARCHITECTURE_MULTI_AGENT
from backend.tests.evaluation.dataset import EvaluationCase
from backend.tests.evaluation.runners.fake_chat import InvocationLog, Script, ScriptedChatModel
from backend.tests.evaluation.runners.openai_provider import ProviderContext
from backend.tests.evaluation.runners.payloads import PayloadBuilder
from backend.tests.evaluation.scenario import Scenario, build_scenario

ARCHITECTURE_CODE = ARCHITECTURE_MULTI_AGENT
EVAL_MODEL_CODE = "eval-scripted-model-v1"

# Short so a HANG script resolves quickly. The production default (5.0s) is a
# provider bound, not a property under test here.
DEFAULT_NODE_TIMEOUT_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class CaseRunResult:
    """One case's run, reduced to what the evaluators and metrics need."""

    case: EvaluationCase
    scenario: Scenario
    architecture_code: str
    script: Script
    graph_result: V3GraphResult
    invocations: tuple[InvocationLog, ...]
    wall_clock_ms: int

    @property
    def status_code(self) -> str:
        return self.graph_result.status_code

    @property
    def compiled_plan(self) -> CompiledPlan | None:
        plan = self.graph_result.compiled_plan
        return plan if isinstance(plan, CompiledPlan) else None

    @property
    def plan_spec(self) -> PlanSpec | None:
        return self.graph_result.plan_spec

    @property
    def has_plan(self) -> bool:
        return self.compiled_plan is not None

    @property
    def provider_was_compliant(self) -> bool:
        """Whether the scripted provider answered correctly for every role."""

        return self.script.is_compliant

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return self.graph_result.failure_codes

    @property
    def decline_reason_codes(self) -> tuple[str, ...]:
        """Why an agent declined, tagged by role.

        Training declined on 11 of 58 paid runs while the pools objectively
        supported a plan, and the reason it was asked to give was discarded with
        the rejected proposal. Recorded per role because a decline means
        something different for the plan owner than for an advisor.
        """

        return tuple(
            f"{audit.role_code}:{code}"
            for audit in self.graph_result.invocation_audits
            for code in audit.decline_reason_codes
        )

    @property
    def used_fallback(self) -> bool:
        return self.graph_result.used_fallback

    @property
    def repair_attempts(self) -> int:
        return self.graph_result.repair_attempts

    @property
    def violation_codes(self) -> tuple[str, ...]:
        """Every integrity violation raised across the run, in order."""

        return tuple(
            code
            for validation in self.graph_result.integrity_validations
            for code in validation.violation_codes
        )

    @property
    def prescribed_exercise_ids(self) -> tuple[str, ...]:
        plan = self.compiled_plan
        if plan is None:
            return ()
        return tuple(str(item.prescription.exercise_id) for item in plan.exercises)

    @property
    def llm_call_count(self) -> int:
        return len(self.invocations)

    @property
    def token_usage(self) -> tuple[int, int]:
        """Total (input, output) tokens the audits reported for this run."""

        audits = self.graph_result.invocation_audits
        return (
            sum(audit.input_token_count or 0 for audit in audits),
            sum(audit.output_token_count or 0 for audit in audits),
        )


def _audit_invocations(graph_result: V3GraphResult) -> tuple[InvocationLog, ...]:
    """Reconstruct the invocation log from the graph's own audits.

    A real provider has no script to record, so the log comes from
    `InvocationAudit`, which the graph produces either way. That keeps the
    multi-agent metrics identical between a scripted run and a paid one.
    """

    return tuple(
        InvocationLog(
            role_code=audit.role_code,
            mode_code="REPAIR" if audit.phase_code == "REPAIR" else "INITIAL",
            script_code=audit.status_code,
        )
        for audit in graph_result.invocation_audits
    )


@dataclass(slots=True)
class MultiAgentRunner:
    """Compose the shipped graph once and run cases through it."""

    versions: V3DemoRuntimeVersions = field(default_factory=V3DemoRuntimeVersions)
    node_timeout_seconds: float = DEFAULT_NODE_TIMEOUT_SECONDS

    # Supplied only for a paid run. When absent the scripted model answers, and
    # the run costs nothing. Everything downstream is identical either way,
    # which is the property that makes the offline results meaningful.
    provider: ProviderContext | None = None

    # ADR-0020 opt-in: export the provider calls themselves to LangSmith. Off by
    # default here for the same reason it is off in the service -- an evaluation
    # run should not start exporting prompts because a key happened to be set.
    # A traced run also pays LangSmith's export on every call, so its latency is
    # not comparable with an untraced one.
    tracing_enabled: bool = False

    @property
    def model_label(self) -> str:
        return self.provider.label if self.provider is not None else EVAL_MODEL_CODE

    async def run(self, case: EvaluationCase, script: Script) -> CaseRunResult:
        scenario = build_scenario(case)
        return await self.run_scenario(scenario, script)

    async def run_scenario(self, scenario: Scenario, script: Script) -> CaseRunResult:
        envelope = scenario.constraint_envelope
        pool = scenario.exercise_pool
        scripted: ScriptedChatModel | None = None
        if self.provider is not None:
            chat_model: Any = self.provider.chat_model
            model_code = self.provider.model_code
            max_attempts = self.provider.max_attempts
            # Production binds the provider's native JSON-schema mode
            # (`build_v3_demo_runtime` passes `use_native_json_schema=chat_model
            # is None`, and in production it builds its own model). A paid run
            # has to bind it the same way or it would be measuring a different
            # structured-output path than the one that ships.
            native_json_schema = True
        else:
            scripted = ScriptedChatModel(
                script=script,
                payload_builder=PayloadBuilder(envelope=envelope, pool=pool),
            )
            chat_model = scripted
            model_code = EVAL_MODEL_CODE
            max_attempts = 1
            # The scripted stand-in implements the plain binding only.
            native_json_schema = False
        invoker = StructuredChatInvoker(
            chat_model=chat_model,
            model_code=model_code,
            max_attempts=max_attempts,
            use_native_json_schema=native_json_schema,
            tracing_enabled=self.tracing_enabled
            or (self.provider.tracing_enabled if self.provider is not None else False),
        )
        context = _ExecutionContext()
        graph_input = V3GraphInput(
            constraint_envelope=envelope,
            exercise_pool=pool,
            graph_version=self.versions.graph_version,
            prompt_version=self.versions.prompt_version,
            model_version=model_code,
            policy_version=envelope.policy_version,
            catalog_version=envelope.catalog_version,
            snapshot_is_fresh=True,
            specialists={
                SpecialistAgentTypeCode.TRAINING: cast(
                    SpecialistPort,
                    TrainingAgentAdapter(
                        invoker=invoker,
                        feasibility_provider=DeterministicGraphFallbackProvider(
                            fallback_version=self.versions.fallback_version
                        ),
                        fallback_version=self.versions.fallback_version,
                    ),
                ),
                SpecialistAgentTypeCode.RECOVERY: cast(
                    SpecialistPort, RecoveryAgentAdapter(invoker=invoker)
                ),
                SpecialistAgentTypeCode.FEASIBILITY: cast(
                    SpecialistPort, FeasibilityAgentAdapter(invoker=invoker)
                ),
            },
            coordinator=LangChainCoordinatorAdapter(invoker=invoker),
            compiler=_Compiler(envelope, pool, context, self.versions.compiler_version),
            validator=cast(
                IntegrityValidatorPort,
                _IntegrityValidator(context, self.versions.validator_version),
            ),
            fallback=_Fallback(
                DeterministicGraphFallbackProvider(fallback_version=self.versions.fallback_version),
                self.versions.fallback_version,
            ),
            meaningful_difference_validator=_MeaningfulDifference(),
            regeneration_context=None,
            node_timeout_seconds=self.node_timeout_seconds,
        )
        runtime = V3LangGraphRuntime(create_v3_graph())
        started_ns = time.monotonic_ns()
        graph_result = await runtime.ainvoke(graph_input)
        elapsed_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        return CaseRunResult(
            case=scenario.case,
            scenario=scenario,
            architecture_code=ARCHITECTURE_CODE,
            script=script,
            graph_result=graph_result,
            invocations=tuple(scripted.calls)
            if scripted is not None
            else _audit_invocations(graph_result),
            wall_clock_ms=elapsed_ms,
        )


__all__ = [
    "ARCHITECTURE_CODE",
    "DEFAULT_NODE_TIMEOUT_SECONDS",
    "EVAL_MODEL_CODE",
    "CaseRunResult",
    "MultiAgentRunner",
]
