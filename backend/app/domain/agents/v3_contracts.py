"""Framework-independent structured contracts for Safety-first V3 LLM agents."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import ClassVar, Final, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import to_jsonable_python

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord, ExercisePoolSnapshot
from backend.app.domain.rules.safety import SafetyRequiredActionCode

CONSTRAINT_ENVELOPE_SCHEMA_VERSION: Final[Literal["constraint-envelope-v4"]] = (
    "constraint-envelope-v4"
)
RECOVERY_CEILING_SCHEMA_VERSION: Final[Literal["recovery-ceiling-v1"]] = "recovery-ceiling-v1"
REGENERATION_CONTEXT_SCHEMA_VERSION: Final[Literal["regeneration-context-v1"]] = (
    "regeneration-context-v1"
)
SPECIALIST_AGENT_INPUT_SCHEMA_VERSION: Final[Literal["specialist-agent-input-v1"]] = (
    "specialist-agent-input-v1"
)
SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION: Final[Literal["specialist-agent-proposal-v1"]] = (
    "specialist-agent-proposal-v1"
)
LLM_INVOCATION_METADATA_SCHEMA_VERSION: Final[Literal["llm-invocation-metadata-v1"]] = (
    "llm-invocation-metadata-v1"
)
V3_COORDINATOR_INPUT_SCHEMA_VERSION: Final[Literal["v3-coordinator-input-v1"]] = (
    "v3-coordinator-input-v1"
)
PLAN_SPEC_SCHEMA_VERSION: Final[Literal["plan-spec-v1"]] = "plan-spec-v1"

_MACHINE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SpecialistAgentTypeCode(StrEnum):
    TRAINING = "TRAINING"
    RECOVERY = "RECOVERY"
    FEASIBILITY = "FEASIBILITY"


SPECIALIST_AGENT_ORDER: Final[tuple[SpecialistAgentTypeCode, ...]] = (
    SpecialistAgentTypeCode.TRAINING,
    SpecialistAgentTypeCode.RECOVERY,
    SpecialistAgentTypeCode.FEASIBILITY,
)


class V3ProposalStatusCode(StrEnum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


class PlanPhaseCode(StrEnum):
    """Session phases a plan item may belong to.

    Declared in the order a session runs them; ``_PHASE_ORDER`` below relies on
    that order, so do not reorder these members.
    """

    WARMUP = "WARMUP"
    MAIN = "MAIN"
    COOLDOWN = "COOLDOWN"


_PHASE_ORDER: Final[dict[PlanPhaseCode, int]] = {
    code: index for index, code in enumerate(PlanPhaseCode)
}


class PlanActionCode(StrEnum):
    KEEP = "KEEP"
    DOWNSHIFT = "DOWNSHIFT"
    CHANGE = "CHANGE"
    RECOVERY = "RECOVERY"


class LLMInvocationStatusCode(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"


def _machine_code(value: str, *, field_name: str) -> str:
    if not _MACHINE_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must contain only a structured machine code")
    return value


def _hash_value(value: str, *, field_name: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _canonical_codes(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    for value in values:
        _machine_code(value, field_name=field_name)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    if values != tuple(sorted(values)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return values


def _canonical_ids(values: tuple[UUID, ...], *, field_name: str) -> tuple[UUID, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    if values != tuple(sorted(values, key=str)):
        raise ValueError(f"{field_name} must use canonical UUID order")
    return values


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        to_jsonable_python(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RecoveryCeiling(BaseModel):
    """Approved upstream recovery limits without embedding default thresholds."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["recovery-ceiling-v1"] = RECOVERY_CEILING_SCHEMA_VERSION
    policy_version: str
    allowed_intensity_codes: tuple[str, ...] = ()
    allowed_load_codes: tuple[str, ...] = ()
    maximum_sets_per_exercise: int | None = Field(default=None, gt=0)
    maximum_repetitions_per_set: int | None = Field(default=None, gt=0)
    maximum_work_seconds_per_set: int | None = Field(default=None, gt=0)
    minimum_rest_seconds_between_sets: int | None = Field(default=None, ge=0)

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        return _machine_code(value, field_name="policy_version")

    @field_validator("allowed_intensity_codes", "allowed_load_codes")
    @classmethod
    def validate_code_sets(cls, values: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        return _canonical_codes(values, field_name=info.field_name or "recovery codes")


class ConstraintEnvelope(BaseModel):
    """Immutable projection of deterministic Safety, duration, and feasibility constraints."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["constraint-envelope-v4"] = CONSTRAINT_ENVELOPE_SCHEMA_VERSION
    requested_duration_minutes: int = Field(gt=0)
    primary_goal_code: str
    allowed_location_codes: tuple[str, ...] = Field(min_length=1)
    allowed_equipment_codes: tuple[str, ...] = ()
    excluded_exercise_ids: tuple[UUID, ...] = ()
    # Reviewed CAUTION verdicts. Unlike an exclusion these stay selectable: the
    # approved rules answer CAUTION, not EXCLUDE, so removing them would change
    # safety policy. They are carried so the decision record and the user-facing
    # response can show which exercises the rules flagged.
    caution_exercise_ids: tuple[UUID, ...] = ()
    mandatory_exercise_ids: tuple[UUID, ...] = ()
    recovery_ceiling: RecoveryCeiling
    plan_generation_allowed: bool
    safety_required_action_code: SafetyRequiredActionCode | None = None
    policy_version: str
    catalog_version: str
    safety_rule_version: str
    envelope_hash: str

    _machine_fields: ClassVar[tuple[str, ...]] = (
        "primary_goal_code",
        "policy_version",
        "catalog_version",
        "safety_rule_version",
    )

    @field_validator(*_machine_fields)
    @classmethod
    def validate_machine_fields(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "envelope field")

    @field_validator("allowed_location_codes", "allowed_equipment_codes")
    @classmethod
    def validate_allowed_codes(
        cls, values: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_codes(values, field_name=info.field_name or "allowed codes")

    @field_validator(
        "excluded_exercise_ids",
        "caution_exercise_ids",
        "mandatory_exercise_ids",
    )
    @classmethod
    def validate_exercise_ids(
        cls, values: tuple[UUID, ...], info: ValidationInfo
    ) -> tuple[UUID, ...]:
        return _canonical_ids(values, field_name=info.field_name or "exercise IDs")

    @field_validator("envelope_hash")
    @classmethod
    def validate_envelope_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="envelope_hash")

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        if set(self.excluded_exercise_ids) & set(self.mandatory_exercise_ids):
            raise ValueError("an exercise cannot be both excluded and mandatory")
        if set(self.excluded_exercise_ids) & set(self.caution_exercise_ids):
            raise ValueError("an exercise cannot be both excluded and cautioned")
        if self.plan_generation_allowed and self.safety_required_action_code is not None:
            raise ValueError("plan generation cannot override REST or STOP_AND_SEEK_HELP")
        if self.envelope_hash != _canonical_hash(self._hash_payload()):
            raise ValueError("envelope_hash does not match the canonical envelope")
        return self

    def _hash_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"envelope_hash"})

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": CONSTRAINT_ENVELOPE_SCHEMA_VERSION,
            "safety_required_action_code": None,
            # Seeded so the hashed payload matches the validated model even when
            # the caller omits it; the model default alone would not be hashed.
            "caution_exercise_ids": (),
            **values,
        }
        payload["envelope_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class RegenerationContext(BaseModel):
    """Optional, identifier-free projection for manual V3 regeneration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["regeneration-context-v1"] = REGENERATION_CONTEXT_SCHEMA_VERSION
    generation_sequence: int = Field(ge=1, le=2)
    previous_plan_hash: str
    previous_exercise_ids: tuple[UUID, ...]
    variation_codes: tuple[str, ...] = Field(min_length=1)
    exact_duplicate_forbidden: Literal[True] = True

    @field_validator("previous_plan_hash")
    @classmethod
    def validate_previous_plan_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="previous_plan_hash")

    @field_validator("previous_exercise_ids")
    @classmethod
    def validate_previous_exercise_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(values) != len(set(values)):
            raise ValueError("previous_exercise_ids must not contain duplicates")
        return values

    @field_validator("variation_codes")
    @classmethod
    def validate_variation_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="variation_codes")


