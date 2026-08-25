"""Deterministic V3 proposal conflict detection and bounded review validation."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    ConstraintEnvelope,
    SpecialistAgentInput,
    SpecialistAgentProposal,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
    _canonical_codes,
    _canonical_hash,
    _hash_value,
)

CONFLICT_DETECTION_SCHEMA_VERSION: Final[Literal["v3-conflict-detection-v1"]] = (
    "v3-conflict-detection-v1"
)
AGENT_REVIEW_SCHEMA_VERSION: Final[Literal["v3-agent-review-v1"]] = "v3-agent-review-v1"
REVIEW_VALIDATION_SCHEMA_VERSION: Final[Literal["v3-review-validation-v1"]] = (
    "v3-review-validation-v1"
)


class ConflictCode(StrEnum):
    PROPOSAL_MISSING = "PROPOSAL_MISSING"
    PROPOSAL_DUPLICATE = "PROPOSAL_DUPLICATE"
    PROPOSAL_FAILED = "PROPOSAL_FAILED"
    PROPOSAL_NEEDS_INPUT = "PROPOSAL_NEEDS_INPUT"
    ENVELOPE_HASH_MISMATCH = "ENVELOPE_HASH_MISMATCH"
    POOL_HASH_MISMATCH = "POOL_HASH_MISMATCH"
    REQUESTED_DURATION_MISMATCH = "REQUESTED_DURATION_MISMATCH"
    MANDATORY_EXERCISE_MISSING = "MANDATORY_EXERCISE_MISSING"
    SAFETY_EXCLUDED_EXERCISE_INCLUDED = "SAFETY_EXCLUDED_EXERCISE_INCLUDED"
    EXERCISE_OUTSIDE_POOL = "EXERCISE_OUTSIDE_POOL"
    RECOVERY_CEILING_EXCEEDED = "RECOVERY_CEILING_EXCEEDED"
    LOCATION_NOT_ALLOWED = "LOCATION_NOT_ALLOWED"
    EQUIPMENT_NOT_AVAILABLE = "EQUIPMENT_NOT_AVAILABLE"
    PRESCRIPTION_SCHEMA_INVALID = "PRESCRIPTION_SCHEMA_INVALID"
    STRUCTURED_PROPOSALS_INCOMPATIBLE = "STRUCTURED_PROPOSALS_INCOMPATIBLE"


_CONFLICT_ORDER = tuple(ConflictCode)
_ROLE_INDEX = {role: index for index, role in enumerate(SPECIALIST_AGENT_ORDER)}
_NON_REVIEWABLE_CODES = frozenset(
    {
        ConflictCode.PROPOSAL_MISSING,
        ConflictCode.PROPOSAL_DUPLICATE,
        ConflictCode.PROPOSAL_FAILED,
        ConflictCode.PROPOSAL_NEEDS_INPUT,
    }
)


def _canonical_roles(
    values: tuple[SpecialistAgentTypeCode, ...],
) -> tuple[SpecialistAgentTypeCode, ...]:
    if len(values) != len(set(values)):
        raise ValueError("affected_agent_types must not contain duplicates")
    if values != tuple(sorted(values, key=_ROLE_INDEX.__getitem__)):
        raise ValueError("affected_agent_types must use canonical role order")
    return values


class ConflictViolation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: ConflictCode
    affected_agent_types: tuple[SpecialistAgentTypeCode, ...] = Field(min_length=1)

    @field_validator("affected_agent_types")
    @classmethod
    def validate_roles(
        cls, values: tuple[SpecialistAgentTypeCode, ...]
    ) -> tuple[SpecialistAgentTypeCode, ...]:
        return _canonical_roles(values)


class ConflictDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-conflict-detection-v1"] = CONFLICT_DETECTION_SCHEMA_VERSION
    envelope_hash: str
    pool_hash: str
    violations: tuple[ConflictViolation, ...]
    review_target_agent_types: tuple[SpecialistAgentTypeCode, ...]
    result_hash: str

    @field_validator("envelope_hash", "pool_hash", "result_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="conflict hash")

    @field_validator("review_target_agent_types")
    @classmethod
    def validate_review_targets(
        cls, values: tuple[SpecialistAgentTypeCode, ...]
    ) -> tuple[SpecialistAgentTypeCode, ...]:
        return _canonical_roles(values)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        keys = tuple(
            (
                _CONFLICT_ORDER.index(item.code),
                tuple(_ROLE_INDEX[role] for role in item.affected_agent_types),
            )
            for item in self.violations
        )
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("violations must be unique and canonically ordered")
        expected_targets = _review_targets(self.violations)
        if self.review_target_agent_types != expected_targets:
            raise ValueError("review targets do not match reviewable conflicts")
        if self.result_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"result_hash"})
        ):
            raise ValueError("result_hash does not match conflict result")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": CONFLICT_DETECTION_SCHEMA_VERSION, **values}
        payload["result_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


def _review_targets(
    violations: tuple[ConflictViolation, ...],
) -> tuple[SpecialistAgentTypeCode, ...]:
    if any(item.code in _NON_REVIEWABLE_CODES for item in violations):
        return ()
    affected = {role for item in violations for role in item.affected_agent_types}
    return tuple(role for role in SPECIALIST_AGENT_ORDER if role in affected)


def _add(
    values: set[tuple[ConflictCode, tuple[SpecialistAgentTypeCode, ...]]],
    code: ConflictCode,
    *roles: SpecialistAgentTypeCode,
) -> None:
    canonical = tuple(role for role in SPECIALIST_AGENT_ORDER if role in set(roles))
    values.add((code, canonical))


def _proposal_constraint_conflicts(
    proposal: SpecialistAgentProposal,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    conflicts: set[tuple[ConflictCode, tuple[SpecialistAgentTypeCode, ...]]],
) -> None:
    role = proposal.agent_type_code
    if proposal.envelope_hash != envelope.envelope_hash:
        _add(conflicts, ConflictCode.ENVELOPE_HASH_MISMATCH, role)
    if proposal.pool_hash != pool.pool_hash:
        _add(conflicts, ConflictCode.POOL_HASH_MISMATCH, role)
    if proposal.requested_duration_minutes != envelope.requested_duration_minutes:
        _add(conflicts, ConflictCode.REQUESTED_DURATION_MISMATCH, role)

    prescriptions = proposal.exercise_prescriptions
    if not prescriptions:
        return
    ids = tuple(item.exercise_id for item in prescriptions)
    if len(ids) != len(set(ids)) or tuple(item.sequence for item in prescriptions) != tuple(
        range(1, len(prescriptions) + 1)
    ):
        _add(conflicts, ConflictCode.PRESCRIPTION_SCHEMA_INVALID, role)
    pool_records = {item.exercise_id: item for item in pool.exercises}
    if not set(ids).issubset(pool_records):
        _add(conflicts, ConflictCode.EXERCISE_OUTSIDE_POOL, role)
    if set(ids) & set(envelope.excluded_exercise_ids):
        _add(conflicts, ConflictCode.SAFETY_EXCLUDED_EXERCISE_INCLUDED, role)
    if not set(envelope.mandatory_exercise_ids).issubset(ids):
        _add(conflicts, ConflictCode.MANDATORY_EXERCISE_MISSING, role)

    ceiling = envelope.recovery_ceiling
    for item in prescriptions:
        record = pool_records.get(item.exercise_id)
        if item.location_code not in envelope.allowed_location_codes or (
            record is not None and item.location_code not in record.location_codes
        ):
            _add(conflicts, ConflictCode.LOCATION_NOT_ALLOWED, role)
        if not set(item.equipment_codes).issubset(envelope.allowed_equipment_codes) or (
            record is not None and not set(item.equipment_codes).issubset(record.equipment_codes)
        ):
            _add(conflicts, ConflictCode.EQUIPMENT_NOT_AVAILABLE, role)
        ceiling_exceeded = (
            bool(ceiling.allowed_intensity_codes)
            and item.intensity_code not in ceiling.allowed_intensity_codes
        ) or (bool(ceiling.allowed_load_codes) and item.load_code not in ceiling.allowed_load_codes)
        ceiling_exceeded = ceiling_exceeded or any(
            actual is not None and maximum is not None and actual > maximum
            for actual, maximum in (
                (item.sets, ceiling.maximum_sets_per_exercise),
                (item.repetitions_per_set, ceiling.maximum_repetitions_per_set),
                (item.work_seconds_per_set, ceiling.maximum_work_seconds_per_set),
            )
        )
        if (
            ceiling.minimum_rest_seconds_between_sets is not None
            and item.rest_seconds_between_sets < ceiling.minimum_rest_seconds_between_sets
        ):
            ceiling_exceeded = True
        if ceiling_exceeded:
            _add(conflicts, ConflictCode.RECOVERY_CEILING_EXCEEDED, role)


def detect_proposal_conflicts(
    proposals: tuple[SpecialistAgentProposal, ...],
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
) -> ConflictDetectionResult:
    """Return canonical conflict codes without raising on incomplete Agent fan-in."""

    conflicts: set[tuple[ConflictCode, tuple[SpecialistAgentTypeCode, ...]]] = set()
    by_role: dict[SpecialistAgentTypeCode, list[SpecialistAgentProposal]] = {
        role: [] for role in SPECIALIST_AGENT_ORDER
    }
    for proposal in proposals:
        by_role[proposal.agent_type_code].append(proposal)

    for role in SPECIALIST_AGENT_ORDER:
        role_proposals = by_role[role]
        if not role_proposals:
            _add(conflicts, ConflictCode.PROPOSAL_MISSING, role)
            continue
        if len(role_proposals) > 1:
            _add(conflicts, ConflictCode.PROPOSAL_DUPLICATE, role)
        for proposal in role_proposals:
            if proposal.proposal_status_code is V3ProposalStatusCode.FAILED:
                _add(conflicts, ConflictCode.PROPOSAL_FAILED, role)
            elif proposal.proposal_status_code is V3ProposalStatusCode.NEEDS_INPUT:
                _add(conflicts, ConflictCode.PROPOSAL_NEEDS_INPUT, role)
            _proposal_constraint_conflicts(proposal, envelope, pool, conflicts)

    plan_proposals = tuple(
        proposal
        for proposal in proposals
        if proposal.proposal_status_code is V3ProposalStatusCode.READY
        and proposal.exercise_prescriptions
    )
    if len(plan_proposals) > 1:
        first_plan = plan_proposals[0].exercise_prescriptions
        disagreeing = tuple(
            proposal.agent_type_code
            for proposal in plan_proposals
            if proposal.exercise_prescriptions != first_plan
        )
        if disagreeing:
            _add(
                conflicts,
                ConflictCode.STRUCTURED_PROPOSALS_INCOMPATIBLE,
                plan_proposals[0].agent_type_code,
                *disagreeing,
            )

    violations = tuple(
        ConflictViolation(code=code, affected_agent_types=roles)
        for code, roles in sorted(
            conflicts,
            key=lambda item: (
                _CONFLICT_ORDER.index(item[0]),
                tuple(_ROLE_INDEX[role] for role in item[1]),
            ),
        )
    )
    return ConflictDetectionResult.create(
        envelope_hash=envelope.envelope_hash,
        pool_hash=pool.pool_hash,
        violations=violations,
        review_target_agent_types=_review_targets(violations),
    )


class ReviewStatusCode(StrEnum):
    READY = "READY"
    NOT_REQUIRED = "NOT_REQUIRED"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


class AgentReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-agent-review-v1"] = AGENT_REVIEW_SCHEMA_VERSION
    agent_type_code: SpecialistAgentTypeCode
    status_code: ReviewStatusCode
    baseline_proposal_hash: str
    reviewed_conflict_codes: tuple[str, ...]
    revised_proposal: SpecialistAgentProposal | None = None
    review_hash: str

    @field_validator("baseline_proposal_hash", "review_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _hash_value(value, field_name="review hash")

    @field_validator("reviewed_conflict_codes")
    @classmethod
    def validate_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="reviewed_conflict_codes")

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if (self.status_code is ReviewStatusCode.READY) != (self.revised_proposal is not None):
            raise ValueError("READY review requires exactly one revised proposal")
        if self.revised_proposal is not None and (
            self.revised_proposal.agent_type_code is not self.agent_type_code
        ):
            raise ValueError("review role does not match revised proposal")
        if self.review_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"review_hash"})
        ):
            raise ValueError("review_hash does not match review result")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": AGENT_REVIEW_SCHEMA_VERSION,
            "revised_proposal": None,
            **values,
        }
        payload["review_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class ReviewValidationStatusCode(StrEnum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


class ReviewValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-review-validation-v1"] = REVIEW_VALIDATION_SCHEMA_VERSION
    status_code: ReviewValidationStatusCode
    effective_proposals: tuple[SpecialistAgentProposal, ...]
    failure_codes: tuple[str, ...]
    result_hash: str

    @field_validator("failure_codes")
    @classmethod
    def validate_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="review failure codes")

    @field_validator("result_hash")
    @classmethod
    def validate_result_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="review validation hash")

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status_code is ReviewValidationStatusCode.READY:
            if (
                tuple(item.agent_type_code for item in self.effective_proposals)
                != SPECIALIST_AGENT_ORDER
            ):
                raise ValueError("effective proposals must use canonical role order")
            if self.failure_codes:
                raise ValueError("READY review validation cannot contain failures")
        elif self.effective_proposals:
            raise ValueError("failed review validation cannot expose partial proposals")
        if self.result_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"result_hash"})
        ):
            raise ValueError("result_hash does not match review validation")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": REVIEW_VALIDATION_SCHEMA_VERSION, **values}
        payload["result_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


def validate_agent_reviews(
    round_one_proposals: tuple[SpecialistAgentProposal, ...],
    conflicts: ConflictDetectionResult,
    reviews: tuple[AgentReviewResult, ...],
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
) -> ReviewValidationResult:
    """Validate exactly one review per target and return canonical effective proposals."""

    targets = conflicts.review_target_agent_types
    target_order = tuple(review.agent_type_code for review in reviews)
    if target_order != targets:
        return ReviewValidationResult.create(
            status_code=ReviewValidationStatusCode.FAILED,
            effective_proposals=(),
            failure_codes=("REVIEW_TARGET_SET_INVALID",),
        )
    round_one = {item.agent_type_code: item for item in round_one_proposals}
    if (
        tuple(role for role in SPECIALIST_AGENT_ORDER if role in round_one)
        != SPECIALIST_AGENT_ORDER
    ):
        return ReviewValidationResult.create(
            status_code=ReviewValidationStatusCode.FAILED,
            effective_proposals=(),
            failure_codes=("ROUND_ONE_PROPOSAL_SET_INVALID",),
        )

    effective = dict(round_one)
    for review in reviews:
        baseline = round_one[review.agent_type_code]
        expected_conflict_codes = tuple(
            sorted(
                {
                    item.code.value
                    for item in conflicts.violations
                    if review.agent_type_code in item.affected_agent_types
                }
            )
        )
        if review.reviewed_conflict_codes != expected_conflict_codes:
            return ReviewValidationResult.create(
                status_code=ReviewValidationStatusCode.FAILED,
                effective_proposals=(),
                failure_codes=("REVIEW_CONFLICT_SET_INVALID",),
            )
        if review.baseline_proposal_hash != baseline.proposal_hash:
            return ReviewValidationResult.create(
                status_code=ReviewValidationStatusCode.FAILED,
                effective_proposals=(),
                failure_codes=("REVIEW_BASELINE_HASH_MISMATCH",),
            )
        if review.status_code is ReviewStatusCode.NEEDS_INPUT:
            return ReviewValidationResult.create(
                status_code=ReviewValidationStatusCode.NEEDS_INPUT,
                effective_proposals=(),
                failure_codes=("REVIEW_NEEDS_INPUT",),
            )
        if review.status_code is not ReviewStatusCode.READY or review.revised_proposal is None:
            return ReviewValidationResult.create(
                status_code=ReviewValidationStatusCode.FAILED,
                effective_proposals=(),
                failure_codes=("REVIEW_FAILED",),
            )
        revised = review.revised_proposal
        if not set(baseline.hard_constraint_codes).issubset(revised.hard_constraint_codes):
            return ReviewValidationResult.create(
                status_code=ReviewValidationStatusCode.FAILED,
                effective_proposals=(),
                failure_codes=("REVIEW_HARD_CONSTRAINT_RELAXED",),
            )
        try:
            SpecialistAgentInput(
                agent_type_code=review.agent_type_code,
                constraint_envelope=envelope,
                envelope_hash=envelope.envelope_hash,
                exercise_pool=pool,
                pool_hash=pool.pool_hash,
            ).validate_proposal(revised)
        except ValueError:
            return ReviewValidationResult.create(
                status_code=ReviewValidationStatusCode.FAILED,
                effective_proposals=(),
                failure_codes=("REVIEW_PROPOSAL_INVALID",),
            )
        effective[review.agent_type_code] = revised

    canonical = tuple(effective[role] for role in SPECIALIST_AGENT_ORDER)
    remaining = detect_proposal_conflicts(canonical, envelope, pool)
    if remaining.violations:
        return ReviewValidationResult.create(
            status_code=ReviewValidationStatusCode.FAILED,
            effective_proposals=(),
            failure_codes=("REVIEW_CONFLICT_UNRESOLVED",),
        )
    return ReviewValidationResult.create(
        status_code=ReviewValidationStatusCode.READY,
        effective_proposals=canonical,
        failure_codes=(),
    )


__all__ = [
    "AGENT_REVIEW_SCHEMA_VERSION",
    "CONFLICT_DETECTION_SCHEMA_VERSION",
    "REVIEW_VALIDATION_SCHEMA_VERSION",
    "AgentReviewResult",
    "ConflictCode",
    "ConflictDetectionResult",
    "ConflictViolation",
    "ReviewStatusCode",
    "ReviewValidationResult",
    "ReviewValidationStatusCode",
    "detect_proposal_conflicts",
    "validate_agent_reviews",
]
