from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from backend.app.domain.agents.contracts import (
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.coordinator import (
    COORDINATOR_VERSION,
    CoordinatorCandidate,
    CoordinatorInput,
    CoordinatorStatusCode,
    DownshiftAdjustmentCode,
    coordinate,
)
from backend.app.domain.rules.duration import (
    DURATION_RULE_VERSION,
    DurationAdjustmentSourceCode,
    DurationPlan,
    PlanItemDuration,
)
from backend.app.domain.rules.safety import SafetyStatusCode


def _duration_plan(*, final_work_seconds: int = 400) -> DurationPlan:
    return DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=(
            PlanItemDuration(work_seconds=600, rest_seconds=180, transition_seconds=15),
            PlanItemDuration(work_seconds=600, rest_seconds=180, transition_seconds=15),
            PlanItemDuration(
                work_seconds=final_work_seconds,
                rest_seconds=155,
                transition_seconds=15,
            ),
        ),
        cooldown_seconds=90,
    )


def _candidate(
    candidate_id: str = "candidate-base",
    *,
    action_code: RecommendedActionCode = RecommendedActionCode.KEEP,
    exercise_ids: tuple[str, ...] = ("push_up", "row"),
    goal_tags: tuple[str, ...] = ("UPPER_BODY",),
    final_work_seconds: int = 400,
    catalog_version: str = "catalog-v1",
    downshift_adjustment_codes: tuple[DownshiftAdjustmentCode, ...] | None = None,
) -> CoordinatorCandidate:
    if downshift_adjustment_codes is None:
        downshift_adjustment_codes = (
            (DownshiftAdjustmentCode.INTENSITY_REDUCED,)
            if action_code is RecommendedActionCode.DOWNSHIFT
            else ()
        )
    return CoordinatorCandidate(
        candidate_id=candidate_id,
        action_code=action_code,
        exercise_ids=exercise_ids,
        goal_tags=goal_tags,
        downshift_adjustment_codes=downshift_adjustment_codes,
        catalog_version=catalog_version,
        duration_plan=_duration_plan(final_work_seconds=final_work_seconds),
    )


def _proposal(
    agent_type: AgentTypeCode,
    *,
    proposal_status: ProposalStatusCode = ProposalStatusCode.READY,
    action_code: RecommendedActionCode = RecommendedActionCode.KEEP,
    preferred_exercise_ids: tuple[str, ...] = (),
    excluded_exercise_ids: tuple[str, ...] = (),
    required_goal_tags: tuple[str, ...] = ("UPPER_BODY",),
    reason_codes: tuple[str, ...] = ("BASE_CANDIDATE_ACCEPTED",),
    safety_status: SafetyStatusCode = SafetyStatusCode.PASS,
    safety_vetoed: bool = False,
    requested_duration_minutes: int = 40,
    policy_version: str = "policy-v1",
) -> AgentProposal:
    is_ready = proposal_status is ProposalStatusCode.READY
    is_safety = agent_type is AgentTypeCode.SAFETY
    return AgentProposal(
        agent_type_code=agent_type,
        proposal_status_code=proposal_status,
        recommended_action_code=action_code if is_ready else None,
        requested_duration_minutes=requested_duration_minutes,
        estimated_duration_seconds=requested_duration_minutes * 60 if is_ready else None,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        required_goal_tags=required_goal_tags,
        preferred_exercise_ids=preferred_exercise_ids,
        excluded_exercise_ids=excluded_exercise_ids,
        hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
        reason_codes=reason_codes,
        evidence_reference_codes=("INPUT.requested_duration_minutes",),
        policy_version=policy_version,
        safety_status_code=safety_status if is_safety else None,
        safety_vetoed=safety_vetoed if is_safety else None,
    )


def _proposals(**replacements: AgentProposal) -> tuple[AgentProposal, ...]:
    by_name = {name.upper(): proposal for name, proposal in replacements.items()}
    return tuple(
        by_name.get(agent_type.value, _proposal(agent_type)) for agent_type in REQUIRED_AGENT_TYPES
    )


