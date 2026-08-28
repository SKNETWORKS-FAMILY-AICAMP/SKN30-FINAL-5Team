"""Minimal, identifier-free state and injected ports for the V3 graph."""

from __future__ import annotations

import operator
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Protocol, TypedDict, runtime_checkable

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    PlanSpec,
    RegenerationContext,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.llm_agents.models import LlmInvocationTelemetry, StructuredAgentResult


@runtime_checkable
class SpecialistPort(Protocol):
    async def apropose(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> StructuredAgentResult[SpecialistAgentProposal]: ...


class CoordinatorPort(Protocol):
    async def acoordinate(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
    ) -> StructuredAgentResult[PlanSpec]: ...

    async def arepair(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
        repair_violation_codes: tuple[str, ...],
    ) -> StructuredAgentResult[PlanSpec]: ...


class CompilationPort(Protocol):
    def compile(
        self,
        plan_spec: PlanSpec | DeterministicFallbackPlanSpec,
        *,
        proposals: tuple[SpecialistAgentProposal, ...],
    ) -> object: ...


class IntegrityValidation(Protocol):
    passed: bool
    repairable: bool
    violation_codes: tuple[str, ...]


class IntegrityValidatorPort(Protocol):
    def validate(
        self,
        compiled_plan: object,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
    ) -> IntegrityValidation: ...


class FallbackPort(Protocol):
    def build(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        failure_codes: tuple[str, ...],
    ) -> DeterministicFallbackPlanSpec | None: ...


class MeaningfulDifferencePort(Protocol):
    def validate(self, plan_spec: PlanSpec, context: RegenerationContext) -> bool: ...


@dataclass(frozen=True, slots=True)
class V3GraphInput:
    """Application-loaded immutable graph boundary; it contains no DB handles or PII."""

    constraint_envelope: ConstraintEnvelope
    exercise_pool: ExercisePoolSnapshot
    graph_version: str
    prompt_version: str
    model_version: str
    policy_version: str
    catalog_version: str
    snapshot_is_fresh: bool
    specialists: Mapping[SpecialistAgentTypeCode, SpecialistPort]
    coordinator: CoordinatorPort
    compiler: CompilationPort
    validator: IntegrityValidatorPort
    fallback: FallbackPort
    meaningful_difference_validator: MeaningfulDifferencePort
    regeneration_context: RegenerationContext | None = None
    node_timeout_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    agent_type: SpecialistAgentTypeCode
    proposal: SpecialistAgentProposal | None = None
    failure_code: str | None = None
    telemetry: LlmInvocationTelemetry | None = None


@dataclass(frozen=True, slots=True)
class InvocationAudit:
    role_code: str
    phase_code: str
    status_code: str
    attempt_count: int
    latency_ms: int
    input_token_count: int | None = None
    output_token_count: int | None = None
    provider_usage_present: bool = False
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class V3GraphResult:
    status_code: str
    graph_version: str
    plan_spec: PlanSpec | None
    compiled_plan: object | None
    failure_codes: tuple[str, ...]
    used_fallback: bool
    repair_attempts: int
    round_one_proposals: tuple[SpecialistAgentProposal, ...] = ()
    coordinator_initial_plan: PlanSpec | None = None
    coordinator_repair_plan: PlanSpec | None = None
    fallback_plan_spec: DeterministicFallbackPlanSpec | None = None
    integrity_validations: tuple[IntegrityValidation, ...] = ()
    compiled_plans: tuple[object, ...] = ()
    invocation_audits: tuple[InvocationAudit, ...] = ()


class V3GraphState(TypedDict, total=False):
    graph_input: V3GraphInput
    entry_failure_code: str
    agent_outcomes: Annotated[tuple[AgentOutcome, ...], operator.add]
    proposals: tuple[SpecialistAgentProposal, ...]
    round_one_proposals: tuple[SpecialistAgentProposal, ...]
    invocation_audits: Annotated[tuple[InvocationAudit, ...], operator.add]
    plan_spec: PlanSpec | None
    fallback_plan_spec: DeterministicFallbackPlanSpec | None
    compiled_plan: object | None
    integrity_validation: IntegrityValidation
    integrity_validations: Annotated[tuple[IntegrityValidation, ...], operator.add]
    compiled_plans: Annotated[tuple[object, ...], operator.add]
    coordinator_initial_plan: PlanSpec | None
    coordinator_repair_plan: PlanSpec | None
    repair_attempts: int
    failure_codes: tuple[str, ...]
    used_fallback: bool
    result: V3GraphResult


__all__ = [
    "AgentOutcome",
    "CompilationPort",
    "CoordinatorPort",
    "FallbackPort",
    "IntegrityValidation",
    "IntegrityValidatorPort",
    "InvocationAudit",
    "MeaningfulDifferencePort",
    "SpecialistPort",
    "V3GraphInput",
    "V3GraphResult",
    "V3GraphState",
]
