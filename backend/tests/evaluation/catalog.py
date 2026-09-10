"""Fixed synthetic exercise catalog for reproducible service-quality evaluation.

Reviewed production catalog rows live in PostgreSQL and are not reachable from an
offline evaluation run.  This module builds a small, fully deterministic stand-in
that satisfies the same ``ExercisePoolExerciseRecord`` contract, so every case in
the dataset resolves to identical bytes on every machine.

The records here are evaluation fixtures, not catalog content: they carry
``eval-`` prefixed versions and reference codes precisely so they can never be
mistaken for reviewed production data (``AGENTS.md`` section 6, "Raw source data
and normalized application data must remain separate").
"""

from __future__ import annotations

from typing import Final
from uuid import UUID, uuid5

from backend.app.domain.agents.retrieval import (
    ExerciseFittContext,
    ExerciseFittVolumeRange,
    ExercisePoolExerciseRecord,
)

CATALOG_VERSION: Final = "eval-catalog-v1"
FITT_POLICY_VERSION: Final = "eval-fitt-policy-v1"

# A fixed namespace keeps every exercise UUID stable across machines and runs,
# which is what makes a stored evaluation result replayable.
_NAMESPACE: Final = UUID("6f1d5f2e-0f4c-4a2b-9c3d-8e7a1b2c3d4e")


def exercise_id_for(stable_code: str) -> UUID:
    """Return the deterministic UUID this evaluation catalog assigns to a code."""

    return uuid5(_NAMESPACE, stable_code)


def _record(
    stable_code: str,
    *,
    phase_codes: tuple[str, ...],
    role_eligibility_code: str,
    body_focus_code: str,
    movement_pattern_codes: tuple[str, ...],
    equipment_codes: tuple[str, ...] = ("BODYWEIGHT",),
    location_codes: tuple[str, ...] = ("HOME",),
    goal_codes: tuple[str, ...] = ("GENERAL_FITNESS",),
    family_code: str | None = None,
    difficulty_code: str = "BEGINNER",
    seconds_per_rep: int = 5,
    rest_seconds: int = 60,
    transition_seconds: int = 20,
    min_sets: int = 1,
    max_sets: int = 3,
    min_reps: int = 8,
    max_reps: int = 15,
    recovery_eligible: bool = True,
) -> ExercisePoolExerciseRecord:
    return ExercisePoolExerciseRecord(
        exercise_id=exercise_id_for(stable_code),
        catalog_version=CATALOG_VERSION,
        content_version=f"eval-content-{stable_code}",
        stable_code=stable_code,
        family_code=family_code,
        training_type_code="STRENGTH",
        body_focus_code=body_focus_code,
        movement_pattern_codes=movement_pattern_codes,
        difficulty_code=difficulty_code,
        timing_mode_code="REPS",
        default_seconds_per_rep=seconds_per_rep,
        default_rest_seconds=rest_seconds,
        default_transition_seconds=transition_seconds,
        fitt_context=ExerciseFittContext(
            source_code="eval-fitt-source-v1",
            policy_version=FITT_POLICY_VERSION,
            review_status_code="DOMAIN_APPROVED",
            template_id=f"EVAL-FITT-{stable_code}",
            frequency_code="PER_SESSION",
            intensity_code="MODERATE",
            time_mode_code="REPS",
            type_code="STRENGTH",
            volume=ExerciseFittVolumeRange(
                min_sets=min_sets,
                max_sets=max_sets,
                min_reps=min_reps,
                max_reps=max_reps,
                default_sets=min_sets,
                default_reps=min_reps,
            ),
        ),
        recovery_eligible=recovery_eligible,
        goal_codes=goal_codes,
        phase_codes=phase_codes,
        role_eligibility_code=role_eligibility_code,
        equipment_codes=equipment_codes,
        location_codes=location_codes,
        prescription_reference_codes=("eval-prescription-v1",),
        source_reference_codes=("eval-source-v1",),
        review_reference_codes=("eval-review-v1",),
    )


# Body areas follow `domain/rules/safety.BodyAreaCode` so a case can express
# "knee discomfort" and the excluded set is derivable rather than hand-listed.
KNEE_LOADING_CODES: Final[tuple[str, ...]] = (
    "SQUAT_BODYWEIGHT",
    "LUNGE_FORWARD",
    "WALL_SIT",
)
SHOULDER_LOADING_CODES: Final[tuple[str, ...]] = (
    "PUSHUP_KNEE",
    "OVERHEAD_PRESS_DUMBBELL",
)

