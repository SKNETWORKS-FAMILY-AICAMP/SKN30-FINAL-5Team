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
from backend.app.domain.agents.v3_duration import (
    accepts_additional_seconds,
    plan_duration_preference,
    prescription_item_duration,
)
from backend.app.domain.agents.v3_orchestration import FallbackRequest
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS, SECONDS_PER_MINUTE
from backend.app.domain.rules.plan_shape import (
    MAX_MAIN_BLOCKS_PER_EXERCISE,
    MAX_PHASE_EXERCISE_TYPES,
    MAX_PLAN_EXERCISE_TYPES,
    PhaseCode,
    has_consecutive_main_repetition,
    phase_rank,
)


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
        # Which end of the approved window to settle on is the ladder's time axis
        # (DOMAIN_RULES 6.1 rung 3), read off the envelope so a replay builds the
        # same plan. Without an adjustment the request itself is the target.
        preference = plan_duration_preference(envelope)

        # A fallback plan is still a session, so it is built phase by phase
        # rather than as a flat list. Integrity validation rejects a plan that
        # covers anything but WARMUP, MAIN and COOLDOWN, and this provider is
        # the path that request takes once the coordinator's repair round is
        # spent: it has to be able to satisfy the shape from the same pool.
        excluded = set(envelope.excluded_exercise_ids)
        required_ids = set(mandatory)
        placed: list[tuple[UUID, PhaseCode]] = []
        sets_by_exercise: dict[UUID, int] = {}
        estimated_seconds = 0

        def place(exercise_id: UUID, phase_code: PhaseCode, *, required: bool) -> bool:
            nonlocal estimated_seconds
            record = records.get(exercise_id)
            existing_phases = tuple(
                existing_phase
                for existing_id, existing_phase in placed
                if existing_id == exercise_id
            )
            if record is None or exercise_id in excluded:
                return False
            if phase_code != "MAIN" and existing_phases:
                return False
            if phase_code == "MAIN" and existing_phases:
                if "MAIN" not in existing_phases:
                    return False
                if existing_phases.count("MAIN") >= MAX_MAIN_BLOCKS_PER_EXERCISE:
                    return False
                if placed[-1] == (exercise_id, "MAIN"):
                    return False
            prescription = self._prescribe(
                record,
                envelope=envelope,
                sequence=len(placed) + 1,
                phase_code=phase_code,
            )
            if prescription is None:
                return False
            maximum_sets = envelope.recovery_ceiling.maximum_sets_per_exercise
            if (
                maximum_sets is not None
                and sets_by_exercise.get(exercise_id, 0) + prescription.sets > maximum_sets
            ):
                return False
            per_exercise_ceiling = next(
                (
                    item
                    for item in envelope.recovery_ceiling.per_exercise_volume_ceilings
                    if item.exercise_id == exercise_id
                ),
                None,
            )
            if (
                per_exercise_ceiling is not None
                and sets_by_exercise.get(exercise_id, 0) + prescription.sets
                > per_exercise_ceiling.maximum_sets_per_exercise
            ):
                return False
            item_seconds = prescription_item_duration(prescription, record).estimated_item_seconds
            # A mandatory exercise, and the one warmup and cooldown the shape
            # requires, are part of the plan whatever they cost; the window
            # check below still refuses a plan they push out of range.
            if not required and not accepts_additional_seconds(
                accumulated_seconds=estimated_seconds,
                additional_seconds=item_seconds,
                target_seconds=target_seconds,
                preference=preference,
            ):
                return False
            placed.append((exercise_id, phase_code))
            sets_by_exercise[exercise_id] = sets_by_exercise.get(exercise_id, 0) + prescription.sets
            estimated_seconds += item_seconds
            return True

        for exercise_id in mandatory:
            record = records.get(exercise_id)
            if record is None or exercise_id in excluded:
                return None
            if not place(exercise_id, _preferred_phase(record), required=True):
                # A mandatory exercise that cannot be prescribed inside the
                # envelope means no safe fallback exists for this request.
                return None

        # Preparation and settling come first, because a plan missing either one
        # is invalid however well the remaining time is filled.
        structural: tuple[PhaseCode, ...] = ("WARMUP", "COOLDOWN")
        for phase_code in structural:
            if any(value == phase_code for _, value in placed):
                continue
            if not any(
                place(exercise_id, phase_code, required=True)
                for exercise_id in ordered_ids
                if _serves_phase(records.get(exercise_id), phase_code)
            ):
                # The approved pool carries no candidate for this phase, so no
                # valid session can be built from it.
                return None

        for exercise_id in ordered_ids:
            distinct_ids = {placed_id for placed_id, _ in placed}
            if exercise_id in distinct_ids or len(distinct_ids) >= MAX_PLAN_EXERCISE_TYPES:
                continue
            record = records.get(exercise_id)
            if record is None:
                continue
            phase_code = _preferred_phase(record)
            cap = MAX_PHASE_EXERCISE_TYPES.get(phase_code)
            if cap is not None and sum(value == phase_code for _, value in placed) >= cap:
                continue
            place(exercise_id, phase_code, required=exercise_id in required_ids)

        main_ids = tuple(exercise_id for exercise_id, phase_code in placed if phase_code == "MAIN")
        while main_ids:
            added_in_round = False
            for exercise_id in main_ids:
                added_in_round = place(exercise_id, "MAIN", required=False) or added_in_round
            if not added_in_round:
                break

        prescriptions = self._ordered_prescriptions(placed, records=records, envelope=envelope)
        if prescriptions is None:
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

    def _ordered_prescriptions(
        self,
        placed: list[tuple[UUID, PhaseCode]],
        *,
        records: dict[UUID, ExercisePoolExerciseRecord],
        envelope: ConstraintEnvelope,
    ) -> tuple[ExercisePrescription, ...] | None:
        """Re-number the selected exercises into canonical WARMUP-MAIN-COOLDOWN order."""

        ordered = sorted(placed, key=lambda entry: phase_rank(entry[1]))
        if has_consecutive_main_repetition(ordered):
            return None
        prescriptions: list[ExercisePrescription] = []
        for sequence, (exercise_id, phase_code) in enumerate(ordered, start=1):
            prescription = self._prescribe(
                records[exercise_id],
                envelope=envelope,
                sequence=sequence,
                phase_code=phase_code,
            )
            if prescription is None:
                return None
            prescriptions.append(prescription)
        return tuple(prescriptions) or None

    @staticmethod
    def _prescribe(
        record: ExercisePoolExerciseRecord,
        *,
        envelope: ConstraintEnvelope,
        sequence: int,
        phase_code: PhaseCode,
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
        per_exercise_ceiling = next(
            (
                item
                for item in ceiling.per_exercise_volume_ceilings
                if item.exercise_id == record.exercise_id
            ),
            None,
        )

        if record.timing_mode_code == "DURATION":
            # A duration prescription is one reviewed work block. It is not
            # assigned the recovery maximum merely because that maximum exists.
            sets = 1
            repetitions = None
            work_seconds = record.default_work_seconds
            if ceiling.maximum_work_seconds_per_set is not None and work_seconds is not None:
                work_seconds = min(work_seconds, ceiling.maximum_work_seconds_per_set)
            if work_seconds is None:
                return None
        else:
            work_seconds = None
            volume = record.approved_fitt_volume()
            if volume is None:
                # No reviewed range covers this exercise. The Recovery ceiling is
                # then the only approved source of a volume, as it was before FITT
                # ranges existed; the fallback still declines rather than inventing
                # one of its own.
                repetitions = ceiling.maximum_repetitions_per_set
                if repetitions is None:
                    return None
                sets = ceiling.maximum_sets_per_exercise or 1
            else:
                sets = volume.default_sets
                repetitions = volume.default_reps
                if ceiling.maximum_sets_per_exercise is not None:
                    sets = min(sets, ceiling.maximum_sets_per_exercise)
                if ceiling.maximum_repetitions_per_set is not None:
                    repetitions = min(repetitions, ceiling.maximum_repetitions_per_set)
                if sets < volume.min_sets or repetitions < volume.min_reps:
                    return None
            if per_exercise_ceiling is not None:
                sets = min(sets, per_exercise_ceiling.maximum_sets_per_exercise)
                repetitions = min(repetitions, per_exercise_ceiling.maximum_repetitions_per_set)

        rest_seconds = max(
            ceiling.minimum_rest_seconds_between_sets or 0, record.default_rest_seconds
        )
        return ExercisePrescription(
            exercise_id=record.exercise_id,
            sequence=sequence,
            phase_code=phase_code,
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


def _serves_phase(record: ExercisePoolExerciseRecord | None, phase_code: PhaseCode) -> bool:
    return record is not None and phase_code in record.phase_codes


def _preferred_phase(record: ExercisePoolExerciseRecord) -> PhaseCode:
    """Pick the phase this record should serve, preferring goal-driving work.

    Main work carries the goal, so an exercise the catalog approves for MAIN is
    spent there. A record that predates the phase projection carries no
    phase_codes and can only be main work.
    """

    if not record.phase_codes or "MAIN" in record.phase_codes:
        return "MAIN"
    if "WARMUP" in record.phase_codes:
        return "WARMUP"
    return "COOLDOWN"


__all__ = ["DeterministicGraphFallbackProvider"]
