"""Deterministic integrity assertions for already-decided V3 compiled plans."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import CompiledPlan
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    _canonical_codes,
    _canonical_hash,
    _canonical_ids,
    _hash_value,
)
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE
from backend.app.domain.rules.plan_shape import (
    MAX_PHASE_EXERCISE_TYPES,
    MAX_PLAN_EXERCISE_TYPES,
    PLAN_PHASE_ORDER,
    families_over_budget,
    has_consecutive_main_repetition,
    phase_rank,
)
from backend.app.domain.rules.safety import SafetyRequiredActionCode

INTEGRITY_VALIDATION_SCHEMA_VERSION: Final[Literal["plan-integrity-validation-v1"]] = (
    "plan-integrity-validation-v1"
)


class IntegrityViolationCode(StrEnum):
    ENVELOPE_HASH_MISMATCH = "ENVELOPE_HASH_MISMATCH"
    POOL_HASH_MISMATCH = "POOL_HASH_MISMATCH"
    REQUESTED_DURATION_MISMATCH = "REQUESTED_DURATION_MISMATCH"
    PRESCRIPTION_SCHEMA_INVALID = "PRESCRIPTION_SCHEMA_INVALID"
    MANDATORY_EXERCISE_MISSING = "MANDATORY_EXERCISE_MISSING"
    EXERCISE_OUTSIDE_POOL = "EXERCISE_OUTSIDE_POOL"
    SAFETY_EXCLUDED_EXERCISE_INCLUDED = "SAFETY_EXCLUDED_EXERCISE_INCLUDED"
    LOCATION_NOT_ALLOWED = "LOCATION_NOT_ALLOWED"
    EQUIPMENT_NOT_AVAILABLE = "EQUIPMENT_NOT_AVAILABLE"
    RECOVERY_CEILING_EXCEEDED = "RECOVERY_CEILING_EXCEEDED"
    FITT_RANGE_UNAVAILABLE = "FITT_RANGE_UNAVAILABLE"
    FITT_RANGE_EXCEEDED = "FITT_RANGE_EXCEEDED"
    PLAN_PHASE_COVERAGE_INVALID = "PLAN_PHASE_COVERAGE_INVALID"
    PLAN_EXERCISE_VARIETY_EXCEEDED = "PLAN_EXERCISE_VARIETY_EXCEEDED"
    PLAN_PHASE_REPETITION_INVALID = "PLAN_PHASE_REPETITION_INVALID"
    PLAN_MAIN_REPEAT_CONSECUTIVE = "PLAN_MAIN_REPEAT_CONSECUTIVE"
    PLAN_EXERCISE_FAMILY_REPEATED = "PLAN_EXERCISE_FAMILY_REPEATED"
    CATALOG_RECORD_MISMATCH = "CATALOG_RECORD_MISMATCH"
    STOP_AND_SEEK_HELP = "STOP_AND_SEEK_HELP"
    PLAN_GENERATION_FORBIDDEN = "PLAN_GENERATION_FORBIDDEN"
    APPROVED_SAFE_EXERCISE_UNAVAILABLE = "APPROVED_SAFE_EXERCISE_UNAVAILABLE"
    REQUIRED_INPUT_MISSING = "REQUIRED_INPUT_MISSING"
    POLICY_DATA_INCOMPLETE = "POLICY_DATA_INCOMPLETE"
    TOTAL_LLM_PROVIDER_FAILURE = "TOTAL_LLM_PROVIDER_FAILURE"
    REPAIR_ATTEMPT_EXHAUSTED = "REPAIR_ATTEMPT_EXHAUSTED"
    FALLBACK_PLAN_INVALID = "FALLBACK_PLAN_INVALID"


_VIOLATION_ORDER = tuple(IntegrityViolationCode)
# A repair is only worth routing to when the Coordinator has somewhere to go,
# and the two ways of having somewhere to go are not the same (ADR-0022).
#
# Replacing an exercise Safety removed needs an exercise Safety approved in its
# place -- the pool at large is not an answer to "what may this user do
# instead". Rearranging a plan needs no such blessing: the pool is already the
# approved candidate set, because PostgreSQL decides eligibility and the
# envelope's exclusions are applied before the snapshot is built.
_SUBSTITUTION_REPAIRABLE = frozenset(
    {
        IntegrityViolationCode.SAFETY_EXCLUDED_EXERCISE_INCLUDED,
    }
)

# Shape and dosage violations are the Coordinator's to correct within the pool
# it was already given: the pool reserves candidates for every phase, so one
# repair round can restore the shape without weakening any safety bound. The
# repaired plan is re-validated by this same function at `repair_attempt=1`, so
# nothing here admits a plan that would otherwise have been refused -- when
# repair does not fix it, REPAIR_ATTEMPT_EXHAUSTED sends the request to the
# deterministic fallback, which builds the same shape from the same pool.
_POOL_REPAIRABLE = frozenset(
    {
        IntegrityViolationCode.REQUESTED_DURATION_MISMATCH,
        IntegrityViolationCode.PRESCRIPTION_SCHEMA_INVALID,
        IntegrityViolationCode.MANDATORY_EXERCISE_MISSING,
        IntegrityViolationCode.LOCATION_NOT_ALLOWED,
        IntegrityViolationCode.EQUIPMENT_NOT_AVAILABLE,
        IntegrityViolationCode.RECOVERY_CEILING_EXCEEDED,
        IntegrityViolationCode.FITT_RANGE_EXCEEDED,
        IntegrityViolationCode.FITT_RANGE_UNAVAILABLE,
        IntegrityViolationCode.PLAN_PHASE_COVERAGE_INVALID,
        IntegrityViolationCode.PLAN_EXERCISE_VARIETY_EXCEEDED,
        IntegrityViolationCode.PLAN_PHASE_REPETITION_INVALID,
        IntegrityViolationCode.PLAN_MAIN_REPEAT_CONSECUTIVE,
        IntegrityViolationCode.PLAN_EXERCISE_FAMILY_REPEATED,
    }
)


def _is_repairable(
    code: IntegrityViolationCode,
    *,
    repair_attempt: int,
    has_approved_alternative: bool,
    pool_can_supply_repair: bool,
) -> bool:
    """Whether one repair round could plausibly clear this violation.

    Never a safety judgement: a repaired plan is re-validated in full, so this
    only decides whether spending the round is worth it.
    """

    if repair_attempt != 0:
        return False
    if code in _SUBSTITUTION_REPAIRABLE:
        return has_approved_alternative
    return code in _POOL_REPAIRABLE and pool_can_supply_repair


class IntegrityValidationStatusCode(StrEnum):
    PASS = "PASS"
    REPAIRABLE = "REPAIRABLE"
    NON_REPAIRABLE = "NON_REPAIRABLE"


class IntegrityValidationContext(BaseModel):
    """Upstream facts used for classification, never a new Safety evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approved_safe_alternative_ids: tuple[UUID, ...] = ()
    required_inputs_complete: bool = True
    policy_data_complete: bool = True
    total_llm_provider_failure: bool = False
    fallback_plan_validation: bool = False

    @field_validator("approved_safe_alternative_ids")
    @classmethod
    def validate_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _canonical_ids(values, field_name="approved_safe_alternative_ids")