def _input(
    *,
    proposals: tuple[AgentProposal, ...] | None = None,
    candidates: tuple[CoordinatorCandidate, ...] | None = None,
    profile_duration_minutes: int = 40,
    requested_duration_minutes: int = 40,
    duration_adjustment_source_code: DurationAdjustmentSourceCode = (
        DurationAdjustmentSourceCode.PROFILE
    ),
    duration_rule_version: str = DURATION_RULE_VERSION,
) -> CoordinatorInput:
    return CoordinatorInput(
        proposals=proposals if proposals is not None else _proposals(),
        candidates=candidates if candidates is not None else (_candidate(),),
        profile_duration_minutes=profile_duration_minutes,
        requested_duration_minutes=requested_duration_minutes,
        duration_adjustment_source_code=duration_adjustment_source_code,
        policy_version="policy-v1",
        catalog_version="catalog-v1",
        catalog_status_code="ACTIVE",
        catalog_review_status_code="DOMAIN_APPROVED",
        catalog_production_eligible=True,
        catalog_activated=True,
        safety_rule_version="safety-v1",
        duration_rule_version=duration_rule_version,
    )


def test_normal_input_selects_one_base_candidate() -> None:
    result = coordinate(_input())

    assert result.coordinator_version == COORDINATOR_VERSION
    assert result.status_code is CoordinatorStatusCode.PASS
    assert result.safety_status_code is SafetyStatusCode.PASS
    assert result.final_action_code is RecommendedActionCode.KEEP
    assert result.selected_candidate_id == "candidate-base"
    assert result.estimated_duration_seconds == 2400
    assert result.applied_agent_types == REQUIRED_AGENT_TYPES


@pytest.mark.parametrize(
    "proposals",
    [
        _proposals()[:-1],
        (*_proposals()[:-1], _proposal(AgentTypeCode.TRAINING)),
    ],
)
def test_missing_or_duplicate_required_agent_fails_without_plan(
    proposals: tuple[AgentProposal, ...],
) -> None:
    result = coordinate(_input(proposals=proposals))

    assert result.status_code is CoordinatorStatusCode.FAILED
    assert result.final_action_code is None
    assert result.selected_candidate_id is None
    assert result.estimated_duration_seconds is None
    assert any(
        code.startswith(("REQUIRED_AGENT_MISSING", "REQUIRED_AGENT_DUPLICATE"))
        for code in result.reason_codes
    )


def test_failed_required_proposal_has_priority_over_plan_selection() -> None:
    failed_recovery = _proposal(
        AgentTypeCode.RECOVERY,
        proposal_status=ProposalStatusCode.FAILED,
        reason_codes=("AGENT_EXECUTION_FAILED",),
    )

    result = coordinate(_input(proposals=_proposals(recovery=failed_recovery)))

    assert result.status_code is CoordinatorStatusCode.FAILED
    assert result.reason_codes == ("REQUIRED_PROPOSAL_FAILED.RECOVERY",)
    assert result.selected_candidate_id is None


def test_safety_needs_input_withholds_plan() -> None:
    needs_input = _proposal(
        AgentTypeCode.SAFETY,
        proposal_status=ProposalStatusCode.NEEDS_INPUT,
        reason_codes=("SAFETY_INPUT_REQUIRED",),
        safety_status=SafetyStatusCode.NEEDS_INPUT,
        safety_vetoed=True,
    )

    result = coordinate(_input(proposals=_proposals(safety=needs_input)))

    assert result.status_code is CoordinatorStatusCode.NEEDS_INPUT
    assert result.safety_status_code is SafetyStatusCode.NEEDS_INPUT
    assert result.final_action_code is None
    assert result.selected_candidate_id is None


