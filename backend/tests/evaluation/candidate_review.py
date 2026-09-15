"""Evaluation-only contracts for candidate review and bounded adjustment.

The coordinator selects; it never rewrites a prescription.  The selected draft
is materialized server-side as the existing PlanSpec, so the production
compiler and integrity validator remain the final enforcement points.
"""

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


def _hash(payload: object) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _code(value: str, *, label: str) -> str:
    if not value or not value.replace("_", "").isalnum() or value.upper() != value:
        raise ValueError(f"{label} must be a non-empty uppercase machine code")
    return value


class AdjustmentCode(StrEnum):
    REDUCE_SETS = "REDUCE_SETS"
    REDUCE_REPETITIONS = "REDUCE_REPETITIONS"
    INCREASE_REST = "INCREASE_REST"


class CandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate_code: str
    objective_code: str
    exercise_prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)
    draft_hash: str

    @field_validator("candidate_code", "objective_code")
    @classmethod
    def validate_codes(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "candidate code"
        return _code(value, label=field_name)

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if self.draft_hash != _hash(self.model_dump(mode="json", exclude={"draft_hash"})):
            raise ValueError("draft_hash does not match candidate")
        return self

    @property
    def prescription_fingerprint(self) -> str:
        return _hash([item.model_dump(mode="json") for item in self.exercise_prescriptions])

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = dict(values)
        payload["draft_hash"] = _hash(payload)
        return cls.model_validate(payload)


class CandidateSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    envelope_hash: str
    pool_hash: str
    requested_duration_minutes: int = Field(gt=0)
    baseline_candidate_code: str
    candidates: tuple[CandidateDraft, CandidateDraft]
    candidate_set_hash: str

    @model_validator(mode="after")
    def validate_set(self) -> Self:
        codes = tuple(item.candidate_code for item in self.candidates)
        if len(set(codes)) != 2:
            raise ValueError("candidate codes must be unique")
        if self.baseline_candidate_code not in codes:
            raise ValueError("baseline candidate must exist")
        if len({item.prescription_fingerprint for item in self.candidates}) != 2:
            raise ValueError("candidate prescriptions must be materially different")
        expected = _hash(self.model_dump(mode="json", exclude={"candidate_set_hash"}))
        if self.candidate_set_hash != expected:
            raise ValueError("candidate_set_hash does not match candidate set")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = dict(values)
        payload["candidate_set_hash"] = _hash(payload)
        return cls.model_validate(payload)


class BoundedAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    adjustment_id: str
    candidate_code: str
    prescription_sequence: int = Field(gt=0)
    adjustment_code: AdjustmentCode
    value: int = Field(gt=0)

    @field_validator("adjustment_id", "candidate_code")
    @classmethod
    def validate_codes(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "adjustment code"
        return _code(value, label=field_name)


class CandidateReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role_code: Literal["RECOVERY", "FEASIBILITY"]
    candidate_set_hash: str
    ranked_candidate_codes: tuple[str, str]
    adjustments: tuple[BoundedAdjustment, ...] = ()
    review_codes: tuple[str, ...] = Field(min_length=1)
    review_hash: str

    @field_validator("review_codes")
    @classmethod
    def validate_review_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("review codes must be unique and sorted")
        return tuple(_code(value, label="review code") for value in values)

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        expected = _hash(self.model_dump(mode="json", exclude={"review_hash"}))
        if self.review_hash != expected:
            raise ValueError("review_hash does not match review")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"adjustments": (), **values}
        payload["review_hash"] = _hash(payload)
        return cls.model_validate(payload)


class CandidateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate_set_hash: str
    selected_candidate_code: str
    accepted_adjustment_ids: tuple[str, ...] = ()
    decision_codes: tuple[str, ...] = Field(min_length=1)
    selection_hash: str

    @field_validator("accepted_adjustment_ids", "decision_codes")
    @classmethod
    def validate_canonical_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("selection codes must be unique and sorted")
        return tuple(_code(value, label="selection code") for value in values)

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        expected = _hash(self.model_dump(mode="json", exclude={"selection_hash"}))
        if self.selection_hash != expected:
            raise ValueError("selection_hash does not match selection")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"accepted_adjustment_ids": (), **values}
        payload["selection_hash"] = _hash(payload)
        return cls.model_validate(payload)


class DeliberationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    plan_spec: PlanSpec
    selected_candidate_code: str
    selection_changed: bool
    specialist_disagreement: bool
    applied_adjustment_ids: tuple[str, ...]


def _validate_reviews(
    candidate_set: CandidateSet, reviews: tuple[CandidateReview, CandidateReview]
) -> dict[str, BoundedAdjustment]:
    if {review.role_code for review in reviews} != {"RECOVERY", "FEASIBILITY"}:
        raise ValueError("exactly one Recovery and one Feasibility review are required")
    candidate_codes = {item.candidate_code for item in candidate_set.candidates}
    adjustments: dict[str, BoundedAdjustment] = {}
    for review in reviews:
        if review.candidate_set_hash != candidate_set.candidate_set_hash:
            raise ValueError("review references another candidate set")
        if set(review.ranked_candidate_codes) != candidate_codes:
            raise ValueError("review must rank every candidate exactly once")
        for adjustment in review.adjustments:
            if adjustment.candidate_code not in candidate_codes:
                raise ValueError("review adjustment references an unknown candidate")
            if adjustment.adjustment_id in adjustments:
                raise ValueError("adjustment IDs must be globally unique")
            adjustments[adjustment.adjustment_id] = adjustment
    return adjustments