class ExercisePrescription(BaseModel):
    """Integer-only exercise prescription referenced by proposals and PlanSpec."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    exercise_id: UUID
    sequence: int = Field(gt=0)
    # The session phase this item belongs to. Required rather than defaulted:
    # a default would silently reproduce the all-MAIN plans this field exists
    # to replace.
    phase_code: PlanPhaseCode
    sets: int = Field(gt=0)
    repetitions_per_set: int | None = Field(default=None, gt=0)
    work_seconds_per_set: int | None = Field(default=None, gt=0)
    rest_seconds_between_sets: int = Field(ge=0)
    transition_seconds: int = Field(ge=0)
    intensity_code: str
    load_code: str | None = None
    location_code: str
    equipment_codes: tuple[str, ...] = ()

    @field_validator("intensity_code", "location_code")
    @classmethod
    def validate_required_codes(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "prescription code")

    @field_validator("load_code")
    @classmethod
    def validate_load_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _machine_code(value, field_name="load_code")

    @field_validator("equipment_codes")
    @classmethod
    def validate_equipment_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="equipment_codes")

    @model_validator(mode="after")
    def validate_timing_mode(self) -> Self:
        if self.repetitions_per_set is None and self.work_seconds_per_set is None:
            raise ValueError("prescription requires repetitions or work seconds")
        return self


def _validate_prescription_order(values: tuple[ExercisePrescription, ...]) -> None:
    ids = tuple(value.exercise_id for value in values)
    if len(ids) != len(set(ids)):
        raise ValueError("exercise prescriptions must not contain duplicate exercise IDs")
    if tuple(value.sequence for value in values) != tuple(range(1, len(values) + 1)):
        raise ValueError("exercise prescriptions must use contiguous canonical sequence")
    ranks = tuple(_PHASE_ORDER[value.phase_code] for value in values)
    if ranks != tuple(sorted(ranks)):
        raise ValueError("exercise prescriptions must run WARMUP, then MAIN, then COOLDOWN")


def _pool_records(pool: ExercisePoolSnapshot) -> dict[UUID, ExercisePoolExerciseRecord]:
    return {exercise.exercise_id: exercise for exercise in pool.exercises}


def _validate_prescription_constraints(
    prescriptions: tuple[ExercisePrescription, ...],
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
) -> None:
    records = _pool_records(pool)
    prescribed_ids = {item.exercise_id for item in prescriptions}
    if not prescribed_ids.issubset(records):
        raise ValueError("exercise prescription references an ID outside ExercisePoolSnapshot")
    if prescribed_ids & set(envelope.excluded_exercise_ids):
        raise ValueError("exercise prescription cannot relax Safety exclusions")
    ceiling = envelope.recovery_ceiling
    for item in prescriptions:
        record = records[item.exercise_id]
        if item.location_code not in envelope.allowed_location_codes:
            raise ValueError("exercise prescription uses a disallowed location")
        if item.location_code not in record.location_codes:
            raise ValueError("exercise prescription location is not supported by the catalog")
        if item.phase_code.value not in record.phase_codes:
            raise ValueError("exercise prescription phase is not approved for this exercise")
        if not set(item.equipment_codes).issubset(envelope.allowed_equipment_codes):
            raise ValueError("exercise prescription uses disallowed equipment")
        if not set(item.equipment_codes).issubset(record.equipment_codes):
            raise ValueError("exercise prescription equipment is not supported by the catalog")
        if ceiling.allowed_intensity_codes and (
            item.intensity_code not in ceiling.allowed_intensity_codes
        ):
            raise ValueError("exercise prescription relaxes the Recovery intensity ceiling")
        if ceiling.allowed_load_codes and item.load_code not in ceiling.allowed_load_codes:
            raise ValueError("exercise prescription relaxes the Recovery load ceiling")
        numeric_ceilings = (
            (item.sets, ceiling.maximum_sets_per_exercise, "sets"),
            (
                item.repetitions_per_set,
                ceiling.maximum_repetitions_per_set,
                "repetitions",
            ),
            (item.work_seconds_per_set, ceiling.maximum_work_seconds_per_set, "work seconds"),
        )
        for actual, maximum, label in numeric_ceilings:
            if actual is not None and maximum is not None and actual > maximum:
                raise ValueError(f"exercise prescription exceeds the Recovery {label} ceiling")
        minimum_rest = ceiling.minimum_rest_seconds_between_sets
        if minimum_rest is not None and item.rest_seconds_between_sets < minimum_rest:
            raise ValueError("exercise prescription relaxes the Recovery rest ceiling")


class SpecialistAgentInput(BaseModel):
    """One role-bound view of the shared immutable envelope and pool."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["specialist-agent-input-v1"] = SPECIALIST_AGENT_INPUT_SCHEMA_VERSION
    agent_type_code: SpecialistAgentTypeCode
    constraint_envelope: ConstraintEnvelope
    envelope_hash: str
    exercise_pool: ExercisePoolSnapshot
    pool_hash: str
    regeneration_context: RegenerationContext | None = None

    @field_validator("envelope_hash", "pool_hash")
    @classmethod
    def validate_hashes(cls, value: str, info: ValidationInfo) -> str:
        return _hash_value(value, field_name=info.field_name or "input hash")

    @model_validator(mode="after")
    def validate_shared_contracts(self) -> Self:
        if self.envelope_hash != self.constraint_envelope.envelope_hash:
            raise ValueError("envelope_hash does not match ConstraintEnvelope")
        if self.pool_hash != self.exercise_pool.pool_hash:
            raise ValueError("pool_hash does not match ExercisePoolSnapshot")
        if self.exercise_pool.constraint_envelope_hash != self.envelope_hash:
            raise ValueError("ExercisePoolSnapshot belongs to another ConstraintEnvelope")
        if self.exercise_pool.catalog_version != self.constraint_envelope.catalog_version:
            raise ValueError("ConstraintEnvelope and ExercisePoolSnapshot catalog versions differ")
        if not self.constraint_envelope.plan_generation_allowed:
            raise ValueError("Specialist Agent cannot run when plan generation is forbidden")
        if not set(self.constraint_envelope.mandatory_exercise_ids).issubset(
            set(self.exercise_pool.mandatory_exercise_ids)
        ):
            raise ValueError("ExercisePoolSnapshot does not preserve envelope mandatory exercises")
        return self

    def validate_proposal(self, proposal: SpecialistAgentProposal) -> None:
        if proposal.agent_type_code is not self.agent_type_code:
            raise ValueError("proposal role does not match SpecialistAgentInput")
        if proposal.envelope_hash != self.envelope_hash or proposal.pool_hash != self.pool_hash:
            raise ValueError("proposal references another envelope or pool")
        if (
            proposal.requested_duration_minutes
            != self.constraint_envelope.requested_duration_minutes
        ):
            raise ValueError("proposal cannot change requested duration")
        _validate_prescription_constraints(
            proposal.exercise_prescriptions,
            envelope=self.constraint_envelope,
            pool=self.exercise_pool,
        )