@pytest.mark.parametrize(
    ("action_code", "reason_code"),
    [
        (RecommendedActionCode.REST, "SEVERE_DISCOMFORT"),
        (RecommendedActionCode.STOP_AND_SEEK_HELP, "SERIOUS_ADVERSE_REACTION"),
    ],
)
def test_blocked_safety_action_cannot_be_overridden(
    action_code: RecommendedActionCode,
    reason_code: str,
) -> None:
    blocked = _proposal(
        AgentTypeCode.SAFETY,
        action_code=action_code,
        reason_codes=(reason_code,),
        safety_status=SafetyStatusCode.BLOCKED,
        safety_vetoed=True,
    )
    training = _proposal(
        AgentTypeCode.TRAINING,
        action_code=RecommendedActionCode.KEEP,
        preferred_exercise_ids=("push_up",),
    )

    result = coordinate(_input(proposals=_proposals(training=training, safety=blocked)))

    assert result.status_code is CoordinatorStatusCode.BLOCKED
    assert result.final_action_code is action_code
    assert result.selected_candidate_id is None
    assert result.estimated_duration_seconds is None
    assert "SAFETY_BLOCKED" in result.blocked_reason_codes


def test_safety_revise_exclusion_beats_other_agent_preference() -> None:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=RecommendedActionCode.CHANGE,
        excluded_exercise_ids=("squat",),
        reason_codes=("KNEE_LOAD_EXCLUDED",),
        safety_status=SafetyStatusCode.REVISE,
        safety_vetoed=True,
    )
    training = _proposal(
        AgentTypeCode.TRAINING,
        action_code=RecommendedActionCode.KEEP,
        preferred_exercise_ids=("squat",),
    )
    unsafe = _candidate(
        "candidate-unsafe",
        action_code=RecommendedActionCode.CHANGE,
        exercise_ids=("row", "squat"),
    )
    approved_replacement = _candidate(
        "candidate-approved-replacement",
        action_code=RecommendedActionCode.CHANGE,
        exercise_ids=("glute_bridge", "row"),
    )

    result = coordinate(
        _input(
            proposals=_proposals(training=training, safety=safety),
            candidates=(unsafe, approved_replacement),
        )
    )

    assert result.status_code is CoordinatorStatusCode.REVISE
    assert result.safety_status_code is SafetyStatusCode.REVISE
    assert result.final_action_code is RecommendedActionCode.CHANGE
    assert result.selected_candidate_id == "candidate-approved-replacement"
    assert result.estimated_duration_seconds == 2400


def test_proposal_cannot_reference_exercise_outside_common_candidates() -> None:
    training = _proposal(
        AgentTypeCode.TRAINING,
        preferred_exercise_ids=("outside_catalog_candidate",),
    )

    result = coordinate(_input(proposals=_proposals(training=training)))

    assert result.status_code is CoordinatorStatusCode.FAILED
    assert result.reason_codes == ("PROPOSAL_EXERCISE_OUTSIDE_COMMON_CANDIDATES",)
    assert result.selected_candidate_id is None


def test_candidate_without_explicit_required_goal_link_is_not_selected() -> None:
    candidate_without_goal_link = _candidate(goal_tags=())

    result = coordinate(_input(candidates=(candidate_without_goal_link,)))

    assert result.status_code is CoordinatorStatusCode.BLOCKED
    assert result.selected_candidate_id is None
    assert "CANDIDATE_MISSING_REQUIRED_GOAL" in result.blocked_reason_codes


def test_non_exact_duration_candidate_is_never_selected() -> None:
    one_second_short = _candidate("candidate-short", final_work_seconds=399)

    result = coordinate(_input(candidates=(one_second_short,)))

    assert result.status_code is CoordinatorStatusCode.BLOCKED
    assert result.final_action_code is RecommendedActionCode.REST
    assert result.selected_candidate_id is None
    assert "CANDIDATE_DURATION_MISMATCH" in result.blocked_reason_codes