def _apply_adjustments(
    prescriptions: tuple[ExercisePrescription, ...],
    adjustments: tuple[BoundedAdjustment, ...],
) -> tuple[ExercisePrescription, ...]:
    by_sequence = {item.sequence: item for item in prescriptions}
    touched: set[tuple[int, AdjustmentCode]] = set()
    for adjustment in adjustments:
        key = (adjustment.prescription_sequence, adjustment.adjustment_code)
        if key in touched:
            raise ValueError("multiple accepted adjustments target the same field")
        touched.add(key)
        current = by_sequence.get(adjustment.prescription_sequence)
        if current is None:
            raise ValueError("adjustment references an unknown prescription")
        if adjustment.adjustment_code is AdjustmentCode.REDUCE_SETS:
            if adjustment.value >= current.sets:
                raise ValueError("REDUCE_SETS must strictly reduce the current value")
            update = {"sets": adjustment.value}
        elif adjustment.adjustment_code is AdjustmentCode.REDUCE_REPETITIONS:
            if (
                current.repetitions_per_set is None
                or adjustment.value >= current.repetitions_per_set
            ):
                raise ValueError("REDUCE_REPETITIONS must strictly reduce a repetitions value")
            update = {"repetitions_per_set": adjustment.value}
        else:
            if adjustment.value <= current.rest_seconds_between_sets:
                raise ValueError("INCREASE_REST must strictly increase the current value")
            update = {"rest_seconds_between_sets": adjustment.value}
        by_sequence[current.sequence] = current.model_copy(update=update)
    return tuple(by_sequence[index] for index in sorted(by_sequence))


def materialize_selection(
    *,
    candidate_set: CandidateSet,
    reviews: tuple[CandidateReview, CandidateReview],
    selection: CandidateSelection,
    coordinator_input: CoordinatorInput,
) -> DeliberationOutcome:
    """Apply only review-originated monotone changes and build the existing PlanSpec."""

    envelope = coordinator_input.constraint_envelope
    pool = coordinator_input.exercise_pool
    if (
        candidate_set.envelope_hash != envelope.envelope_hash
        or candidate_set.pool_hash != pool.pool_hash
        or candidate_set.requested_duration_minutes != envelope.requested_duration_minutes
    ):
        raise ValueError("candidate set references another envelope or pool")
    if selection.candidate_set_hash != candidate_set.candidate_set_hash:
        raise ValueError("selection references another candidate set")
    by_code = {item.candidate_code: item for item in candidate_set.candidates}
    selected = by_code.get(selection.selected_candidate_code)
    if selected is None:
        raise ValueError("selection references an unknown candidate")
    available = _validate_reviews(candidate_set, reviews)
    accepted: list[BoundedAdjustment] = []
    for adjustment_id in selection.accepted_adjustment_ids:
        adjustment = available.get(adjustment_id)
        if adjustment is None:
            raise ValueError("Coordinator accepted an adjustment no specialist submitted")
        if adjustment.candidate_code != selected.candidate_code:
            raise ValueError("accepted adjustment targets an unselected candidate")
        accepted.append(adjustment)
    prescriptions = _apply_adjustments(selected.exercise_prescriptions, tuple(accepted))
    references = tuple(
        ProposalReference(
            agent_type_code=proposal.agent_type_code,
            proposal_hash=proposal.proposal_hash,
        )
        for proposal in coordinator_input.proposals
    )
    decision_codes = tuple(
        sorted(
            {
                *selection.decision_codes,
                f"SELECTED_{selected.candidate_code}",
                *(f"APPLIED_{item.adjustment_code.value}" for item in accepted),
            }
        )
    )
    plan = PlanSpec.create(
        envelope_hash=envelope.envelope_hash,
        pool_hash=pool.pool_hash,
        action_code=PlanActionCode.DOWNSHIFT if accepted else PlanActionCode.KEEP,
        requested_duration_minutes=envelope.requested_duration_minutes,
        estimated_duration_seconds=envelope.requested_duration_minutes * 60,
        exercise_prescriptions=prescriptions,
        proposal_references=references,
        repair_attempt=coordinator_input.repair_attempt,
        decision_codes=decision_codes,
    )
    plan.validate_against(coordinator_input)
    return DeliberationOutcome(
        plan_spec=plan,
        selected_candidate_code=selected.candidate_code,
        selection_changed=selected.candidate_code != candidate_set.baseline_candidate_code,
        specialist_disagreement=(
            reviews[0].ranked_candidate_codes[0] != reviews[1].ranked_candidate_codes[0]
        ),
        applied_adjustment_ids=selection.accepted_adjustment_ids,
    )


__all__ = [
    "AdjustmentCode",
    "BoundedAdjustment",
    "CandidateDraft",
    "CandidateReview",
    "CandidateSelection",
    "CandidateSet",
    "DeliberationOutcome",
    "materialize_selection",
]
