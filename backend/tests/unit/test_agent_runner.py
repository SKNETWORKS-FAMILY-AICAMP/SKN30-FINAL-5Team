from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, field
from threading import Barrier

import pytest

from backend.app.domain.agents.contracts import (
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalBatchStatusCode,
    ProposalStatusCode,
    RecommendedActionCode,
)
from backend.app.domain.agents.runner import ProposalRequest, run_required_agents
from backend.app.domain.rules.duration import DurationAdjustmentSourceCode
from backend.app.domain.rules.safety import SafetyStatusCode

Context = tuple[str, ...]
Candidate = str
Request = ProposalRequest[Context, Candidate]


def _request() -> Request:
    return ProposalRequest(
        context=("normalized-context-v1",),
        candidates=("base-candidate-v1",),
        candidate_exercise_ids=("push_up", "row"),
        requested_duration_minutes=40,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        policy_version="policy-v1",
    )


def _ready_proposal(
    agent_type_code: AgentTypeCode,
    *,
    policy_version: str = "policy-v1",
    requested_duration_minutes: int = 40,
    preferred_exercise_ids: tuple[str, ...] = (),
) -> AgentProposal:
    is_safety = agent_type_code is AgentTypeCode.SAFETY
    return AgentProposal(
        agent_type_code=agent_type_code,
        proposal_status_code=ProposalStatusCode.READY,
        recommended_action_code=RecommendedActionCode.KEEP,
        requested_duration_minutes=requested_duration_minutes,
        estimated_duration_seconds=requested_duration_minutes * 60,
        duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
        preferred_exercise_ids=preferred_exercise_ids,
        reason_codes=("BASE_CANDIDATE_ACCEPTED",),
        evidence_reference_codes=("INPUT.requested_duration_minutes",),
        policy_version=policy_version,
        safety_status_code=SafetyStatusCode.PASS if is_safety else None,
        safety_vetoed=False if is_safety else None,
    )


@dataclass
class StubAgent:
    agent_type_code: AgentTypeCode
    proposal_factory: Callable[[Request], AgentProposal]
    policy_version: str = "policy-v1"
    seen_requests: list[Request] = field(default_factory=list)

    def propose(self, request: Request) -> AgentProposal:
        self.seen_requests.append(request)
        return self.proposal_factory(request)


@dataclass
class InvalidRegistrationAgent:
    agent_type_code: object
    policy_version: str = "policy-v1"

    def propose(self, _request: Request) -> AgentProposal:
        return _ready_proposal(AgentTypeCode.TRAINING)


def _agents() -> list[StubAgent]:
    return [
        StubAgent(
            agent_type,
            lambda _request, agent_type=agent_type: _ready_proposal(agent_type),
        )
        for agent_type in REQUIRED_AGENT_TYPES
    ]


def test_runner_executes_all_agents_with_same_frozen_request_in_parallel() -> None:
    request = _request()
    barrier = Barrier(len(REQUIRED_AGENT_TYPES))

    def wait_and_propose(agent_type: AgentTypeCode) -> Callable[[Request], AgentProposal]:
        def factory(_request: Request) -> AgentProposal:
            barrier.wait(timeout=5)
            return _ready_proposal(agent_type)

        return factory

    agents = [
        StubAgent(agent_type, wait_and_propose(agent_type)) for agent_type in REQUIRED_AGENT_TYPES
    ]

    batch = run_required_agents(request=request, agents=agents)

    assert batch.status_code is ProposalBatchStatusCode.READY
    assert tuple(proposal.agent_type_code for proposal in batch.proposals) == REQUIRED_AGENT_TYPES
    assert all(agent.seen_requests == [request] for agent in agents)
    assert all(agent.seen_requests[0] is request for agent in agents)
    with pytest.raises(FrozenInstanceError):
        request.policy_version = "changed"  # type: ignore[misc]


def test_missing_agent_fails_closed() -> None:
    request = _request()
    agents = [agent for agent in _agents() if agent.agent_type_code is not AgentTypeCode.RECOVERY]

    batch = run_required_agents(request=request, agents=agents)

    failure = batch.by_agent_type(AgentTypeCode.RECOVERY)
    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert batch.exercise_plan_success_forbidden is True
    assert failure.reason_codes == ("AGENT_MISSING",)


def test_duplicate_agent_registration_fails_closed() -> None:
    request = _request()
    agents = _agents()
    agents.append(
        StubAgent(
            AgentTypeCode.TRAINING,
            lambda _request: _ready_proposal(AgentTypeCode.TRAINING),
        )
    )

    batch = run_required_agents(request=request, agents=agents)

    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert batch.by_agent_type(AgentTypeCode.TRAINING).reason_codes == (
        "AGENT_REGISTRATION_DUPLICATE",
    )


