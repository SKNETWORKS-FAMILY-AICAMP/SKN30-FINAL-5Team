"""Fail-closed parallel execution boundary for required specialist agents."""

from __future__ import annotations

import re
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from backend.app.domain.agents.contracts import (
    REQUIRED_AGENT_TYPES,
    AgentProposal,
    AgentTypeCode,
    ProposalBatch,
)
from backend.app.domain.rules.duration import DurationAdjustmentSourceCode

_MACHINE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _require_machine_reference(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _MACHINE_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a non-empty machine reference")


@dataclass(frozen=True, slots=True)
class ProposalRequest[ContextT, CandidateT]:
    """One immutable envelope shared by all four agents.

    Context and candidate payload schemas remain owned by their later tasks. The caller must
    provide a normalized, identifier-free context and approved common candidates.
    """

    context: ContextT
    candidates: tuple[CandidateT, ...]
    candidate_exercise_ids: tuple[str, ...]
    requested_duration_minutes: int
    duration_adjustment_source_code: DurationAdjustmentSourceCode
    policy_version: str

    def __post_init__(self) -> None:
        if self.context is None:
            raise ValueError("context is required")
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise ValueError("approved common candidates must be a non-empty tuple")
        if not isinstance(self.candidate_exercise_ids, tuple) or not self.candidate_exercise_ids:
            raise ValueError("candidate_exercise_ids must be a non-empty tuple")
        if len(self.candidate_exercise_ids) != len(set(self.candidate_exercise_ids)):
            raise ValueError("candidate_exercise_ids must not contain duplicates")
        if self.candidate_exercise_ids != tuple(sorted(self.candidate_exercise_ids)):
            raise ValueError("candidate_exercise_ids must use canonical sorted order")
        for exercise_id in self.candidate_exercise_ids:
            _require_machine_reference(exercise_id, field_name="candidate_exercise_ids")
        if type(self.requested_duration_minutes) is not int:
            raise ValueError("requested_duration_minutes must be an integer")
        if self.requested_duration_minutes <= 0:
            raise ValueError("requested_duration_minutes must be positive")
        if not isinstance(self.duration_adjustment_source_code, DurationAdjustmentSourceCode):
            raise ValueError("duration_adjustment_source_code is invalid")
        _require_machine_reference(self.policy_version, field_name="policy_version")


class ProposalAgent[ContextT, CandidateT](Protocol):
    agent_type_code: AgentTypeCode
    policy_version: str

    def propose(
        self,
        request: ProposalRequest[ContextT, CandidateT],
    ) -> AgentProposal: ...


def _failed_proposal[ContextT, CandidateT](
    *,
    agent_type_code: AgentTypeCode,
    request: ProposalRequest[ContextT, CandidateT],
    reason_code: str,
) -> AgentProposal:
    return AgentProposal.failed(
        agent_type_code=agent_type_code,
        requested_duration_minutes=request.requested_duration_minutes,
        duration_adjustment_source_code=request.duration_adjustment_source_code,
        policy_version=request.policy_version,
        reason_code=reason_code,
    )


def _validated_result[ContextT, CandidateT](
    *,
    expected_agent_type: AgentTypeCode,
    agent: ProposalAgent[ContextT, CandidateT],
    request: ProposalRequest[ContextT, CandidateT],
) -> AgentProposal:
    try:
        proposal = agent.propose(request)
    except Exception:
        return _failed_proposal(
            agent_type_code=expected_agent_type,
            request=request,
            reason_code="AGENT_EXECUTION_FAILED",
        )

    try:
        if not isinstance(proposal, AgentProposal):
            raise ValueError("agent returned an invalid proposal type")
        if proposal.agent_type_code is not expected_agent_type:
            raise ValueError("proposal agent type does not match registration")
        if agent.policy_version != request.policy_version:
            raise ValueError("registered policy version does not match request")
        if proposal.policy_version != request.policy_version:
            raise ValueError("proposal policy version does not match request")
        if proposal.requested_duration_minutes != request.requested_duration_minutes:
            raise ValueError("proposal requested duration does not match request")
        if proposal.duration_adjustment_source_code is not request.duration_adjustment_source_code:
            raise ValueError("proposal duration source does not match request")
        referenced_exercise_ids = set(proposal.preferred_exercise_ids) | set(
            proposal.excluded_exercise_ids
        )
        if not referenced_exercise_ids.issubset(request.candidate_exercise_ids):
            raise ValueError("proposal references an exercise outside the common candidates")
    except Exception:
        return _failed_proposal(
            agent_type_code=expected_agent_type,
            request=request,
            reason_code="AGENT_RESULT_INVALID",
        )
    return proposal


def run_required_agents[ContextT, CandidateT](
    *,
    request: ProposalRequest[ContextT, CandidateT],
    agents: Sequence[ProposalAgent[ContextT, CandidateT]],
) -> ProposalBatch:
    """Run one of each required agent concurrently and return a canonical batch.

    Agent exceptions and configuration defects become fixed failure codes. Exception text and
    request contents are intentionally never copied to proposals or logs.
    """

    registered: dict[AgentTypeCode, list[ProposalAgent[ContextT, CandidateT]]] = {
        agent_type: [] for agent_type in REQUIRED_AGENT_TYPES
    }
    registration_invalid = False
    for agent in agents:
        try:
            agent_type = agent.agent_type_code
        except AttributeError:
            registration_invalid = True
            continue
        if not isinstance(agent_type, AgentTypeCode):
            registration_invalid = True
            continue
        registered[agent_type].append(agent)

    if registration_invalid:
        return ProposalBatch(
            proposals=tuple(
                _failed_proposal(
                    agent_type_code=agent_type,
                    request=request,
                    reason_code="AGENT_REGISTRATION_INVALID",
                )
                for agent_type in REQUIRED_AGENT_TYPES
            )
        )

    results: dict[AgentTypeCode, AgentProposal] = {}
    runnable: dict[AgentTypeCode, ProposalAgent[ContextT, CandidateT]] = {}
    for agent_type in REQUIRED_AGENT_TYPES:
        matching_agents = registered[agent_type]
        if not matching_agents:
            results[agent_type] = _failed_proposal(
                agent_type_code=agent_type,
                request=request,
                reason_code="AGENT_MISSING",
            )
        elif len(matching_agents) > 1:
            results[agent_type] = _failed_proposal(
                agent_type_code=agent_type,
                request=request,
                reason_code="AGENT_REGISTRATION_DUPLICATE",
            )
        else:
            runnable[agent_type] = matching_agents[0]

    futures: dict[AgentTypeCode, Future[AgentProposal]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(runnable))) as executor:
        for agent_type, agent in runnable.items():
            futures[agent_type] = executor.submit(
                _validated_result,
                expected_agent_type=agent_type,
                agent=agent,
                request=request,
            )
        for agent_type, future in futures.items():
            results[agent_type] = future.result()

    return ProposalBatch(
        proposals=tuple(results[agent_type] for agent_type in REQUIRED_AGENT_TYPES)
    )
