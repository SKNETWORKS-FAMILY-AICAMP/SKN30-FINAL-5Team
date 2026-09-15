"""Evaluation-only contracts for architecture E bounded draft review."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.domain.agents.v3_contracts import (
    CoordinatorInput,
    ExercisePrescription,
    PlanActionCode,
    PlanSpec,
    ProposalReference,
)
from backend.tests.evaluation.runners.single_agent import SingleAgentPlanDraft


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _hash(value: object) -> str:
    encoded = json.dumps(
        _jsonable(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _machine_code(value: str, *, label: str) -> str:
    if not value or value.upper() != value or not value.replace("_", "").isalnum():
        raise ValueError(f"{label} must be an uppercase machine code")
    return value


class DraftAdjustmentCode(StrEnum):
    REDUCE_SETS = "REDUCE_SETS"
    REDUCE_REPETITIONS = "REDUCE_REPETITIONS"
    INCREASE_REST = "INCREASE_REST"


class DraftAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    adjustment_id: str
    prescription_sequence: int = Field(gt=0)
    adjustment_code: DraftAdjustmentCode
    value: int = Field(gt=0)

    @field_validator("adjustment_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _machine_code(value, label="adjustment_id")


class DraftReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role_code: Literal["RECOVERY", "FEASIBILITY"]
    draft_hash: str
    adjustments: tuple[DraftAdjustment, ...]
    review_codes: tuple[str, ...] = Field(min_length=1)
    review_hash: str

    @field_validator("review_codes")
    @classmethod
    def validate_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("review codes must be unique and sorted")
        return tuple(_machine_code(value, label="review code") for value in values)

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        expected = _hash(self.model_dump(mode="json", exclude={"review_hash"}))
        if self.review_hash != expected:
            raise ValueError("review_hash does not match review")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = dict(values)
        payload["review_hash"] = _hash(payload)
        return cls.model_validate(payload)


class PatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    draft_hash: str
    accepted_adjustment_ids: tuple[str, ...]
    rejected_adjustment_ids: tuple[str, ...]
    decision_codes: tuple[str, ...] = Field(min_length=1)
    decision_hash: str

    @field_validator("accepted_adjustment_ids", "rejected_adjustment_ids", "decision_codes")
    @classmethod
    def validate_codes(cls, values: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError(f"{info.field_name} must be unique and sorted")
        return tuple(
            _machine_code(value, label=info.field_name or "decision code") for value in values
        )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if set(self.accepted_adjustment_ids) & set(self.rejected_adjustment_ids):
            raise ValueError("accepted and rejected adjustments must be disjoint")
        expected = _hash(self.model_dump(mode="json", exclude={"decision_hash"}))
        if self.decision_hash != expected:
            raise ValueError("decision_hash does not match decision")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = dict(values)
        payload["decision_hash"] = _hash(payload)
        return cls.model_validate(payload)


class DraftReviewOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    plan_spec: PlanSpec
    original_draft_hash: str
    changed: bool
    specialist_disagreement: bool
    applied_adjustment_ids: tuple[str, ...]


def draft_hash(draft: SingleAgentPlanDraft) -> str:
    return _hash(draft.model_dump(mode="json"))


def _review_adjustments(
    draft: SingleAgentPlanDraft, reviews: tuple[DraftReview, DraftReview]
) -> dict[str, DraftAdjustment]:
    expected_hash = draft_hash(draft)
    if {review.role_code for review in reviews} != {"RECOVERY", "FEASIBILITY"}:
        raise ValueError("exactly one Recovery and one Feasibility review are required")
    adjustments: dict[str, DraftAdjustment] = {}
    for review in reviews:
        if review.draft_hash != expected_hash:
            raise ValueError("review references another draft")
        for adjustment in review.adjustments:
            if adjustment.adjustment_id in adjustments:
                raise ValueError("adjustment IDs must be globally unique")
            adjustments[adjustment.adjustment_id] = adjustment
    return adjustments


def _apply(
    prescriptions: tuple[ExercisePrescription, ...],
    adjustments: tuple[DraftAdjustment, ...],
) -> tuple[ExercisePrescription, ...]:
    by_sequence = {item.sequence: item for item in prescriptions}
    touched: set[tuple[int, DraftAdjustmentCode]] = set()
    for adjustment in adjustments:
        key = (adjustment.prescription_sequence, adjustment.adjustment_code)
        if key in touched:
            raise ValueError("multiple accepted adjustments target the same field")
        touched.add(key)
        current = by_sequence.get(adjustment.prescription_sequence)
        if current is None:
            raise ValueError("adjustment references an unknown prescription")
        if adjustment.adjustment_code is DraftAdjustmentCode.REDUCE_SETS:
            if adjustment.value >= current.sets:
                raise ValueError("REDUCE_SETS must strictly reduce the current value")
            update = {"sets": adjustment.value}
        elif adjustment.adjustment_code is DraftAdjustmentCode.REDUCE_REPETITIONS:
            if (
                current.repetitions_per_set is None
                or adjustment.value >= current.repetitions_per_set
            ):
                raise ValueError("REDUCE_REPETITIONS must strictly reduce the current value")
            update = {"repetitions_per_set": adjustment.value}
        else:
            if adjustment.value <= current.rest_seconds_between_sets:
                raise ValueError("INCREASE_REST must strictly increase the current value")
            update = {"rest_seconds_between_sets": adjustment.value}
        by_sequence[current.sequence] = current.model_copy(update=update)
    return tuple(by_sequence[index] for index in sorted(by_sequence))


def materialize_reviewed_draft(
    *,
    draft: SingleAgentPlanDraft,
    reviews: tuple[DraftReview, DraftReview],
    decision: PatchDecision,
    coordinator_input: CoordinatorInput,
) -> DraftReviewOutcome:
    """Apply only submitted monotone patches; never let the Coordinator rewrite."""

    expected_hash = draft_hash(draft)
    if decision.draft_hash != expected_hash:
        raise ValueError("decision references another draft")
    available = _review_adjustments(draft, reviews)
    submitted = set(available)
    decided = set(decision.accepted_adjustment_ids) | set(decision.rejected_adjustment_ids)
    if submitted != decided:
        raise ValueError("Coordinator must explicitly decide every submitted adjustment")
    accepted = tuple(available[item] for item in decision.accepted_adjustment_ids)
    prescriptions = _apply(draft.exercise_prescriptions, accepted)
    references = tuple(
        ProposalReference(
            agent_type_code=proposal.agent_type_code,
            proposal_hash=proposal.proposal_hash,
        )
        for proposal in coordinator_input.proposals
    )
    plan = PlanSpec.create(
        envelope_hash=draft.envelope_hash,
        pool_hash=draft.pool_hash,
        action_code=PlanActionCode.DOWNSHIFT if accepted else draft.action_code,
        requested_duration_minutes=draft.requested_duration_minutes,
        estimated_duration_seconds=draft.estimated_duration_seconds,
        exercise_prescriptions=prescriptions,
        proposal_references=references,
        repair_attempt=0,
        decision_codes=tuple(sorted({*draft.decision_codes, *decision.decision_codes})),
        public_summary_code=draft.public_summary_code,
    )
    plan.validate_against(coordinator_input)
    signatures = {
        tuple(
            (item.adjustment_code.value, item.prescription_sequence, item.value)
            for item in review.adjustments
        )
        for review in reviews
    }
    return DraftReviewOutcome(
        plan_spec=plan,
        original_draft_hash=expected_hash,
        changed=bool(accepted),
        specialist_disagreement=len(signatures) > 1,
        applied_adjustment_ids=decision.accepted_adjustment_ids,
    )


__all__ = [
    "DraftAdjustment",
    "DraftAdjustmentCode",
    "DraftReview",
    "DraftReviewOutcome",
    "PatchDecision",
    "draft_hash",
    "materialize_reviewed_draft",
]
