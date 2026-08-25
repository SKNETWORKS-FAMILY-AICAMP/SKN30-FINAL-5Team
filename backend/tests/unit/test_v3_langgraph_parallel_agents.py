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


def test_non_ready_specialist_never_allows_partial_coordinator_input() -> None:
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

    assert result.used_fallback
    assert coordinator.initial_calls == 0


def test_proposal_for_another_envelope_is_invalid_and_skips_coordinator() -> None:
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