class SpecialistAgentProposal(BaseModel):
    """Structured proposal without hidden reasoning or provider metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["specialist-agent-proposal-v1"] = (
        SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION
    )
    agent_type_code: SpecialistAgentTypeCode
    proposal_status_code: V3ProposalStatusCode
    envelope_hash: str
    pool_hash: str
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int | None = Field(default=None, gt=0)
    exercise_prescriptions: tuple[ExercisePrescription, ...] = ()
    adjustment_codes: tuple[str, ...] = ()
    hard_constraint_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_reference_codes: tuple[str, ...] = ()
    public_summary_code: str | None = None
    proposal_hash: str

    _canonical_code_fields: ClassVar[tuple[str, ...]] = (
        "adjustment_codes",
        "hard_constraint_codes",
        "reason_codes",
        "evidence_reference_codes",
    )

    @field_validator("envelope_hash", "pool_hash", "proposal_hash")
    @classmethod
    def validate_hash_fields(cls, value: str, info: ValidationInfo) -> str:
        return _hash_value(value, field_name=info.field_name or "proposal hash")

    @field_validator(*_canonical_code_fields)
    @classmethod
    def validate_code_fields(cls, values: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        return _canonical_codes(values, field_name=info.field_name or "proposal codes")

    @field_validator("public_summary_code")
    @classmethod
    def validate_summary_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _machine_code(value, field_name="public_summary_code")

    @field_validator("exercise_prescriptions")
    @classmethod
    def validate_prescriptions(
        cls, values: tuple[ExercisePrescription, ...]
    ) -> tuple[ExercisePrescription, ...]:
        _validate_prescription_order(values)
        return values

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        if (
            self.agent_type_code
            in {
                SpecialistAgentTypeCode.RECOVERY,
                SpecialistAgentTypeCode.FEASIBILITY,
            }
            and self.exercise_prescriptions
        ):
            raise ValueError("only TRAINING proposals may include exercise_prescriptions")
        if self.proposal_status_code is V3ProposalStatusCode.READY:
            expected_seconds = self.requested_duration_minutes * 60
            if self.estimated_duration_seconds != expected_seconds:
                raise ValueError("READY proposal must preserve requested duration")
            if self.agent_type_code is SpecialistAgentTypeCode.TRAINING:
                if not self.exercise_prescriptions:
                    raise ValueError("TRAINING proposal requires an ordered exercise plan")
            elif not self.exercise_prescriptions and not self.adjustment_codes:
                raise ValueError("READY specialist proposal requires a plan or adjustment codes")
        elif self.estimated_duration_seconds is not None or self.exercise_prescriptions:
            raise ValueError("non-READY proposal cannot claim an exercise plan or duration")
        if self.proposal_hash != _canonical_hash(self._hash_payload()):
            raise ValueError("proposal_hash does not match the canonical proposal")
        return self

    def _hash_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"proposal_hash"})

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION,
            "exercise_prescriptions": (),
            "adjustment_codes": (),
            "hard_constraint_codes": (),
            "reason_codes": (),
            "evidence_reference_codes": (),
            "public_summary_code": None,
            **values,
        }
        # A READY proposal must preserve the requested duration exactly, and a
        # non-READY one must claim no duration at all. Both are fully determined
        # by the status and the requested minutes, so the server derives them
        # rather than asking a model to compute a value it cannot choose.
        payload["estimated_duration_seconds"] = cls.derive_estimated_duration_seconds(
            proposal_status_code=payload.get("proposal_status_code"),
            requested_duration_minutes=payload.get("requested_duration_minutes"),
        )
        payload["proposal_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)

    @staticmethod
    def derive_estimated_duration_seconds(
        *, proposal_status_code: object, requested_duration_minutes: object
    ) -> int | None:
        """Compute the duration a proposal is allowed to claim for its status."""

        is_ready = proposal_status_code in {
            V3ProposalStatusCode.READY,
            V3ProposalStatusCode.READY.value,
        }
        if not is_ready or not isinstance(requested_duration_minutes, int):
            return None
        return requested_duration_minutes * 60


class LLMInvocationMetadata(BaseModel):
    """Non-sensitive invocation lineage stored separately from structured output."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["llm-invocation-metadata-v1"] = LLM_INVOCATION_METADATA_SCHEMA_VERSION
    provider_code: str
    model_version: str
    prompt_version: str
    output_schema_version: str
    attempt: int = Field(ge=0, le=1)
    status_code: LLMInvocationStatusCode
    latency_ms: int = Field(ge=0)

    @field_validator("provider_code", "model_version", "prompt_version", "output_schema_version")
    @classmethod
    def validate_metadata_codes(cls, value: str, info: ValidationInfo) -> str:
        return _machine_code(value, field_name=info.field_name or "invocation metadata")