class IntegrityViolation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: IntegrityViolationCode
    repairable: bool


class IntegrityValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["plan-integrity-validation-v1"] = INTEGRITY_VALIDATION_SCHEMA_VERSION
    validator_version: str
    envelope_hash: str
    pool_hash: str
    compiled_plan_hash: str | None
    repair_attempt: int
    status_code: IntegrityValidationStatusCode
    violations: tuple[IntegrityViolation, ...]
    validation_hash: str

    @field_validator("envelope_hash", "pool_hash", "validation_hash")
    @classmethod
    def validate_required_hashes(cls, value: str) -> str:
        return _hash_value(value, field_name="integrity hash")

    @field_validator("compiled_plan_hash")
    @classmethod
    def validate_optional_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _hash_value(value, field_name="compiled_plan_hash")

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        _canonical_codes((self.validator_version,), field_name="validator_version")
        if self.repair_attempt not in (0, 1):
            raise ValueError("repair_attempt must be 0 or 1")
        codes = tuple(item.code for item in self.violations)
        if codes != tuple(sorted(set(codes), key=_VIOLATION_ORDER.index)):
            raise ValueError("integrity violations must be unique and canonical")
        if self.status_code is IntegrityValidationStatusCode.PASS:
            if self.violations or self.compiled_plan_hash is None:
                raise ValueError("PASS requires a compiled plan and no violations")
        elif not self.violations:
            raise ValueError("failed validation requires at least one violation")
        if self.status_code is IntegrityValidationStatusCode.REPAIRABLE and not all(
            item.repairable for item in self.violations
        ):
            raise ValueError("REPAIRABLE result cannot contain non-repairable violations")
        if self.status_code is IntegrityValidationStatusCode.NON_REPAIRABLE and all(
            item.repairable for item in self.violations
        ):
            raise ValueError("NON_REPAIRABLE result must retain a terminal violation")
        if self.validation_hash != _canonical_hash(
            self.model_dump(mode="json", exclude={"validation_hash"})
        ):
            raise ValueError("validation_hash does not match integrity result")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = {"schema_version": INTEGRITY_VALIDATION_SCHEMA_VERSION, **values}
        payload["validation_hash"] = _canonical_hash(payload)
        return cls.model_validate(payload)


