from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models.decision import AgentProposalRecord, DecisionRun, PlanCandidate
from backend.app.db.models.v3_decision import DecisionConstraintEnvelopeRecord
from backend.app.domain.agents.retrieval import (
    ExerciseRetrievalRequest,
    RetrievalStatusCode,
)
from backend.app.integrations.langgraph.demo_runtime import V3DemoRuntime
from backend.app.integrations.langgraph.graph import V3LangGraphRuntime, create_v3_graph
from backend.app.integrations.llm_agents.provider import StructuredChatInvoker
from backend.app.integrations.qdrant.exercise_retriever import deterministic_retrieval_fallback
from backend.app.integrations.qdrant.snapshot_loader import QdrantExercisePoolSnapshotLoader
from backend.app.modules.decisions.v3_application import (
    DeterministicV3SafetyPolicyAdapter,
    FailClosedV3ApplicationFallback,
    PostgreSQLV3ExercisePoolSource,
    SqlAlchemyV3CreationUnitOfWork,
    V3DecisionResponseProjector,
)
from backend.app.modules.decisions.v3_creation import V3InitialCreationService
from backend.tests.integration.test_decision_repository import (
    LOCAL_DATE,
    _add_user,
    _prepare_decision_inputs,
    _request,
    postgres_session,  # noqa: F401
)
from backend.tests.unit.test_v3_demo_runtime import _successful_model


class DeterministicRetriever:
    calls = 0

    def retrieve(self, request: ExerciseRetrievalRequest):
        self.calls += 1
        return deterministic_retrieval_fallback(
            request, status=RetrievalStatusCode.VECTOR_INDEX_UNAVAILABLE
        )


class Runtime:
    async def create(self, *, root_snapshot):
        model = _successful_model(root_snapshot)
        runtime = V3DemoRuntime(
            settings=Settings(
                _env_file=None,
                app_env="staging",
                llm_agents_model_code="fake-model-v1",
            ),
            graph_runtime=V3LangGraphRuntime(create_v3_graph()),
            invoker=StructuredChatInvoker(
                chat_model=model,
                model_code="fake-model-v1",
                max_attempts=1,
            ),
        )
        return await runtime.create(root_snapshot=root_snapshot)


@pytest.mark.integration
def test_creation_persists_public_plan_and_separate_v3_artifacts_atomically(
    request: pytest.FixtureRequest,
) -> None:
    session: Session = request.getfixturevalue("postgres_session")
    user_id = _add_user(session, attention_areas=())
    daily_context_id = _prepare_decision_inputs(session, user_id)
    retriever = DeterministicRetriever()
    service = V3InitialCreationService(
        unit_of_work_factory=SqlAlchemyV3CreationUnitOfWork,
        safety_policy=DeterministicV3SafetyPolicyAdapter(),
        exercise_pool_loader=QdrantExercisePoolSnapshotLoader(
            catalog=PostgreSQLV3ExercisePoolSource(), retriever=retriever
        ),
        graph_runtime=Runtime(),
        fallback=FailClosedV3ApplicationFallback(),
        projector=V3DecisionResponseProjector(),
    )

    response = asyncio.run(service.create(session, user_id, _request(daily_context_id), uuid4()))

    run = session.get(DecisionRun, response.decision_id)
    assert run is not None
    assert response.local_date == LOCAL_DATE
    assert response.final_plan is not None
    assert run.root_decision_run_id == run.id
    assert run.decision_engine_code in {
        "LLM_MULTI_AGENT",
        "DETERMINISTIC_FALLBACK",
    }
    assert (
        session.scalar(
            select(func.count(AgentProposalRecord.id)).where(
                AgentProposalRecord.decision_run_id == run.id
            )
        )
        == 3
    )
    assert (
        session.scalar(
            select(func.count(PlanCandidate.id)).where(PlanCandidate.decision_run_id == run.id)
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count(DecisionConstraintEnvelopeRecord.id)).where(
                DecisionConstraintEnvelopeRecord.root_decision_run_id == run.id
            )
        )
        == 1
    )
    assert retriever.calls == 1
