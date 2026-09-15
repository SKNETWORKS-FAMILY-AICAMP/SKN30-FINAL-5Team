"""Provider adapters for the ADR-0025 candidate-review experiment."""

from __future__ import annotations

import asyncio
import json
from typing import Literal, Self

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, ExercisePrescription
from backend.app.integrations.llm_agents.models import (
    LlmAgentFailureCode,
    LlmAgentRoleCode,
    StructuredAgentResult,
)
from backend.app.integrations.llm_agents.payload import (
    _CONSTRAINT_ENVELOPE_FIELDS,
    assert_private_machine_payload,
    project_contract,
    project_exercise_pool,
)
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.candidate_review import (
    CandidateDraft,
    CandidateReview,
    CandidateSelection,
    CandidateSet,
)

CANDIDATE_GENERATION_SCHEMA_VERSION = "candidate-generation-v1"
CANDIDATE_REVIEW_SCHEMA_VERSION = "candidate-review-v1"
CANDIDATE_SELECTION_SCHEMA_VERSION = "candidate-selection-v1"

TRAINING_CANDIDATE_PROMPT_VERSION = "eval-training-candidates-v1"
RECOVERY_REVIEW_PROMPT_VERSION = "eval-recovery-candidate-review-v1"
FEASIBILITY_REVIEW_PROMPT_VERSION = "eval-feasibility-candidate-review-v1"
CANDIDATE_SELECTION_PROMPT_VERSION = "eval-candidate-selection-v1"


class CandidateOptionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate_code: Literal["GOAL_FOCUSED", "RECOVERY_FOCUSED"]
    objective_code: Literal["GOAL_PRESERVATION", "RECOVERY_LOAD"]
    exercise_prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)


class TrainingCandidatesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidates: tuple[CandidateOptionOutput, CandidateOptionOutput]

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        expected = {
            ("GOAL_FOCUSED", "GOAL_PRESERVATION"),
            ("RECOVERY_FOCUSED", "RECOVERY_LOAD"),
        }
        actual = {(item.candidate_code, item.objective_code) for item in self.candidates}
        if actual != expected:
            raise ValueError("Training must return the two fixed candidate objectives")
        return self


