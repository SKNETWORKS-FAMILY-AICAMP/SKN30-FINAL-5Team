"""Single-call Coordinator adapter bound to V3 CoordinatorInput and PlanSpec."""

from __future__ import annotations

from pydantic import ValidationError

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    PLAN_SPEC_SCHEMA_VERSION,
    ConstraintEnvelope,
    CoordinatorInput,
    PlanSpec,
    SpecialistAgentProposal,
)
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.payload import coordinator_payload
from backend.app.integrations.llm_agents.prompts import ROLE_PROMPTS, messages_for
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker


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
        )


__all__ = ["LangChainCoordinatorAdapter"]
