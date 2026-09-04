"""The two ladder axes that reach the plan through the pool and the clock.

`DOMAIN_RULES.md` 6.1 orders the downshift ladder exercise difficulty, then intensity,
then time allocation. Intensity already lands on the recovery ceiling. These are the other
two, and both are applied from the hashed `ConstraintEnvelope` rather than from the
feedback row, so a replay of a stored decision reaches the same plan.

The time axis is the one worth stating plainly: it never shortens the requested duration.
It goes exactly as far as settling on the shorter side of the +/-300s window that
`DOMAIN_RULES.md` 5 already approved, and the plan still fails outside that window.
"""

from __future__ import annotations

from uuid import UUID

from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    FeedbackAdjustmentEnvelope,
    RecoveryCeiling,
)
from backend.app.domain.agents.v3_duration import (
    PlanDurationPreferenceCode,
    accepts_additional_seconds,
    plan_duration_preference,
    plan_duration_seconds,
)
from backend.app.domain.agents.v3_orchestration import FallbackRequest
from backend.app.domain.rules.duration import DURATION_TOLERANCE_SECONDS
from backend.app.integrations.langgraph.fallback import DeterministicGraphFallbackProvider
from backend.app.modules.decisions.v3_application import (
    DeterministicV3SafetyPolicyAdapter,
    PostgreSQLV3ExercisePoolSource,
)
from backend.tests.unit.test_v3_application_adapters import _exercise, _source
from backend.tests.unit.test_v3_duration import _pool as duration_pool
from backend.tests.unit.test_v3_duration import reps_record

FALLBACK_VERSION = "v3-deterministic-fallback-v1"
TARGET_MINUTES = 30
TARGET_SECONDS = TARGET_MINUTES * 60


def _adjusted_envelope(axis_code: str | None) -> ConstraintEnvelope:
    """The duration envelope from `test_v3_duration`, optionally carrying an axis."""

    adjustment = (
        None
        if axis_code is None
        else FeedbackAdjustmentEnvelope(
            axis_code=axis_code,
            reason_codes=("BOTH_REPORTED_DIFFICULTY_FIRST",),
            policy_version="feedback-adjustment-policy-v1",
        )
    )
    return ConstraintEnvelope.create(
        requested_duration_minutes=TARGET_MINUTES,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=("BODYWEIGHT",),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=RecoveryCeiling(
            policy_version="recovery-policy-v1",
            allowed_intensity_codes=("LOW", "MODERATE"),
            allowed_load_codes=("BODYWEIGHT",),
            maximum_sets_per_exercise=3,
            maximum_repetitions_per_set=12,
            maximum_work_seconds_per_set=60,
            minimum_rest_seconds_between_sets=30,
        ),
        plan_generation_allowed=True,
        policy_version="decision-policy-v3",
        catalog_version="catalog-v3",
        safety_rule_version="safety-rules-v3",
        feedback_adjustment=adjustment,
    )


def _fallback_seconds(axis_code: str | None) -> int:
    envelope = _adjusted_envelope(axis_code)
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))
    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=duration_pool(envelope, records),
            fallback_version=FALLBACK_VERSION,
        )
    )
    assert spec is not None
    # The spec asserts its own total; measure it back from the catalog basis so the
    # test cannot pass on a number the fallback merely declared.
    measured = plan_duration_seconds(
        spec.exercise_prescriptions, {item.exercise_id: item for item in records}
    )
    assert spec.estimated_duration_seconds == measured
    return measured


# --- the time axis ------------------------------------------------------------------


def test_an_envelope_without_an_adjustment_targets_the_request() -> None:
    assert (
        plan_duration_preference(_adjusted_envelope(None))
        is PlanDurationPreferenceCode.CLOSEST_TO_REQUEST
    )


def test_only_the_time_axis_moves_the_duration_preference() -> None:
    """Difficulty and intensity are answered elsewhere; neither touches the clock."""

    for axis_code in ("EXERCISE_DIFFICULTY", "INTENSITY"):
        assert (
            plan_duration_preference(_adjusted_envelope(axis_code))
            is PlanDurationPreferenceCode.CLOSEST_TO_REQUEST
        )

    assert (
        plan_duration_preference(_adjusted_envelope("TIME_ALLOCATION"))
        is PlanDurationPreferenceCode.SHORTER_WITHIN_WINDOW
    )


def test_the_shorter_preference_stops_at_the_window_floor() -> None:
    """It settles on the short side of the window and never drops through it."""

    floor = TARGET_SECONDS - DURATION_TOLERANCE_SECONDS

    assert accepts_additional_seconds(
        accumulated_seconds=floor - 1,
        additional_seconds=200,
        target_seconds=TARGET_SECONDS,
        preference=PlanDurationPreferenceCode.SHORTER_WITHIN_WINDOW,
    )
    assert not accepts_additional_seconds(
        accumulated_seconds=floor,
        additional_seconds=200,
        target_seconds=TARGET_SECONDS,
        preference=PlanDurationPreferenceCode.SHORTER_WITHIN_WINDOW,
    )


