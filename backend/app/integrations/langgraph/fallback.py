"""Deterministic, safety-bounded fallback for the V3 demo graph."""

from __future__ import annotations

from collections.abc import Sequence
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
    PlanDurationPreferenceCode,
    accepts_additional_seconds,
    plan_duration_preference,
    plan_duration_seconds,
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

DETERMINISTIC_FALLBACK_VERSION = "v3-deterministic-fallback-v2"


@dataclass(frozen=True, slots=True)
class DeterministicGraphFallbackProvider:
    """Build a conservative plan only from the already-approved immutable pool.

    A fallback is still a downshift, so it lowers intensity and load to the
    lowest value the envelope allows while keeping the user's requested
    duration (AGENTS.md section 7). Time is filled with approved movements and
    longer between-set recovery rather than by driving any exercise past its
    work ceiling.
    """

    fallback_version: str = DETERMINISTIC_FALLBACK_VERSION

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
            candidates = tuple(
                exercise_id
                for exercise_id in ordered_ids
                if _serves_phase(records.get(exercise_id), phase_code)
            )
            # Prefer a movement whose family this session has not used yet, so
            # filling a required phase does not quietly spend a second slot on a
            # variant of something already prescribed. Preference, not a filter:
            # a plan missing its warmup or cooldown is invalid outright, which is
            # a worse outcome than one repeated family.
            if not any(
                place(exercise_id, phase_code, required=True)
                for exercise_id in self._unused_family_first(candidates, records, placed)
            ):
                # The approved pool carries no candidate for this phase, so no
                # valid session can be built from it.
                return None

        # Among equally approved candidates, take the ones whose reviewed volume
        # spans more than one set first. A single-set block has no gap between
        # sets, so it offers the session no recovery time of its own; filling a
        # long request out of single-set blocks leaves the whole shortfall to be
        # absorbed by the few multi-set blocks that happen to be present, which
        # is how a thirty-minute LIGHT session ended up prescribing rests of
        # nearly four minutes. Relative rank is preserved inside each group, so
        # this reorders equals rather than overriding retrieval.
        for exercise_id in self._time_bearing_first(ordered_ids, records, envelope):
            distinct_ids = {placed_id for placed_id, _ in placed}
            if exercise_id in distinct_ids or len(distinct_ids) >= MAX_PLAN_EXERCISE_TYPES:
                continue
            record = records.get(exercise_id)
            if record is None:
                continue
            # One movement per family. The catalog groups near-identical variants
            # under a family code -- barbell, seated and smith good mornings are
            # one family -- and taking several of them spends the session's
            # exercise budget without giving the user anything new to do. Read
            # from what is already placed so the mandatory and structural blocks
            # above claim their families too. A record with no family code groups
            # with nothing, so those are never skipped.
            placed_families = {
                placed_record.family_code
                for placed_id, _ in placed
                if (placed_record := records.get(placed_id)) is not None
                and placed_record.family_code
            }
            if record.family_code and record.family_code in placed_families:
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
        prescriptions = self._extend_rests_to_duration(
            prescriptions,
            records=records,
            target_seconds=target_seconds,
            preference=preference,
        )
        estimated_seconds = plan_duration_seconds(prescriptions, records)
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
    def _unused_family_first(
        exercise_ids: tuple[UUID, ...],
        records: dict[UUID, ExercisePoolExerciseRecord],
        placed: Sequence[tuple[UUID, PhaseCode]],
    ) -> tuple[UUID, ...]:
        """Stable partition: candidates from an as-yet-unused family come first."""

        used = {
            record.family_code
            for placed_id, _ in placed
            if (record := records.get(placed_id)) is not None and record.family_code
        }
        fresh: list[UUID] = []
        repeated: list[UUID] = []
        for exercise_id in exercise_ids:
            record = records.get(exercise_id)
            family_code = None if record is None else record.family_code
            target = repeated if family_code and family_code in used else fresh
            target.append(exercise_id)
        return (*fresh, *repeated)

    @staticmethod
    def _time_bearing_first(
        ordered_ids: tuple[UUID, ...],
        records: dict[UUID, ExercisePoolExerciseRecord],
        envelope: ConstraintEnvelope,
    ) -> tuple[UUID, ...]:
        """Stable partition: candidates carrying a rest gap of their own come first."""

        multi_set: list[UUID] = []
        single_set: list[UUID] = []
        for exercise_id in ordered_ids:
            record = records.get(exercise_id)
            prescription = (
                None
                if record is None
                else DeterministicGraphFallbackProvider._prescribe(
                    record, envelope=envelope, sequence=1, phase_code="MAIN"
                )
            )
            target = multi_set if prescription is not None and prescription.sets > 1 else single_set
            target.append(exercise_id)
        return (*multi_set, *single_set)

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
    def _extend_rests_to_duration(
        prescriptions: tuple[ExercisePrescription, ...],
        *,
        records: dict[UUID, ExercisePoolExerciseRecord],
        target_seconds: int,
        preference: PlanDurationPreferenceCode,
    ) -> tuple[ExercisePrescription, ...]:
        """Fill a short safe plan by lengthening its already-approved rest structure.

        Recovery ceilings place a lower bound on rest and upper bounds on work.
        Increasing rest therefore cannot relax Safety or Recovery.  It also avoids
        adding needless movements or exceeding a per-exercise set ceiling merely to
        reach the requested duration.  A prescription stores one rest value for all
        of its between-set gaps, so the small subset calculation below finds the
        nearest deterministic whole-second distribution without inventing work.
        """

        current_seconds = plan_duration_seconds(prescriptions, records)
        desired_seconds = (
            target_seconds - DURATION_TOLERANCE_SECONDS
            if preference is PlanDurationPreferenceCode.SHORTER_WITHIN_WINDOW
            else target_seconds
        )
        deficit = desired_seconds - current_seconds
        rest_slots = tuple(max(item.sets - 1, 0) for item in prescriptions)
        total_slots = sum(rest_slots)
        if deficit <= 0 or total_slots == 0:
            return prescriptions

        seconds_per_slot, remainder = divmod(deficit, total_slots)
        selected: set[int] = set()
        if remainder:
            # At most ten distinct exercises are present, so exhaustive subset
            # selection is bounded and gives a stable closest non-short result.
            candidates = tuple(index for index, slots in enumerate(rest_slots) if slots)
            best: tuple[int, tuple[int, ...]] | None = None
            for mask in range(1 << len(candidates)):
                indices = tuple(
                    candidates[offset] for offset in range(len(candidates)) if mask & (1 << offset)
                )
                added = sum(rest_slots[index] for index in indices)
                if added < remainder:
                    continue
                choice = (added, indices)
                if best is None or choice < best:
                    best = choice
            if best is not None:
                selected.update(best[1])

        return tuple(
            item.model_copy(
                update={
                    "rest_seconds_between_sets": item.rest_seconds_between_sets
                    + seconds_per_slot
                    + (1 if index in selected else 0)
                }
            )
            if rest_slots[index]
            else item
            for index, item in enumerate(prescriptions)
        )

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


__all__ = ["DETERMINISTIC_FALLBACK_VERSION", "DeterministicGraphFallbackProvider"]