class CoordinatorInput(BaseModel):
    """Canonical three-proposal input accepted by the future LLM Coordinator adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["v3-coordinator-input-v1"] = V3_COORDINATOR_INPUT_SCHEMA_VERSION
    constraint_envelope: ConstraintEnvelope
    exercise_pool: ExercisePoolSnapshot
    proposals: tuple[SpecialistAgentProposal, ...]
    repair_attempt: int = Field(ge=0, le=1)
    repair_violation_codes: tuple[str, ...] = ()

    @field_validator("repair_violation_codes")
    @classmethod
    def validate_repair_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="repair_violation_codes")

    @model_validator(mode="after")
    def validate_coordinator_input(self) -> Self:
        if not self.constraint_envelope.plan_generation_allowed:
            raise ValueError("Coordinator cannot run when plan generation is forbidden")
        if self.constraint_envelope.safety_required_action_code is not None:
            raise ValueError("Coordinator cannot override REST or STOP_AND_SEEK_HELP")
        if self.exercise_pool.constraint_envelope_hash != self.constraint_envelope.envelope_hash:
            raise ValueError("Coordinator envelope and pool hashes do not match")
        agent_order = tuple(proposal.agent_type_code for proposal in self.proposals)
        if agent_order != SPECIALIST_AGENT_ORDER:
            raise ValueError("Coordinator requires three proposals in canonical role order")
        if any(
            proposal.proposal_status_code is not V3ProposalStatusCode.READY
            for proposal in self.proposals
        ):
            raise ValueError("Coordinator cannot run with missing, failed, or non-ready proposals")
        if self.repair_attempt == 0 and self.repair_violation_codes:
            raise ValueError("initial Coordinator input cannot carry repair violations")
        if self.repair_attempt == 1 and not self.repair_violation_codes:
            raise ValueError("repair Coordinator input requires violation codes")
        for agent_type, proposal in zip(SPECIALIST_AGENT_ORDER, self.proposals, strict=True):
            SpecialistAgentInput(
                agent_type_code=agent_type,
                constraint_envelope=self.constraint_envelope,
                envelope_hash=self.constraint_envelope.envelope_hash,
                exercise_pool=self.exercise_pool,
                pool_hash=self.exercise_pool.pool_hash,
            ).validate_proposal(proposal)
        return self


class ProposalReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    agent_type_code: SpecialistAgentTypeCode
    proposal_hash: str

    @field_validator("proposal_hash")
    @classmethod
    def validate_proposal_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="proposal_hash")


class PlanSpec(BaseModel):
    """Single structured plan returned by the future LLM Coordinator adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["plan-spec-v1"] = PLAN_SPEC_SCHEMA_VERSION
    envelope_hash: str
    pool_hash: str
    action_code: PlanActionCode
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int = Field(gt=0)
    exercise_prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)
    proposal_references: tuple[ProposalReference, ...]
    repair_attempt: int = Field(ge=0, le=1)
    decision_codes: tuple[str, ...] = Field(min_length=1)
    public_summary_code: str | None = None
    plan_hash: str

    @field_validator("envelope_hash", "pool_hash", "plan_hash")
    @classmethod
    def validate_hash_fields(cls, value: str, info: ValidationInfo) -> str:
        return _hash_value(value, field_name=info.field_name or "plan hash")

    @field_validator("decision_codes")
    @classmethod
    def validate_decision_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="decision_codes")

    @field_validator("public_summary_code")
    @classmethod
    def validate_public_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _machine_code(value, field_name="public_summary_code")

    @field_validator("exercise_prescriptions")
    @classmethod
    def validate_prescriptions(
        cls, values: tuple[ExercisePrescription, ...]
    ) -> tuple[ExercisePrescription, ...]:
        _validate_prescription_order(values)
        return values

    @model_validator(mode="after")
    def validate_plan_spec(self) -> Self:
        if tuple(ref.agent_type_code for ref in self.proposal_references) != (
            SPECIALIST_AGENT_ORDER
        ):
            raise ValueError("PlanSpec proposal references must use canonical role order")
        if self.estimated_duration_seconds != self.requested_duration_minutes * 60:
            raise ValueError("PlanSpec must preserve requested duration")
        if self.plan_hash != _canonical_hash(self._hash_payload()):
            raise ValueError("plan_hash does not match the canonical PlanSpec")
        return self

    def _hash_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"plan_hash"})

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": PLAN_SPEC_SCHEMA_VERSION,
            "public_summary_code": None,
            **values,
        }
        payload["plan_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)

    def validate_against(self, coordinator_input: CoordinatorInput) -> None:
        envelope = coordinator_input.constraint_envelope
        if self.envelope_hash != envelope.envelope_hash:
            raise ValueError("PlanSpec references another ConstraintEnvelope")
        if self.pool_hash != coordinator_input.exercise_pool.pool_hash:
            raise ValueError("PlanSpec references another ExercisePoolSnapshot")
        if self.requested_duration_minutes != envelope.requested_duration_minutes:
            raise ValueError("PlanSpec cannot change requested duration")
        if self.repair_attempt != coordinator_input.repair_attempt:
            raise ValueError("PlanSpec repair attempt does not match CoordinatorInput")
        expected_references = tuple(
            ProposalReference(
                agent_type_code=proposal.agent_type_code,
                proposal_hash=proposal.proposal_hash,
            )
            for proposal in coordinator_input.proposals
        )
        if self.proposal_references != expected_references:
            raise ValueError("PlanSpec does not reference the canonical proposal set")
        _validate_prescription_constraints(
            self.exercise_prescriptions,
            envelope=envelope,
            pool=coordinator_input.exercise_pool,
        )
        prescribed_ids = {item.exercise_id for item in self.exercise_prescriptions}
        if not set(envelope.mandatory_exercise_ids).issubset(prescribed_ids):
            raise ValueError("PlanSpec cannot remove mandatory exercises")


__all__ = [
    "CONSTRAINT_ENVELOPE_SCHEMA_VERSION",
    "LLM_INVOCATION_METADATA_SCHEMA_VERSION",
    "PLAN_SPEC_SCHEMA_VERSION",
    "RECOVERY_CEILING_SCHEMA_VERSION",
    "REGENERATION_CONTEXT_SCHEMA_VERSION",
    "SPECIALIST_AGENT_INPUT_SCHEMA_VERSION",
    "SPECIALIST_AGENT_ORDER",
    "SPECIALIST_AGENT_PROPOSAL_SCHEMA_VERSION",
    "V3_COORDINATOR_INPUT_SCHEMA_VERSION",
    "ConstraintEnvelope",
    "CoordinatorInput",
    "ExercisePrescription",
    "LLMInvocationMetadata",
    "LLMInvocationStatusCode",
    "PlanActionCode",
    "PlanPhaseCode",
    "PlanSpec",
    "ProposalReference",
    "RecoveryCeiling",
    "RegenerationContext",
    "SpecialistAgentInput",
    "SpecialistAgentProposal",
    "SpecialistAgentTypeCode",
    "V3ProposalStatusCode",
]
