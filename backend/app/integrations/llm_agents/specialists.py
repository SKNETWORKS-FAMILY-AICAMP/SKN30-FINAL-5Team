"""Training, Recovery, and Feasibility adapters bound to the approved V3 contracts."""

from __future__ import annotations

from pydantic import ValidationError

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION,
    ConstraintEnvelope,
    RegenerationContext,
    SpecialistAgentInput,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    TrainingNeedsInputReasonCode,
    TrainingPlanFeasibilityCode,
    V3ProposalStatusCode,
)
from backend.app.domain.agents.v3_orchestration import (
    DeterministicFallbackProvider,
    FallbackRequest,
)
from backend.app.integrations.llm_agents.canonicalization import canonical_proposal_values
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.payload import specialist_payload
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS, messages_for
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker


class LangChainSpecialistAdapter:
    """Run one approved role and revalidate its proposal against the shared input."""

    def __init__(
        self,
        *,
        role_code: LlmAgentRoleCode,
        invoker: StructuredChatInvoker,
        feasibility_provider: DeterministicFallbackProvider | None = None,
        fallback_version: str | None = None,
    ) -> None:
        if role_code not in {
            LlmAgentRoleCode.TRAINING,
            LlmAgentRoleCode.RECOVERY,
            LlmAgentRoleCode.FEASIBILITY,
        }:
            raise ValueError("specialist adapter requires a specialist role")
        self.role_code = role_code
        self.agent_type_code = SpecialistAgentTypeCode(role_code.value)
        self._invoker = invoker
        self._feasibility_provider = feasibility_provider
        self._fallback_version = fallback_version

    def _training_feasibility_code(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
    ) -> TrainingPlanFeasibilityCode | None:
        if self.role_code is not LlmAgentRoleCode.TRAINING:
            return None
        if self._feasibility_provider is None or self._fallback_version is None:
            return TrainingPlanFeasibilityCode.UNPROVEN
        try:
            request = FallbackRequest.create(
                constraint_envelope=constraint_envelope,
                exercise_pool=exercise_pool,
                fallback_version=self._fallback_version,
            )
            candidate = self._feasibility_provider.generate(request)
        except Exception:
            # Preflight is advisory evidence. Its failure must not suppress the
            # normal provider path or be misreported as proof of infeasibility.
            return TrainingPlanFeasibilityCode.UNPROVEN
        if (
            candidate is None
            or candidate.fallback_version != self._fallback_version
            or candidate.envelope_hash != constraint_envelope.envelope_hash
            or candidate.pool_hash != exercise_pool.pool_hash
        ):
            return TrainingPlanFeasibilityCode.UNPROVEN
        return TrainingPlanFeasibilityCode.CANDIDATE_AVAILABLE

    @staticmethod
    def _validate_training_decline(
        output: SpecialistAgentProposal,
        feasibility_code: TrainingPlanFeasibilityCode | None,
    ) -> None:
        if not (
            output.agent_type_code is SpecialistAgentTypeCode.TRAINING
            and output.proposal_status_code is V3ProposalStatusCode.NEEDS_INPUT
        ):
            return
        if output.reason_codes != (
            TrainingNeedsInputReasonCode.DETERMINISTIC_PLAN_FEASIBILITY_UNPROVEN.value,
        ):
            raise ValueError("TRAINING NEEDS_INPUT requires the stable feasibility reason code")
        if feasibility_code is TrainingPlanFeasibilityCode.CANDIDATE_AVAILABLE:
            raise ValueError(
                "TRAINING cannot return NEEDS_INPUT when a deterministic candidate is available"
            )

    @property
    def prompt_version(self) -> str:
        return ROLE_PROMPTS[self.role_code].version

    @property
    def output_schema_version(self) -> str:
        return SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION

    def propose(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> StructuredAgentResult[SpecialistAgentProposal]:
        prompt = ROLE_PROMPTS[self.role_code]
        try:
            agent_input = SpecialistAgentInput(
                agent_type_code=self.agent_type_code,
                constraint_envelope=constraint_envelope,
                envelope_hash=constraint_envelope.envelope_hash,
                exercise_pool=exercise_pool,
                pool_hash=exercise_pool.pool_hash,
                regeneration_context=regeneration_context,
            )
            feasibility_code = self._training_feasibility_code(
                constraint_envelope=constraint_envelope,
                exercise_pool=exercise_pool,
            )
            payload = specialist_payload(
                agent_input,
                training_plan_feasibility_code=feasibility_code,
            )
        except (ValidationError, ValueError):
            return self._invoker.failure(
                code=LlmAgentFailureCode.DOMAIN_INVALID,
                role_code=self.role_code,
                prompt_version=prompt.version,
                output_schema_version=self.output_schema_version,
                attempt_count=0,
            )

        def validate(output: SpecialistAgentProposal) -> SpecialistAgentProposal:
            agent_input.validate_proposal(output)
            self._validate_training_decline(output, feasibility_code)
            return output

        return self._invoker.invoke(
            role_code=self.role_code,
            prompt_version=prompt.version,
            output_schema_version=self.output_schema_version,
            output_schema=SpecialistAgentProposal,
            messages=messages_for(
                prompt,
                output_schema_version=self.output_schema_version,
                payload=payload,
            ),
            domain_validator=validate,
            canonical_factory=lambda values: SpecialistAgentProposal.create(
                **canonical_proposal_values(values)
            ),
            # estimated_duration_seconds is derived from the status and the
            # requested minutes, so it is withheld from the provider schema for
            # the same reason proposal_hash is: a model cannot choose it, and
            # asking it to compute one discards otherwise valid proposals.
            server_owned_fields=("estimated_duration_seconds", "proposal_hash"),
        )

    async def apropose(
        self,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> StructuredAgentResult[SpecialistAgentProposal]:
        prompt = ROLE_PROMPTS[self.role_code]
        try:
            agent_input = SpecialistAgentInput(
                agent_type_code=self.agent_type_code,
                constraint_envelope=constraint_envelope,
                envelope_hash=constraint_envelope.envelope_hash,
                exercise_pool=exercise_pool,
                pool_hash=exercise_pool.pool_hash,
                regeneration_context=regeneration_context,
            )
            feasibility_code = self._training_feasibility_code(
                constraint_envelope=constraint_envelope,
                exercise_pool=exercise_pool,
            )
            payload = specialist_payload(
                agent_input,
                training_plan_feasibility_code=feasibility_code,
            )
        except (ValidationError, ValueError):
            return self._invoker.failure(
                code=LlmAgentFailureCode.DOMAIN_INVALID,
                role_code=self.role_code,
                prompt_version=prompt.version,
                output_schema_version=self.output_schema_version,
                attempt_count=0,
            )

        def validate(output: SpecialistAgentProposal) -> SpecialistAgentProposal:
            agent_input.validate_proposal(output)
            self._validate_training_decline(output, feasibility_code)
            return output

        return await self._invoker.ainvoke(
            role_code=self.role_code,
            prompt_version=prompt.version,
            output_schema_version=self.output_schema_version,
            output_schema=SpecialistAgentProposal,
            messages=messages_for(
                prompt,
                output_schema_version=self.output_schema_version,
                payload=payload,
            ),
            domain_validator=validate,
            canonical_factory=lambda values: SpecialistAgentProposal.create(
                **canonical_proposal_values(values)
            ),
            # estimated_duration_seconds is derived from the status and the
            # requested minutes, so it is withheld from the provider schema for
            # the same reason proposal_hash is: a model cannot choose it, and
            # asking it to compute one discards otherwise valid proposals.
            server_owned_fields=("estimated_duration_seconds", "proposal_hash"),
        )


class TrainingAgentAdapter(LangChainSpecialistAdapter):
    def __init__(
        self,
        *,
        invoker: StructuredChatInvoker,
        feasibility_provider: DeterministicFallbackProvider | None = None,
        fallback_version: str | None = None,
    ) -> None:
        super().__init__(
            role_code=LlmAgentRoleCode.TRAINING,
            invoker=invoker,
            feasibility_provider=feasibility_provider,
            fallback_version=fallback_version,
        )


class RecoveryAgentAdapter(LangChainSpecialistAdapter):
    def __init__(self, *, invoker: StructuredChatInvoker) -> None:
        super().__init__(role_code=LlmAgentRoleCode.RECOVERY, invoker=invoker)


class FeasibilityAgentAdapter(LangChainSpecialistAdapter):
    def __init__(self, *, invoker: StructuredChatInvoker) -> None:
        super().__init__(role_code=LlmAgentRoleCode.FEASIBILITY, invoker=invoker)


__all__ = [
    "FeasibilityAgentAdapter",
    "LangChainSpecialistAdapter",
    "RecoveryAgentAdapter",
    "TrainingAgentAdapter",
]
