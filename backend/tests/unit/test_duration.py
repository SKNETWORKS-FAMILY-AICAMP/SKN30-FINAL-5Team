import pytest

from backend.app.domain.rules.duration import (
    DURATION_RULE_VERSION,
    DurationPlan,
    DurationTargetMismatchError,
    InvalidDurationInputError,
    PlanItemDuration,
    RequestedDurationNotPreservedError,
    assess_duration,
    calculate_estimated_duration_seconds,
    require_exact_duration,
    validate_requested_duration,
)


def _forty_minute_plan() -> DurationPlan:
    return DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=(
            PlanItemDuration(work_seconds=600, rest_seconds=180, transition_seconds=15),
            PlanItemDuration(work_seconds=600, rest_seconds=180, transition_seconds=15),
            PlanItemDuration(work_seconds=400, rest_seconds=155, transition_seconds=15),
        ),
        cooldown_seconds=90,
    )


def test_complete_plan_components_sum_to_exact_forty_minute_target() -> None:
    request = validate_requested_duration(
        profile_duration_minutes=40,
        requested_duration_minutes=40,
        adjustment_source_code="PROFILE",
    )
    plan = _forty_minute_plan()

    assessment = require_exact_duration(request, plan)

    assert calculate_estimated_duration_seconds(plan) == 2_400
    assert assessment.requested_duration_minutes == 40
    assert assessment.target_duration_seconds == 2_400
    assert assessment.estimated_duration_seconds == 2_400
    assert assessment.delta_seconds == 0
    assert assessment.is_exact_match is True
    assert assessment.duration_rule_version == DURATION_RULE_VERSION


def test_explicit_user_override_becomes_new_exact_target() -> None:
    request = validate_requested_duration(
        profile_duration_minutes=40,
        requested_duration_minutes=30,
        adjustment_source_code="USER_OVERRIDE",
    )
    plan = DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=(
            PlanItemDuration(work_seconds=600, rest_seconds=165, transition_seconds=15),
            PlanItemDuration(work_seconds=600, rest_seconds=165, transition_seconds=15),
        ),
        cooldown_seconds=90,
    )

    assessment = require_exact_duration(request, plan)

    assert assessment.target_duration_seconds == 1_800
    assert assessment.estimated_duration_seconds == 1_800


def test_profile_source_cannot_change_default_requested_duration() -> None:
    with pytest.raises(RequestedDurationNotPreservedError):
        validate_requested_duration(
            profile_duration_minutes=40,
            requested_duration_minutes=15,
            adjustment_source_code="PROFILE",
        )


@pytest.mark.parametrize("requested_duration_minutes", [0, -1, True, 30.5])
def test_requested_duration_must_be_a_positive_integer(
    requested_duration_minutes: object,
) -> None:
    with pytest.raises(InvalidDurationInputError):
        validate_requested_duration(
            profile_duration_minutes=40,
            requested_duration_minutes=requested_duration_minutes,  # type: ignore[arg-type]
            adjustment_source_code="USER_OVERRIDE",
        )


def test_unknown_adjustment_source_is_rejected() -> None:
    with pytest.raises(InvalidDurationInputError):
        validate_requested_duration(
            profile_duration_minutes=40,
            requested_duration_minutes=40,
            adjustment_source_code="SYSTEM",
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("setup_seconds", -1),
        ("setup_seconds", 61),
        ("warmup_seconds", 59),
        ("warmup_seconds", 181),
        ("cooldown_seconds", 44),
        ("cooldown_seconds", 121),
    ],
)
def test_plan_level_component_ranges_are_enforced(
    field_name: str,
    invalid_value: int,
) -> None:
    values = {
        "setup_seconds": 30,
        "warmup_seconds": 120,
        "items": (PlanItemDuration(60, 30, 15),),
        "cooldown_seconds": 90,
    }
    values[field_name] = invalid_value

    with pytest.raises(InvalidDurationInputError):
        DurationPlan(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("setup_seconds", "warmup_seconds", "cooldown_seconds"),
    [
        (0, 60, 45),
        (60, 180, 120),
    ],
)
def test_plan_level_component_boundaries_are_accepted(
    setup_seconds: int,
    warmup_seconds: int,
    cooldown_seconds: int,
) -> None:
    plan = DurationPlan(
        setup_seconds=setup_seconds,
        warmup_seconds=warmup_seconds,
        items=(PlanItemDuration(0, 0, 10),),
        cooldown_seconds=cooldown_seconds,
    )

    assert plan.setup_seconds == setup_seconds
    assert plan.warmup_seconds == warmup_seconds
    assert plan.cooldown_seconds == cooldown_seconds


@pytest.mark.parametrize(
    ("work_seconds", "rest_seconds", "transition_seconds"),
    [
        (-1, 0, 10),
        (0, -1, 10),
        (0, 0, 9),
        (0, 0, 21),
    ],
)
def test_item_component_ranges_are_enforced(
    work_seconds: int,
    rest_seconds: int,
    transition_seconds: int,
) -> None:
    with pytest.raises(InvalidDurationInputError):
        PlanItemDuration(
            work_seconds=work_seconds,
            rest_seconds=rest_seconds,
            transition_seconds=transition_seconds,
        )


@pytest.mark.parametrize("transition_seconds", [10, 20])
def test_item_transition_boundaries_are_accepted(transition_seconds: int) -> None:
    item = PlanItemDuration(
        work_seconds=0,
        rest_seconds=0,
        transition_seconds=transition_seconds,
    )

    assert item.estimated_item_seconds == transition_seconds


@pytest.mark.parametrize("changed_work_seconds", [399, 401])
def test_plan_one_second_short_or_long_cannot_pass(
    changed_work_seconds: int,
) -> None:
    request = validate_requested_duration(
        profile_duration_minutes=40,
        requested_duration_minutes=40,
        adjustment_source_code="PROFILE",
    )
    plan = _forty_minute_plan()
    changed_plan = DurationPlan(
        setup_seconds=plan.setup_seconds,
        warmup_seconds=plan.warmup_seconds,
        items=(
            *plan.items[:-1],
            PlanItemDuration(
                work_seconds=changed_work_seconds,
                rest_seconds=plan.items[-1].rest_seconds,
                transition_seconds=plan.items[-1].transition_seconds,
            ),
        ),
        cooldown_seconds=plan.cooldown_seconds,
    )

    assessment = assess_duration(request, changed_plan)

    assert assessment.is_exact_match is False
    assert assessment.delta_seconds in {-1, 1}
    with pytest.raises(DurationTargetMismatchError) as exc_info:
        require_exact_duration(request, changed_plan)
    assert exc_info.value.assessment == assessment


def test_same_input_produces_same_versioned_assessment() -> None:
    request = validate_requested_duration(
        profile_duration_minutes=40,
        requested_duration_minutes=40,
        adjustment_source_code="PROFILE",
    )
    plan = _forty_minute_plan()

    assert assess_duration(request, plan) == assess_duration(request, plan)
    assert assess_duration(request, plan).duration_rule_version == "1.0.0"
