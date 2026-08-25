"""Private V3 shadow composition root over immutable synthetic inputs."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Final, cast

from langchain_core.language_models import BaseChatModel

from backend.app.core.config import Settings
from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import (
    CompiledPlan,
    DeterministicFallbackPlanSpec,
    compile_plan,
)
from backend.app.domain.agents.v3_conflicts import (
    ConflictDetectionResult,
    detect_proposal_conflicts,
)
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    ConstraintEnvelope,
    CoordinatorInput,
    PlanSpec,
    RegenerationContext,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.domain.agents.v3_orchestration import (
    DeterministicFallbackProvider,
    FallbackRequest,
    GraphTerminalStatusCode,
)
from backend.app.domain.agents.v3_validation import (
    IntegrityValidationContext,
    IntegrityValidationResult,
    IntegrityValidationStatusCode,
    validate_plan_integrity,
)
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.app.integrations.langgraph.state import (
    ConflictDetectorPort,
    IntegrityValidatorPort,
    SpecialistPort,
    V3GraphInput,
    V3GraphResult,
)
from backend.app.integrations.llm_agents.coordinator import LangChainCoordinatorAdapter
from backend.app.integrations.llm_agents.openai import build_openai_shadow_chat_model
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.app.integrations.llm_agents.specialists import (
    FeasibilityAgentAdapter,
    RecoveryAgentAdapter,
    TrainingAgentAdapter,
)
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowExecutionError,
    V3ShadowExecutionRequest,
    V3ShadowExecutionResult,
    V3ShadowFailureCode,
    V3ShadowInvocationMetric,
    V3ShadowInvocationPhaseCode,
    V3ShadowInvocationStatusCode,
    V3ShadowPlanProjection,
    V3ShadowRoleCode,
    V3ShadowSafetyMetric,
    V3ShadowSafetyViolationCode,
    V3ShadowStructuredOutputStatusCode,
    V3ShadowUsageMetric,
    V3ShadowUsageStatusCode,
)

_RUN_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class V3ShadowRuntimeVersions:
    graph_version: str = "v3-langgraph-shadow-v1"
    compiler_version: str = "v3-plan-compiler-v1"
    validator_version: str = "v3-integrity-validator-v1"
    fallback_version: str = "v3-deterministic-fallback-v1"


@dataclass(frozen=True, slots=True)
class V3ShadowPricingReference:
    version: str
    model_version: str
    currency_code: str
    input_cost_per_token: Decimal
    output_cost_per_token: Decimal

    def __post_init__(self) -> None:
        if self.input_cost_per_token < 0 or self.output_cost_per_token < 0:
            raise ValueError("pricing values cannot be negative")


@dataclass(slots=True)
class _ExecutionContext:
    proposals: tuple[SpecialistAgentProposal, ...] = ()
    repair_violation_codes: tuple[str, ...] = ()
    repair_attempt: int = 0
    fallback_compilation: bool = False


@dataclass(frozen=True, slots=True)
class _ConflictReport:
    canonical: ConflictDetectionResult
    conflict_codes: tuple[str, ...]
    affected_agent_types: tuple[SpecialistAgentTypeCode, ...]
    hard_constraint_weakened: bool


@dataclass(slots=True)
class _ConflictDetector:
    envelope: ConstraintEnvelope
    pool: ExercisePoolSnapshot
    context: _ExecutionContext

    def detect(self, proposals: tuple[SpecialistAgentProposal, ...]) -> _ConflictReport:
        canonical = detect_proposal_conflicts(proposals, self.envelope, self.pool)
        self.context.proposals = proposals
        codes = tuple(item.code.value for item in canonical.violations)
        return _ConflictReport(
            canonical=canonical,
            conflict_codes=codes,
            affected_agent_types=canonical.review_target_agent_types,
            hard_constraint_weakened=bool(codes and not canonical.review_target_agent_types),
        )


@dataclass(slots=True)
class _Compiler:
    envelope: ConstraintEnvelope
    pool: ExercisePoolSnapshot
    context: _ExecutionContext
    version: str

    def compile(self, source: PlanSpec | DeterministicFallbackPlanSpec) -> CompiledPlan:
        if isinstance(source, DeterministicFallbackPlanSpec):
            self.context.fallback_compilation = True
            self.context.repair_attempt = 0
            return compile_plan(
                source,
                envelope=self.envelope,
                pool=self.pool,
                compiler_version=self.version,
            )
        self.context.fallback_compilation = False
        self.context.repair_attempt = source.repair_attempt
        coordinator_input = CoordinatorInput(
            constraint_envelope=self.envelope,
            exercise_pool=self.pool,
            proposals=self.context.proposals,
            repair_attempt=source.repair_attempt,
            repair_violation_codes=(
                self.context.repair_violation_codes if source.repair_attempt == 1 else ()
            ),
        )
        return compile_plan(
            source,
            envelope=self.envelope,
            pool=self.pool,
            compiler_version=self.version,
            coordinator_input=coordinator_input,
        )


@dataclass(frozen=True, slots=True)
class _IntegrityReport:
    canonical: IntegrityValidationResult
    passed: bool
    repairable: bool
    violation_codes: tuple[str, ...]


@dataclass(slots=True)
class _IntegrityValidator:
    context: _ExecutionContext
    version: str

    def validate(
        self,
        compiled_plan: object,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
    ) -> _IntegrityReport:
        typed_plan = compiled_plan if isinstance(compiled_plan, CompiledPlan) else None
        canonical = validate_plan_integrity(
            typed_plan,
            envelope=constraint_envelope,
            pool=exercise_pool,
            repair_attempt=self.context.repair_attempt,
            validator_version=self.version,
            context=IntegrityValidationContext(
                fallback_plan_validation=self.context.fallback_compilation
            ),
        )
        codes = tuple(item.code.value for item in canonical.violations)
        self.context.repair_violation_codes = tuple(sorted(codes))
        return _IntegrityReport(
            canonical=canonical,
            passed=canonical.status_code is IntegrityValidationStatusCode.PASS,
            repairable=canonical.status_code is IntegrityValidationStatusCode.REPAIRABLE,
            violation_codes=codes,
        )


@dataclass(slots=True)
class _Fallback:
    provider: DeterministicFallbackProvider
    version: str

    def build(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        failure_codes: tuple[str, ...],
    ) -> DeterministicFallbackPlanSpec | None:
        del failure_codes
        request = FallbackRequest.create(
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            fallback_version=self.version,
        )
        result = self.provider.generate(request)
        if result is not None and result.fallback_version != self.version:
            return None
        return result


class _NoFallbackProvider:
    def generate(self, request: FallbackRequest) -> DeterministicFallbackPlanSpec | None:
        del request
        return None


class _MeaningfulDifference:
    def validate(self, plan_spec: PlanSpec, context: RegenerationContext) -> bool:
        current_ids = tuple(item.exercise_id for item in plan_spec.exercise_prescriptions)
        return plan_spec.plan_hash != context.previous_plan_hash and (
            current_ids != context.previous_exercise_ids
        )


@dataclass(slots=True)
class V3ShadowRuntime:
    settings: Settings
    graph_runtime: V3LangGraphRuntime
    invoker: StructuredChatInvoker
    fallback_provider: DeterministicFallbackProvider = field(default_factory=_NoFallbackProvider)
    versions: V3ShadowRuntimeVersions = field(default_factory=V3ShadowRuntimeVersions)
    pricing_reference: V3ShadowPricingReference | None = None

    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult:
        started_ns = time.monotonic_ns()
        self._validate_request(request, constraint_envelope, exercise_pool)
        context = _ExecutionContext()
        graph_input = V3GraphInput(
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            graph_version=request.graph_version,
            prompt_version=request.prompt_version,
            model_version=request.model_version,
            policy_version=request.policy_version,
            catalog_version=request.catalog_version,
            snapshot_is_fresh=request.snapshot_is_fresh,
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
            conflict_detector=cast(
                ConflictDetectorPort,
                _ConflictDetector(constraint_envelope, exercise_pool, context),
            ),
            compiler=_Compiler(
                constraint_envelope,
                exercise_pool,
                context,
                self.versions.compiler_version,
            ),
            validator=cast(
                IntegrityValidatorPort,
                _IntegrityValidator(context, self.versions.validator_version),
            ),
            fallback=_Fallback(self.fallback_provider, self.versions.fallback_version),
            meaningful_difference_validator=_MeaningfulDifference(),
            regeneration_context=regeneration_context,
            node_timeout_seconds=self.settings.llm_agents_timeout_seconds,
        )
        graph_result = await self.graph_runtime.ainvoke(graph_input)
        total_latency_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        return self._project_result(request, graph_result, total_latency_ms)

    def _validate_request(
        self,
        request: V3ShadowExecutionRequest,
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
    ) -> None:
        if not request.snapshot_is_fresh:
            raise V3ShadowExecutionError(V3ShadowFailureCode.INPUT_STALE)
        if (
            request.graph_version != self.versions.graph_version
            or request.policy_version != envelope.policy_version
            or request.catalog_version != envelope.catalog_version
            or request.catalog_version != pool.catalog_version
            or pool.constraint_envelope_hash != envelope.envelope_hash
            or request.provider_code != "OPENAI"
            or request.model_version != self.settings.llm_agents_model_code
        ):
            raise V3ShadowExecutionError(V3ShadowFailureCode.INPUT_INVALID)
        if (
            envelope.plan_generation_allowed
            and envelope.safety_required_action_code is None
            and self.invoker.chat_model is None
        ):
            raise V3ShadowExecutionError(V3ShadowFailureCode.PROVIDER_NOT_CONFIGURED)

    def _project_result(
        self,
        request: V3ShadowExecutionRequest,
        graph: V3GraphResult,
        total_latency_ms: int,
    ) -> V3ShadowExecutionResult:
        metrics = tuple(
            V3ShadowInvocationMetric(
                role_code=V3ShadowRoleCode(item.role_code),
                phase_code=V3ShadowInvocationPhaseCode(item.phase_code),
                status_code=V3ShadowInvocationStatusCode(item.status_code),
                attempt_count=item.attempt_count,
                latency_ms=item.latency_ms,
                provider_code=request.provider_code,
                model_version=request.model_version,
                prompt_version=request.prompt_version,
                output_schema_version=(
                    "plan-spec-v1"
                    if item.role_code == "COORDINATOR"
                    else "specialist-agent-proposal-v1"
                ),
                failure_code=item.failure_code,
                input_token_count=item.input_token_count,
                output_token_count=item.output_token_count,
            )
            for item in sorted(
                graph.invocation_audits,
                key=lambda value: (
                    tuple(V3ShadowRoleCode).index(V3ShadowRoleCode(value.role_code)),
                    tuple(V3ShadowInvocationPhaseCode).index(
                        V3ShadowInvocationPhaseCode(value.phase_code)
                    ),
                ),
            )
        )
        safety = self._safety_metric(graph)
        terminal = self._terminal_status(graph.status_code)
        plan = (
            self._plan_projection(graph.compiled_plan)
            if terminal is GraphTerminalStatusCode.COMPLETED
            else None
        )
        usage = self._usage_metric(metrics, request.model_version)
        fallback_used = graph.used_fallback and graph.fallback_plan_spec is not None
        return V3ShadowExecutionResult.create(
            scenario_code=request.case.scenario_code,
            case_hash=request.case.case_hash,
            graph_version=request.graph_version,
            policy_version=request.policy_version,
            catalog_version=request.catalog_version,
            prompt_version=request.prompt_version,
            provider_code=request.provider_code,
            model_version=request.model_version,
            terminal_status_code=terminal,
            plan=plan,
            safety=safety,
            structured_output_status_code=(
                V3ShadowStructuredOutputStatusCode.SUCCEEDED
                if all(
                    item.status_code is V3ShadowInvocationStatusCode.SUCCEEDED for item in metrics
                )
                else V3ShadowStructuredOutputStatusCode.FAILED
            ),
            constraint_violation_codes=tuple(
                sorted(
                    {
                        code
                        for validation in graph.integrity_validations
                        for code in validation.violation_codes
                    }
                )
            ),
            invocation_metrics=metrics,
            review_attempt_count=sum(
                item.phase_code is V3ShadowInvocationPhaseCode.REVIEW for item in metrics
            ),
            repair_attempt_count=graph.repair_attempts,
            fallback_used=fallback_used,
            fallback_code="DETERMINISTIC_FALLBACK_USED" if fallback_used else None,
            fallback_version=self.versions.fallback_version if fallback_used else None,
            failure_codes=tuple(sorted(set(graph.failure_codes))),
            total_latency_ms=max(
                total_latency_ms,
                max((item.latency_ms for item in metrics), default=0),
            ),
            usage=usage,
        )

    def _safety_metric(self, graph: V3GraphResult) -> V3ShadowSafetyMetric:
        violations: set[V3ShadowSafetyViolationCode] = set()
        if graph.status_code == "STOP_AND_SEEK_HELP" and graph.compiled_plan is not None:
            violations.add(V3ShadowSafetyViolationCode.SAFETY_VETO_OVERRIDDEN)
        if graph.status_code in {"STOP_AND_SEEK_HELP", "REST"} and graph.invocation_audits:
            violations.add(V3ShadowSafetyViolationCode.PROVIDER_CALLED_AFTER_SAFETY_TERMINAL)
        if len(graph.round_one_proposals) < len(SPECIALIST_AGENT_ORDER) and any(
            item.role_code == "COORDINATOR" for item in graph.invocation_audits
        ):
            violations.add(V3ShadowSafetyViolationCode.PARTIAL_PROPOSALS_COORDINATED)
        integrity_map = {
            "EXERCISE_OUTSIDE_POOL": V3ShadowSafetyViolationCode.EXERCISE_POOL_MEMBERSHIP_VIOLATED,
            "MANDATORY_EXERCISE_MISSING": V3ShadowSafetyViolationCode.MANDATORY_EXERCISE_MISSING,
            "REQUESTED_DURATION_MISMATCH": V3ShadowSafetyViolationCode.DURATION_CONSTRAINT_VIOLATED,
            "RECOVERY_CEILING_EXCEEDED": V3ShadowSafetyViolationCode.RECOVERY_CEILING_EXCEEDED,
        }
        for validation in graph.integrity_validations:
            for code in validation.violation_codes:
                mapped = integrity_map.get(code)
                if mapped is not None:
                    violations.add(mapped)
        canonical = tuple(code for code in V3ShadowSafetyViolationCode if code in violations)
        return V3ShadowSafetyMetric(invariant_passed=not canonical, violation_codes=canonical)

    def _usage_metric(
        self,
        metrics: tuple[V3ShadowInvocationMetric, ...],
        model_version: str,
    ) -> V3ShadowUsageMetric:
        provider_calls = sum(item.attempt_count for item in metrics)
        if provider_calls == 0:
            return V3ShadowUsageMetric(
                status_code=V3ShadowUsageStatusCode.NOT_APPLICABLE,
                provider_call_count=0,
            )
        if not metrics or any(item.input_token_count is None for item in metrics):
            return V3ShadowUsageMetric(
                status_code=V3ShadowUsageStatusCode.UNAVAILABLE,
                provider_call_count=provider_calls,
            )
        input_tokens = sum(item.input_token_count or 0 for item in metrics)
        output_tokens = sum(item.output_token_count or 0 for item in metrics)
        pricing = self.pricing_reference
        if pricing is not None and pricing.model_version == model_version:
            return V3ShadowUsageMetric(
                status_code=V3ShadowUsageStatusCode.COMPLETE,
                provider_call_count=provider_calls,
                input_token_count=input_tokens,
                output_token_count=output_tokens,
                decision_cost=(
                    input_tokens * pricing.input_cost_per_token
                    + output_tokens * pricing.output_cost_per_token
                ),
                currency_code=pricing.currency_code,
                pricing_reference_version=pricing.version,
            )
        return V3ShadowUsageMetric(
            status_code=V3ShadowUsageStatusCode.COMPLETE,
            provider_call_count=provider_calls,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
        )

    @staticmethod
    def _terminal_status(status_code: str) -> GraphTerminalStatusCode:
        if status_code == "SUCCEEDED":
            return GraphTerminalStatusCode.COMPLETED
        try:
            return GraphTerminalStatusCode(status_code)
        except ValueError:
            return GraphTerminalStatusCode.FAILED

    @staticmethod
    def _plan_projection(compiled: object | None) -> V3ShadowPlanProjection | None:
        if not isinstance(compiled, CompiledPlan):
            return None
        return V3ShadowPlanProjection(
            action_code=compiled.action_code.value,
            requested_duration_minutes=compiled.requested_duration_minutes,
            estimated_duration_seconds=compiled.estimated_duration_seconds,
            prescriptions=tuple(item.prescription for item in compiled.exercises),
            plan_hash=compiled.compiled_plan_hash,
        )


def build_v3_shadow_runtime(
    settings: Settings,
    *,
    allow_provider_calls: bool,
    chat_model: BaseChatModel | None = None,
    fallback_provider: DeterministicFallbackProvider | None = None,
    versions: V3ShadowRuntimeVersions | None = None,
    pricing_reference: V3ShadowPricingReference | None = None,
) -> V3ShadowRuntime:
    """Compose the private runtime without touching FastAPI, SQLAlchemy, or Qdrant."""

    model = chat_model or build_openai_shadow_chat_model(
        settings, allow_provider_calls=allow_provider_calls
    )
    invoker = StructuredChatInvoker(
        chat_model=model,
        model_code=settings.llm_agents_model_code,
        max_attempts=settings.llm_agents_max_attempts,
        use_native_json_schema=chat_model is None and model is not None,
    )
    return V3ShadowRuntime(
        settings=settings,
        graph_runtime=V3LangGraphRuntime(create_v3_graph()),
        invoker=invoker,
        fallback_provider=fallback_provider or _NoFallbackProvider(),
        versions=versions or V3ShadowRuntimeVersions(),
        pricing_reference=pricing_reference,
    )


def write_shadow_results_jsonl(
    workspace_root: Path,
    *,
    run_id: str,
    results: tuple[V3ShadowExecutionResult, ...],
) -> Path:
    """Write canonical identifier-free records only under ignored shadow outputs."""

    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be a structured local output code")
    output_root = (workspace_root / "outputs" / "v3-shadow").resolve()
    output_path = (output_root / run_id / "results.jsonl").resolve()
    if output_root not in output_path.parents:
        raise ValueError("shadow output path escaped the ignored output root")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for result in results:
            stream.write(
                json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            stream.write("\n")
    return output_path


__all__ = [
    "V3ShadowPricingReference",
    "V3ShadowRuntime",
    "V3ShadowRuntimeVersions",
    "build_v3_shadow_runtime",
    "write_shadow_results_jsonl",
]
