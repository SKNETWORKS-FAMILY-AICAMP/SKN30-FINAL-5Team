import asyncio

from backend.app.domain.agents.v3_contracts import (
    SPECIALIST_AGENT_ORDER,
    ConstraintEnvelope,
    SpecialistAgentTypeCode,
    V3ProposalStatusCode,
)
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.tests.unit.test_v3_agent_contracts import envelope, pool, proposal
from backend.tests.unit.v3_langgraph_test_support import Coordinator, Specialist, graph_input


def test_three_specialists_are_in_flight_together_and_order_is_canonical() -> None:
    async def scenario() -> None:
        current_envelope = envelope()
        current_pool = pool(current_envelope)
        barrier = asyncio.Event()
        active = []
        releases = {agent_type: asyncio.Event() for agent_type in SPECIALIST_AGENT_ORDER}
        specialists = {
            agent_type: Specialist(
                agent_type,
                proposal(agent_type, current_envelope, current_pool),
                barrier=barrier,
                release=releases[agent_type],
                active=active,
            )
            for agent_type in SPECIALIST_AGENT_ORDER
        }
        coordinator = Coordinator()
        current_input = graph_input(
            current_envelope=current_envelope,
            current_pool=current_pool,
            specialists=specialists,
            coordinator=coordinator,
        )
        task = asyncio.create_task(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))
        await barrier.wait()
        assert set(active) == set(SPECIALIST_AGENT_ORDER)
        for agent_type in reversed(SPECIALIST_AGENT_ORDER):
            releases[agent_type].set()
            await asyncio.sleep(0)
        result = await task

        assert result.status_code == "SUCCEEDED"
        assert coordinator.proposal_orders == [SPECIALIST_AGENT_ORDER]

    asyncio.run(scenario())


def test_one_specialist_timeout_cancels_coroutine_and_skips_coordinator() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    specialists = {
        agent_type: Specialist(
            agent_type,
            proposal(agent_type, current_envelope, current_pool),
            timeout=agent_type is SPECIALIST_AGENT_ORDER[1],
        )
        for agent_type in SPECIALIST_AGENT_ORDER
    }
    coordinator = Coordinator()
    current_input = graph_input(
        current_envelope=current_envelope,
        current_pool=current_pool,
        specialists=specialists,
        coordinator=coordinator,
        timeout=0.01,
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.used_fallback
    assert coordinator.initial_calls == 0
    assert specialists[SPECIALIST_AGENT_ORDER[1]].cancelled


def test_needs_input_advisory_reaches_coordinator_without_fallback() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    specialists = {
        agent_type: Specialist(
            agent_type,
            proposal(
                agent_type,
                current_envelope,
                current_pool,
                status=(
                    V3ProposalStatusCode.NEEDS_INPUT
                    if agent_type is SpecialistAgentTypeCode.FEASIBILITY
                    else V3ProposalStatusCode.READY
                ),
            ),
        )
        for agent_type in SPECIALIST_AGENT_ORDER
    }
    coordinator = Coordinator()
    current_input = graph_input(
        current_envelope=current_envelope,
        current_pool=current_pool,
        specialists=specialists,
        coordinator=coordinator,
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.status_code == "SUCCEEDED"
    assert not result.used_fallback
    assert coordinator.initial_calls == 1
    assert len(result.round_one_proposals) == 3
    assert result.round_one_proposals[2].proposal_status_code is V3ProposalStatusCode.NEEDS_INPUT


def test_needs_input_training_still_skips_coordinator() -> None:
    current_envelope = envelope()
    current_pool = pool(current_envelope)
    specialists = {
        agent_type: Specialist(
            agent_type,
            proposal(
                agent_type,
                current_envelope,
                current_pool,
                status=(
                    V3ProposalStatusCode.NEEDS_INPUT
                    if agent_type is SpecialistAgentTypeCode.TRAINING
                    else V3ProposalStatusCode.READY
                ),
                prescriptions=(() if agent_type is SpecialistAgentTypeCode.TRAINING else None),
            ),
        )
        for agent_type in SPECIALIST_AGENT_ORDER
    }
    coordinator = Coordinator()
    current_input = graph_input(
        current_envelope=current_envelope,
        current_pool=current_pool,
        specialists=specialists,
        coordinator=coordinator,
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.used_fallback
    assert coordinator.initial_calls == 0
    assert "V3_TRAINING_NOT_READY" in result.failure_codes


def test_proposal_for_another_envelope_is_invalid_and_skips_coordinator() -> None:
    """ADR-0022: a contract breach carries its own code.

    Both this and the agent declining its inputs above reported
    V3_TRAINING_NOT_READY until a paid held-out run had to tell them apart
    after the fact and could not.
    """

    current_envelope = envelope()
    current_pool = pool(current_envelope)
    other_values = current_envelope.model_dump(exclude={"envelope_hash"})
    other_values["primary_goal_code"] = "MOBILITY"
    other_envelope = ConstraintEnvelope.create(**other_values)
    other_pool = pool(other_envelope)
    specialists = {
        agent_type: Specialist(
            agent_type,
            (
                proposal(agent_type, other_envelope, other_pool)
                if agent_type is SpecialistAgentTypeCode.TRAINING
                else proposal(agent_type, current_envelope, current_pool)
            ),
        )
        for agent_type in SPECIALIST_AGENT_ORDER
    }
    coordinator = Coordinator()
    current_input = graph_input(
        current_envelope=current_envelope,
        current_pool=current_pool,
        specialists=specialists,
        coordinator=coordinator,
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert result.used_fallback
    assert coordinator.initial_calls == 0
    assert "V3_TRAINING_PROPOSAL_INVALID" in result.failure_codes
    assert "V3_TRAINING_NOT_READY" not in result.failure_codes


def test_a_declining_training_still_reports_its_tokens_and_its_reason() -> None:
    """Both were dropped, and both mattered to the held-out analysis.

    Telemetry: the audit summed 0 tokens for a declined call, so a run where
    Training declined reported roughly 6,500 tokens where ~16,700 had been
    spent -- under-reporting the cost of exactly the runs that failed.

    Reason codes: the Training prompt asks the agent to name the condition it
    declined on, and the graph discarded that with the rejected proposal.
    """

    current_envelope = envelope()
    current_pool = pool(current_envelope)
    specialists = {
        agent_type: Specialist(
            agent_type,
            proposal(
                agent_type,
                current_envelope,
                current_pool,
                status=(
                    V3ProposalStatusCode.NEEDS_INPUT
                    if agent_type is SpecialistAgentTypeCode.TRAINING
                    else V3ProposalStatusCode.READY
                ),
                prescriptions=(() if agent_type is SpecialistAgentTypeCode.TRAINING else None),
            ),
        )
        for agent_type in SPECIALIST_AGENT_ORDER
    }
    current_input = graph_input(
        current_envelope=current_envelope,
        current_pool=current_pool,
        specialists=specialists,
        coordinator=Coordinator(),
    )

    result = asyncio.run(V3LangGraphRuntime(create_v3_graph()).ainvoke(current_input))

    assert "V3_TRAINING_NOT_READY" in result.failure_codes
    training = next(audit for audit in result.invocation_audits if audit.role_code == "TRAINING")
    assert training.decline_reason_codes == ("GOAL_PRESERVED",)
    assert training.attempt_count > 0, "a declined call still cost an attempt"
