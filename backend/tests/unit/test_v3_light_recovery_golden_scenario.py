"""A LIGHT 30-minute session must be buildable from the catalog actually shipped.

The existing fallback duration tests pass because they use synthetic records that
are long enough to fill any request. That is what allowed a release in which the
screen's own default check-in -- moderate fatigue, six hours of sleep, no pain,
thirty minutes -- reached ``DECISION_FAILED``: the LIGHT ceiling caps a real
catalog exercise at two sets of ten, and ten such exercises fall short of thirty
minutes, so the deterministic fallback correctly refused to hand back a shorter
session than the user asked for.

So this scenario is pinned against the promoted bundle rather than a fixture. It
reads the same rows the importer loads into the database, applies the same
eligibility rule the pool loader applies, and derives the recovery ceiling with
the production helper, so a catalog change that makes the default check-in
unplannable fails here instead of in the app.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from backend.app.domain.agents.retrieval import (
    ExerciseFittContext,
    ExerciseFittVolumeRange,
    ExercisePoolExerciseRecord,
    ExercisePoolSnapshot,
    RetrievalMetadata,
    RetrievalStatusCode,
)
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RecoveryCeiling
from backend.app.domain.agents.v3_validation import IntegrityValidationContext
from backend.app.domain.rules.fitt import context_for_exercise
from backend.app.domain.rules.recovery import (
    RECOVERY_POLICY_VERSION,
    RecoveryLevelCode,
    recovery_level,
)
from backend.app.domain.rules.training_level import is_exercise_allowed_for_user
from backend.app.integrations.langgraph.fallback import (
    DETERMINISTIC_FALLBACK_VERSION,
    DeterministicGraphFallbackProvider,
)
from backend.app.modules.decisions.v3_application import _fitt_volume_ceilings
from backend.tests.unit.test_v3_deterministic_graph_fallback import (
    execute_deterministic_fallback,
)

BUNDLE = Path("data/generated/integrated-catalog-v2.0.7-final/backend_bundle/catalog")
CATALOG_VERSION = "exercise-catalog-v2.0.7-final"
# Stable ids for the test pool; the database assigns the real ones on import.
NAMESPACE = UUID("00000000-0000-0000-0000-00000000ca7a")

# The screen's own defaults, and the pair that grades to LIGHT.
EXPERIENCE_LEVEL = "BEGINNER"
FATIGUE_LEVEL = "MODERATE"
SLEEP_MINUTES = 360
REQUESTED_MINUTES = 30
LOCATION = "HOME"
GOAL = "GENERAL_FITNESS"


def _read(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _pool_records() -> tuple[ExercisePoolExerciseRecord, ...]:
    """Rebuild the eligible pool the way `load_source` does, from the shipped rows."""

    prescriptions = _read(BUNDLE / "prescriptions/prescription_profiles.jsonl")
    levels: dict[str, set[str]] = {}
    goals: dict[str, set[str]] = {}
    phases: dict[str, set[str]] = {}
    for row in prescriptions:
        code = row["exercise_stable_code"]
        levels.setdefault(code, set()).add(row["experience_level_code"])
        if row["experience_level_code"] == EXPERIENCE_LEVEL:
            goals.setdefault(code, set()).add(row["goal_code"])
            phases.setdefault(code, set()).add(row["phase_code"])

    records: list[ExercisePoolExerciseRecord] = []
    for row in _read(BUNDLE / "catalog/exercises.jsonl"):
        code = row["stable_code"]
        if not is_exercise_allowed_for_user(
            exercise_difficulty_code=row["difficulty_code"],
            user_experience_level_code=EXPERIENCE_LEVEL,
        ):
            continue
        if EXPERIENCE_LEVEL not in levels.get(code, set()):
            continue
        if LOCATION not in row["location_codes"]:
            continue
        fitt = context_for_exercise(
            stable_code=code,
            experience_level_code=EXPERIENCE_LEVEL,
            timing_mode_code=row["timing_mode_code"],
        )
        volume = fitt.volume
        records.append(
            ExercisePoolExerciseRecord(
                exercise_id=uuid5(NAMESPACE, code),
                catalog_version=CATALOG_VERSION,
                content_version=row["instruction_content_version"],
                stable_code=code,
                training_type_code=row["training_type_code"],
                body_focus_code=row["body_focus_code"],
                movement_pattern_codes=(row["primary_movement_pattern_code"],),
                difficulty_code=row["difficulty_code"],
                timing_mode_code=row["timing_mode_code"],
                default_seconds_per_rep=row["default_seconds_per_rep"],
                default_work_seconds=row["default_work_seconds"],
                default_rest_seconds=row["default_rest_seconds"],
                default_transition_seconds=row["default_transition_seconds"],
                fitt_context=ExerciseFittContext(
                    source_code=fitt.source_code,
                    policy_version=fitt.policy_version,
                    review_status_code=fitt.review_status_code,
                    template_id=fitt.template_id,
                    frequency_code=fitt.frequency_code,
                    intensity_code=fitt.intensity_code,
                    time_mode_code=fitt.time_mode_code,
                    type_code=fitt.type_code,
                    volume=None
                    if volume is None
                    else ExerciseFittVolumeRange(
                        min_sets=volume.min_sets,
                        max_sets=volume.max_sets,
                        min_reps=volume.min_reps,
                        max_reps=volume.max_reps,
                        default_sets=volume.default_sets,
                        default_reps=volume.default_reps,
                    ),
                ),
                recovery_eligible=row["recovery_eligible"],
                goal_codes=tuple(sorted(goals.get(code, set()))),
                phase_codes=tuple(sorted(phases.get(code, set()))),
                equipment_codes=tuple(sorted(row["equipment_codes"])),
                location_codes=tuple(sorted(row["location_codes"])),
                prescription_reference_codes=(f"prescription/{code}",),
                source_reference_codes=(f"catalog/{CATALOG_VERSION}",),
                review_reference_codes=("DOMAIN_APPROVED",),
            )
        )
    return tuple(sorted(records, key=lambda item: str(item.exercise_id)))


def _light_envelope(records: tuple[ExercisePoolExerciseRecord, ...]) -> ConstraintEnvelope:
    """Derive the ceiling with the production helper rather than restating it."""

    recovery = recovery_level(sleep_minutes=SLEEP_MINUTES, fatigue_level_code=FATIGUE_LEVEL)
    assert recovery is RecoveryLevelCode.LIGHT, "the scenario depends on this grading"

    volume_ceilings = _fitt_volume_ceilings(records, recovery=recovery)
    return ConstraintEnvelope.create(
        requested_duration_minutes=REQUESTED_MINUTES,
        primary_goal_code=GOAL,
        allowed_location_codes=(LOCATION,),
        # Production sends no equipment: the 2026-08-27 approval dropped it from
        # onboarding, so a real user has no UserEquipment rows.
        allowed_equipment_codes=(),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=RecoveryCeiling(
            policy_version=RECOVERY_POLICY_VERSION,
            # LIGHT is an immutable global cap, not a catalog data mutation.
            allowed_intensity_codes=("LOW",),
            maximum_sets_per_exercise=2,
            maximum_repetitions_per_set=10,
            minimum_rest_seconds_between_sets=30,
            per_exercise_volume_ceilings=volume_ceilings,
        ),
        plan_generation_allowed=True,
        policy_version="decision-policy-v3",
        catalog_version=CATALOG_VERSION,
        safety_rule_version="safety-rules-v3",
    )


def _snapshot(
    envelope: ConstraintEnvelope, records: tuple[ExercisePoolExerciseRecord, ...]
) -> ExercisePoolSnapshot:
    return ExercisePoolSnapshot.create(
        catalog_version=CATALOG_VERSION,
        constraint_envelope_hash=envelope.envelope_hash,
        exercises=records,
        mandatory_exercise_ids=(),
        vector_ranked_exercise_ids=tuple(item.exercise_id for item in records),
        retrieval_metadata=RetrievalMetadata(
            collection_name="exercise-catalog-v3",
            vector_index_version="vector-index-v3",
            embedding_model_version="embedding-v3",
            query_hash="c" * 64,
            retrieval_status_code=RetrievalStatusCode.VECTOR_RETRIEVAL_SUCCEEDED,
            deterministic_pool_fallback_used=False,
        ),
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )


def test_the_promoted_catalog_still_yields_a_light_thirty_minute_plan() -> None:
    records = _pool_records()
    assert records, "the promoted bundle must produce a beginner home pool"

    envelope = _light_envelope(records)
    outcome = execute_deterministic_fallback(
        DeterministicGraphFallbackProvider(),
        envelope=envelope,
        pool=_snapshot(envelope, records),
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )

    assert outcome.terminal_result is None, "the default check-in must not fail closed"
    plan = outcome.compiled_plan
    assert plan is not None
    assert abs(plan.estimated_duration_seconds - REQUESTED_MINUTES * 60) <= 5 * 60


def test_the_light_plan_reaches_the_duration_without_relaxing_any_ceiling() -> None:
    """The duration is bought with rest, which is bounded below, never above."""

    records = _pool_records()
    envelope = _light_envelope(records)
    ceiling = envelope.recovery_ceiling
    outcome = execute_deterministic_fallback(
        DeterministicGraphFallbackProvider(),
        envelope=envelope,
        pool=_snapshot(envelope, records),
        fallback_version=DETERMINISTIC_FALLBACK_VERSION,
        compiler_version="v3-plan-compiler-v1",
        validator_version="v3-integrity-validator-v1",
        validation_context=IntegrityValidationContext(),
    )

    plan = outcome.compiled_plan
    assert plan is not None
    minimum_rest = ceiling.minimum_rest_seconds_between_sets
    assert minimum_rest is not None, "the scenario is only meaningful with a rest floor"
    by_exercise: dict[UUID, int] = {}
    for item in plan.exercises:
        prescription = item.prescription
        assert prescription.intensity_code == "LOW"
        assert prescription.sets <= 2
        assert prescription.repetitions_per_set is None or prescription.repetitions_per_set <= 10
        assert prescription.rest_seconds_between_sets >= minimum_rest
        key = prescription.exercise_id
        by_exercise[key] = by_exercise.get(key, 0) + prescription.sets

    # Repeated blocks share one ceiling; the sum is what the validator compares.
    assert all(total <= 2 for total in by_exercise.values())