def _recovery_exceeded(compiled_plan: CompiledPlan, envelope: ConstraintEnvelope) -> bool:
    ceiling = envelope.recovery_ceiling
    sets_by_exercise: dict[UUID, int] = {}
    for compiled in compiled_plan.exercises:
        item = compiled.prescription
        sets_by_exercise[item.exercise_id] = sets_by_exercise.get(item.exercise_id, 0) + item.sets
        if (
            ceiling.allowed_intensity_codes
            and item.intensity_code not in ceiling.allowed_intensity_codes
        ):
            return True
        per_exercise_ceiling = next(
            (
                value
                for value in ceiling.per_exercise_volume_ceilings
                if value.exercise_id == item.exercise_id
            ),
            None,
        )
        if per_exercise_ceiling is not None and (
            item.sets > per_exercise_ceiling.maximum_sets_per_exercise
            or (
                item.repetitions_per_set is not None
                and item.repetitions_per_set > per_exercise_ceiling.maximum_repetitions_per_set
            )
        ):
            return True
        if ceiling.allowed_load_codes and item.load_code not in ceiling.allowed_load_codes:
            return True
        if any(
            actual is not None and maximum is not None and actual > maximum
            for actual, maximum in (
                (item.repetitions_per_set, ceiling.maximum_repetitions_per_set),
                (item.work_seconds_per_set, ceiling.maximum_work_seconds_per_set),
            )
        ):
            return True
        if (
            ceiling.minimum_rest_seconds_between_sets is not None
            and item.rest_seconds_between_sets < ceiling.minimum_rest_seconds_between_sets
        ):
            return True
    if ceiling.maximum_sets_per_exercise is not None and any(
        sets > ceiling.maximum_sets_per_exercise for sets in sets_by_exercise.values()
    ):
        return True
    return False


def _fitt_violation_codes(compiled_plan: CompiledPlan) -> set[IntegrityViolationCode]:
    """Check the reviewed FITT range for the exercises one actually covers.

    No reviewed range covers every catalog entry. Where none covers an exercise
    the Recovery ceiling checked by `_recovery_exceeded` is the operative bound,
    so an absent range is not a violation of anything -- reporting it as one
    would reject every plan while bounding no volume at all.
    """

    codes: set[IntegrityViolationCode] = set()
    for compiled in compiled_plan.exercises:
        prescription = compiled.prescription
        record = compiled.catalog_record
        if record.timing_mode_code != "REPS":
            continue
        volume = record.approved_fitt_volume()
        if volume is None:
            continue
        if prescription.repetitions_per_set is None:
            # An approved range exists and the prescription omitted the value it
            # bounds. That is the Coordinator's to correct, not missing data.
            codes.add(IntegrityViolationCode.FITT_RANGE_UNAVAILABLE)
            continue
        if not (
            volume.min_sets <= prescription.sets <= volume.max_sets
            and volume.min_reps <= prescription.repetitions_per_set <= volume.max_reps
        ):
            codes.add(IntegrityViolationCode.FITT_RANGE_EXCEEDED)
    return codes


