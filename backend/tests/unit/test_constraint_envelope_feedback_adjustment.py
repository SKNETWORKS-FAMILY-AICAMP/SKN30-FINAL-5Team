"""The feedback adjustment travels inside the hashed constraint envelope.

`DOMAIN_RULES.md` 6.1 lets the last `HARD` feedback lower one axis. Carrying the result in
the envelope, rather than passing it beside one, means the coordinator cannot argue with
it and a replay reproduces the same constraint set.

The version rule is the interesting part: an envelope with no adjustment stays
`constraint-envelope-v3` and keeps the hash it always had, so every stored envelope
remains replayable.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.v3_contracts import (
    ConstraintEnvelope,
    FeedbackAdjustmentEnvelope,
    RecoveryCeiling,
)

CEILING = RecoveryCeiling(policy_version="recovery-policy-v1")


def _envelope(adjustment: FeedbackAdjustmentEnvelope | None = None) -> ConstraintEnvelope:
    return ConstraintEnvelope.create(
        requested_duration_minutes=30,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=(),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=CEILING,
        plan_generation_allowed=True,
        policy_version="decision-policy-v3",
        catalog_version="exercise-catalog-v2.0.5-final",
        safety_rule_version="safety-policy-v1",
        feedback_adjustment=adjustment,
    )


def _adjustment(axis: str = "INTENSITY") -> FeedbackAdjustmentEnvelope:
    return FeedbackAdjustmentEnvelope(
        axis_code=axis,
        reason_codes=("VOLUME_HIGH_REPORTED",),
        policy_version="feedback-adjustment-policy-v1",
    )


def test_envelope_without_an_adjustment_stays_on_the_old_schema_version() -> None:
    """Otherwise every stored envelope would need a new hash to record an absent field."""

    envelope = _envelope()

    assert envelope.schema_version == "constraint-envelope-v3"
    assert envelope.feedback_adjustment is None


def test_an_adjusted_envelope_declares_the_new_schema_version() -> None:
    envelope = _envelope(_adjustment())

    assert envelope.schema_version == "constraint-envelope-v4"
    assert envelope.feedback_adjustment is not None
    assert envelope.feedback_adjustment.axis_code == "INTENSITY"


def test_the_adjustment_changes_the_envelope_hash() -> None:
    """The adjustment is part of the constraint set, so it must be covered by the hash."""

    assert _envelope().envelope_hash != _envelope(_adjustment()).envelope_hash


def test_different_axes_hash_differently() -> None:
    assert (
        _envelope(_adjustment("INTENSITY")).envelope_hash
        != _envelope(_adjustment("EXERCISE_DIFFICULTY")).envelope_hash
    )


def test_omitting_the_field_hashes_like_passing_none() -> None:
    """An envelope written before the field existed must keep the hash it had.

    `create` drops the key when there is no adjustment, so a v3 envelope's canonical
    payload is byte-identical to what it was before this field was added.
    """

    without_key = ConstraintEnvelope.create(
        requested_duration_minutes=30,
        primary_goal_code="GENERAL_FITNESS",
        allowed_location_codes=("HOME",),
        allowed_equipment_codes=(),
        excluded_exercise_ids=(),
        mandatory_exercise_ids=(),
        recovery_ceiling=CEILING,
        plan_generation_allowed=True,
        policy_version="decision-policy-v3",
        catalog_version="exercise-catalog-v2.0.5-final",
        safety_rule_version="safety-policy-v1",
    )

    assert without_key.envelope_hash == _envelope().envelope_hash
    assert without_key.schema_version == "constraint-envelope-v3"


def test_the_envelope_stays_frozen() -> None:
    envelope = _envelope(_adjustment())

    with pytest.raises(ValidationError):
        envelope.feedback_adjustment = None  # type: ignore[misc]


def test_an_adjustment_must_carry_at_least_one_reason() -> None:
    """A bare axis would not be reproducible: nothing would say why it was chosen."""

    with pytest.raises(ValidationError):
        FeedbackAdjustmentEnvelope(
            axis_code="INTENSITY",
            reason_codes=(),
            policy_version="feedback-adjustment-policy-v1",
        )


def test_excluded_and_mandatory_rules_still_apply_with_an_adjustment() -> None:
    """The adjustment must not become a way around the safety constraints."""

    shared = uuid4()
    with pytest.raises(ValidationError):
        ConstraintEnvelope.create(
            requested_duration_minutes=30,
            primary_goal_code="GENERAL_FITNESS",
            allowed_location_codes=("HOME",),
            allowed_equipment_codes=(),
            excluded_exercise_ids=(shared,),
            mandatory_exercise_ids=(shared,),
            recovery_ceiling=CEILING,
            plan_generation_allowed=True,
            policy_version="decision-policy-v3",
            catalog_version="exercise-catalog-v2.0.5-final",
            safety_rule_version="safety-policy-v1",
            feedback_adjustment=_adjustment(),
        )
