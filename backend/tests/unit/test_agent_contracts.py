import pytest
from pydantic import ValidationError

from backend.app.domain.agents.contracts import (
    AGENT_PROPOSAL_SCHEMA_VERSION,
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalBatch,
    ProposalBatchStatusCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.rules.duration import DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SafetyStatusCode


def _proposal(
    agent_type_code: AgentTypeCode,
    *,
    proposal_status_code: ProposalStatusCode = ProposalStatusCode.READY,
    requested_duration_minutes: int = 40,
    estimated_duration_seconds: int | None = 2400,
    recommended_action_code: RecommendedActionCode | None = RecommendedActionCode.KEEP,
    preferred_exercise_ids: tuple[str, ...] = (),
    excluded_exercise_ids: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = ("BASE_CANDIDATE_ACCEPTED",),
    policy_version: str = "policy-v1",
    safety_status_code: SafetyStatusCode | None = None,
    safety_vetoed: bool | None = None,
) -> AgentProposal:
    if proposal_status_code is not ProposalStatusCode.READY:
        estimated_duration_seconds = None
        recommended_action_code = None
    if agent_type_code is AgentTypeCode.SAFETY:
        if safety_status_code is None:
            safety_status_code = {
                ProposalStatusCode.READY: SafetyStatusCode.PASS,
                ProposalStatusCode.NEEDS_INPUT: SafetyStatusCode.NEEDS_INPUT,
                ProposalStatusCode.FAILED: SafetyStatusCode.FAILED,
            }[proposal_status_code]
        if safety_vetoed is None:
            safety_vetoed = safety_status_code is not SafetyStatusCode.PASS
    return AgentProposal(
        agent_type_code=agent_type_code,
        proposal_status_code=proposal_status_code,
        recommended_action_code=recommended_action_code,
        requested_duration_minutes=requested_duration_minutes,
        estimated_duration_seconds=estimated_duration_seconds,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        intensity_delta=0,
        required_goal_tags=("UPPER_BODY",),
        preferred_exercise_ids=preferred_exercise_ids,
        excluded_exercise_ids=excluded_exercise_ids,
        hard_constraint_codes=("REQUESTED_DURATION_PRESERVED",),
        reason_codes=reason_codes,
        evidence_reference_codes=("INPUT.requested_duration_minutes",),
        policy_version=policy_version,
        safety_status_code=safety_status_code,
        safety_vetoed=safety_vetoed,
    )


def _batch_with(
    replacement: AgentProposal | None = None,
) -> ProposalBatch:
    proposals = [
        replacement
        if replacement and replacement.agent_type_code is agent_type
        else _proposal(agent_type)
        for agent_type in REQUIRED_AGENT_TYPES
    ]
    return ProposalBatch(proposals=tuple(proposals))


def test_ready_proposal_is_versioned_and_json_serializable() -> None:
    proposal = _proposal(
        AgentTypeCode.TRAINING,
        preferred_exercise_ids=("push_up",),
    )

    payload = proposal.model_dump(mode="json")

    assert payload["schema_version"] == AGENT_PROPOSAL_SCHEMA_VERSION
    assert payload["agent_type_code"] == "TRAINING"
    assert payload["requested_duration_minutes"] == 40
    assert payload["estimated_duration_seconds"] == 2400
    assert "confidence" not in payload


def test_contract_rejects_extra_or_unapproved_enum_fields() -> None:
    payload = _proposal(AgentTypeCode.TRAINING).model_dump()

    with pytest.raises(ValidationError):
        AgentProposal(**payload, internal_reasoning="hidden")

    payload["agent_type_code"] = "UNAPPROVED"
    with pytest.raises(ValidationError):
        AgentProposal(**payload)


@pytest.mark.parametrize("estimated_seconds", [2399, 2401, None])
def test_ready_proposal_must_preserve_requested_duration(
    estimated_seconds: int | None,
) -> None:
    with pytest.raises(ValidationError):
        _proposal(
            AgentTypeCode.RECOVERY,
            estimated_duration_seconds=estimated_seconds,
        )


def test_non_ready_proposal_cannot_claim_action_or_estimated_duration() -> None:
    payload = _proposal(
        AgentTypeCode.TRAINING,
        proposal_status_code=ProposalStatusCode.NEEDS_INPUT,
    ).model_dump()
    payload["recommended_action_code"] = RecommendedActionCode.KEEP

    with pytest.raises(ValidationError):
        AgentProposal(**payload)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("reason_codes", ("HAS FREE TEXT",)),
        ("hard_constraint_codes", ("Z_LAST", "A_FIRST")),
        ("evidence_reference_codes", ("INPUT.same", "INPUT.same")),
    ],
)
def test_reference_fields_are_structured_unique_and_canonical(
    field_name: str,
    invalid_value: tuple[str, ...],
) -> None:
    payload = _proposal(AgentTypeCode.TRAINING).model_dump()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        AgentProposal(**payload)