def _messages(
    *, prompt_version: str, instruction: str, schema_version: str, payload: dict[str, object]
) -> tuple[SystemMessage, HumanMessage]:
    assert_private_machine_payload(payload)
    body = json.dumps(
        {
            "prompt_version": prompt_version,
            "output_schema_version": schema_version,
            "input": payload,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return SystemMessage(content=instruction), HumanMessage(content=body)


_TRAINING_INSTRUCTION = (
    "Create exactly two independently useful exercise-plan candidates from the supplied approved "
    "pool and immutable constraint envelope. GOAL_FOCUSED/GOAL_PRESERVATION should prioritize "
    "the requested training goal. RECOVERY_FOCUSED/RECOVERY_LOAD should reduce recovery burden "
    "while preserving requested duration. Both candidates must independently satisfy every "
    "constraint, cover WARMUP, MAIN and COOLDOWN, and differ in their prescriptions. Equipment "
    "ownership is not a selection condition. Return only the requested schema and no reasoning."
)

_REVIEW_INSTRUCTION = (
    "Rank both supplied candidates from the Recovery perspective. You may propose only bounded "
    "REDUCE_SETS, REDUCE_REPETITIONS, or INCREASE_REST adjustments against an existing candidate "
    "and prescription sequence. Every adjustment_id must be an uppercase machine code. Do not "
    "add, remove, replace, or reorder exercises. Return only the requested schema."
)

_FEASIBILITY_INSTRUCTION = (
    "Rank both supplied candidates from execution-feasibility perspective, considering requested "
    "duration, location, phase flow and transition burden. Equipment ownership is not a selection "
    "condition. You may propose only bounded REDUCE_SETS, REDUCE_REPETITIONS, or INCREASE_REST "
    "adjustments. Do not add, remove, replace, or reorder exercises. Return only the requested "
    "schema."
)

_SELECTION_INSTRUCTION = (
    "Select exactly one supplied candidate after considering both reviews. Accept only adjustment "
    "IDs that a review actually submitted for the selected candidate. Do not output or rewrite any "
    "exercise prescription. Use stable uppercase decision codes and return only the requested "
    "schema."
)


def _shared_payload(envelope: ConstraintEnvelope, pool: ExercisePoolSnapshot) -> dict[str, object]:
    payload: dict[str, object] = {
        "constraint_envelope": project_contract(
            envelope, field_allowlist=_CONSTRAINT_ENVELOPE_FIELDS
        ),
        "exercise_pool": project_exercise_pool(pool),
    }
    assert_private_machine_payload(payload)
    return payload


class CandidateReviewProviderAdapter:
    def __init__(self, *, invoker: StructuredChatInvoker) -> None:
        self._invoker = invoker

    async def generate_candidates(
        self, *, envelope: ConstraintEnvelope, pool: ExercisePoolSnapshot
    ) -> StructuredAgentResult[CandidateSet]:
        payload = _shared_payload(envelope, pool)

        def canonical(values: dict[str, object]) -> CandidateSet:
            parsed = TrainingCandidatesOutput.model_validate(values)
            candidates = tuple(
                CandidateDraft.create(
                    candidate_code=item.candidate_code,
                    objective_code=item.objective_code,
                    exercise_prescriptions=item.exercise_prescriptions,
                )
                for item in parsed.candidates
            )
            return CandidateSet.create(
                envelope_hash=envelope.envelope_hash,
                pool_hash=pool.pool_hash,
                requested_duration_minutes=envelope.requested_duration_minutes,
                baseline_candidate_code="GOAL_FOCUSED",
                candidates=candidates,
            )

        def validate(output: TrainingCandidatesOutput) -> TrainingCandidatesOutput:
            canonical(output.model_dump())
            return output

        result = await self._invoker.ainvoke(
            role_code=LlmAgentRoleCode.TRAINING,
            prompt_version=TRAINING_CANDIDATE_PROMPT_VERSION,
            output_schema_version=CANDIDATE_GENERATION_SCHEMA_VERSION,
            output_schema=TrainingCandidatesOutput,
            messages=_messages(
                prompt_version=TRAINING_CANDIDATE_PROMPT_VERSION,
                instruction=_TRAINING_INSTRUCTION,
                schema_version=CANDIDATE_GENERATION_SCHEMA_VERSION,
                payload=payload,
            ),
            domain_validator=validate,
        )
        if result.output is not None:
            return StructuredAgentResult.success(
                canonical(result.output.model_dump()), telemetry=result.telemetry
            )
        assert result.failure is not None
        return StructuredAgentResult.failed(
            code=LlmAgentFailureCode(result.failure.code),
            role_code=result.failure.role_code,
            prompt_version=result.failure.prompt_version,
            output_schema_version=result.failure.output_schema_version,
            model_code=result.failure.model_code,
            attempt_count=result.failure.attempt_count,
            telemetry=result.telemetry,
        )

    async def review_candidates(
        self,
        *,
        role_code: Literal["RECOVERY", "FEASIBILITY"],
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
        candidate_set: CandidateSet,
    ) -> StructuredAgentResult[CandidateReview]:
        prompt_version = (
            RECOVERY_REVIEW_PROMPT_VERSION
            if role_code == "RECOVERY"
            else FEASIBILITY_REVIEW_PROMPT_VERSION
        )
        instruction = _REVIEW_INSTRUCTION if role_code == "RECOVERY" else _FEASIBILITY_INSTRUCTION
        payload: dict[str, object] = {
            **_shared_payload(envelope, pool),
            "candidate_set": candidate_set.model_dump(mode="json"),
        }

        def canonical(values: dict[str, object]) -> CandidateReview:
            return CandidateReview.create(
                role_code=role_code,
                candidate_set_hash=candidate_set.candidate_set_hash,
                **values,
            )

        return await self._invoker.ainvoke(
            role_code=LlmAgentRoleCode(role_code),
            prompt_version=prompt_version,
            output_schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
            output_schema=CandidateReview,
            messages=_messages(
                prompt_version=prompt_version,
                instruction=instruction,
                schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
                payload=payload,
            ),
            domain_validator=lambda output: output,
            canonical_factory=canonical,
            server_owned_fields=("role_code", "candidate_set_hash", "review_hash"),
        )

    async def review_both(
        self,
        *,
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
        candidate_set: CandidateSet,
    ) -> tuple[StructuredAgentResult[CandidateReview], StructuredAgentResult[CandidateReview]]:
        return await asyncio.gather(
            self.review_candidates(
                role_code="RECOVERY", envelope=envelope, pool=pool, candidate_set=candidate_set
            ),
            self.review_candidates(
                role_code="FEASIBILITY",
                envelope=envelope,
                pool=pool,
                candidate_set=candidate_set,
            ),
        )

    async def select_candidate(
        self,
        *,
        candidate_set: CandidateSet,
        reviews: tuple[CandidateReview, CandidateReview],
    ) -> StructuredAgentResult[CandidateSelection]:
        payload: dict[str, object] = {
            "candidate_codes": [item.candidate_code for item in candidate_set.candidates],
            "candidate_set_hash": candidate_set.candidate_set_hash,
            "reviews": [item.model_dump(mode="json") for item in reviews],
        }

        def canonical(values: dict[str, object]) -> CandidateSelection:
            return CandidateSelection.create(
                candidate_set_hash=candidate_set.candidate_set_hash, **values
            )

        return await self._invoker.ainvoke(
            role_code=LlmAgentRoleCode.COORDINATOR,
            prompt_version=CANDIDATE_SELECTION_PROMPT_VERSION,
            output_schema_version=CANDIDATE_SELECTION_SCHEMA_VERSION,
            output_schema=CandidateSelection,
            messages=_messages(
                prompt_version=CANDIDATE_SELECTION_PROMPT_VERSION,
                instruction=_SELECTION_INSTRUCTION,
                schema_version=CANDIDATE_SELECTION_SCHEMA_VERSION,
                payload=payload,
            ),
            domain_validator=lambda output: output,
            canonical_factory=canonical,
            server_owned_fields=("candidate_set_hash", "selection_hash"),
        )


__all__ = [
    "CANDIDATE_GENERATION_SCHEMA_VERSION",
    "CANDIDATE_REVIEW_SCHEMA_VERSION",
    "CANDIDATE_SELECTION_SCHEMA_VERSION",
    "CANDIDATE_SELECTION_PROMPT_VERSION",
    "FEASIBILITY_REVIEW_PROMPT_VERSION",
    "RECOVERY_REVIEW_PROMPT_VERSION",
    "TRAINING_CANDIDATE_PROMPT_VERSION",
    "CandidateOptionOutput",
    "CandidateReviewProviderAdapter",
    "TrainingCandidatesOutput",
]