def test_empty_common_candidate_set_blocks_without_inventing_a_plan() -> None:
    result = coordinate(_input(candidates=()))

    assert result.status_code is CoordinatorStatusCode.BLOCKED
    assert result.final_action_code is RecommendedActionCode.REST
    assert result.selected_candidate_id is None
    assert result.blocked_reason_codes == ("NO_ELIGIBLE_COMMON_CANDIDATE",)


def test_duplicate_candidate_id_or_catalog_version_mismatch_fails_closed() -> None:
    duplicate = _candidate()
    duplicate_result = coordinate(_input(candidates=(duplicate, duplicate)))
    wrong_version_result = coordinate(
        _input(candidates=(_candidate(catalog_version="catalog-v2"),))
    )

    assert duplicate_result.status_code is CoordinatorStatusCode.FAILED
    assert duplicate_result.reason_codes == ("COMMON_CANDIDATE_ID_DUPLICATE",)
    assert wrong_version_result.status_code is CoordinatorStatusCode.FAILED
    assert wrong_version_result.reason_codes == ("COMMON_CANDIDATE_VERSION_MISMATCH",)


@pytest.mark.parametrize(
    ("safety_status", "safety_vetoed"),
    [
        (SafetyStatusCode.PASS, False),
        (SafetyStatusCode.REVISE, False),
    ],
)
def test_safety_exclusion_requires_revise_veto(
    safety_status: SafetyStatusCode,
    safety_vetoed: bool,
) -> None:
    safety = _proposal(
        AgentTypeCode.SAFETY,
        action_code=(
            RecommendedActionCode.KEEP
            if safety_status is SafetyStatusCode.PASS
            else RecommendedActionCode.CHANGE
        ),
        excluded_exercise_ids=("push_up",),
        safety_status=safety_status,
        safety_vetoed=safety_vetoed,
    )

    result = coordinate(_input(proposals=_proposals(safety=safety)))

    assert result.status_code is CoordinatorStatusCode.FAILED
    assert result.reason_codes == ("SAFETY_PROPOSAL_INCONSISTENT",)


def test_profile_source_cannot_change_requested_duration() -> None:
    proposals = tuple(
        _proposal(agent_type, requested_duration_minutes=30) for agent_type in REQUIRED_AGENT_TYPES
    )

    result = coordinate(
        _input(
            proposals=proposals,
            profile_duration_minutes=40,
            requested_duration_minutes=30,
        )
    )

    assert result.status_code is CoordinatorStatusCode.FAILED
    assert result.reason_codes == ("DURATION_REQUEST_INVALID",)


def test_explicit_user_override_preserves_new_requested_duration() -> None:
    proposals = tuple(
        AgentProposal(
            **{
                **_proposal(agent_type, requested_duration_minutes=30).model_dump(),
                "duration_adjustment_source_code": DurationAdjustmentSourceCode.USER_OVERRIDE,
            }
        )
        for agent_type in REQUIRED_AGENT_TYPES
    )
    thirty_minute_plan = DurationPlan(
        setup_seconds=30,
        warmup_seconds=120,
        items=(
            PlanItemDuration(work_seconds=600, rest_seconds=165, transition_seconds=15),
            PlanItemDuration(work_seconds=600, rest_seconds=165, transition_seconds=15),
        ),
        cooldown_seconds=90,
    )
    candidate = CoordinatorCandidate(
        candidate_id="candidate-user-override",
        action_code=RecommendedActionCode.KEEP,
        exercise_ids=("push_up", "row"),
        goal_tags=("UPPER_BODY",),
        catalog_version="catalog-v1",
        duration_plan=thirty_minute_plan,
    )

    result = coordinate(
        _input(
            proposals=proposals,
            candidates=(candidate,),
            profile_duration_minutes=40,
            requested_duration_minutes=30,
            duration_adjustment_source_code=DurationAdjustmentSourceCode.USER_OVERRIDE,
        )
    )

    assert result.status_code is CoordinatorStatusCode.PASS
    assert result.requested_duration_minutes == 30
    assert result.duration_adjustment_source_code is DurationAdjustmentSourceCode.USER_OVERRIDE
    assert result.estimated_duration_seconds == 1800


