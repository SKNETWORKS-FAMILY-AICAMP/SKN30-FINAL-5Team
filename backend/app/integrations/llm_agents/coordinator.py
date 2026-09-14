"""Single-call Coordinator adapter bound to V3 CoordinatorInput and PlanSpec."""

from __future__ import annotations

from pydantic import ValidationError

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    PLAN_SPEC_SCHEMA_VERSION,
    ConstraintEnvelope,
    CoordinatorInput,
    PlanSpec,
    ProposalReference,
    SpecialistAgentProposal,
)
from backend.app.integrations.llm_agents.canonicalization import canonical_plan_values
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.payload import coordinator_payload
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS, messages_for
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker

_SERVER_OWNED_PLAN_FIELDS = (
    "schema_version",
    "envelope_hash",
    "pool_hash",
    "requested_duration_minutes",
    "estimated_duration_seconds",
    "proposal_references",
    "repair_attempt",
    "plan_hash",
)


def _canonical_plan_from_model(
    values: dict[str, object], *, coordinator_input: CoordinatorInput
) -> PlanSpec:
    """Attach immutable orchestration identity to the Coordinator's choices."""

    canonical = canonical_plan_values(values)
    canonical.update(
        envelope_hash=coordinator_input.constraint_envelope.envelope_hash,
        pool_hash=coordinator_input.exercise_pool.pool_hash,
        requested_duration_minutes=(
            coordinator_input.constraint_envelope.requested_duration_minutes
        ),
        # PlanSpec records the requested-duration claim. Compilation replaces
        # it with the catalog-measured duration before integrity validation.
        estimated_duration_seconds=(
            coordinator_input.constraint_envelope.requested_duration_minutes * 60
        ),
        proposal_references=tuple(
            ProposalReference(
                agent_type_code=proposal.agent_type_code,
                proposal_hash=proposal.proposal_hash,
            )
            for proposal in coordinator_input.proposals
        ),
        repair_attempt=coordinator_input.repair_attempt,
    )
    return PlanSpec.create(**canonical)


class LangChainCoordinatorAdapter:
    """Return one validated PlanSpec without tools, retrieval, or repair loops."""

    def __init__(self, *, invoker: StructuredChatInvoker) -> None:
        self._invoker = invoker

    @property
    def prompt_version(self) -> str:
        return ROLE_PROMPTS[LlmAgentRoleCode.COORDINATOR].version

    @property
    def output_schema_version(self) -> str:
        return PLAN_SPEC_SCHEMA_VERSION

    def coordinate(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
    ) -> StructuredAgentResult[PlanSpec]:
        return self._build_and_invoke(
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            proposals=proposals,
            repair_attempt=0,
            repair_violation_codes=(),
        )

    def repair(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
        repair_violation_codes: tuple[str, ...],
    ) -> StructuredAgentResult[PlanSpec]:
        """Perform one structured repair call; loop control belongs to LangGraph V3-A3."""

        return self._build_and_invoke(
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            proposals=proposals,
            repair_attempt=1,
            repair_violation_codes=repair_violation_codes,
        )

    async def acoordinate(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
    ) -> StructuredAgentResult[PlanSpec]:
        return await self._build_and_ainvoke(
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            proposals=proposals,
            repair_attempt=0,
            repair_violation_codes=(),
        )

    async def arepair(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
        repair_violation_codes: tuple[str, ...],
    ) -> StructuredAgentResult[PlanSpec]:
        return await self._build_and_ainvoke(
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            proposals=proposals,
            repair_attempt=1,
            repair_violation_codes=repair_violation_codes,
        )

    def _build_and_invoke(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
        repair_attempt: int,
        repair_violation_codes: tuple[str, ...],
    ) -> StructuredAgentResult[PlanSpec]:
        role_code = LlmAgentRoleCode.COORDINATOR
        prompt = ROLE_PROMPTS[role_code]
        try:
            coordinator_input = CoordinatorInput(
                constraint_envelope=constraint_envelope,
                exercise_pool=exercise_pool,
                proposals=proposals,
                repair_attempt=repair_attempt,
                repair_violation_codes=repair_violation_codes,
            )
            payload = coordinator_payload(coordinator_input)
        except (ValidationError, ValueError):
            return self._invoker.failure(
                code=LlmAgentFailureCode.DOMAIN_INVALID,
                role_code=role_code,
                prompt_version=prompt.version,
                output_schema_version=self.output_schema_version,
                attempt_count=0,
            )

        def validate(output: PlanSpec) -> PlanSpec:
            output.validate_against(coordinator_input)
            return output

        return self._invoker.invoke(
            role_code=role_code,
            prompt_version=prompt.version,
            output_schema_version=self.output_schema_version,
            output_schema=PlanSpec,
            messages=messages_for(
                prompt,
                output_schema_version=self.output_schema_version,
                payload=payload,
            ),
            domain_validator=validate,
            canonical_factory=lambda values: _canonical_plan_from_model(
                values, coordinator_input=coordinator_input
            ),
            server_owned_fields=_SERVER_OWNED_PLAN_FIELDS,
        )

    async def _build_and_ainvoke(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        proposals: tuple[SpecialistAgentProposal, ...],
        repair_attempt: int,
        repair_violation_codes: tuple[str, ...],
    ) -> StructuredAgentResult[PlanSpec]:
        role_code = LlmAgentRoleCode.COORDINATOR
        prompt = ROLE_PROMPTS[role_code]
        try:
            coordinator_input = CoordinatorInput(
                constraint_envelope=constraint_envelope,
                exercise_pool=exercise_pool,
                proposals=proposals,
                repair_attempt=repair_attempt,
                repair_violation_codes=repair_violation_codes,
            )
            payload = coordinator_payload(coordinator_input)
        except (ValidationError, ValueError):
            return self._invoker.failure(
                code=LlmAgentFailureCode.DOMAIN_INVALID,
                role_code=role_code,
                prompt_version=prompt.version,
                output_schema_version=self.output_schema_version,
                attempt_count=0,
            )

        def validate(output: PlanSpec) -> PlanSpec:
            output.validate_against(coordinator_input)
            return output

        return await self._invoker.ainvoke(
            role_code=role_code,
            prompt_version=prompt.version,
            output_schema_version=self.output_schema_version,
            output_schema=PlanSpec,
            messages=messages_for(
                prompt,
                output_schema_version=self.output_schema_version,
                payload=payload,
            ),
            domain_validator=validate,
            canonical_factory=lambda values: _canonical_plan_from_model(
                values, coordinator_input=coordinator_input
            ),
            server_owned_fields=_SERVER_OWNED_PLAN_FIELDS,
        )


__all__ = ["LangChainCoordinatorAdapter"]
