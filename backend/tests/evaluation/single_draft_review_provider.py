"""Provider adapters for architecture E parallel critics and bounded selection."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope
from backend.app.integrations.llm_agents.models import LlmAgentRoleCode, StructuredAgentResult
from backend.app.integrations.llm_agents.payload import (
    _CONSTRAINT_ENVELOPE_FIELDS,
    assert_private_machine_payload,
    project_contract,
    project_exercise_pool,
)
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.tests.evaluation.runners.single_agent import SingleAgentPlanDraft
from backend.tests.evaluation.single_draft_review import (
    DraftAdjustment,
    DraftAdjustmentCode,
    DraftReview,
    PatchDecision,
    draft_hash,
)

REVIEW_SCHEMA_VERSION = "single-draft-review-v1"
PATCH_DECISION_SCHEMA_VERSION = "single-draft-patch-decision-v1"
RECOVERY_PROMPT_VERSION = "eval-single-draft-recovery-v1"
FEASIBILITY_PROMPT_VERSION = "eval-single-draft-feasibility-v1"
COORDINATOR_PROMPT_VERSION = "eval-single-draft-patch-selector-v1"


class DraftReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    adjustments: list[DraftAdjustment]
    review_codes: list[str] = Field(min_length=1)


class PatchDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    accepted_adjustment_ids: list[str]
    rejected_adjustment_ids: list[str]
    decision_codes: list[str] = Field(min_length=1)


def _messages(
    *, prompt_version: str, schema_version: str, instruction: str, payload: dict[str, object]
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


_RECOVERY_INSTRUCTION = (
    "Review the already valid exercise draft only for recovery burden. Return zero or more "
    "bounded changes using REDUCE_SETS, REDUCE_REPETITIONS, or INCREASE_REST. Do not add, "
    "remove, replace, or reorder exercises. Equipment ownership is not a review condition. "
    "If no material improvement is needed, return an empty adjustments list and a NO_CHANGE "
    "review code. Return only the requested schema."
)

_FEASIBILITY_INSTRUCTION = (
    "Review the already valid exercise draft only for execution feasibility, requested "
    "duration, phase flow, and transition burden. Return zero or more bounded changes using "
    "REDUCE_SETS, REDUCE_REPETITIONS, or INCREASE_REST. Do not add, remove, replace, or "
    "reorder exercises. Equipment ownership is not a review condition. If no material "
    "improvement is needed, return an empty adjustments list and a NO_CHANGE review code. "
    "Return only the requested schema."
)

_COORDINATOR_INSTRUCTION = (
    "Decide every submitted adjustment ID by placing it in exactly one of accepted or "
    "rejected IDs. Do not output or rewrite prescriptions. Prefer NO_CHANGE unless a submitted "
    "patch materially improves the draft without risking safety, requested duration, goal, "
    "location, or recovery constraints. Return only the requested schema."
)


def _selected_pool_payload(
    draft: SingleAgentPlanDraft, pool: ExercisePoolSnapshot
) -> dict[str, object]:
    projected = project_exercise_pool(pool)
    selected = {str(item.exercise_id) for item in draft.exercise_prescriptions}
    exercises = projected.get("exercises")
    if isinstance(exercises, list):
        projected["exercises"] = [
            item
            for item in exercises
            if isinstance(item, dict) and item.get("exercise_id") in selected
        ]
    projected["exercise_id_allowlist"] = sorted(selected)
    return projected


def _validate_adjustments(
    output: DraftReviewOutput, *, draft: SingleAgentPlanDraft
) -> DraftReviewOutput:
    by_sequence = {item.sequence: item for item in draft.exercise_prescriptions}
    seen: set[str] = set()
    for adjustment in output.adjustments:
        if adjustment.adjustment_id in seen:
            raise ValueError("review adjustment IDs must be unique")
        seen.add(adjustment.adjustment_id)
        current = by_sequence.get(adjustment.prescription_sequence)
        if current is None:
            raise ValueError("review adjustment references an unknown prescription")
        if (
            adjustment.adjustment_code is DraftAdjustmentCode.REDUCE_SETS
            and adjustment.value >= current.sets
        ):
            raise ValueError("REDUCE_SETS must strictly reduce the current value")
        if adjustment.adjustment_code is DraftAdjustmentCode.REDUCE_REPETITIONS and (
            current.repetitions_per_set is None or adjustment.value >= current.repetitions_per_set
        ):
            raise ValueError("REDUCE_REPETITIONS must strictly reduce the current value")
        if (
            adjustment.adjustment_code is DraftAdjustmentCode.INCREASE_REST
            and adjustment.value <= current.rest_seconds_between_sets
        ):
            raise ValueError("INCREASE_REST must strictly increase the current value")
    return output


class SingleDraftReviewProviderAdapter:
    def __init__(self, *, invoker: StructuredChatInvoker) -> None:
        self._invoker = invoker

    async def review(
        self,
        *,
        role_code: Literal["RECOVERY", "FEASIBILITY"],
        draft: SingleAgentPlanDraft,
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
    ) -> StructuredAgentResult[DraftReview]:
        prompt_version = (
            RECOVERY_PROMPT_VERSION if role_code == "RECOVERY" else FEASIBILITY_PROMPT_VERSION
        )
        instruction = _RECOVERY_INSTRUCTION if role_code == "RECOVERY" else _FEASIBILITY_INSTRUCTION
        payload: dict[str, object] = {
            "draft": draft.model_dump(mode="json"),
            "constraint_envelope": project_contract(
                envelope, field_allowlist=_CONSTRAINT_ENVELOPE_FIELDS
            ),
            # Keep the established key path so the privacy guard can distinguish
            # catalog body_focus_code from user-reported health body-area data.
            "exercise_pool": _selected_pool_payload(draft, pool),
        }

        def canonical(values: dict[str, object]) -> DraftReview:
            parsed = DraftReviewOutput.model_validate(values)
            return DraftReview.create(
                role_code=role_code,
                draft_hash=draft_hash(draft),
                adjustments=tuple(parsed.adjustments),
                review_codes=tuple(sorted(set(parsed.review_codes))),
            )

        result = await self._invoker.ainvoke(
            role_code=LlmAgentRoleCode(role_code),
            prompt_version=prompt_version,
            output_schema_version=REVIEW_SCHEMA_VERSION,
            output_schema=DraftReviewOutput,
            messages=_messages(
                prompt_version=prompt_version,
                schema_version=REVIEW_SCHEMA_VERSION,
                instruction=instruction,
                payload=payload,
            ),
            domain_validator=lambda output: _validate_adjustments(output, draft=draft),
        )
        if result.output is not None:
            return StructuredAgentResult.success(
                canonical(result.output.model_dump()), telemetry=result.telemetry
            )
        assert result.failure is not None
        return StructuredAgentResult(
            failure=result.failure,
            telemetry=result.telemetry,
        )

    async def review_both(
        self,
        *,
        draft: SingleAgentPlanDraft,
        envelope: ConstraintEnvelope,
        pool: ExercisePoolSnapshot,
    ) -> tuple[StructuredAgentResult[DraftReview], StructuredAgentResult[DraftReview]]:
        return await asyncio.gather(
            self.review(role_code="RECOVERY", draft=draft, envelope=envelope, pool=pool),
            self.review(role_code="FEASIBILITY", draft=draft, envelope=envelope, pool=pool),
        )

    async def select(
        self, *, draft: SingleAgentPlanDraft, reviews: tuple[DraftReview, DraftReview]
    ) -> StructuredAgentResult[PatchDecision]:
        submitted = sorted(
            adjustment.adjustment_id for review in reviews for adjustment in review.adjustments
        )
        payload: dict[str, object] = {
            "draft_hash": draft_hash(draft),
            "submitted_adjustment_ids": submitted,
            "reviews": [review.model_dump(mode="json") for review in reviews],
        }

        def canonical(values: dict[str, object]) -> PatchDecision:
            parsed = PatchDecisionOutput.model_validate(values)
            return PatchDecision.create(
                draft_hash=draft_hash(draft),
                accepted_adjustment_ids=tuple(sorted(set(parsed.accepted_adjustment_ids))),
                rejected_adjustment_ids=tuple(sorted(set(parsed.rejected_adjustment_ids))),
                decision_codes=tuple(sorted(set(parsed.decision_codes))),
            )

        def validate(output: PatchDecisionOutput) -> PatchDecisionOutput:
            decision = canonical(output.model_dump())
            decided = set(decision.accepted_adjustment_ids) | set(decision.rejected_adjustment_ids)
            if decided != set(submitted):
                raise ValueError("Coordinator must decide every submitted adjustment")
            return output

        result = await self._invoker.ainvoke(
            role_code=LlmAgentRoleCode.COORDINATOR,
            prompt_version=COORDINATOR_PROMPT_VERSION,
            output_schema_version=PATCH_DECISION_SCHEMA_VERSION,
            output_schema=PatchDecisionOutput,
            messages=_messages(
                prompt_version=COORDINATOR_PROMPT_VERSION,
                schema_version=PATCH_DECISION_SCHEMA_VERSION,
                instruction=_COORDINATOR_INSTRUCTION,
                payload=payload,
            ),
            domain_validator=validate,
        )
        if result.output is not None:
            return StructuredAgentResult.success(
                canonical(result.output.model_dump()), telemetry=result.telemetry
            )
        assert result.failure is not None
        return StructuredAgentResult(failure=result.failure, telemetry=result.telemetry)


__all__ = [
    "COORDINATOR_PROMPT_VERSION",
    "FEASIBILITY_PROMPT_VERSION",
    "PATCH_DECISION_SCHEMA_VERSION",
    "RECOVERY_PROMPT_VERSION",
    "REVIEW_SCHEMA_VERSION",
    "DraftReviewOutput",
    "PatchDecisionOutput",
    "SingleDraftReviewProviderAdapter",
]
