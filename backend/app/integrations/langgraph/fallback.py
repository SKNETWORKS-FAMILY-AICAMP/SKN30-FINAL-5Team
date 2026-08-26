"""Deterministic, safety-bounded fallback for the V3 demo graph."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.agents.v3_compiler import DeterministicFallbackPlanSpec
from backend.app.domain.agents.v3_contracts import ExercisePrescription, PlanActionCode
from backend.app.domain.agents.v3_orchestration import FallbackRequest


@dataclass(frozen=True, slots=True)
class DeterministicGraphFallbackProvider:
    """Build a conservative plan only from the already-approved immutable pool."""

    fallback_version: str = "v3-deterministic-fallback-v1"
    maximum_optional_exercises: int = 3

    def __post_init__(self) -> None:
        if self.maximum_optional_exercises <= 0:
            raise ValueError("maximum_optional_exercises must be positive")

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
        ordered_ids = (
            *mandatory,
            *(
                exercise_id
                for exercise_id in pool.vector_ranked_exercise_ids
                if exercise_id not in set(mandatory)
            ),
            *(
                item.exercise_id
                for item in pool.exercises
                if item.exercise_id not in set(mandatory)
                and item.exercise_id not in set(pool.vector_ranked_exercise_ids)
            ),
        )
        selected_ids = (*mandatory, *ordered_ids[len(mandatory) : self.maximum_optional_exercises])
        if not selected_ids or not set(mandatory).issubset(selected_ids):
            return None

        prescriptions: list[ExercisePrescription] = []
        for sequence, exercise_id in enumerate(selected_ids, start=1):
            record = records.get(exercise_id)
            if record is None or exercise_id in set(envelope.excluded_exercise_ids):
                return None
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
            equipment = tuple(
                code
                for code in record.equipment_codes
                if code in set(envelope.allowed_equipment_codes)
            )
            if set(record.equipment_codes) and not equipment:
                return None
            ceiling = envelope.recovery_ceiling
            intensity = (
                ceiling.allowed_intensity_codes[0] if ceiling.allowed_intensity_codes else "LOW"
            )
            load = ceiling.allowed_load_codes[0] if ceiling.allowed_load_codes else None
            sets = min(1, ceiling.maximum_sets_per_exercise or 1)
            rest_seconds = ceiling.minimum_rest_seconds_between_sets or 0
            timed = any(
                marker in record.timing_mode_code for marker in ("DURATION", "SECOND", "TIME")
            )
            repetitions = None if timed else min(1, ceiling.maximum_repetitions_per_set or 1)
            work_seconds = min(30, ceiling.maximum_work_seconds_per_set or 30) if timed else None
            prescriptions.append(
                ExercisePrescription(
                    exercise_id=exercise_id,
                    sequence=sequence,
                    sets=sets,
                    repetitions_per_set=repetitions,
                    work_seconds_per_set=work_seconds,
                    rest_seconds_between_sets=rest_seconds,
                    transition_seconds=0,
                    intensity_code=intensity,
                    load_code=load,
                    location_code=location,
                    equipment_codes=equipment,
                )
            )

        return DeterministicFallbackPlanSpec.create(
            fallback_version=self.fallback_version,
            envelope_hash=envelope.envelope_hash,
            pool_hash=pool.pool_hash,
            action_code=PlanActionCode.DOWNSHIFT,
            requested_duration_minutes=envelope.requested_duration_minutes,
            estimated_duration_seconds=envelope.requested_duration_minutes * 60,
            exercise_prescriptions=tuple(prescriptions),
            reason_codes=("LLM_PROVIDER_FALLBACK",),
        )


__all__ = ["DeterministicGraphFallbackProvider"]