def test_same_input_and_versions_are_reproducible_and_order_independent() -> None:
    feasibility = _proposal(
        AgentTypeCode.FEASIBILITY,
        preferred_exercise_ids=("row",),
    )
    candidates = (
        _candidate("candidate-z", exercise_ids=("push_up", "row")),
        _candidate("candidate-a", exercise_ids=("push_up", "row")),
    )
    original = _input(
        proposals=_proposals(feasibility=feasibility),
        candidates=candidates,
    )
    reordered = _input(
        proposals=tuple(reversed(original.proposals)),
        candidates=tuple(reversed(original.candidates)),
    )

    first = coordinate(original)
    second = coordinate(original)
    reordered_result = coordinate(reordered)

    assert first == second == reordered_result
    assert first.selected_candidate_id == "candidate-a"


def test_priority_is_feasibility_then_recovery_then_training() -> None:
    training = _proposal(
        AgentTypeCode.TRAINING,
        action_code=RecommendedActionCode.CHANGE,
    )
    recovery = _proposal(
        AgentTypeCode.RECOVERY,
        action_code=RecommendedActionCode.DOWNSHIFT,
    )
    feasibility = _proposal(
        AgentTypeCode.FEASIBILITY,
        action_code=RecommendedActionCode.RECOVERY,
    )
    candidates = (
        _candidate("candidate-change", action_code=RecommendedActionCode.CHANGE),
        _candidate("candidate-downshift", action_code=RecommendedActionCode.DOWNSHIFT),
        _candidate("candidate-recovery", action_code=RecommendedActionCode.RECOVERY),
    )

    result = coordinate(
        _input(
            proposals=_proposals(
                training=training,
                recovery=recovery,
                feasibility=feasibility,
            ),
            candidates=candidates,
        )
    )

    assert result.final_action_code is RecommendedActionCode.RECOVERY
    assert result.selected_candidate_id == "candidate-recovery"


def test_unknown_duration_rule_version_fails_closed() -> None:
    result = coordinate(_input(duration_rule_version="duration-v999"))

    assert result.status_code is CoordinatorStatusCode.FAILED
    assert result.reason_codes == ("DURATION_RULE_VERSION_UNSUPPORTED",)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("catalog_status_code", "DRAFT"),
        ("catalog_review_status_code", "TECH_REVIEWED"),
        ("catalog_production_eligible", False),
        ("catalog_activated", False),
    ],
)
def test_input_rejects_non_production_catalog_snapshot(
    field_name: str,
    invalid_value: object,
) -> None:
    valid_input = _input()

    with pytest.raises(ValidationError):
        CoordinatorInput.model_validate({**valid_input.__dict__, field_name: invalid_value})


def test_input_forbids_sensitive_or_free_form_extra_fields_and_emits_no_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    valid_input = _input()
    for forbidden_field in (
        "date_of_birth",
        "age",
        "email",
        "full_name",
        "token",
        "raw_health_record",
    ):
        with pytest.raises(ValidationError):
            CoordinatorInput.model_validate(
                {**valid_input.__dict__, forbidden_field: "SENSITIVE_SENTINEL"}
            )

    with caplog.at_level(logging.DEBUG):
        result = coordinate(valid_input)

    serialized = result.model_dump_json()
    assert "SENSITIVE_SENTINEL" not in serialized
    assert "date_of_birth" not in serialized
    assert "email" not in serialized
    assert caplog.records == []


def test_candidate_contract_rejects_terminal_actions_and_noncanonical_ids() -> None:
    with pytest.raises(ValidationError):
        _candidate(action_code=RecommendedActionCode.REST)

    with pytest.raises(ValidationError):
        _candidate(exercise_ids=("row", "push_up"))
