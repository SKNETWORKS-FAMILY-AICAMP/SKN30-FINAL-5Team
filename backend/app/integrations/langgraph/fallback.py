"""Deterministic, safety-bounded fallback for the V3 demo graph."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.app.domain.agents.retrieval import ExercisePoolExerciseRecord, ExercisePoolSnapshot
from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec
from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    ExercisePrescription,
    PlanActionCode,
)
from backend.app.domain.agents.v3_duration import prescription_item_duration
from backend.app.domain.agents.v3_orchestration import FallbackRequest
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE


@dataclass(frozen=True, slots=True)
class DeterministicGraphFallbackProvider:
    """Build a conservative plan only from the already-approved immutable pool.

    A fallback is still a downshift, so it lowers intensity and load to the
    lowest value the envelope allows while keeping the user's requested
    duration (AGENTS.md section 7). Time is filled by adding approved movements
    rather than by driving any single exercise past its recovery ceiling.
    """

    fallback_version: str = "v3-deterministic-fallback-v1"

    def generate(self, request: FallbackRequest) -> DeterministicFallbackPlanSpec | None:
        envelope = request.constraint_envelope
        pool = request.exercise_pool
        if (
            request.fallback_version != self.fallback_version
            or not envelope.plan_generation_allowed
            or envelope.safety_required_action_code is not None
            or not pool.exercises
        ):
            return None

        records = {item.exercise_id: item for item in pool.exercises}
        mandatory = tuple(envelope.mandatory_exercise_ids)
        ordered_ids = self._ordered_ids(pool, mandatory)
        target_seconds = envelope.requested_duration_minutes * SECONDS_PER_MINUTE

        prescriptions: list[ExercisePrescription] = []
        estimated_seconds = 0
        for exercise_id in ordered_ids:
            required = exercise_id in set(mandatory)
            if not required and estimated_seconds >= target_seconds - DURATION_TOLERANCE_SECONDS:
                break
            record = records.get(exercise_id)
            if record is None or exercise_id in set(envelope.excluded_exercise_ids):
                if required:
                    return None
                continue
            prescription = self._prescribe(
                record,
                envelope=envelope,
                sequence=len(prescriptions) + 1,
            )
            if prescription is None:
                # A mandatory exercise that cannot be prescribed inside the
                # envelope means no safe fallback exists for this request.
                if required:
                    return None
                continue
            prescriptions.append(prescription)
            estimated_seconds += prescription_item_duration(
                prescription, record
            ).estimated_item_seconds

        if not prescriptions:
            return None
        if abs(estimated_seconds - target_seconds) > DURATION_TOLERANCE_SECONDS:
            # Section 7 requires the request to fail rather than quietly hand the
            # user a session that is shorter than the one they asked for.
            return None

        return DeterministicFallbackPlanSpec.create(
            fallback_version=self.fallback_version,
            envelope_hash=envelope.envelope_hash,
            pool_hash=pool.pool_hash,
            action_code=PlanActionCode.DOWNSHIFT,
            requested_duration_minutes=envelope.requested_duration_minutes,
            estimated_duration_seconds=estimated_seconds,
            exercise_prescriptions=tuple(prescriptions),
            reason_codes=("LLM_PROVIDER_FALLBACK",),
        )

    @staticmethod
    def _ordered_ids(pool: ExercisePoolSnapshot, mandatory: tuple[UUID, ...]) -> tuple[UUID, ...]:
        ranked = pool.vector_ranked_exercise_ids
        chosen = set(mandatory)
        return (
            *mandatory,
            *(exercise_id for exercise_id in ranked if exercise_id not in chosen),
            *(
                item.exercise_id
                for item in pool.exercises
                if item.exercise_id not in chosen and item.exercise_id not in set(ranked)
            ),
        )

    @staticmethod
    def _prescribe(
        record: ExercisePoolExerciseRecord,
        *,
        envelope: ConstraintEnvelope,
        sequence: int,
    ) -> ExercisePrescription | None:
        location = next(
            (
                code
                for code in envelope.allowed_location_codes
                if code in set(record.location_codes)
            ),
            None,
        )
        if location is None:
            return None
        # Equipment is not a gate. The 2026-08-27 approval dropped it from
        # onboarding, so the envelope allowlist is empty by design; intersecting
        # with it discarded every record that names any equipment, BODYWEIGHT
        # included, and the deterministic fallback then had nothing to build
        # from. The prescription carries the reviewed record's own equipment so
        # the integrity validator can still check it against the catalog.
        equipment = tuple(record.equipment_codes)

        ceiling = envelope.recovery_ceiling
        intensity = ceiling.allowed_intensity_codes[0] if ceiling.allowed_intensity_codes else "LOW"
        load = ceiling.allowed_load_codes[0] if ceiling.allowed_load_codes else None
        sets = ceiling.maximum_sets_per_exercise or 1

        if record.timing_mode_code == "DURATION":
            repetitions = None
            work_seconds = record.default_work_seconds
            if ceiling.maximum_work_seconds_per_set is not None and work_seconds is not None:
                work_seconds = min(work_seconds, ceiling.maximum_work_seconds_per_set)
            if work_seconds is None:
                return None
        else:
            work_seconds = None
            # No approved repetition count exists outside the recovery ceiling, so
            # the fallback declines rather than inventing a volume of its own.
            repetitions = ceiling.maximum_repetitions_per_set
            if repetitions is None:
                return None

        rest_seconds = max(
            ceiling.minimum_rest_seconds_between_sets or 0, record.default_rest_seconds
        )
        return ExercisePrescription(
            exercise_id=record.exercise_id,
            sequence=sequence,
            sets=sets,
            repetitions_per_set=repetitions,
            work_seconds_per_set=work_seconds,
            rest_seconds_between_sets=rest_seconds,
            transition_seconds=record.default_transition_seconds,
            intensity_code=intensity,
            load_code=load,
            location_code=location,
            equipment_codes=equipment,
        )


__all__ = ["DeterministicGraphFallbackProvider"]
