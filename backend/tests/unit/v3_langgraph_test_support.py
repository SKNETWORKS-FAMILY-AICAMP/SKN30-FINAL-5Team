from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    CoordinatorInput,
    PlanSpec,
    RegenerationContext,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
)
from backend.app.integrations.langgraph.state import V3GraphInput
from backend.app.integrations.llm_agents.models import StructuredAgentResult
from backend.tests.unit.test_v3_agent_contracts import (
    envelope as make_envelope,
)
from backend.tests.unit.test_v3_agent_contracts import (
    pool as make_pool,
)
from backend.tests.unit.test_v3_coordinator_contracts import plan, proposals


@dataclass(frozen=True)
class Conflict:
    conflict_codes: tuple[str, ...] = ()
    affected_agent_types: tuple[SpecialistAgentTypeCode, ...] = ()
    hard_constraint_weakened: bool = False


class ConflictDetector:
    def __init__(self, reports: list[Conflict] | None = None) -> None:
        self.reports = reports or [Conflict()]
        self.calls = 0

    def detect(self, values: tuple[SpecialistAgentProposal, ...]) -> Conflict:
        assert len(values) == 3
        index = min(self.calls, len(self.reports) - 1)
        self.calls += 1
        return self.reports[index]


class Specialist:
    def __init__(
        self,
        agent_type: SpecialistAgentTypeCode,
        output: SpecialistAgentProposal,
        *,
        barrier: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        active: list[SpecialistAgentTypeCode] | None = None,
        timeout: bool = False,
        review_timeout: bool = False,
    ) -> None:
        self.agent_type = agent_type
        self.output = output
        self.barrier = barrier
        self.release = release
        self.active = active
        self.timeout = timeout
        self.review_timeout = review_timeout
        self.propose_calls = 0
        self.review_calls = 0
        self.cancelled = False

    async def apropose(self, **_: object) -> StructuredAgentResult[SpecialistAgentProposal]:
        self.propose_calls += 1
        if self.active is not None:
            self.active.append(self.agent_type)
            if len(self.active) == 3 and self.barrier is not None:
                self.barrier.set()
        if self.timeout:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self.barrier is not None:
            await self.barrier.wait()
        if self.release is not None:
            await self.release.wait()
        return StructuredAgentResult.success(self.output)

    async def areview(self, **_: object) -> StructuredAgentResult[SpecialistAgentProposal]:
        self.review_calls += 1
        if self.review_timeout:
            await asyncio.Event().wait()
        return StructuredAgentResult.success(self.output)


class Coordinator:
    def __init__(self, *, timeout: bool = False) -> None:
        self.initial_calls = 0
        self.repair_calls = 0
        self.timeout = timeout
        self.proposal_orders: list[tuple[SpecialistAgentTypeCode, ...]] = []

    async def acoordinate(self, **kwargs: object) -> StructuredAgentResult[PlanSpec]:
        self.initial_calls += 1
        if self.timeout:
            await asyncio.Event().wait()
        received = kwargs["proposals"]
        self.proposal_orders.append(tuple(item.agent_type_code for item in received))
        current_input = CoordinatorInput(
            constraint_envelope=kwargs["constraint_envelope"],
            exercise_pool=kwargs["exercise_pool"],
            proposals=received,
            repair_attempt=0,
        )
        return StructuredAgentResult.success(plan(current_input))

    async def arepair(self, **kwargs: object) -> StructuredAgentResult[PlanSpec]:
        self.repair_calls += 1
        current_input = CoordinatorInput(
            constraint_envelope=kwargs["constraint_envelope"],
            exercise_pool=kwargs["exercise_pool"],
            proposals=kwargs["proposals"],
            repair_attempt=1,
            repair_violation_codes=kwargs["repair_violation_codes"],
        )
        return StructuredAgentResult.success(plan(current_input))


class Compiler:
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, plan_spec: PlanSpec) -> object:
        self.calls += 1
        return plan_spec


@dataclass(frozen=True)
class Validation:
    passed: bool
    repairable: bool = False
    violation_codes: tuple[str, ...] = ()


class Validator:
    def __init__(self, results: list[Validation] | None = None) -> None:
        self.results = results or [Validation(True)]
        self.calls = 0

    def validate(self, compiled_plan: object, **_: object) -> Validation:
        assert isinstance(compiled_plan, PlanSpec)
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        return self.results[index]


class Fallback:
    def __init__(self, fallback_plan: PlanSpec | None) -> None:
        self.plan = fallback_plan
        self.calls = 0

    def build(self, **_: object) -> PlanSpec | None:
        self.calls += 1
        return self.plan


class Difference:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls = 0

    def validate(self, plan_spec: PlanSpec, context: RegenerationContext) -> bool:
        del plan_spec, context
        self.calls += 1
        return self.result


def graph_input(
    *,
    current_envelope: ConstraintEnvelope | None = None,
    current_pool: ExercisePoolSnapshot | None = None,
    specialists: dict[SpecialistAgentTypeCode, Specialist] | None = None,
    coordinator: Coordinator | None = None,
    detector: ConflictDetector | None = None,
    validator: Validator | None = None,
    fallback: Fallback | None = None,
    regeneration_context: RegenerationContext | None = None,
    difference: Difference | None = None,
    snapshot_is_fresh: bool = True,
    timeout: float = 0.1,
) -> V3GraphInput:
    if current_envelope is None:
        current_envelope = make_envelope()
    if current_pool is None:
        current_pool = make_pool(current_envelope)
    current_proposals = proposals(current_envelope, current_pool)
    specialist_map = specialists or {
        item.agent_type_code: Specialist(item.agent_type_code, item) for item in current_proposals
    }
    fallback_plan = None
    if current_envelope.plan_generation_allowed:
        fallback_plan = plan(
            CoordinatorInput(
                constraint_envelope=current_envelope,
                exercise_pool=current_pool,
                proposals=current_proposals,
                repair_attempt=0,
            )
        )
    return V3GraphInput(
        constraint_envelope=current_envelope,
        exercise_pool=current_pool,
        graph_version="v3-langgraph-v1",
        prompt_version="v3-prompts-v1",
        model_version="fake-model-v1",
        policy_version=current_envelope.policy_version,
        catalog_version=current_envelope.catalog_version,
        snapshot_is_fresh=snapshot_is_fresh,
        specialists=specialist_map,
        coordinator=coordinator or Coordinator(),
        conflict_detector=detector or ConflictDetector(),
        compiler=Compiler(),
        validator=validator or Validator(),
        fallback=fallback or Fallback(fallback_plan),
        meaningful_difference_validator=difference or Difference(),
        regeneration_context=regeneration_context,
        node_timeout_seconds=timeout,
    )


__all__ = [
    "Conflict",
    "ConflictDetector",
    "Coordinator",
    "Difference",
    "Fallback",
    "Specialist",
    "Validation",
    "Validator",
    "graph_input",
]