def test_preferred_and_excluded_exercise_ids_cannot_overlap() -> None:
    with pytest.raises(ValidationError):
        _proposal(
            AgentTypeCode.FEASIBILITY,
            preferred_exercise_ids=("push_up",),
            excluded_exercise_ids=("push_up",),
        )


def test_only_safety_proposal_can_carry_safety_fields() -> None:
    with pytest.raises(ValidationError):
        _proposal(
            AgentTypeCode.TRAINING,
            safety_status_code=SafetyStatusCode.PASS,
            safety_vetoed=False,
        )


@pytest.mark.parametrize(
    ("proposal_status", "safety_status", "vetoed"),
    [
        (ProposalStatusCode.READY, SafetyStatusCode.PASS, True),
        (ProposalStatusCode.READY, SafetyStatusCode.BLOCKED, False),
        (ProposalStatusCode.NEEDS_INPUT, SafetyStatusCode.PASS, False),
        (ProposalStatusCode.FAILED, SafetyStatusCode.NEEDS_INPUT, True),
    ],
)
def test_safety_status_and_veto_must_fail_closed(
    proposal_status: ProposalStatusCode,
    safety_status: SafetyStatusCode,
    vetoed: bool,
) -> None:
    with pytest.raises(ValidationError):
        _proposal(
            AgentTypeCode.SAFETY,
            proposal_status_code=proposal_status,
            safety_status_code=safety_status,
            safety_vetoed=vetoed,
        )


@pytest.mark.parametrize(
    ("safety_status", "action"),
    [
        (SafetyStatusCode.BLOCKED, RecommendedActionCode.KEEP),
        (SafetyStatusCode.PASS, RecommendedActionCode.REST),
        (SafetyStatusCode.REVISE, RecommendedActionCode.STOP_AND_SEEK_HELP),
    ],
)
def test_safety_status_requires_compatible_action(
    safety_status: SafetyStatusCode,
    action: RecommendedActionCode,
) -> None:
    with pytest.raises(ValidationError):
        _proposal(
            AgentTypeCode.SAFETY,
            recommended_action_code=action,
            safety_status_code=safety_status,
            safety_vetoed=safety_status is not SafetyStatusCode.PASS,
        )


def test_failed_factory_does_not_claim_a_plan() -> None:
    failure = AgentProposal.failed(
        agent_type_code=AgentTypeCode.SAFETY,
        requested_duration_minutes=40,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.USER_OVERRIDE,
        policy_version="UNAVAILABLE",
        reason_code="AGENT_EXECUTION_FAILED",
    )

    assert failure.proposal_status_code is ProposalStatusCode.FAILED
    assert failure.recommended_action_code is None
    assert failure.estimated_duration_seconds is None
    assert failure.safety_status_code is SafetyStatusCode.FAILED
    assert failure.safety_vetoed is True


def test_batch_requires_all_agents_in_canonical_order() -> None:
    proposals = tuple(_proposal(agent_type) for agent_type in reversed(REQUIRED_AGENT_TYPES))

    with pytest.raises(ValidationError):
        ProposalBatch(proposals=proposals)


def test_batch_requires_shared_request_and_policy_metadata() -> None:
    proposals = tuple(
        _proposal(
            agent_type,
            policy_version="policy-v2" if agent_type is AgentTypeCode.RECOVERY else "policy-v1",
        )
        for agent_type in REQUIRED_AGENT_TYPES
    )

    with pytest.raises(ValidationError):
        ProposalBatch(proposals=proposals)


def test_failed_status_has_priority_over_needs_input() -> None:
    proposals = tuple(
        _proposal(
            agent_type,
            proposal_status_code=(
                ProposalStatusCode.NEEDS_INPUT
                if agent_type is AgentTypeCode.TRAINING
                else ProposalStatusCode.FAILED
                if agent_type is AgentTypeCode.RECOVERY
                else ProposalStatusCode.READY
            ),
        )
        for agent_type in REQUIRED_AGENT_TYPES
    )
    batch = ProposalBatch(proposals=proposals)

    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert batch.exercise_plan_success_forbidden is True


def test_blocked_safety_proposal_forbids_exercise_plan_success() -> None:
    blocked = _proposal(
        AgentTypeCode.SAFETY,
        recommended_action_code=RecommendedActionCode.REST,
        safety_status_code=SafetyStatusCode.BLOCKED,
        safety_vetoed=True,
    )
    batch = _batch_with(blocked)

    assert batch.status_code is ProposalBatchStatusCode.READY
    assert batch.exercise_plan_success_forbidden is True
    assert batch.by_agent_type(AgentTypeCode.SAFETY) is blocked