def test_invalid_agent_registration_fails_entire_batch_closed() -> None:
    request = _request()
    agents: list[object] = [*_agents(), InvalidRegistrationAgent(agent_type_code="TRAINING")]

    batch = run_required_agents(request=request, agents=agents)  # type: ignore[arg-type]

    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert all(
        proposal.reason_codes == ("AGENT_REGISTRATION_INVALID",) for proposal in batch.proposals
    )
    assert all(proposal.policy_version == request.policy_version for proposal in batch.proposals)


def test_agent_exception_is_redacted_to_fixed_failure_code() -> None:
    request = _request()

    def raise_sensitive_exception(_request: Request) -> AgentProposal:
        raise RuntimeError("DIRECT_IDENTIFIER_SENTINEL raw check-in")

    agents = _agents()
    agents[0] = StubAgent(AgentTypeCode.TRAINING, raise_sensitive_exception)

    batch = run_required_agents(request=request, agents=agents)

    failure = batch.by_agent_type(AgentTypeCode.TRAINING)
    serialized = failure.model_dump_json()
    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert failure.reason_codes == ("AGENT_EXECUTION_FAILED",)
    assert "DIRECT_IDENTIFIER_SENTINEL" not in serialized
    assert "check-in" not in serialized


@pytest.mark.parametrize(
    "invalid_proposal",
    [
        _ready_proposal(AgentTypeCode.RECOVERY),
        _ready_proposal(AgentTypeCode.TRAINING, policy_version="policy-v2"),
        _ready_proposal(AgentTypeCode.TRAINING, requested_duration_minutes=30),
        _ready_proposal(
            AgentTypeCode.TRAINING,
            preferred_exercise_ids=("unapproved_exercise",),
        ),
    ],
)
def test_invalid_agent_result_fails_closed(invalid_proposal: AgentProposal) -> None:
    request = _request()
    agents = _agents()
    agents[0] = StubAgent(AgentTypeCode.TRAINING, lambda _request: invalid_proposal)

    batch = run_required_agents(request=request, agents=agents)

    failure = batch.by_agent_type(AgentTypeCode.TRAINING)
    assert batch.status_code is ProposalBatchStatusCode.FAILED
    assert failure.reason_codes == ("AGENT_RESULT_INVALID",)


def test_registered_policy_version_must_match_request() -> None:
    request = _request()
    agents = _agents()
    agents[0].policy_version = "policy-v2"

    batch = run_required_agents(request=request, agents=agents)

    assert batch.by_agent_type(AgentTypeCode.TRAINING).reason_codes == ("AGENT_RESULT_INVALID",)


def test_needs_input_batch_withholds_plan_without_marking_agent_failed() -> None:
    request = _request()
    agents = _agents()
    agents[0] = StubAgent(
        AgentTypeCode.TRAINING,
        lambda _request: AgentProposal(
            agent_type_code=AgentTypeCode.TRAINING,
            proposal_status_code=ProposalStatusCode.NEEDS_INPUT,
            requested_duration_minutes=40,
            duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
            reason_codes=("GOAL_INPUT_REQUIRED",),
            policy_version="policy-v1",
        ),
    )

    batch = run_required_agents(request=request, agents=agents)

    assert batch.status_code is ProposalBatchStatusCode.NEEDS_INPUT
    assert batch.exercise_plan_success_forbidden is True
    assert (
        batch.by_agent_type(AgentTypeCode.TRAINING).proposal_status_code
        is ProposalStatusCode.NEEDS_INPUT
    )


def test_request_rejects_noncanonical_or_invalid_execution_metadata() -> None:
    with pytest.raises(ValueError):
        ProposalRequest(
            context=("normalized",),
            candidates=("candidate",),
            candidate_exercise_ids=("row", "push_up"),
            requested_duration_minutes=40,
            duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
            policy_version="policy-v1",
        )

    with pytest.raises(ValueError):
        ProposalRequest(
            context=("normalized",),
            candidates=("candidate",),
            candidate_exercise_ids=("push_up",),
            requested_duration_minutes=0,
            duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
            policy_version="policy v1",
        )

    with pytest.raises(ValueError):
        ProposalRequest(
            context=("normalized",),
            candidates=("candidate",),
            candidate_exercise_ids=("push@up",),
            requested_duration_minutes=True,
            duration_adjustment_source_code=DurationAdjustmentSourceCode.PROFILE,
            policy_version="policy-v1",
        )