def test_the_default_preference_accepts_only_what_moves_closer_to_the_request() -> None:
    assert accepts_additional_seconds(
        accumulated_seconds=TARGET_SECONDS - 400,
        additional_seconds=200,
        target_seconds=TARGET_SECONDS,
        preference=PlanDurationPreferenceCode.CLOSEST_TO_REQUEST,
    )
    # 200 more would overshoot by 100 having been 60 short: further away, so refused.
    assert not accepts_additional_seconds(
        accumulated_seconds=TARGET_SECONDS - 60,
        additional_seconds=200,
        target_seconds=TARGET_SECONDS,
        preference=PlanDurationPreferenceCode.CLOSEST_TO_REQUEST,
    )


def test_the_time_axis_builds_a_shorter_plan_than_the_default() -> None:
    default_seconds = _fallback_seconds(None)
    adjusted_seconds = _fallback_seconds("TIME_ALLOCATION")

    assert adjusted_seconds < default_seconds
    assert adjusted_seconds < TARGET_SECONDS


def test_the_time_axis_never_leaves_the_approved_window() -> None:
    """The point of the rung: a shorter session, not a shortened request."""

    for axis_code in (None, "TIME_ALLOCATION"):
        seconds = _fallback_seconds(axis_code)
        assert abs(seconds - TARGET_SECONDS) <= DURATION_TOLERANCE_SECONDS


def test_the_time_axis_does_not_rewrite_the_requested_duration() -> None:
    envelope = _adjusted_envelope("TIME_ALLOCATION")
    records = tuple(reps_record(UUID(int=index)) for index in range(1, 11))

    spec = DeterministicGraphFallbackProvider().generate(
        FallbackRequest.create(
            constraint_envelope=envelope,
            exercise_pool=duration_pool(envelope, records),
            fallback_version=FALLBACK_VERSION,
        )
    )

    assert spec is not None
    assert spec.requested_duration_minutes == TARGET_MINUTES


# --- the exercise-difficulty axis ---------------------------------------------------


def _difficulty_source(*, reason_codes: tuple[str, ...], difficulty_code: str | None):
    return _source(
        experience_level_code="INTERMEDIATE",
        exercises=(
            _exercise(UUID(int=101), "BEGINNER"),
            _exercise(UUID(int=102), "INTERMEDIATE"),
        ),
        latest_difficulty_code=difficulty_code,
        latest_difficulty_reason_codes=reason_codes,
    )


def _pool_ids(source) -> set[UUID]:
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)
    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(source=source, envelope=envelope)
    return {item.exercise_id for item in eligible.exercises}


def test_movement_difficulty_feedback_narrows_the_pool_to_easier_exercises() -> None:
    """Rung 1: replace the movement with a lower-difficulty one.

    Removing the harder records is what makes this stick. The specialist agents, the
    deterministic fallback and the integrity validator all read the same pool, so no
    coordinator output can put the intermediate movement back in.
    """

    source = _difficulty_source(reason_codes=("MOVEMENT_DIFFICULT",), difficulty_code="HARD")

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)
    assert envelope.feedback_adjustment is not None
    assert envelope.feedback_adjustment.axis_code == "EXERCISE_DIFFICULTY"
    assert _pool_ids(source) == {UUID(int=101)}


def test_a_volume_complaint_leaves_the_pool_alone() -> None:
    """It picks the intensity axis, which is a ceiling change, not a catalog change."""

    source = _difficulty_source(reason_codes=("VOLUME_HIGH",), difficulty_code="HARD")

    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)
    assert envelope.feedback_adjustment is not None
    assert envelope.feedback_adjustment.axis_code == "INTENSITY"
    assert _pool_ids(source) == {UUID(int=101), UUID(int=102)}


def test_no_feedback_leaves_the_pool_alone() -> None:
    source = _difficulty_source(reason_codes=(), difficulty_code=None)

    assert DeterministicV3SafetyPolicyAdapter().evaluate(source).feedback_adjustment is None
    assert _pool_ids(source) == {UUID(int=101), UUID(int=102)}


def test_the_difficulty_axis_never_re_admits_a_safety_exclusion() -> None:
    """Narrowing runs after the exclusions, so it can only ever remove exercises."""

    source = _difficulty_source(
        reason_codes=("MOVEMENT_DIFFICULT", "VOLUME_HIGH"), difficulty_code="HARD"
    )
    envelope = DeterministicV3SafetyPolicyAdapter().evaluate(source)
    excluded = envelope.model_dump(exclude={"envelope_hash"})
    excluded["excluded_exercise_ids"] = (UUID(int=101),)
    narrowed = ConstraintEnvelope.create(**excluded)

    eligible = PostgreSQLV3ExercisePoolSource().load_eligible(source=source, envelope=narrowed)

    assert UUID(int=101) not in {item.exercise_id for item in eligible.exercises}