_RECORDS: Final[tuple[ExercisePoolExerciseRecord, ...]] = (
    # --- WARMUP (SUPPORT tier) -------------------------------------------
    _record(
        "WARMUP_ARM_CIRCLE",
        phase_codes=("WARMUP",),
        role_eligibility_code="SUPPORT",
        body_focus_code="UPPER_BODY",
        movement_pattern_codes=("MOBILITY",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("GENERAL_FITNESS", "MOBILITY"),
    ),
    _record(
        "WARMUP_HIP_OPENER",
        phase_codes=("WARMUP",),
        role_eligibility_code="SUPPORT",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("MOBILITY",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("GENERAL_FITNESS", "MOBILITY"),
    ),
    _record(
        "WARMUP_MARCH_IN_PLACE",
        phase_codes=("WARMUP",),
        role_eligibility_code="SUPPORT",
        body_focus_code="FULL_BODY",
        movement_pattern_codes=("GAIT",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=20,
        goal_codes=("GENERAL_FITNESS", "MOBILITY"),
    ),
    _record(
        "WARMUP_SHOULDER_ROLL",
        phase_codes=("WARMUP",),
        role_eligibility_code="SUPPORT",
        body_focus_code="UPPER_BODY",
        movement_pattern_codes=("MOBILITY",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("GENERAL_FITNESS", "MOBILITY"),
    ),
    # --- MAIN (CORE tier) -------------------------------------------------
    _record(
        "SQUAT_BODYWEIGHT",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("SQUAT",),
        family_code="SQUAT_FAMILY",
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    _record(
        "LUNGE_FORWARD",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("LUNGE",),
        family_code="LUNGE_FAMILY",
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    _record(
        "WALL_SIT",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("ISOMETRIC",),
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    _record(
        "PUSHUP_KNEE",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="UPPER_BODY",
        movement_pattern_codes=("PUSH",),
        family_code="PUSH_FAMILY",
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    _record(
        "GLUTE_BRIDGE",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("HINGE",),
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    _record(
        "PLANK_FOREARM",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="TRUNK",
        movement_pattern_codes=("BRACE",),
        goal_codes=("CORE_STABILITY", "GENERAL_FITNESS"),
    ),
    _record(
        "DEAD_BUG",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="TRUNK",
        movement_pattern_codes=("BRACE",),
        goal_codes=("CORE_STABILITY", "GENERAL_FITNESS"),
    ),
    # Equipment-gated MAIN work. Present so a case can ask for a plan the
    # catalog can only satisfy with equipment the user does not have.
    _record(
        "ROW_DUMBBELL",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="UPPER_BODY",
        movement_pattern_codes=("PULL",),
        equipment_codes=("DUMBBELL",),
        family_code="PULL_FAMILY",
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    _record(
        "OVERHEAD_PRESS_DUMBBELL",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="UPPER_BODY",
        movement_pattern_codes=("PUSH",),
        equipment_codes=("DUMBBELL",),
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    # Gym-only location. Lets a case exercise the location gate.
    _record(
        "LEG_PRESS_MACHINE",
        phase_codes=("MAIN",),
        role_eligibility_code="CORE",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("SQUAT",),
        equipment_codes=("MACHINE",),
        location_codes=("GYM",),
        goal_codes=("GENERAL_FITNESS", "STRENGTH"),
    ),
    # --- COOLDOWN (SUPPORT tier) -----------------------------------------
    _record(
        "COOLDOWN_HAMSTRING_STRETCH",
        phase_codes=("COOLDOWN",),
        role_eligibility_code="SUPPORT",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("STRETCH",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("FLEXIBILITY", "GENERAL_FITNESS"),
    ),
    _record(
        "COOLDOWN_CHEST_STRETCH",
        phase_codes=("COOLDOWN",),
        role_eligibility_code="SUPPORT",
        body_focus_code="UPPER_BODY",
        movement_pattern_codes=("STRETCH",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("FLEXIBILITY", "GENERAL_FITNESS"),
    ),
    _record(
        "COOLDOWN_CHILD_POSE",
        phase_codes=("COOLDOWN",),
        role_eligibility_code="SUPPORT",
        body_focus_code="TRUNK",
        movement_pattern_codes=("STRETCH",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("FLEXIBILITY", "GENERAL_FITNESS"),
    ),
    _record(
        "COOLDOWN_CALF_STRETCH",
        phase_codes=("COOLDOWN",),
        role_eligibility_code="SUPPORT",
        body_focus_code="LOWER_BODY",
        movement_pattern_codes=("STRETCH",),
        seconds_per_rep=3,
        rest_seconds=30,
        transition_seconds=15,
        min_sets=1,
        max_sets=2,
        min_reps=8,
        max_reps=15,
        goal_codes=("FLEXIBILITY", "GENERAL_FITNESS"),
    ),
)

CATALOG: Final[dict[str, ExercisePoolExerciseRecord]] = {
    record.stable_code: record for record in _RECORDS
}

BY_ID: Final[dict[UUID, ExercisePoolExerciseRecord]] = {
    record.exercise_id: record for record in _RECORDS
}


def records_for(stable_codes: tuple[str, ...]) -> tuple[ExercisePoolExerciseRecord, ...]:
    """Return the named records in canonical UUID order, as the pool contract requires."""

    unknown = tuple(code for code in stable_codes if code not in CATALOG)
    if unknown:
        raise KeyError(f"unknown evaluation exercise codes: {unknown}")
    selected = [CATALOG[code] for code in dict.fromkeys(stable_codes)]
    return tuple(sorted(selected, key=lambda record: str(record.exercise_id)))


def ids_for(stable_codes: tuple[str, ...]) -> tuple[UUID, ...]:
    """Return the named exercise IDs in canonical UUID order."""

    return tuple(record.exercise_id for record in records_for(stable_codes))


def codes_in_phase(phase_code: str) -> tuple[str, ...]:
    """Return every stable code the catalog allows in one session phase."""

    return tuple(
        sorted(record.stable_code for record in _RECORDS if phase_code in record.phase_codes)
    )


__all__ = [
    "BY_ID",
    "CATALOG",
    "CATALOG_VERSION",
    "KNEE_LOADING_CODES",
    "SHOULDER_LOADING_CODES",
    "codes_in_phase",
    "exercise_id_for",
    "ids_for",
    "records_for",
]