def validate_plan_integrity(
    compiled_plan: CompiledPlan | None,
    *,
    envelope: ConstraintEnvelope,
    pool: ExercisePoolSnapshot,
    repair_attempt: int,
    validator_version: str,
    context: IntegrityValidationContext,
) -> IntegrityValidationResult:
    """Assert the frozen envelope; do not rerun or reinterpret SafetyPolicyEngine."""

    if repair_attempt not in (0, 1):
        raise ValueError("repair_attempt must be 0 or 1")
    codes: set[IntegrityViolationCode] = set()
    if envelope.safety_required_action_code is SafetyRequiredActionCode.STOP_AND_SEEK_HELP:
        codes.add(IntegrityViolationCode.STOP_AND_SEEK_HELP)
    if not envelope.plan_generation_allowed:
        codes.add(IntegrityViolationCode.PLAN_GENERATION_FORBIDDEN)
    if not context.required_inputs_complete:
        codes.add(IntegrityViolationCode.REQUIRED_INPUT_MISSING)
    if not context.policy_data_complete:
        codes.add(IntegrityViolationCode.POLICY_DATA_INCOMPLETE)
    if context.total_llm_provider_failure:
        codes.add(IntegrityViolationCode.TOTAL_LLM_PROVIDER_FAILURE)
    if not pool.exercises:
        codes.add(IntegrityViolationCode.APPROVED_SAFE_EXERCISE_UNAVAILABLE)

    if compiled_plan is None:
        if context.fallback_plan_validation:
            codes.add(IntegrityViolationCode.FALLBACK_PLAN_INVALID)
        elif not codes:
            codes.add(IntegrityViolationCode.REQUIRED_INPUT_MISSING)
    else:
        if compiled_plan.envelope_hash != envelope.envelope_hash:
            codes.add(IntegrityViolationCode.ENVELOPE_HASH_MISMATCH)
        if compiled_plan.pool_hash != pool.pool_hash:
            codes.add(IntegrityViolationCode.POOL_HASH_MISMATCH)
        # The compiled duration is measured from the catalog timing basis, so this
        # compares what the plan actually costs against what the user asked for.
        # Comparing it to requested_duration_minutes * 60 would be an identity now
        # that the compiler computes the value, and would verify nothing.
        target_seconds = envelope.requested_duration_minutes * SECONDS_PER_MINUTE
        duration_delta = abs(compiled_plan.estimated_duration_seconds - target_seconds)
        if (
            compiled_plan.requested_duration_minutes != envelope.requested_duration_minutes
            or duration_delta > DURATION_TOLERANCE_SECONDS
        ):
            codes.add(IntegrityViolationCode.REQUESTED_DURATION_MISMATCH)
        sequences = tuple(item.prescription.sequence for item in compiled_plan.exercises)
        if sequences != tuple(range(1, len(compiled_plan.exercises) + 1)):
            codes.add(IntegrityViolationCode.PRESCRIPTION_SCHEMA_INVALID)
        pool_records = {item.exercise_id: item for item in pool.exercises}
        ids = tuple(item.prescription.exercise_id for item in compiled_plan.exercises)
        if not set(envelope.mandatory_exercise_ids).issubset(ids):
            codes.add(IntegrityViolationCode.MANDATORY_EXERCISE_MISSING)
        if not set(ids).issubset(pool_records):
            codes.add(IntegrityViolationCode.EXERCISE_OUTSIDE_POOL)
        if set(ids) & set(envelope.excluded_exercise_ids):
            codes.add(IntegrityViolationCode.SAFETY_EXCLUDED_EXERCISE_INCLUDED)
        # Session shape. The prompts ask for a warmup and a cooldown, but asking
        # is not enforcing: an LLM that answered with twelve MAIN blocks used to
        # reach the user unchallenged. Enforce it here, downstream of the
        # coordinator, where every other plan bound is already asserted.
        phases = tuple(item.prescription.phase_code for item in compiled_plan.exercises)
        ranks = [phase_rank(phase) for phase in phases]
        if set(phases) != set(PLAN_PHASE_ORDER) or ranks != sorted(ranks):
            codes.add(IntegrityViolationCode.PLAN_PHASE_COVERAGE_INVALID)
        if len(set(ids)) > MAX_PLAN_EXERCISE_TYPES:
            codes.add(IntegrityViolationCode.PLAN_EXERCISE_VARIETY_EXCEEDED)
        # Near-identical variants share a catalog family code, so a plan naming
        # three good mornings is padding the session rather than varying it.
        # Deterministic selection already refuses this; assert it here so a plan
        # that came from the LLM cannot reach the user with it either.
        if families_over_budget(
            (item.prescription.exercise_id, record.family_code)
            for item in compiled_plan.exercises
            if (record := pool_records.get(item.prescription.exercise_id)) is not None
        ):
            codes.add(IntegrityViolationCode.PLAN_EXERCISE_FAMILY_REPEATED)
        for phase_code, cap in MAX_PHASE_EXERCISE_TYPES.items():
            phase_ids = tuple(
                item.prescription.exercise_id
                for item in compiled_plan.exercises
                if item.prescription.phase_code == phase_code
            )
            if len(set(phase_ids)) > cap:
                codes.add(IntegrityViolationCode.PLAN_EXERCISE_VARIETY_EXCEEDED)
            if len(phase_ids) != len(set(phase_ids)):
                codes.add(IntegrityViolationCode.PLAN_PHASE_REPETITION_INVALID)
        if has_consecutive_main_repetition(tuple(zip(ids, phases, strict=True))):
            codes.add(IntegrityViolationCode.PLAN_MAIN_REPEAT_CONSECUTIVE)
        for item in compiled_plan.exercises:
            prescription = item.prescription
            canonical = pool_records.get(prescription.exercise_id)
            if canonical is None:
                continue
            if (
                item.catalog_record != canonical
                or canonical.catalog_version != envelope.catalog_version
            ):
                codes.add(IntegrityViolationCode.CATALOG_RECORD_MISMATCH)
            if (
                prescription.location_code not in envelope.allowed_location_codes
                or prescription.location_code not in canonical.location_codes
            ):
                codes.add(IntegrityViolationCode.LOCATION_NOT_ALLOWED)
            # A phase is a reviewed property of the exercise, so a plan may not
            # call a loaded compound lift a cooldown. Records that predate the
            # phase projection carry no phase_codes and are left to the
            # plan-level coverage check above.
            if canonical.phase_codes and prescription.phase_code not in canonical.phase_codes:
                codes.add(IntegrityViolationCode.PLAN_PHASE_COVERAGE_INVALID)
            # Equipment is not a gate. The 2026-08-27 approval dropped it from
            # onboarding, so a user has no UserEquipment rows and the envelope
            # allowlist is empty by design. Comparing against it rejected every
            # plan that named any equipment at all, BODYWEIGHT included, which
            # failed the whole graph after all three agents had answered.
            #
            # The catalog link below is the part that has to hold: a plan may
            # not claim equipment the reviewed record does not list.
            if not set(prescription.equipment_codes).issubset(canonical.equipment_codes):
                codes.add(IntegrityViolationCode.EQUIPMENT_NOT_AVAILABLE)
        if _recovery_exceeded(compiled_plan, envelope):
            codes.add(IntegrityViolationCode.RECOVERY_CEILING_EXCEEDED)
        codes.update(_fitt_violation_codes(compiled_plan))

    if repair_attempt == 1 and codes:
        codes.add(IntegrityViolationCode.REPAIR_ATTEMPT_EXHAUSTED)
    safe_alternative_ids = set(context.approved_safe_alternative_ids)
    pool_ids = {item.exercise_id for item in pool.exercises}
    has_approved_alternative = bool(
        safe_alternative_ids
        and safe_alternative_ids.issubset(pool_ids)
        and safe_alternative_ids.isdisjoint(envelope.excluded_exercise_ids)
    )
    # The pool is the approved candidate set, so a rearranging repair has
    # somewhere to go as soon as the pool holds anything Safety did not exclude.
    pool_can_supply_repair = bool(pool_ids - set(envelope.excluded_exercise_ids))
    ordered_codes = tuple(code for code in _VIOLATION_ORDER if code in codes)
    violations = tuple(
        IntegrityViolation(
            code=code,
            repairable=_is_repairable(
                code,
                repair_attempt=repair_attempt,
                has_approved_alternative=has_approved_alternative,
                pool_can_supply_repair=pool_can_supply_repair,
            ),
        )
        for code in ordered_codes
    )
    if not violations:
        status = IntegrityValidationStatusCode.PASS
    elif all(item.repairable for item in violations):
        status = IntegrityValidationStatusCode.REPAIRABLE
    else:
        status = IntegrityValidationStatusCode.NON_REPAIRABLE
    return IntegrityValidationResult.create(
        validator_version=validator_version,
        envelope_hash=envelope.envelope_hash,
        pool_hash=pool.pool_hash,
        compiled_plan_hash=(compiled_plan.compiled_plan_hash if compiled_plan else None),
        repair_attempt=repair_attempt,
        status_code=status,
        violations=violations,
    )


__all__ = [
    "INTEGRITY_VALIDATION_SCHEMA_VERSION",
    "IntegrityValidationContext",
    "IntegrityValidationResult",
    "IntegrityValidationStatusCode",
    "IntegrityViolation",
    "IntegrityViolationCode",
    "validate_plan_integrity",
]
