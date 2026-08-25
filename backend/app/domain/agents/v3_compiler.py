"""Pure deterministic compilation of approved V3 plan specifications."""

from __future__ import annotations

from typing import Final, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord, ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    CoordinatorInput,
    ExercisePrescription,
    PlanActionCode,
    PlanSpec,
    _canonical_codes,
    _canonical_hash,
    _hash_value,
    _validate_prescription_constraints,
    _validate_prescription_order,
)

COMPILED_PLAN_SCHEMA_VERSION: Final[Literal["compiled-plan-v1"]] = "compiled-plan-v1"
DETERMINISTIC_FALLBACK_PLAN_SCHEMA_VERSION: Final[Literal["deterministic-fallback-plan-v1"]] = (
    "deterministic-fallback-plan-v1"
)
DURATION_VERIFICATION_CODE: Final[Literal["PLAN_SPEC_EXACT_DURATION_ASSERTED"]] = (
    "PLAN_SPEC_EXACT_DURATION_ASSERTED"
)


class CompilablePlan(Protocol):
    envelope_hash: str
    pool_hash: str
    action_code: PlanActionCode
    requested_duration_minutes: int
    estimated_duration_seconds: int
    exercise_prescriptions: tuple[ExercisePrescription, ...]

    @property
    def source_hash(self) -> str: ...


class DeterministicFallbackPlanSpec(BaseModel):
    """Fallback-owned plan input with no fabricated LLM proposal references."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["deterministic-fallback-plan-v1"] = (
        DETERMINISTIC_FALLBACK_PLAN_SCHEMA_VERSION
    )
    envelope_hash: str
    pool_hash: str
    action_code: PlanActionCode
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int = Field(gt=0)
    exercise_prescriptions: tuple[ExercisePrescription, ...] = Field(min_length=1)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    fallback_version: str
    fallback_plan_hash: str

    @field_validator("envelope_hash", "pool_hash", "fallback_plan_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="fallback plan hash")

    @field_validator("reason_codes")
    @classmethod
    def validate_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, field_name="fallback reason codes")

    @field_validator("exercise_prescriptions")
    @classmethod
    def validate_prescriptions(
        cls, values: tuple[ExercisePrescription, ...]
    ) -> tuple[ExercisePrescription, ...]:
        _validate_prescription_order(values)
        return values

    @model_validator(mode="after")
    def validate_fallback(self) -> Self:
        _canonical_codes((self.fallback_version,), field_name="fallback_version")
        if self.estimated_duration_seconds != self.requested_duration_minutes * 60:
            raise ValueError("fallback plan must preserve exact requested duration")
        if self.fallback_plan_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"fallback_plan_hash"})
        ):
            raise ValueError("fallback_plan_hash does not match fallback plan")
        return self

    @property
    def source_hash(self) -> str:
        return self.fallback_plan_hash

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": DETERMINISTIC_FALLBACK_PLAN_SCHEMA_VERSION, **values}
        payload["fallback_plan_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


class CompiledExercise(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    prescription: ExercisePrescription
    catalog_record: ExercisePoolExerciseRecord

    @model_validator(mode="after")
    def validate_record_link(self) -> Self:
        if self.prescription.exercise_id != self.catalog_record.exercise_id:
            raise ValueError("compiled prescription and catalog record IDs must match")
        return self


class CompiledPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["compiled-plan-v1"] = COMPILED_PLAN_SCHEMA_VERSION
    compiler_version: str
    envelope_hash: str
    pool_hash: str
    source_plan_hash: str
    action_code: PlanActionCode
    requested_duration_minutes: int = Field(gt=0)
    estimated_duration_seconds: int = Field(gt=0)
    duration_verification_code: Literal["PLAN_SPEC_EXACT_DURATION_ASSERTED"] = (
        DURATION_VERIFICATION_CODE
    )
    exercises: tuple[CompiledExercise, ...] = Field(min_length=1)
    compiled_plan_hash: str

    @field_validator("envelope_hash", "pool_hash", "source_plan_hash", "compiled_plan_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _hash_value(value, field_name="compiled plan hash")

    @model_validator(mode="after")
    def validate_compiled_plan(self) -> Self:
        _canonical_codes((self.compiler_version,), field_name="compiler_version")
        prescriptions = tuple(item.prescription for item in self.exercises)
        _validate_prescription_order(prescriptions)
        if self.estimated_duration_seconds != self.requested_duration_minutes * 60:
            raise ValueError("compiled plan must preserve exact requested duration")
        if self.compiled_plan_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"compiled_plan_hash"})
        ):
            raise ValueError("compiled_plan_hash does not match compiled plan")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {
            "schema_version": COMPILED_PLAN_SCHEMA_VERSION,
            "duration_verification_code": DURATION_VERIFICATION_CODE,
            **values,
        }
        payload["compiled_plan_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


def _source_hash(plan: PlanSpec | DeterministicFallbackPlanSpec) -> str:
    return plan.plan_hash if isinstance(plan, PlanSpec) else plan.fallback_plan_hash


def compile_plan(
    plan: PlanSpec | DeterministicFallbackPlanSpec,
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    compiler_version: str,
    coordinator_input: CoordinatorInput | None = None,
) -> CompiledPlan:
    """Resolve existing exercise references without selecting or replacing exercises.

    The current prescription contract has no reviewed seconds-per-repetition value.
    Compilation therefore preserves the already exact PlanSpec duration assertion and
    deliberately does not invent component-duration arithmetic.
    """

    _canonical_codes((compiler_version,), field_name="compiler_version")
    if isinstance(plan, PlanSpec):
        if coordinator_input is None:
            raise ValueError("LLM PlanSpec compilation requires CoordinatorInput")
        plan.validate_against(coordinator_input)
    elif coordinator_input is not None:
        raise ValueError("deterministic fallback cannot claim LLM CoordinatorInput")

    if plan.envelope_hash != envelope.envelope_hash or plan.pool_hash != pool.pool_hash:
        raise ValueError("plan references another envelope or pool")
    if plan.requested_duration_minutes != envelope.requested_duration_minutes:
        raise ValueError("compiler cannot change requested duration")
    _validate_prescription_constraints(plan.exercise_prescriptions, envelope=envelope, pool=pool)
    prescribed_ids = {item.exercise_id for item in plan.exercise_prescriptions}
    if not set(envelope.mandatory_exercise_ids).issubset(prescribed_ids):
        raise ValueError("compiled plan cannot remove mandatory exercises")

    records = {item.exercise_id: item for item in pool.exercises}
    exercises = tuple(
        CompiledExercise(prescription=item, catalog_record=records[item.exercise_id])
        for item in plan.exercise_prescriptions
    )
    return CompiledPlan.create(
        compiler_version=compiler_version,
        envelope_hash=envelope.envelope_hash,
        pool_hash=pool.pool_hash,
        source_plan_hash=_source_hash(plan),
        action_code=plan.action_code,
        requested_duration_minutes=plan.requested_duration_minutes,
        estimated_duration_seconds=plan.estimated_duration_seconds,
        exercises=exercises,
    )


__all__ = [
    "COMPILED_PLAN_SCHEMA_VERSION",
    "DETERMINISTIC_FALLBACK_PLAN_SCHEMA_VERSION",
    "DURATION_VERIFICATION_CODE",
    "CompiledExercise",
    "CompiledPlan",
    "DeterministicFallbackPlanSpec",
    "compile_plan",
]
